from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

from rasai.console_m23 import State
from rasai.console_session import get_config_path, is_dirty, mark_dirty, set_config_path
from rasai.console_settings import (
    configuration_fingerprint,
    load_console_config,
    save_console_config,
)
from rasai.time_contract import (
    PRESENTATION_TIMEZONE_ENV,
    configured_presentation_timezone,
)


class ConsoleSettingsTests(unittest.TestCase):
    def test_missing_ini_is_created_with_defaults_and_no_secret(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "super-secret-value", "RASAI_PAGESPEED_API_KEY": "page-secret"},
            clear=False,
        ):
            os.environ.pop(PRESENTATION_TIMEZONE_ENV, None)
            path = Path(directory) / "rasai-console.ini"
            state = State()
            result = load_console_config(state, path)
            self.assertTrue(result.created)
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn("[console]", text)
            self.assertIn("[presentation]", text)
            self.assertIn("timezone = America/Sao_Paulo", text)
            self.assertIn("[synthetic_apdex]", text)
            self.assertNotIn("super-secret-value", text)
            self.assertNotIn("page-secret", text)
            self.assertNotIn("OPENAI_API_KEY", text)
            self.assertNotIn("RASAI_PAGESPEED_API_KEY", text)

    def test_round_trip_persists_console_operational_parameters(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=False):
            os.environ[PRESENTATION_TIMEZONE_ENV] = "Europe/London"
            path = Path(directory) / "settings.ini"
            state = State()
            state.target = "https://example.test/"
            state.project = "Projeto"
            state.device = "both"
            state.ai_provider = "openai"
            state.ai_model = "gpt-5.6-luna"
            state.ai_reasoning = "NONE"
            state.ai_timeout = 210.0
            state.content_remediation = True
            state.web_performance = True
            state.web_timeout = 150.0
            state.synthetic_apdex = True
            state.apdex_threshold = 2.0
            state.apdex_samples = 5
            state.apdex_max_attempts = 7
            save_console_config(state, path)

            os.environ.pop(PRESENTATION_TIMEZONE_ENV, None)
            restored = State()
            result = load_console_config(restored, path)
            self.assertFalse(result.created)
            self.assertEqual(result.warnings, ())
            self.assertEqual(restored.target, state.target)
            self.assertEqual(restored.project, state.project)
            self.assertEqual(restored.device, "both")
            self.assertEqual(restored.ai_provider, "openai")
            self.assertEqual(restored.ai_model, "gpt-5.6-luna")
            self.assertEqual(restored.ai_reasoning, "NONE")
            self.assertEqual(restored.ai_timeout, 210.0)
            self.assertTrue(restored.content_remediation)
            self.assertTrue(restored.web_performance)
            self.assertEqual(restored.web_timeout, 150.0)
            self.assertTrue(restored.synthetic_apdex)
            self.assertEqual(restored.apdex_threshold, 2.0)
            self.assertEqual(restored.apdex_samples, 5)
            self.assertEqual(restored.apdex_max_attempts, 7)
            self.assertEqual(configured_presentation_timezone(), "Europe/London")
            text = path.read_text(encoding="utf-8")
            self.assertIn("[presentation]", text)
            self.assertIn("timezone = Europe/London", text)

    def test_environment_override_wins_over_ini_timezone(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=False):
            path = Path(directory) / "settings.ini"
            path.write_text(
                "[console]\nconfig_version = 4\n\n[presentation]\ntimezone = America/Sao_Paulo\n",
                encoding="utf-8",
            )
            os.environ[PRESENTATION_TIMEZONE_ENV] = "Asia/Tokyo"
            result = load_console_config(State(), path)
            self.assertEqual(result.warnings, ())
            self.assertEqual(configured_presentation_timezone(), "Asia/Tokyo")

    def test_invalid_timezone_in_ini_warns_and_keeps_safe_default(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=False):
            os.environ.pop(PRESENTATION_TIMEZONE_ENV, None)
            path = Path(directory) / "settings.ini"
            path.write_text(
                "[console]\nconfig_version = 4\n\n[presentation]\ntimezone = -03:00\n",
                encoding="utf-8",
            )
            result = load_console_config(State(), path)
            self.assertTrue(any("presentation.timezone" in warning for warning in result.warnings))
            self.assertEqual(configured_presentation_timezone(), "America/Sao_Paulo")

    def test_fingerprint_changes_only_with_persistable_state(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(PRESENTATION_TIMEZONE_ENV, None)
            state = State()
            first = configuration_fingerprint(state)
            state.project = "mudou"
            self.assertNotEqual(first, configuration_fingerprint(state))
            state.status = "ANALYZING"
            second = configuration_fingerprint(state)
            state.status = "COMPLETE"
            self.assertEqual(second, configuration_fingerprint(state))
            os.environ[PRESENTATION_TIMEZONE_ENV] = "UTC"
            self.assertNotEqual(second, configuration_fingerprint(state))

    def test_session_dirty_metadata_is_independent_from_state_schema(self) -> None:
        state = State()
        path = Path("settings.ini")
        set_config_path(state, path)
        self.assertEqual(get_config_path(state), path)
        self.assertFalse(is_dirty(state))
        mark_dirty(state)
        self.assertTrue(is_dirty(state))
        mark_dirty(state, False)
        self.assertFalse(is_dirty(state))


if __name__ == "__main__":
    unittest.main()
