"""Read-only, evidence-limited GEO report projection.

Perplexity Search API retrieval is not proof of generative answer inclusion.
This projection must never create a search request or write to audit.db.
"""
from __future__ import annotations

from contextlib import closing

from collections import Counter
from html import escape
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _observations(database: Path, audit_id: str) -> tuple[list[dict], list[dict]]:
    # mode=ro forbids any schema initialization/mutation during report generation.
    with closing(sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)) as con:
        existing = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('perplexity_search_runs','perplexity_search_sources')"
            )
        }
        if len(existing) < 2:
            return [], []
        columns = {row[1] for row in con.execute("PRAGMA table_info(perplexity_search_runs)")}
        optional = ", ".join(
            field if field in columns else "NULL AS " + field
            for field in ("error_class", "http_status", "error_code")
        )
        con.row_factory = sqlite3.Row
        runs = [dict(r) for r in con.execute(
            "SELECT run_id, query_json, search_type, status, started_at, " + optional +
            " FROM perplexity_search_runs WHERE audit_id=? ORDER BY started_at, run_id",
            (audit_id,),
        )]
        if not runs:
            return [], []
        sources = [dict(r) for r in con.execute(
            "SELECT s.run_id, s.position, s.url, s.title, s.snippet "
            "FROM perplexity_search_sources s "
            "JOIN perplexity_search_runs r ON r.run_id=s.run_id "
            "WHERE r.audit_id=? ORDER BY r.started_at, s.position", (audit_id,)
        )]
    return runs, sources



def _stored_comparison(database: Path, audit_id: str) -> dict | None:
    """Read only the frozen GEO observation snapshot; never derive metrics in HTML."""
    with sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True) as con:
        table = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='geo_observation_runs'"
        ).fetchone()
        if table is None:
            return None
        row = con.execute(
            "SELECT projection_json FROM geo_observation_runs WHERE audit_id=? "
            "ORDER BY created_at DESC, analysis_id DESC LIMIT 1", (audit_id,)
        ).fetchone()
    if row is None:
        return None
    try:
        result = json.loads(row[0])
    except (ValueError, TypeError):
        return None
    return result if isinstance(result, dict) else None



def _prior_competitive_ai(database: Path, audit_id: str, serp_id: str | None) -> dict | None:
    """Consume only a previously persisted, canonical competitive-AI assessment.

    This adapter neither invokes a provider nor creates an AI task. Existing
    source consumer owns evidence validation and provider/usage provenance.
    """
    if not serp_id:
        return None
    with closing(sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)) as con:
        if not con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='serp_competitive_ai_analyses'"
        ).fetchone():
            return None
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT observation_id,state,provider,model,contract_version,prompt_id,"
            "prompt_version,summary,opportunities_json,evidence_ref,evidence_sha256 "
            "FROM serp_competitive_ai_analyses "
            "WHERE audit_id=? AND observation_id=? AND state='AVAILABLE'",
            (audit_id, serp_id),
        ).fetchone()
    if row is None:
        return None
    assessment = dict(row)
    try:
        opportunities = json.loads(assessment["opportunities_json"] or "[]")
    except (TypeError, ValueError):
        return None
    if not isinstance(opportunities, list):
        return None
    # Reject opportunity entries without provenance identifiers; do not
    # manufacture evidence to make AI claims appear more confident.
    assessment["opportunities"] = [
        o for o in opportunities
        if isinstance(o, dict) and isinstance(o.get("evidence_ids"), list)
        and o["evidence_ids"] and all(isinstance(i, str) and i.strip() for i in o["evidence_ids"])
    ]
    return assessment




def _geo_relevant_findings(database: Path, audit_id: str) -> list[dict]:
    """Map only observed audit issues to review candidates; never infer causality."""
    with closing(sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)) as con:
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('findings','recommendations')"
        )}
        if "findings" not in tables:
            return []
        con.row_factory = sqlite3.Row
        findings = [dict(r) for r in con.execute(
            "SELECT finding_id, rule_id, category, severity, title, evidence_ids, "
            "observed_value, expected_condition FROM findings WHERE audit_id=? "
            "ORDER BY CASE UPPER(severity) WHEN 'CRITICAL' THEN 0 "
            "WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END, finding_id",
            (audit_id,),
        )]
        # A rule's title and category are useful heuristics for routing human
        # inspection, not proof that the issue affects AI answer ranking.
        terms = ("CONTENT", "SEMANTIC", "STRUCTURE", "HTML", "INDEX",
                 "CRAWL", "CANONICAL", "DISCOVER", "ENTITY", "SCHEMA", "META",
                 "ROBOTS", "SITEMAP", "SEARCH", "JSON_LD")
        eligible = [
            item for item in findings
            if any(term in (
                str(item.get("category") or "") + " " +
                str(item.get("rule_id") or "") + " " +
                str(item.get("title") or "")
            ).upper() for term in terms)
        ][:12]
        if "recommendations" in tables and eligible:
            ids = [item["finding_id"] for item in eligible]
            placeholders = ",".join("?" for _ in ids)
            rows = con.execute(
                "SELECT finding_id, title, description, priority_class FROM recommendations "
                "WHERE audit_id=? AND finding_id IN (" + placeholders + ") "
                "ORDER BY priority_score DESC",
                (audit_id, *ids),
            )
            recommendations = {}
            for row in rows:
                recommendations.setdefault(row["finding_id"], dict(row))
            for item in eligible:
                item["existing_recommendation"] = recommendations.get(item["finding_id"])
    return eligible




def _geo_ai_result(database: Path, audit_id: str, latest_run_id: str) -> dict | None:
    """Read an already-persisted GEO interpretation without AI calls."""
    with closing(sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)) as con:
        if not con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='geo_ai_interpretations'"
        ).fetchone():
            return None
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT state, provider, model, prompt_id, prompt_version, "
            "summary, opportunities_json, input_sha256, error_reason "
            "FROM geo_ai_interpretations WHERE audit_id=? AND perplexity_run_id=? "
            "ORDER BY created_at DESC, result_id DESC LIMIT 1",
            (audit_id, latest_run_id),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    try:
        opportunities = json.loads(result["opportunities_json"] or "[]")
    except (ValueError, TypeError):
        opportunities = []
    result["opportunities"] = [
        x for x in opportunities
        if isinstance(x, dict) and isinstance(x.get("evidence_ids"), list)
        and x["evidence_ids"]
    ] if isinstance(opportunities, list) else []
    return result



def geo_body(database: Path, audit_id: str) -> str:
    """Evidence-backed readout; no scores, causal attribution or speculative gaps."""
    runs, sources = _observations(database, audit_id)
    # Scoped component styling: no global report layout or engine changes.
    style = """
    <style>
    .geo-view {--geo-border:#dbe4ee;--geo-surface:#fff;--geo-muted:#526579;
      --geo-accent:#126b86;display:grid;gap:1.25rem;max-width:100%}
    .geo-view > h1 {margin:.2rem 0 0;font-size:clamp(1.5rem,2.6vw,2rem);line-height:1.25}
    .geo-view > p {color:var(--geo-muted);max-width:88ch;line-height:1.65;margin:0 0 .25rem}
    .geo-view > section {background:var(--geo-surface);border:1px solid var(--geo-border);
      border-left:4px solid var(--geo-accent);border-radius:12px;padding:1.3rem 1.5rem;
      box-shadow:0 3px 14px rgba(20,42,66,.045);min-width:0}
    .geo-view > section:nth-of-type(even) {border-left-color:#5774b9}
    .geo-view section h2 {margin:0 0 .85rem;font-size:1.15rem;letter-spacing:-.01em}
    .geo-view section p {line-height:1.6;color:var(--geo-muted);margin:.65rem 0}
    .geo-view section table {display:block;overflow-x:auto;width:100%;border-collapse:collapse}
    .geo-view section th,.geo-view section td {padding:.75rem .8rem;text-align:left;
      border-bottom:1px solid var(--geo-border);vertical-align:top;overflow-wrap:anywhere}
    .geo-view section th {background:#eef4f9;color:#243f58;font-weight:650}
    .geo-view section li {margin:.55rem 0;line-height:1.6}
    .geo-view section a {text-underline-offset:3px}
    .geo-view > section:focus-within {outline:2px solid #abd3e0;outline-offset:2px}
    @media(max-width:650px){.geo-view{gap:.85rem}.geo-view>section{padding:1rem}
      .geo-view section th,.geo-view section td{padding:.6rem;font-size:.9rem}}
    </style>
    """
    header = (
        "<h1>GEO — Oportunidades para pesquisa orientada por IA</h1>"
        "<p>Esta página reúne observações externas e orientações de análise. "
        "A presença em fontes da Perplexity Search API não comprova inclusão, "
        "recomendação ou citação em respostas de IAs de outros buscadores. "
        "Melhorias representam boas práticas, nunca garantia de visibilidade.</p>"
    )
    if not runs:
        return style + '<div class="geo-view">' + header + (
            "<section><h2>Estado da observação</h2><p>Não há execução "
            "Perplexity Search persistida nesta auditoria. "
            "Pode estar não solicitada, desabilitada ou sem aquisição registrada. "
            "Sem dados, não é possível concluir presença ou ausência da URL em AI Search.</p></section>"
            "<p>Detalhes técnicos: <a href='cat-05.html'>CAT-05</a>; "
            "<a href='ai-integrations.html'>IA e integrações</a>.</p>"
        ) + "</div>"
    counts = Counter(_host(x["url"]) for x in sources if _host(x["url"]))
    summary = "<section><h2>Observações recuperadas</h2>"
    summary += f"<p>{len(runs)} execução(ões) persistida(s); {len(sources)} fonte(s) recuperada(s).</p>"
    summary += "<p>O denominador refere-se a resultados externos, não a respostas generativas. "
    summary += "Consultas agrupadas em um request não autorizam atribuir cada fonte a uma query individual.</p>"
    summary += "<table><thead><tr><th>Run</th><th>Consultas</th><th>Status</th><th>Modo</th></tr></thead><tbody>"
    for run in runs:
        try:
            queries = json.loads(run["query_json"])
        except (TypeError, ValueError):
            queries = "(registro indisponível)"
        qs = "; ".join(map(str, queries)) if isinstance(queries, list) else str(queries)
        summary += "<tr>" + "".join(
            f"<td>{escape(str(value or '-'))}</td>"
            for value in (run["run_id"], qs, run["status"], run["search_type"])
        ) + "</tr>"
    summary += "</tbody></table>"
    latest_status = str(runs[-1].get("status") or "UNAVAILABLE").upper()
    explanations = {
        "NOT_CONFIGURED": "Credencial não configurada. Revise a chave PERPLEXITY_API_KEY no menu de integrações.",
        "SUCCESS": "A pesquisa retornou fontes; presença em resultado de busca não equivale a citação em resposta generativa.",
        "TIMEOUT_ERROR": "A requisição externa excedeu o tempo; o diagnóstico RASAi permanece utilizável.",
        "NETWORK_ERROR": "Falha de comunicação externa; auditoria e catálogos continuam íntegros.",
        "AUTH_ERROR": "Autenticação recusada; confira validade da chave Perplexity.",
        "PERMISSION_ERROR": "Permissão insuficiente para a Search API.",
        "QUOTA_ERROR": "Limitação de quota/crédito do serviço externo.",
        "RATE_LIMIT_ERROR": "Limite de frequência externo. Não houve repetição automática pela projeção GEO.",
        "INVALID_RESPONSE": "Resposta externa fora do contrato esperado. Não inferir resultados ausentes.",
    }
    explanation = explanations.get(
        latest_status,
        "Fonte externa indisponível ou com erro; não inferir ausência da URL."
    )
    summary += "<p>Estado mais recente: <strong>" + escape(latest_status) + "</strong> - "
    summary += escape(explanation) + "</p>"
    if runs[-1].get("http_status") is not None:
        summary += "<p>HTTP externo: " + escape(str(runs[-1]["http_status"])) + "</p>"
    if runs[-1].get("error_code"):
        summary += "<p>Código externo: " + escape(str(runs[-1]["error_code"])) + "</p>"
    summary += "</section>"
    comparison = _stored_comparison(database, audit_id)
    if comparison is not None and comparison.get("perplexity_run_id") != runs[-1]["run_id"]:
        # Never promote a previous successful snapshot to the latest failed attempt.
        comparison = None
    summary += "<section><h2>Comparação SERP × Perplexity</h2>"
    if comparison is None or comparison.get("serp_observation_id") is None:
        summary += "<p>Comparação não aplicável: não há snapshot de análise GEO "
        summary += "com consulta única e observação SERP live válida. Requests multi-query "
        summary += "não são desagregados artificialmente.</p>"
    else:
        summary += "<p>Sobreposição observacional de URLs exatas na mesma consulta: "
        summary += f"{int(comparison.get('url_overlap_count') or 0)} em ambas; "
        summary += f"{int(comparison.get('serp_url_count') or 0)} URLs SERP e "
        summary += f"{int(comparison.get('perplexity_url_count') or 0)} URLs Perplexity."
        summary += " Não demonstra causalidade, ranking equivalente ou citação generativa.</p>"
    summary += "</section>"
    if comparison:
        target = comparison.get("target_observation") or {}
        status = str(target.get("status") or "UNAVAILABLE")
        labels = {
            "EXACT_URL_OBSERVED": "URL auditada recuperada nesta observação",
            "DOMAIN_ALTERNATIVE_OBSERVED": "Domínio recuperado por URL alternativa",
            "TARGET_NOT_IN_RETURNED_SOURCES": "URL/domínio não recuperados nas fontes retornadas",
            "NOT_COMPARABLE": "Comparação com o alvo indisponível",
            "UNAVAILABLE": "Observação inconclusiva",
        }
        summary += "<section><h2>Alvo auditado — leitura GEO</h2>"
        summary += "<p><strong>" + escape(labels.get(status, "Indisponível")) + "</strong></p>"
        if target.get("query"):
            summary += "<p>Consulta: " + escape(str(target["query"])) + "</p>"
        if target.get("target_url"):
            summary += "<p>URL analisada: " + escape(str(target["target_url"])) + "</p>"
        if target.get("recommendation"):
            summary += "<p>Ação para avaliação: " + escape(str(target["recommendation"])) + "</p>"
        if target.get("evidence_run_id"):
            summary += "<p>Run de origem: " + escape(str(target["evidence_run_id"])) + "</p>"
        summary += "<p>Este resultado não determina por que uma URL foi ou não foi recuperada.</p></section>"
    geo_ai = _geo_ai_result(database, audit_id, runs[-1]["run_id"])
    summary += "<section><h2>Interpretação GEO por IA canônica (opcional)</h2>"
    if geo_ai is None:
        summary += "<p>Não solicitada, indisponível ou sem resultado persistido "
        summary += "para a observação externa mais recente.</p>"
    else:
        summary += "<p>Status: " + escape(str(geo_ai.get("state") or "-"))
        summary += "; provider: " + escape(str(geo_ai.get("provider") or "-"))
        summary += "; modelo: " + escape(str(geo_ai.get("model") or "-"))
        summary += "; prompt: " + escape(str(geo_ai.get("prompt_id") or "-"))
        summary += " / " + escape(str(geo_ai.get("prompt_version") or "-"))
        summary += "; input hash: " + escape(str(geo_ai.get("input_sha256") or "-"))
        summary += "</p>"
        if geo_ai.get("summary"):
            summary += "<p>" + escape(str(geo_ai["summary"])) + "</p>"
        if geo_ai["opportunities"]:
            summary += "<ol>"
            for opportunity in geo_ai["opportunities"][:12]:
                summary += "<li><strong>" + escape(str(opportunity.get("title") or "-"))
                summary += "</strong> (" + escape(str(opportunity.get("priority") or "-")) + ")"
                summary += ": " + escape(str(opportunity.get("recommendation") or "-"))
                summary += " | evidências: " + ", ".join(
                    escape(str(x)) for x in opportunity["evidence_ids"]
                ) + "</li>"
            summary += "</ol>"
        else:
            summary += "<p>Sem oportunidade com referência de evidência validada.</p>"
        if geo_ai.get("error_reason"):
            summary += "<p>Limitação: " + escape(str(geo_ai["error_reason"])) + "</p>"
        summary += "<p>Inferências não comprovam causalidade, preferência de buscadores "
        summary += "ou avaliação do conteúdo integral dos concorrentes.</p>"
    summary += "</section>"
    ai = _prior_competitive_ai(
        database, audit_id, comparison.get("serp_observation_id") if comparison else None
    )
    summary += "<section><h2>Síntese competitiva de IA disponível</h2>"
    if ai is None:
        summary += "<p>Não há síntese competitiva canônica compatível persistida para a "
        summary += "observação SERP correlacionada. Nenhuma chamada adicional de IA é "
        summary += "executada para materializar este relatório.</p>"
    else:
        summary += "<p>Origem: análise competitiva por IA já persistida no CAT-05, "
        summary += "não uma avaliação nova da Perplexity. "
        summary += "Provider: " + escape(str(ai.get("provider") or "-"))
        summary += "; modelo: " + escape(str(ai.get("model") or "-"))
        summary += "; contrato: " + escape(str(ai.get("contract_version") or "-"))
        summary += "; prompt: " + escape(str(ai.get("prompt_id") or "-"))
        summary += " / " + escape(str(ai.get("prompt_version") or "-")) + ".</p>"
        if ai.get("summary"):
            summary += "<p>" + escape(str(ai["summary"])) + "</p>"
        if ai["opportunities"]:
            summary += "<ol>"
            for opportunity in ai["opportunities"][:12]:
                summary += "<li><strong>" + escape(str(opportunity.get("title") or "-"))
                summary += "</strong> — " + escape(str(opportunity.get("recommendation") or "-"))
                summary += " (evidências: "
                summary += ", ".join(escape(x) for x in opportunity["evidence_ids"])
                summary += ")</li>"
            summary += "</ol>"
        else:
            summary += "<p>Não há oportunidades com referência de evidência auditável.</p>"
        summary += "<p>A análise é uma hipótese assistida; confirme cada remediação "
        summary += "nas evidências correspondentes antes de priorizar.</p>"
    summary += "</section>"
    summary += "<section><h2>Domínios das fontes observadas</h2><ul>"
    for host, n in counts.most_common(20):
        summary += f"<li>{escape(host)}: {n} fonte(s)</li>"
    summary += "</ul><p>Recorrência de fontes não mede participação de mercado nem preferência "
    summary += "dos modelos de IA. É necessário verificar consultas, conteúdo e contexto.</p></section>"
    summary += "<section><h2>Evidências externas para análise competitiva</h2>"
    summary += "<p>Recorte geográfico: fontes estrangeiras podem aparecer "
    summary += "mesmo com filtros de país e idioma. TLD .es, por exemplo, é "
    summary += "um sinal para conferir pertinência ao mercado brasileiro, "
    summary += "não prova que a fonte seja irrelevante. Essas fontes permanecem "
    summary += "registradas por integridade da observação.</p>"
    summary += "<p>Somente metadados de fontes e trechos retornados pela Search API. "
    summary += "Não houve leitura integral de páginas concorrentes; os trechos não "
    summary += "comprovam profundidade, precisão ou superioridade do conteúdo.</p>"
    if not sources:
        summary += "<p>Nenhuma fonte retornada para comparação nesta execução.</p>"
    else:
        summary += "<table><thead><tr><th>Run/posição</th><th>Domínio e URL</th>"
        summary += "<th>Título retornado</th><th>Trecho disponível</th></tr></thead><tbody>"
        for source in sources[:20]:
            url = str(source.get("url") or "")
            run_id = str(source.get("run_id") or "")
            evidence_id = (
                f"PX:{run_id}:{source.get('position')}:"
                f"{sha256(url.encode('utf-8')).hexdigest()[:10]}"
            )
            summary += "<tr><td>" + escape(evidence_id) + "</td>"
            host = _host(url)
            tld = host.rsplit(".", 1)[-1] if "." in host else ""
            locale_hint = (
                " | TLD estrangeiro (verificar aderência ao Brasil)"
                if tld in {"es", "pt", "mx", "ar", "cl", "us", "uk"}
                else ""
            )
            summary += "<td>" + escape(host) + escape(locale_hint)
            summary += "<br>" + escape(url[:300]) + "</td>"
            summary += "<td>" + escape(str(source.get("title") or "-")[:250]) + "</td>"
            summary += "<td>" + escape(str(source.get("snippet") or "Não fornecido")[:450])
            summary += "</td></tr>"
        summary += "</tbody></table>"
        if len(sources) > 20:
            summary += f"<p>Exibindo 20 de {len(sources)} fontes; dados completos persistidos no audit.db.</p>"
    summary += "</section>"

    quality_path = database.parent / "artifacts" / "geo-extraction-quality.json"
    if quality_path.is_file():
        try:
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
            anomalies = [
                row for row in quality.get("observations", [])
                if isinstance(row, dict) and row.get("state") == "NAVIGATION_DOMINATED_SUSPECTED"
            ]
        except (OSError, ValueError, AttributeError):
            anomalies = []
        if anomalies:
            summary += "<section><h2>Confiabilidade da extração principal</h2>"
            summary += "<p>A extração determinística contém sinais de conteúdo "
            summary += "predominantemente de navegação. Verifique o DOM principal "
            summary += "antes de usar esse texto em recomendações editoriais ou GEO. "
            summary += "Isso é uma suspeita, não prova de falha do crawler ou indexabilidade.</p>"
            summary += "<ul>"
            for item in anomalies[:20]:
                summary += "<li>" + escape(str(item.get("artifact_ref") or "-"))
                summary += ": " + escape(str(item.get("word_count") or 0))
                summary += " palavras extraídas</li>"
            summary += "</ul></section>"
    findings = _geo_relevant_findings(database, audit_id)
    summary += "<section><h2>Oportunidades técnicas/editoriais contextualizadas</h2>"
    if findings:
        summary += "<p>Os achados abaixo são evidências existentes na auditoria que "
        summary += "merecem revisão para descoberta e compreensão de conteúdo. "
        summary += "Não comprovam impacto causal nas fontes Perplexity recuperadas.</p><ol>"
        for finding in findings:
            summary += "<li><strong>" + escape(str(finding.get("title") or "-"))
            summary += "</strong> — " + escape(str(finding.get("category") or "-"))
            summary += " / " + escape(str(finding.get("severity") or "-"))
            summary += " | regra: " + escape(str(finding.get("rule_id") or "-"))
            summary += " | evidência: " + escape(str(finding.get("finding_id") or "-"))
            existing = finding.get("existing_recommendation") or {}
            if existing.get("description"):
                summary += "<br>Ação previamente registrada no RASAi: "
                summary += escape(str(existing["description"]))
            summary += "</li>"
        summary += "</ol>"
    else:
        summary += "<p>Nenhum achado técnico/editorial elegível foi encontrado nesta "
        summary += "projeção. Isso não significa ausência de oportunidades GEO.</p>"
    summary += "</section>"
    summary += "<section><h2>Próximas ações de análise</h2><p>"
    summary += "Confronte as consultas com as evidências de descoberta e indexabilidade "
    summary += "do <a href='cat-01.html'>CAT-01</a>, conteúdo e entidades do "
    summary += "<a href='cat-03.html'>CAT-03</a>, inteligência do "
    summary += "<a href='cat-05.html'>CAT-05</a> e recomendações do "
    summary += "<a href='cat-09.html'>CAT-09</a>. "
    summary += "Não atribua causalidade sem evidência de conteúdo ou de acesso.</p></section>"
    return style + '<div class="geo-view">' + header + summary + "</div>"
