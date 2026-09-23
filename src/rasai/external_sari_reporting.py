"""Transparent report projection for BR-GEO-060 external SARI corroboration."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any

from rasai.external_sari import MAX_OVERALL_IMPACT_POINTS, MIN_OBSERVED_URL_RATIO, RULE_ID
from rasai.score_geo_004 import GROUP_WEIGHTS

_MARKER = "RASAI_EXTERNAL_SARI_CORROBORATION"
_GROUP_ID = "EXTERNAL_CRAWL_CORROBORATION"
_GROUP_LABEL = "External Crawl Corroboration"


def install() -> None:
    from rasai import report_navigation, report_presentation

    # The scoring vocabulary is extensible during pre-publication. Keep the canonical
    # presentation maps aligned when this scoring extension is installed so generic
    # scoring tables never expose the raw machine group identifier.
    report_presentation.SCORING_CONCEPT_LABELS.setdefault(_GROUP_ID, _GROUP_LABEL)
    report_presentation._PUBLIC_LABELS.setdefault(_GROUP_ID, _GROUP_LABEL)
    report_navigation._RULE_TOOLTIPS[RULE_ID] = (
        "Corroboração externa de discovery - evidência histórica positiva do Common Crawl. "
        "É positive-only, não integra Critical Gates, não prova indexação Google/Bing e tem impacto máximo de 0,45 ponto no SARI Overall."
    )
    if getattr(report_navigation, "_rasai_external_sari_reporting", False):
        return
    original = report_navigation.normalize_report_navigation

    def normalize_with_external_sari(report_dir: str | Path, *args: Any, **kwargs: Any):
        result = original(report_dir, *args, **kwargs)
        root = Path(report_dir)
        state = _load_state(root.parent)
        for filename in ("readiness.html", "scoring.html"):
            _inject(root / filename, state=state, detailed=(filename == "scoring.html"))
        return result

    report_navigation.normalize_report_navigation = normalize_with_external_sari
    report_navigation._rasai_external_sari_reporting = True


def _load_state(workspace: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "materialized": False,
        "result": "NÃO APLICADO",
        "ratio": None,
        "dataset_id": None,
        "evidence_source": "Common Crawl CDX History",
        "rule_id": RULE_ID,
    }
    database = workspace / "audit.db"
    if database.is_file():
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                """SELECT re.result,re.observed_value,re.evidence_ids
                   FROM rule_executions re WHERE re.rule_id=?
                   ORDER BY re.executed_at DESC LIMIT 1""",
                (RULE_ID,),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        finally:
            connection.close()
        if row is not None:
            try:
                observed = json.loads(str(row["observed_value"] or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                observed = {}
            result.update(
                materialized=True,
                result=str(row["result"] or "PASS"),
                ratio=observed.get("observed_url_ratio"),
                dataset_id=observed.get("dataset_id"),
                selected=observed.get("selected_url_count"),
                observed=observed.get("observed_url_count"),
            )
    state_path = workspace / "artifacts" / "observability" / "common-crawl-pre-scoring-state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
        if isinstance(state, dict):
            result.setdefault("selected", state.get("selected_url_count"))
            result.setdefault("observed", state.get("observed_url_count"))
            if result.get("ratio") is None:
                result["ratio"] = state.get("observed_url_ratio")
            if result.get("dataset_id") is None:
                datasets = state.get("datasets") or []
                if isinstance(datasets, list) and datasets:
                    result["dataset_id"] = datasets[0]
            result["collection_state"] = state.get("collection_state")
            result["reason"] = state.get("reason")
    return result


def _inject(path: Path, *, state: dict[str, Any], detailed: bool) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    start = f"<!-- {_MARKER}:START -->"
    end = f"<!-- {_MARKER}:END -->"
    while True:
        begin = text.find(start)
        if begin < 0:
            break
        finish = text.find(end, begin + len(start))
        if finish < 0:
            break
        text = text[:begin] + text[finish + len(end):]

    text = text.replace(
        "Search Console e demais outcomes de Observability;",
        "Search Console, CrUX History, Microsoft Clarity e demais outcomes de Observability não mapeados explicitamente;",
    )

    panel = _panel(state, detailed=detailed)
    position = text.find("</main>")
    if position < 0:
        position = text.find("</body>")
    if position < 0:
        position = len(text)
    block = start + panel + end
    text = text[:position] + block + text[position:]
    path.write_text(text, encoding="utf-8", newline="\n")


def _panel(state: dict[str, Any], *, detailed: bool) -> str:
    weight = GROUP_WEIGHTS["DISCOVERY_ACCESS"][_GROUP_ID]
    status = "APLICADA" if state.get("materialized") else "NÃO APLICADA"
    ratio = _pct(state.get("ratio"))
    selected = state.get("selected")
    observed = state.get("observed")
    reason = str(state.get("reason") or "").strip()
    detail = ""
    if detailed:
        detail = (
            "<div class='table-wrap'><table><thead><tr>"
            "<th>Regra</th><th>Dimensão / grupo</th><th>Peso no grupo</th><th>Impacto máximo Overall</th>"
            "<th>Threshold</th><th>Resultado desta auditoria</th></tr></thead><tbody><tr>"
            f"<td><strong>{escape(RULE_ID)}</strong></td>"
            "<td>Discovery &amp; Crawler Access / External Crawl Corroboration</td>"
            f"<td>{weight * 100:.1f}% de DISCOVERY_ACCESS</td>"
            f"<td>{MAX_OVERALL_IMPACT_POINTS:.2f} ponto</td>"
            f"<td>captura positiva em pelo menos {MIN_OBSERVED_URL_RATIO * 100:.0f}% das URLs bounded selecionadas</td>"
            f"<td>{escape(status)}</td></tr></tbody></table></div>"
        )
    sample = ""
    if selected is not None:
        sample = (
            f" <strong>Amostra:</strong> {escape(str(observed if observed is not None else 0))}/"
            f"{escape(str(selected))} URL(s) observada(s); razão {escape(ratio)}."
        )
    reason_text = f" <strong>Motivo:</strong> {escape(reason)}." if reason else ""
    return (
        "<section class='panel' data-external-sari-corroboration='true'>"
        "<div class='kicker'>SARI · evidência externa bounded</div>"
        "<h2>Common Crawl como corroboração de Discovery</h2>"
        "<p>O SARI admite uma única evidência externa neste contrato: presença histórica positiva no Common Crawl, "
        "materializada como <code>BR-GEO-060</code>. Ela não prova indexação Google/Bing, ranking, disponibilidade atual "
        "ou acesso por crawler de IA. Ausência, erro da API, alvo inelegível ou amostra insuficiente <strong>não vira FAIL, "
        "não recebe zero e não reduz Coverage/Confidence</strong>.</p>"
        f"<div class='metric-grid'><div class='metric'><span>Estado</span><strong>{escape(status)}</strong></div>"
        f"<div class='metric'><span>Peso em Discovery</span><strong>{weight * 100:.1f}%</strong></div>"
        f"<div class='metric'><span>Impacto máximo no SARI</span><strong>{MAX_OVERALL_IMPACT_POINTS:.2f}</strong></div>"
        f"<div class='metric'><span>Razão observada</span><strong>{escape(ratio)}</strong></div></div>"
        f"{detail}<p class='intro'>{sample}{reason_text} A regra não participa de Critical Readiness Gates e não pode "
        "compensar um bloqueio atual de acesso/robots/redirect.</p></section>"
    )


def _pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(value)
