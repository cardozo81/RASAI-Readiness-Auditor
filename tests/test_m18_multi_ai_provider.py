from __future__ import annotations

import io
import json
import os
import sqlite3
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from rasai.acquisition import HttpClient
from rasai.audit_runner import run_audit
from rasai.device_context import DEVICE_CONTEXT_ENV
from rasai.discovery import DiscoveryEngine
from rasai.m18_ai import (
    DeepSeekProvider,
    MiMoProvider,
    OpenAIProvider,
    ProviderErrorClass,
    ProviderRoutingSession,
    ProviderState,
    ProviderUsage,
    SEMANTIC_RULE_IDS,
    build_semantic_provider,
    estimate_cost,
)
from rasai.semantic import SemanticEvidenceInput, SemanticInput
from rasai.ai_governance import begin_round, register_task, seal_evidence
from rasai.domain import Audit, Page, PageSnapshot, DeviceContext, DiscoverySource
from rasai.m18_persistence import M18Persistence, _durable_semantic_governance
from rasai.persistence import AuditPersistence, AuditWorkspace
from tests.test_m12_stable_baseline import _FixtureRenderer, _server


def _input(url: str = "https://example.com/produto", snapshot_id: str = "SNP-1") -> SemanticInput:
    return SemanticInput(
        snapshot_id=snapshot_id,
        page_url=url,
        title="Produto Alpha",
        main_content="Conteúdo factual sobre Produto Alpha.",
        structured_data=None,
        primary_language="pt-BR",
        market="BR",
        evidence=(SemanticEvidenceInput(
            evidence_id="EVD-1",
            evidence_type="TEXT_EXCERPT",
            source="test",
            observed_value={"text": "Produto Alpha"},
        ),),
    )


def _assessment(rule_id: str, evidence_ids: list[str] | None = None) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "result": "UNKNOWN",
        "confidence": 0.0,
        "evidence_ids": evidence_ids or [],
        "reasoning_summary": "Insufficient evidence in fixture.",
        "observed_value": {"summary": "", "details": []},
    }


def _payload(rule_ids: tuple[str, ...] = SEMANTIC_RULE_IDS) -> dict[str, object]:
    return {
        "assessments": [_assessment(rule_id) for rule_id in rule_ids],
        "entities": [],
        "primary_intent": None,
        "secondary_intents": [],
    }


def _success_transport(calls: list[dict[str, object]] | None = None):
    def transport(url, headers, body, timeout):
        if calls is not None:
            calls.append({"url": url, "headers": headers, "body": json.loads(body), "timeout": timeout})
        return {
            "output_text": json.dumps(_payload()),
            "usage": {
                "input_tokens": 100,
                "input_tokens_details": {"cached_tokens": 20},
                "output_tokens": 50,
                "output_tokens_details": {"reasoning_tokens": 10},
                "total_tokens": 150,
            },
        }
    return transport


def _http_error(status: int, *, error_type: str, error_code: str):
    headers = Message()
    headers["x-request-id"] = "req_safe_1"
    body = io.BytesIO(json.dumps({"error": {"type": error_type, "code": error_code, "message": "SECRET-MESSAGE"}}).encode())
    return HTTPError("https://provider.invalid/responses", status, "error", headers, body)


class M18ProviderTests(unittest.TestCase):
    def test_configuration_supports_each_provider_and_auto_order(self) -> None:
        openai = build_semantic_provider("openai", env={"OPENAI_API_KEY": "x"})
        deepseek = build_semantic_provider("deepseek", env={"DEEPSEEK_API_KEY": "x"})
        mimo = build_semantic_provider("mimo", env={"MIMO_API_KEY": "x"})
        self.assertEqual((openai.name, openai.model), ("OPENAI", "gpt-5.6-terra"))
        self.assertEqual((deepseek.name, deepseek.model), ("DEEPSEEK", "deepseek-v4-pro"))
        self.assertEqual((mimo.name, mimo.model, mimo.reasoning_profile), ("MIMO", "mimo-v2.5-pro", "THINKING_ENABLED"))

        auto = build_semantic_provider("auto", env={
            "OPENAI_API_KEY": "x", "DEEPSEEK_API_KEY": "x", "MIMO_API_KEY": "x",
        })
        self.assertEqual([item.name for item in auto.providers], ["OPENAI", "DEEPSEEK", "MIMO"])
        self.assertEqual([item.policy.rank for item in auto.providers], [2, 3, 4])

    def test_auto_excludes_missing_and_invalid_configuration(self) -> None:
        auto = build_semantic_provider("auto", env={
            "OPENAI_API_KEY": "x",
            "MIMO_API_KEY": "x",
            "RASAI_MIMO_MODEL": "bad-model",
        })
        self.assertEqual([item.name for item in auto.providers], ["OPENAI"])
        self.assertEqual(auto.excluded_configurations, ("MIMO:INVALID_CONFIGURATION",))

    def test_provider_requests_use_expected_structured_modes_and_reasoning(self) -> None:
        calls: list[dict[str, object]] = []
        for provider in (
            OpenAIProvider(api_key="x", transport=_success_transport(calls)),
            DeepSeekProvider(api_key="x", transport=_success_transport(calls)),
            MiMoProvider(api_key="x", transport=_success_transport(calls)),
        ):
            result = provider.analyze(_input(snapshot_id=f"SNP-{provider.name}"))
            self.assertEqual(result.state, ProviderState.AVAILABLE)
        self.assertEqual(calls[0]["body"]["text"]["format"]["type"], "json_schema")
        self.assertTrue(calls[0]["body"]["text"]["format"]["strict"])
        self.assertEqual(calls[1]["body"]["text"]["format"]["type"], "json_schema")
        self.assertNotIn("strict", calls[1]["body"]["text"]["format"])
        self.assertEqual(calls[2]["body"]["text"]["format"]["type"], "json_object")
        self.assertEqual(calls[2]["body"]["reasoning"]["effort"], "high")

    def test_usage_and_estimated_cost_are_normalized(self) -> None:
        provider = OpenAIProvider(api_key="x", transport=_success_transport())
        result = provider.analyze(_input())
        self.assertEqual(result.usage, ProviderUsage(100, 20, 50, 10, 150))
        attempts = provider.attempt_history()
        self.assertEqual(len(attempts), 1)
        self.assertIsNotNone(attempts[0].estimated_cost)
        self.assertEqual(attempts[0].cost_currency, "USD")
        amount, currency, version = estimate_cost(
            "OPENAI", "gpt-5.6-terra", ProviderUsage(100, 20, 50, 10, 150), datetime.now(timezone.utc)
        )
        self.assertIsNotNone(amount)
        self.assertEqual(currency, "USD")
        self.assertTrue(version)
        missing, _, _ = estimate_cost("OPENAI", "gpt-5.6-terra", ProviderUsage(100, None, 50, None, 150), datetime.now(timezone.utc))
        self.assertIsNone(missing)

    def test_contract_rejects_partial_invalid_evidence_and_empty_output(self) -> None:
        partial = OpenAIProvider(api_key="x", transport=lambda *_: {"output_text": json.dumps(_payload(SEMANTIC_RULE_IDS[:-1]))})
        self.assertEqual(partial.analyze(_input()).diagnostic.error_class, ProviderErrorClass.CONTRACT_ERROR)

        invented_payload = _payload()
        invented_payload["assessments"][0]["evidence_ids"] = ["INVENTED"]
        invented = OpenAIProvider(api_key="x", transport=lambda *_: {"output_text": json.dumps(invented_payload)})
        self.assertEqual(invented.analyze(_input()).diagnostic.error_class, ProviderErrorClass.CONTRACT_ERROR)

        invalid = OpenAIProvider(api_key="x", transport=lambda *_: {"output_text": "{not-json"})
        self.assertEqual(invalid.analyze(_input()).diagnostic.error_class, ProviderErrorClass.INVALID_RESPONSE)

        empty = OpenAIProvider(api_key="x", transport=lambda *_: {})
        self.assertEqual(empty.analyze(_input()).diagnostic.error_class, ProviderErrorClass.EMPTY_RESPONSE)

    def test_http_and_network_errors_are_sanitized_and_classified(self) -> None:
        def quota(*_):
            raise _http_error(429, error_type="insufficient_quota", error_code="credit_balance_exhausted")
        result = OpenAIProvider(api_key="SUPER-SECRET-KEY", transport=quota).analyze(_input())
        self.assertEqual(result.diagnostic.error_class, ProviderErrorClass.CREDIT_ERROR)
        self.assertNotIn("SUPER-SECRET-KEY", result.reason)
        self.assertNotIn("SECRET-MESSAGE", result.reason)

        def auth(*_):
            raise _http_error(401, error_type="invalid_api_key", error_code="invalid_api_key")
        self.assertEqual(OpenAIProvider(api_key="x", transport=auth).analyze(_input()).diagnostic.error_class, ProviderErrorClass.AUTH_ERROR)

        def network(*_):
            raise URLError("offline")
        self.assertEqual(OpenAIProvider(api_key="x", transport=network).analyze(_input()).diagnostic.error_class, ProviderErrorClass.NETWORK_ERROR)

    def test_auto_failover_quarantines_and_promotes_fallback(self) -> None:
        calls = {"OPENAI": 0, "DEEPSEEK": 0, "MIMO": 0}
        def openai_fail(*_):
            calls["OPENAI"] += 1
            raise _http_error(429, error_type="insufficient_quota", error_code="credit_balance_exhausted")
        def deepseek_success(*args):
            calls["DEEPSEEK"] += 1
            return _success_transport()(*args)
        def mimo_success(*args):
            calls["MIMO"] += 1
            return _success_transport()(*args)

        router = ProviderRoutingSession((
            OpenAIProvider(api_key="x", transport=openai_fail),
            DeepSeekProvider(api_key="x", transport=deepseek_success),
            MiMoProvider(api_key="x", transport=mimo_success),
        ))
        result = router.analyze(_input("https://example.com/a", "SNP-A-D"))
        self.assertEqual(result.provider, "DEEPSEEK")
        self.assertEqual(calls, {"OPENAI": 1, "DEEPSEEK": 1, "MIMO": 0})
        snapshot = router.session_snapshot()
        self.assertEqual(snapshot["provider_states"]["OPENAI"], "QUARANTINED_FOR_AUDIT")
        self.assertEqual(snapshot["effective_provider"], "DEEPSEEK")

        router.analyze(_input("https://example.com/b", "SNP-B-D"))
        self.assertEqual(calls["OPENAI"], 1)
        self.assertEqual(calls["DEEPSEEK"], 2)

    def test_url_lock_prevents_cross_provider_mobile_completion(self) -> None:
        deepseek_calls = 0
        mimo_calls = 0
        def deepseek(*args):
            nonlocal deepseek_calls
            deepseek_calls += 1
            if deepseek_calls == 1:
                return _success_transport()(*args)
            raise TimeoutError()
        def mimo(*args):
            nonlocal mimo_calls
            mimo_calls += 1
            return _success_transport()(*args)

        router = ProviderRoutingSession((
            DeepSeekProvider(api_key="x", transport=deepseek),
            MiMoProvider(api_key="x", transport=mimo),
        ))
        url = "https://example.com/a"
        self.assertEqual(router.analyze(_input(url, "SNP-A-D")).provider, "DEEPSEEK")
        recovered_mobile = router.analyze(_input(url, "SNP-A-M"))
        self.assertEqual(recovered_mobile.state, ProviderState.AVAILABLE)
        self.assertEqual(recovered_mobile.provider, "MIMO")
        self.assertEqual(mimo_calls, 1)
        attempts = router.consume_attempts()
        self.assertTrue(any(item.fallback_from_provider == "DEEPSEEK" for item in attempts))
        self.assertEqual(router.analyze(_input("https://example.com/b", "SNP-B-D")).provider, "MIMO")
        self.assertEqual(mimo_calls, 2)

    def test_success_stops_chain_and_chain_exhaustion_is_explicit(self) -> None:
        mimo_calls = 0
        def mimo(*args):
            nonlocal mimo_calls
            mimo_calls += 1
            return _success_transport()(*args)
        router = ProviderRoutingSession((
            OpenAIProvider(api_key="x", transport=_success_transport()),
            DeepSeekProvider(api_key="x", transport=_success_transport()),
            MiMoProvider(api_key="x", transport=mimo),
        ))
        self.assertEqual(router.analyze(_input()).provider, "OPENAI")
        self.assertEqual(mimo_calls, 0)
        self.assertEqual(len(router.attempt_history()), 1)

        def fail(*_):
            raise TimeoutError()
        exhausted = ProviderRoutingSession((
            DeepSeekProvider(api_key="x", transport=fail),
            MiMoProvider(api_key="x", transport=fail),
        ))
        result = exhausted.analyze(_input())
        self.assertEqual(result.reason, "AI_PROVIDER_CHAIN_EXHAUSTED")
        self.assertTrue(all(value == "QUARANTINED_FOR_AUDIT" for value in exhausted.session_snapshot()["provider_states"].values()))

    def test_explicit_provider_quarantine_blocks_retries_across_urls(self) -> None:
        calls = 0

        def fail(*_):
            nonlocal calls
            calls += 1
            raise TimeoutError()

        provider = OpenAIProvider(api_key="x", transport=fail)
        first = provider.analyze(_input("https://example.com/a", "SNP-A"))
        second = provider.analyze(_input("https://example.com/b", "SNP-B"))

        self.assertEqual(first.state, ProviderState.UNAVAILABLE)
        self.assertEqual(second.state, ProviderState.UNAVAILABLE)
        self.assertEqual(second.reason, "AI_PROVIDER_UNAVAILABLE:PROVIDER_QUARANTINED")
        self.assertEqual(calls, 2)
        snapshot = provider.session_snapshot()
        self.assertEqual(snapshot["strategy"], "SINGLE_PROVIDER")
        self.assertEqual(snapshot["provider_states"]["OPENAI"], "QUARANTINED_FOR_AUDIT")
        self.assertEqual(len(provider.attempt_history()), 2)

    def test_run_audit_persists_attempts_and_materializes_ai_telemetry_page(self) -> None:
        with _server() as origin, TemporaryDirectory() as directory:
            html = f"""<!doctype html><html lang='pt-BR'><head><title>Guia M18</title>
<meta name='description' content='Guia técnico.'><link rel='canonical' href='{origin}/'>
<script type='application/ld+json'>{{"@context":"https://schema.org","@type":"Article","headline":"Guia M18"}}</script>
</head><body><main><h1>Guia M18</h1><h2>Visão geral</h2><p>Conteúdo técnico verificável para integração M18.</p></main></body></html>"""
            secret = "M18-INTEGRATION-SECRET"
            provider = OpenAIProvider(api_key=secret, transport=_success_transport())
            result = run_audit(
                f"{origin}/",
                audits_root=Path(directory),
                project_name="Integração M18",
                max_pages=1,
                semantic_provider=provider,
                discovery_engine=DiscoveryEngine(HttpClient(timeout=1)),
                renderer=_FixtureRenderer(html),
                lazy_probe=lambda url, device: None,
            )

            connection = sqlite3.connect(result.audit_root / "audit.db")
            connection.row_factory = sqlite3.Row
            try:
                attempts = connection.execute(
                    "SELECT provider,model,status,input_tokens,output_tokens,estimated_cost FROM ai_provider_attempts WHERE audit_id=? ORDER BY started_at",
                    (result.audit_id,),
                ).fetchall()
                self.assertEqual(len(attempts), 2)
                self.assertTrue(all(row["provider"] == "OPENAI" for row in attempts))
                self.assertTrue(all(row["model"] == "gpt-5.6-terra" for row in attempts))
                self.assertTrue(all(row["status"] == "SUCCESS" for row in attempts))
                self.assertTrue(all(row["input_tokens"] == 100 for row in attempts))
                self.assertTrue(all(row["output_tokens"] == 50 for row in attempts))
                self.assertTrue(all(row["estimated_cost"] is not None for row in attempts))
                session = connection.execute(
                    "SELECT strategy,effective_provider,effective_model,status FROM ai_audit_sessions WHERE audit_id=?",
                    (result.audit_id,),
                ).fetchone()
                self.assertIsNotNone(session)
                self.assertEqual(session["strategy"], "SINGLE_PROVIDER")
                self.assertEqual(session["effective_provider"], "OPENAI")
                self.assertEqual(session["effective_model"], "gpt-5.6-terra")
            finally:
                connection.close()

            from rasai.catalog_report_site import materialize_catalog_report_site

            workspace = AuditWorkspace.open(result.audit_root)
            report_root = materialize_catalog_report_site(
                audit_id=result.audit_id,
                workspace=workspace,
            ).parent
            ai = (report_root / "ai-integrations.html").read_text(encoding="utf-8")
            self.assertIn("IA e integrações", ai)
            self.assertIn("OPENAI", ai)
            self.assertIn("gpt-5.6-terra", ai)
            self.assertNotIn(secret, ai)
            self.assertFalse((result.audit_root / "report").exists())

    def test_mobile_device_context_limits_semantic_provider_to_one_context_per_page(self) -> None:
        with _server() as origin, TemporaryDirectory() as directory:
            html = """<!doctype html><html lang='pt-BR'><head><title>Mobile AI</title></head>
<body><main><h1>Mobile AI</h1><p>Conteúdo técnico para validar custo por dispositivo.</p></main></body></html>"""
            provider = OpenAIProvider(api_key="x", transport=_success_transport())
            with patch.dict(os.environ, {DEVICE_CONTEXT_ENV: "mobile"}, clear=False):
                result = run_audit(
                    f"{origin}/",
                    audits_root=Path(directory),
                    project_name="M18 mobile only",
                    max_pages=1,
                    semantic_provider=provider,
                    discovery_engine=DiscoveryEngine(HttpClient(timeout=1)),
                    renderer=_FixtureRenderer(html),
                    lazy_probe=lambda url, device: None,
                )

            connection = sqlite3.connect(result.audit_root / "audit.db")
            try:
                devices = {row[0] for row in connection.execute("SELECT DISTINCT device FROM page_snapshots")}
                attempts = list(connection.execute("SELECT device FROM ai_provider_attempts WHERE audit_id=?", (result.audit_id,)))
            finally:
                connection.close()
            self.assertEqual(devices, {"MOBILE"})
            self.assertEqual(len(attempts), 1)
            self.assertEqual({row[0] for row in attempts}, {"MOBILE"})
            self.assertFalse((result.audit_root / "report").exists())
            from rasai.catalog_report_site import materialize_catalog_report_site
            report_root = materialize_catalog_report_site(
                audit_id=result.audit_id,
                workspace=AuditWorkspace.open(result.audit_root),
            ).parent
            capture = (report_root / "capture-context.html").read_text(encoding="utf-8")
            self.assertIn("Dispositivo móvel", capture)


if __name__ == "__main__":
    unittest.main()

def test_durable_semantic_governance_resolves_round_for_provider_attempt(tmp_path: Path) -> None:
    audit_id = "AUD-M18-GOV"
    workspace = AuditWorkspace.create(tmp_path, audit_id)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=audit_id, project_name="m18 governance"))
        persistence.pages.add(Page(
            "P1",
            audit_id,
            "https://example.test/",
            "https://example.test/",
            (DiscoverySource.SEED,),
            0,
        ))
        persistence.snapshots.add(PageSnapshot(
            snapshot_id="SNP-GOV",
            page_id="P1",
            device=DeviceContext.MOBILE,
            requested_url="https://example.test/",
            final_url="https://example.test/",
            captured_at=datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc),
            http_status=200,
        ))

    evidence = seal_evidence(
        workspace=workspace,
        audit_id=audit_id,
        evidence_ids=(),
        collection_states={"CORE": "SUCCESS"},
    )
    task_id = register_task(
        workspace=workspace,
        audit_id=audit_id,
        purpose="SEMANTIC_M7",
        scope_type="SNAPSHOT",
        scope_key="SNP-GOV",
        evidence_snapshot_id=evidence.evidence_snapshot_id,
        requirements=("BR-GEO-028",),
    )
    round_id = begin_round(
        workspace=workspace,
        ai_task_id=task_id,
        requested_requirements=("BR-GEO-028",),
        input_payload={"snapshot_id": "SNP-GOV"},
    )

    connection = sqlite3.connect(workspace.database)
    try:
        started_at = connection.execute(
            "SELECT started_at FROM ai_request_rounds WHERE ai_round_id=?",
            (round_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
    attempt = __import__("rasai.m18_ai", fromlist=["ProviderAttempt"]).ProviderAttempt(
        provider="OPENAI",
        model="gpt-test",
        reasoning_profile="NONE",
        provider_rank=1,
        attempt_index=1,
        snapshot_id="SNP-GOV",
        url="https://example.test/",
        started_at=started,
        finished_at=started,
        duration_ms=0,
        status=__import__("rasai.m18_ai", fromlist=["AttemptStatus"]).AttemptStatus.SUCCESS,
        usage=ProviderUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        estimated_cost=0.001,
        cost_currency="USD",
        pricing_version="test",
        request_message_summary="semantic",
        request_payload_hash="hash",
        semantic_contract_version="M18-SEMANTIC-22-v1",
    )

    with M18Persistence(workspace) as store:
        assert _durable_semantic_governance(
            store,
            audit_id=audit_id,
            attempt=attempt,
        ) == ("SEMANTIC_M7", task_id, round_id)
