from __future__ import annotations

import json

from rasai import report_site
from rasai.sari_readiness_presentation import install


def _overall(*, readiness: str, gates: dict[str, str]) -> dict[str, object]:
    limitations = [f"READINESS_STATUS:{readiness}"]
    limitations.extend(f"CRITICAL_GATE:{name}:{state}" for name, state in gates.items())
    return {
        "device": "MOBILE",
        "dimension": "OVERALL_READINESS",
        "value": 90.6,
        "coverage": 0.97,
        "confidence": "HIGH",
        "consolidation_status": "CONSOLIDATED",
        "limitations": json.dumps(limitations),
    }


def test_device_card_uses_readiness_attention_as_primary_visual_state() -> None:
    install()
    html = report_site._overall_card(
        [_overall(readiness="ATTENTION", gates={"DISCOVERY": "WARNING", "INDEXABILITY": "WARNING", "EXTRACTION": "PASS"})],
        "MOBILE",
    )
    assert "score-card warn" in html
    assert "Readiness requer atenção" in html
    assert "Qualidade Excelente (90-100)" in html
    assert "score-card good" not in html


def test_device_card_can_be_green_only_when_operational_readiness_is_ready() -> None:
    install()
    html = report_site._overall_card(
        [_overall(readiness="READY", gates={"DISCOVERY": "PASS", "INDEXABILITY": "PASS", "EXTRACTION": "PASS"})],
        "MOBILE",
    )
    assert "score-card good" in html
    assert "Readiness pronta" in html
    assert "Qualidade Excelente (90-100)" in html
