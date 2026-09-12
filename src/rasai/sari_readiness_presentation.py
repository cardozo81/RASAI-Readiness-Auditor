"""Public SARI readiness presentation guardrails.

SCORE-GEO-004 deliberately keeps measured quality, measurement strength and
critical readiness gates as separate persisted concepts. This module makes that
separation explicit in the public HTML surfaces so a high measured-quality number
is never presented by itself as "excellent readiness" when the measurement is
partial/insufficient or a critical gate is blocked/unknown.

The module is projection-only. It does not change persisted scores, weights,
RuleExecutions, findings, evidence or critical-gate arithmetic.
"""
from __future__ import annotations

from html import escape
import json
from typing import Any

from rasai.report_observation_reconciliation import (
    install as install_report_observation_reconciliation,
    sari_band,
)


_VALID_READINESS = {"READY", "ATTENTION", "BLOCKED", "UNKNOWN"}


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        if hasattr(row, "keys") and key not in row.keys():
            return default
        value = row[key]
    except (KeyError, IndexError, TypeError, AttributeError):
        return default
    return default if value is None else value


def _limitations(row: Any) -> tuple[str, ...]:
    raw = _row_value(row, "limitations", ())
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = [raw]
    else:
        decoded = raw
    if isinstance(decoded, (list, tuple, set, frozenset)):
        return tuple(str(item) for item in decoded if str(item).strip())
    if decoded:
        return (str(decoded),)
    return ()


def readiness_state(row: Any) -> tuple[str, dict[str, str]]:
    """Return persisted readiness status and critical-gate states for one Overall row."""
    status = "UNKNOWN"
    gates: dict[str, str] = {}
    for item in _limitations(row):
        if item.startswith("READINESS_STATUS:"):
            candidate = item.split(":", 1)[1].strip().upper()
            if candidate in _VALID_READINESS:
                status = candidate
        elif item.startswith("CRITICAL_GATE:"):
            parts = item.split(":", 2)
            if len(parts) == 3:
                gates[parts[1].strip().upper()] = parts[2].strip().upper()

    # Defensive compatibility for a persisted row that has individual gates but no
    # aggregate marker. Do not infer READY unless every persisted gate is PASS.
    if status == "UNKNOWN" and gates:
        values = set(gates.values())
        if "BLOCKED" in values:
            status = "BLOCKED"
        elif "UNKNOWN" in values:
            status = "UNKNOWN"
        elif "WARNING" in values:
            status = "ATTENTION"
        elif values and values <= {"PASS"}:
            status = "READY"
    return status, gates


def public_readiness_condition(row: Any) -> tuple[str, str, str]:
    """Return visual condition, primary readiness label and numeric-quality label."""
    raw_value = _row_value(row, "value")
    value = None if raw_value is None else float(raw_value)
    quality_state, quality_label, quality_range = sari_band(value)
    quality_text = quality_label if quality_state == "neutral" else f"{quality_label} ({quality_range})"

    consolidation = str(_row_value(row, "consolidation_status", "NOT_CONSOLIDATED")).upper()
    confidence = str(_row_value(row, "confidence", "UNAVAILABLE")).upper()
    readiness, _gates = readiness_state(row)

    if value is None:
        return "neutral", "Readiness não determinada", quality_text
    if consolidation == "NOT_CONSOLIDATED" or confidence == "UNAVAILABLE":
        return "neutral", "Readiness não consolidada", quality_text
    if consolidation == "PARTIAL" or confidence == "LOW":
        return "near", "Readiness com medição parcial", quality_text
    if readiness == "BLOCKED":
        return "critical", "Readiness bloqueada", quality_text
    if readiness == "UNKNOWN":
        return "neutral", "Readiness indeterminada", quality_text
    if readiness == "ATTENTION":
        return "near", "Readiness requer atenção", quality_text

    # READY means the critical operational gates are satisfied. The measured-quality
    # band still determines whether the otherwise-operationally-ready site is strong.
    if quality_state == "expected":
        return "expected", "Readiness pronta", quality_text
    if quality_state == "near":
        return "near", "Readiness pronta, qualidade moderada", quality_text
    if quality_state == "below":
        return "below", "Readiness pronta, qualidade baixa", quality_text
    if quality_state == "critical":
        return "critical", "Readiness pronta, qualidade crítica", quality_text
    return "neutral", "Readiness indeterminada", quality_text


def _score_card_class(condition: str) -> str:
    return {
        "expected": "good",
        "near": "warn",
        "below": "low",
        "critical": "bad",
        "neutral": "neutral",
    }.get(condition, "neutral")


def _gate_detail(gates: dict[str, str]) -> str:
    material = [f"{gate}={state}" for gate, state in sorted(gates.items()) if state != "PASS"]
    return "; ".join(material)


def operational_readiness_panel(data: dict[str, Any]) -> str:
    scores = list(data.get("scores") or [])
    cards: list[str] = []
    for device in ("MOBILE", "DESKTOP"):
        row = next(
            (
                item for item in scores
                if str(_row_value(item, "device", "")).upper() == device
                and str(_row_value(item, "dimension", "")) == "OVERALL_READINESS"
            ),
            None,
        )
        if row is None:
            continue
        label = "Mobile" if device == "MOBILE" else "Desktop"
        condition, readiness_label, quality_label = public_readiness_condition(row)
        readiness, gates = readiness_state(row)
        value = _row_value(row, "value")
        score = "-" if value is None else f"{float(value):.1f}/100"
        coverage = f"{float(_row_value(row, 'coverage', 0.0)) * 100:.1f}%"
        confidence = str(_row_value(row, "confidence", "UNAVAILABLE"))
        consolidation = str(_row_value(row, "consolidation_status", "NOT_CONSOLIDATED"))
        gate_detail = _gate_detail(gates)
        cards.append(
            f"<article class='ref-card condition-{escape(condition, quote=True)}'>"
            f"<h3>{escape(label)}</h3>"
            f"<p><strong>{escape(readiness_label)}</strong></p>"
            f"<p>Qualidade medida: <strong>{escape(score)}</strong> · {escape(quality_label)}</p>"
            f"<p>Coverage {escape(coverage)} · Confidence {escape(confidence)} · Consolidation {escape(consolidation)}</p>"
            f"<p>Critical readiness: <strong>{escape(readiness)}</strong>"
            + (f" · {escape(gate_detail)}" if gate_detail else "")
            + "</p></article>"
        )
    if not cards:
        return ""
    return (
        "<section id='sari-public-readiness-reading' class='panel' data-sari-public-readiness='true'>"
        "<div class='kicker'>Leitura executiva do SARI</div>"
        "<h2>Nota medida não substitui readiness operacional</h2>"
        "<p class='intro'>O número 0-100 descreve a qualidade do universo efetivamente avaliado. "
        "A conclusão pública de readiness também exige força suficiente da medição (Coverage, Confidence e Consolidation) "
        "e leitura dos Critical Readiness Gates. Portanto, uma nota acima de 90 não é apresentada isoladamente como "
        "readiness excelente quando a medição está parcial/não consolidada ou quando Discovery, Indexability ou Extraction "
        "estão BLOCKED/UNKNOWN.</p>"
        "<div class='grid'>" + "".join(cards) + "</div>"
        "<div class='notice'><strong>Integrações externas:</strong> erro de provider/API/coleta não é defeito do website e "
        "não gera penalidade artificial no SARI. Um finding técnico externo só participa do score quando existe uma BR-GEO "
        "equivalente, mapeamento explícito e evidência persistida sem dupla pontuação.</div>"
        "</section>"
    )


def install() -> None:
    """Install the public-readiness projection after the generic score-band layer."""
    # Direct report-finalizer callers may bypass the top-level entrypoints. Ensure the
    # common score-band/CSS projection is installed before applying the readiness guard.
    install_report_observation_reconciliation()

    from rasai import rasai_readiness_reporting as reporting

    if getattr(reporting, "_rasai_public_readiness_guardrails", False):
        return

    original_governance = reporting._sari_governance_block

    def sari_condition(row: Any) -> tuple[str, str]:
        condition, readiness_label, quality_label = public_readiness_condition(row)
        return condition, f"{readiness_label} · qualidade {quality_label}"

    def overall_card(scores: list[Any], device: str) -> str:
        row = next(
            (
                item for item in scores
                if str(_row_value(item, "device", "")).upper() == device
                and str(_row_value(item, "dimension", "")) == "OVERALL_READINESS"
            ),
            None,
        )
        label = "Mobile" if device == "MOBILE" else "Desktop"
        if row is None:
            return (
                f"<article class='score-card neutral'><div class='label'>{label} - {reporting.PUBLIC_METHOD_VERSION}</div>"
                "<div class='score-number'>Indisponível</div>"
                "<span class='score-band-label neutral'>Readiness não determinada</span>"
                "<p class='intro'>Overall não persistido.</p></article>"
            )

        raw_value = _row_value(row, "value")
        condition, readiness_label, quality_label = public_readiness_condition(row)
        css = _score_card_class(condition)
        coverage = f"{float(_row_value(row, 'coverage', 0.0)) * 100:.0f}%"
        confidence_raw = str(_row_value(row, "confidence", "UNAVAILABLE"))
        confidence = reporting._STATUS_LABELS.get(confidence_raw, confidence_raw)
        consolidation_raw = str(_row_value(row, "consolidation_status", "NOT_CONSOLIDATED"))
        consolidation = reporting._STATUS_LABELS.get(consolidation_raw, consolidation_raw)
        readiness, gates = readiness_state(row)
        gate_detail = _gate_detail(gates)

        if raw_value is None:
            score_markup = "<div class='score-number'>Não consolidado</div>"
        else:
            score_markup = f"<div class='score-number'>{float(raw_value):.1f}<span>/100</span></div>"

        qualifier = (
            f"<p class='intro'><strong>Qualidade do universo medido:</strong> {escape(quality_label)}. "
            "A badge acima é a conclusão de readiness e prevalece sobre a leitura isolada da nota."
            + (f" Gates não-PASS: {escape(gate_detail)}." if gate_detail else "")
            + "</p>"
        )
        return (
            f"<article class='score-card {css}'><div class='label'>{label} - {reporting.PUBLIC_METHOD_VERSION}</div>"
            f"{score_markup}<span class='score-band-label {condition}'>{escape(readiness_label)}</span>"
            "<div class='score-meta'>"
            f"<div><small>Cobertura</small><strong>{escape(coverage)}</strong></div>"
            f"<div><small>Confiança</small><strong>{escape(confidence)}</strong></div>"
            f"<div><small>Consolidação</small><strong>{escape(consolidation)}</strong></div>"
            f"<div><small>Readiness</small><strong>{escape(readiness)}</strong></div>"
            "</div>" + qualifier + "</article>"
        )

    def governance_with_public_readiness(data: dict[str, Any]) -> str:
        return operational_readiness_panel(data) + original_governance(data)

    reporting._sari_condition = sari_condition
    reporting._overall_card = overall_card
    reporting._sari_governance_block = governance_with_public_readiness
    reporting._rasai_public_readiness_guardrails = True
