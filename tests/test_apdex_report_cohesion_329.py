"""#329: Apdex report copy is cohesive, nonduplicative and auditable.

No M23/M25 engines, timing, scores or historical AUD records are touched.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sqlite3

import pytest

import rasai.catalog_report_page as page
from rasai.apdex_sampling_reliability_reporting import apdex_sampling_reliability_html


def _summary_db(path: Path) -> None:
    with sqlite3.connect(path) as con:
        for table in ("synthetic_apdex_summaries", "synthetic_ux_apdex_summaries"):
            con.execute(
                "CREATE TABLE " + table + " (audit_id TEXT, device TEXT,"
                "valid_samples INTEGER, small_group INTEGER, final_group INTEGER)"
            )
            con.execute("INSERT INTO " + table + " VALUES (?,?,?,?,?)",
                        ("AUD-1", "MOBILE", 3, 1, 0))


@pytest.mark.parametrize("catalog_id", ["CAT-06", "CAT-07"])
def test_interpretation_organizes_distinct_explanations_in_one_block(
    tmp_path: Path, catalog_id: str,
) -> None:
    db = tmp_path / "audit.db"
    _summary_db(db)
    before = db.read_bytes()
    html = page._apdex_interpretation_html(db, "AUD-1", catalog_id)

    assert html.startswith("<div class='subsection'><h3>Confiabilidade e limites do índice</h3>")
    assert html.endswith("</p></div>")
    assert html.count("<div class='subsection'>") == 1
    assert html.count("<p>") == 2
    assert html.count("</p>") == 2
    assert "<div class='notice" not in html
    assert html.count("Confiabilidade da interpretação do Apdex:") == 1
    assert html.count("Carregamento não é prontidão do conteúdo:") == 1
    assert "LIMITADA para generalização" in html
    assert "amostras válidas por grupo: 3" in html
    assert "100 amostras" in html
    assert "não mede o instante de conteúdo principal pronto" in html
    assert "capture-context.html" in html
    assert "cat-04.html" in html
    assert db.read_bytes() == before


def test_non_apdex_catalog_remains_unchanged(tmp_path: Path) -> None:
    assert page._apdex_interpretation_html(tmp_path / "not-present.db", "AUD-1", "CAT-05") == ""


def test_existing_fragment_contract_stays_supported(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    _summary_db(db)
    traditional = apdex_sampling_reliability_html(db, "AUD-1", "CAT-06")
    compact = apdex_sampling_reliability_html(db, "AUD-1", "CAT-06", compact=True)
    assert traditional.startswith("<div class='notice'>")
    assert traditional.endswith("</div>")
    assert compact.startswith("<p>")
    assert compact.endswith("</p>")
    assert compact.count("LIMITADA para generalização") == 1


def test_partial_status_does_not_repeat_sampling_reliability_discussion(monkeypatch) -> None:
    monkeypatch.setattr(
        page, "_explicit_run",
        lambda database, data, catalog_id: {
            "status": "PARTIAL",
            "reason": "SMALL_GROUP_BELOW_NORMAL_MINIMUM",
            "valid_samples": 3,
            "target_valid_samples": 3,
        },
    )
    body = page._execution_context_notice(Path("not-used"), SimpleNamespace(), "CAT-06")
    assert "3 amostra(s) válida(s)" in body
    assert "meta de 3" in body
    assert "não uma falha de execução" in body
    assert "href='#summary'" in body
    assert "100 amostras" not in body
    assert "intervalo de confiança estatística" not in body
