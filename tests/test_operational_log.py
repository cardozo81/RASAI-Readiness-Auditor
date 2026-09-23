from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rasai.operational_log import append_operational_event, operational_log_path, try_append_operational_event
from rasai.persistence import AuditWorkspace


class OperationalLogTests(unittest.TestCase):
    def test_sensitive_fields_are_redacted_and_configuration_booleans_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = AuditWorkspace(Path(directory) / "AUD-LOG")
            secret = "secret-value-must-not-appear"

            path = append_operational_event(
                workspace,
                "TEST_EVENT",
                api_key=secret,
                authorization=f"Bearer {secret}",
                nested={"access_token": secret, "safe": "visible"},
                pagespeed_api_key_configured=True,
                ordinary="value",
                request_url="https://user:TEST_ONLY_PASSWORD@example.test/path",
                error_message="Authorization: Bearer TEST_ONLY_BEARER",
            )

            self.assertEqual(path, operational_log_path(workspace))
            rendered = path.read_text(encoding="utf-8")
            payload = json.loads(rendered.strip())
            self.assertEqual(payload["event"], "TEST_EVENT")
            self.assertEqual(payload["api_key"], "[REDACTED]")
            self.assertEqual(payload["authorization"], "[REDACTED]")
            self.assertEqual(payload["nested"]["access_token"], "[REDACTED]")
            self.assertEqual(payload["nested"]["safe"], "visible")
            self.assertTrue(payload["pagespeed_api_key_configured"])
            self.assertEqual(payload["ordinary"], "value")
            self.assertNotIn(secret, rendered)
            self.assertNotIn("TEST_ONLY_PASSWORD", rendered)
            self.assertNotIn("TEST_ONLY_BEARER", rendered)

    def test_try_append_is_fail_open_on_log_io_error(self) -> None:
        workspace = AuditWorkspace(Path("unused-audit-root"))
        with patch("rasai.operational_log.append_operational_event", side_effect=OSError("disk unavailable")):
            result = try_append_operational_event(workspace, "TEST_FAILURE")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
