from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sqlite3
import tempfile

from rasai.catalog_state_trust import install


def _data(*catalogs: str):
    selected = set(catalogs)
    return SimpleNamespace(
        audit_id="AUD-1",
        selected=selected,
        work_items=[],
        catalog_items={},
        configuration={"audit_catalog": {"selected": sorted(selected)}},
        config_hash="test-plan",
        computed_hash="test-plan",
        targets=(),
    )


def _database(root: Path) -> Path:
    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE audits(audit_id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO audits VALUES ('AUD-1')")
        connection.commit()
    finally:
        connection.close()
    return database


def test_cat02_does_not_treat_unrelated_lighthouse_row_as_accessibility_result() -> None:
    install()
    from rasai import catalog_report_page as page

    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "CREATE TABLE web_performance_observations(audit_id TEXT,performance_score REAL,accessibility_score REAL)"
            )
            connection.execute("INSERT INTO web_performance_observations VALUES ('AUD-1',91,NULL)")
            connection.commit()
        finally:
            connection.close()

        status, tone, detail = page._catalog_status(database, _data("CAT-02"), "CAT-02")
        assert status == "SEM RESULTADO"
        assert tone == "warn"
        assert "acessibilidade" in detail.casefold()
        assert not page._catalog_sources(database, _data("CAT-02"), "CAT-02")


def test_cat04_success_without_measurement_is_partial() -> None:
    install()
    from rasai import catalog_report_page as page

    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE web_performance_runs(audit_id TEXT,status TEXT)")
            connection.execute("INSERT INTO web_performance_runs VALUES ('AUD-1','SUCCESS')")
            connection.commit()
        finally:
            connection.close()

        status, tone, detail = page._catalog_status(database, _data("CAT-04"), "CAT-04")
        assert status == "PARCIAL"
        assert tone == "warn"
        assert "nenhuma medição" in detail.casefold()


def test_cat06_success_without_samples_or_summary_is_partial() -> None:
    install()
    from rasai import catalog_report_page as page

    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE synthetic_apdex_runs(audit_id TEXT,status TEXT)")
            connection.execute("INSERT INTO synthetic_apdex_runs VALUES ('AUD-1','SUCCESS')")
            connection.commit()
        finally:
            connection.close()

        status, tone, detail = page._catalog_status(database, _data("CAT-06"), "CAT-06")
        assert status == "PARCIAL"
        assert tone == "warn"
        assert "sem amostra/resumo" in detail.casefold()


def test_cat07_success_without_samples_or_summary_is_partial() -> None:
    install()
    from rasai import catalog_report_page as page

    with tempfile.TemporaryDirectory() as directory:
        database = _database(Path(directory))
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE synthetic_ux_apdex_runs(audit_id TEXT,status TEXT)")
            connection.execute("INSERT INTO synthetic_ux_apdex_runs VALUES ('AUD-1','SUCCESS')")
            connection.commit()
        finally:
            connection.close()

        status, tone, detail = page._catalog_status(database, _data("CAT-07"), "CAT-07")
        assert status == "PARCIAL"
        assert tone == "warn"
        assert "sem amostra/resumo" in detail.casefold()
