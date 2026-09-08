from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rasai.m11 import _ai_usage_status
from rasai.m23_apdex import _run_status
from rasai.m23_apdex_profiles import MOBILE_STANDARD_PROFILE
from rasai.openai_provider import OpenAIProvider, hardened_semantic_output_schema
from rasai.report_semantics import enhance_report_html
from rasai.scoring import _metadata
from rasai.semantic import SemanticEvidenceInput, SemanticInput


class ConsolidatedBacklogRegressionTests(unittest.TestCase):
    def test_soft_error_rules_share_indexability_group(self) -> None:
        self.assertEqual(_metadata("BR-GEO-016").dimension, "INDEXABILITY")
        self.assertEqual(_metadata("BR-GEO-016").scoring_group, "SOFT_ERROR")
        self.assertEqual(_metadata("BR-GEO-023").dimension, "INDEXABILITY")
        self.assertEqual(_metadata("BR-GEO-023").scoring_group, "SOFT_ERROR")

    def test_semantic_schema_binds_allowed_evidence_ids(self) -> None:
        schema = hardened_semantic_output_schema(frozenset({"EV-1", "EV-2"}))
        assessment_ids = schema["properties"]["assessments"]["items"]["properties"]["evidence_ids"]["items"]["enum"]
        entity_ids = schema["properties"]["entities"]["items"]["properties"]["evidence_ids"]["items"]["enum"]
        self.assertEqual(assessment_ids, ["EV-1", "EV-2"])
        self.assertEqual(entity_ids, ["EV-1", "EV-2"])

    def test_openai_request_schema_is_bound_to_context_evidence(self) -> None:
        semantic = SemanticInput(
            snapshot_id="SNP-1",
            page_url="https://example.test/",
            title="Example",
            main_content="Evidence",
            structured_data=None,
            primary_language="pt-BR",
            market="BR",
            evidence=(SemanticEvidenceInput("EV-ONLY", "TEXT_EXCERPT", "test", {"text": "Evidence"}),),
        )
        provider = OpenAIProvider(model="gpt-5.6-luna", api_key="x")
        payload = provider._request_payload(semantic)
        ids = payload["text"]["format"]["schema"]["properties"]["assessments"]["items"]["properties"]["evidence_ids"]["items"]["enum"]
        self.assertEqual(ids, ["EV-ONLY"])

    def test_ai_usage_is_provider_neutral_and_distinguishes_rejection(self) -> None:
        self.assertEqual(_ai_usage_status([{"provider": "DEEPSEEK"}]), "SIM")
        self.assertEqual(_ai_usage_status([{"provider": "MIMO"}, {"provider": "UNAVAILABLE"}]), "SIM")
        self.assertEqual(_ai_usage_status([{"provider": "UNAVAILABLE"}]), "TENTATIVA SEM SUCESSO")
        self.assertEqual(_ai_usage_status([{"provider": "DETERMINISTIC_BASELINE"}]), "NÃO")

    def test_apdex_small_group_is_not_invalid_sampling(self) -> None:
        self.assertEqual(
            _run_status(
                context_count=1, final_contexts=0, target_met_contexts=1,
                small_groups=1, valid_total=20, invalid_total=0,
            ),
            ("PARTIAL", "SMALL_GROUP_BELOW_NORMAL_MINIMUM"),
        )
        self.assertEqual(
            _run_status(
                context_count=1, final_contexts=0, target_met_contexts=0,
                small_groups=1, valid_total=15, invalid_total=5,
            ),
            ("PARTIAL", "ONE_OR_MORE_CONTEXTS_INCOMPLETE_OR_INVALID"),
        )

    def test_synthetic_profile_declares_user_agent_provenance(self) -> None:
        data = MOBILE_STANDARD_PROFILE.as_dict()
        self.assertEqual(data["user_agent_role"], "PROFILE_TEMPLATE_ONLY_NOT_EFFECTIVE_RUNTIME_VALUE")
        self.assertEqual(data["effective_user_agent_source"], "PLAYWRIGHT_DEVICE_DESCRIPTOR_ALIGNED_TO_RUNTIME_BROWSER")
        self.assertFalse(data["effective_user_agent_persisted"])

    def test_web_performance_metadata_is_not_scored_as_bad(self) -> None:
        html = """<html><head><style></style></head><body>
        <div class='metric'><small>Performance</small><strong>42/100</strong></div>
        <div class='metric'><small>Escopo</small><strong>URL</strong></div>
        <div class='metric'><small>Fonte</small><strong>PAGESPEED_CRUX</strong></div>
        </body></html>"""
        with TemporaryDirectory() as tmp:
            output = enhance_report_html(html, page_name="web-performance.html", report_dir=Path(tmp))
        self.assertEqual(output.count("Ruim (0-49)"), 1)
        self.assertNotIn("<small>Escopo</small><strong>URL</strong><span class='result-tag bad'>", output)
        self.assertNotIn("<small>Fonte</small><strong>PAGESPEED_CRUX</strong><span class='result-tag bad'>", output)

    def test_current_runtime_files_do_not_claim_score_geo_002(self) -> None:
        selected = [
            "src/rasai/m20_reporting.py", "src/rasai/m23_reporting.py",
            "src/rasai/m24_reporting.py", "src/rasai/m25_reporting.py",
            "src/rasai/external_metrics_integrity.py", "src/rasai/cli_extensions.py",
        ]
        root = Path(__file__).resolve().parents[1]
        for relative in selected:
            with self.subTest(relative=relative):
                self.assertNotIn("SCORE-GEO-002", (root / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
