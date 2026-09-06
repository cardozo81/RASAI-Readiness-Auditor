from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from searchgeo.cli_extensions import build_parser
from searchgeo.m23_cli import configured_apdex
from searchgeo.m25_apdex_experience import (
    Calibration,
    ExperienceApdexConfig,
    UxMeasurement,
    allocate_samples,
    classify_measurement,
    execute_m25_experience,
)
from searchgeo.m25_cli import parse_device_mix
from searchgeo.m25_dynatrace import parse_dynatrace_configuration
from searchgeo.m25_runtime import consume_pending_config, peek_pending_config
from searchgeo.persistence import AuditWorkspace


class _Gateway:
    def __init__(self, measurements):
        self.measurements = list(measurements)
        self.closed = False

    def environment(self):
        return {"system": "TEST", "chromium_version": "test", "m25_profile_version": "test"}

    def measure(self, **_kwargs):
        return self.measurements.pop(0)

    def close(self):
        self.closed = True


def _ux(duration: float, *, js: int = 0, first_http: int = 0) -> UxMeasurement:
    return UxMeasurement(
        status="SUCCESS",
        user_action_duration_ms=duration,
        navigation_duration_ms=duration,
        response_start_ms=100.0,
        response_end_ms=200.0,
        dom_interactive_ms=duration * 0.7,
        load_event_start_ms=duration * 0.9,
        load_event_end_ms=duration,
        lcp_ms=duration * 0.8,
        cls=0.01,
        http_status=200,
        final_url="https://example.com/",
        javascript_error_count=js,
        first_party_http_error_count=first_http,
        http_error_count=first_http,
    )


def _workspace(directory: str) -> AuditWorkspace:
    workspace = AuditWorkspace.create(Path(directory), "AUD-M25")
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
                CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT NOT NULL,normalized_url TEXT NOT NULL);
                CREATE TABLE page_snapshots(snapshot_id TEXT PRIMARY KEY,page_id TEXT NOT NULL,device TEXT NOT NULL,final_url TEXT);
                INSERT INTO audits VALUES ('AUD-M25');
                INSERT INTO pages VALUES ('PAGE-1','AUD-M25','https://example.com/');
                INSERT INTO page_snapshots VALUES ('SNAP-1','PAGE-1','MOBILE','https://example.com/');
                """
            )
    finally:
        connection.close()
    (workspace.root / "report").mkdir(exist_ok=True)
    return workspace


class M25SyntheticUserExperienceTests(unittest.TestCase):
    def tearDown(self) -> None:
        consume_pending_config()

    def test_device_mix_requires_explicit_100_percent_and_allocates_exact_total(self) -> None:
        mix = parse_device_mix("mobile=62,desktop=31,tablet=7")
        self.assertEqual(dict(mix), {"MOBILE": 62.0, "DESKTOP": 31.0, "TABLET": 7.0})
        allocation = allocate_samples(1000, dict(mix))
        self.assertEqual(allocation, {"MOBILE": 620, "DESKTOP": 310, "TABLET": 70})
        with self.assertRaises(ValueError):
            parse_device_mix("mobile=50,desktop=40")

    def test_calibrated_thresholds_are_independent_from_standard_4t(self) -> None:
        calibration = Calibration(
            source="TEST", kpm="USER_ACTION_DURATION",
            satisfied_threshold_seconds=1.0,
            frustrated_threshold_seconds=2.5,
            errors_affect_apdex=False,
            metadata={},
        )
        self.assertEqual(classify_measurement(_ux(500), calibration, error_scope="first-party")[0], "SATISFIED")
        self.assertEqual(classify_measurement(_ux(2000), calibration, error_scope="first-party")[0], "TOLERATING")
        self.assertEqual(classify_measurement(_ux(3000), calibration, error_scope="first-party")[0], "FRUSTRATED")

    def test_qualifying_error_can_force_fast_action_to_frustrated(self) -> None:
        calibration = Calibration(
            source="TEST", kpm="USER_ACTION_DURATION",
            satisfied_threshold_seconds=1.0, frustrated_threshold_seconds=4.0,
            errors_affect_apdex=True, metadata={},
        )
        classification, value, forced = classify_measurement(
            _ux(300, js=1), calibration, error_scope="first-party"
        )
        self.assertEqual(value, 300.0)
        self.assertEqual(classification, "FRUSTRATED")
        self.assertTrue(forced)

    def test_dynatrace_configuration_parser_converts_old_millisecond_thresholds(self) -> None:
        parsed = parse_dynatrace_configuration(
            {
                "loadActionKeyPerformanceMetric": "ACTION_DURATION",
                "loadActionApdexSettings": {
                    "toleratedThreshold": 2000,
                    "frustratingThreshold": 6000,
                    "frustratingIfReportedOrWebRequestError": True,
                },
            },
            source="TEST_EXPORT",
        )
        self.assertEqual(parsed.kpm, "USER_ACTION_DURATION")
        self.assertEqual(parsed.satisfied_threshold_seconds, 2.0)
        self.assertEqual(parsed.frustrated_threshold_seconds, 6.0)
        self.assertTrue(parsed.errors_affect_apdex)

    def test_cli_handoff_requires_standard_m23_and_keeps_m25_separate(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "audit", "https://example.com",
            "--synthetic-apdex", "--apdex-threshold-seconds", "1",
            "--apdex-experience", "--apdex-experience-samples", "1000",
            "--apdex-experience-device-mix", "mobile=60,desktop=35,tablet=5",
            "--apdex-experience-satisfied-seconds", "2",
            "--apdex-experience-frustrated-seconds", "6",
        ])
        standard = configured_apdex(args, {})
        pending = peek_pending_config()
        self.assertTrue(standard.enabled)
        self.assertEqual(standard.target_valid_samples, 100)
        self.assertTrue(pending.enabled)
        self.assertEqual(pending.target_samples_per_page, 1000)
        self.assertEqual(pending.device_mix_dict()["TABLET"], 5.0)

        args_without_standard = parser.parse_args([
            "audit", "https://example.com", "--apdex-experience",
            "--apdex-experience-device-mix", "mobile=100",
            "--apdex-experience-satisfied-seconds", "2",
            "--apdex-experience-frustrated-seconds", "6",
        ])
        with self.assertRaises(ValueError):
            configured_apdex(args_without_standard, {})

    def test_execution_persists_population_tablet_errors_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = _workspace(directory)
            gateway = _Gateway([
                _ux(500),
                _ux(2000, js=1),
                _ux(700),
                _ux(3000),
            ])
            config = ExperienceApdexConfig(
                enabled=True,
                target_samples_per_page=4,
                max_attempts_per_page=4,
                max_pages=1,
                device_mix=(("MOBILE", 50.0), ("DESKTOP", 25.0), ("TABLET", 25.0)),
                session_mode="cold",
                kpm="USER_ACTION_DURATION",
                satisfied_threshold_seconds=1.0,
                frustrated_threshold_seconds=2.5,
                errors_affect_apdex=True,
                error_scope="first-party",
                settle_seconds=1.0,
                delay_seconds=0.0,
                concurrency=1,
            )
            result = execute_m25_experience(
                audit_id="AUD-M25", workspace=workspace, config=config, gateway=gateway
            )
            self.assertEqual(result.valid_samples, 4)
            self.assertEqual(result.final_population_groups, 1)
            self.assertTrue(gateway.closed)

            connection = sqlite3.connect(workspace.database)
            try:
                population = connection.execute(
                    "SELECT apdex_score,satisfied_count,tolerating_count,frustrated_count,error_forced_frustrated_count "
                    "FROM synthetic_ux_apdex_summaries WHERE device='POPULATION'"
                ).fetchone()
                tablet = connection.execute(
                    "SELECT COUNT(*) FROM synthetic_ux_apdex_samples WHERE device='TABLET'"
                ).fetchone()[0]
                stored_config = connection.execute(
                    "SELECT configuration FROM synthetic_ux_apdex_runs"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(population, (0.625, 2, 1, 1, 1))
            self.assertEqual(tablet, 1)
            self.assertNotIn("DYNATRACE_API_TOKEN", stored_config)
            report = workspace.root / "report" / "apdex-experience.html"
            self.assertTrue(report.is_file())
            html = report.read_text(encoding="utf-8")
            self.assertIn("Synthetic User Experience Apdex", html)
            self.assertIn("Não é RUM", html)
            self.assertIn("TABLET", html)

    def test_exported_dynatrace_json_does_not_persist_raw_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dynatrace.json"
            path.write_text(json.dumps({
                "loadActionKeyPerformanceMetric": "ACTION_DURATION",
                "loadActionApdexSettings": {"toleratedThreshold": 1000, "frustratingThreshold": 4000},
                "arbitraryPrivateConfiguration": "do-not-copy",
            }), encoding="utf-8")
            from searchgeo.m25_dynatrace import load_dynatrace_calibration
            value = load_dynatrace_calibration(base_url=None, application_id=None, config_json_path=str(path))
            self.assertEqual(value.satisfied_threshold_seconds, 1.0)
            self.assertFalse(value.metadata["raw_configuration_persisted"])
            self.assertNotIn("arbitraryPrivateConfiguration", json.dumps(value.metadata))


if __name__ == "__main__":
    unittest.main()
