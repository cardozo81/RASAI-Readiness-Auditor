from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from rasai.audit_fulfillment import (
    REPLAY_SAFE,
    SUCCESS,
    initialize_contract,
    register_work_item,
    set_work_item_status,
)
from rasai.consolidation.index import ConsolidationIndex
from rasai.consolidation.execution_log import ConsolidationExecutionError
from rasai.consolidation.service import build_data, generate, normalize_filter
from rasai.consolidation.selection import resolve_selection
from rasai.consolidation.specialist import SpecialistAttempt, SpecialistPreview, SpecialistRun, build_longitudinal



def _complete_ai() -> SpecialistRun:
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
        baseline_audit_id="AUD-001",
        current_audit_id="AUD-002",
        comparison_mode="LONGITUDINAL",
        candidates=(),
        selected=None,
        event_count=0,
        excluded_candidates=(),
        forecast={"currency": "USD", "expected_cost": 0.0, "candidate_count": 0},
    )


def _complete_ai_with_exchange() -> SpecialistRun:
    return SpecialistRun(
        requested=True,
        status="COMPLETE",
        summary="No marco inicial a URL tinha menor prontidão. Nos intervalos houve melhora e regressão parcial. No marco final o SARI está acima do início, mas há foco imediato em desempenho e confiança.",
        topic_analyses=(
            {
                "topic": "PERFORMANCE",
                "assessment": "A evidência aponta regressão de desempenho no estado final.",
                "cause_analysis": "A associação observada indica aumento de custo de carregamento; a causa precisa ser confirmada na análise técnica.",
                "recommended_actions": ("Inspecionar LCP/TBT e long tasks; validar novamente após a correção.",),
                "priority": "P0",
                "confidence": 0.9,
                "evidence_ids": (),
            },
        ),
        attempts=(
            SpecialistAttempt(
                provider="OPENAI",
                model="gpt-5.6-luna",
                reasoning="LOW",
                status="SUCCESS",
                duration_ms=120,
                estimated_cost=0.01,
                currency="USD",
                pricing_version="TEST",
                input_tokens=100,
                cached_input_tokens=0,
                output_tokens=40,
                reasoning_tokens=0,
                attempt_no=1,
                round_no=1,
                decision="SUCCESS",
            ),
        ),
        interval_analyses=(),
        tradeoffs=(),
        strategy={"preservar": (), "corrigir": (), "otimizar": (), "conciliar": (), "investigar": ()},
        profile_id="EVOLUTION",
        profile_version="2.0",
        rounds=1,
        candidates=(
            {
                "provider": "OPENAI",
                "model": "gpt-5.6-luna",
                "reasoning_profile": "LOW",
                "estimated_cost": 0.008,
                "currency": "USD",
            },
        ),
        forecast={
            "currency": "USD",
            "expected_cost": 0.008,
            "likely_low": 0.008,
            "likely_high": 0.008,
            "potential": 0.016,
            "max_rounds": 2,
        },
        context_projection={
            "contract": "CONSOLIDATED-AI-CONTEXT-001",
            "level": "COMPACT",
            "estimated_input_tokens": 42000,
            "max_input_hint_tokens": 80000,
        },
        exchanges=(
            {
                "exchange_id": "AIX-TEST",
                "sequence_no": 1,
                "provider": "OPENAI",
                "model": "gpt-5.6-luna",
                "purpose": "AI_REQUEST",
                "endpoint": "https://example.invalid/v1",
                "started_at": "2026-09-20T10:00:00+00:00",
                "finished_at": "2026-09-20T10:00:01+00:00",
                "duration_ms": 120,
                "outcome": "RESPONSE",
                "http_status": 200,
                "exception_type": None,
                "request_payload": "{\"input\":\"sanitizado\"}",
                "request_sha256": "reqhash",
                "request_truncated": False,
                "response_payload": "{\"output\":\"sanitizado\"}",
                "response_sha256": "reshash",
                "response_truncated": False,
            },
        ),
    )


def _failed_ai_with_exchange() -> SpecialistRun:
    return SpecialistRun(
        requested=True,
        status="UNAVAILABLE",
        summary="",
        topic_analyses=(),
        attempts=(
            SpecialistAttempt(
                provider="OPENAI",
                model="gpt-5.6-luna",
                reasoning="LOW",
                status="TECHNICAL_ERROR",
                duration_ms=80,
                estimated_cost=None,
                currency=None,
                pricing_version="TEST",
                input_tokens=None,
                cached_input_tokens=None,
                output_tokens=None,
                reasoning_tokens=None,
                error_class="RATE_LIMIT_ERROR",
                http_status=429,
                attempt_no=1,
                round_no=1,
                decision="RETRY_ROUND",
                retry_eligible=True,
                retry_after_seconds=1.0,
            ),
            SpecialistAttempt(
                provider="OPENAI",
                model="gpt-5.6-luna",
                reasoning="LOW",
                status="TECHNICAL_ERROR",
                duration_ms=90,
                estimated_cost=None,
                currency=None,
                pricing_version="TEST",
                input_tokens=None,
                cached_input_tokens=None,
                output_tokens=None,
                reasoning_tokens=None,
                error_class="RATE_LIMIT_ERROR",
                http_status=429,
                attempt_no=2,
                round_no=2,
                decision="STOP",
                retry_eligible=True,
            ),
        ),
        reason="AI_PROVIDER_CHAIN_EXHAUSTED_AFTER_RETRY",
        profile_id="EVOLUTION",
        profile_version="2.0",
        rounds=2,
        forecast={"currency": "USD", "expected_cost": 0.008, "potential": 0.016},
        exchanges=(
            {
                "exchange_id": "AIX-FAIL-1",
                "sequence_no": 1,
                "provider": "OPENAI",
                "model": "gpt-5.6-luna",
                "request_payload": "{\"input\":\"sanitizado\"}",
                "request_sha256": "req1",
                "request_truncated": False,
                "response_payload": "{\"error\":\"rate limit\"}",
                "response_sha256": "res1",
                "response_truncated": False,
            },
            {
                "exchange_id": "AIX-FAIL-2",
                "sequence_no": 2,
                "provider": "OPENAI",
                "model": "gpt-5.6-luna",
                "request_payload": "{\"input\":\"sanitizado\"}",
                "request_sha256": "req2",
                "request_truncated": False,
                "response_payload": "{\"error\":\"rate limit\"}",
                "response_sha256": "res2",
                "response_truncated": False,
            },
        ),
    )

def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mark_fulfillment_complete(workspace: Path, audit_id: str) -> None:
    """Materialize the current fulfillment contract for a completed fixture AUD."""
    initialize_contract(workspace, audit_id, {"source": "consolidation-test-fixture"})
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


def _make_audit(
    root: Path,
    audit_id: str,
    *,
    when: str,
    urls: tuple[str, ...] = ("https://example.com/a",),
    score: float = 80.0,
    scoring_version: str = "1",
    device: str = "MOBILE",
) -> Path:
    workspace = root / audit_id
    workspace.mkdir(parents=True)
    db = workspace / "audit.db"
    connection = sqlite3.connect(db)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(
                audit_id TEXT PRIMARY KEY, project_name TEXT, status TEXT, completion_status TEXT,
                created_at TEXT, started_at TEXT, completed_at TEXT, auditor_version TEXT,
                ruleset_version TEXT
            );
            CREATE TABLE audit_targets(audit_id TEXT, normalized_origin TEXT);
            CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            CREATE TABLE page_snapshots(
                snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT,captured_at TEXT,
                http_status INTEGER,final_url TEXT,canonical TEXT,meta_robots TEXT,title TEXT,
                browser_metadata TEXT
            );
            CREATE TABLE rule_executions(
                audit_id TEXT,rule_id TEXT,page_id TEXT,device TEXT,result TEXT,
                observed_value TEXT,error TEXT,executed_at TEXT
            );
            CREATE TABLE scores(
                audit_id TEXT,device TEXT,dimension TEXT,value REAL,coverage REAL,confidence TEXT,
                consolidation_status TEXT,scoring_version TEXT,calculated_at TEXT
            );
            CREATE TABLE web_performance_observations(
                audit_id TEXT,url TEXT,device TEXT,captured_at TEXT,status TEXT,strategy TEXT,
                performance_score REAL,accessibility_score REAL,best_practices_score REAL,seo_score REAL,
                fcp_lab_ms REAL,speed_index_lab_ms REAL,lcp_lab_ms REAL,tbt_lab_ms REAL,cls_lab REAL,
                field_source TEXT,field_scope TEXT,lcp_p75_ms REAL,inp_p75_ms REAL,cls_p75 REAL,cwv_assessment TEXT
            );
            CREATE TABLE synthetic_apdex_summaries(
                audit_id TEXT,url TEXT,device TEXT,calculated_at TEXT,profile_id TEXT,threshold_seconds REAL,
                valid_samples INTEGER,invalid_samples INTEGER,satisfied_count INTEGER,tolerating_count INTEGER,
                frustrated_count INTEGER,apdex_score REAL,small_group INTEGER,final_group INTEGER,
                mean_ms REAL,median_ms REAL,p75_ms REAL,p90_ms REAL,p95_ms REAL,p99_ms REAL,trend_percent REAL
            );
            CREATE TABLE findings(
                audit_id TEXT,device TEXT,severity TEXT,category TEXT,page_id TEXT,
                rule_id TEXT,status TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO audits VALUES (?,?,?,?,?,?,?,?,?)",
            (audit_id, "Fixture", "COMPLETED", "COMPLETE", when, when, when, "0.1.0", "rules-v1"),
        )
        connection.execute("INSERT INTO audit_targets VALUES (?,?)", (audit_id, "https://example.com"))
        for pos, url in enumerate(urls, 1):
            page_id = f"{audit_id}-P{pos}"
            connection.execute("INSERT INTO pages VALUES (?,?,?)", (page_id, audit_id, url))
            connection.execute(
                "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    f"{audit_id}-S{pos}", page_id, device, when, 200, url,
                    url, "index,follow", f"Fixture {pos}", "{}",
                ),
            )
            connection.execute(
                "INSERT INTO rule_executions VALUES (?,?,?,?,?,?,?,?)",
                (
                    audit_id, "BR-GEO-002", page_id, device, "PASS",
                    json.dumps({"fixture": True}), None, when,
                ),
            )
            connection.execute(
                "INSERT INTO web_performance_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    audit_id, url, device, when, "SUCCESS", "mobile", 0.90 + pos / 1000,
                    0.88, 0.91, 0.92, 900.0, 1400.0, 2100.0, 120.0, 0.05,
                    "PAGESPEED", "URL", 2300.0, 180.0, 0.06, "GOOD",
                ),
            )
            connection.execute(
                "INSERT INTO synthetic_apdex_summaries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    audit_id, url, device, when, "RASAI_MOBILE_TEST", 2.0,
                    100, 0, 90, 8, 2, 0.94, 0, 1,
                    980.0, 900.0, 1200.0, 1500.0, 1900.0, 2400.0, 2.0,
                ),
            )
            connection.execute(
                "INSERT INTO findings VALUES (?,?,?,?,?,?,?)",
                (audit_id, device, "MEDIUM", "TEST", page_id, "BR-GEO-002", "OPEN"),
            )
        connection.execute(
            "INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?)",
            (audit_id, device, "OVERALL_READINESS", score, 1.0, "HIGH", "COMPLETE", scoring_version, when),
        )
        connection.commit()
    finally:
        connection.close()
    _mark_fulfillment_complete(workspace, audit_id)
    return db


class ConsolidationTests(unittest.TestCase):
    def test_generation_is_read_only_and_deduplicates_identical_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db1 = _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00", score=70.0)
            db2 = _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00", score=80.0)
            before = {db1: _digest(db1), db2: _digest(db2)}
            filters = normalize_filter(
                domains=("example.com",),
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai()):
                first = generate(root, filters)
            with patch(
                "rasai.consolidation.service.prepare_longitudinal_specialist",
                side_effect=AssertionError("dedupe deve ocorrer antes da preparação pesada"),
            ) as prepare_again, patch(
                "rasai.consolidation.service.preview_longitudinal_specialist",
                side_effect=AssertionError("reuso não deve recalcular prévia"),
            ) as preview_again:
                second = generate(root, filters)
            prepare_again.assert_not_called()
            preview_again.assert_not_called()
            self.assertFalse(first.reused)
            self.assertTrue(second.reused)
            self.assertEqual(first.report_path, second.report_path)
            self.assertTrue(first.report_path.is_file())
            self.assertTrue(first.manifest_path.is_file())
            self.assertEqual(before, {db1: _digest(db1), db2: _digest(db2)})
            manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["summary"]["audits"], 2)
            self.assertEqual(manifest["filters"]["domains"], ["example.com"])
            report_hash = _digest(first.report_path)
            self.assertEqual(report_hash, manifest["package_integrity"]["files"]["report.html"]["sha256"])
            self.assertEqual(report_hash, _digest(second.report_path))

    def test_new_matching_audit_invalidates_report_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-07-01T10:00:00-03:00", score=70.0)
            _make_audit(root, "AUD-002", when="2026-08-01T10:00:00-03:00", score=80.0)
            filters = normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai()):
                first = generate(root, filters)
            _make_audit(root, "AUD-003", when="2026-09-01T10:00:00-03:00", score=85.0)
            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai()):
                second = generate(root, filters)
            self.assertFalse(second.reused)
            self.assertNotEqual(first.request_fingerprint, second.request_fingerprint)
            self.assertNotEqual(first.report_path, second.report_path)

    def test_source_fingerprint_change_prevents_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00", score=70.0)
            db2 = _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00", score=80.0)
            filters = normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai()):
                first = generate(root, filters)

            connection = sqlite3.connect(db2)
            try:
                connection.execute(
                    "UPDATE audits SET project_name=? WHERE audit_id=?",
                    ("Projeto com fingerprint alterado", "AUD-002"),
                )
                connection.commit()
            finally:
                connection.close()

            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai()):
                second = generate(root, filters)

            self.assertFalse(second.reused)
            self.assertNotEqual(first.request_fingerprint, second.request_fingerprint)


    def test_filter_change_prevents_reuse_with_same_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00", score=70.0)
            _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00", score=80.0)
            first_filters = normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
                ai_reasoning="LOW",
            )
            second_filters = normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
                ai_reasoning="MEDIUM",
            )
            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai()):
                first = generate(root, first_filters)
                second = generate(root, second_filters)

            self.assertFalse(second.reused)
            self.assertNotEqual(first.request_fingerprint, second.request_fingerprint)


    def test_materialization_revision_prevents_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00", score=70.0)
            _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00", score=80.0)
            filters = normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai()):
                first = generate(root, filters)

            with patch(
                "rasai.consolidation.cons5.MATERIALIZATION_CONTRACT",
                "CONSOLIDATED-MATERIALIZATION-TEST-REVISION",
            ), patch(
                "rasai.consolidation.service.preview_longitudinal_specialist",
                return_value=_preview_ok(),
            ), patch(
                "rasai.consolidation.service.run_longitudinal_ai",
                return_value=_complete_ai(),
            ):
                second = generate(root, filters)

            self.assertFalse(second.reused)
            self.assertNotEqual(first.request_fingerprint, second.request_fingerprint)


    def test_url_filter_never_reuses_audit_level_score_for_partial_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(
                root,
                "AUD-001",
                when="2026-09-01T10:00:00-03:00",
                urls=("https://example.com/a", "https://example.com/b"),
                score=77.0,
            )
            index = ConsolidationIndex(root)
            index.refresh()
            filters = normalize_filter(urls=("https://example.com/a",), devices=("MOBILE",))
            points = index.load_points(filters)
            self.assertEqual(points["scores"], ())
            self.assertEqual(len(points["performance"]), 1)
            self.assertEqual(points["performance"][0]["url"], "https://example.com/a")
            data = build_data(index, filters)
            self.assertFalse(data.scores)
            self.assertTrue(any("pontuações calculadas" in item for item in data.limitations))

    def test_mixed_scoring_versions_are_not_averaged_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00", score=50.0, scoring_version="1")
            _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00", score=90.0, scoring_version="2")
            index = ConsolidationIndex(root)
            index.refresh()
            data = build_data(index, normalize_filter(devices=("MOBILE",)))
            overall = next(item for item in data.scores if item.dimension == "OVERALL_READINESS")
            self.assertEqual(overall.scoring_versions, ("1", "2"))
            self.assertEqual(overall.statistics.count, 1)
            self.assertEqual(overall.statistics.current, 90.0)
            self.assertIsNotNone(overall.limitation)

    def test_generation_supports_deterministic_mode_and_rejects_non_unique_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00")
            _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00")

            deterministic = generate(
                root,
                normalize_filter(devices=("MOBILE",), urls=("https://example.com/a",)),
            )
            manifest = json.loads(deterministic.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["generation_mode"], "DETERMINISTIC")
            self.assertFalse(manifest["specialist_ai"]["requested"])
            self.assertEqual(manifest["longitudinal_analysis"]["ai_status"], "NOT_REQUESTED")

            filters = normalize_filter(
                devices=("MOBILE", "DESKTOP"),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            with self.assertRaisesRegex(ConsolidationExecutionError, "exatamente um dispositivo"):
                generate(root, filters)

    def test_single_audit_is_not_a_consolidated_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-09-01T10:00:00-03:00")
            filters = normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            with self.assertRaisesRegex(ConsolidationExecutionError, "pelo menos duas auditorias"):
                generate(root, filters)

    def test_failed_ai_preserves_deterministic_consolidation_and_execution_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00")
            _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00")
            filters = normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_failed_ai_with_exchange()):
                result = generate(root, filters)

            self.assertTrue(result.report_path.is_file())
            execution = json.loads((result.report_dir / "execution.json").read_text(encoding="utf-8"))
            exchanges = json.loads((result.report_dir / "ai-exchanges.json").read_text(encoding="utf-8"))
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(execution["status"], "COMPLETE")
            self.assertEqual(execution["ai"]["status"], "UNAVAILABLE")
            self.assertEqual(execution["ai"]["rounds"], 2)
            self.assertEqual(len(exchanges["exchanges"]), 2)
            self.assertEqual(manifest["specialist_ai"]["status"], "UNAVAILABLE")
            self.assertEqual(manifest["longitudinal_analysis"]["ai_status"], "UNAVAILABLE")
            self.assertTrue(tuple((root / "consolidated").glob("CONS-*")))

    def test_successful_cons5_renders_cost_forecast_and_ai_exchange(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00")
            _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00")
            filters = normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai_with_exchange()):
                result = generate(root, filters)

            html = result.report_path.read_text(encoding="utf-8")
            self.assertIn("Custo esperado", html)
            self.assertIn("Solicitação enviada à IA", html)
            self.assertIn("Resposta recebida da IA", html)
            self.assertIn("sanitizado", html)
            self.assertIn("Governança da IA, custos e comunicações", html)
            self.assertIn("Análise longitudinal assistida por IA", html)
            self.assertIn("Visão executiva do estudo longitudinal", html)
            self.assertIn("SARI - Índice de prontidão para Busca e IA", html)
            self.assertIn("Resumo gerencial gerado por IA", html)
            self.assertIn("Prioridades para decisão", html)
            self.assertIn("Diagnóstico / causa provável", html)
            self.assertIn("Governança, integridade e auditabilidade", html)
            self.assertNotIn("Análise especialista por IA e plano priorizado", html)
            self.assertIn("longitudinal-evidence.json", html)
            for name in (
                "ai-exchanges.json", "longitudinal-evidence.json", "decision-context.json",
                "execution.json", "specialist-analysis.json",
            ):
                self.assertTrue((result.report_dir / name).is_file(), name)
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["consolidation_execution"]["execution_path"], "execution.json")
            self.assertEqual(manifest["consolidation_execution"]["exchanges_path"], "ai-exchanges.json")
            self.assertEqual(manifest["specialist_ai"]["rounds"], 1)
            self.assertEqual(manifest["specialist_ai"]["context_projection"]["level"], "COMPACT")
            self.assertEqual(manifest["longitudinal_analysis"]["evidence_file"], "longitudinal-evidence.json")
            self.assertEqual(manifest["decision_context"]["contract"], "CONSOLIDATED-DECISION-CONTEXT-002")
            self.assertEqual(manifest["source_governance"]["contract"], "CONSOLIDATED-SOURCE-GOVERNANCE-003")
            self.assertEqual(manifest["source_governance"]["conclusion_state"], "CONCLUSIVE")
            self.assertTrue(all(item["source_integrity_sha256"] for item in manifest["source_governance"]["audits"]))
            self.assertIn("execution.json", manifest["package_integrity"]["files"])
            decision = json.loads((result.report_dir / "decision-context.json").read_text(encoding="utf-8"))
            self.assertTrue(decision["sari"]["available"])
            self.assertEqual(decision["sari"]["method"], "SARI-001 / SCORE-GEO-004")
            self.assertIn(decision["ai_reliability"]["label"], {"Muito alta", "Alta", "Limitada", "Não determinada"})
            self.assertIn("Confiabilidade da interpretação por IA", html)

    def test_non_final_source_makes_series_non_conclusive_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00", score=70.0)
            db2 = _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00", score=80.0)
            connection = sqlite3.connect(db2)
            try:
                connection.execute(
                    "UPDATE audit_fulfillment_contracts SET processing_status='PARTIAL_RETRYABLE', "
                    "report_status='INCOMPLETE', consolidation_eligible=0, pending_items=1 "
                    "WHERE audit_id='AUD-002'"
                )
                connection.execute(
                    "UPDATE audit_fulfillment_work_items SET status='FAILED_RETRYABLE', retryable=1, "
                    "last_error_code='TEST_RETRY' WHERE audit_id='AUD-002' AND component='CORE_AUDIT'"
                )
                connection.commit()
            finally:
                connection.close()

            filters = normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            index = ConsolidationIndex(root)
            index.refresh()
            bundle = build_longitudinal(root, filters)
            self.assertEqual(bundle.governance["conclusion_state"], "NON_CONCLUSIVE")
            self.assertIn("AUD-002", bundle.governance["reprocess_recommended_audit_ids"])
            self.assertTrue(any("não conclusiva" in item.casefold() for item in bundle.limitations))

            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai_with_exchange()):
                result = generate(root, filters)
            html = result.report_path.read_text(encoding="utf-8")
            self.assertIn("Análise não conclusiva", html)
            self.assertIn("AUD-002", html)
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_governance"]["conclusion_state"], "NON_CONCLUSIVE")

    def test_complete_with_limitations_is_final_without_reprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00", score=70.0)
            db2 = _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00", score=80.0)
            connection = sqlite3.connect(db2)
            try:
                connection.execute(
                    "UPDATE audits SET completion_status='COMPLETE_WITH_LIMITATIONS' WHERE audit_id='AUD-002'"
                )
                connection.commit()
            finally:
                connection.close()

            filters = normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            index = ConsolidationIndex(root)
            index.refresh()
            bundle = build_longitudinal(root, filters)

            self.assertEqual(bundle.governance["conclusion_state"], "CONCLUSIVE_WITH_LIMITATIONS")
            self.assertEqual(bundle.governance["limited_audits"], 1)
            self.assertEqual(bundle.governance["reprocess_recommended_audit_ids"], [])

            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai_with_exchange()):
                result = generate(root, filters)
            html = result.report_path.read_text(encoding="utf-8")
            self.assertIn("Série conclusiva com limitações", html)
            self.assertIn("não há recomendação automática de reprocessamento", html)


    def test_invalid_audit_is_isolated_during_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-OK", when="2026-09-01T10:00:00-03:00")
            broken = root / "AUD-BROKEN"
            broken.mkdir()
            (broken / "audit.db").write_bytes(b"not sqlite")
            refresh = ConsolidationIndex(root).refresh()
            self.assertEqual(refresh.discovered, 2)
            self.assertEqual(refresh.indexed, 1)
            self.assertEqual(len(refresh.issues), 1)

    def test_date_filter_is_inclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00")
            _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00")
            index = ConsolidationIndex(root)
            index.refresh()
            rows = index.candidate_audits(normalize_filter(date_from=date(2026, 9, 1), date_to=date(2026, 9, 1)))
            self.assertEqual([row["audit_id"] for row in rows], ["AUD-002"])


    def test_audit_selection_resolves_base_current_and_intermediate_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-09-01T10:00:00-03:00")
            _make_audit(root, "AUD-002", when="2026-09-10T10:00:00-03:00")
            _make_audit(root, "AUD-003", when="2026-09-20T10:00:00-03:00")
            index = ConsolidationIndex(root)
            index.refresh()

            all_selection = resolve_selection(
                index,
                "AUD-003",
                "AUD-001",
                selection_mode="ALL",
            )
            self.assertEqual(all_selection.baseline_audit_id, "AUD-001")
            self.assertEqual(all_selection.current_audit_id, "AUD-003")
            self.assertEqual(all_selection.audit_ids, ("AUD-001", "AUD-002", "AUD-003"))

            manual = resolve_selection(
                index,
                "AUD-001",
                "AUD-003",
                selection_mode="MANUAL",
                manual_audit_ids=(),
            )
            self.assertEqual(manual.audit_ids, ("AUD-001", "AUD-003"))
            self.assertEqual(manual.excluded_audit_ids, ("AUD-002",))

    def test_success_only_uses_source_governance_and_keeps_successful_marks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-09-01T10:00:00-03:00")
            db2 = _make_audit(root, "AUD-002", when="2026-09-10T10:00:00-03:00")
            _make_audit(root, "AUD-003", when="2026-09-20T10:00:00-03:00")
            connection = sqlite3.connect(db2)
            try:
                connection.execute(
                    "UPDATE audit_fulfillment_contracts SET processing_status='PARTIAL_RETRYABLE', "
                    "report_status='INCOMPLETE', consolidation_eligible=0, pending_items=1 "
                    "WHERE audit_id='AUD-002'"
                )
                connection.execute(
                    "UPDATE audit_fulfillment_work_items SET status='FAILED_RETRYABLE', retryable=1 "
                    "WHERE audit_id='AUD-002' AND component='CORE_AUDIT'"
                )
                connection.commit()
            finally:
                connection.close()

            index = ConsolidationIndex(root)
            index.refresh()
            selection = resolve_selection(
                index,
                "AUD-001",
                "AUD-003",
                selection_mode="SUCCESS_ONLY",
            )
            self.assertEqual(selection.audit_ids, ("AUD-001", "AUD-003"))
            self.assertEqual(selection.excluded_audit_ids, ("AUD-002",))

    def test_consolidated_generation_without_ai_is_valid_and_does_not_call_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-09-01T10:00:00-03:00", score=72.0)
            _make_audit(root, "AUD-002", when="2026-09-20T10:00:00-03:00", score=81.0)
            filters = normalize_filter(
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                audit_ids=("AUD-001", "AUD-002"),
                selection_mode="ALL",
                specialist_ai=False,
            )
            with patch(
                "rasai.consolidation.service.run_longitudinal_ai",
                side_effect=AssertionError("modo determinístico não deve chamar IA"),
            ) as run_ai:
                first = generate(root, filters)
            run_ai.assert_not_called()
            manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["generation_mode"], "DETERMINISTIC")
            self.assertEqual(manifest["specialist_ai"]["status"], "NOT_REQUESTED")
            self.assertFalse(manifest["specialist_ai"]["requested"])
            self.assertFalse(manifest["specialist_ai"]["required"])
            self.assertEqual(manifest["selection_mode"], "ALL")
            self.assertEqual(manifest["selection"]["audit_ids"], ["AUD-001", "AUD-002"])
            self.assertTrue(manifest["consolidation_confidence"]["ai_independent"])

            second = generate(root, filters)
            self.assertTrue(second.reused)
            self.assertEqual(first.report_path, second.report_path)


if __name__ == "__main__":
    unittest.main()

def test_source_governance_detects_report_catalog_that_no_longer_matches_live_audit(tmp_path: Path) -> None:
    from rasai.consolidation.governance import _logical_sqlite_digest, _report_catalog_freshness

    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY,value TEXT)")
        connection.execute("INSERT INTO sample(value) VALUES ('initial')")
        connection.commit()
    finally:
        connection.close()

    report_dir = tmp_path / "report-catalog"
    report_dir.mkdir()
    logical_digest = _logical_sqlite_digest(database)
    (report_dir / "manifest.json").write_text(
        json.dumps({
            "source_fingerprint": "deliberately-not-used-when-logical-digest-exists",
            "audit_snapshot": {"source_logical_sha256": logical_digest},
        }),
        encoding="utf-8",
    )

    initial = _report_catalog_freshness(database)
    assert initial["report_catalog_fresh"] is True
    assert initial["report_catalog_freshness_basis"] == "LOGICAL_SQLITE"

    connection = sqlite3.connect(database)
    try:
        connection.execute("INSERT INTO sample(value) VALUES ('after-report')")
        connection.commit()
    finally:
        connection.close()

    state = _report_catalog_freshness(database)
    assert state["report_catalog_present"] is True
    assert state["report_catalog_fresh"] is False
    assert state["report_catalog_state"] == "STALE"

def test_source_revision_state_uses_material_rpr_and_preserves_replay_safe_chronology(tmp_path: Path) -> None:
    from rasai.consolidation.governance import _source_revision_state

    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audit_reprocess_runs(
                reprocess_id TEXT PRIMARY KEY,
                audit_id TEXT,
                successful_items INTEGER,
                completed_at TEXT
            );
            CREATE TABLE audit_fulfillment_work_items(
                work_item_id TEXT PRIMARY KEY,
                audit_id TEXT,
                temporal_mode TEXT
            );
            CREATE TABLE audit_fulfillment_attempts(
                attempt_id TEXT PRIMARY KEY,
                audit_id TEXT,
                work_item_id TEXT,
                reprocess_id TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO audit_reprocess_runs VALUES (?,?,?,?)",
            ("RPR-MATERIAL", "AUD-REV", 1, "2026-09-22T12:36:00Z"),
        )
        connection.execute(
            "INSERT INTO audit_reprocess_runs VALUES (?,?,?,?)",
            ("RPR-NOOP", "AUD-REV", 0, "2026-09-22T12:40:00Z"),
        )
        connection.execute(
            "INSERT INTO audit_fulfillment_work_items VALUES (?,?,?)",
            ("WI-REPLAY", "AUD-REV", "REPLAY_SAFE"),
        )
        connection.execute(
            "INSERT INTO audit_fulfillment_attempts VALUES (?,?,?,?)",
            ("ATT-1", "AUD-REV", "WI-REPLAY", "RPR-MATERIAL"),
        )
        connection.commit()
    finally:
        connection.close()

    state = _source_revision_state(database, "AUD-REV", "2026-09-22T12:26:00Z")

    assert state["source_revision_id"].startswith("REV-")
    assert len(state["source_revision_logical_sha256"]) == 64
    assert state["post_observation_revision"] is True
    assert state["reprocess_count_after_observation"] == 1
    assert state["revision_at"] == "2026-09-22T12:36:00Z"
    assert state["revision_mode"] == "REPLAY_SAFE"

def test_consolidation_confidence_penalizes_live_temporal_overlap_but_not_replay_safe() -> None:
    from types import SimpleNamespace
    from rasai.consolidation.confidence import evaluate_consolidation_confidence

    data = SimpleNamespace(
        configuration_comparability={"pair_status": "EXACT"},
        score_history=({"dimension": "OVERALL_READINESS", "scoring_version": "SCORE-GEO-004"},),
        limitations=(),
    )
    replay_bundle = SimpleNamespace(
        audit_ids=("AUD-A", "AUD-B"),
        governance={
            "conclusion_state": "CONCLUSIVE",
            "temporal_revision_overlaps": (
                {"state": "REPLAY_SAFE_AFTER_NEXT_OBSERVATION"},
            ),
        },
    )
    live_bundle = SimpleNamespace(
        audit_ids=("AUD-A", "AUD-B"),
        governance={
            "conclusion_state": "CONCLUSIVE",
            "temporal_revision_overlaps": (
                {"state": "LIVE_RECOLLECTION_AFTER_NEXT_OBSERVATION"},
            ),
        },
    )

    replay = evaluate_consolidation_confidence(data, replay_bundle)
    live = evaluate_consolidation_confidence(data, live_bundle)

    assert replay["score"] == 100
    assert live["score"] == 80
    assert any(
        item["factor"] == "revisao_temporal_pos_observacao"
        and item["state"] == "LIVE_RECOLLECTION_AFTER_NEXT_OBSERVATION"
        and item["impact"] == -20
        for item in live["factors"]
    )

def test_source_navigation_policy_strips_stale_renderer_link_without_ai_dependency(tmp_path: Path) -> None:
    from types import SimpleNamespace
    from rasai.consolidation.service import _enforce_source_navigation_policy

    report_path = tmp_path / "report.html"
    report_path.write_text(
        "<html><body>"
        "<a href='../../AUD-FRESH/report-catalog/index.html'>AUD-FRESH</a>"
        "<a href='../../AUD-STALE/report-catalog/index.html'>AUD-STALE</a>"
        "</body></html>",
        encoding="utf-8",
    )
    result = SimpleNamespace(report_path=report_path)
    governance = {
        "audits": [
            {"audit_id": "AUD-FRESH", "report_catalog_fresh": True},
            {"audit_id": "AUD-STALE", "report_catalog_fresh": False},
        ]
    }

    _enforce_source_navigation_policy(result, governance)

    rendered = report_path.read_text(encoding="utf-8")
    assert "../../AUD-FRESH/report-catalog/index.html" in rendered
    assert "../../AUD-STALE/report-catalog/index.html" not in rendered
    assert "AUD-STALE" in rendered

def test_source_governance_contract_versions_temporal_revision_semantics() -> None:
    from rasai.consolidation import cons5
    from rasai.consolidation import governance

    assert governance.GOVERNANCE_CONTRACT == "CONSOLIDATED-SOURCE-GOVERNANCE-003"
    assert cons5.GOVERNANCE_CONTRACT == governance.GOVERNANCE_CONTRACT

