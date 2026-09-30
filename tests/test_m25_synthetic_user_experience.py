from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.cli_extensions import build_parser
from rasai.m23_cli import configured_apdex
from rasai.m25_apdex_experience import (
    Calibration,
    ExperienceApdexConfig,
    UxMeasurement,
    allocate_samples,
    classify_measurement,
    execute_m25_experience,
)
from rasai.m25_cli import parse_device_mix
from rasai.m25_dynatrace import parse_dynatrace_configuration
from rasai.m25_runtime import consume_pending_config, peek_pending_config
from rasai.persistence import AuditWorkspace


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


def _ux(
    duration: float,
    *,
    js: int = 0,
    console: int = 0,
    first_http: int = 0,
    csp: int = 0,
    request_events: tuple[dict[str, object], ...] = (),
) -> UxMeasurement:
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
        console_error_count=console,
        first_party_http_error_count=first_http,
        http_error_count=first_http,
        csp_violation_count=csp,
        first_party_csp_violation_count=csp,
        request_error_events=request_events,
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
        # Dynatrace load-action semantics: below the lower threshold is Satisfied;
        # equality belongs to the Tolerating zone. Frustrated is strictly above the
        # upper threshold, so equality at that boundary remains Tolerating.
        self.assertEqual(classify_measurement(_ux(1000), calibration, error_scope="first-party")[0], "TOLERATING")
        self.assertEqual(classify_measurement(_ux(2000), calibration, error_scope="first-party")[0], "TOLERATING")
        self.assertEqual(classify_measurement(_ux(2500), calibration, error_scope="first-party")[0], "TOLERATING")
        self.assertEqual(classify_measurement(_ux(2501), calibration, error_scope="first-party")[0], "FRUSTRATED")

    def test_javascript_runtime_error_forces_frustrated_independent_of_request_scope(self) -> None:
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

        classification, value, forced = classify_measurement(
            _ux(300, first_http=1), calibration, error_scope="first-party"
        )
        self.assertEqual(value, 300.0)
        self.assertEqual(classification, "FRUSTRATED")
        self.assertTrue(forced)

    def test_generic_aborted_subresource_is_diagnostic_but_transport_failure_can_affect_apdex(self) -> None:
        calibration = Calibration(
            source="TEST", kpm="USER_ACTION_DURATION",
            satisfied_threshold_seconds=3.0, frustrated_threshold_seconds=12.0,
            errors_affect_apdex=True, metadata={},
        )
        aborted = _ux(
            2000,
            request_events=({
                "error_type": "REQUEST_FAILED",
                "url": "https://analytics.example/collect",
                "resource_type": "fetch",
                "first_party": False,
                "http_status": None,
                "failed_image": False,
                "csp": False,
                "failure_reason": "net::ERR_ABORTED",
            },),
        )
        classification, value, forced = classify_measurement(
            aborted, calibration, error_scope="all"
        )
        self.assertEqual(value, 2000.0)
        self.assertEqual(classification, "SATISFIED")
        self.assertFalse(forced)

        reset = _ux(
            2000,
            request_events=({
                "error_type": "REQUEST_FAILED",
                "url": "https://cdn.example/asset.js",
                "resource_type": "script",
                "first_party": False,
                "http_status": None,
                "failed_image": False,
                "csp": False,
                "failure_reason": "net::ERR_CONNECTION_RESET",
            },),
        )
        classification, _, forced = classify_measurement(
            reset, calibration, error_scope="all"
        )
        self.assertEqual(classification, "FRUSTRATED")
        self.assertTrue(forced)

        main_navigation = UxMeasurement(
            status="NAVIGATION_ERROR",
            user_action_duration_ms=2000.0,
            request_error_events=({
                "error_type": "REQUEST_FAILED",
                "url": "https://example.com/",
                "resource_type": "document",
                "first_party": True,
                "failure_reason": "net::ERR_ABORTED",
            },),
        )
        classification, _, forced = classify_measurement(
            main_navigation, calibration, error_scope="all"
        )
        self.assertEqual(classification, "FRUSTRATED")
        self.assertTrue(forced)

    def test_console_error_is_diagnostic_by_default_and_can_be_enabled(self) -> None:
        calibration = Calibration(
            source="TEST", kpm="USER_ACTION_DURATION",
            satisfied_threshold_seconds=1.0, frustrated_threshold_seconds=4.0,
            errors_affect_apdex=True, metadata={},
        )
        classification, value, forced = classify_measurement(
            _ux(300, console=1), calibration, error_scope="all"
        )
        self.assertEqual(value, 300.0)
        self.assertEqual(classification, "SATISFIED")
        self.assertFalse(forced)

        enabled = Calibration(
            source="TEST", kpm="USER_ACTION_DURATION",
            satisfied_threshold_seconds=1.0, frustrated_threshold_seconds=4.0,
            errors_affect_apdex=True, metadata={},
            console_errors_affect_apdex=True,
        )
        classification, value, forced = classify_measurement(
            _ux(300, console=1), enabled, error_scope="first-party"
        )
        self.assertEqual(value, 300.0)
        self.assertEqual(classification, "FRUSTRATED")
        self.assertTrue(forced)

    def test_csp_violation_is_request_error_by_default(self) -> None:
        calibration = Calibration(
            source="TEST", kpm="USER_ACTION_DURATION",
            satisfied_threshold_seconds=1.0, frustrated_threshold_seconds=4.0,
            errors_affect_apdex=True, metadata={},
        )
        classification, _, forced = classify_measurement(
            _ux(300, csp=1), calibration, error_scope="first-party"
        )
        self.assertEqual(classification, "FRUSTRATED")
        self.assertTrue(forced)

    def test_imported_dynatrace_http_rules_apply_first_match_impact_apdex(self) -> None:
        calibration = Calibration(
            source="TEST",
            kpm="USER_ACTION_DURATION",
            satisfied_threshold_seconds=1.0,
            frustrated_threshold_seconds=4.0,
            errors_affect_apdex=True,
            metadata={
                "http_error_rules": [
                    {
                        "capture": True,
                        "impact_apdex": False,
                        "error_codes": "404",
                        "consider_csp": False,
                        "consider_failed_images": False,
                        "consider_unknown": False,
                        "filter_by_url": False,
                        "url_matcher": "",
                        "url": "",
                    },
                    {
                        "capture": True,
                        "impact_apdex": True,
                        "error_codes": "5xx",
                        "consider_csp": True,
                        "consider_failed_images": True,
                        "consider_unknown": True,
                        "filter_by_url": False,
                        "url_matcher": "",
                        "url": "",
                    },
                ]
            },
        )
        ignored_404 = _ux(
            300,
            first_http=1,
            request_events=({
                "error_type": "HTTP_ERROR",
                "url": "https://example.com/missing.png",
                "http_status": 404,
                "resource_type": "image",
                "first_party": True,
                "failed_image": True,
                "csp": False,
            },),
        )
        classification, _, forced = classify_measurement(ignored_404, calibration, error_scope="all")
        self.assertEqual(classification, "SATISFIED")
        self.assertFalse(forced)

        impacting_500 = _ux(
            300,
            first_http=1,
            request_events=({
                "error_type": "HTTP_ERROR",
                "url": "https://example.com/api",
                "http_status": 503,
                "resource_type": "xhr",
                "first_party": True,
                "failed_image": False,
                "csp": False,
            },),
        )
        classification, _, forced = classify_measurement(impacting_500, calibration, error_scope="all")
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

    def test_cli_handoff_keeps_m23_m25_separate_and_allows_m25_standalone(self) -> None:
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
            "audit", "https://example.com",
            "--no-synthetic-apdex",
            "--apdex-experience",
            "--apdex-experience-device-mix", "mobile=100",
            "--apdex-experience-satisfied-seconds", "2",
            "--apdex-experience-frustrated-seconds", "6",
        ])
        standalone = configured_apdex(args_without_standard, {})
        pending = peek_pending_config()
        self.assertFalse(standalone.enabled)
        self.assertTrue(pending.enabled)
        self.assertEqual(pending.device_mix_dict()["MOBILE"], 100.0)

    def test_execution_persists_population_tablet_errors_without_html_side_effect(self) -> None:
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
            # Injected gateways follow the M23 ownership convention: the caller owns lifecycle.
            self.assertFalse(gateway.closed)

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
            # JavaScript error follows Dynatrace semantics and forces the 2000ms action to Frustrated.
            self.assertEqual(population, (0.5, 2, 0, 2, 1))
            self.assertEqual(tablet, 1)
            self.assertNotIn("DYNATRACE_API_TOKEN", stored_config)
            self.assertIn("measurement_contract", stored_config)
            self.assertIsNone(result.report_path)
            self.assertFalse((workspace.root / "report").exists())


    def test_experience_concurrency_guardrails_safe_inheritance_and_target_aware_parallelism(self) -> None:
        with self.assertRaises(ValueError):
            ExperienceApdexConfig(
                enabled=True, target_samples_per_page=1, max_attempts_per_page=1,
                device_mix=(("MOBILE", 100.0),), satisfied_threshold_seconds=1.0,
                frustrated_threshold_seconds=4.0, delay_seconds=0.0, concurrency=3,
            ).validate()
        ExperienceApdexConfig(
            enabled=True, target_samples_per_page=1, max_attempts_per_page=1,
            device_mix=(("MOBILE", 100.0),), satisfied_threshold_seconds=1.0,
            frustrated_threshold_seconds=4.0, delay_seconds=1.0, concurrency=3,
        ).validate()
        with self.assertRaises(ValueError):
            ExperienceApdexConfig(
                enabled=True, target_samples_per_page=1, max_attempts_per_page=1,
                device_mix=(("MOBILE", 100.0),), satisfied_threshold_seconds=1.0,
                frustrated_threshold_seconds=4.0, delay_seconds=1.0, concurrency=4,
            ).validate()

        parser = build_parser()
        inherited_args = parser.parse_args([
            "audit", "https://example.com", "--synthetic-apdex",
            "--apdex-threshold-seconds", "1", "--apdex-concurrency", "4",
            "--apdex-delay-seconds", "1", "--apdex-experience",
            "--apdex-experience-device-mix", "mobile=100",
        ])
        configured_apdex(inherited_args, {})
        self.assertEqual(peek_pending_config().concurrency, 2)
        consume_pending_config()

        explicit_args = parser.parse_args([
            "audit", "https://example.com", "--synthetic-apdex",
            "--apdex-threshold-seconds", "1", "--apdex-concurrency", "4",
            "--apdex-delay-seconds", "1", "--apdex-experience",
            "--apdex-experience-device-mix", "mobile=100",
            "--apdex-experience-concurrency", "3",
            "--apdex-experience-delay-seconds", "1",
        ])
        configured_apdex(explicit_args, {})
        self.assertEqual(peek_pending_config().concurrency, 3)
        consume_pending_config()

        with tempfile.TemporaryDirectory() as directory:
            workspace = _workspace(directory)
            calls = []

            class _ParallelUxGateway:
                def environment(self):
                    return {"system": "TEST", "chromium_version": "test", "m25_profile_version": "test"}

                def measure(self, **_kwargs):
                    calls.append(1)
                    return _ux(500)

                def close(self):
                    pass

            result = execute_m25_experience(
                audit_id="AUD-M25", workspace=workspace,
                config=ExperienceApdexConfig(
                    enabled=True, target_samples_per_page=1, max_attempts_per_page=3,
                    max_pages=1, device_mix=(("MOBILE", 100.0),),
                    satisfied_threshold_seconds=1.0, frustrated_threshold_seconds=4.0,
                    settle_seconds=1.0, delay_seconds=1.0, concurrency=3,
                ),
                gateway_factory=_ParallelUxGateway,
            )
            self.assertEqual(result.attempted_samples, 1)
            self.assertEqual(len(calls), 1)

    def test_exported_dynatrace_json_does_not_persist_raw_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dynatrace.json"
            path.write_text(json.dumps({
                "loadActionKeyPerformanceMetric": "ACTION_DURATION",
                "loadActionApdexSettings": {"toleratedThreshold": 1000, "frustratingThreshold": 4000},
                "arbitraryPrivateConfiguration": "do-not-copy",
            }), encoding="utf-8")
            from rasai.m25_dynatrace import load_dynatrace_calibration
            value = load_dynatrace_calibration(base_url=None, application_id=None, config_json_path=str(path))
            self.assertEqual(value.satisfied_threshold_seconds, 1.0)
            self.assertFalse(value.metadata["raw_configuration_persisted"])
            self.assertNotIn("arbitraryPrivateConfiguration", json.dumps(value.metadata))


if __name__ == "__main__":
    unittest.main()
