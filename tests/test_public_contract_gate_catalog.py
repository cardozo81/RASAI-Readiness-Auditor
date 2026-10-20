from __future__ import annotations

from rasai import public_contract_gate as gate


def test_runtime_contract_uses_report_catalog_only() -> None:
    errors: list[str] = []

    gate._check_runtime(errors)

    assert errors == []
    assert gate.CATALOG_REPORT_DIR == "report-catalog"
    assert "index.html" in gate.CATALOG_REPORT_FILENAMES
    assert "methodology.html" in gate.CATALOG_REPORT_FILENAMES



def test_scoring_contract_gate_accepts_versioned_replay_and_rejects_unapproved_ids() -> None:
    assert gate.EXPECTED_SCORING_VERSION == "SCORE-GEO-005"
    assert gate._OLD_VERSION_RE.search("SCORE-GEO-005") is None
    assert gate._OLD_VERSION_RE.search("SCORE-GEO-004") is None
    assert gate._OLD_VERSION_RE.search("SCORE-GEO-999") is not None
