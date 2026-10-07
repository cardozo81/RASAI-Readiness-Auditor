"""Read-only, evidence-limited GEO report projection.

Perplexity Search API retrieval is not proof of generative answer inclusion.
This projection must never create a search request or write to audit.db.
"""
from __future__ import annotations

from contextlib import closing

from collections import Counter
from html import escape
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
        con.row_factory = sqlite3.Row
        runs = [dict(r) for r in con.execute(
            "SELECT run_id, query_json, search_type, status, started_at, error_class "
            "FROM perplexity_search_runs WHERE audit_id=? ORDER BY started_at, run_id",
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



def geo_body(database: Path, audit_id: str) -> str:
    """Evidence-backed readout; no scores, causal attribution or speculative gaps."""
    runs, sources = _observations(database, audit_id)
    header = (
        "<h1>GEO — Oportunidades para pesquisa orientada por IA</h1>"
        "<p>Esta página reúne observações externas e orientações de análise. "
        "A presença em fontes da Perplexity Search API não comprova inclusão, "
        "recomendação ou citação em respostas de IAs de outros buscadores. "
        "Melhorias representam boas práticas, nunca garantia de visibilidade.</p>"
    )
    if not runs:
        return header + (
            "<section><h2>Estado da observação</h2><p>Não há execução "
            "Perplexity Search persistida nesta auditoria. "
            "Sem dados, não é possível concluir presença ou ausência da URL em AI Search.</p></section>"
            "<p>Detalhes técnicos: <a href='cat-05.html'>CAT-05</a>; "
            "<a href='ai-integrations.html'>IA e integrações</a>.</p>"
        )
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
    summary += "</tbody></table></section>"
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
    summary += "<section><h2>Evidências externas para análise competitiva</h2>"
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
            evidence_id = run_id + ":" + str(source.get("position") or "-")
            summary += "<tr><td>" + escape(evidence_id) + "</td>"
            summary += "<td>" + escape(_host(url)) + "<br>" + escape(url[:300]) + "</td>"
            summary += "<td>" + escape(str(source.get("title") or "-")[:250]) + "</td>"
            summary += "<td>" + escape(str(source.get("snippet") or "Não fornecido")[:450])
            summary += "</td></tr>"
        summary += "</tbody></table>"
        if len(sources) > 20:
            summary += f"<p>Exibindo 20 de {len(sources)} fontes; dados completos persistidos no audit.db.</p>"
    summary += "</section>"
    summary += "</ul><p>Recorrência de fontes não mede participação de mercado nem preferência "
    summary += "dos modelos de IA. É necessário verificar consultas, conteúdo e contexto.</p></section>"
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
    return header + summary
