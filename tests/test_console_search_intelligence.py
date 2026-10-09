from __future__ import annotations

import os
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from rasai.console_search_intelligence import (
    SearchConsoleState,
    install,
    build_search_argv,
    execute_search_for_audit,
    execute_perplexity_for_audit,
    parse_search_terms,
    validate_perplexity_readiness,
    validate_search_readiness,
)
from rasai.console_settings import _state_values
from rasai.search_intelligence.config import (
    SCRAPINGDOG_KEY_ENV,
    SERPAPI_KEY_ENV,
    SERP_MAX_DEPTH_ENV,
    SERP_MAX_QUERIES_ENV,
    SERP_MAX_REQUESTS_ENV,
    SERP_MODE_ENV,
    SERP_PROVIDER_ENV,
    ZENSERP_KEY_ENV,
)


class ConsoleSearchIntelligenceTests(unittest.TestCase):
    def _live_env(self) -> dict[str, str]:
        return {
            SERP_MODE_ENV: "live",
            SERP_PROVIDER_ENV: "serpapi",
            SERPAPI_KEY_ENV: "opaque-serp-value",
            SERP_MAX_QUERIES_ENV: "10",
            SERP_MAX_REQUESTS_ENV: "10",
            SERP_MAX_DEPTH_ENV: "20",
        }

    def test_terms_are_execution_input_and_are_deduplicated(self) -> None:
        self.assertEqual(
            parse_search_terms("seguro auto; seguro residencial\nSeguro Auto ;  "),
            ("seguro auto", "seguro residencial"),
        )

    def test_search_terms_are_not_serialized_into_console_ini_state(self) -> None:
        state = SearchConsoleState(
            search_queries=("seguro auto", "seguro residencial"),
            search_depth=20,
        )
        serialized = repr(_state_values(state))
        self.assertNotIn("seguro auto", serialized)
        self.assertNotIn("seguro residencial", serialized)
        self.assertNotIn("search_queries", serialized)

    def test_readiness_requires_selected_live_provider_key_when_terms_exist(self) -> None:
        state = SimpleNamespace(
            search_queries=("seguro auto",),
            search_depth=20,
            search_device="mobile",
        )
        env = self._live_env()
        env.pop(SERPAPI_KEY_ENV)
        ready, reason = validate_search_readiness(state, env)
        self.assertTrue(ready, reason)
        self.assertIn("Search Intelligence", reason)
        self.assertNotIn(SERPAPI_KEY_ENV, reason)

    def test_readiness_uses_zenserp_registry_key_without_compat_patch(self) -> None:
        state = SimpleNamespace(
            search_queries=("seguro auto",),
            search_depth=10,
            search_device="desktop",
        )
        env = self._live_env()
        env[SERP_PROVIDER_ENV] = "zenserp"
        env.pop(SERPAPI_KEY_ENV)
        env[ZENSERP_KEY_ENV] = "opaque-zen-value"
        ready, reason = validate_search_readiness(state, env)
        self.assertTrue(ready, reason)
        argv = build_search_argv(
            state,
            workspace=Path("audits/AUD-TEST"),
            target_url="https://example.com/",
            env=env,
        )
        self.assertEqual("google", argv[argv.index("--engine") + 1])

    def test_readiness_uses_scrapingdog_registry_key_without_compat_patch(self) -> None:
        state = SimpleNamespace(
            search_queries=("seguro auto",),
            search_depth=10,
            search_device="mobile",
        )
        env = self._live_env()
        env[SERP_PROVIDER_ENV] = "scrapingdog"
        env.pop(SERPAPI_KEY_ENV)
        env[SCRAPINGDOG_KEY_ENV] = "opaque-dog-value"
        ready, reason = validate_search_readiness(state, env)
        self.assertTrue(ready, reason)

    def test_readiness_enforces_query_limit(self) -> None:
        state = SimpleNamespace(
            search_queries=("um", "dois"),
            search_depth=10,
            search_device="mobile",
        )
        env = self._live_env()
        env[SERP_MAX_QUERIES_ENV] = "1"
        ready, reason = validate_search_readiness(state, env)
        self.assertFalse(ready)
        self.assertIn("excedem", reason)

    def test_build_argv_derives_domain_and_audit_context(self) -> None:
        state = SimpleNamespace(
            search_queries=("seguro auto", "seguro residencial"),
            search_depth=20,
            search_device="mobile",
            search_region="Porto Alegre, RS, Brazil",
            search_competitive=True,
            market="BR",
            language="pt-BR",
        )
        workspace = Path("audits/AUD-TEST")
        argv = build_search_argv(
            state,
            workspace=workspace,
            target_url="https://loja.example.com.br/produto",
            env=self._live_env(),
        )
        self.assertEqual(argv[:2], ["seguro auto", "seguro residencial"])
        self.assertEqual(argv[argv.index("--domain") + 1], "loja.example.com.br")
        self.assertEqual(argv[argv.index("--engine") + 1], "google")
        self.assertEqual(argv[argv.index("--audit-workspace") + 1], str(workspace))
        self.assertEqual(argv[argv.index("--region") + 1], "Porto Alegre, RS, Brazil")
        self.assertIn("--competitive", argv)

    def test_execute_search_keeps_audit_binding_without_non_catalog_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "AUD-TEST"
            workspace.mkdir(parents=True)
            state = SearchConsoleState(
                audits_root=str(root),
                audit_id="AUD-TEST",
                market="BR",
                language="pt-BR",
                search_queries=("seguro auto",),
                search_depth=10,
                search_device="mobile",
                search_competitive=True,
            )
            captured: list[str] = []

            def runner(argv):
                captured.extend(argv or ())
                return 0

            with patch.dict(os.environ, self._live_env(), clear=False):
                code = execute_search_for_audit(
                    state,
                    target_url="https://loja.example.com.br/",
                    runner=runner,
                )

            self.assertEqual(code, 0)
            self.assertEqual(state.search_last_status, "COMPLETE")
            self.assertEqual(state.search_last_report, "")
            self.assertFalse((workspace / "report").exists())
            self.assertEqual(captured[captured.index("--domain") + 1], "loja.example.com.br")
            captured_workspace = captured[captured.index("--audit-workspace") + 1]
            self.assertEqual(
                os.path.normcase(os.path.realpath(captured_workspace)),
                os.path.normcase(os.path.realpath(workspace)),
            )

    def test_perplexity_readiness_keeps_missing_key_as_external_limitation(self) -> None:
        state = SimpleNamespace(
            perplexity_queries=("rasai readiness",),
            perplexity_search_type="web",
        )
        ready, reason = validate_perplexity_readiness(state, {})
        self.assertTrue(ready, reason)
        self.assertIn("não configurada", reason)
        self.assertNotIn("secret", reason.casefold())

    def test_perplexity_readiness_rejects_invalid_type_and_query_overflow(self) -> None:
        invalid_type = SimpleNamespace(
            perplexity_queries=("rasai readiness",),
            perplexity_search_type="invalid",
        )
        ready, reason = validate_perplexity_readiness(invalid_type, {"PERPLEXITY_API_KEY": "secret"})
        self.assertFalse(ready)
        self.assertIn("search_type inválido", reason)

        overflow = SimpleNamespace(
            perplexity_queries=("1", "2", "3", "4", "5", "6"),
            perplexity_search_type="web",
        )
        ready, reason = validate_perplexity_readiness(overflow, {"PERPLEXITY_API_KEY": "secret"})
        self.assertFalse(ready)
        self.assertIn("excede 5 queries", reason)

    def test_perplexity_execution_is_independent_from_serp_and_humanized(self) -> None:
        import sqlite3

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "AUD-TEST"
            workspace.mkdir(parents=True)
            (workspace / "artifacts").mkdir()
            connection = sqlite3.connect(workspace / "audit.db")
            try:
                connection.execute("CREATE TABLE audits(audit_id TEXT PRIMARY KEY)")
                connection.execute("INSERT INTO audits VALUES ('AUD-TEST')")
                connection.commit()
            finally:
                connection.close()

            state = SearchConsoleState(
                audits_root=str(root),
                audit_id="AUD-TEST",
                search_queries=(),
                perplexity_queries=("rasai readiness", "search readiness"),
                perplexity_search_type="fast",
            )

            def runner(workspace_obj, **kwargs):
                self.assertEqual(
                    os.path.normcase(os.path.realpath(workspace_obj.root)),
                    os.path.normcase(os.path.realpath(workspace)),
                )
                self.assertEqual(kwargs["audit_id"], "AUD-TEST")
                self.assertEqual(
                    kwargs["query"],
                    ("rasai readiness", "search readiness"),
                )
                self.assertEqual(kwargs["search_type"], "fast")
                return SimpleNamespace(
                    status="SUCCESS",
                    search_type="fast",
                    queries=kwargs["query"],
                    native_usage=(SimpleNamespace(quantity=1.0),),
                    sources=(SimpleNamespace(url="https://example.test/"),),
                    pricing=SimpleNamespace(estimated_cost=0.001, currency="USD"),
                )

            code = execute_perplexity_for_audit(state, runner=runner)

            self.assertEqual(code, 0)
            self.assertEqual(state.perplexity_last_status, "COMPLETE")
            self.assertIn("Perplexity Search API - pesquisa externa", state.perplexity_last_detail)
            self.assertIn("requests=1.0", state.perplexity_last_detail)
            self.assertEqual(state.search_queries, ())


    def test_cumulative_usage_reprojects_persisted_search_success(self) -> None:
        from rasai import console_governed_search_runtime as governed

        module = ModuleType("search_usage_projection_console")
        module._menu = lambda state: "V"
        module._configure = lambda state, choice: None
        module._execution_readiness = lambda state: (True, "ok")
        module.run_audit_from_console = lambda state: 0
        module._render_actual_usage = lambda state: print("BASE-USAGE")

        original_installed = getattr(module, "_search_intelligence_console_installed", False)
        with patch.object(
            governed,
            "_project_result",
            side_effect=lambda state: setattr(state, "search_last_status", "COMPLETE"),
        ):
            install(module)
            state = SearchConsoleState(
                audit_id="AUD-TEST",
                audits_root="audits",
                search_queries=("seguro auto",),
                search_last_status="NOT_REQUESTED",
            )
            with redirect_stdout(StringIO()) as output:
                module._render_actual_usage(state)

        rendered = output.getvalue()
        self.assertIn("Search Intelligence   : COMPLETE | termos=1", rendered)
        self.assertNotIn("NOT_REQUESTED | termos=1", rendered)
        if not original_installed and hasattr(module, "_search_intelligence_console_installed"):
            delattr(module, "_search_intelligence_console_installed")


    def test_search_failure_is_recorded_as_optional_limitation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "AUD-TEST"
            workspace.mkdir(parents=True)
            state = SearchConsoleState(
                audits_root=str(root),
                audit_id="AUD-TEST",
                search_queries=("seguro auto",),
                search_depth=10,
                search_device="mobile",
            )

            def runner(_argv):
                print("provider unavailable")
                return 1

            with patch.dict(os.environ, self._live_env(), clear=False):
                code = execute_search_for_audit(
                    state,
                    target_url="https://loja.example.com.br/",
                    runner=runner,
                )

            self.assertEqual(code, 1)
            self.assertEqual(state.search_last_status, "COMPLETE_WITH_LIMITATIONS")
            self.assertIn("provider unavailable", state.search_last_detail)
            self.assertEqual(state.search_last_report, "")



class PerplexityExplicitCopy318Tests(unittest.TestCase):
    """#318: no SERP inheritance or charge without two operator choices."""

    def test_copy_is_explicit_and_follows_a_second_charge_confirmation(self):
        from rasai.console_search_intelligence import configure_perplexity_search
        state = SearchConsoleState(
            search_queries=("seguro de vida", "seguro residencial"),
            perplexity_queries=(),
        )
        with patch.dict(os.environ, {
            "RASAI_PERPLEXITY_ENABLED": "true",
            "PERPLEXITY_API_KEY": "TEST_OPAQUE_KEY",
        }, clear=False), patch(
            "builtins.input", side_effect=("s", "s", "", "fast", "sim"),
        ) as answers, redirect_stdout(StringIO()) as output:
            configure_perplexity_search(state)
        self.assertEqual(answers.call_count, 5)
        self.assertEqual(
            state.perplexity_queries, ("seguro de vida", "seguro residencial")
        )
        self.assertEqual(state.perplexity_search_type, "fast")
        self.assertEqual(state.perplexity_last_status, "PENDING")
        rendered = output.getvalue()
        self.assertIn("Termos SERP NÃO são herdados automaticamente", rendered)
        self.assertIn("custo exato: N/D", rendered)
        self.assertNotIn("TEST_OPAQUE_KEY", rendered)

    def test_serp_declined_and_operator_types_independent_queries(self):
        from rasai.console_search_intelligence import configure_perplexity_search
        state = SearchConsoleState(
            search_queries=("serp-exclusive",),
            perplexity_queries=(),
        )
        with patch("builtins.input", side_effect=(
            "s", "n", "perplexity-exclusive", "", "s",
        )), redirect_stdout(StringIO()):
            configure_perplexity_search(state)
        self.assertEqual(state.perplexity_queries, ("perplexity-exclusive",))
        self.assertNotIn("serp-exclusive", state.perplexity_queries)
        self.assertEqual(state.perplexity_last_status, "PENDING")

    def test_missing_final_authorization_clears_previous_draft(self):
        from rasai.console_search_intelligence import configure_perplexity_search
        state = SearchConsoleState(
            search_queries=(),
            perplexity_queries=("previous-consent-does-not-carry",),
            perplexity_search_type="web",
        )
        with patch("builtins.input", side_effect=(
            "s", "", "", "n",
        )), redirect_stdout(StringIO()):
            configure_perplexity_search(state)
        self.assertEqual(state.perplexity_queries, ())
        self.assertEqual(state.perplexity_last_status, "NOT_REQUESTED")
        self.assertIn("zero requisição", state.perplexity_last_detail)

    def test_more_than_five_serp_terms_never_copy_partially(self):
        from rasai.console_search_intelligence import configure_perplexity_search
        state = SearchConsoleState(
            search_queries=("q1", "q2", "q3", "q4", "q5", "q6"),
            perplexity_queries=(),
        )
        with patch("builtins.input", side_effect=("s", "s")) as answers, (
            redirect_stdout(StringIO())
        ):
            configure_perplexity_search(state)
        self.assertEqual(answers.call_count, 2)
        self.assertEqual(state.perplexity_queries, ())
        self.assertIn("Não copiar parcialmente", state.error)
        self.assertEqual(state.perplexity_last_status, "NOT_REQUESTED")

    def test_pre_audit_menu_distinguishes_enabled_key_and_request(self):
        from rasai.console_search_intelligence import _render_menu_extension
        empty = SearchConsoleState(
            search_queries=("serp-stays-serp",), perplexity_queries=(),
        )
        with patch.dict(os.environ, {
            "RASAI_PERPLEXITY_ENABLED": "true",
            "PERPLEXITY_API_KEY": "OPAQUE_NEVER_PRINT",
        }, clear=False), redirect_stdout(StringIO()) as output:
            _render_menu_extension(empty)
        rendered = output.getvalue()
        self.assertIn("U. Perplexity externa", rendered)
        self.assertIn("integração HABILITADA", rendered)
        self.assertIn("não solicitado", rendered)
        self.assertIn("credencial configurada", rendered)
        self.assertIn("não solicita pesquisa externa", rendered)
        self.assertNotIn("OPAQUE_NEVER_PRINT", rendered)
        self.assertNotIn("serp-stays-serp | integração", rendered)

        with patch.dict(os.environ, {
            "RASAI_PERPLEXITY_ENABLED": "false",
            "PERPLEXITY_API_KEY": "",
        }, clear=False), redirect_stdout(StringIO()) as off:
            _render_menu_extension(empty)
        self.assertIn("integração DESABILITADA", off.getvalue())
        self.assertIn("credencial não configurada", off.getvalue())

    def test_copy_refusal_does_not_trigger_perplexity_transport(self):
        from rasai.console_search_intelligence import configure_perplexity_search
        state = SearchConsoleState(
            search_queries=("serp-query",), perplexity_queries=(),
        )
        with patch("builtins.input", side_effect=("n",)) as answers, (
            redirect_stdout(StringIO())
        ), patch("rasai.console_search_intelligence.execute_perplexity_search") as provider:
            configure_perplexity_search(state)
        provider.assert_not_called()
        self.assertEqual(answers.call_count, 1)
        self.assertEqual(state.perplexity_last_status, "NOT_REQUESTED")
        self.assertEqual(state.perplexity_queries, ())


if __name__ == "__main__":
    unittest.main()
