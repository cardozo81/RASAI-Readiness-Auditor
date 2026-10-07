"""Read-only, evidence-limited GEO report projection.

Perplexity Search API retrieval is not proof of generative answer inclusion.
This projection must never create a search request or write to audit.db.
"""
from __future__ import annotations

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
    with sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True) as con:
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
    summary += "<section><h2>Domínios das fontes observadas</h2><ul>"
    for host, n in counts.most_common(20):
        summary += f"<li>{escape(host)}: {n} fonte(s)</li>"
    summary += "</ul><p>Recorrência de fontes não mede participação de mercado nem preferência "
    summary += "dos modelos de IA. É necessário verificar consultas, conteúdo e contexto.</p></section>"
    summary += "<section><h2>Próximas ações de análise</h2><p>"
    summary += "Confronte as consultas com as evidências de descoberta e indexabilidade "
    summary += "do <a href='cat-01.html'>CAT-01</a>, conteúdo e entidades do "
    summary += "<a href='cat-03.html'>CAT-03</a>, inteligência do "
    summary += "<a href='cat-05.html'>CAT-05</a> e recomendações do "
    summary += "<a href='cat-09.html'>CAT-09</a>. "
    summary += "Não atribua causalidade sem evidência de conteúdo ou de acesso.</p></section>"
    return header + summary
