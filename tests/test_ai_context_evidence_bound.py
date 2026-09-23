from __future__ import annotations

from rasai.ai_exchange_log import _normalize_context_interpretation


def _interpretation(evidence_ids: list[str]) -> dict[str, dict[str, object]]:
    values = {
        "risk_profile": "ymyl",
        "ymyl_category": "financial-security",
        "page_purpose": "informational",
        "intended_audience": "general",
        "experience_requirement": "beneficial",
        "freshness_sensitivity": "high",
        "content_origin": "first-party",
    }
    return {
        field: {
            "status": "INTERPRETED",
            "value": value,
            "confidence": 0.8,
            "rationale": "fixture evidence-bound interpretation",
            "evidence_ids": list(evidence_ids),
        }
        for field, value in values.items()
    }


def test_transient_context_rejects_evidence_ids_when_request_supplied_none() -> None:
    result = _normalize_context_interpretation(
        _interpretation(["EV-INVENTED"]),
        allowed_evidence_ids=frozenset(),
    )
    assert result is None


def test_transient_context_accepts_only_ids_supplied_in_request() -> None:
    accepted = _normalize_context_interpretation(
        _interpretation(["EV-1"]),
        allowed_evidence_ids=frozenset({"EV-1", "EV-2"}),
    )
    assert accepted is not None
    assert accepted["risk_profile"]["evidence_ids"] == ("EV-1",)

    rejected = _normalize_context_interpretation(
        _interpretation(["EV-1", "EV-OUTSIDE"]),
        allowed_evidence_ids=frozenset({"EV-1", "EV-2"}),
    )
    assert rejected is None
