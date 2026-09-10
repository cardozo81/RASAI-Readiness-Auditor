from __future__ import annotations

from datetime import datetime, timezone
import os
import unittest
from unittest.mock import patch

from rasai.platform.reporting import _shell
from rasai.time_contract import (
    DEFAULT_PRESENTATION_TIMEZONE,
    PRESENTATION_TIMEZONE_ENV,
    configured_presentation_timezone,
    format_presentation_timestamp,
    localize_visible_timestamps,
    normalize_timestamp_values,
    parse_timestamp,
    timezone_offset_label,
    to_utc,
    validate_presentation_timezone,
)


class TimeContractTests(unittest.TestCase):
    def test_internal_normalization_is_utc(self) -> None:
        parsed = parse_timestamp("2026-09-10T19:02:15-03:00")
        self.assertEqual(parsed.isoformat(), "2026-09-10T22:02:15+00:00")
        self.assertEqual(to_utc(datetime(2026, 9, 10, 22, 2, 15, tzinfo=timezone.utc)).utcoffset().total_seconds(), 0)

    def test_presentation_defaults_to_sao_paulo(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(PRESENTATION_TIMEZONE_ENV, None)
            self.assertEqual(DEFAULT_PRESENTATION_TIMEZONE, "America/Sao_Paulo")
            self.assertEqual(configured_presentation_timezone(), "America/Sao_Paulo")
            self.assertEqual(
                format_presentation_timestamp("2026-09-10T22:02:15Z"),
                "10/09/2026 19:02:15 (America/Sao_Paulo)",
            )

    def test_environment_override_changes_only_presentation(self) -> None:
        with patch.dict(os.environ, {PRESENTATION_TIMEZONE_ENV: "Asia/Tokyo"}, clear=False):
            self.assertEqual(configured_presentation_timezone(), "Asia/Tokyo")
            self.assertEqual(
                format_presentation_timestamp("2026-09-10T22:02:15Z"),
                "11/09/2026 07:02:15 (Asia/Tokyo)",
            )
            self.assertEqual(
                parse_timestamp("2026-09-10T19:02:15-03:00").isoformat(),
                "2026-09-10T22:02:15+00:00",
            )

    def test_timezone_requires_iana_identifier_not_numeric_offset(self) -> None:
        self.assertEqual(validate_presentation_timezone("UTC"), "UTC")
        self.assertEqual(validate_presentation_timezone("America/Sao_Paulo"), "America/Sao_Paulo")
        with self.assertRaises(ValueError):
            validate_presentation_timezone("-03:00")
        fixed = datetime(2026, 9, 10, 22, 0, tzinfo=timezone.utc)
        self.assertEqual(
            timezone_offset_label("America/Sao_Paulo", instant=fixed),
            "UTC-03:00",
        )

    def test_visible_timestamp_localization_requires_an_instant(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(PRESENTATION_TIMEZONE_ENV, None)
            text = "Criado 2026-09-10T22:02:15+00:00; data de referência 2026-09-10."
            rendered = localize_visible_timestamps(text)
            self.assertIn("10/09/2026 19:02:15 (America/Sao_Paulo)", rendered)
            self.assertIn("data de referência 2026-09-10", rendered)

    def test_derivative_payloads_are_recursively_normalized_to_utc(self) -> None:
        payload = {
            "generated_at": "2026-09-10T19:02:15-03:00",
            "source": [{"event_time": "2026-09-10T22:02:15Z", "date": "2026-09-10"}],
            "note": "executado em 2026-09-10T19:02:15-03:00",
        }
        normalized = normalize_timestamp_values(payload)
        self.assertEqual(normalized["generated_at"], "2026-09-10T22:02:15+00:00")
        self.assertEqual(normalized["source"][0]["event_time"], "2026-09-10T22:02:15+00:00")
        self.assertEqual(normalized["source"][0]["date"], "2026-09-10")
        self.assertEqual(normalized["note"], payload["note"])

    def test_product_platform_shell_uses_presentation_timezone(self) -> None:
        with patch.dict(os.environ, {PRESENTATION_TIMEZONE_ENV: "UTC"}, clear=False):
            rendered = _shell(
                "Timeline",
                "timeline.html",
                "<p>Evento 2026-09-10T22:02:15+00:00</p><code>2026-09-10T22:02:15+00:00</code>",
            )
        self.assertIn("Evento 10/09/2026 22:02:15 (UTC)", rendered)
        self.assertIn("<code>2026-09-10T22:02:15+00:00</code>", rendered)


if __name__ == "__main__":
    unittest.main()
