from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from searchgeo.console_m23 import State, append_m23_command, experience_from_state
from searchgeo.console_settings import load_console_config, save_console_config


class M25ConsoleIntegrationTests(unittest.TestCase):
    def _state(self) -> State:
        return State(
            target="https://example.com",
            synthetic_apdex=True,
            apdex_threshold=1.0,
            apdex_samples=5,
            apdex_max_attempts=7,
            apdex_max_pages=1,
            apdex_timeout=45.0,
            apdex_delay=1.0,
            apdex_concurrency=1,
            apdex_experience=True,
            apdex_experience_samples=10,
            apdex_experience_max_attempts=13,
            apdex_experience_max_pages=1,
            apdex_experience_device_mix="mobile=60,desktop=30,tablet=10",
            apdex_experience_session_mode="cold",
            apdex_experience_kpm="USER_ACTION_DURATION",
            apdex_experience_satisfied=2.0,
            apdex_experience_frustrated=6.0,
            apdex_experience_errors=True,
            apdex_experience_error_scope="first-party",
            apdex_experience_settle=5.0,
            apdex_experience_delay=1.0,
            apdex_experience_concurrency=1,
            apdex_dynatrace_import=False,
        )

    def test_console_command_projects_m25_without_secret(self) -> None:
        state = self._state()
        command = append_m23_command(["python", "-m", "searchgeo", "audit", state.target], state)
        self.assertIn("--synthetic-apdex", command)
        self.assertIn("--apdex-experience", command)
        self.assertIn("mobile=60,desktop=30,tablet=10", command)
        self.assertIn("--apdex-experience-satisfied-seconds", command)
        self.assertIn("--apdex-experience-frustrated-seconds", command)
        self.assertNotIn("DYNATRACE_API_TOKEN", " ".join(command))
        cfg = experience_from_state(state)
        self.assertEqual(cfg.target_samples_per_page, 10)
        self.assertEqual(cfg.device_mix_dict()["TABLET"], 10.0)

    def test_ini_roundtrip_persists_m25_nonsecret_settings_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "searchgeo-console.ini"
            state = self._state()
            state.apdex_dynatrace_import = True
            state.dynatrace_base_url = "https://example.live.dynatrace.com"
            state.dynatrace_application_id = "APPLICATION-123"
            state.apdex_dynatrace_config_json = "dynatrace-export.json"
            with patch.dict(os.environ, {"DYNATRACE_API_TOKEN": "super-secret-token"}, clear=False):
                save_console_config(state, path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("[synthetic_apdex_experience]", text)
            self.assertIn("device_mix = mobile=60,desktop=30,tablet=10", text)
            self.assertIn("dynatrace_application_id = APPLICATION-123", text)
            self.assertNotIn("super-secret-token", text)
            self.assertNotIn("dynatrace_api_token =", text.casefold())

            restored = State()
            result = load_console_config(restored, path)
            self.assertEqual(result.warnings, ())
            self.assertTrue(restored.apdex_experience)
            self.assertEqual(restored.apdex_experience_samples, 10)
            self.assertEqual(restored.apdex_experience_device_mix, "mobile=60,desktop=30,tablet=10")
            self.assertEqual(restored.apdex_experience_satisfied, 2.0)
            self.assertEqual(restored.apdex_experience_frustrated, 6.0)
            self.assertTrue(restored.apdex_dynatrace_import)
            self.assertEqual(restored.dynatrace_application_id, "APPLICATION-123")

    def test_m25_requires_standard_m23_in_console_state(self) -> None:
        state = self._state()
        state.synthetic_apdex = False
        with self.assertRaises(ValueError):
            experience_from_state(state)


if __name__ == "__main__":
    unittest.main()
