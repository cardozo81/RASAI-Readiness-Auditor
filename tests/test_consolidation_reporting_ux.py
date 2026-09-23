from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from rasai.consolidation.aggregate import _PERF_FIELDS, summarize_findings
from rasai.consolidation.decision_context import _ai_reliability, _catalog_matrix
from rasai.consolidation.execution_log import ConsolidationExecutionError
from rasai.consolidation.presentation import _source_limitation_label, finalize_reader_experience
from rasai.consolidation.reporting import _FINDING_CATEGORY, _audit_link, _confidence, _device, _dimension, _human_counts
from rasai.consolidation.service import generate, normalize_filter
from rasai.consolidation.specialist import _event_indicator_label
from rasai.consolidation.temporal_apdex import TemporalApdexSeries, _kind_label, render_temporal_apdex
from tests.test_consolidation import _complete_ai, _make_audit, _preview_ok


class ConsolidationReportingUXTests(unittest.TestCase):
    def test_public_labels_match_audit_reports(self) -> None:
        self.assertEqual(_device("MOBILE"), "Dispositivo móvel")
        self.assertEqual(_dimension("DISCOVERY_ACCESS"), "Acesso e descoberta")
        self.assertEqual(_dimension("INDEXABILITY"), "Indexabilidade e canonicalização")
        self.assertEqual(_dimension("EVIDENCE_TRUST"), "Evidências e confiabilidade")
        self.assertEqual(_dimension("CONTENT_VALUE"), "Valor do conteúdo")
        self.assertEqual(_dimension("Discovery & Crawler Access"), "Acesso e descoberta")
        self.assertEqual(_dimension("Answerability"), "Capacidade de resposta")
        self.assertEqual(_confidence("VERY_HIGH"), "Muito alta")
        self.assertEqual(_confidence("MEDIUM"), "Média")
        self.assertEqual(_confidence("UNAVAILABLE"), "Indisponível")
        self.assertEqual(_confidence("NOT_DETERMINABLE"), "Não determinada")
        self.assertEqual(_confidence("FUTURE_ENUM"), "Não determinada")
        self.assertEqual(_kind_label("NAVIGATION"), "Apdex de navegação")
        self.assertEqual(_kind_label("EXPERIENCE"), "Apdex de experiência")
        self.assertEqual(_event_indicator_label({"domain": "APDEX", "label": "Apdex Score"}), "Apdex de navegação")
        self.assertEqual(_event_indicator_label({"domain": "UX_APDEX", "label": "Apdex Score"}), "Apdex de experiência")
        labels = {field: label for field, label, _unit in _PERF_FIELDS}
        self.assertEqual(labels["performance_score"], "Lighthouse Performance")
        self.assertEqual(labels["accessibility_score"], "Lighthouse Accessibility")
        self.assertEqual(labels["best_practices_score"], "Lighthouse Best Practices")
        self.assertEqual(labels["fcp_lab_ms"], "FCP de laboratório")
        self.assertEqual(labels["tbt_lab_ms"], "Total Blocking Time")
        self.assertEqual(_FINDING_CATEGORY["PERFORMANCE"], "Desempenho")
        self.assertEqual(_FINDING_CATEGORY["SECURITY"], "Segurança")
        self.assertEqual(_FINDING_CATEGORY["Answerability"], "Capacidade de resposta")
        self.assertEqual(_FINDING_CATEGORY["Citation Readiness"], "Preparação para citação")
        self.assertEqual(_FINDING_CATEGORY["Evidence & Trust"], "Evidência e confiança")
        chips = _human_counts({"Answerability": 7, "Citation Readiness": 3}, _FINDING_CATEGORY)
        self.assertIn("Capacidade de resposta", chips)
        self.assertIn("Preparação para citação", chips)
        self.assertNotIn(">Answerability<", chips)
        self.assertNotIn(">Citation Readiness<", chips)

    def test_source_audit_link_targets_canonical_report_in_new_tab(self) -> None:
        rendered = _audit_link("AUD-20260920-ABC123")
        self.assertIn("href='../../AUD-20260920-ABC123/report-catalog/index.html'", rendered)
        self.assertIn("target='_blank'", rendered)
        self.assertIn("rel='noopener noreferrer'", rendered)

    def test_findings_count_unique_affected_urls_not_page_ids(self) -> None:
        rows = (
            {"severity": "MEDIUM", "category": "SEO", "page_id": "P-1", "url": "https://example.test/"},
            {"severity": "MEDIUM", "category": "SEO", "page_id": "P-2", "url": "https://example.test/"},
            {"severity": "MEDIUM", "category": "SEO", "page_id": "P-3", "url": "https://example.test/"},
        )
        summary = summarize_findings(rows)
        self.assertEqual(summary.observations, 3)
        self.assertEqual(summary.affected_pages, 1)

    def test_catalog_not_requested_has_no_longitudinal_baseline(self) -> None:
        bundle = SimpleNamespace(
            catalog_snapshots=(
                SimpleNamespace(catalogs=(
                    {"catalog_id": "CAT-06", "label": "Apdex de navegação", "status": "PARCIAL"},
                    {"catalog_id": "CAT-10", "label": "Segurança passiva", "status": "NÃO SOLICITADO"},
                )),
                SimpleNamespace(catalogs=(
                    {"catalog_id": "CAT-06", "label": "Apdex de navegação", "status": "PARCIAL"},
                    {"catalog_id": "CAT-10", "label": "Segurança passiva", "status": "CONCLUÍDO"},
                )),
            )
        )
        matrix = _catalog_matrix(bundle)
        by_id = {item["catalog_id"]: item for item in matrix["rows"]}
        self.assertFalse(by_id["CAT-10"]["comparable"])
        self.assertEqual(matrix["warnings"], 2)

    def test_ai_reliability_is_limited_when_configurations_are_unrelated(self) -> None:
        data = SimpleNamespace(configuration_comparability={"pair_status": "UNRELATED"})
        bundle = SimpleNamespace(governance={"conclusion_state": "CONCLUSIVE_WITH_LIMITATIONS"})
        priorities = [
            {"confidence": 0.95, "evidence_ids": ["EV-1"]},
            {"confidence": 0.90, "evidence_ids": ["EV-2"]},
        ]
        reliability = _ai_reliability(data, bundle, SimpleNamespace(status="COMPLETE"), priorities)
        self.assertEqual(reliability["label"], "Limitada")
        self.assertIn("não é uma repetição controlada equivalente", " ".join(reliability["reasons"]))

    def test_source_limitation_is_exposed_with_human_label(self) -> None:
        self.assertEqual(
            _source_limitation_label("RENDERED_DISCOVERY_GAP:8"),
            "Lacuna na descoberta renderizada: 8 URLs renderizadas fora do universo auditado",
        )

    def test_header_and_status_are_left_aligned_without_max_width(self) -> None:
        html = (
            "<html><head></head><body><header><h1>RASAi</h1></header>"
            "<section class='rasai-analysis-status state-info' data-rasai-consolidated-experience='true'>"
            "<div class='rasai-analysis-status-main'><div><h2>Estado</h2></div></div>"
            "<div class='rasai-status-meta'></div></section>"
            "<nav aria-label='Navegação do relatório'></nav><main></main></body></html>"
        )
        rendered = finalize_reader_experience(html, {})
        self.assertIn("class='cons-header-shell'", rendered)
        self.assertIn("class='rasai-analysis-status-shell'", rendered)
        self.assertIn(".cons-header-shell{margin:0;padding:0 26px}", rendered)
        self.assertIn(".rasai-analysis-status-shell{margin:0;padding:0 26px;box-sizing:border-box}", rendered)
        self.assertIn("nav{padding-left:26px;padding-right:26px}", rendered)
        self.assertNotIn("max-width:1500px", rendered)
        self.assertNotIn("calc((100% - 1500px)/2 + 26px)", rendered)

    def test_visible_cons_text_humanizes_internal_domains_but_preserves_raw_payloads(self) -> None:
        html = (
            "<html><head></head><body><header><p>MOBILE · PERFORMANCE · WARNING</p></header>"
            "<p>BALANCED · NONE · Mobile · FAIL</p>"
            "<p>Aplicar ADD_FACTUAL_CONTEXT e revisar NAVIGATION_LOAD.</p>"
            "<p>Canonical declarations must be interpretable and non-conflicting</p>"
            "<pre>{\"device\":\"MOBILE\",\"status\":\"FAIL\",\"projection\":\"BALANCED\"}</pre>"
            "<section class='rasai-analysis-status state-info' data-rasai-consolidated-experience='true'>"
            "<div class='rasai-analysis-status-main'><div><h2>Estado</h2></div></div>"
            "<div class='rasai-status-meta'></div></section>"
            "<nav aria-label='Navegação do relatório'></nav><main></main></body></html>"
        )
        rendered = finalize_reader_experience(html, {})
        self.assertIn("Dispositivo móvel · Desempenho · Atenção", rendered)
        self.assertIn("Balanceado · Nenhum · dispositivo móvel · Não aprovado", rendered)
        self.assertIn("Adicionar contexto factual", rendered)
        self.assertIn("Carregamento da navegação", rendered)
        self.assertIn("Declarações canonical devem ser interpretáveis e não conflitantes", rendered)
        self.assertIn('<pre>{\"device\":\"MOBILE\",\"status\":\"FAIL\",\"projection\":\"BALANCED\"}</pre>', rendered)

    def test_temporal_apdex_uses_human_labels_instead_of_internal_variables(self) -> None:
        series = TemporalApdexSeries(
            contract="TEMPORAL-APDEX-001",
            kind="EXPERIENCE",
            url="https://example.test/",
            device="MOBILE",
            task_id="SYNTHETIC_LOAD_ACTION",
            profile_id="RASAI_MOBILE_mobile-balanced-chromium_mobile-balanced_mobile-4g-balanced",
            threshold_seconds=3.0,
            frustrated_threshold_seconds=12.0,
            kpm="USER_ACTION_DURATION",
            session_mode="cold",
            errors_affect_apdex=True,
            error_scope="navigation",
            pacing="delay=1.0;concurrency=1;settle=5.0",
            context_note="KPM=USER_ACTION_DURATION; calibração=MANUAL_CALIBRATION",
            audits=3,
            summary_observations=3,
            valid_samples=6,
            invalid_samples=0,
            satisfied_count=3,
            tolerating_count=2,
            frustrated_count=1,
            apdex_score=2/3,
            samples_with_duration=6,
            duration_mean_ms=4000.0,
            duration_median_ms=3500.0,
            duration_p75_ms=5000.0,
            duration_p90_ms=8000.0,
            duration_p95_ms=9000.0,
            duration_p99_ms=10000.0,
            duration_min_ms=1000.0,
            duration_max_ms=11000.0,
            duration_stddev_ms=3000.0,
            duration_cv=0.75,
            first_observed_at="2026-09-19T00:00:00Z",
            last_observed_at="2026-09-20T00:00:00Z",
            small_groups=3,
            final_groups=0,
            limitation=None,
        )
        rendered = render_temporal_apdex((series,))
        self.assertIn("Duração da ação do usuário", rendered)
        self.assertIn("Satisfeitas / Toleráveis / Frustradas", rendered)
        self.assertIn("Dispositivo móvel · Chromium · perfil balanceado · rede móvel 4G balanceada", rendered)
        self.assertIn("intervalo entre amostras: 1.0 s", rendered)
        self.assertIn("calibração manual", rendered)
        self.assertNotIn("USER_ACTION_DURATION", rendered)
        self.assertNotIn("MANUAL_CALIBRATION", rendered)
        self.assertNotIn("RASAI_MOBILE_mobile-balanced", rendered)
        self.assertNotIn("Satisfied / Tolerating / Frustrated", rendered)

    def test_single_audit_is_rejected_as_consolidated_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(
                root,
                "AUD-001",
                when="2026-09-05T10:00:00-03:00",
                score=97.22,
                scoring_version="SCORE-GEO-004",
            )
            filters = normalize_filter(
                urls=("https://example.com/a",),
                devices=("MOBILE",),
                specialist_ai=True,
                ai_provider="openai",
            )
            with self.assertRaisesRegex(ConsolidationExecutionError, "pelo menos duas auditorias"):
                generate(root, filters)

    def test_three_comparable_audits_render_historical_chart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, score in enumerate((70.0, 80.0, 90.0), 1):
                _make_audit(
                    root,
                    f"AUD-00{index}",
                    when=f"2026-0{6 + index}-01T10:00:00-03:00",
                    score=score,
                    scoring_version="SCORE-GEO-004",
                )
            filters = normalize_filter(
                domains=("example.com",),
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai()):
                result = generate(root, filters)
            html = result.report_path.read_text(encoding="utf-8")
            self.assertIn("Série histórica descritiva", html)
            self.assertIn("Evolução do SARI", html)
            self.assertIn("<svg", html)
            self.assertIn("SARI", html)
            self.assertIn("Cobertura", html)
            self.assertIn("Matriz histórica das dimensões", html)
            self.assertIn("main{margin:auto;padding:26px}", html)
            self.assertNotIn("main{max-width:1500px", html)

    def test_final_materialization_keeps_consolidated_scoring_labels_in_pt_br(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for audit_id, when in (
                ("AUD-001", "2026-08-05T10:00:00-03:00"),
                ("AUD-002", "2026-09-05T10:00:00-03:00"),
            ):
                db = _make_audit(
                    root,
                    audit_id,
                    when=when,
                    scoring_version="SCORE-GEO-004",
                )
                import sqlite3
                connection = sqlite3.connect(db)
                try:
                    connection.execute(
                        "INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?)",
                        (
                            audit_id,
                            "MOBILE",
                            "ANSWERABILITY",
                            67.5,
                            1.0,
                            "HIGH",
                            "CONSOLIDATED",
                            "SCORE-GEO-004",
                            when,
                        ),
                    )
                    connection.execute(
                        "INSERT INTO findings VALUES (?,?,?,?,?,?,?)",
                        (
                            audit_id,
                            "MOBILE",
                            "MEDIUM",
                            "Answerability",
                            f"{audit_id}-P1",
                            "BR-GEO-040",
                            "OPEN",
                        ),
                    )
                    connection.commit()
                finally:
                    connection.close()

            filters = normalize_filter(
                domains=("example.com",),
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai()):
                result = generate(root, filters)

            html = result.report_path.read_text(encoding="utf-8")
            self.assertIn(">Capacidade de resposta<", html)
            self.assertNotIn(">Answerability<", html)

    def test_identical_request_reuses_cons5_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-05T10:00:00-03:00", scoring_version="SCORE-GEO-004")
            _make_audit(root, "AUD-002", when="2026-09-05T10:00:00-03:00", scoring_version="SCORE-GEO-004")
            filters = normalize_filter(
                domains=("example.com",),
                devices=("MOBILE",),
                urls=("https://example.com/a",),
                specialist_ai=True,
                ai_provider="openai",
            )
            with patch("rasai.consolidation.service.preview_longitudinal_specialist", return_value=_preview_ok()), patch("rasai.consolidation.service.run_longitudinal_ai", return_value=_complete_ai()):
                first = generate(root, filters)
                second = generate(root, filters)
            self.assertFalse(first.reused)
            self.assertTrue(second.reused)
            self.assertEqual(first.report_path, second.report_path)
            manifest = json.loads(second.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["report_format_version"], "CONS-5")
            self.assertEqual(manifest["longitudinal_analysis"]["ai_status"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
