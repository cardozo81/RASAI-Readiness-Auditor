from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from rasai import windows_environment
from rasai.windows_environment import (
    activate_persisted_environment,
    classify_environment_origin,
    current_matches_persisted,
    effective_persisted_value,
    persist_user_environment,
    remove_user_environment,
)


class WindowsEnvironmentTests(unittest.TestCase):
    def test_origin_prefers_user_persistence(self) -> None:
        self.assertEqual(classify_environment_origin("key", "key", "machine"), "SO:USER")

    def test_origin_reports_machine_when_no_user_override_exists(self) -> None:
        self.assertEqual(classify_environment_origin("key", None, "key"), "SO:MACHINE")

    def test_session_override_is_explicit_when_user_value_exists(self) -> None:
        self.assertEqual(
            classify_environment_origin("session", "persisted", None),
            "SESSÃO | SO:USER existente",
        )

    def test_persisted_but_removed_from_current_session_is_visible(self) -> None:
        self.assertEqual(
            classify_environment_origin(None, "persisted", None),
            "SO:USER persistida (não ativa nesta sessão)",
        )

    def test_plain_process_value_is_reported_as_session(self) -> None:
        self.assertEqual(classify_environment_origin("session", None, None), "SESSÃO")

    def test_effective_persisted_value_prefers_user_over_machine(self) -> None:
        with (
            patch.object(windows_environment, "user_environment_value", return_value="user-value"),
            patch.object(windows_environment, "machine_environment_value", return_value="machine-value"),
        ):
            self.assertEqual(effective_persisted_value("RASAI_TEST_SECRET"), "user-value")

    def test_activate_persisted_environment_hydrates_missing_process_value(self) -> None:
        name = "RASAI_TEST_PERSISTED_SECRET"
        previous = os.environ.pop(name, None)
        self.addCleanup(self._restore_environment, name, previous)
        with patch.object(windows_environment, "effective_persisted_value", return_value="persisted-value"):
            activated = activate_persisted_environment((name,))
        self.assertEqual(activated, (name,))
        self.assertEqual(os.environ[name], "persisted-value")

    def test_activate_persisted_environment_preserves_explicit_process_value(self) -> None:
        name = "RASAI_TEST_PROCESS_OVERRIDE"
        previous = os.environ.get(name)
        os.environ[name] = "session-value"
        self.addCleanup(self._restore_environment, name, previous)
        with patch.object(windows_environment, "effective_persisted_value", return_value="persisted-value"):
            activated = activate_persisted_environment((name,))
        self.assertEqual(activated, ())
        self.assertEqual(os.environ[name], "session-value")

    def test_activate_persisted_environment_can_explicitly_overwrite(self) -> None:
        name = "RASAI_TEST_PROCESS_OVERWRITE"
        previous = os.environ.get(name)
        os.environ[name] = "session-value"
        self.addCleanup(self._restore_environment, name, previous)
        with patch.object(windows_environment, "effective_persisted_value", return_value="persisted-value"):
            activated = activate_persisted_environment((name,), overwrite=True)
        self.assertEqual(activated, (name,))
        self.assertEqual(os.environ[name], "persisted-value")

    def test_activate_persisted_environment_ignores_blank_duplicate_and_missing_values(self) -> None:
        name = "RASAI_TEST_NO_PERSISTED_SECRET"
        previous = os.environ.pop(name, None)
        self.addCleanup(self._restore_environment, name, previous)
        with patch.object(windows_environment, "effective_persisted_value", return_value=None) as persisted:
            activated = activate_persisted_environment(("", name, name))
        self.assertEqual(activated, ())
        persisted.assert_called_once_with(name)
        self.assertNotIn(name, os.environ)

    @staticmethod
    def _restore_environment(name: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value

    @unittest.skipIf(os.name == "nt", "non-Windows guard test")
    def test_persistence_is_fail_closed_outside_windows(self) -> None:
        with self.assertRaises(OSError):
            persist_user_environment("OPENAI_API_KEY", "sk-test")
        with self.assertRaises(OSError):
            remove_user_environment("OPENAI_API_KEY")


if __name__ == "__main__":
    unittest.main()
