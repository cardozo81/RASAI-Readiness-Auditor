from __future__ import annotations

import argparse
import unittest

from rasai.m25_cli import (
    DEFAULT_UX_ERROR_SCOPE,
    DEFAULT_UX_FRUSTRATED_SECONDS,
    DEFAULT_UX_KPM,
    DEFAULT_UX_SATISFIED_SECONDS,
    UX_ENABLED_ENV,
    configured_experience,
    register_experience_arguments,
)
from rasai.m25_dynatrace import parse_dynatrace_configuration


class M25DynatraceCompatibilityDefaultsTests(unittest.TestCase):
    @staticmethod
    def _args(*values: str):
        parser = argparse.ArgumentParser()
        register_experience_arguments(parser)
        return parser.parse_args(list(values))

    def test_enabled_experience_resolves_dynatrace_compatible_defaults(self) -> None:
        cfg = configured_experience(self._args(), {UX_ENABLED_ENV: "true"})
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.kpm, DEFAULT_UX_KPM)
        self.assertEqual(cfg.kpm, "USER_ACTION_DURATION")
        self.assertEqual(cfg.satisfied_threshold_seconds, DEFAULT_UX_SATISFIED_SECONDS)
        self.assertEqual(cfg.satisfied_threshold_seconds, 3.0)
        self.assertEqual(cfg.frustrated_threshold_seconds, DEFAULT_UX_FRUSTRATED_SECONDS)
        self.assertEqual(cfg.frustrated_threshold_seconds, 12.0)
        self.assertTrue(cfg.errors_affect_apdex)
        self.assertEqual(cfg.error_scope, DEFAULT_UX_ERROR_SCOPE)
        self.assertEqual(cfg.error_scope, "first-party")

    def test_user_can_override_default_thresholds_and_kpm(self) -> None:
        cfg = configured_experience(
            self._args(
                "--apdex-experience",
                "--apdex-experience-kpm", "LARGEST_CONTENTFUL_PAINT",
                "--apdex-experience-satisfied-seconds", "2.25",
                "--apdex-experience-frustrated-seconds", "7.5",
                "--apdex-experience-error-scope", "navigation",
            ),
            {},
        )
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.kpm, "LARGEST_CONTENTFUL_PAINT")
        self.assertEqual(cfg.satisfied_threshold_seconds, 2.25)
        self.assertEqual(cfg.frustrated_threshold_seconds, 7.5)
        self.assertEqual(cfg.error_scope, "navigation")

    def test_dynatrace_visually_complete_uses_explicit_user_action_duration_fallback(self) -> None:
        parsed = parse_dynatrace_configuration(
            {
                "loadActionKeyPerformanceMetric": "VISUALLY_COMPLETE",
                "loadActionApdexSettings": {
                    "toleratedThreshold": 3000,
                    "frustratingThreshold": 12000,
                    "toleratedFallbackThreshold": 3000,
                    "frustratingFallbackThreshold": 12000,
                },
                "xhrActionKeyPerformanceMetric": "ACTION_DURATION",
                "xhrActionApdexSettings": {
                    "toleratedThreshold": 2500,
                    "frustratingThreshold": 10000,
                    "toleratedFallbackThreshold": 3000,
                    "frustratingFallbackThreshold": 12000,
                },
                "customActionApdexSettings": {
                    "toleratedThreshold": 3000,
                    "frustratingThreshold": 12000,
                },
            },
            source="TEST_DYNATRACE",
        )
        self.assertEqual(parsed.kpm, "USER_ACTION_DURATION")
        self.assertEqual(parsed.satisfied_threshold_seconds, 3.0)
        self.assertEqual(parsed.frustrated_threshold_seconds, 12.0)
        self.assertIn("RASAI_CAPABILITY_FALLBACK", parsed.source)
        self.assertTrue(parsed.metadata["rasai_capability_fallback_applied"])
        self.assertEqual(parsed.metadata["requested_kpm"], "VISUALLY_COMPLETE")
        self.assertEqual(parsed.metadata["effective_kpm"], "USER_ACTION_DURATION")
        contract = parsed.metadata["dynatrace_apdex_contract"]
        self.assertEqual(contract["xhr"]["satisfied_threshold_seconds"], 2.5)
        self.assertEqual(contract["xhr"]["frustrated_threshold_seconds"], 10.0)
        self.assertEqual(contract["custom"]["satisfied_threshold_seconds"], 3.0)
        self.assertEqual(
            parsed.metadata["standalone_action_support"]["custom"],
            "NOT_EXECUTABLE_WITHOUT_SCRIPTED_ACTION",
        )

    def test_unsupported_primary_kpm_without_fallback_still_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "fallback"):
            parse_dynatrace_configuration(
                {
                    "loadActionKeyPerformanceMetric": "VISUALLY_COMPLETE",
                    "loadActionApdexSettings": {
                        "toleratedThreshold": 3000,
                        "frustratingThreshold": 12000,
                    },
                },
                source="TEST_DYNATRACE",
            )

    def test_supported_imported_kpm_uses_primary_thresholds_without_fallback(self) -> None:
        parsed = parse_dynatrace_configuration(
            {
                "loadActionKeyPerformanceMetric": "LARGEST_CONTENTFUL_PAINT",
                "loadActionApdexSettings": {
                    "toleratedThreshold": 2500,
                    "frustratingThreshold": 8000,
                    "toleratedFallbackThreshold": 3000,
                    "frustratingFallbackThreshold": 12000,
                },
            },
            source="TEST_DYNATRACE",
        )
        self.assertEqual(parsed.kpm, "LARGEST_CONTENTFUL_PAINT")
        self.assertEqual(parsed.satisfied_threshold_seconds, 2.5)
        self.assertEqual(parsed.frustrated_threshold_seconds, 8.0)
        self.assertFalse(parsed.metadata["rasai_capability_fallback_applied"])


if __name__ == "__main__":
    unittest.main()
