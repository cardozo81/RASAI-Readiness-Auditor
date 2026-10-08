"""Focused opt-out regression coverage for optional Perplexity Search."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rasai.console_search_intelligence import (
    execute_perplexity_for_audit,
    perplexity_enabled,
    validate_perplexity_readiness,
)


class PerplexityActivationFlagTests(unittest.TestCase):
    def test_flag_is_managed_by_canonical_nonsecret_registry(self):
        from rasai import console_provider_environment
        from rasai.console_settings import _known_nonsecret_environment_names
        spec = console_provider_environment.refresh_specs()
        flag = next(item for item in spec if item.name == "RASAI_PERPLEXITY_ENABLED")
        key = next(item for item in spec if item.name == "PERPLEXITY_API_KEY")
        self.assertFalse(flag.sensitive)
        self.assertTrue(key.sensitive)
        self.assertIn("RASAI_PERPLEXITY_ENABLED", _known_nonsecret_environment_names())
        self.assertNotIn("PERPLEXITY_API_KEY", _known_nonsecret_environment_names())

    def test_missing_flag_preserves_legacy_behavior(self):
        self.assertTrue(perplexity_enabled({}))
        self.assertTrue(perplexity_enabled({"PERPLEXITY_API_KEY": "opaque"}))

    def test_explicit_opt_out(self):
        for value in ("false", "FALSE", "0", "off", "no"):
            with self.subTest(value=value):
                self.assertFalse(perplexity_enabled({"RASAI_PERPLEXITY_ENABLED": value}))

    def test_explicit_opt_out_persists_without_secret(self):
        import configparser
        import tempfile
        from pathlib import Path
        from rasai.console_settings import save_console_config
        from rasai.console_search_intelligence import SearchConsoleState

        with tempfile.TemporaryDirectory() as root, patch.dict(
            "os.environ",
            {"RASAI_PERPLEXITY_ENABLED": "false", "PERPLEXITY_API_KEY": "opaque-secret"},
        ):
            destination = Path(root) / "rasai-console.ini"
            save_console_config(SearchConsoleState(), destination)
            parser = configparser.ConfigParser(interpolation=None)
            parser.optionxform = str
            parser.read(destination, encoding="utf-8")
            self.assertEqual(parser.get("environment", "RASAI_PERPLEXITY_ENABLED"), "false")
            self.assertFalse(parser.has_option("environment", "PERPLEXITY_API_KEY"))
            self.assertNotIn("opaque-secret", destination.read_text(encoding="utf-8"))

    def test_disabled_readiness_is_advisory(self):
        state = SimpleNamespace(perplexity_queries=("example",))
        ready, detail = validate_perplexity_readiness(
            state, {"RASAI_PERPLEXITY_ENABLED": "false", "PERPLEXITY_API_KEY": "opaque"}
        )
        self.assertTrue(ready)
        self.assertIn("desabilitada", detail)

    def test_optional_search_failure_never_demotes_audit_status(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "src" / "rasai" /
                  "console_search_intelligence.py").read_text(encoding="utf-8")
        self.assertIn("execute_perplexity_for_audit(state)", source)
        self.assertNotIn(
            "if execute_perplexity_for_audit(state) != 0:\\n                any_limitation = True",
            source,
        )

    def test_disabled_never_reaches_workspace_or_runner(self):
        state = SimpleNamespace(perplexity_queries=("example",))
        with patch.dict("os.environ", {"RASAI_PERPLEXITY_ENABLED": "false"}), patch(
            "rasai.console_search_intelligence.audit_workspace",
            side_effect=AssertionError("workspace accessed despite opt-out"),
        ):
            self.assertEqual(
                execute_perplexity_for_audit(
                    state, runner=lambda *a, **kw: self.fail("request executed")
                ),
                0,
            )
        self.assertEqual(state.perplexity_last_status, "DISABLED_BY_USER")


if __name__ == "__main__":
    unittest.main()
