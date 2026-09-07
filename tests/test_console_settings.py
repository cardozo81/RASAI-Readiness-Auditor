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


class ConsoleSettingsTests(unittest.TestCase):
    def test_missing_ini_is_created_with_defaults_and_no_secret(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "super-secret-value", "RASAI_PAGESPEED_API_KEY": "page-secret"},
            clear=False,
        ):
            path = Path(directory) / "rasai-console.ini"
            state = State()
            result = load_console_config(state, path)
            self.assertTrue(result.created)
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn("[console]", text)
            self.assertIn("[synthetic_apdex]", text)
            self.assertNotIn("super-secret-value", text)
            self.assertNotIn("page-secret", text)
            self.assertNotIn("OPENAI_API_KEY", text)
            self.assertNotIn("RASAI_PAGESPEED_API_KEY", text)

    def test_round_trip_persists_console_operational_parameters(self) -> None:
        with TemporaryDirectory() as directory:
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

    def test_fingerprint_changes_only_with_persistable_state(self) -> None:
        state = State()
        first = configuration_fingerprint(state)
        state.project = "mudou"
        self.assertNotEqual(first, configuration_fingerprint(state))
        state.status = "ANALYZING"
        second = configuration_fingerprint(state)
        state.status = "COMPLETE"
        self.assertEqual(second, configuration_fingerprint(state))

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
