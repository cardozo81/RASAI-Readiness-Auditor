from __future__ import annotations

from pathlib import Path
import re


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual < count:
        raise SystemExit(
            f"{path}: expected at least {count} occurrence(s), found {actual}: {old[:120]!r}"
        )
    target.write_text(text.replace(old, new, count), encoding="utf-8", newline="\n")


# 1. Scoring: materialize only the devices explicitly selected by the audit pipeline.
replace(
    "src/searchgeo/scoring.py",
    "    def score(self, *, audit_id: str, executions: Iterable[RuleExecution]) -> ScoringResult:\n"
    "        execution_list = tuple(executions)\n"
    "        scores: list[Score] = []\n"
    "        contributions: list[ScoreContribution] = []\n"
    "        for device in (DeviceContext.DESKTOP, DeviceContext.MOBILE):",
    "    def score(\n"
    "        self,\n"
    "        *,\n"
    "        audit_id: str,\n"
    "        executions: Iterable[RuleExecution],\n"
    "        devices: Iterable[DeviceContext] | None = None,\n"
    "    ) -> ScoringResult:\n"
    "        execution_list = tuple(executions)\n"
    "        selected_devices = tuple(dict.fromkeys(devices or (DeviceContext.DESKTOP, DeviceContext.MOBILE)))\n"
    "        if not selected_devices:\n"
    "            raise ValueError(\"scoring requires at least one device\")\n"
    "        scores: list[Score] = []\n"
    "        contributions: list[ScoreContribution] = []\n"
    "        for device in selected_devices:",
)
replace(
    "src/searchgeo/scoring.py",
    "        overall = {\n"
    "            device: self._overall(audit_id, device, tuple(score for score in scores if score.device is device))\n"
    "            for device in (DeviceContext.DESKTOP, DeviceContext.MOBILE)\n"
    "        }",
    "        overall = {\n"
    "            device: self._overall(audit_id, device, tuple(score for score in scores if score.device is device))\n"
    "            for device in selected_devices\n"
    "        }",
)
replace(
    "src/searchgeo/m9.py",
    "    engine = ScoringEngine()\n"
    "    calculated = engine.score(audit_id=audit_id, executions=executions)",
    "    engine = ScoringEngine()\n"
    "    active_devices = tuple(dict.fromkeys(\n"
    "        execution.device for execution in executions if execution.device is not None\n"
    "    ))\n"
    "    calculated = engine.score(\n"
    "        audit_id=audit_id,\n"
    "        executions=executions,\n"
    "        devices=active_devices or None,\n"
    "    )",
)
replace(
    "src/searchgeo/m9.py",
    "    recalculated = ScoringEngine().score(audit_id=audit_id, executions=executions)",
    "    recalculated = ScoringEngine().score(\n"
    "        audit_id=audit_id,\n"
    "        executions=executions,\n"
    "        devices=tuple(original.overall_by_device),\n"
    "    )",
)

# 2. Redirect recovery: if Chromium fails before it exposes response events, use the
# deterministic M2 redirect trace only as fallback input to the same strict same-site
# HTTPS-upgrade candidate function. TLS validation remains enabled.
replace(
    "src/searchgeo/browser_identity_renderer.py",
    "    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult:",
    "    def render(\n"
    "        self,\n"
    "        url: str,\n"
    "        device: DeviceContext,\n"
    "        *,\n"
    "        preflight_navigation_trace: Any = None,\n"
    "    ) -> BrowserRenderResult:",
)
replace(
    "src/searchgeo/browser_identity_renderer.py",
    "        original_trace = first.browser_metadata.get(\"navigation_trace\")\n"
    "        candidate = secure_upgrade_candidate(url, original_trace)\n"
    "        if candidate is None:\n"
    "            return first",
    "        original_trace = first.browser_metadata.get(\"navigation_trace\")\n"
    "        candidate_source = \"BROWSER_NAVIGATION_TRACE\"\n"
    "        candidate = secure_upgrade_candidate(url, original_trace)\n"
    "        if candidate is None:\n"
    "            candidate = secure_upgrade_candidate(url, preflight_navigation_trace)\n"
    "            candidate_source = \"M2_HTTP_PREFLIGHT_TRACE\"\n"
    "        if candidate is None:\n"
    "            return first",
)
replace(
    "src/searchgeo/browser_identity_renderer.py",
    "            \"trigger\": \"HTTPS_TO_HTTP_DOWNGRADE_AFTER_NAVIGATION_FAILURE\",\n"
    "            \"attempted\": True,",
    "            \"trigger\": \"HTTPS_TO_HTTP_DOWNGRADE_AFTER_NAVIGATION_FAILURE\",\n"
    "            \"candidate_source\": candidate_source,\n"
    "            \"preflight_navigation_trace\": preflight_navigation_trace if isinstance(preflight_navigation_trace, list) else [],\n"
    "            \"attempted\": True,",
)
replace(
    "src/searchgeo/m3.py",
    "                try:\n"
    "                    render_result = session_renderer.render(url, device)\n"
    "                except Exception:\n"
    "                    render_result = _unexpected_failure(url, device)",
    "                preflight_navigation_trace = [\n"
    "                    {\n"
    "                        \"url\": hop.source_url,\n"
    "                        \"status\": hop.status,\n"
    "                        \"location\": hop.location,\n"
    "                    }\n"
    "                    for hop in acquisition.redirects\n"
    "                ]\n"
    "                try:\n"
    "                    if isinstance(session_renderer, BrowserIdentityRenderer):\n"
    "                        render_result = session_renderer.render(\n"
    "                            url,\n"
    "                            device,\n"
    "                            preflight_navigation_trace=preflight_navigation_trace,\n"
    "                        )\n"
    "                    else:\n"
    "                        render_result = session_renderer.render(url, device)\n"
    "                except Exception:\n"
    "                    render_result = _unexpected_failure(url, device)",
)
replace(
    "src/searchgeo/m3.py",
    "                    \"redirect_count\": len(acquisition.redirects),\n"
    "                    \"network_error\": acquisition.network_error.kind.value if acquisition.network_error else None,",
    "                    \"redirect_count\": len(acquisition.redirects),\n"
    "                    \"redirects\": [\n"
    "                        {\n"
    "                            \"status\": hop.status,\n"
    "                            \"source_url\": hop.source_url,\n"
    "                            \"location\": hop.location,\n"
    "                            \"target_url\": hop.target_url,\n"
    "                        }\n"
    "                        for hop in acquisition.redirects\n"
    "                    ],\n"
    "                    \"network_error\": acquisition.network_error.kind.value if acquisition.network_error else None,",
)

# 3. Provider output: tolerate only a conventional fenced JSON object. Arbitrary prose,
# truncated JSON and schema/evidence violations remain failures.
replace(
    "src/searchgeo/semantic.py",
    "def _extract_json_payload(response: dict[str, Any]) -> Any:\n",
    "def _decode_json_text(text: str) -> Any:\n"
    "    candidate = text.strip().lstrip(\"\\ufeff\")\n"
    "    try:\n"
    "        return json.loads(candidate)\n"
    "    except json.JSONDecodeError as first_error:\n"
    "        lines = candidate.splitlines()\n"
    "        if len(lines) < 3:\n"
    "            raise first_error\n"
    "        opening = lines[0].strip().casefold()\n"
    "        closing = lines[-1].strip()\n"
    "        if opening not in {\"```\", \"```json\"} or closing != \"```\":\n"
    "            raise first_error\n"
    "        return json.loads(\"\\n\".join(lines[1:-1]).strip())\n"
    "\n"
    "\n"
    "def _extract_json_payload(response: dict[str, Any]) -> Any:\n",
)
replace(
    "src/searchgeo/semantic.py",
    "        return json.loads(response[\"output_text\"])",
    "        return _decode_json_text(response[\"output_text\"])",
)
replace(
    "src/searchgeo/semantic.py",
    "                return json.loads(content[\"text\"])",
    "                return _decode_json_text(content[\"text\"])",
)

# 4. Main SearchGEO report: surface audit-level limitations next to the non-consolidated
# score instead of forcing the analyst to infer the cause from another page.
replace(
    "src/searchgeo/searchgeo_readiness_reporting.py",
    "from collections import Counter\nfrom html import escape",
    "from collections import Counter\nfrom html import escape\nimport json",
)
replace(
    "src/searchgeo/searchgeo_readiness_reporting.py",
    "    content_context = _content_context_block(workspace, str(audit[\"audit_id\"]) if audit is not None else \"\")\n"
    "    nav = report_navigation.render_report_navigation(report_dir, SEARCHGEO_FILE)",
    "    content_context = _content_context_block(workspace, str(audit[\"audit_id\"]) if audit is not None else \"\")\n"
    "    limitations_block = _audit_limitations_block(audit)\n"
    "    nav = report_navigation.render_report_navigation(report_dir, SEARCHGEO_FILE)",
)
replace(
    "src/searchgeo/searchgeo_readiness_reporting.py",
    "<section class='notice'><strong>Compatibilidade metodológica:</strong> {PUBLIC_METHOD_VERSION} é a identidade pública desta apresentação. O cálculo persistido continua usando <code>{escape(engine_label)}</code>; esta mudança de relatório não recalcula auditorias, não altera pesos e não quebra comparabilidade histórica.</section>\n"
    "<section class='panel'>",
    "<section class='notice'><strong>Compatibilidade metodológica:</strong> {PUBLIC_METHOD_VERSION} é a identidade pública desta apresentação. O cálculo persistido continua usando <code>{escape(engine_label)}</code>; esta mudança de relatório não recalcula auditorias, não altera pesos e não quebra comparabilidade histórica.</section>\n"
    "{limitations_block}\n"
    "<section class='panel'>",
)
path = Path("src/searchgeo/searchgeo_readiness_reporting.py")
text = path.read_text(encoding="utf-8")
marker = "\n\ndef _overall_card(scores: list[sqlite3.Row], device: str) -> str:\n"
helper = '''

def _audit_limitations_block(audit: sqlite3.Row | None) -> str:
    if audit is None or "limitations" not in audit.keys():
        return ""
    raw = audit["limitations"]
    try:
        values = json.loads(str(raw or "[]"))
    except (json.JSONDecodeError, TypeError, ValueError):
        values = []
    if not isinstance(values, list):
        values = []
    items = [str(item).strip() for item in values if str(item).strip()]
    if not items:
        return ""
    rows = "".join(f"<li>{escape(item)}</li>" for item in items)
    return (
        "<section class='notice warn' data-audit-limitations='true'>"
        "<strong>Por que esta auditoria possui limitações:</strong>"
        f"<ul>{rows}</ul>"
        "<p>Essas condições reduzem Coverage/Consolidation; não são convertidas automaticamente em falha do website.</p>"
        "</section>"
    )
'''
if marker not in text:
    raise SystemExit("searchgeo_readiness_reporting.py: overall marker not found")
path.write_text(text.replace(marker, helper + marker, 1), encoding="utf-8", newline="\n")

# 5. Console UX: vertical action lists and V as the single navigation key for back/cancel.
replace(
    "src/searchgeo/interactive_console.py",
    "    print(\" 0. cancelar\")\n"
    "    while True:\n"
    "        raw = input(\"Escolha: \").strip()\n"
    "        if raw == \"0\":\n"
    "            return None",
    "    print(\"\\n V. Voltar\")\n"
    "    while True:\n"
    "        raw = input(\"Escolha: \").strip().upper()\n"
    "        if raw == \"V\":\n"
    "            return None",
)
replace(
    "src/searchgeo/interactive_console.py",
    "        action = input(\"\\nS=setar/alterar sessão | R=remover da sessão | P=persistir/remover credencial no Windows | H=ajuda/custo | V=voltar: \").strip().upper()",
    "        print(\"\\nAÇÕES\")\n"
    "        print(\"S. Setar/alterar sessão\")\n"
    "        print(\"R. Remover da sessão\")\n"
    "        print(\"P. Persistir/remover credencial no Windows\")\n"
    "        print(\"H. Ajuda / custo\")\n"
    "        print(\"V. Voltar\")\n"
    "        action = input(\"Escolha: \").strip().upper()",
)
replace(
    "src/searchgeo/interactive_console.py",
    "        print(\" M. Voltar ao menu\")",
    "        print(\" V. Voltar ao menu\")",
)
replace(
    "src/searchgeo/interactive_console.py",
    "        if choice == \"M\":",
    "        if choice == \"V\":",
)
replace(
    "src/searchgeo/console_environment.py",
    "            print(\"\\nS. Setar/alterar sessão | R. Remover da sessão | P. Persistência Windows/User | D. Documentação | V. Voltar\")",
    "            print(\"\\nAÇÕES\")\n"
    "            print(\"S. Setar/alterar sessão\")\n"
    "            print(\"R. Remover da sessão\")\n"
    "            print(\"P. Persistência Windows/User\")\n"
    "            print(\"D. Documentação\")\n"
    "            print(\"V. Voltar\")",
)
replace(
    "src/searchgeo/console_environment.py",
    "            print(\"\\nS. Setar/alterar | R. Remover override | D. Documentação | V. Voltar\")",
    "            print(\"\\nAÇÕES\")\n"
    "            print(\"S. Setar/alterar\")\n"
    "            print(\"R. Remover override\")\n"
    "            print(\"D. Documentação\")\n"
    "            print(\"V. Voltar\")",
)
replace(
    "src/searchgeo/console_environment.py",
    "        print(\"\\nD. Abrir documentação detalhada | V. Voltar\")",
    "        print(\"\\nAÇÕES\")\n"
    "        print(\"D. Abrir documentação detalhada\")\n"
    "        print(\"V. Voltar\")",
)
replace("docs/INTERACTIVE_CONSOLE.md", "M. Voltar ao menu", "V. Voltar ao menu")

# 6. Reports: solid backgrounds only. Semantic meaning remains in color/border/typography.
report_nav = Path("src/searchgeo/report_navigation.py")
nav_text = report_nav.read_text(encoding="utf-8")
nav_text = nav_text.replace(
    ".score-card.good{background:linear-gradient(180deg,#fff 0%,var(--soft-green) 165%)}.score-card.warn{background:linear-gradient(180deg,#fff 0%,var(--soft-amber) 165%)}.score-card.bad{background:linear-gradient(180deg,#fff 0%,var(--soft-red) 155%)}",
    ".score-card.good{background:var(--soft-green)}.score-card.warn{background:var(--soft-amber)}.score-card.bad{background:var(--soft-red)}",
)
nav_text = nav_text.replace(
    "background:linear-gradient(180deg,#f8f9fb 0%,#f1f3f7 100%)",
    "background:#f3f5f8",
)
report_nav.write_text(nav_text, encoding="utf-8", newline="\n")

semantics = Path("src/searchgeo/report_semantics.py")
sem_text = semantics.read_text(encoding="utf-8")
sem_text = sem_text.replace(
    "tr.result-state-warn{background:linear-gradient(90deg,var(--soft-amber),transparent 46%)}tr.result-state-bad{background:linear-gradient(90deg,var(--soft-red),transparent 46%)}tr.result-state-neutral{background:linear-gradient(90deg,var(--soft-blue),transparent 46%)}",
    "tr.result-state-warn{background:var(--soft-amber)}tr.result-state-bad{background:var(--soft-red)}tr.result-state-neutral{background:var(--soft-blue)}",
)
sem_text = sem_text.replace(
    "details.priority-high{border-left:4px solid var(--red);background:linear-gradient(90deg,var(--soft-red),#fbfbfc 28%)}details.priority-medium{border-left:4px solid var(--amber);background:linear-gradient(90deg,var(--soft-amber),#fbfbfc 28%)}",
    "details.priority-high{border-left:4px solid var(--red);background:var(--soft-red)}details.priority-medium{border-left:4px solid var(--amber);background:var(--soft-amber)}",
)
semantics.write_text(sem_text, encoding="utf-8", newline="\n")

# Regression coverage for the observed smoke failures and visual/navigation contract.
Path("tests/test_smoke_integrity_regressions.py").write_text(
    r'''from __future__ import annotations

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
''',
    encoding="utf-8",
    newline="\n",
)

# Guardrail for all report-source CSS declarations.
offenders: list[str] = []
for source in Path("src/searchgeo").glob("*.py"):
    if "report" not in source.name and "reporting" not in source.name:
        continue
    lower = source.read_text(encoding="utf-8").casefold()
    if "linear-gradient" in lower or "radial-gradient" in lower:
        offenders.append(str(source))
if offenders:
    raise SystemExit("gradient declarations remain in report sources: " + ", ".join(offenders))
