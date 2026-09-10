from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rasai.console_search_intelligence import (
    SearchConsoleState,
    build_search_argv,
    execute_search_for_audit,
    parse_search_terms,
    validate_search_readiness,
)
from rasai.console_settings import _state_values
from rasai.search_intelligence.config import (
    SERPAPI_KEY_ENV,
    SERP_MAX_DEPTH_ENV,
    SERP_MAX_QUERIES_ENV,
    SERP_MAX_REQUESTS_ENV,
    SERP_MODE_ENV,
    SERP_PROVIDER_ENV,
)


class ConsoleSearchIntelligenceTests(unittest.TestCase):
    def _live_env(self) -> dict[str, str]:
        return {
            SERP_MODE_ENV: "live",
            SERP_PROVIDER_ENV: "serpapi",
            SERPAPI_KEY_ENV: "test-serp-key",
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

    def test_readiness_requires_live_key_when_terms_exist(self) -> None:
        state = SimpleNamespace(
            search_queries=("seguro auto",),
            search_depth=20,
            search_device="mobile",
        )
        env = self._live_env()
        env.pop(SERPAPI_KEY_ENV)
        ready, reason = validate_search_readiness(state, env)
        self.assertFalse(ready)
        self.assertIn(SERPAPI_KEY_ENV, reason)

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

    def test_execute_search_materializes_report_and_keeps_audit_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "AUD-TEST"
            (workspace / "report").mkdir(parents=True)
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
                report = workspace / "report" / "search-intelligence.html"
                report.write_text("<html>ok</html>", encoding="utf-8")
                return 0

            with patch.dict(os.environ, self._live_env(), clear=False):
                code = execute_search_for_audit(
                    state,
                    target_url="https://loja.example.com.br/",
                    runner=runner,
                )

            self.assertEqual(code, 0)
            self.assertEqual(state.search_last_status, "COMPLETE")
            self.assertTrue(Path(state.search_last_report).is_file())
            self.assertEqual(captured[captured.index("--domain") + 1], "loja.example.com.br")
            captured_workspace = captured[captured.index("--audit-workspace") + 1]
            self.assertEqual(
                os.path.normcase(os.path.realpath(captured_workspace)),
                os.path.normcase(os.path.realpath(workspace)),
            )

    def test_search_failure_is_recorded_as_optional_limitation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "AUD-TEST"
            (workspace / "report").mkdir(parents=True)
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


if __name__ == "__main__":
    unittest.main()
