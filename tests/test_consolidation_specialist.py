from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from urllib.error import HTTPError
import pytest
from types import SimpleNamespace
from unittest.mock import patch

from rasai.ai_cost_policy import CandidateCostEstimate
from rasai.audit_fulfillment import (
    REPLAY_SAFE,
    SUCCESS,
    initialize_contract,
    register_work_item,
    set_work_item_status,
)
from rasai.consolidation.catalog_longitudinal import build_catalog_snapshot
from rasai.consolidation.cons5 import request_fingerprint
from rasai.consolidation.console import _print_preview
from rasai.consolidation.execution_log import ConsolidationExecutionError
from rasai.consolidation.presentation import finalize_reader_experience
from rasai.consolidation.index import ConsolidationIndex
from rasai.consolidation.service import generate, normalize_filter
from rasai.consolidation.specialist import (
    AI_MAX_INPUT_HINT_TOKENS,
    SpecialistPreview,
    SpecialistRun,
    _ai_packet_projection,
    _ai_technical_finding,
    _forecast,
    _longitudinal_packet,
    _longitudinal_schema,
    _token_hint,
    _validate_canonical_audit_references,
    _validate_configuration_comparability_language,
    build_evolution,
    build_longitudinal,
    prepare_longitudinal_specialist,
    preview_longitudinal_specialist,
    run_longitudinal_ai,
)
from rasai.monitoring.compare import compare_audits as compare_audits_actual
from rasai.monitoring.reader import read_audit_snapshot
from rasai.m18_ai import ProviderDiagnostic, ProviderErrorClass



def _complete_longitudinal_ai() -> SpecialistRun:
    return SpecialistRun(
        requested=True,
        status="COMPLETE",
        summary="Análise longitudinal de teste.",
        topic_analyses=(),
        attempts=(),
        interval_analyses=(),
        tradeoffs=(),
        strategy={"preservar": (), "corrigir": (), "otimizar": (), "conciliar": (), "investigar": ()},
        profile_id="EVOLUTION",
        profile_version="2.0",
    )


def _preview_ok() -> SpecialistPreview:
    return SpecialistPreview(
        available=True,
        reason=None,
        baseline_audit_id="AUD-BASE",
        current_audit_id="AUD-CURRENT",
        comparison_mode="LONGITUDINAL",
        candidates=(),
        selected=None,
        forecast={"currency": "USD", "expected_cost": 0.0},
    )

def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mark_fulfillment_complete(workspace: Path, audit_id: str) -> None:
    initialize_contract(workspace, audit_id, {"source": "consolidation-specialist-fixture"})
    register_work_item(
        workspace,
        audit_id=audit_id,
        component="CORE_AUDIT",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS,
        retryable=False,
    )
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="CORE_AUDIT",
        status=SUCCESS,
        result_ref=f"audit:{audit_id}",
        retryable=False,
    )


def _workspace(root: Path, audit_id: str, *, when: str, rule_result: str, score: float) -> Path:
    workspace = root / audit_id
    workspace.mkdir(parents=True)
    database = workspace / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits (
                audit_id TEXT PRIMARY KEY, project_name TEXT, created_at TEXT, started_at TEXT,
                completed_at TEXT, status TEXT, completion_status TEXT, auditor_version TEXT, ruleset_version TEXT
            );
            CREATE TABLE audit_targets (target_id TEXT PRIMARY KEY,audit_id TEXT,normalized_origin TEXT,target_type TEXT);
            CREATE TABLE pages (page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            CREATE TABLE page_snapshots (
                snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT,captured_at TEXT,http_status INTEGER,
                final_url TEXT,canonical TEXT,meta_robots TEXT,title TEXT,browser_metadata TEXT
            );
            CREATE TABLE rule_executions (
                audit_id TEXT,rule_id TEXT,page_id TEXT,device TEXT,result TEXT,observed_value TEXT,error TEXT,executed_at TEXT
            );
            CREATE TABLE findings (
                audit_id TEXT,severity TEXT,category TEXT,rule_id TEXT,page_id TEXT,device TEXT,status TEXT,title TEXT,observed_value TEXT
            );
            CREATE TABLE scores (
                score_id TEXT PRIMARY KEY,audit_id TEXT,dimension TEXT,device TEXT,value REAL,coverage REAL,
                confidence TEXT,consolidation_status TEXT,scoring_version TEXT,calculated_at TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO audits VALUES (?,?,?,?,?,?,?,?,?)",
            (audit_id, "Projeto", when, when, when, "COMPLETED", "COMPLETE", "1.0", "RULESET-1"),
        )
        connection.execute("INSERT INTO audit_targets VALUES (?,?,?,?)", (f"T-{audit_id}", audit_id, "https://example.test", "DOMAIN"))
        connection.execute("INSERT INTO pages VALUES (?,?,?)", (f"P-{audit_id}", audit_id, "https://example.test/a"))
        connection.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f"S-{audit_id}", f"P-{audit_id}", "MOBILE", when, 200, "https://example.test/a", "https://example.test/a", "index,follow", "Produto A", "{}"),
        )
        connection.execute(
            "INSERT INTO rule_executions VALUES (?,?,?,?,?,?,?,?)",
            (audit_id, "BR-GEO-011", f"P-{audit_id}", "MOBILE", rule_result, "{}", None, when),
        )
        connection.execute(
            "INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?)",
            (audit_id, "HIGH", "INDEXABILITY", "BR-GEO-011", f"P-{audit_id}", "MOBILE", "OPEN", "Indexabilidade", "{}"),
        )
        connection.execute(
            "INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f"SC-{audit_id}", audit_id, "INDEXABILITY", "MOBILE", score, 1.0, "HIGH", "CONSOLIDATED", "SCORE-GEO-004", when),
        )
        connection.commit()
    finally:
        connection.close()
    _mark_fulfillment_complete(workspace, audit_id)
    return workspace


def test_consolidated_report_uses_full_longitudinal_evolution_read_only() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = _workspace(root, "AUD-BASE", when="2026-08-01T10:00:00Z", rule_result="FAIL", score=70)
        current = _workspace(root, "AUD-CURRENT", when="2026-09-01T10:00:00Z", rule_result="PASS", score=82)
        before = {_digest(baseline / "audit.db"), _digest(current / "audit.db")}
        filters = normalize_filter(
            domains=("example.test",),
            devices=("MOBILE",),
            urls=("https://example.test/a",),
            specialist_ai=True,
            ai_provider="openai",
        )
        ConsolidationIndex(root).refresh()
        bundle = build_longitudinal(root, filters)
        assert bundle.audit_ids == ("AUD-BASE", "AUD-CURRENT")
        assert len(bundle.intervals) == 1
        assert any(item.get("rule_id") == "BR-GEO-011" for item in bundle.intervals[0].events)
        with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_longitudinal_ai()):
            result = generate(root, filters, refresh_index=False)
        after = {_digest(baseline / "audit.db"), _digest(current / "audit.db")}
        assert before == after
        html = result.report_path.read_text(encoding="utf-8")
        assert "Evolução longitudinal" in html
        assert "Trajetória completa da URL por dispositivo" in html
        assert "BR-GEO-011" in html
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert manifest["longitudinal_analysis"]["audit_count"] == 2
        assert manifest["longitudinal_analysis"]["device"] == "MOBILE"
        assert manifest["longitudinal_analysis"]["ai_required"] is True
        assert manifest["longitudinal_analysis"]["ai_status"] == "COMPLETE"
        assert manifest["longitudinal_analysis"]["evidence_file"] == "longitudinal-evidence.json"
        evidence = json.loads((result.report_dir / "longitudinal-evidence.json").read_text(encoding="utf-8"))
        assert (result.report_dir / "longitudinal-evidence.json").is_file()
        assert len(evidence["evidence"]["intervals"][0]["catalog_changes"]) == len(bundle.catalog_intervals[0].changes)
        assert "Cobertura dos catálogos" in html
        assert "longitudinal-evidence.json" in html


def test_consolidated_report_without_ai_materializes_deterministic_longitudinal_result() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-BASE", when="2026-08-01T10:00:00Z", rule_result="FAIL", score=70)
        _workspace(root, "AUD-CURRENT", when="2026-09-01T10:00:00Z", rule_result="PASS", score=82)
        filters = normalize_filter(
            devices=("MOBILE",),
            urls=("https://example.test/a",),
            audit_ids=("AUD-BASE", "AUD-CURRENT"),
            specialist_ai=False,
        )
        ConsolidationIndex(root).refresh()

        result = generate(root, filters, refresh_index=False)

        html = result.report_path.read_text(encoding="utf-8")
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert "Evolução longitudinal" in html
        assert "Trajetória completa da URL por dispositivo" in html
        assert manifest["generation_mode"] == "DETERMINISTIC"
        assert manifest["specialist_ai"]["requested"] is False
        assert manifest["specialist_ai"]["required"] is False
        assert manifest["specialist_ai"]["status"] == "NOT_REQUESTED"
        assert manifest["longitudinal_analysis"]["ai_required"] is False
        assert manifest["longitudinal_analysis"]["ai_status"] == "NOT_REQUESTED"
        assert manifest["consolidation_confidence"]["ai_independent"] is True
        assert (result.report_dir / "decision-context.json").is_file()
        assert (result.report_dir / "longitudinal-evidence.json").is_file()
        assert (result.report_dir / "rules-reference.html").is_file()
        assert "id='decision-overview'" in html
        assert "id='cons-governance'" in html
        assert "Revisão temporal" in html
        assert "rules-reference.html" in html
        assert "href='#longitudinal-ai'" not in html
        assert not (result.report_dir / "specialist-analysis.json").exists()
        assert not (result.report_dir / "ai-exchanges.json").exists()


def test_comparison_modes_select_expected_pair() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-001", when="2026-07-01T10:00:00Z", rule_result="FAIL", score=70)
        _workspace(root, "AUD-002", when="2026-08-01T10:00:00Z", rule_result="FAIL", score=75)
        _workspace(root, "AUD-003", when="2026-09-01T10:00:00Z", rule_result="PASS", score=85)
        index = ConsolidationIndex(root)
        index.refresh()
        first_last = build_evolution(root, normalize_filter(comparison_mode="FIRST_LAST"))
        assert first_last.comparison.baseline.audit_id == "AUD-001"
        assert first_last.comparison.current.audit_id == "AUD-003"
        latest = build_evolution(root, normalize_filter(comparison_mode="LATEST_PREVIOUS"))
        assert latest.comparison.baseline.audit_id == "AUD-002"
        assert latest.comparison.current.audit_id == "AUD-003"
        manual = build_evolution(root, normalize_filter(comparison_mode="MANUAL", baseline_audit_id="AUD-001", current_audit_id="AUD-002"))
        assert manual.comparison.baseline.audit_id == "AUD-001"
        assert manual.comparison.current.audit_id == "AUD-002"


def test_fix_verification_reuses_comparison_result_already_built() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-001", when="2026-08-01T10:00:00Z", rule_result="FAIL", score=70)
        _workspace(root, "AUD-002", when="2026-09-01T10:00:00Z", rule_result="PASS", score=82)
        ConsolidationIndex(root).refresh()
        filters = normalize_filter(
            urls=("https://example.test/a",),
            devices=("MOBILE",),
            comparison_mode="FIRST_LAST",
        )
        with patch(
            "rasai.quality.verification.compare_audits",
            side_effect=AssertionError("Verification não deve recalcular ComparisonResult"),
        ) as duplicate:
            evolution = build_evolution(root, filters)

        assert evolution.comparison.baseline.audit_id == "AUD-001"
        assert evolution.comparison.current.audit_id == "AUD-002"
        assert any(item["status"] == "FIXED" for item in evolution.fixes)
        duplicate.assert_not_called()


def test_five_audit_longitudinal_build_reads_monitoring_snapshot_once_per_audit() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for index in range(1, 6):
            _workspace(
                root,
                f"AUD-{index:03d}",
                when=f"2026-0{index + 3}-01T10:00:00Z",
                rule_result="PASS" if index == 5 else "FAIL",
                score=65 + index * 4,
            )
        ConsolidationIndex(root).refresh()
        filters = normalize_filter(
            urls=("https://example.test/a",),
            devices=("MOBILE",),
        )

        with patch(
            "rasai.consolidation.specialist.read_audit_snapshot",
            wraps=read_audit_snapshot,
        ) as reads, patch(
            "rasai.consolidation.specialist.compare_audits",
            wraps=compare_audits_actual,
        ) as comparisons, patch(
            "rasai.quality.verification.compare_audits",
            side_effect=AssertionError("Verification não deve recalcular comparação"),
        ) as verification_compare, patch(
            "rasai.consolidation.catalog_longitudinal.read_audit_snapshot",
            side_effect=AssertionError("catálogo deve reutilizar AuditSnapshot já carregado"),
        ) as catalog_reads:
            bundle = build_longitudinal(root, filters)

        assert bundle.audit_ids == tuple(f"AUD-{index:03d}" for index in range(1, 6))
        assert len(bundle.intervals) == 4
        assert reads.call_count == 5
        assert comparisons.call_count == 5  # quatro intervalos consecutivos + inicial -> final
        verification_compare.assert_not_called()
        catalog_reads.assert_not_called()


def test_catalog_source_records_share_one_connection_per_audit_snapshot() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(
            root,
            "AUD-001",
            when="2026-09-01T10:00:00Z",
            rule_result="PASS",
            score=82,
        )
        snapshot = read_audit_snapshot(workspace)
        connections: set[int] = set()
        audit_db_opens = {"count": 0}
        original_connect = sqlite3.connect

        from rasai.consolidation import catalog_longitudinal as catalog_module

        source_records = catalog_module._source_records

        def capture_connection(connection, *args, **kwargs):
            connections.add(id(connection))
            return source_records(connection, *args, **kwargs)

        def counted_connect(database, *args, **kwargs):
            if "audit.db" in str(database).casefold():
                audit_db_opens["count"] += 1
            return original_connect(database, *args, **kwargs)

        with patch("sqlite3.connect", side_effect=counted_connect), patch(
            "rasai.consolidation.catalog_longitudinal._source_records",
            side_effect=capture_connection,
        ) as calls:
            built = build_catalog_snapshot(
                workspace,
                url="https://example.test/a",
                device="MOBILE",
                audit_snapshot=snapshot,
            )

        assert built.audit_id == "AUD-001"
        assert calls.call_count > 1
        assert len(connections) == 1
        assert audit_db_opens["count"] == 1


def test_catalog_source_records_include_both_device_rows_for_mobile_scope() -> None:
    from rasai.consolidation import catalog_longitudinal as catalog_module

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(
            """CREATE TABLE recommendations(
                   audit_id TEXT,
                   recommendation_id TEXT,
                   device TEXT,
                   title TEXT
               )"""
        )
        connection.executemany(
            "INSERT INTO recommendations VALUES (?,?,?,?)",
            (
                ("AUD-001", "REC-MOBILE", "MOBILE", "Mobile"),
                ("AUD-001", "REC-BOTH", "BOTH", "Both"),
                ("AUD-001", "REC-DESKTOP", "DESKTOP", "Desktop"),
            ),
        )
        rows = catalog_module._source_records(
            connection,
            "AUD-001",
            "CAT-09",
            url="https://example.test/a",
            device="MOBILE",
        )
    finally:
        connection.close()

    recommendations = rows["recommendations"]
    assert {(item["device"], item["title"]) for item in recommendations} == {
        ("MOBILE", "Mobile"),
        ("BOTH", "Both"),
    }
    assert all("recommendation_id" not in item for item in recommendations)


def test_catalog_source_records_cat02_excludes_crux_attempt_from_pagespeed_source() -> None:
    from rasai.consolidation import catalog_longitudinal as catalog_module

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(
            """CREATE TABLE web_performance_attempts(
                   attempt_id TEXT,
                   audit_id TEXT,
                   page_id TEXT,
                   snapshot_id TEXT,
                   device TEXT,
                   url TEXT,
                   service TEXT,
                   status TEXT
               )"""
        )
        connection.executemany(
            "INSERT INTO web_performance_attempts VALUES (?,?,?,?,?,?,?,?)",
            (
                ("WPA-1", "AUD-001", "P-1", "S-1", "MOBILE", "https://example.test/a", "PAGESPEED_INSIGHTS", "ERROR"),
                ("WPA-2", "AUD-001", "P-1", "S-1", "MOBILE", "https://example.test/a", "CRUX_API", "SUCCESS"),
                ("WPA-3", "AUD-001", "P-1", "S-1", "MOBILE", "https://example.test/a", "PAGESPEED_INSIGHTS", "SUCCESS"),
            ),
        )
        rows = catalog_module._source_records(
            connection,
            "AUD-001",
            "CAT-02",
            url="https://example.test/a",
            device="MOBILE",
        )
    finally:
        connection.close()

    attempts = rows["web_performance_attempts"]
    assert len(attempts) == 2
    assert {item["service"] for item in attempts} == {"PAGESPEED_INSIGHTS"}


def test_catalog_row_fingerprint_ignores_audit_scoped_identifiers() -> None:
    from rasai.consolidation import catalog_longitudinal as catalog_module

    diagnostic_before = {
        "code": "M24-ROBOTS-ABSENT",
        "diagnostic_id": "M24D-00001-AUD-A",
        "evidence_ids": "[\"EV-GEO-A\"]",
        "observed_value": "{\"state\":\"ABSENT\"}",
        "title": "robots.txt não encontrado",
    }
    diagnostic_after = {
        **diagnostic_before,
        "diagnostic_id": "M24D-00001-AUD-B",
        "evidence_ids": "[\"EV-GEO-B\"]",
    }
    assert catalog_module._row_fingerprint(diagnostic_before) == catalog_module._row_fingerprint(diagnostic_after)

    provenance_before = {
        "source_audit_id": "AUD-A",
        "source_observation_id": "SERP-A",
        "temporal_mode": "LIVE_RECOLLECTION",
        "reuse_reason": None,
    }
    provenance_after = {
        **provenance_before,
        "source_audit_id": "AUD-B",
        "source_observation_id": "SERP-B",
    }
    assert catalog_module._row_fingerprint(provenance_before) == catalog_module._row_fingerprint(provenance_after)

    suggestion_before = {
        "suggestion_id": "JLD-A",
        "evidence_ids": "[\"EV-GEO-A\"]",
        "status": "MISSING_PROPOSED",
        "proposed_json": "{\"@type\":\"WebPage\"}",
    }
    suggestion_after = {
        **suggestion_before,
        "suggestion_id": "JLD-B",
        "evidence_ids": "[\"EV-GEO-B\"]",
    }
    assert catalog_module._row_fingerprint(suggestion_before) == catalog_module._row_fingerprint(suggestion_after)

    recommendation_before = {
        "recommendation_id": "REC-A",
        "remediation_group_id": "RMG-A",
        "finding_id": "FND-A",
        "title": "Corrigir declaração canonical",
        "description": "Definir uma única canonical válida.",
        "priority_score": 70.25,
    }
    recommendation_after = {
        **recommendation_before,
        "recommendation_id": "REC-B",
        "remediation_group_id": "RMG-B",
        "finding_id": "FND-B",
    }
    assert catalog_module._row_fingerprint(recommendation_before) == catalog_module._row_fingerprint(recommendation_after)

    summary_before = {
        "summary_id": "SCS-A",
        "criterion_id": "SC-X01",
        "evidence_ids_json": "[\"EV-A\"]",
        "result": "NOT_DETERMINABLE",
        "summary": "São necessárias ao menos duas páginas.",
    }
    summary_after = {
        **summary_before,
        "summary_id": "SCS-B",
        "evidence_ids_json": "[\"EV-B\"]",
    }
    assert catalog_module._row_fingerprint(summary_before) == catalog_module._row_fingerprint(summary_after)

    sample_before = {
        "sample_id": "UXA-A",
        "task_id": "SYNTHETIC_LOAD_ACTION",
        "profile_id": "PROFILE-MOBILE",
        "status": "FAILED",
        "error_type": "NETWORK",
    }
    sample_after = {**sample_before, "sample_id": "UXA-B"}
    assert catalog_module._row_fingerprint(sample_before) == catalog_module._row_fingerprint(sample_after)

    changed = {**diagnostic_after, "observed_value": "{\"state\":\"PRESENT\"}"}
    assert catalog_module._row_fingerprint(diagnostic_before) != catalog_module._row_fingerprint(changed)
    recommendation_changed = {**recommendation_after, "description": "Definir canonical e revisar conflito."}
    assert catalog_module._row_fingerprint(recommendation_before) != catalog_module._row_fingerprint(recommendation_changed)

    security_resource_before = {
        "resource_id": "PSR-A",
        "page_id": "PGE-A",
        "snapshot_id": "SNP-A",
        "resource_url": "https://cdn.example.test/app.js",
        "resource_kind": "SCRIPT",
        "party": "THIRD_PARTY",
        "evidence_ids_json": "[\"SNP-A\",\"EV-A\"]",
    }
    security_resource_after = {
        **security_resource_before,
        "resource_id": "PSR-B",
        "page_id": "PGE-B",
        "snapshot_id": "SNP-B",
        "evidence_ids_json": "[\"SNP-B\",\"EV-B\"]",
    }
    assert catalog_module._row_fingerprint(security_resource_before) == catalog_module._row_fingerprint(security_resource_after)

    governance_before = {
        "governance_id": "RGV-A",
        "source_id": "REC-A",
        "source_evidence_json": "[\"EV-A\"]",
        "decision": "REJECTED",
        "target_class": "INFORMATIONAL",
        "title": "Corrigir robots.txt não interpretável",
    }
    governance_after = {
        **governance_before,
        "governance_id": "RGV-B",
        "source_id": "REC-B",
        "source_evidence_json": "[\"EV-B\"]",
    }
    assert catalog_module._row_fingerprint(governance_before) == catalog_module._row_fingerprint(governance_after)

    group_before = {
        "group_id": "RMG-A",
        "affected_findings": "[\"FND-A\"]",
        "affected_pages": "[\"PGE-A\"]",
        "rule_id": "BR-GEO-017",
        "root_cause": "robots ausente",
        "priority_score": 77.75,
    }
    group_after = {
        **group_before,
        "group_id": "RMG-B",
        "affected_findings": "[\"FND-B\"]",
        "affected_pages": "[\"PGE-B\"]",
    }
    assert catalog_module._row_fingerprint(group_before) == catalog_module._row_fingerprint(group_after)

    collected_before = {
        "observation_id": "OBS-A",
        "collected_at": "2026-09-19T17:29:51+00:00",
        "result_count": 10,
        "state": "SUCCESS",
    }
    collected_after = {
        **collected_before,
        "observation_id": "OBS-B",
        "collected_at": "2026-09-19T22:29:43+00:00",
    }
    assert catalog_module._row_fingerprint(collected_before) == catalog_module._row_fingerprint(collected_after)
    collected_changed = {**collected_after, "result_count": 9}
    assert catalog_module._row_fingerprint(collected_before) != catalog_module._row_fingerprint(collected_changed)


def test_prepared_preview_and_generation_reuse_identical_longitudinal_universe() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-BASE", when="2026-08-01T10:00:00Z", rule_result="FAIL", score=70)
        _workspace(root, "AUD-CURRENT", when="2026-09-01T10:00:00Z", rule_result="PASS", score=82)
        ConsolidationIndex(root).refresh()
        filters = normalize_filter(
            urls=("https://example.test/a",),
            devices=("MOBILE",),
            specialist_ai=True,
            ai_provider="openai",
            ai_model="gpt-5.6-luna",
            ai_reasoning="LOW",
        )
        reference_bundle = build_longitudinal(root, filters)
        reference_packet, reference_ids = _longitudinal_packet(reference_bundle)
        prepared = prepare_longitudinal_specialist(root, filters)
        assert prepared.bundle == reference_bundle
        assert prepared.full_packet == reference_packet
        assert prepared.full_evidence_ids == reference_ids

        provider = SimpleNamespace(
            name="OPENAI",
            model="gpt-5.6-luna",
            reasoning_profile="LOW",
            requested_reasoning_effort="LOW",
        )
        with patch("rasai.consolidation.specialist._build_ai", return_value=provider):
            preview = preview_longitudinal_specialist(root, filters, prepared=prepared)

        assert preview.available is True
        assert preview.context_projection == prepared.context_projection

        with patch(
            "rasai.consolidation.service.prepare_longitudinal_specialist",
            side_effect=AssertionError("generate não deve reconstruir a preparação"),
        ) as rebuild, patch(
            "rasai.consolidation.service.preview_longitudinal_specialist",
            side_effect=AssertionError("generate deve usar a prévia já autorizada"),
        ) as second_preview, patch(
            "rasai.consolidation.service.run_longitudinal_ai",
            return_value=_complete_longitudinal_ai(),
        ), patch(
            "rasai.consolidation.specialist._longitudinal_packet",
            side_effect=AssertionError("materialização deve reutilizar o packet integral preparado"),
        ) as repacket:
            result = generate(
                root,
                filters,
                refresh_index=False,
                prepared=prepared,
                preview=preview,
            )

        rebuild.assert_not_called()
        second_preview.assert_not_called()
        repacket.assert_not_called()
        evidence = json.loads(
            (result.report_dir / "longitudinal-evidence.json").read_text(encoding="utf-8")
        )
        expected = json.loads(json.dumps(prepared.full_packet, ensure_ascii=False, default=str))
        assert evidence["evidence"] == expected


def test_authorized_preview_blocks_provider_chain_change_before_transport() -> None:
    calls = {"transport": 0}

    def transport(*args, **kwargs):
        calls["transport"] += 1
        raise AssertionError("provider não pode ser chamado após divergência da prévia")

    provider = SimpleNamespace(
        name="OPENAI",
        model="gpt-5.6-luna",
        reasoning_profile="LOW",
        requested_reasoning_effort="LOW",
        endpoint="https://example.invalid/ai",
        _headers=lambda: {},
        _transport=transport,
        policy=SimpleNamespace(rank=1, qualification="QUALIFIED", reliability_score=1.0),
    )

    class Selection:
        excluded_configurations = ()
        coordinator = None

        def ordered_candidates_for_need(self, request, *, scope):
            return (provider,)

    expected = SpecialistPreview(
        available=True,
        reason=None,
        baseline_audit_id="AUD-1",
        current_audit_id="AUD-2",
        comparison_mode="LONGITUDINAL",
        candidates=(),
        selected=None,
        forecast={},
    )
    bundle = SimpleNamespace(
        catalog_intervals=(SimpleNamespace(interval_id="INTERVALO-001"),),
        governance={},
        audit_ids=("AUD-BASE", "AUD-CURRENT"),
    )
    filters = normalize_filter(
        devices=("MOBILE",),
        urls=("https://example.test/a",),
        specialist_ai=True,
        ai_provider="auto",
    )

    with patch("rasai.consolidation.specialist._longitudinal_packet", return_value=({}, ("E1",))), \
         patch("rasai.consolidation.specialist._longitudinal_schema", return_value={}), \
         patch("rasai.consolidation.specialist._build_ai", return_value=Selection()):
        with pytest.raises(RuntimeError, match="mudou após a prévia autorizada"):
            run_longitudinal_ai(bundle, filters, expected_preview=expected)

    assert calls["transport"] == 0


def test_ai_choice_changes_request_identity_without_persisting_secrets() -> None:
    base = normalize_filter(domains=("example.test",), comparison_mode="FIRST_LAST")
    ai = normalize_filter(
        domains=("example.test",), comparison_mode="FIRST_LAST", specialist_ai=True,
        ai_provider="openai", ai_model="gpt-5.6-luna", ai_reasoning="LOW", ai_timeout_seconds=180,
    )
    assert request_fingerprint("source", base) != request_fingerprint("source", ai)
    canonical = ai.canonical()
    assert canonical["specialist_ai"] is True
    assert canonical["ai_provider"] == "openai"
    assert not any("key" in key.casefold() or "secret" in key.casefold() for key in canonical)


def test_cost_preview_uses_canonical_pricing_and_request_token_hints() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-BASE", when="2026-08-01T10:00:00Z", rule_result="FAIL", score=70)
        _workspace(root, "AUD-CURRENT", when="2026-09-01T10:00:00Z", rule_result="PASS", score=82)
        ConsolidationIndex(root).refresh()
        filters = normalize_filter(
            urls=("https://example.test/a",),
            devices=("MOBILE",),
            specialist_ai=True,
            ai_provider="openai",
            ai_model="gpt-5.6-luna",
            ai_reasoning="LOW",
        )
        provider = SimpleNamespace(name="OPENAI", model="gpt-5.6-luna", reasoning_profile="LOW", requested_reasoning_effort="LOW")
        with patch("rasai.consolidation.specialist._build_ai", return_value=provider):
            preview = preview_longitudinal_specialist(root, filters)
        assert preview.available is True
        assert preview.selected is not None
        assert preview.selected.provider == "OPENAI"
        assert preview.selected.estimated_input_tokens >= 2000
        assert preview.selected.estimated_output_tokens > 0
        assert preview.selected.estimated_cost is not None
        assert preview.selected.currency == "USD"


def test_console_preview_exposes_ai_context_projection(capsys) -> None:
    candidate = SimpleNamespace(
        provider="OPENAI",
        model="gpt-5.6-luna",
        reasoning_profile="LOW",
        estimated_input_tokens=42000,
        estimated_output_tokens=2000,
        estimated_cost=0.01,
        currency="USD",
        pricing_context="STANDARD",
        pricing_version="TEST",
    )
    preview = SpecialistPreview(
        available=True,
        reason=None,
        baseline_audit_id="AUD-1",
        current_audit_id="AUD-2",
        comparison_mode="LONGITUDINAL",
        candidates=(candidate,),
        selected=candidate,
        event_count=10,
        forecast={"currency": "USD", "expected_cost": 0.01, "max_rounds": 2},
        context_projection={
            "level": "COMPACT",
            "estimated_input_tokens": 42000,
            "max_input_hint_tokens": 80000,
        },
    )

    _print_preview(preview, "auto")
    output = capsys.readouterr().out

    assert "Contexto IA  : COMPACT | 42000 tokens estimados (limite 80000)" in output
    assert "Evidência    : integral local" in output


def test_longitudinal_schema_requires_every_topic_property_for_strict_providers() -> None:
    schema = _longitudinal_schema(("EV-1",), ("INTERVALO-001",))
    topic = schema["properties"]["topic_analyses"]["items"]
    assert set(topic["required"]) == set(topic["properties"])
    assert "cause_analysis" in topic["required"]


def test_ai_technical_finding_exposes_only_canonical_evidence_id() -> None:
    projected = _ai_technical_finding({
        "evidence_id": "I001-FINDING-0001",
        "finding_id": "FND-INTERNAL",
        "rule_id": "BR-GEO-013",
        "severity": "HIGH",
        "cause_summary": "Canonical inconsistente.",
    })
    assert projected["evidence_id"] == "I001-FINDING-0001"
    assert "finding_id" not in projected


def test_final_reader_experience_uses_current_counters_and_rules_navigation() -> None:
    html = """
    <html><body>
    <section class='rasai-analysis-status state-info' data-rasai-consolidated-experience='true'>
      <div class='rasai-analysis-status-main'><div><h2>Leitura histórica materializada</h2></div></div>
      <div class='rasai-status-meta'>
        <span class='rasai-state-chip state-good'>IA especialista concluída</span>
        <span class='rasai-state-chip state-neutral'>0 melhora(s) / resolução(ões) observada(s)</span>
        <span class='rasai-state-chip state-neutral'>0 regressão(ões) / novo(s) sinal(is)</span>
      </div>
    </section>
    <nav aria-label='Navegação do relatório'><a href='#cons-governance'>Governança</a></nav>
    <p><a class='cons-rule-ref' href='rules-reference.html#BR-GEO-013'>BR-GEO-013</a></p>
    <table><tr><td>Answerability</td><td>PASS</td><td>Mobile</td></tr></table>
    </body></html>
    """
    artifact = {
        "ai": {"requested": True, "status": "COMPLETE"},
        "rule_reference": [{"rule_id": "BR-GEO-013"}],
        "initial_to_final": {
            "changes": [
                {"status": "IMPROVED"},
                {"status": "RESOLVED"},
                {"status": "REGRESSED"},
                {"status": "CHANGED"},
                {"status": "DATA_UNAVAILABLE"},
            ]
        },
    }

    rendered = finalize_reader_experience(html, artifact)

    assert "2 melhoria(s) ou resolução(ões) entre marco inicial e final" in rendered
    assert "1 regressão(ões) ou novo(s) sinal(is) entre marco inicial e final" in rendered
    assert "2 alteração(ões) ou indisponibilidade(s) a investigar" in rendered
    assert "Capacidade de resposta" in rendered
    assert ">Aprovado<" in rendered
    assert ">Dispositivo móvel<" in rendered


def test_ai_context_projection_is_bounded_and_auditable() -> None:
    huge = "X" * 12000
    intervals = []
    for interval_no in range(1, 5):
        intervals.append({
            "interval_id": f"INTERVALO-{interval_no:03d}",
            "baseline": {"audit_id": f"AUD-{interval_no}", "event_time": "2026-09-18T00:00:00Z"},
            "current": {"audit_id": f"AUD-{interval_no + 1}", "event_time": "2026-09-19T00:00:00Z"},
            "comparable": True,
            "limitations": [],
            "changes": [
                {
                    "evidence_id": f"I{interval_no:03d}-EV-{index:04d}",
                    "status": "REGRESSED" if index % 3 == 0 else "CHANGED",
                    "severity": "HIGH",
                    "label": f"Indicador {index}",
                    "before": huge,
                    "after": huge,
                }
                for index in range(180)
            ],
            "fix_verification": [
                {
                    "evidence_id": f"I{interval_no:03d}-FIX-{index:04d}",
                    "status": "STILL_FAILING",
                    "rule_id": f"BR-GEO-{index % 70:03d}",
                    "before": huge,
                    "after": huge,
                }
                for index in range(90)
            ],
            "catalog_changes": [
                {
                    "evidence_id": f"I{interval_no:03d}-CAT-{index:04d}",
                    "catalog_id": f"CAT-{(index % 10) + 1:02d}",
                    "catalog_label": "Catálogo",
                    "status": "ALTERADO",
                    "label": f"Métrica {index}",
                    "before": huge,
                    "after": huge,
                    "evidence": {"added": [huge] * 8, "removed": [huge] * 8},
                }
                for index in range(260)
            ],
            "stable_within_expected": 400,
            "stable_requiring_attention": 20,
            "current_technical_findings": [
                {
                    "finding_id": f"F-{index}",
                    "rule_id": f"BR-GEO-{index:03d}",
                    "severity": "HIGH",
                    "evolution_status": "NEW",
                    "cause_summary": huge,
                    "exact_change": huge,
                    "affected_elements": [{"selector": "body", "outer_html": huge}],
                }
                for index in range(30)
            ],
        })

    packet = {
        "contract": "CONSOLIDATED-LONGITUDINAL-001",
        "catalog_contract": "CONSOLIDATED-CATALOG-LONGITUDINAL-001",
        "scope": {"url": "https://example.test/", "device": "MOBILE", "audit_ids": [f"AUD-{i}" for i in range(1, 6)]},
        "intervals": intervals,
        "initial_to_final": {
            "baseline_audit_id": "AUD-1",
            "current_audit_id": "AUD-5",
            "changes": intervals[0]["changes"] + intervals[-1]["changes"],
            "fix_verification": intervals[-1]["fix_verification"],
            "current_technical_findings": intervals[-1]["current_technical_findings"],
            "limitations": [],
        },
        "catalog_state_initial": [
            {"catalog_id": f"CAT-{i:02d}", "label": f"Catálogo {i}", "status": "COMPLETE", "metrics": [{"value": huge}] * 20}
            for i in range(1, 11)
        ],
        "catalog_state_final": [
            {"catalog_id": f"CAT-{i:02d}", "label": f"Catálogo {i}", "status": "COMPLETE", "metrics": [{"value": huge}] * 20}
            for i in range(1, 11)
        ],
        "rule_reference": [
            {
                "rule_id": f"BR-GEO-{index:03d}",
                "tooltip": huge,
                "remediation": {"description": huge, "example": huge, "validation": [huge] * 10},
            }
            for index in range(100)
        ],
        "governance": {"source": "persistido", "human_review_required": True},
    }

    projected, allowed, meta = _ai_packet_projection(packet)
    hint = _token_hint(projected)

    assert hint.estimated_input_tokens <= AI_MAX_INPUT_HINT_TOKENS
    assert meta["estimated_input_tokens"] <= AI_MAX_INPUT_HINT_TOKENS
    assert meta["projection_is_lossy_for_ai"] is True
    assert meta["source_is_complete_locally"] is True
    assert meta["full_evidence_artifact"] == "longitudinal-evidence.json"
    assert len(meta["intervals"]) == 4
    assert meta["intervals"][0]["catalog_changes_total"] == 260
    assert meta["intervals"][0]["catalog_changes_sent"] < 260
    assert set(meta["catalogs_initial"]) == {f"CAT-{i:02d}" for i in range(1, 11)}
    assert allowed


def test_longitudinal_ai_retries_transient_failure_once() -> None:
    calls = {"count": 0}

    def transport(url, headers, body, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise HTTPError(url, 429, "too many requests", {}, None)
        return {"ok": True}

    provider = SimpleNamespace(
        name="OPENAI",
        model="gpt-5.6-luna",
        reasoning_profile="LOW",
        requested_reasoning_effort="LOW",
        endpoint="https://example.invalid/ai",
        _headers=lambda: {},
        _transport=transport,
        policy=SimpleNamespace(rank=1, qualification="QUALIFIED", reliability_score=1.0),
    )

    class Coordinator:
        def record_attempt(self, attempt, *, scope):
            return None

    class Selection:
        excluded_configurations = ()
        coordinator = Coordinator()

        def ordered_candidates_for_need(self, request, *, scope):
            return (provider,)

    bundle = SimpleNamespace(
        catalog_intervals=(SimpleNamespace(interval_id="INTERVALO-001"),),
        governance={},
        audit_ids=("AUD-BASE", "AUD-CURRENT"),
    )
    validated = (
        "Resumo",
        ({"interval_id": "INTERVALO-001"},),
        (),
        (),
        {"preservar": (), "corrigir": (), "otimizar": (), "conciliar": (), "investigar": ()},
    )
    with patch("rasai.consolidation.specialist._longitudinal_packet", return_value=({}, ("E1",))), \
         patch("rasai.consolidation.specialist._longitudinal_schema", return_value={}), \
         patch("rasai.consolidation.specialist._build_ai", return_value=Selection()), \
         patch("rasai.consolidation.specialist._provider_payload", return_value={"request": True}), \
         patch("rasai.consolidation.specialist._provider_native_error", return_value=None), \
         patch("rasai.consolidation.specialist._provider_usage", return_value=SimpleNamespace(input_tokens=10, cached_input_tokens=0, output_tokens=5, reasoning_tokens=0)), \
         patch("rasai.consolidation.specialist._provider_extract", return_value={}), \
         patch("rasai.consolidation.specialist._validated_longitudinal_payload", return_value=validated), \
         patch("rasai.consolidation.specialist._extension_diagnostic_from_http", return_value=ProviderDiagnostic(ProviderErrorClass.RATE_LIMIT_ERROR, http_status=429, retry_after_seconds=0)), \
         patch("rasai.consolidation.specialist.time.sleep") as sleep:
        run = run_longitudinal_ai(
            bundle,
            normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.test/a",),
                specialist_ai=True,
                ai_provider="auto",
            ),
        )

    assert run.status == "COMPLETE"
    assert run.rounds == 2
    assert calls["count"] == 2
    assert len(run.attempts) == 2
    assert run.attempts[0].retry_eligible is True
    assert run.attempts[0].decision == "RETRY_ROUND"
    assert run.attempts[1].status == "SUCCESS"
    sleep.assert_called_once_with(5.0)


def test_longitudinal_ai_does_not_retry_terminal_error() -> None:
    calls = {"count": 0}

    def transport(url, headers, body, timeout):
        calls["count"] += 1
        raise HTTPError(url, 401, "unauthorized", {}, None)

    provider = SimpleNamespace(
        name="OPENAI",
        model="gpt-5.6-luna",
        reasoning_profile="LOW",
        requested_reasoning_effort="LOW",
        endpoint="https://example.invalid/ai",
        _headers=lambda: {},
        _transport=transport,
        policy=SimpleNamespace(rank=1, qualification="QUALIFIED", reliability_score=1.0),
    )

    class Coordinator:
        def record_attempt(self, attempt, *, scope):
            return None

    class Selection:
        excluded_configurations = ()
        coordinator = Coordinator()

        def ordered_candidates_for_need(self, request, *, scope):
            return (provider,)

    bundle = SimpleNamespace(catalog_intervals=(SimpleNamespace(interval_id="INTERVALO-001"),), governance={})
    with patch("rasai.consolidation.specialist._longitudinal_packet", return_value=({}, ("E1",))), \
         patch("rasai.consolidation.specialist._longitudinal_schema", return_value={}), \
         patch("rasai.consolidation.specialist._build_ai", return_value=Selection()), \
         patch("rasai.consolidation.specialist._provider_payload", return_value={"request": True}), \
         patch("rasai.consolidation.specialist._extension_diagnostic_from_http", return_value=ProviderDiagnostic(ProviderErrorClass.AUTH_ERROR, http_status=401)), \
         patch("rasai.consolidation.specialist.time.sleep") as sleep:
        run = run_longitudinal_ai(
            bundle,
            normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.test/a",),
                specialist_ai=True,
                ai_provider="auto",
            ),
        )

    assert run.status == "UNAVAILABLE"
    assert run.rounds == 1
    assert calls["count"] == 1
    assert len(run.attempts) == 1
    assert run.attempts[0].retry_eligible is False
    sleep.assert_not_called()


def test_one_audit_does_not_satisfy_consolidated_contract() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-ONLY", when="2026-09-01T10:00:00Z", rule_result="PASS", score=80)
        filters = normalize_filter(
            urls=("https://example.test/a",),
            devices=("MOBILE",),
            specialist_ai=True,
            ai_provider="openai",
        )
        with pytest.raises(ConsolidationExecutionError, match="pelo menos duas auditorias"):
            generate(root, filters)

def test_specialist_rejects_truncated_or_unknown_audit_reference() -> None:
    _validate_canonical_audit_references(
        {
            "summary": "Comparação entre AUD-BASE-123 e AUD-CURRENT-456.",
            "nested": [{"value": "AUD-BASE-123"}],
        },
        {"AUD-BASE-123", "AUD-CURRENT-456"},
    )

    with pytest.raises(ValueError, match="identificador truncado"):
        _validate_canonical_audit_references(
            {"summary": "A auditoria AUD-CURRENT apresentou melhora."},
            {"AUD-BASE-123", "AUD-CURRENT-456"},
        )


def test_effective_web_performance_state_marks_only_current_attempt_as_final() -> None:
    from rasai.consolidation.catalog_longitudinal import _effective_web_performance_state

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(
            """
            CREATE TABLE web_performance_attempts(
                audit_id TEXT,snapshot_id TEXT,service TEXT,status TEXT,
                http_status INTEGER,error_code TEXT,artifact_reference TEXT
            );
            CREATE TABLE web_performance_observations(
                audit_id TEXT,observation_id TEXT,snapshot_id TEXT,status TEXT,
                url TEXT,device TEXT,pagespeed_artifact_reference TEXT,
                crux_artifact_reference TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO web_performance_attempts VALUES (?,?,?,?,?,?,?)",
            (
                "AUD-CURRENT-456",
                "S1",
                "PAGESPEED_INSIGHTS",
                "FAILED_RETRYABLE",
                500,
                "UPSTREAM_ERROR",
                "artifacts/pagespeed-old.json",
            ),
        )
        connection.execute(
            "INSERT INTO web_performance_attempts VALUES (?,?,?,?,?,?,?)",
            (
                "AUD-CURRENT-456",
                "S1",
                "PAGESPEED_INSIGHTS",
                "SUCCESS",
                200,
                None,
                "artifacts/pagespeed-final.json",
            ),
        )
        connection.execute(
            "INSERT INTO web_performance_observations VALUES (?,?,?,?,?,?,?,?)",
            (
                "AUD-CURRENT-456",
                "OBS-1",
                "S1",
                "SUCCESS",
                "https://example.test/",
                "MOBILE",
                "artifacts/pagespeed-final.json",
                None,
            ),
        )
        connection.commit()

        state = _effective_web_performance_state(connection, "AUD-CURRENT-456")
    finally:
        connection.close()

    service = state["contexts"][0]["services"][0]
    assert service["status"] == "SUCCESS"
    assert service["http_status"] == 200
    assert service["artifact_reference"] == "artifacts/pagespeed-final.json"
    assert service["effective_for_current_observation"] is True
    assert service["superseded_attempts"] == 1

def test_longitudinal_ai_html_marks_machine_generated_interpretation() -> None:
    from rasai.consolidation.specialist import SpecialistRun, _longitudinal_ai_html

    run = SpecialistRun(
        requested=True,
        status="COMPLETE",
        summary="Síntese interpretativa.",
        topic_analyses=(),
        attempts=(),
        interval_analyses=(),
        tradeoffs=(),
        strategy={"preservar": (), "corrigir": (), "otimizar": (), "conciliar": (), "investigar": ()},
        profile_id="EVOLUTION",
        profile_version="2.0",
    )

    rendered = _longitudinal_ai_html(run)

    assert "data-ai-generated='true'" in rendered
    assert "Conteúdo interpretativo gerado por IA" in rendered
    assert "requer validação humana" in rendered
    assert "class='grid-2 strategy-grid'" in rendered

def test_unrelated_configuration_rejects_ai_language_that_claims_controlled_comparability() -> None:
    for invalid_text in (
        "Intervalo comparável entre AUD-A e AUD-B.",
        "O intervalo é comparável entre os marcos.",
        "Os marcos são comparáveis.",
        "Há comparabilidade plena entre as execuções.",
        "Não só houve mudança; o intervalo é comparável entre os marcos.",
    ):
        with pytest.raises(ValueError, match="comparação contextual"):
            _validate_configuration_comparability_language(
                {"summary": invalid_text},
                "UNRELATED",
            )

    for valid_text in (
        "Comparação contextual entre AUD-A e AUD-B; as configurações diferem.",
        "As evidências não apresentam uma métrica de Apdex comparável entre os marcos.",
        "Não há intervalo comparável entre as execuções.",
        "Sem comparabilidade plena, a leitura permanece contextual.",
    ):
        _validate_configuration_comparability_language(
            {"summary": valid_text},
            "UNRELATED",
        )


def test_specialist_forecast_does_not_call_price_coverage_high_confidence() -> None:
    estimate = CandidateCostEstimate(
        provider="OPENAI",
        model="gpt-test",
        scope="CONSOLIDATED_SPECIALIST",
        reasoning_profile="LOW",
        estimated_input_tokens=1000,
        estimated_cached_input_tokens=0,
        estimated_output_tokens=2100,
        estimated_cost=0.01,
        currency="USD",
        pricing_context="STANDARD",
    )

    forecast = _forecast((estimate,))

    assert forecast["expected_cost"] == 0.01
    assert forecast["pricing_coverage"] == 1.0
    assert forecast["confidence"] == "MÉDIA"
    assert "volume de tokens" in forecast["confidence_basis"]

def test_ai_projection_disambiguates_scope_from_configuration_comparability() -> None:
    packet = {
        "contract": "CONSOLIDATED-LONGITUDINAL-001",
        "catalog_contract": "CONSOLIDATED-CATALOG-LONGITUDINAL-006",
        "scope": {
            "url": "https://example.test/",
            "device": "MOBILE",
            "audit_count": 2,
            "audit_ids": ["AUD-A", "AUD-B"],
            "event_times": ["2026-09-01T10:00:00Z", "2026-09-02T10:00:00Z"],
        },
        "intervals": [
            {
                "interval_id": "INTERVALO-001",
                "baseline": {"audit_id": "AUD-A", "event_time": "2026-09-01T10:00:00Z"},
                "current": {"audit_id": "AUD-B", "event_time": "2026-09-02T10:00:00Z"},
                "comparable": True,
                "limitations": [],
                "changes": [],
                "fix_verification": [],
                "catalog_changes": [],
                "stable_within_expected": 1,
                "stable_requiring_attention": 0,
                "current_technical_findings": [],
            }
        ],
        "initial_to_final": {
            "baseline_audit_id": "AUD-A",
            "current_audit_id": "AUD-B",
            "changes": [],
            "fix_verification": [],
            "limitations": [],
            "current_technical_findings": [],
        },
        "catalog_state_initial": [],
        "catalog_state_final": [],
        "rule_reference": [],
        "governance": {
            "source_audit_governance": {
                "configuration_comparability": {"pair_status": "UNRELATED"}
            }
        },
    }

    projected, _evidence_ids, _meta = _ai_packet_projection(packet)
    interval = projected["intervals"][0]

    assert "comparable" not in interval
    assert interval["scope_comparable"] is True
    assert interval["configuration_pair_status"] == "UNRELATED"

