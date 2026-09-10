from __future__ import annotations

from datetime import datetime, timezone
import unittest

from rasai.platform.reporting import _shell
from rasai.time_contract import (
    DEFAULT_PRESENTATION_TIMEZONE,
    format_presentation_timestamp,
    localize_visible_timestamps,
    normalize_timestamp_values,
    parse_timestamp,
    to_utc,
)


class TimeContractTests(unittest.TestCase):
    def test_internal_normalization_is_utc(self) -> None:
        parsed = parse_timestamp("2026-09-10T19:02:15-03:00")
        self.assertEqual(parsed.isoformat(), "2026-09-10T22:02:15+00:00")
        self.assertEqual(to_utc(datetime(2026, 9, 10, 22, 2, 15, tzinfo=timezone.utc)).utcoffset().total_seconds(), 0)

    def test_presentation_defaults_to_sao_paulo(self) -> None:
        self.assertEqual(DEFAULT_PRESENTATION_TIMEZONE, "America/Sao_Paulo")
        self.assertEqual(
            format_presentation_timestamp("2026-09-10T22:02:15Z"),
            "10/09/2026 19:02:15 (America/Sao_Paulo)",
        )

    def test_visible_timestamp_localization_requires_an_instant(self) -> None:
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
        rendered = _shell(
            "Timeline",
            "timeline.html",
            "<p>Evento 2026-09-10T22:02:15+00:00</p><code>2026-09-10T22:02:15+00:00</code>",
        )
        self.assertIn("Evento 10/09/2026 19:02:15 (America/Sao_Paulo)", rendered)
        self.assertIn("<code>2026-09-10T22:02:15+00:00</code>", rendered)


if __name__ == "__main__":
    unittest.main()
