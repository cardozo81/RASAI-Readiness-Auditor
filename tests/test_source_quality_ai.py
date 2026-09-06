from __future__ import annotations

import json
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from searchgeo.acquisition import HttpAcquisitionResult, NetworkError, NetworkErrorKind, RedirectHop
from searchgeo.audit_runner import run_audit
from searchgeo.discovery import DEFAULT_CRAWLERS, DiscoveredPage, DiscoveryProvenance, DiscoveryResult, RobotsResult, RobotsState
from searchgeo.domain import DeviceContext, DiscoverySource
from searchgeo.m18_ai import OpenAIProvider
from searchgeo.rendering import BrowserRenderResult, RenderErrorKind


_SOURCE = "https://mdsgroup.com/"
_FINAL = "https://mds.pt/"


class _BlockedDiscovery:
    def discover(self, seed_url: str, *, max_pages: int) -> DiscoveryResult:
        acquisition = HttpAcquisitionResult(
            requested_url=_SOURCE,
            final_url=_FINAL,
            status=None,
            headers=(),
            body=b"",
            redirects=(
                RedirectHop(301, _SOURCE, "http://www.mdsgroup.com/", "http://www.mdsgroup.com/"),
                RedirectHop(301, "http://www.mdsgroup.com/", _FINAL, _FINAL),
            ),
            network_error=NetworkError(NetworkErrorKind.TLS, "hostname mismatch"),
            elapsed_ms=10,
        )
        return DiscoveryResult(
            origin="https://mdsgroup.com",
            pages=(DiscoveredPage(_SOURCE, _SOURCE, (DiscoverySource.SEED,), 0, 0),),
            page_acquisitions={_SOURCE: acquisition},
            provenance=(DiscoveryProvenance(_SOURCE, DiscoverySource.SEED, None, _SOURCE),),
            robots=RobotsResult(
                "https://mdsgroup.com/robots.txt",
                RobotsState.NETWORK_ERROR,
                acquisition,
                (),
                {_SOURCE: {crawler: None for crawler in DEFAULT_CRAWLERS}},
            ),
            sitemaps=(),
            total_discovered=1,
            total_audited=1,
            max_pages=max_pages,
            limit_reached=False,
        )


class _BrowserFailureRenderer:
    """Keep this unit test deterministic and independent from the live MDS route."""

    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult:
        return BrowserRenderResult(
            requested_url=url,
            final_url=_FINAL,
            http_status=None,
            content_type=None,
            rendered_html=None,
            browser_metadata={
                "engine": "fake-chromium",
                "profile": {"device": device.value},
                "navigation_trace": [
                    {"url": _SOURCE, "status": 301, "location": "http://www.mdsgroup.com/"},
                    {"url": "http://www.mdsgroup.com/", "status": 301, "location": _FINAL},
                ],
                "render_error": RenderErrorKind.NAVIGATION_ERROR.value,
            },
            error_kind=RenderErrorKind.NAVIGATION_ERROR,
        )


class SourceQualityAiTests(unittest.TestCase):
    def test_ai_receives_facts_once_and_cannot_replace_deterministic_tls_classification(self) -> None:
        calls: list[dict] = []

        def transport(_url, _headers, body, _timeout):
            request = json.loads(body.decode("utf-8"))
            calls.append(request)
            text = request["input"][0]["content"][0]["text"]
            self.assertIn("TLS_CERTIFICATE_ERROR", text)
            self.assertIn("https://mdsgroup.com/", text)
            self.assertIn("https://mds.pt/", text)
            return {
                "output_text": json.dumps(
                    {
                        "summary_pt": "A aquisição foi interrompida por incompatibilidade TLS no destino final.",
                        "likely_root_cause_pt": "O certificado apresentado não valida o hostname final segundo a evidência fornecida.",
                        "redirect_assessment_pt": "A troca de domínio pode ser intencional, mas a cadeia não é tecnicamente utilizável enquanto o TLS falhar.",
                        "recommended_actions_pt": [
                            "Corrigir o certificado do hostname final e validar novamente a cadeia de redirecionamento."
                        ],
                        "human_validation_required": True,
                    },
                    ensure_ascii=False,
                ),
                "usage": {
                    "input_tokens": 120,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 60,
                    "output_tokens_details": {"reasoning_tokens": 10},
                    "total_tokens": 180,
                },
            }

        provider = OpenAIProvider(api_key="test", transport=transport)
        with TemporaryDirectory() as directory:
            result = run_audit(
                _SOURCE,
                audits_root=directory,
                project_name="MDS infra AI",
                max_pages=1,
                semantic_provider=provider,
                discovery_engine=_BlockedDiscovery(),
                renderer=_BrowserFailureRenderer(),
            )
            self.assertEqual(len(calls), 1)
            artifact = result.audit_root / "artifacts" / "source-quality-ai.json"
            payload = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(payload["state"], "AVAILABLE")
            self.assertEqual(payload["provider"], "OPENAI")

            deterministic = json.loads(
                (result.audit_root / "artifacts" / "source-quality.json").read_text(encoding="utf-8")
            )
            self.assertEqual(deterministic["issues"][0]["classification"], "TLS_CERTIFICATE_ERROR")
            self.assertTrue(deterministic["issues"][0]["hard_blocker"])

            connection = sqlite3.connect(result.audit_root / "audit.db")
            connection.row_factory = sqlite3.Row
            try:
                attempts = connection.execute(
                    "SELECT status,semantic_contract_version,input_tokens,output_tokens FROM ai_provider_attempts"
                ).fetchall()
            finally:
                connection.close()
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0]["status"], "SUCCESS")
            self.assertEqual(attempts[0]["semantic_contract_version"], "SOURCE-QUALITY-AI-v1")
            self.assertEqual(attempts[0]["input_tokens"], 120)
            self.assertEqual(attempts[0]["output_tokens"], 60)


if __name__ == "__main__":
    unittest.main()
