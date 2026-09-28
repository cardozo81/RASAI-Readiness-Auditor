from __future__ import annotations

from copy import deepcopy

from rasai.improvement_intelligence import _evidence_fingerprint


def _finding(*, finding_id: str = "FND-A", evidence_id: str = "EV-A") -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "domain": "SEMANTICS_STRUCTURE",
        "severity": "MEDIUM",
        "title": "Dados estruturados ausentes",
        "observation": '{"blocks":0,"present":false}',
        "evidence_ids": [evidence_id],
        "impacts": {
            "performance": 0,
            "seo": 2,
            "best_practices": 0,
            "accessibility": 0,
            "ai_access": 3,
            "security": 0,
        },
        "source": "RASAI_FINDING",
        "selector": None,
        "original_html": None,
        "details": {
            "rule_id": "BR-GEO-034",
            "expected_condition": "structured data is interpretable when present",
            "status": "OPEN",
        },
    }


def test_fingerprint_ignores_regenerated_finding_and_evidence_ids() -> None:
    first = _evidence_fingerprint(
        [_finding(finding_id="CORE:FND-OLD", evidence_id="EV-GEO-OLD")],
        {"status": "COMPLETE", "query": "seguro de vida"},
        [{"device": "MOBILE", "performance_score": 1.0}],
    )
    replayed = _evidence_fingerprint(
        [_finding(finding_id="CORE:FND-NEW", evidence_id="EV-GEO-NEW")],
        {"status": "COMPLETE", "query": "seguro de vida"},
        [{"device": "MOBILE", "performance_score": 1.0}],
    )

    assert replayed == first


def test_fingerprint_is_independent_of_finding_order_and_identity() -> None:
    first_finding = _finding(finding_id="FND-A", evidence_id="EV-A")
    second_finding = _finding(finding_id="FND-B", evidence_id="EV-B")
    second_finding["title"] = "Canonical ausente"
    second_finding["details"] = {
        "rule_id": "BR-GEO-013",
        "expected_condition": "canonical declaration is interpretable",
        "status": "OPEN",
    }

    forward = _evidence_fingerprint([first_finding, second_finding], {}, [])
    reverse_with_new_ids = _evidence_fingerprint(
        [
            {**second_finding, "finding_id": "FND-X", "evidence_ids": ["EV-X"]},
            {**first_finding, "finding_id": "FND-Y", "evidence_ids": ["EV-Y"]},
        ],
        {},
        [],
    )

    assert reverse_with_new_ids == forward


def test_fingerprint_changes_when_finding_material_changes() -> None:
    baseline = _finding()
    baseline_hash = _evidence_fingerprint([baseline], {}, [])

    for field, value in (
        ("severity", "HIGH"),
        ("title", "Outro título"),
        ("observation", '{"blocks":1,"present":true}'),
        ("source", "OTHER_SOURCE"),
    ):
        changed = deepcopy(baseline)
        changed[field] = value
        assert _evidence_fingerprint([changed], {}, []) != baseline_hash

    changed_details = deepcopy(baseline)
    changed_details["details"]["rule_id"] = "BR-GEO-035"
    assert _evidence_fingerprint([changed_details], {}, []) != baseline_hash


def test_fingerprint_changes_when_material_finding_is_added_or_removed() -> None:
    first = _finding()
    second = deepcopy(first)
    second["title"] = "Segundo finding"
    second["details"]["rule_id"] = "BR-GEO-035"

    one = _evidence_fingerprint([first], {}, [])
    two = _evidence_fingerprint([first, second], {}, [])

    assert one != two


def test_fingerprint_remains_sensitive_to_search_and_lighthouse_material() -> None:
    finding = _finding()
    baseline = _evidence_fingerprint(
        [finding],
        {"status": "COMPLETE", "position": None},
        [{"device": "MOBILE", "performance_score": 1.0}],
    )
    changed_search = _evidence_fingerprint(
        [finding],
        {"status": "COMPLETE", "position": 3},
        [{"device": "MOBILE", "performance_score": 1.0}],
    )
    changed_lighthouse = _evidence_fingerprint(
        [finding],
        {"status": "COMPLETE", "position": None},
        [{"device": "MOBILE", "performance_score": 0.8}],
    )

    assert changed_search != baseline
    assert changed_lighthouse != baseline
