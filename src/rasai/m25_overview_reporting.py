"""Overview projection for Synthetic User Experience Apdex.

Keeps the executive index symmetric with Synthetic Navigation Apdex without
changing either calculation or persistence contract.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
import re
import sqlite3
from typing import Any

from rasai.persistence import AuditWorkspace

M25_REPORT_FILE = "apdex-experience.html"
_START_INDEX = "<!-- rasai-apdex-experience-index-start -->"
_END_INDEX = "<!-- rasai-apdex-experience-index-end -->"
_M23_INDEX_END = "<!-- rasai-apdex-index-end -->"


def enrich_m25_overview_summary(*, audit_id: str, workspace: AuditWorkspace) -> Path | None:
    """Add or refresh the Experience Apdex summary in ``report/index.html``."""
    index_path = workspace.root / "report" / "index.html"
    if not index_path.is_file():
        return None

    data = _load(audit_id, workspace)
    html = index_path.read_text(encoding="utf-8")
    rendered = _index_summary(data)
    html = _replace_or_insert(html, rendered)
    index_path.write_text(html, encoding="utf-8", newline="\n")
    return index_path


def _load(audit_id: str, workspace: AuditWorkspace) -> dict[str, Any]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        run = _one(connection, "SELECT * FROM synthetic_ux_apdex_runs WHERE audit_id=?", (audit_id,))
        summaries = _many(
            connection,
            "SELECT * FROM synthetic_ux_apdex_summaries WHERE audit_id=? ORDER BY url,device,summary_id",
            (audit_id,),
        )
        return {"run": run, "summaries": summaries}
    finally:
        connection.close()


def _one(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
    try:
        return connection.execute(sql, params).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return None
        raise


def _many(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise


def _index_summary(data: dict[str, Any]) -> str:
    run = data["run"]
    summaries = data["summaries"]
    if run is None:
        state = "NÃO MATERIALIZADO"
        detail = "Synthetic User Experience Apdex ainda não possui estado persistido."
        kpm = "-"
        calibration = "-"
    elif not bool(run["enabled"]):
        state = "DESABILITADO"
        detail = "Nenhuma user action sintética adicional foi executada."
        kpm = str(run["kpm"])
        calibration = str(run["calibration_source"])
    else:
        state = str(run["status"])
        detail = (
            f"{int(run['valid_samples'])} amostra(s) válida(s); "
            f"alvo {int(run['target_samples_per_page'])} por página."
        )
        kpm = str(run["kpm"])
        calibration = str(run["calibration_source"])

    population_rows = [row for row in summaries if str(row["device"]).upper() == "POPULATION"]
    final_populations = sum(bool(row["final_group"]) for row in population_rows)
    return (
        f"{_START_INDEX}<section id='m25-apdex-experience-summary' class='panel'>"
        "<div class='kicker'>Web Performance · Synthetic User Experience Apdex</div>"
        "<h2>Apdex calibrado</h2>"
        "<p class='intro'>Synthetic User Experience Apdex é uma visão sintética calibrável, separada do Synthetic Navigation Apdex e de SCORE-GEO-004. Não é RUM.</p>"
        "<div class='metric-grid'>"
        f"{_metric('Estado', state)}"
        f"{_metric('KPM efetiva', kpm)}"
        f"{_metric('Calibração', calibration)}"
        f"{_metric('Populações finais', final_populations)}"
        f"{_metric('Contextos', len(summaries))}"
        "</div>"
        f"<p class='intro'>{escape(detail)}</p>"
        f"<p><a href='{M25_REPORT_FILE}'>Abrir análise Apdex calibrada completa →</a></p>"
        f"</section>{_END_INDEX}"
    )


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><small>{escape(str(label))}</small><strong>{escape(str(value))}</strong></div>"


def _replace_or_insert(html: str, content: str) -> str:
    pattern = re.compile(re.escape(_START_INDEX) + r".*?" + re.escape(_END_INDEX), flags=re.DOTALL)
    if pattern.search(html):
        return pattern.sub(content, html, count=1)
    if _M23_INDEX_END in html:
        return html.replace(_M23_INDEX_END, _M23_INDEX_END + content, 1)
    return html.replace("</main>", content + "</main>", 1) if "</main>" in html else html + content
