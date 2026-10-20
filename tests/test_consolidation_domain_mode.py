"""Focal #210 regressions for the user-facing mutually exclusive CONS modes."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from rasai import consolidation_cli
from rasai.consolidation import console


_OUTCOME = {
    "package_id": "CDOM-TEST", "html_path": "/tmp/CDOM/report.html",
    "manifest_path": "/tmp/CDOM/manifest.json", "status": "MATERIALIZED",
}


class ConsolidationDomainModeTests(unittest.TestCase):
    def test_cli_domain_only_delegates_to_source_verified_cdom(self) -> None:
        with patch(
            "rasai.consolidation.domain_comparative_package.materialize_same_domain_package",
            return_value=_OUTCOME,
        ) as package, patch(
            "rasai.consolidation.index.ConsolidationIndex.refresh",
            side_effect=AssertionError("CDOM must not refresh the index"),
        ), patch(
            "rasai.consolidation.service.generate",
            side_effect=AssertionError("CDOM must not call CONS generator"),
        ), redirect_stdout(StringIO()) as stream:
            rc = consolidation_cli.main([
                "AUD-ONE", "AUD-TWO", "--audits-root", "audits",
                "--comparison-mode", "SAME_DOMAIN_COMPARATIVE",
                "--additional-audit-id", "AUD-THREE",
                "--verify-source-bytes",
            ])
        self.assertEqual(rc, 0)
        package.assert_called_once_with(
            Path("audits"), ("AUD-ONE", "AUD-TWO", "AUD-THREE"),
            verify_source_bytes=True,
        )
        self.assertIn("CDOM-TEST", stream.getvalue())
        self.assertIn("sem deltas", stream.getvalue())

    def test_domain_rejects_implicit_cost_filters_and_unverified_bytes(self) -> None:
        base = ["AUD-ONE", "AUD-TWO", "--comparison-mode", "SAME_DOMAIN_COMPARATIVE"]
        denied = (
            [],
            ["--specialist-ai", "--verify-source-bytes"],
            ["--ai-provider", "openai", "--verify-source-bytes"],
            ["--selection-mode", "MANUAL", "--verify-source-bytes"],
            ["--selection-mode", "SUCCESS_ONLY", "--verify-source-bytes"],
        )
        with patch(
            "rasai.consolidation.domain_comparative_package.materialize_same_domain_package",
        ) as package:
            for extra in denied:
                with self.subTest(extra=extra), self.assertRaises(SystemExit):
                    consolidation_cli.main(base + extra)
            package.assert_not_called()

    def test_legacy_mode_rejects_domain_only_options_before_refresh(self) -> None:
        with patch(
            "rasai.consolidation.index.ConsolidationIndex.refresh",
            side_effect=AssertionError("legacy misuse must be rejected"),
        ):
            for flags in (["--verify-source-bytes"], ["--additional-audit-id", "AUD-THREE"]):
                with self.subTest(flags=flags), self.assertRaises(SystemExit):
                    consolidation_cli.main(["AUD-ONE", "AUD-TWO", *flags])

    def test_top_level_domain_dispatch_avoids_audit_runtime_and_secrets(self) -> None:
        from rasai import entrypoint

        flags = (
            ["--comparison-mode", "SAME_DOMAIN_COMPARATIVE"],
            ["--comparison-mode=SAME_DOMAIN_COMPARATIVE"],
        )
        for option in flags:
            with self.subTest(option=option), patch.object(
                entrypoint, "_install_audit_runtime",
                side_effect=AssertionError("CDOM cannot install audit/provider runtime"),
            ), patch.object(
                entrypoint, "_activate_persisted_cli_secrets",
                side_effect=AssertionError("CDOM cannot activate provider secrets"),
            ), patch(
                "rasai.consolidation.domain_comparative_package.materialize_same_domain_package",
                return_value=_OUTCOME,
            ) as package, redirect_stdout(StringIO()):
                result = entrypoint.main([
                    "consolidate", "AUD-ONE", "AUD-TWO",
                    *option, "--verify-source-bytes",
                ])
            self.assertEqual(result, 0)
            package.assert_called_once_with(
                Path("audits"), ("AUD-ONE", "AUD-TWO"),
                verify_source_bytes=True,
            )

    def test_console_requires_literal_confirmation_and_keeps_cdom_isolated(self) -> None:
        with patch.object(console, "_clear"), patch.object(console, "_pause"), patch(
            "builtins.input",
            side_effect=["AUD-ONE", "AUD-TWO", "", "NAO"],
        ), patch(
            "rasai.consolidation.domain_comparative_package.materialize_same_domain_package",
        ) as package, redirect_stdout(StringIO()) as stream:
            console._domain_comparative(Path("audits"))
        package.assert_not_called()
        self.assertIn("Cancelado", stream.getvalue())
        with patch.object(console, "_clear"), patch.object(console, "_pause"), patch(
            "builtins.input",
            side_effect=["AUD-ONE", "AUD-TWO", "AUD-THREE", "SIM", "N"],
        ), patch(
            "rasai.consolidation.domain_comparative_package.materialize_same_domain_package",
            return_value=_OUTCOME,
        ) as package, redirect_stdout(StringIO()) as stream:
            console._domain_comparative(Path("audits"))
        package.assert_called_once_with(
            Path("audits"), ("AUD-ONE", "AUD-TWO", "AUD-THREE"),
            verify_source_bytes=True,
        )
        self.assertIn("CDOM-TEST", stream.getvalue())

    def test_console_menu_exposes_separate_route_without_rewriting_legacy(self) -> None:
        with patch.object(console, "_clear"), patch.object(
            console, "_domain_comparative",
        ) as domain, patch.object(
            console, "_generate",
        ) as legacy, patch("builtins.input", side_effect=["3", "V"]):
            console.run("audits")
        domain.assert_called_once_with(Path("audits"))
        legacy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
