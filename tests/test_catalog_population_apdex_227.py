from __future__ import annotations

from pathlib import Path
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
