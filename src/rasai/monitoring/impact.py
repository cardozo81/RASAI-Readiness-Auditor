"""Observed-outcome change analysis layered over an audit comparison."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from html import escape
from pathlib import Path
import sqlite3
from typing import Any

from rasai.report_presentation import humanize_report_html

from .models import ComparisonResult

_GENAI_EXPORT_PREFIX = "GOOGLE_SEARCH_CONSOLE_GENERATIVE_AI_PERFORMANCE_EXPORT"


@dataclass(frozen=True, slots=True)
class OutcomeChange:
    key: str
    source: str
    metric: str
    before: float | str | None
    after: float | str | None
    status: str
    delta: float | None = None
    unit: str | None = None


@dataclass(frozen=True, slots=True)
class ImpactAnalysis:
    outcome_changes: tuple[OutcomeChange, ...]
    associations: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]
    window_comparability: tuple[dict[str, Any], ...] = ()


def analyze_change_impact(result: ComparisonResult) -> ImpactAnalysis:
    before, before_datasets = _observed_snapshot(result.baseline.workspace)
    after, after_datasets = _observed_snapshot(result.current.workspace)
    windows = _compare_windows(before_datasets, after_datasets)
    window_by_source = {str(item["source"]): str(item["status"]) for item in windows}

    changes: list[OutcomeChange] = []
    for key in sorted(set(before) | set(after)):
        left = before.get(key)
        right = after.get(key)
        if left is None or right is None:
            item = right or left
            assert item is not None
            changes.append(
                OutcomeChange(
                    key,
                    item["source"],
                    item["metric"],
                    left["value"] if left else None,
                    right["value"] if right else None,
                    "DATA_UNAVAILABLE",
                    unit=item.get("unit"),
                )
            )
            continue
        old = left["value"]
        new = right["value"]
        if old == new:
            continue
        direction = right.get("direction", "STATE")
        status = "CHANGED"
        delta: float | None = None
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            delta = float(new) - float(old)
            if direction == "HIGHER_BETTER":
                status = "IMPROVED" if delta > 0 else "REGRESSED"
            elif direction == "LOWER_BETTER":
                status = "IMPROVED" if delta < 0 else "REGRESSED"
        changes.append(OutcomeChange(key, right["source"], right["metric"], old, new, status, delta, right.get("unit")))

    technical = [event for event in result.regressions if event.domain in {"RULE", "PAGE"}]
    outcome_regressions = [change for change in changes if change.status == "REGRESSED"]
    associations: list[dict[str, Any]] = []
    for change in outcome_regressions:
        temporal_status = window_by_source.get(change.source, "UNKNOWN_PERIOD")
        if not technical or temporal_status not in {"ALIGNED_WINDOW", "PARTIAL_OVERLAP"}:
            continue
        associations.append(
            {
                "status": "TEMPORAL_ASSOCIATION_ONLY",
                "window_status": temporal_status,
                "outcome_key": change.key,
                "outcome_metric": change.metric,
                "outcome_source": change.source,
                "technical_regression_count": len(technical),
                "technical_examples": [event.rule_id or event.label for event in technical[:8]],
                "statement": (
                    "Technical regression(s) and an observed outcome regression coexist across comparable observation "
                    "windows. Causality is not established."
                ),
            }
        )

    limitations = [
        "One latest dataset per source is selected in each AUD; overlapping historical datasets are not summed.",
        "Missing metrics stay unavailable; NULL is never converted into an observed zero.",
        "Google Generative AI Performance exports are treated as non-directional changes because exported zero values can represent unavailable/non-numeric report values.",
        "Temporal association is emitted only for aligned or partially overlapping observation windows.",
        "Search engines, demand, competition, seasonality and measurement coverage can change independently of the website.",
        "This analyzer reports co-occurrence/temporal association only and never causal attribution.",
    ]
    return ImpactAnalysis(tuple(changes), tuple(associations), tuple(limitations), tuple(windows))


def write_impact_report(report_dir: str | Path, result: ComparisonResult, analysis: ImpactAnalysis | None = None) -> Path:
    active = analysis or analyze_change_impact(result)
    root = Path(report_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "impact.html"
    rows = "".join(_change_row(item) for item in active.outcome_changes) or "<tr><td colspan='7'>Nenhum outcome observacional comparável ou alterado.</td></tr>"
    window_rows = "".join(
        "<tr>"
        f"<td>{escape(str(item['status']))}</td><td>{escape(str(item['source']))}</td>"
        f"<td>{escape(str(item.get('baseline_period') or '-'))}</td>"
        f"<td>{escape(str(item.get('current_period') or '-'))}</td>"
        f"<td>{escape(str(item.get('detail') or ''))}</td></tr>"
        for item in active.window_comparability
    ) or "<tr><td colspan='5'>Nenhuma janela observacional comum para comparar.</td></tr>"
    association_rows = "".join(
        f"<tr><td>{escape(str(item['status']))}</td><td>{escape(str(item.get('window_status') or '-'))}</td>"
        f"<td>{escape(str(item['outcome_source']))}</td><td>{escape(str(item['outcome_metric']))}</td>"
        f"<td>{int(item['technical_regression_count'])}</td><td>{escape(', '.join(item['technical_examples']))}</td>"
        f"<td>{escape(str(item['statement']))}</td></tr>"
        for item in active.associations
    ) or "<tr><td colspan='7'>Nenhuma associação temporal elegível foi emitida neste par.</td></tr>"
    limitations = "".join(f"<li>{escape(item)}</li>" for item in active.limitations)
    html = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>RASAi Change Impact</title><style>{_CSS}</style></head><body><main><header class='hero'><div class='eyebrow'>RASAi Monitor · Change Impact</div><h1>Mudança técnica × outcomes observados</h1><p>Baseline <code>{escape(result.baseline.audit_id)}</code> → atual <code>{escape(result.current.audit_id)}</code>. Esta página não estabelece causalidade.</p></header><section class='panel'><h2>Comparabilidade das janelas</h2><div class='table-wrap'><table><thead><tr><th>Status</th><th>Fonte</th><th>Baseline</th><th>Atual</th><th>Interpretação</th></tr></thead><tbody>{window_rows}</tbody></table></div></section><section class='panel'><h2>Outcomes alterados</h2><div class='table-wrap'><table><thead><tr><th>Status</th><th>Fonte</th><th>Métrica</th><th>Antes</th><th>Depois</th><th>Delta</th><th>Unidade</th></tr></thead><tbody>{rows}</tbody></table></div></section><section class='panel'><h2>Associações temporais</h2><div class='table-wrap'><table><thead><tr><th>Status</th><th>Janela</th><th>Fonte</th><th>Outcome</th><th>Regressões técnicas</th><th>Exemplos</th><th>Interpretação</th></tr></thead><tbody>{association_rows}</tbody></table></div></section><section class='panel'><h2>Limitações</h2><ul>{limitations}</ul></section></main></body></html>"""
    path.write_text(
        humanize_report_html(html, page_name="monitoring-impact.html"),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _observed_snapshot(workspace: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    database = workspace / "observability.db"
    if not database.is_file():
        return {}, {}
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        output: dict[str, dict[str, Any]] = {}
        selected = _latest_datasets(connection) if "datasets" in tables else {}
        if "search_performance" in tables:
            _search_signals(connection, output, selected)
        if "index_observations" in tables:
            _index_signals(connection, output, selected)
        if "crux_history" in tables:
            _crux_signals(connection, output, selected)
        return output, selected
    finally:
        connection.close()


def _latest_datasets(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        "SELECT dataset_id,source_type,period_start,period_end,collected_at FROM datasets ORDER BY collected_at,dataset_id"
    ).fetchall()
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest[str(row["source_type"])] = {
            "dataset_id": str(row["dataset_id"]),
            "source": str(row["source_type"]),
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "collected_at": str(row["collected_at"]),
        }
    return latest


def _selected_ids(selected: dict[str, dict[str, Any]]) -> tuple[str, ...]:
    return tuple(str(item["dataset_id"]) for item in selected.values())


def _search_signals(connection: sqlite3.Connection, output: dict[str, dict[str, Any]], selected: dict[str, dict[str, Any]]) -> None:
    dataset_ids = _selected_ids(selected)
    if not dataset_ids:
        return
    placeholders = ",".join("?" for _ in dataset_ids)
    rows = connection.execute(
        f"SELECT dataset_id,source,COALESCE(surface,'ALL') surface,clicks,impressions,position FROM search_performance WHERE dataset_id IN ({placeholders})",
        dataset_ids,
    ).fetchall()
    groups: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        groups[(str(row["source"]), str(row["surface"]))].append(row)
    for (source, surface), items in groups.items():
        click_values = [float(row["clicks"]) for row in items if row["clicks"] is not None]
        impression_values = [float(row["impressions"]) for row in items if row["impressions"] is not None]
        clicks = sum(click_values) if click_values else None
        impressions = sum(impression_values) if impression_values else None
        positioned = [row for row in items if row["position"] is not None]
        weighted_position_den = sum(
            float(row["impressions"]) for row in positioned if row["impressions"] is not None
        )
        weighted_position = None
        if weighted_position_den > 0:
            weighted_position = sum(
                float(row["position"]) * float(row["impressions"])
                for row in positioned if row["impressions"] is not None
            ) / weighted_position_den
        ctr = None
        if clicks is not None and impressions is not None and impressions > 0:
            ctr = clicks / impressions
        non_directional = source.startswith(_GENAI_EXPORT_PREFIX)
        for metric, value, direction, unit in (
            ("impressions", impressions, "HIGHER_BETTER", "count"),
            ("clicks", clicks, "HIGHER_BETTER", "count"),
            ("ctr", ctr, "HIGHER_BETTER", "ratio"),
            ("position", weighted_position, "LOWER_BETTER", "position"),
        ):
            if value is None:
                continue
            key = f"SEARCH|{source}|{surface}|{metric}"
            output[key] = {
                "source": source,
                "metric": f"{surface} {metric}",
                "value": float(value),
                "direction": "STATE" if non_directional else direction,
                "unit": unit,
            }


def _index_signals(connection: sqlite3.Connection, output: dict[str, dict[str, Any]], selected: dict[str, dict[str, Any]]) -> None:
    dataset_ids = _selected_ids(selected)
    if not dataset_ids:
        return
    placeholders = ",".join("?" for _ in dataset_ids)
    rows = connection.execute(
        f"SELECT dataset_id,source,url,verdict,indexing_state,selected_canonical FROM index_observations WHERE dataset_id IN ({placeholders})",
        dataset_ids,
    ).fetchall()
    for row in rows:
        source = str(row["source"])
        url = str(row["url"])
        for metric, value in (
            ("verdict", row["verdict"]),
            ("indexing_state", row["indexing_state"]),
            ("selected_canonical", row["selected_canonical"]),
        ):
            if value is None:
                continue
            key = f"INDEX|{source}|{url}|{metric}"
            output[key] = {"source": source, "metric": metric, "value": str(value), "direction": "STATE", "unit": None}


def _crux_signals(connection: sqlite3.Connection, output: dict[str, dict[str, Any]], selected: dict[str, dict[str, Any]]) -> None:
    dataset_ids = _selected_ids(selected)
    if not dataset_ids:
        return
    placeholders = ",".join("?" for _ in dataset_ids)
    rows = connection.execute(
        f"SELECT * FROM crux_history WHERE dataset_id IN ({placeholders}) ORDER BY COALESCE(period_end,''),rowid",
        dataset_ids,
    ).fetchall()
    latest: dict[tuple[str, str, str, str], sqlite3.Row] = {}
    for row in rows:
        latest[(str(row["target"]), str(row["target_scope"]), str(row["form_factor"] or "ALL"), str(row["metric"]))] = row
    for (target, scope, form, metric), row in latest.items():
        if row["p75"] is None:
            continue
        key = f"CRUX|{scope}|{target}|{form}|{metric}"
        output[key] = {
            "source": "CHROME_UX_REPORT_HISTORY",
            "metric": f"{metric} p75",
            "value": float(row["p75"]),
            "direction": "LOWER_BETTER",
            "unit": "native",
        }


def _compare_windows(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source in sorted(set(before) | set(after)):
        left = before.get(source)
        right = after.get(source)
        if left is None or right is None:
            output.append({
                "source": source,
                "status": "DATA_UNAVAILABLE",
                "baseline_period": _period(left),
                "current_period": _period(right),
                "detail": "Source exists on only one side of the audit pair.",
            })
            continue
        start_left, end_left = _period_dates(left)
        start_right, end_right = _period_dates(right)
        if None in {start_left, end_left, start_right, end_right}:
            status = "UNKNOWN_PERIOD"
            detail = "At least one selected dataset has no complete observation period."
        elif start_left == start_right and end_left == end_right:
            status = "ALIGNED_WINDOW"
            detail = "Observation periods are identical."
        elif max(start_left, start_right) <= min(end_left, end_right):  # type: ignore[arg-type]
            status = "PARTIAL_OVERLAP"
            detail = "Observation periods overlap but are not identical; interpret deltas with caution."
        else:
            status = "NON_OVERLAPPING"
            detail = "Observation periods do not overlap; no temporal association is emitted."
        output.append({
            "source": source,
            "status": status,
            "baseline_period": _period(left),
            "current_period": _period(right),
            "detail": detail,
        })
    return output


def _period(item: dict[str, Any] | None) -> str | None:
    if item is None:
        return None
    start = item.get("period_start")
    end = item.get("period_end")
    if start or end:
        return f"{start or '?'} → {end or '?'}"
    return None


def _period_dates(item: dict[str, Any]) -> tuple[date | None, date | None]:
    def parse(value: Any) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
    return parse(item.get("period_start")), parse(item.get("period_end"))


def _change_row(item: OutcomeChange) -> str:
    delta = "-" if item.delta is None else f"{item.delta:+.4f}".rstrip("0").rstrip(".")
    return f"<tr><td>{escape(item.status)}</td><td>{escape(item.source)}</td><td>{escape(item.metric)}</td><td>{escape(_value(item.before))}</td><td>{escape(_value(item.after))}</td><td>{escape(delta)}</td><td>{escape(item.unit or '-')}</td></tr>"


def _value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


_CSS = """body{margin:0;background:#f5f7fa;color:#273449;font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1450px;margin:auto;padding:32px}.hero,.panel{background:#fff;border:1px solid #e1e6ec;border-radius:7px;padding:24px;margin-bottom:16px}.eyebrow{font-size:12px;text-transform:uppercase;color:#6d7786;letter-spacing:.08em}.table-wrap{overflow:auto;border:1px solid #e1e6ec;border-radius:6px}table{width:100%;border-collapse:collapse;min-width:900px}th,td{padding:9px 10px;border-bottom:1px solid #e1e6ec;text-align:left;vertical-align:top}th{background:#f7f8fb}code{background:#f1f3f6;padding:1px 4px;border-radius:4px}@media(max-width:700px){main{padding:16px}}"""
