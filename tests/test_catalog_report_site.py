from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import shutil
from types import SimpleNamespace

from rasai.audit_configuration_reuse import configuration_hash
from rasai.catalog_report_contract import (
    CATALOG_REPORT_CONTRACT_VERSION,
    CATALOG_REPORT_FILENAMES,
    CATALOG_REPORT_PAGES,
)
from rasai.catalog_report_site import materialize_catalog_report_site


AUDIT_ID = "AUD-CATALOG-REPORT"


def _workspace(tmp_path: Path):
    root = tmp_path / AUDIT_ID
    root.mkdir()
    non_catalog = root / "report"
    non_catalog.mkdir()
    (non_catalog / "index.html").write_text("NON-CATALOG-REPORT-BOUNDARY", encoding="utf-8")
    database = root / "audit.db"
    configuration = {
        "targets": ["https://example.test/"],
        "search_intelligence": {
            "enabled": True,
            "queries": ["seguro auto", "seguro residencial"],
            "depth": 20,
            "region": "Porto Alegre, RS, Brazil",
            "device": "mobile",
            "competitive": True,
        },
        "settings": {
            "environment": {
                # Defensive fixture: even malformed historical input containing secret
                # material must never be dumped by the new report projection.
                "RASAI_OPENAI_API_KEY": "DO-NOT-LEAK-THIS-SECRET",
                "RASAI_SERP_MAX_DEPTH": "20",
            }
        },
        "audit_catalog": {
            "version": "1",
            "selected": ["CAT-01", "CAT-04", "CAT-05", "CAT-06"],
            "ai_enabled": False,
            "items": [
                {
                    "id": "CAT-01",
                    "selected": True,
                    "status": "APTO",
                    "detail": "baseline técnico",
                    "ai_mode": "OPTIONAL",
                    "capability_ids": ["domain-discovery"],
                },
                {
                    "id": "CAT-04",
                    "selected": True,
                    "status": "APTO",
                    "detail": "web performance apto",
                    "ai_mode": "OPTIONAL",
                    "capability_ids": ["web-performance"],
                },
                {
                    "id": "CAT-05",
                    "selected": True,
                    "status": "APTO",
                    "detail": "SERP solicitada",
                    "ai_mode": "OPTIONAL",
                    "capability_ids": ["search-intelligence", "google-search-console"],
                },
                {
                    "id": "CAT-06",
                    "selected": True,
                    "status": "APTO",
                    "detail": "Apdex solicitado",
                    "ai_mode": "NONE",
                    "capability_ids": ["apdex-navigation"],
                },
            ],
        },
    }
    digest = configuration_hash(configuration)
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(
                audit_id TEXT PRIMARY KEY, project_name TEXT, status TEXT,
                completion_status TEXT, created_at TEXT, started_at TEXT, completed_at TEXT
            );
            CREATE TABLE audit_execution_configurations(
                audit_id TEXT PRIMARY KEY, configuration_json TEXT, configuration_hash TEXT
            );
            CREATE TABLE scores(
                audit_id TEXT, device TEXT, dimension TEXT, value REAL, coverage REAL,
                confidence TEXT, consolidation_status TEXT, scoring_version TEXT, limitations TEXT
            );
            CREATE TABLE web_performance_observations(
                audit_id TEXT, performance_score REAL, accessibility_score REAL,
                lcp_ms REAL, inp_ms REAL, cls REAL, ttfb_ms REAL
            );
            CREATE TABLE serp_observations(
                observation_id TEXT PRIMARY KEY, audit_id TEXT, query TEXT
            );
            CREATE TABLE serp_results(
                observation_id TEXT, position INTEGER, url TEXT
            );
            CREATE TABLE synthetic_apdex_summaries(
                audit_id TEXT, apdex REAL, threshold_seconds REAL,
                satisfied_count INTEGER, tolerating_count INTEGER,
                frustrated_count INTEGER, sample_count INTEGER
            );
            CREATE TABLE audit_fulfillment_work_items(
                audit_id TEXT, component TEXT, scope_key TEXT, status TEXT,
                attempt_count INTEGER, effective_result_ref TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO audits VALUES (?,?,?,?,?,?,?)",
            (AUDIT_ID, "Projeto catálogo", "SUCCESS", "COMPLETE", "2026-09-15T20:00:00Z", "2026-09-15T20:01:00Z", "2026-09-15T20:03:00Z"),
        )
        connection.execute(
            "INSERT INTO audit_execution_configurations VALUES (?,?,?)",
            (AUDIT_ID, json.dumps(configuration, ensure_ascii=False), digest),
        )
        connection.executemany(
            "INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (AUDIT_ID, "MOBILE", "OVERALL_READINESS", 74.2, 0.92, "HIGH", "CONSOLIDATED", "SARI-TEST-1", "[]"),
                (AUDIT_ID, "MOBILE", "DISCOVERY_ACCESS", 82.0, 1.0, "HIGH", "CONSOLIDATED", "SARI-TEST-1", "[]"),
                (AUDIT_ID, "MOBILE", "STRUCTURED_DATA", 68.0, 0.8, "MEDIUM", "CONSOLIDATED", "SARI-TEST-1", "[]"),
            ],
        )
        connection.execute(
            "INSERT INTO web_performance_observations VALUES (?,?,?,?,?,?,?)",
            (AUDIT_ID, 0.68, 0.92, 3100, 184, 0.08, 820),
        )
        connection.executemany(
            "INSERT INTO serp_observations VALUES (?,?,?)",
            [("SERP-1", AUDIT_ID, "seguro auto"), ("SERP-2", AUDIT_ID, "seguro residencial")],
        )
        connection.executemany(
            "INSERT INTO serp_results VALUES (?,?,?)",
            [("SERP-1", 8, "https://example.test/a"), ("SERP-1", 12, "https://example.test/b"), ("SERP-2", 5, "https://example.test/c")],
        )
        connection.execute(
            "INSERT INTO synthetic_apdex_summaries VALUES (?,?,?,?,?,?,?)",
            (AUDIT_ID, 0.78, 3.0, 36, 6, 8, 50),
        )
        connection.executemany(
            "INSERT INTO audit_fulfillment_work_items VALUES (?,?,?,?,?,?)",
            [
                (AUDIT_ID, "WEB_PERFORMANCE", "mobile", "SUCCESS", 1, "web-performance"),
                (AUDIT_ID, "SEARCH_INTELLIGENCE", "mobile", "SUCCESS", 1, "search-intelligence"),
                (AUDIT_ID, "SYNTHETIC_APDEX", "mobile", "SUCCESS", 1, "synthetic-apdex"),
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return SimpleNamespace(root=root, database=database), non_catalog


def test_catalog_report_is_isolated_from_non_catalog_tree(tmp_path: Path) -> None:
    workspace, non_catalog = _workspace(tmp_path)
    index = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace)

    assert index == workspace.root / "report-catalog" / "index.html"
    assert (non_catalog / "index.html").read_text(encoding="utf-8") == "NON-CATALOG-REPORT-BOUNDARY"
    assert set(path.name for path in index.parent.glob("*.html")) == set(CATALOG_REPORT_FILENAMES)
    assert (index.parent / "manifest.json").is_file()
    assert (index.parent / "css" / "site.css").is_file()


def test_catalog_report_materializes_without_non_catalog_report_tree(tmp_path: Path) -> None:
    workspace, non_catalog = _workspace(tmp_path)
    shutil.rmtree(non_catalog)

    index = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace)

    assert index == workspace.root / "report-catalog" / "index.html"
    assert index.is_file()
    assert not (workspace.root / "report").exists()
    assert not (workspace.root / "report.html").exists()
    assert not (workspace.root / "remediation.html").exists()
    assert set(path.name for path in index.parent.glob("*.html")) == set(CATALOG_REPORT_FILENAMES)


def test_every_new_page_uses_the_same_menu_and_one_active_item(tmp_path: Path) -> None:
    workspace, _non_catalog = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent

    expected_links = tuple(page.filename for page in CATALOG_REPORT_PAGES)
    for page in CATALOG_REPORT_PAGES:
        html = (report / page.filename).read_text(encoding="utf-8")
        assert f"data-shared-report-menu='{CATALOG_REPORT_CONTRACT_VERSION}'" in html
        assert html.count("aria-current='page'") == 1
        positions = [html.index(f"href='{filename}'") for filename in expected_links]
        assert positions == sorted(positions)


def test_sari_and_metrics_use_persisted_values_without_recalculation(tmp_path: Path) -> None:
    workspace, _non_catalog = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent

    sari = (report / "sari.html").read_text(encoding="utf-8")
    metrics = (report / "metrics.html").read_text(encoding="utf-8")
    overview = (report / "index.html").read_text(encoding="utf-8")

    assert "74.2" in sari
    assert "SARI-TEST-1" in sari
    assert "O HTML não recalcula o índice" in sari
    assert "Acesso e descoberta" in sari
    assert "Lighthouse · Desempenho" in metrics
    assert "LCP" in metrics
    assert "Apdex" in metrics
    assert "Índices e métricas evidentes" in overview


def test_catalog_contexts_show_execution_scope_and_unselected_state(tmp_path: Path) -> None:
    workspace, _non_catalog = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent

    search = (report / "cat-05.html").read_text(encoding="utf-8")
    remediation = (report / "cat-09.html").read_text(encoding="utf-8")

    assert "seguro auto" in search
    assert "Porto Alegre, RS, Brazil" in search
    assert "Top 20" in search
    assert "Faixa de posições observada" in search
    assert "NÃO SOLICITADO" in remediation


def test_catalog_report_never_dumps_secret_configuration_values(tmp_path: Path) -> None:
    workspace, _non_catalog = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent

    combined = "\n".join(path.read_text(encoding="utf-8") for path in report.glob("*.html"))
    assert "DO-NOT-LEAK-THIS-SECRET" not in combined
    assert "RASAI_OPENAI_API_KEY" not in combined

def test_structural_assurance_is_only_in_overview_not_repeated_in_catalog_pages(tmp_path: Path) -> None:
    workspace, _non_catalog = _workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent

    overview = (report / "index.html").read_text(encoding="utf-8")
    assert overview.count("Matriz de encerramento estrutural") == 1
    assert "Como ler os eixos" in overview

    for catalog_id in range(1, 11):
        html = (report / f"cat-{catalog_id:02d}.html").read_text(encoding="utf-8")
        assert "Confiabilidade e governança estrutural" not in html
