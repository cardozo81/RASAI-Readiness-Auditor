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

    def test_true_never_schedules_implicit_requests(self):
        for value in ("true", "TRUE", "1", "on", "yes"):
            with self.subTest(value=value):
                self.assertTrue(perplexity_enabled({"RASAI_PERPLEXITY_ENABLED": value}))
        state = SimpleNamespace(perplexity_queries=())
        with patch.dict("os.environ", {"RASAI_PERPLEXITY_ENABLED": "true"}), patch(
            "rasai.console_search_intelligence.audit_workspace",
            side_effect=AssertionError("no query must not access workspace"),
        ):
            self.assertEqual(execute_perplexity_for_audit(state, runner=lambda **kw: self.fail("request")), 0)

    def test_invalid_flag_is_fail_closed(self):
        for value in ("invalid", "enabled", "tru", "true; false"):
            with self.subTest(value=value):
                self.assertFalse(perplexity_enabled({"RASAI_PERPLEXITY_ENABLED": value}))
        state = SimpleNamespace(perplexity_queries=("example",))
        with patch.dict("os.environ", {"RASAI_PERPLEXITY_ENABLED": "invalid"}), patch(
            "rasai.console_search_intelligence.audit_workspace",
            side_effect=AssertionError("invalid flag must not access workspace"),
        ):
            self.assertEqual(execute_perplexity_for_audit(state, runner=lambda **kw: self.fail("request")), 0)
        ready, detail = validate_perplexity_readiness(state, {"RASAI_PERPLEXITY_ENABLED": "invalid"})
        self.assertTrue(ready)
        self.assertIn("inválida", detail)

    def test_missing_flag_preserves_legacy_behavior(self):
        self.assertTrue(perplexity_enabled({}))
        self.assertTrue(perplexity_enabled({"PERPLEXITY_API_KEY": "opaque"}))

    def test_explicit_opt_out(self):
        for value in ("false", "FALSE", "0", "off", "no"):
            with self.subTest(value=value):
                self.assertFalse(perplexity_enabled({"RASAI_PERPLEXITY_ENABLED": value}))

    def test_brazil_geography_is_explicit_not_substring_or_provider_guess(self):
        from rasai.console_search_intelligence import _explicit_brazil_scope
        for region in (
            "Porto Alegre, RS, Brazil", "São Paulo, SP, Brasil",
            "Brazil", "BR", "Curitiba, PR, BR",
        ):
            self.assertTrue(_explicit_brazil_scope(region), region)
        for region in ("", "Porto", "Lisboa, Portugal", "Bratislava, Slovakia", "Bristol, UK"):
            self.assertFalse(_explicit_brazil_scope(region), region)

    def test_editor_accepts_only_boolean_values(self):
        from rasai.console_environment import _validate
        self.assertEqual(_validate("RASAI_PERPLEXITY_ENABLED", " TRUE "), "true")
        self.assertEqual(_validate("RASAI_PERPLEXITY_ENABLED", "OFF"), "false")
        with self.assertRaises(ValueError):
            _validate("RASAI_PERPLEXITY_ENABLED", "automatic")

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

    def test_startup_reload_accepts_persisted_activation_without_warning(self):
        """A saved GEO flag must reopen through the same canonical INI allowlist."""
        import os
        import tempfile
        from pathlib import Path
        from rasai.console_settings import load_console_config, save_console_config
        from rasai.console_search_intelligence import SearchConsoleState

        with tempfile.TemporaryDirectory() as root, patch.dict(
            os.environ,
            {"RASAI_PERPLEXITY_ENABLED": "false", "PERPLEXITY_API_KEY": "opaque-secret"},
            clear=True,
        ):
            destination = Path(root) / "rasai-console.ini"
            save_console_config(SearchConsoleState(), destination)
            # Simulate a fresh console process: reload the persisted nonsecret flag.
            os.environ.pop("RASAI_PERPLEXITY_ENABLED")
            restored = SearchConsoleState()
            outcome = load_console_config(restored, destination)
            self.assertFalse(outcome.created)
            self.assertEqual(outcome.warnings, ())
            self.assertEqual(os.environ.get("RASAI_PERPLEXITY_ENABLED"), "false")
            self.assertFalse(perplexity_enabled(os.environ))
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
