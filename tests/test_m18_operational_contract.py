from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from rasai.acquisition import HttpClient
from rasai.audit_runner import run_audit
from rasai.discovery import DiscoveryEngine
from rasai.m18_ai import DeepSeekProvider, MiMoProvider, OpenAIProvider
from rasai.m18_persistence import _resolve_session_status
from tests.test_m12_stable_baseline import _FixtureRenderer, _server


class M18OperationalContractTests(unittest.TestCase):
    def test_single_provider_failure_is_degraded_not_chain_exhausted(self) -> None:
        status, exhausted = _resolve_session_status(
            strategy="SINGLE_PROVIDER",
            enabled=True,
            configured=True,
            audit_mode="DEGRADED",
            provider_states={"OPENAI": "QUARANTINED_FOR_AUDIT"},
        )
        self.assertEqual(status, "DEGRADED")
        self.assertFalse(exhausted)

    def test_selected_provider_without_credential_is_not_configured(self) -> None:
        status, exhausted = _resolve_session_status(
            strategy="SINGLE_PROVIDER",
            enabled=True,
            configured=False,
            audit_mode="NO_AI",
            provider_states={"OPENAI": "ACTIVE"},
        )
        self.assertEqual(status, "NOT_CONFIGURED")
        self.assertFalse(exhausted)

    def test_auto_all_quarantined_is_chain_exhausted(self) -> None:
        status, exhausted = _resolve_session_status(
            strategy="AUTO",
            enabled=True,
            configured=True,
            audit_mode="DEGRADED",
            provider_states={
                "OPENAI": "QUARANTINED_FOR_AUDIT",
                "DEEPSEEK": "QUARANTINED_FOR_AUDIT",
            },
        )
        self.assertEqual(status, "CHAIN_EXHAUSTED")
        self.assertTrue(exhausted)

    def test_provider_credentials_are_isolated_from_openai_environment(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "ambient-openai-key",
                "DEEPSEEK_API_KEY": "",
                "MIMO_API_KEY": "",
            },
            clear=False,
        ):
            self.assertEqual(OpenAIProvider().api_key, "ambient-openai-key")
            self.assertFalse(OpenAIProvider(api_key="").api_key)
            self.assertFalse(DeepSeekProvider().api_key)
            self.assertFalse(MiMoProvider().api_key)

    def test_explicit_provider_without_token_is_visible_in_persistence_and_ai_page(self) -> None:
        # This test must never inherit a developer's real API credential. Besides
        # making the assertion nondeterministic, doing so could perform paid
        # external calls during an ordinary local unit-test run.
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with _server() as origin, TemporaryDirectory() as directory:
                html = """<!doctype html><html lang='pt-BR'><head><title>Sem token</title></head>
<body><main><h1>Sem token</h1><p>Fixture para validar estado operacional sem credencial.</p></main></body></html>"""
                provider = OpenAIProvider(api_key="")
                result = run_audit(
                    f"{origin}/",
                    audits_root=Path(directory),
                    project_name="M18 sem token",
                    max_pages=1,
                    semantic_provider=provider,
                    discovery_engine=DiscoveryEngine(HttpClient(timeout=1)),
                    renderer=_FixtureRenderer(html),
                    lazy_probe=lambda url, device: None,
                )

                connection = sqlite3.connect(result.audit_root / "audit.db")
                connection.row_factory = sqlite3.Row
                try:
                    session = connection.execute(
                        "SELECT strategy,enabled,status,effective_provider FROM ai_audit_sessions WHERE audit_id=?",
                        (result.audit_id,),
                    ).fetchone()
                    attempts = connection.execute(
                        "SELECT COUNT(*) FROM ai_provider_attempts WHERE audit_id=?",
                        (result.audit_id,),
                    ).fetchone()[0]
                finally:
                    connection.close()

                self.assertIsNotNone(session)
                self.assertEqual(session["strategy"], "SINGLE_PROVIDER")
                self.assertEqual(session["enabled"], 1)
                self.assertEqual(session["status"], "NOT_CONFIGURED")
                self.assertIsNone(session["effective_provider"])
                self.assertEqual(attempts, 0)

                overview = result.report_path.read_text(encoding="utf-8")
                ai = (result.audit_root / "report" / "ai-usage.html").read_text(encoding="utf-8")
                remediation = (result.audit_root / "report" / "remediation.html").read_text(encoding="utf-8")
                self.assertIn("Uso de IA", ai)
                self.assertIn("IA habilitada", ai)
                self.assertIn("NOT_CONFIGURED", ai)
                self.assertIn("Nenhuma chamada externa", ai)
                self.assertIn("Nenhum resultado semântico válido", ai)
                self.assertNotIn("NOT_CONFIGURED", overview)
                self.assertIn("Remediações", remediation)

    def test_cli_reference_documents_every_exposed_argument(self) -> None:
        text = Path("docs/CLI_REFERENCE.md").read_text(encoding="utf-8")
        required_tokens = (
            "`-h`, `--help`",
            "`--version`",
            "`--config PATH`",
            "`target`",
            "`--urls-file PATH`",
            "`--project TEXT`",
            "`--language CODE`",
            "`--market CODE`",
            "`--max-pages N`",
            "`--audits-root PATH`",
            "`--device-context`",
            "`--ai-provider`",
            "`--ai-model MODEL_ID`",
            "`RASAI_DEVICE_CONTEXT`",
        )
        for token in required_tokens:
            with self.subTest(token=token):
                self.assertIn(token, text)

        for provider_name in ("none", "openai", "deepseek", "mimo", "auto"):
            with self.subTest(provider=provider_name):
                self.assertIn(provider_name, text)


if __name__ == "__main__":
    unittest.main()
