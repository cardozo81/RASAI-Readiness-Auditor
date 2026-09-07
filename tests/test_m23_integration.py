from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.cli_extensions import build_parser
from rasai.console_m23 import State, append_m23_command, synthetic_load_summary, validate_m23_state
from rasai.m23_apdex import SyntheticApdexConfig, execute_m23_apdex
from rasai.m23_apdex_profiles import NavigationMeasurement
from rasai.persistence import AuditWorkspace


class _Gateway:
    def __init__(self, measurements):
        self.measurements = list(measurements)
        self.closed = False

    def environment(self):
        return {"system": "TEST", "chromium_version": "test"}

    def measure(self, *, url, profile, timeout_seconds):
        return self.measurements.pop(0)

    def close(self):
        self.closed = True


def _measurement(duration_ms: int, status: str = "SUCCESS") -> NavigationMeasurement:
    return NavigationMeasurement(
        status=status,
        duration_ms=duration_ms,
        http_status=200,
        final_url="https://example.com/",
        error_code=None,
        error_message=None,
        profile_applied=True,
        cpu_method="TEST_CPU",
        network_method="TEST_NETWORK",
    )


def _workspace(directory: str) -> AuditWorkspace:
    workspace = AuditWorkspace.create(Path(directory), "AUD-M23")
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
                CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT NOT NULL,normalized_url TEXT NOT NULL);
                CREATE TABLE page_snapshots(snapshot_id TEXT PRIMARY KEY,page_id TEXT NOT NULL,device TEXT NOT NULL,final_url TEXT);
                INSERT INTO audits VALUES ('AUD-M23');
                INSERT INTO pages VALUES ('PAGE-1','AUD-M23','https://example.com/');
                INSERT INTO page_snapshots VALUES ('SNAP-1','PAGE-1','MOBILE','https://example.com/');
                """
            )
    finally:
        connection.close()
    return workspace


class M23IntegrationTests(unittest.TestCase):
    def test_public_parser_exposes_m23_without_changing_default(self) -> None:
        parser = build_parser()
        disabled = parser.parse_args(["audit", "https://example.com"])
        self.assertIsNone(disabled.synthetic_apdex)
        enabled = parser.parse_args(
            [
                "audit", "https://example.com", "--synthetic-apdex",
                "--apdex-threshold-seconds", "1.0",
                "--apdex-samples-per-context", "5",
            ]
        )
        self.assertTrue(enabled.synthetic_apdex)
        self.assertEqual(enabled.apdex_threshold_seconds, 1.0)
        self.assertEqual(enabled.apdex_samples_per_context, 5)

    def test_three_valid_samples_are_small_group_and_formula_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = _workspace(directory)
            gateway = _Gateway([_measurement(500), _measurement(2000), _measurement(5000)])
            result = execute_m23_apdex(
                audit_id="AUD-M23",
                workspace=workspace,
                config=SyntheticApdexConfig(
                    enabled=True,
                    threshold_seconds=1.0,
                    target_valid_samples=3,
                    max_attempts_per_context=3,
                    max_pages=1,
                    timeout_seconds=5.0,
                    delay_seconds=0.0,
                    concurrency=1,
                ),
                gateway=gateway,
            )
            self.assertEqual(result.valid_samples, 3)
            self.assertEqual(result.small_group_summaries, 1)
            self.assertEqual(result.status, "PARTIAL")
            connection = sqlite3.connect(workspace.database)
            try:
                row = connection.execute(
                    "SELECT apdex_score,satisfied_count,tolerating_count,frustrated_count,small_group,final_group "
                    "FROM synthetic_apdex_summaries"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(row, (0.5, 1, 1, 1, 1, 0))

    def test_tool_failure_is_excluded_from_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = _workspace(directory)
            invalid = NavigationMeasurement(
                status="BROWSER_UNAVAILABLE", duration_ms=None, http_status=None,
                final_url=None, error_code="BROWSER_UNAVAILABLE", error_message=None,
                profile_applied=False, cpu_method=None, network_method=None,
            )
            gateway = _Gateway([invalid, _measurement(500)])
            result = execute_m23_apdex(
                audit_id="AUD-M23",
                workspace=workspace,
                config=SyntheticApdexConfig(
                    enabled=True, threshold_seconds=1.0, target_valid_samples=1,
                    max_attempts_per_context=2, max_pages=1, timeout_seconds=5.0,
                    delay_seconds=0.0, concurrency=1,
                ),
                gateway=gateway,
            )
            self.assertEqual(result.attempted_samples, 2)
            self.assertEqual(result.valid_samples, 1)
            self.assertEqual(result.invalid_samples, 1)

    def test_disabled_m23_persists_zero_work_without_starting_browser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = _workspace(directory)
            result = execute_m23_apdex(
                audit_id="AUD-M23",
                workspace=workspace,
                config=SyntheticApdexConfig(enabled=False),
            )
            self.assertFalse(result.enabled)
            connection = sqlite3.connect(workspace.database)
            try:
                row = connection.execute(
                    "SELECT status,attempted_samples,valid_samples FROM synthetic_apdex_runs"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(row, ("DISABLED", 0, 0))

    def test_console_command_and_load_warning_match_configuration(self) -> None:
        state = State(
            target="https://example.com",
            max_pages=5,
            device="both",
            synthetic_apdex=True,
            apdex_threshold=1.0,
            apdex_samples=5,
            apdex_max_attempts=7,
            apdex_max_pages=2,
            apdex_timeout=5.0,
            apdex_delay=1.0,
            apdex_concurrency=1,
        )
        validate_m23_state(state)
        command = append_m23_command(["python", "-m", "rasai", "audit", state.target], state)
        self.assertIn("--synthetic-apdex", command)
        self.assertIn("--apdex-threshold-seconds", command)
        attempts, message = synthetic_load_summary(state)
        self.assertEqual(attempts, 28)
        self.assertIn("múltiplos requests HTTP", message)

    def test_timeout_must_exceed_4t(self) -> None:
        state = State(synthetic_apdex=True, apdex_threshold=2.0, apdex_timeout=8.0)
        with self.assertRaises(ValueError):
            validate_m23_state(state)


if __name__ == "__main__":
    unittest.main()
