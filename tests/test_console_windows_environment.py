from __future__ import annotations

import os
import unittest

from rasai.windows_environment import (
    classify_environment_origin,
    current_matches_persisted,
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

    @unittest.skipIf(os.name == "nt", "non-Windows guard test")
    def test_persistence_is_fail_closed_outside_windows(self) -> None:
        with self.assertRaises(OSError):
            persist_user_environment("OPENAI_API_KEY", "sk-test")
        with self.assertRaises(OSError):
            remove_user_environment("OPENAI_API_KEY")


if __name__ == "__main__":
    unittest.main()
