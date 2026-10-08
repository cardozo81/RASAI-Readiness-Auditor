"""#326: persisted zeros are valid observations, not unavailable metrics."""
from __future__ import annotations

from decimal import Decimal

import pytest

from rasai.catalog_report_presentation import _table, _ui_text


@pytest.mark.parametrize("value,expected", [(0, "0"), (0.0, "0.0"), (Decimal("0.00"), "0.00")])
def test_numeric_zero_is_not_coalesced_into_missing(value, expected) -> None:
    assert _ui_text(value) == expected


def test_non_numeric_empty_compatibility_and_table_semantics() -> None:
    assert _ui_text(None) == ""
    assert _ui_text(False) == ""
    assert _ui_text("") == ""

    body = _table(
        ("Indicador", "Valor"),
        (
            ("Satisfatórias", 0),
            ("Frustradas por erro", 0),
            ("Amostras válidas", 3),
            ("Sem observação", None),
        ),
    )
    assert "<td>0</td>" in body
    assert body.count("<td>0</td>") == 2
    assert "<td>3</td>" in body
    assert "Satisfatórias" in body
