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



def _serp_comparison(database: Path, audit_id: str, runs: list[dict], sources: list[dict]) -> list[tuple[str, int, int, int]]:
    """Compare URL overlap only for unambiguously single-query Perplexity requests.

    Multi-query search sources cannot reliably be assigned to individual queries.
    SERP comparisons only use successful live observations; fixture/failed data abstains.
    """
    eligible: list[tuple[str, str]] = []
    for run in runs:
        if str(run.get("status", "")).upper() != "SUCCESS":
            continue
        try:
            queries = json.loads(run["query_json"])
        except (TypeError, ValueError):
            continue
        if isinstance(queries, list) and len(queries) == 1 and isinstance(queries[0], str):
            eligible.append((run["run_id"], queries[0].strip().casefold()))
    if not eligible:
        return []
    with sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True) as con:
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('serp_observations','serp_results')"
        )}
        if len(tables) < 2:
            return []
        observations = list(con.execute(
            "SELECT observation_id, query, collected_at FROM serp_observations "
            "WHERE audit_id=? AND observation_status='OBSERVED' AND data_mode='OBSERVED_API' "
            "ORDER BY collected_at DESC, observation_id DESC", (audit_id,)
        ))
        latest: dict[str, str] = {}
        for obs_id, query, _ in observations:
            latest.setdefault(str(query).strip().casefold(), obs_id)
        result = []
        for run_id, query in eligible:
            obs_id = latest.get(query)
            if not obs_id:
                continue
            serp_urls = {str(row[0]).strip() for row in con.execute(
                "SELECT url FROM serp_results WHERE observation_id=?", (obs_id,)
            )}
            perplexity_urls = {str(s["url"]).strip() for s in sources if s["run_id"] == run_id}
            if not serp_urls and not perplexity_urls:
                continue
            result.append((query, len(serp_urls), len(perplexity_urls),
                           len(serp_urls & perplexity_urls)))
    return result



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
    comparisons = _serp_comparison(database, audit_id, runs, sources)
    summary += "<section><h2>Comparação SERP × Perplexity</h2>"
    if not comparisons:
        summary += "<p>Comparação não aplicável: não há queries singulares correspondentes "
        summary += "com SERP live válida e fontes rastreáveis. Requests com múltiplas queries "
        summary += "não são desagregados artificialmente.</p>"
    else:
        summary += "<table><thead><tr><th>Consulta</th><th>URLs SERP</th>"
        summary += "<th>URLs Perplexity</th><th>URLs em ambas</th></tr></thead><tbody>"
        for query, serp_count, px_count, overlap in comparisons:
            summary += f"<tr><td>{escape(query)}</td><td>{serp_count}</td>"
            summary += f"<td>{px_count}</td><td>{overlap}</td></tr>"
        summary += "</tbody></table><p>Sobreposição observacional de URLs exatas, "
        summary += "sem equivalência temporal, de ranking ou de comportamento dos modelos.</p>"
    summary += "</section>"
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
