from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from rasai.console_artifacts import audit_workspace, report_entrypoint
from rasai.console_config import (
    State,
    apply_environment_defaults,
    build_command,
    environment_summary,
    preflight,
    provider_capabilities,
    validate_env_value,
)
from rasai.console_cost import actual_usage, estimate_exposure, persist_execution_projection
from rasai.console_help import current_cost_summary, environment_help, menu_cost_badges


class InteractiveConsoleTests(unittest.TestCase):
    def test_defaults_are_single_url_mobile_without_ai(self) -> None:
        state = State()
        self.assertEqual(state.input_mode, "url")
        self.assertEqual(state.device, "mobile")
        self.assertEqual(state.ai_provider, "none")
        self.assertFalse(state.content_remediation)
        self.assertFalse(state.web_performance)

    def test_environment_defaults_are_reflected_in_console_state(self) -> None:
        state = State()
        issues = apply_environment_defaults(state, {
            "RASAI_DEVICE_CONTEXT": "desktop",
            "RASAI_AI_CONTENT_REMEDIATION": "true",
            "RASAI_WEB_PERFORMANCE": "true",
            "RASAI_WEB_PERFORMANCE_MAX_PAGES": "4",
            "RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS": "30",
            "RASAI_WEB_PERFORMANCE_FIELD_SOURCE": "pagespeed",
        })
        self.assertEqual(issues, ())
        self.assertEqual(state.device, "desktop")
        self.assertTrue(state.content_remediation)
        self.assertTrue(state.web_performance)
        self.assertEqual(state.web_max_pages, 4)
        self.assertEqual(state.web_timeout, 30.0)
        self.assertEqual(state.field_source, "pagespeed")

    def test_environment_edit_sync_can_be_scoped_without_resetting_menu_choices(self) -> None:
        state = State(device="both", web_performance=True)
        issues = apply_environment_defaults(
            state,
            {"RASAI_WEB_PERFORMANCE_MAX_PAGES": "3"},
            names={"RASAI_WEB_PERFORMANCE_MAX_PAGES"},
        )
        self.assertEqual(issues, ())
        self.assertEqual(state.web_max_pages, 3)
        self.assertEqual(state.device, "both")
        self.assertTrue(state.web_performance)

    def test_only_configured_valid_providers_are_available(self) -> None:
        caps = provider_capabilities({})
        self.assertTrue(caps["none"].available)
        self.assertFalse(caps["openai"].available)
        self.assertFalse(caps["deepseek"].available)
        self.assertFalse(caps["mimo"].available)
        self.assertFalse(caps["auto"].available)
        caps = provider_capabilities({"OPENAI_API_KEY": "sk-test"})
        self.assertTrue(caps["openai"].available)
        self.assertTrue(caps["auto"].available)

    def test_mimo_token_plan_key_is_rejected(self) -> None:
        caps = provider_capabilities({"MIMO_API_KEY": "tp-test"})
        self.assertFalse(caps["mimo"].available)
        with self.assertRaises(ValueError):
            validate_env_value("MIMO_API_KEY", "tp-test")

    def test_invalid_model_reasoning_and_runtime_quarantine_disable_provider(self) -> None:
        caps = provider_capabilities({"OPENAI_API_KEY": "sk-test", "RASAI_OPENAI_MODEL": "bad"})
        self.assertFalse(caps["openai"].available)
        caps = provider_capabilities({"OPENAI_API_KEY": "sk-test", "RASAI_OPENAI_REASONING_EFFORT": "bad"})
        self.assertFalse(caps["openai"].available)
        caps = provider_capabilities({"OPENAI_API_KEY": "sk-test"}, {"openai": "AUTH_ERROR/HTTP 401"})
        self.assertFalse(caps["openai"].available)
        self.assertFalse(caps["auto"].available)

    def test_environment_header_masks_secrets(self) -> None:
        values = environment_summary({"OPENAI_API_KEY": "secret-value", "RASAI_LOG_LEVEL": "DEBUG"})
        rendered = " | ".join(values)
        self.assertIn("OPENAI_API_KEY=[SET]", rendered)
        self.assertNotIn("secret-value", rendered)
        self.assertIn("RASAI_LOG_LEVEL=DEBUG", rendered)
        custom = " | ".join(environment_summary({"RASAI_CUSTOM_API_KEY": "also-secret"}))
        self.assertIn("RASAI_CUSTOM_API_KEY=[SET]", custom)
        self.assertNotIn("also-secret", custom)

    def test_preflight_accepts_single_url(self) -> None:
        state = State(target="https://example.com/path")
        self.assertEqual(preflight(state, {}), ("https://example.com/path",))

    def test_preflight_txt_validates_origin_and_max_pages(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "urls.txt"
            path.write_text("https://example.com/a\nhttps://example.com/b\n", encoding="utf-8")
            state = State(input_mode="file", target=str(path), max_pages=2)
            self.assertEqual(len(preflight(state, {})), 2)
            state.max_pages = 1
            with self.assertRaises(ValueError):
                preflight(state, {})
            path.write_text("https://example.com/a\nhttps://other.example/b\n", encoding="utf-8")
            state.max_pages = 2
            with self.assertRaises(ValueError):
                preflight(state, {})

    def test_preflight_blocks_incompatible_features_before_execution(self) -> None:
        state = State(target="https://example.com", content_remediation=True)
        with self.assertRaises(ValueError):
            preflight(state, {})
        state.content_remediation = False
        state.field_source = "crux"
        self.assertEqual(preflight(state, {}), ("https://example.com/",))
        state.web_performance = True
        with self.assertRaises(ValueError):
            preflight(state, {})

    def test_command_delegates_to_stable_audit_cli(self) -> None:
        state = State(
            target="https://example.com",
            project="Example",
            device="both",
            ai_provider="openai",
            ai_model="gpt-5.6-terra",
            content_remediation=True,
            web_performance=True,
            field_source="none",
        )
        command = build_command(state)
        self.assertIn("audit", command)
        self.assertIn("--device-context", command)
        self.assertIn("both", command)
        self.assertIn("--ai-provider", command)
        self.assertIn("openai", command)
        self.assertIn("--ai-content-remediation", command)
        self.assertIn("--web-performance", command)
        self.assertIn("--web-performance-field-source", command)
        self.assertIn("none", command)

    def test_cost_help_surfaces_external_cost_and_volume_multipliers(self) -> None:
        state = State(
            target="https://example.com",
            max_pages=3,
            ai_provider="openai",
            ai_model="gpt-5.6-terra",
            content_remediation=True,
            device="both",
            web_performance=True,
            web_max_pages=3,
        )
        summary = " ".join(current_cost_summary(state))
        self.assertIn("Exposição financeira potencial", summary)
        self.assertIn("tentativa(s) potenciais", summary)
        self.assertIn("PageSpeed/CrUX", summary)
        badges = menu_cost_badges(state)
        self.assertEqual(badges["ai"], " [CUSTO EXTERNO]")
        self.assertEqual(badges["remediation"], " [CUSTO IA ADICIONAL]")
        self.assertEqual(badges["web"], " [QUOTA EXTERNA]")

    def test_environment_help_has_generic_rules_for_future_provider_variables(self) -> None:
        purpose, cost = environment_help("FUTURE_PROVIDER_API_KEY")
        self.assertIn("Credencial", purpose)
        self.assertIn("CUSTO", cost)
        purpose, cost = environment_help("RASAI_FUTURE_PROVIDER_MODEL")
        self.assertIn("modelo", purpose)
        self.assertIn("preços", cost)
        purpose, cost = environment_help("RASAI_FUTURE_PROVIDER_REASONING_EFFORT")
        self.assertIn("reasoning", purpose)
        self.assertIn("custo", cost)

    def test_artifact_navigation_resolves_only_the_session_audit(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            wanted = root / "AUD-SESSION"
            unrelated = root / "AUD-OTHER"
            (wanted / "report").mkdir(parents=True)
            unrelated.mkdir()
            entrypoint = wanted / "report" / "index.html"
            entrypoint.write_text("<html></html>", encoding="utf-8")
            state = State(audits_root=str(root), audit_id="AUD-SESSION")
            self.assertEqual(audit_workspace(state), wanted.resolve())
            self.assertEqual(report_entrypoint(audit_workspace(state)), entrypoint.resolve())
            state.audit_id = ""
            self.assertIsNone(audit_workspace(state))

    def test_report_entrypoint_requires_canonical_layout(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "AUD-X"
            (workspace / "report").mkdir(parents=True)
            noncanonical = workspace / "report.html"
            noncanonical.write_text("noncanonical", encoding="utf-8")
            self.assertIsNone(report_entrypoint(workspace))
            current = workspace / "report" / "index.html"
            current.write_text("current", encoding="utf-8")
            self.assertEqual(report_entrypoint(workspace), current.resolve())

    def test_exposure_uses_exact_txt_urls_devices_m20_and_m21(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "urls.txt"
            path.write_text(
                "https://example.com/a\nhttps://example.com/b\nhttps://example.com/c\n",
                encoding="utf-8",
            )
            state = State(
                input_mode="file",
                target=str(path),
                max_pages=3,
                device="both",
                ai_provider="openai",
                ai_model="gpt-5.6-terra",
                content_remediation=True,
                web_performance=True,
                web_max_pages=2,
                field_source="auto",
            )
            estimate = estimate_exposure(state)
            self.assertEqual((estimate.min_pages, estimate.max_pages), (3, 3))
            self.assertEqual(estimate.device_contexts, 2)
            self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (6, 24))
            self.assertEqual((estimate.min_web_calls, estimate.max_web_calls), (4, 8))
            self.assertEqual(estimate.level, "ALTO")
            self.assertTrue(any("USD" in line for line in estimate.pricing_lines))

    def test_url_seed_uses_max_pages_as_projection_ceiling(self) -> None:
        state = State(
            target="https://example.com",
            max_pages=5,
            ai_provider="openai",
            ai_model="gpt-5.6-luna",
        )
        estimate = estimate_exposure(state)
        self.assertEqual((estimate.min_pages, estimate.max_pages), (1, 5))
        self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (1, 10))
        self.assertEqual(estimate.level, "MÉDIO")

    def test_web_only_tracks_quota_without_inventing_monetary_cost(self) -> None:
        state = State(
            target="https://example.com",
            max_pages=2,
            ai_provider="none",
            web_performance=True,
            web_max_pages=2,
            field_source="auto",
        )
        estimate = estimate_exposure(state)
        self.assertEqual(estimate.level, "NENHUM")
        self.assertEqual((estimate.min_web_calls, estimate.max_web_calls), (1, 4))

    def test_actual_usage_sums_existing_m18_m20_and_m21_database_telemetry(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "AUD-USAGE"
            workspace.mkdir(parents=True)
            database = workspace / "audit.db"
            connection = sqlite3.connect(database)
            try:
                for table in ("ai_provider_attempts", "content_remediation_attempts"):
                    connection.execute(
                        f"""
                        CREATE TABLE {table} (
                            status TEXT,
                            input_tokens INTEGER,
                            cached_input_tokens INTEGER,
                            output_tokens INTEGER,
                            reasoning_tokens INTEGER,
                            total_tokens INTEGER,
                            estimated_cost REAL,
                            cost_currency TEXT
                        )
                        """
                    )
                connection.execute("CREATE TABLE web_performance_attempts (service TEXT)")
                connection.execute("INSERT INTO ai_provider_attempts VALUES ('SUCCESS',100,20,50,10,150,0.01,'USD')")
                connection.execute("INSERT INTO content_remediation_attempts VALUES ('SUCCESS',200,0,100,20,300,0.02,'USD')")
                connection.execute("INSERT INTO web_performance_attempts VALUES ('PAGESPEED')")
                connection.execute("INSERT INTO web_performance_attempts VALUES ('CRUX')")
                connection.commit()
            finally:
                connection.close()
            usage = actual_usage(workspace)
            self.assertIsNotNone(usage)
            assert usage is not None
            self.assertEqual(usage.ai_attempts, 2)
            self.assertEqual(usage.ai_successes, 2)
            self.assertEqual(usage.input_tokens, 300)
            self.assertEqual(usage.output_tokens, 150)
            self.assertEqual(usage.total_tokens, 450)
            self.assertEqual(usage.costs, (("USD", 0.03),))
            self.assertEqual(usage.web_external_calls, 2)
            self.assertEqual(dict(usage.web_services), {"CRUX": 1, "PAGESPEED": 1})

    def test_projection_persistence_does_not_duplicate_actual_tokens_or_costs(self) -> None:
        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "AUD-PROJECTION"
            workspace.mkdir(parents=True)
            database = workspace / "audit.db"
            connection = sqlite3.connect(database)
            try:
                connection.execute("CREATE TABLE audits (audit_id TEXT PRIMARY KEY)")
                connection.execute("INSERT INTO audits VALUES ('AUD-PROJECTION')")
                connection.commit()
            finally:
                connection.close()
            state = State(
                audits_root=directory,
                audit_id="AUD-PROJECTION",
                target="https://example.com",
                max_pages=2,
                ai_provider="openai",
                ai_model="gpt-5.6-terra",
                web_performance=True,
            )
            estimate = estimate_exposure(state)
            self.assertTrue(
                persist_execution_projection(
                    workspace,
                    state,
                    estimate,
                    projected_at="2026-09-03T23:00:00-03:00",
                    started_at="2026-09-03T23:00:01-03:00",
                    finished_at="2026-09-03T23:01:01-03:00",
                    duration_ms=60000,
                )
            )
            connection = sqlite3.connect(database)
            try:
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(console_execution_projections)").fetchall()
                }
                row = connection.execute(
                    "SELECT audit_id,exposure_level,duration_ms FROM console_execution_projections"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(row, ("AUD-PROJECTION", estimate.level, 60000))
            self.assertNotIn("input_tokens", columns)
            self.assertNotIn("output_tokens", columns)
            self.assertNotIn("estimated_cost", columns)


if __name__ == "__main__":
    unittest.main()