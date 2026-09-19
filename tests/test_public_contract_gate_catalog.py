from __future__ import annotations

from rasai import public_contract_gate as gate


def test_runtime_contract_uses_report_catalog_only() -> None:
    errors: list[str] = []

    gate._check_runtime(errors)

    assert errors == []
    assert gate.CATALOG_REPORT_DIR == "report-catalog"
    assert "index.html" in gate.CATALOG_REPORT_FILENAMES
    assert "methodology.html" in gate.CATALOG_REPORT_FILENAMES
