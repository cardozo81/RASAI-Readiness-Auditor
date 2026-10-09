"""Read-only, evidence-scoped GEO crossrefs. No CAT engines or scores are changed."""
from __future__ import annotations

from contextlib import closing
from html import escape
import json
from pathlib import Path
import sqlite3

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


def _columns(con: sqlite3.Connection, name: str) -> set[str]:
    if con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is None:
        return set()
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({name})")}


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
    row = con.execute(
        "SELECT observation_id, query FROM serp_observations "
        "WHERE audit_id=? AND data_mode='OBSERVED_API' "
        "AND observation_status='OBSERVED' ORDER BY observation_id DESC LIMIT 1",
        (audit,),
    ).fetchone()
    if row is None:
        return "<p>Não há observação SERP live elegível para esta auditoria.</p>"
    return ("<p>Consulta SERP observada: " + escape(str(row[1] or "-")[:160])
            + "; observação <code>" + escape(str(row[0])) + "</code>. "
            "Não comprova citações generativas.</p>")


def _interpretation(con: sqlite3.Connection, audit: str) -> str:
    cols = _columns(con, "geo_ai_interpretations")
    if not {"audit_id", "result_id", "state"}.issubset(cols):
        return "<p>Interpretação GEO por IA não materializada.</p>"
    row = con.execute(
        "SELECT result_id FROM geo_ai_interpretations "
        "WHERE audit_id=? AND state='AVAILABLE' ORDER BY result_id DESC LIMIT 1",
        (audit,),
    ).fetchone()
    if row is None:
        return "<p>Sem interpretação GEO por IA disponível e persistida.</p>"
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
    entries = [
        (fid, title, priority, _refs(evidence))
        for fid, title, priority, category, evidence in rows
        if str(category or "").upper() in valid_categories and _refs(evidence)
    ][:5]
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
    except (OSError, sqlite3.Error):
        result += "<p>Projeção indisponível: dados persistidos não legíveis.</p>"
    return (result + "<p><a href='geo.html'>Síntese GEO e evidências</a>. "
            "A associação é orientativa e não comprova efeito em ranking ou "
            "respostas generativas.</p></section>")
