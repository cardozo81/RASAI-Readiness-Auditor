"""Read-only, evidence-scoped GEO crossrefs. No CAT engines or scores are changed."""
from __future__ import annotations

from contextlib import closing
from html import escape
import json
from pathlib import Path
import sqlite3

from rasai.geo_snapshot_context_308 import geo_snapshot_context_html
from rasai.geo_temporal_provenance import (
    _UNVERIFIABLE, _columns, _last_temporally_verified,
)

_TOPICS = {
    "CAT-01": ("Acesso e descoberta", "SEO técnico e Engenharia"),
    "CAT-03": ("Conteúdo e entidades", "Conteúdo, SEO e especialista de produto"),
    "CAT-05": ("Inteligência de busca", "SEO e análise competitiva"),
    "CAT-08": ("Interpretação de oportunidades", "SEO e negócio"),
    "CAT-09": ("Remediações", "Engenharia, Conteúdo e negócio"),
}
_CATEGORIES = {
    "CAT-01": frozenset(("FILES_DISCOVERY", "TECHNICAL_HTML", "BEST_PRACTICES",
        "AI_ACCESS", "DISCOVERY_ACCESS", "TECHNICAL_ACCESSIBILITY",
        "INDEXABILITY", "CONTENT_EXTRACTABILITY", "CRAWLABILITY")),
    "CAT-03": frozenset(("SEMANTICS_STRUCTURE", "CONTENT", "SEMANTIC_STRUCTURE",
        "ENTITY_CLARITY", "STRUCTURED_DATA", "ANSWERABILITY", "CITATION_READINESS",
        "EVIDENCE_TRUST", "INTENT_COVERAGE", "CONTENT_VALUE")),
    "CAT-05": frozenset(("SEARCH_RANKING", "SEARCH_INTELLIGENCE")),
}


def _refs(raw: object) -> tuple[str, ...]:
    try:
        values = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return ()
    if not isinstance(values, list):
        return ()
    return tuple(str(x)[:100] for x in values[:8] if isinstance(x, str) and x.strip())


def _findings(con: sqlite3.Connection, audit: str, catalog: str) -> list[tuple]:
    needed = {"audit_id", "finding_id", "category", "rule_id", "title", "evidence_ids"}
    if not needed.issubset(_columns(con, "findings")):
        return []
    rows = con.execute(
        "SELECT finding_id, category, rule_id, title, evidence_ids FROM findings "
        "WHERE audit_id=? ORDER BY finding_id", (audit,)
    )
    return [
        (finding_id, rule, title, _refs(evidence))
        for finding_id, category, rule, title, evidence in rows
        if str(category or "").upper() in _CATEGORIES[catalog] and _refs(evidence)
    ][:6]


def _serp(con: sqlite3.Connection, audit: str) -> str:
    needed = {"audit_id", "observation_id", "query", "data_mode", "observation_status"}
    if not needed.issubset(_columns(con, "serp_observations")):
        return "<p>Não há observação SERP live elegível para esta auditoria.</p>"
    row = _last_temporally_verified(
        con, table="serp_observations", audit_id=audit,
        columns=("observation_id", "query"), time_column="collected_at",
        condition=" AND data_mode='OBSERVED_API' AND observation_status='OBSERVED'",
    )
    if row is _UNVERIFIABLE:
        return ("<p>Há observações SERP elegíveis, mas a cronologia não "
                "é verificável; consulta mais recente N/D. "
                "Nenhuma conclusão GEO é inferida.</p>")
    if row is None:
        return "<p>Não há observação SERP live elegível para esta auditoria.</p>"
    return ("<p>Consulta SERP observada: " + escape(str(row[1] or "-")[:160])
            + "; observação <code>" + escape(str(row[0])) + "</code>. "
            "Não comprova citações generativas.</p>")


def _interpretation(con: sqlite3.Connection, audit: str) -> str:
    cols = _columns(con, "geo_ai_interpretations")
    if not {"audit_id", "result_id", "state"}.issubset(cols):
        return "<p>Interpretação GEO por IA não materializada.</p>"
    row = _last_temporally_verified(
        con, table="geo_ai_interpretations", audit_id=audit,
        columns=("result_id", "state"), time_column="created_at",
    )
    if row is _UNVERIFIABLE:
        return (
            "<p>Interpretação GEO por IA: múltiplas tentativas sem cronologia "
            "verificável; último estado N/D. Não promover resultado anterior "
            "nem executar IA nesta projeção.</p>"
        )
    if row is None:
        return "<p>Sem interpretação GEO por IA disponível e persistida.</p>"
    if row[1] != "AVAILABLE":
        return (
            "<p>Interpretação GEO por IA indisponível na última tentativa "
            "(estado: " + escape(str(row[1] or "INDETERMINADO")[:60]) + "). "
            "Uma interpretação anterior não representa o estado atual; "
            "nenhuma IA é acionada nesta projeção.</p>"
        )
    return ("<p>Interpretação GEO persistida: <code>" + escape(str(row[0]))
            + "</code>. Verifique suas fontes e limitações em GEO; "
            "nenhuma IA é acionada nesta projeção.</p>")


def _recommendations(con: sqlite3.Connection, audit: str) -> str:
    if not {"audit_id", "finding_id", "title", "priority_class"}.issubset(
        _columns(con, "recommendations")
    ) or not {"audit_id", "finding_id", "category", "evidence_ids"}.issubset(
        _columns(con, "findings")
    ):
        return "<p>Sem recomendações com proveniência verificável.</p>"
    rows = con.execute(
        "SELECT r.finding_id,r.title,r.priority_class,f.category,f.evidence_ids "
        "FROM recommendations r JOIN findings f "
        "ON r.audit_id=f.audit_id AND r.finding_id=f.finding_id "
        "WHERE r.audit_id=? ORDER BY r.finding_id LIMIT 100", (audit,),
    )
    valid_categories = frozenset().union(*_CATEGORIES.values())
    entries = []
    seen: set[tuple[str, str]] = set()
    for fid, title, priority, category, evidence in rows:
        refs = _refs(evidence)
        if str(category or "").upper() not in valid_categories or not refs:
            continue
        # Legacy recommendation stores can contain repeated projections of
        # the same finding/action. Do not duplicate an identical callout.
        key = (str(fid), str(title))
        if key in seen:
            continue
        seen.add(key)
        entries.append((fid, title, priority, refs))
        if len(entries) >= 5:
            break
    if not entries:
        return "<p>Sem recomendações GEO associadas a evidências desta AUD.</p>"
    return "<ul>" + "".join(
        "<li>" + escape(str(title or "-")[:180]) + " | prioridade original: "
        + escape(str(priority or "-")) + " | achado <code>" + escape(str(fid))
        + "</code> | evidências: " + ", ".join(escape(e) for e in refs) + "</li>"
        for fid, title, priority, refs in entries
    ) + "</ul>"


def catalog_geo_context(database: Path, audit_id: str, catalog_id: str) -> str:
    """Abstain on legacy data, never infer absence/causality or cross-AUD evidence."""
    if catalog_id not in _TOPICS:
        return ""
    title, owner = _TOPICS[catalog_id]
    result = ("<section><h2>Perspectiva GEO — " + escape(title) + "</h2>"
              "<p>Projeção de fontes persistidas nesta AUD, sem alterar catálogo, "
              "índices ou achados. Revisão sugerida: " + escape(owner) + ".</p>")
    try:
        with closing(sqlite3.connect(
            f"file:{database.resolve().as_posix()}?mode=ro", uri=True
        )) as con:
            if catalog_id in _CATEGORIES:
                rows = _findings(con, audit_id, catalog_id)
                if rows:
                    result += "<ul>" + "".join(
                        "<li>" + escape(str(label or "-")[:180])
                        + " | regra <code>" + escape(str(rule))
                        + "</code> | achado <code>" + escape(str(fid))
                        + "</code> | evidências: " + ", ".join(escape(e) for e in refs)
                        + "</li>" for fid, rule, label, refs in rows
                    ) + "</ul>"
                else:
                    result += ("<p>Sem achados desta dimensão com IDs de evidência "
                               "persistidos. Não deduzir ausência de oportunidade.</p>")
                if catalog_id == "CAT-05":
                    result += _serp(con, audit_id)
            elif catalog_id == "CAT-08":
                result += _interpretation(con, audit_id)
            elif catalog_id == "CAT-09":
                result += _recommendations(con, audit_id)
            result += geo_snapshot_context_html(con, audit_id, catalog_id)
    except (OSError, sqlite3.Error):
        result += "<p>Projeção indisponível: dados persistidos não legíveis.</p>"
    return (result + "<p><a href='geo.html'>Síntese GEO e evidências</a>. "
            "A associação é orientativa e não comprova efeito em ranking ou "
            "respostas generativas.</p></section>")


def geo_surface_context(database: Path, audit_id: str, surface: str) -> str:
    """Status/provenance only. Never assert GEO inference was used by other engines."""
    if surface not in {"index", "directed-analysis", "ai-integrations"}:
        return ""
    intro = {
        "index": "Panorama GEO desta auditoria",
        "directed-analysis": "Relação com análise direcionada",
        "ai-integrations": "Integração externa GEO e proveniência",
    }[surface]
    result = "<section><h2>" + escape(intro) + "</h2>"
    try:
        with closing(sqlite3.connect(
            f"file:{database.resolve().as_posix()}?mode=ro", uri=True
        )) as con:
            necessary = {"audit_id", "run_id", "status"}
            if not necessary.issubset(_columns(con, "perplexity_search_runs")):
                result += "<p>Perplexity Search não solicitada ou não persistida nesta AUD.</p>"
            else:
                row = _last_temporally_verified(
                    con, table="perplexity_search_runs", audit_id=audit_id,
                    columns=("run_id", "status"), time_column="started_at",
                )
                if row is _UNVERIFIABLE:
                    result += (
                        "<p>Múltiplas buscas externas sem cronologia verificável; "
                        "última execução N/D. Nenhum sucesso anterior é promovido.</p>"
                    )
                elif row is None:
                    result += "<p>Perplexity Search não solicitada ou não persistida nesta AUD.</p>"
                else:
                    run_id, status = row
                    result += (
                        "<p>Última busca externa registrada: "
                        + escape(str(status or "INDETERMINADO")[:60])
                        + "; execução <code>" + escape(str(run_id)[:100])
                        + "</code>. "
                    )
                    if {"run_id", "url"}.issubset(
                        _columns(con, "perplexity_search_sources")
                    ):
                        sources = con.execute(
                            "SELECT COUNT(*) FROM perplexity_search_sources "
                            "WHERE run_id=?", (run_id,)
                        ).fetchone()[0]
                        result += "Fontes externas retornadas: " + str(sources) + ". "
                    result += "</p>"
                    if surface == "directed-analysis":
                        result += (
                            "<p>A existência dessa observação não significa que "
                            "a análise direcionada a tenha consumido. Verifique "
                            "as evidências citadas na própria análise.</p>"
                        )
                    if surface == "ai-integrations":
                        result += (
                            "<p>Custo e tentativas: consultar os lançamentos "
                            "persistidos nesta página. A projeção GEO não "
                            "recontabiliza gasto, nem presume faturamento.</p>"
                        )
                    if surface == "index":
                        result += (
                            "<p>O status da fonte não comprova presença da "
                            "URL auditada em respostas generativas.</p>"
                        )
            result += geo_snapshot_context_html(con, audit_id, surface)
    except (OSError, sqlite3.Error):
        result += "<p>Estado da fonte externa indisponível nesta projeção.</p>"
    return (
        result + "<p>Consulte a <a href='geo.html'>síntese GEO</a> "
        "para evidências, ressalvas e interpretação sem efeitos de ranking "
        "presumidos.</p></section>"
    )
