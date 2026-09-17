"""Trust refinements for catalog status: execution success is not data availability."""
from __future__ import annotations

import sqlite3
from typing import Any

_INSTALLED = False


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _count(connection: sqlite3.Connection, table: str, audit_id: str) -> int:
    if not _table_exists(connection, table) or "audit_id" not in _columns(connection, table):
        return 0
    return int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE audit_id=?", (audit_id,)).fetchone()[0])


def _accessibility_count(database: Any, audit_id: str) -> int:
    connection = sqlite3.connect(database)
    try:
        if not _table_exists(connection, "web_performance_observations"):
            return 0
        cols = _columns(connection, "web_performance_observations")
        if "audit_id" not in cols or "accessibility_score" not in cols:
            return 0
        return int(connection.execute(
            "SELECT COUNT(*) FROM web_performance_observations WHERE audit_id=? AND accessibility_score IS NOT NULL",
            (audit_id,),
        ).fetchone()[0])
    finally:
        connection.close()


def _web_result_count(database: Any, audit_id: str) -> int:
    connection = sqlite3.connect(database)
    try:
        if not _table_exists(connection, "web_performance_observations"):
            return 0
        cols = _columns(connection, "web_performance_observations")
        if "audit_id" not in cols:
            return 0
        measurable = [
            name for name in (
                "performance_score", "lcp_lab_ms", "lcp_ms", "inp_field_ms", "inp_ms", "cls_lab", "cls",
                "fcp_lab_ms", "speed_index_lab_ms", "tbt_lab_ms",
            ) if name in cols
        ]
        if not measurable:
            return _count(connection, "web_performance_observations", audit_id)
        predicate = " OR ".join(f"{name} IS NOT NULL" for name in measurable)
        return int(connection.execute(
            f"SELECT COUNT(*) FROM web_performance_observations WHERE audit_id=? AND ({predicate})",
            (audit_id,),
        ).fetchone()[0])
    finally:
        connection.close()


def _apdex_result_count(database: Any, audit_id: str, *, experience: bool) -> int:
    connection = sqlite3.connect(database)
    try:
        tables = (
            ("synthetic_ux_apdex_samples", "synthetic_ux_apdex_summaries")
            if experience else
            ("synthetic_apdex_samples", "synthetic_apdex_summaries")
        )
        return sum(_count(connection, table, audit_id) for table in tables)
    finally:
        connection.close()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import catalog_report_page as page

    original_sources = page._catalog_sources
    original_status = page._catalog_status

    def catalog_sources(database: Any, data: Any, catalog_id: str):
        rows = list(original_sources(database, data, catalog_id))
        if catalog_id == "CAT-02":
            rows = [row for row in rows if row[0] != "web_performance_observations"]
            count = _accessibility_count(database, data.audit_id)
            if count:
                rows.append(("web_performance_observations", "Medições automatizadas de acessibilidade", count))
        return rows

    def catalog_status(database: Any, data: Any, catalog_id: str):
        status, tone, detail = original_status(database, data, catalog_id)
        if catalog_id not in data.selected:
            return status, tone, detail
        if catalog_id == "CAT-02" and _accessibility_count(database, data.audit_id) == 0:
            return (
                "SEM RESULTADO", "warn",
                "O catálogo foi solicitado, mas nenhuma pontuação/medição de acessibilidade foi materializada. "
                "A existência de outras métricas Lighthouse não é tratada como evidência de acessibilidade.",
            )
        if catalog_id == "CAT-04" and status == "CONCLUÍDO" and _web_result_count(database, data.audit_id) == 0:
            return (
                "PARCIAL", "warn",
                "A etapa de Web Performance terminou, mas nenhuma medição de desempenho utilizável foi persistida; "
                "sucesso de execução não equivale a dado disponível.",
            )
        if catalog_id == "CAT-06" and status == "CONCLUÍDO" and _apdex_result_count(database, data.audit_id, experience=False) == 0:
            return (
                "PARCIAL", "warn",
                "A etapa de Apdex de navegação terminou sem amostra/resumo persistido. O catálogo não é tratado como resultado completo.",
            )
        if catalog_id == "CAT-07" and status == "CONCLUÍDO" and _apdex_result_count(database, data.audit_id, experience=True) == 0:
            return (
                "PARCIAL", "warn",
                "A etapa de Apdex de experiência terminou sem amostra/resumo persistido. O catálogo não é tratado como resultado completo.",
            )
        return status, tone, detail

    catalog_sources._rasai_catalog_state_trust = True
    catalog_sources._rasai_original = original_sources
    catalog_status._rasai_catalog_state_trust = True
    catalog_status._rasai_original = original_status
    page._catalog_sources = catalog_sources
    page._catalog_status = catalog_status
    _INSTALLED = True


__all__ = ["install"]
