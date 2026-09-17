from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from rasai.catalog_report_adherence import install_catalog_report_adherence
from rasai.catalog_report_final_refinements import (
    _ai_totals,
    _apdex_samples_html,
    _attempt_input_detail,
    _capture_context_body,
    _discovery_title,
    _improvement_html,
    _jsonld_title,
    _web_metric_rows,
)
from rasai.catalog_report_label_refinements import install_catalog_human_labels
from rasai.catalog_report_site import (
    _sha256_file,
    _source_fingerprint,
    catalog_report_is_fresh,
    materialize_catalog_report_site,
)


def test_lighthouse_one_is_one_out_of_100_not_100(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    con = sqlite3.connect(database)
    try:
        con.execute(
            "CREATE TABLE web_performance_observations("
            "audit_id TEXT, performance_score REAL, accessibility_score REAL)"
        )
        con.execute(
            "INSERT INTO web_performance_observations VALUES (?,?,?)",
            ("AUD-1", 1.0, 78.0),
        )
        con.commit()
    finally:
        con.close()

    install_catalog_report_adherence()
    rows = _web_metric_rows(database, "AUD-1")
    values = {str(row[0]): str(row[1]) for row in rows}
    assert values["Lighthouse · Desempenho"] == "1 / 100"
    assert values["Lighthouse · Acessibilidade"] == "78 / 100"


def test_ai_totals_use_one_canonical_aggregation_without_reasoning_double_count() -> None:
    attempts = [
        {"status": "SUCCESS", "input_tokens": 11493, "output_tokens": 3974, "reasoning_tokens": 0, "total_tokens": 15467, "estimated_cost": "0.00706740"},
        {"status": "SUCCESS", "input_tokens": 2256, "output_tokens": 701, "reasoning_tokens": 0, "total_tokens": 2957, "estimated_cost": "0.00129240"},
        {"status": "SUCCESS", "input_tokens": 4225, "output_tokens": 1370, "reasoning_tokens": 0, "total_tokens": 5595, "estimated_cost": "0.00248900"},
        {"status": "CONTRACT_ERROR", "input_tokens": 25553, "output_tokens": 5180, "reasoning_tokens": 516, "total_tokens": 30733, "estimated_cost": "0.01132660"},
        {"status": "SUCCESS", "input_tokens": 27976, "output_tokens": 17165, "reasoning_tokens": 5565, "total_tokens": 45141, "estimated_cost": "0.05245086"},
    ]
    totals = _ai_totals(attempts)
    assert totals["attempts"] == 5
    assert totals["success"] == 4
    assert totals["input"] == 71503
    assert totals["output"] == 28390
    assert totals["reasoning"] == 6081
    assert totals["total"] == 99893
    assert totals["cost"] == Decimal("0.07462626")


def test_ai_usage_extract_explains_real_input_counts() -> None:
    detail = _attempt_input_detail(
        {
            "contract": "M18-SEMANTIC-22-v1",
            "request_message_summary": "semantic_contract=M18-SEMANTIC-22-v1;rules=22;evidence=8;snapshot=SNP-1",
        }
    )
    assert "22 regras/critérios" in detail
    assert "8 evidências" in detail
    assert "captura SNP-1" in detail


def test_absent_discovery_files_are_opportunities_not_errors() -> None:
    robots = _discovery_title({"diagnostic_code": "M24-ROBOTS-ABSENT"})
    sitemap = _discovery_title({"diagnostic_code": "M24-SITEMAP-ABSENT"})
    llms = _discovery_title({"diagnostic_code": "M24-LLMS-ABSENT"})
    assert robots == ("Considerar publicar robots.txt explícito", "Oportunidade")
    assert sitemap == ("Avaliar publicação e localização do sitemap", "Oportunidade")
    assert llms == ("Avaliar llms.txt apenas como recurso opcional", "Oportunidade")


def test_missing_jsonld_is_not_called_syntax_correction() -> None:
    assert _jsonld_title({"existing_types": "[]"}) == "Considerar implementar dados estruturados aplicáveis"
    assert _jsonld_title({"existing_types": '["Organization"]'}) == "Aprimorar dados estruturados existentes"


def test_portuguese_cost_classification_is_humanized() -> None:
    install_catalog_human_labels()
    from rasai import catalog_report_integrations as integrations

    assert integrations._level_label("CRÍTICO") == "Crítico"
    assert integrations._level_label("MODERADA") == "Moderada"


def test_catalog_freshness_fails_after_source_database_changes(tmp_path: Path) -> None:
    root = tmp_path / "AUD"
    root.mkdir()
    database = root / "audit.db"
    con = sqlite3.connect(database)
    try:
        con.execute("CREATE TABLE marker(value TEXT)")
        con.execute("INSERT INTO marker VALUES ('source-v1')")
        con.commit()
    finally:
        con.close()

    report = root / "report-catalog"
    integrity = report / "integrity"
    integrity.mkdir(parents=True)
    (report / "index.html").write_text("OK", encoding="utf-8")
    snapshot = integrity / "audit-snapshot.db"
    snapshot.write_bytes(database.read_bytes())
    fingerprint = _source_fingerprint(database)
    packaged_files = [
        {"path": "index.html", "sha256": _sha256_file(report / "index.html"), "size_bytes": (report / "index.html").stat().st_size},
        {"path": "integrity/audit-snapshot.db", "sha256": _sha256_file(snapshot), "size_bytes": snapshot.stat().st_size},
    ]
    (report / "manifest.json").write_text(
        json.dumps(
            {
                "audit_id": "AUD",
                "freshness": "FINAL",
                "source_fingerprint": fingerprint,
                "audit_snapshot": {
                    "path": "integrity/audit-snapshot.db",
                    "sha256": _sha256_file(snapshot),
                },
                "packaged_files": packaged_files,
            }
        ),
        encoding="utf-8",
    )
    workspace = SimpleNamespace(root=root, database=database)
    assert catalog_report_is_fresh(audit_id="AUD", workspace=workspace) is True
    con = sqlite3.connect(database)
    try:
        con.execute("INSERT INTO marker VALUES ('source-v2')")
        con.commit()
    finally:
        con.close()
    assert catalog_report_is_fresh(audit_id="AUD", workspace=workspace) is False


def test_failed_materialization_never_leaves_old_catalog_public(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "AUD"
    root.mkdir()
    database = root / "audit.db"
    con = sqlite3.connect(database)
    try:
        con.execute("CREATE TABLE audits(audit_id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO audits VALUES ('AUD')")
        con.commit()
    finally:
        con.close()
    old = root / "report-catalog"
    old.mkdir()
    (old / "index.html").write_text("STALE", encoding="utf-8")

    from rasai import catalog_report_site as site

    def fail_load(*args, **kwargs):
        raise RuntimeError("synthetic renderer failure")

    monkeypatch.setattr(site, "_load_data", fail_load)
    workspace = SimpleNamespace(root=root, database=database)
    with pytest.raises(RuntimeError, match="synthetic renderer failure"):
        materialize_catalog_report_site(audit_id="AUD", workspace=workspace)
    assert not (root / "report-catalog").exists()


def test_cat07_table_pages_sorts_and_explains_error_forced_frustration(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    con = sqlite3.connect(database)
    try:
        con.executescript(
            """
            CREATE TABLE synthetic_ux_apdex_runs(
                audit_id TEXT, status TEXT, errors_affect_apdex INTEGER, error_scope TEXT
            );
            CREATE TABLE synthetic_ux_apdex_summaries(
                audit_id TEXT, device TEXT, valid_samples INTEGER,
                error_forced_frustrated_count INTEGER
            );
            CREATE TABLE synthetic_ux_apdex_samples(
                audit_id TEXT, sample_id TEXT, run_index INTEGER, captured_at TEXT,
                device TEXT, classification TEXT, status TEXT, url TEXT, final_url TEXT,
                kpm_value_ms REAL, user_action_duration_ms REAL, navigation_duration_ms REAL,
                lcp_ms REAL, cls REAL, xhr_fetch_count INTEGER, dynamic_resource_count INTEGER,
                javascript_error_count INTEGER, console_error_count INTEGER,
                request_failed_count INTEGER, first_party_request_failed_count INTEGER,
                http_error_count INTEGER, network_settled INTEGER,
                error_forced_frustrated INTEGER, error_message TEXT, error_code TEXT
            );
            """
        )
        con.execute("INSERT INTO synthetic_ux_apdex_runs VALUES (?,?,?,?)", ("AUD", "SUCCESS", 1, "all"))
        con.execute("INSERT INTO synthetic_ux_apdex_summaries VALUES (?,?,?,?)", ("AUD", "POPULATION", 11, 11))
        for index in range(1, 12):
            con.execute(
                "INSERT INTO synthetic_ux_apdex_samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "AUD", f"S-{index}", index, f"2026-09-16T11:57:{index:02d}+00:00",
                    "mobile", "FRUSTRATED", "SUCCESS", "https://example.test/", "https://example.test/",
                    1000 + index, 1000 + index, 900 + index, 800 + index, 0.01,
                    2, 3, 0, 0, index, 0, 0, 1, 1, None, None,
                ),
            )
        con.commit()
    finally:
        con.close()

    html = _apdex_samples_html(database, SimpleNamespace(audit_id="AUD"), experience=True)
    assert "data-page-size='10'" in html
    assert "data-sortable='true'" in html
    assert "LCP" in html
    assert "Falhas de requisição" in html
    assert "11 de 11 amostra(s) válida(s) foram forçadas" in html
    assert "momento persistido da captura da amostra" in html


def test_cat08_explains_findings_without_individual_remediation(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    con = sqlite3.connect(database)
    try:
        con.executescript(
            """
            CREATE TABLE improvement_intelligence_runs(
                audit_id TEXT, status TEXT, analysis_language TEXT, max_recommendations INTEGER
            );
            CREATE TABLE improvement_intelligence_findings(
                audit_id TEXT, finding_id TEXT, title TEXT, observation TEXT,
                domain TEXT, severity TEXT, source TEXT, selector TEXT,
                original_html TEXT, evidence_ids_json TEXT
            );
            CREATE TABLE improvement_intelligence_recommendations(
                audit_id TEXT, finding_id TEXT, title TEXT, recommendation TEXT,
                domain TEXT, priority TEXT
            );
            """
        )
        con.execute("INSERT INTO improvement_intelligence_runs VALUES (?,?,?,?)", ("AUD", "COMPLETE", "pt-BR", 1))
        con.execute("INSERT INTO improvement_intelligence_findings VALUES (?,?,?,?,?,?,?,?,?,?)", ("AUD", "F-1", "Problema A", "A", "ACCESSIBILITY", "HIGH", "LIGHTHOUSE", "#a", "<div>", "[]"))
        con.execute("INSERT INTO improvement_intelligence_findings VALUES (?,?,?,?,?,?,?,?,?,?)", ("AUD", "F-2", "Problema B", "B", "PERFORMANCE", "HIGH", "LIGHTHOUSE", None, None, "[]"))
        con.execute("INSERT INTO improvement_intelligence_recommendations VALUES (?,?,?,?,?,?)", ("AUD", "F-1", "Corrigir A", "Aplicar A", "ACCESSIBILITY", "HIGH"))
        con.commit()
    finally:
        con.close()

    html = _improvement_html(database, SimpleNamespace(audit_id="AUD"))
    assert "Problemas correlacionados" in html
    assert "Achados sem remediação individual" in html
    assert "foi configurada para no máximo 1 recomendações" in html
    assert "Este finding não possui remediação individual" in html


def test_capture_context_has_visible_preview_and_atomic_screenshot_modal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "audit.db"
    database.write_bytes(b"")
    visual = tmp_path / "artifacts" / "visual" / "shot.png"
    visual.parent.mkdir(parents=True)
    visual.write_bytes(b"png")

    from rasai import catalog_report_governance as governance

    snapshot = {
        "page_id": "P-1", "snapshot_id": "S-1", "device": "mobile",
        "requested_url": "https://example.test/", "final_url": "https://example.test/",
        "captured_at": "2026-09-16T11:57:02+00:00", "http_status": 200,
        "browser_metadata": json.dumps({
            "visual_artifact_ref": "artifacts/visual/shot.png",
            "visual_snapshot": {"state": "CAPTURED", "viewport_width": 412, "viewport_height": 915},
            "profile": {"viewport": {"width": 412, "height": 915}},
        }),
    }
    monkeypatch.setattr(governance, "_capture_snapshots", lambda *args, **kwargs: [snapshot])
    monkeypatch.setattr(governance, "_runtime_items", lambda *args, **kwargs: [])

    data = SimpleNamespace(
        audit_id="AUD", targets=("https://example.test/",), audit={"project_name": "Projeto"},
        fulfillment={"processing_status": "COMPLETE"}, selected={"CAT-01"},
    )
    html = _capture_context_body(database, data)
    assert "Prévia visual" in html
    assert "<img class='capture-preview'" in html
    assert "data-modal-open='capture-image-1'" in html
    assert "<dialog id='capture-image-1'" in html
    assert "viewport 412 × 915" in html
