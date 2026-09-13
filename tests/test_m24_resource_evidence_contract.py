from __future__ import annotations

from types import SimpleNamespace

import pytest

from rasai import m24_ai, technical_ai_eligibility


def _response(resource: str, evidence_id: str) -> dict[str, object]:
    return {
        "summary_pt": "Resumo técnico baseado somente nas evidências fornecidas.",
        "actions": [],
        "resource_assessments": [
            {
                "resource": resource,
                "verdict": "NEUTRAL",
                "confidence": 0.8,
                "evidence_ids": [evidence_id],
                "rationale_pt": "Classificação limitada à evidência persistida do recurso.",
            }
        ],
        "policy_note_pt": "Requer validação humana para qualquer mudança de política.",
    }


def test_m24_prompt_exposes_resource_scoped_evidence_universe() -> None:
    technical_ai_eligibility._install_m24_resource_evidence_contract()
    candidate = SimpleNamespace(
        structured_mode="json_object",
        name="DEEPSEEK",
        model="deepseek-v4-flash",
        requested_reasoning_effort="LOW",
    )
    payload = m24_ai._candidate_payload(
        candidate,
        schema={"type": "object"},
        instructions="Contrato técnico.",
        facts=[
            {
                "category": "ROBOTS",
                "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
                "evidence_ids": ["EV-ROBOTS-1"],
            },
            {
                "category": "SITEMAP",
                "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
                "evidence_ids": ["EV-SITEMAP-1"],
            },
        ],
    )
    instructions = str(payload["instructions"])
    assert 'resource_evidence_ids={"ROBOTS":["EV-ROBOTS-1"],"SITEMAP":["EV-SITEMAP-1"]}' in instructions
    assert "não cruze ROBOTS com SITEMAP" in instructions


def test_m24_validator_accepts_matching_resource_evidence() -> None:
    result = m24_ai._validate(
        _response("ROBOTS", "EV-ROBOTS-1"),
        allowed_codes=frozenset(),
        allowed_evidence=frozenset({"EV-ROBOTS-1", "EV-SITEMAP-1"}),
        resource_evidence={
            "ROBOTS": frozenset({"EV-ROBOTS-1"}),
            "SITEMAP": frozenset({"EV-SITEMAP-1"}),
        },
    )
    assert result["resource_assessments"][0]["evidence_ids"] == ["EV-ROBOTS-1"]


def test_m24_validator_still_rejects_cross_resource_evidence() -> None:
    with pytest.raises(ValueError, match="outside its resource universe"):
        m24_ai._validate(
            _response("ROBOTS", "EV-SITEMAP-1"),
            allowed_codes=frozenset(),
            allowed_evidence=frozenset({"EV-ROBOTS-1", "EV-SITEMAP-1"}),
            resource_evidence={
                "ROBOTS": frozenset({"EV-ROBOTS-1"}),
                "SITEMAP": frozenset({"EV-SITEMAP-1"}),
            },
        )
