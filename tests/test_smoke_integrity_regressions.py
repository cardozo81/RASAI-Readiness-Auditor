from __future__ import annotations

import json
from pathlib import Path
import unittest

from searchgeo.browser_identity_renderer import BrowserIdentityRenderer
from searchgeo.domain import DeviceContext, RuleExecution, RuleResult
from searchgeo.rendering import BrowserRenderResult, RenderErrorKind
from searchgeo.scoring import ScoringEngine
from searchgeo.semantic import _extract_json_payload


class _FakeBrowser:
    version = "152.0.0.0"


class _FakePlaywright:
    devices = {
        "Desktop Chrome": {
            "user_agent": "Mozilla/5.0 Chrome/152.0.0.0 Safari/537.36",
            "viewport": {"width": 1280, "height": 720},
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
        }
    }


class _EmptyTraceRecoveryRenderer(BrowserIdentityRenderer):
    def __init__(self) -> None:
        super().__init__()
        self._browser = _FakeBrowser()
        self._playwright = _FakePlaywright()
        self.browser_channel = "chrome"
        self.calls: list[str] = []

    def start(self):
        return None

    def _render_once(self, *, url, profile, options, identity):
        self.calls.append(url)
        if len(self.calls) == 1:
            return BrowserRenderResult(
                requested_url=url,
                final_url="https://mds.pt/",
                http_status=None,
                content_type=None,
                rendered_html=None,
                browser_metadata={"navigation_trace": []},
                error_kind=RenderErrorKind.NAVIGATION_TIMEOUT,
            )
        return BrowserRenderResult(
            requested_url=url,
            final_url="https://www.mdsgroup.com/pt/",
            http_status=200,
            content_type="text/html",
            rendered_html="<html><body>MDS</body></html>",
            browser_metadata={
                "navigation_trace": [
                    {"url": url, "status": 301, "location": "/pt/"},
                    {"url": "https://www.mdsgroup.com/pt/", "status": 200, "location": None},
                ]
            },
        )


def _execution(rule_id: str, device: DeviceContext | None) -> RuleExecution:
    from datetime import datetime, timezone

    return RuleExecution(
        rule_execution_id=f"REX-{rule_id}-{device.value if device else 'GLOBAL'}",
        audit_id="AUD-X",
        rule_id=rule_id,
        rule_version="1",
        page_id="P1",
        snapshot_id=None,
        device=device,
        result=RuleResult.PASS,
        observed_value={},
        expected_condition="fixture",
        evidence_ids=("EV-1",),
        executed_at=datetime.now(timezone.utc),
    )


class SmokeIntegrityRegressionTests(unittest.TestCase):
    def test_single_device_scoring_does_not_materialize_phantom_device(self) -> None:
        result = ScoringEngine().score(
            audit_id="AUD-X",
            executions=(
                _execution("BR-GEO-005", None),
                _execution("BR-GEO-025", DeviceContext.MOBILE),
            ),
            devices=(DeviceContext.MOBILE,),
        )
        self.assertEqual(set(result.overall_by_device), {DeviceContext.MOBILE})
        self.assertTrue(result.scores)
        self.assertTrue(all(item.device is DeviceContext.MOBILE for item in result.scores))

    def test_mds_recovery_can_use_m2_trace_when_browser_trace_is_empty(self) -> None:
        renderer = _EmptyTraceRecoveryRenderer()
        preflight = [
            {"url": "https://mdsgroup.com/", "status": 301, "location": "http://www.mdsgroup.com/"},
            {"url": "http://www.mdsgroup.com/", "status": 301, "location": "https://mds.pt/"},
        ]
        result = renderer.render(
            "https://mdsgroup.com/",
            DeviceContext.DESKTOP,
            preflight_navigation_trace=preflight,
        )
        self.assertTrue(result.succeeded)
        self.assertEqual(renderer.calls, ["https://mdsgroup.com/", "https://www.mdsgroup.com/"])
        recovery = result.browser_metadata["secure_redirect_recovery"]
        self.assertEqual(recovery["candidate_source"], "M2_HTTP_PREFLIGHT_TRACE")
        self.assertEqual(recovery["preflight_navigation_trace"], preflight)
        self.assertEqual(recovery["tls_validation"], "ENABLED")

    def test_fenced_provider_json_is_accepted_but_prose_is_not(self) -> None:
        self.assertEqual(
            _extract_json_payload({"output_text": "```json\n{\"a\": 1}\n```"}),
            {"a": 1},
        )
        with self.assertRaises(json.JSONDecodeError):
            _extract_json_payload({"output_text": "texto antes\n{\"a\": 1}"})

    def test_report_sources_have_no_gradients(self) -> None:
        for path in Path("src/searchgeo").glob("*.py"):
            if "report" not in path.name and "reporting" not in path.name:
                continue
            text = path.read_text(encoding="utf-8").casefold()
            self.assertNotIn("linear-gradient", text, path)
            self.assertNotIn("radial-gradient", text, path)

    def test_console_back_action_is_v_and_actions_are_not_pipe_compacted(self) -> None:
        interactive = Path("src/searchgeo/interactive_console.py").read_text(encoding="utf-8")
        environment = Path("src/searchgeo/console_environment.py").read_text(encoding="utf-8")
        self.assertNotIn("0. cancelar", interactive)
        self.assertNotIn("M. Voltar ao menu", interactive)
        self.assertNotIn("V=voltar:", interactive)
        self.assertNotIn(" | V. Voltar", environment)


if __name__ == "__main__":
    unittest.main()
