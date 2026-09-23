from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from rasai.catalog_report_catalog_state import _catalog_status, _configuration_rows


def _data():
    return SimpleNamespace(
        configuration={},
        config_hash="",
        computed_hash="",
        selected=set(),
        catalog_items={},
        targets=("https://example.com/",),
        work_items=[],
        audit_id="AUD-MISSING-PLAN",
    )


def test_missing_plan_is_not_reported_as_unrequested_catalog(tmp_path: Path) -> None:
    data = _data()
    status, tone, detail = _catalog_status(tmp_path / "unused.db", data, "CAT-01")

    assert status == "INDETERMINADO"
    assert tone == "warn"
    assert "snapshot" in detail.casefold()

    rows = _configuration_rows(data, "CAT-01")
    included = rows[0]
    assert included[0] == "Incluído nesta auditoria"
    assert "Indeterminado" in str(included[1])
