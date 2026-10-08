"""#327: read-only sampling sufficiency, no fabricated statistical confidence."""
from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from rasai.apdex_sampling_reliability_reporting import apdex_sampling_reliability_html as report


def _db(path: Path, *, cat: str, groups: list[tuple[str, int, int, int]]) -> None:
    table = (
        "synthetic_apdex_summaries" if cat == "CAT-06"
        else "synthetic_ux_apdex_summaries"
    )
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE " + table +
            "(audit_id TEXT, device TEXT, valid_samples INTEGER,"
            "small_group INTEGER, final_group INTEGER)"
        )
        con.executemany(
            "INSERT INTO " + table + " VALUES (?,?,?,?,?)",
            [("AUD-1", device, valid, small, final)
             for device, valid, small, final in groups]
            + [("AUD-OTHER", "MOBILE", 100, 0, 1)],
        )


@pytest.mark.parametrize("catalog", ["CAT-06", "CAT-07"])
def test_three_valid_samples_are_limited_not_invalid_and_readonly(
    tmp_path: Path, catalog: str,
) -> None:
    db = tmp_path / "audit.db"
    _db(db, cat=catalog, groups=[("MOBILE", 3, 1, 0)])
    before = db.read_bytes()
    html = report(db, "AUD-1", catalog)
    assert "LIMITADA para generalização" in html
    assert "amostras válidas por grupo: 3" in html
    assert "100 amostras" in html
    assert "meta configurada" in html
    assert "intervalo de confiança estatística" in html
    assert "AUD-OTHER" not in html
    assert db.read_bytes() == before


@pytest.mark.parametrize("target_met", [False, True])
def test_cat07_real_smoke_three_of_three_is_limited_even_when_final(
    tmp_path: Path, target_met: bool,
) -> None:
    """Real AUD shape: M25 small_group=1 AND final_group=1 at n=3."""
    db = tmp_path / "audit.db"
    _db(db, cat="CAT-07", groups=[
        ("MOBILE", 3, 1, int(target_met)),
        ("POPULATION", 3, 1, 1),
    ])
    text = report(db, "AUD-1", "CAT-07")
    assert "LIMITADA para generalização" in text
    assert "amostras válidas por grupo: 3" in text
    assert "indeterminada" not in text
    assert f"atingida ({int(target_met)}/1 grupo(s))" in text
    assert "não define suficiência estatística" in text


def test_cat07_methodological_minimum_can_precede_operational_target(
    tmp_path: Path,
) -> None:
    db = tmp_path / "audit.db"
    _db(db, cat="CAT-07", groups=[("MOBILE", 100, 0, 0)])
    text = report(db, "AUD-1", "CAT-07")
    assert "MÍNIMO METODOLÓGICO ATINGIDO" in text
    assert "atingida (0/1 grupo(s))" in text


def test_normal_group_is_not_called_statistically_confident(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    _db(db, cat="CAT-06", groups=[("MOBILE", 100, 0, 1)])
    html = report(db, "AUD-1", "CAT-06")
    assert "MÍNIMO METODOLÓGICO ATINGIDO" in html
    assert "não equivale a confiança estatística" in html


def test_mixed_groups_disclose_variance_of_sufficiency(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    _db(db, cat="CAT-07", groups=[("MOBILE", 3, 1, 0), ("DESKTOP", 120, 0, 1)])
    html = report(db, "AUD-1", "CAT-07")
    assert "HETEROGÊNEA: 1/2 grupo(s) pequenos" in html
    assert "3–120" in html


def test_population_rows_do_not_inflate_cat07_baseline(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    _db(db, cat="CAT-07", groups=[("MOBILE", 3, 1, 0), ("POPULATION", 300, 0, 1)])
    html = report(db, "AUD-1", "CAT-07")
    assert "Grupos observados: 1;" in html
    assert "LIMITADA" in html
    assert "300" not in html


@pytest.mark.parametrize("catalog", ["CAT-06", "CAT-07"])
def test_missing_and_legacy_schema_are_inconclusive(tmp_path: Path, catalog: str) -> None:
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE placeholder (id TEXT)")
    assert "não determinável" in report(db, "AUD-1", catalog)
    table = (
        "synthetic_apdex_summaries" if catalog == "CAT-06"
        else "synthetic_ux_apdex_summaries"
    )
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE " + table + " (audit_id TEXT, valid_samples INTEGER)")
    assert "não determinável" in report(db, "AUD-1", catalog)
    assert report(db, "AUD-1", "CAT-05") == ""


@pytest.mark.parametrize("valid,small,final", [(0, 0, 0), (3, 0, 1), (101, 1, 0), (100, 0, 0)])
def test_inconsistent_group_evidence_is_not_promoted(
    tmp_path: Path, valid: int, small: int, final: int,
) -> None:
    db = tmp_path / "audit.db"
    _db(db, cat="CAT-06", groups=[("MOBILE", valid, small, final)])
    html = report(db, "AUD-1", "CAT-06")
    assert "indeterminada: metadados de grupos" in html
    assert "MÍNIMO METODOLÓGICO ATINGIDO" not in html
