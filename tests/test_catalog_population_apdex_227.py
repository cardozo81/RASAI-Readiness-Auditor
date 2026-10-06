from __future__ import annotations

from pathlib import Path
import json
import sqlite3
from types import SimpleNamespace

from rasai import catalog_report_adherence as adherence
from rasai import catalog_report_analysis as analysis
from rasai import catalog_report_page as page
from rasai.synthetic_population_apdex import (
    PopulationProfile,
    PopulationStatistics,
    PopulationStratum,
    StratumStatistics,
    SyntheticPopulationPersistence,
)


def test_cat07_summary_exposes_uad_lighthouse_and_unconfigured_population(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE synthetic_ux_apdex_runs(
                audit_id TEXT,
                status TEXT,
                configuration TEXT
            );
            CREATE TABLE web_performance_observations(
                audit_id TEXT,
                device TEXT,
                performance_score REAL,
                lcp_lab_ms REAL,
                strategy TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO synthetic_ux_apdex_runs VALUES (?,?,?)",
            (
                "AUD-UAD",
                "SUCCESS",
                json.dumps({
                    "measurement_contract": {"version": "UAD-BOUNDARY-001"},
                    "population_profile_json": None,
                }),
            ),
        )
        connection.execute(
            "INSERT INTO web_performance_observations VALUES (?,?,?,?,?)",
            ("AUD-UAD", "MOBILE", 28.0, 7800.0, "PAGESPEED_INSIGHTS"),
        )

    html = page._cat07_methodology_summary_html(
        database,
        SimpleNamespace(audit_id="AUD-UAD"),
    )

    assert "UAD-BOUNDARY-001" in html
    assert "settle pós-load" in html
    assert "network-idle" in html
    assert "LCP" in html
    assert "sem contradição matemática" in html
    assert "PageSpeed/Lighthouse pertence ao CAT-04" in html
    assert "28" in html
    assert "7 800" in html or "7800" in html
    assert "Não configurado nesta AUD" in html
    assert "não os torna equivalentes a Dynatrace RUM" in html


def test_cat07_summary_reports_configured_population_without_merging_it_into_baseline(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE synthetic_ux_apdex_runs(
                audit_id TEXT,
                status TEXT,
                configuration TEXT
            );
            CREATE TABLE synthetic_population_apdex_runs(
                audit_id TEXT,
                status TEXT,
                measurement_contract_version TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO synthetic_ux_apdex_runs VALUES (?,?,?)",
            (
                "AUD-POP-CONFIG",
                "SUCCESS",
                json.dumps({
                    "measurement_contract": {"version": "UAD-BOUNDARY-001"},
                    "population_profile_json": json.dumps({
                        "population_profile_id": "POP-1",
                        "profile_version": "1",
                    }),
                }),
            ),
        )
        connection.execute(
            "INSERT INTO synthetic_population_apdex_runs VALUES (?,?,?)",
            ("AUD-POP-CONFIG", "SUCCESS", "UAD-BOUNDARY-001"),
        )

    html = page._cat07_methodology_summary_html(
        database,
        SimpleNamespace(audit_id="AUD-POP-CONFIG"),
    )

    assert "Baseline Synthetic User Experience Apdex" in html
    assert "Synthetic Population Apdex" in html
    assert "Configurado nesta AUD" in html
    assert "Não configurado nesta AUD" not in html
    assert "não entram na fórmula" not in html  # no Lighthouse observation was persisted
    assert "não os torna equivalentes a Dynatrace RUM" in html


def test_cat07_summary_does_not_retroactively_infer_uad_boundary(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE synthetic_ux_apdex_runs(audit_id TEXT,status TEXT,configuration TEXT)"
        )
        connection.execute(
            "INSERT INTO synthetic_ux_apdex_runs VALUES (?,?,?)",
            ("AUD-LEGACY", "SUCCESS", "{}"),
        )

    html = page._cat07_methodology_summary_html(
        database,
        SimpleNamespace(audit_id="AUD-LEGACY"),
    )

    assert "Não identificada na provenance persistida desta AUD" in html
    assert "não atribui UAD-BOUNDARY-001 retroativamente" in html


def test_cat07_projects_population_separately_with_provenance_and_limits(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
            CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT NOT NULL);
            INSERT INTO audits VALUES ('AUD-POP');
            INSERT INTO pages VALUES ('PAGE-1','AUD-POP');
            """
        )

    workspace = SimpleNamespace(database=database)
    profile = PopulationProfile(
        population_profile_id="POP-MOBILE-CONTROLLED",
        profile_version="1",
        weight_source="ANALYTICS",
        weight_source_ref="analytics-export-2026-10",
        target_samples_per_page=100,
        strata=(
            PopulationStratum(
                "constrained", 40.0, "MOBILE",
                "mobile-balanced-chromium", "mobile-entry", "mobile-3g-constrained", "cold",
            ),
            PopulationStratum(
                "balanced", 60.0, "MOBILE",
                "mobile-balanced-chromium", "mobile-balanced", "mobile-4g-balanced", "warm",
            ),
        ),
    )
    with SyntheticPopulationPersistence(workspace) as store:
        store.upsert_run(
            "AUD-POP", profile,
            device="MOBILE",
            kpm="USER_ACTION_DURATION",
            measurement_contract_version="UAD-BOUNDARY-001",
            status="SUCCESS",
            configuration={"execution_policy": {"randomization": "NONE", "geography": "NOT_MODELED"}},
        )
        store.upsert_stratum(
            "AUD-POP", "PAGE-1", "https://example.test/", profile.strata[0],
            StratumStatistics(
                "constrained", 40, 40, 0, 10, 10, 20, 0.375,
                4000.0, 5000.0, 6500.0, 8000.0, (4000.0,) * 40,
            ),
        )
        store.upsert_stratum(
            "AUD-POP", "PAGE-1", "https://example.test/", profile.strata[1],
            StratumStatistics(
                "balanced", 60, 60, 0, 50, 5, 5, 0.875,
                900.0, 1200.0, 1800.0, 2400.0, (900.0,) * 60,
            ),
        )
        store.upsert_summary(
            "AUD-POP", "PAGE-1", "https://example.test/",
            PopulationStatistics(
                status="SUCCESS",
                weighted_apdex=0.675,
                observed_weight_percent=100.0,
                satisfied_count=60,
                tolerating_count=15,
                frustrated_count=25,
                weighted_satisfied_share=0.70,
                weighted_tolerating_share=0.10,
                weighted_frustrated_share=0.20,
                median_ms=900.0,
                p75_ms=4000.0,
                p90_ms=4000.0,
                p95_ms=4000.0,
                standard_error=0.04,
                ci95_low=0.597,
                ci95_high=0.753,
                valid_samples=100,
                invalid_samples=0,
            ),
        )

    html = adherence._synthetic_population_projection_html(
        database,
        SimpleNamespace(audit_id="AUD-POP"),
        analysis,
        page,
    )
    assert "Apdex populacional sintético" in html
    assert "Apdex populacional ponderado" in html
    assert "0.675" in html
    assert "100.0%" in html
    assert "POP-MOBILE-CONTROLLED" in html
    assert "ANALYTICS" in html
    assert "analytics-export-2026-10" in html
    assert "mobile-3g-constrained" in html
    assert "não substitui o Apdex efetivo baseline" in html
    assert "não é apresentada como RUM" in html
    assert "não modela geografia de rede" in html
    assert "incerteza amostral" in html
    assert "não mede erro de representatividade" in html
