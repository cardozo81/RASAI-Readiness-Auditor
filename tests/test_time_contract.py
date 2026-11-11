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



    def test_frozen_audit_timezone_overrides_host_environment(self) -> None:
        from rasai.catalog_report_contract import page_by_filename
        from rasai.catalog_report_presentation import _shell as catalog_shell
        from rasai.time_contract import presentation_timezone_for_audit
        config = {"settings": {"presentation": {"timezone": "UTC"},
                               "environment": {"RASAI_PRESENTATION_TIMEZONE": "UTC"}}}
        name, origin = presentation_timezone_for_audit(config)
        self.assertEqual((name, origin), ("UTC", "settings.presentation.timezone"))
        with patch.dict(os.environ, {PRESENTATION_TIMEZONE_ENV: "Asia/Tokyo"}):
            html = catalog_shell(page_by_filename("cat-01.html"), "AUD-SYNTHETIC",
                "<p>Captura 2026-09-11T00:00:00Z</p><code>2026-09-11T00:00:00Z</code>",
                timezone_name=name, timezone_source=origin)
        self.assertIn("11/09/2026 00:00:00 (UTC)", html)
        self.assertNotIn("12/09/2026 09:00:00", html)
        self.assertIn("<code>2026-09-11T00:00:00Z</code>", html)
        self.assertIn("configuração persistida da auditoria", html)

    def test_absent_or_invalid_historical_zone_has_explicit_default_and_nd(self) -> None:
        from rasai.time_contract import presentation_timezone_for_audit
        self.assertEqual(presentation_timezone_for_audit({}), (
            "America/Sao_Paulo", "HISTORICAL_TIMEZONE_NOT_PERSISTED_ND_DEFAULT_USED"))
        self.assertEqual(presentation_timezone_for_audit(
            {"settings": {"presentation": {"timezone": "not/a-zone"}}}), (
            "America/Sao_Paulo", "INVALID_PERSISTED_TIMEZONE_ND_DEFAULT_USED"))
        self.assertEqual(presentation_timezone_for_audit(
            {"settings": {"environment": {"RASAI_PRESENTATION_TIMEZONE": "Europe/Berlin"}}}), (
            "Europe/Berlin", "settings.environment.RASAI_PRESENTATION_TIMEZONE"))

    def test_day_boundary_dst_and_date_without_instant(self) -> None:
        from rasai.time_contract import presentation_timezone_for_audit
        self.assertEqual(format_presentation_timestamp(
            "2026-09-11T00:00:00Z", timezone_name="America/Sao_Paulo"),
            "10/09/2026 21:00:00 (America/Sao_Paulo)")
        self.assertEqual(format_presentation_timestamp(
            "2026-03-29T01:30:00Z", timezone_name="Europe/Berlin"),
            "29/03/2026 03:30:00 (Europe/Berlin)")
        self.assertEqual(localize_visible_timestamps("Fonte: 2026-09-11", timezone_name="UTC"),
                         "Fonte: 2026-09-11")

def test_typed_rfc7231_and_epoch_at_day_boundary_without_ambient_timezone(monkeypatch):
    from datetime import datetime, timezone
    from rasai.time_contract import format_presentation_http_date, format_presentation_unix_epoch
    monkeypatch.setenv("RASAI_PRESENTATION_TIMEZONE", "Asia/Tokyo")
    raw = "Fri, 11 Sep 2026 00:00:00 GMT"
    expected = "10/09/2026 21:00:00 (America/Sao_Paulo)"
    assert format_presentation_http_date(raw, timezone_name="America/Sao_Paulo") == expected
    epoch = datetime(2026, 9, 11, tzinfo=timezone.utc).timestamp()
    assert format_presentation_unix_epoch(epoch, unit="seconds", timezone_name="America/Sao_Paulo") == expected
    assert format_presentation_unix_epoch(epoch * 1000, unit="milliseconds", timezone_name="America/Sao_Paulo") == expected
    assert raw == "Fri, 11 Sep 2026 00:00:00 GMT"


def test_typed_temporal_inputs_refuse_ambiguous_values():
    import pytest
    from rasai.time_contract import format_presentation_http_date, format_presentation_unix_epoch
    with pytest.raises(ValueError):
        format_presentation_http_date("2026-09-11T00:00:00")
    with pytest.raises(ValueError):
        format_presentation_unix_epoch(1500, unit="duration_ms")
    with pytest.raises(ValueError):
        format_presentation_unix_epoch(float("nan"), unit="seconds")
    with pytest.raises(ValueError):
        format_presentation_unix_epoch(True, unit="seconds")


def test_rfc7231_accepts_three_http_date_variants_and_refuses_generic_email_date():
    import pytest
    from rasai.time_contract import format_presentation_http_date
    for raw in ("Sun, 06 Nov 1994 08:49:37 GMT",
                "Sunday, 06-Nov-94 08:49:37 GMT",
                "Sun Nov  6 08:49:37 1994"):
        assert format_presentation_http_date(raw, timezone_name="UTC") == "06/11/1994 08:49:37 (UTC)"
    with pytest.raises(ValueError):
        format_presentation_http_date("Fri, 11 Sep 2026 00:00:00 +0000", timezone_name="UTC")


if __name__ == "__main__":
    unittest.main()
