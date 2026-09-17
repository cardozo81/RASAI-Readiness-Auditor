from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from rasai.audit_fulfillment import list_work_items
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace


def _workspace(root: Path, audit_id: str = "AUD-CURRENT-CONTRACT") -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, audit_id)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=audit_id, project_name="current contract"))
    return workspace


def test_cwv_assessments_keep_needs_improvement_separate_from_poor() -> None:
    from rasai import m21_web_performance as m21

    result = m21._assess_cwv({"lcp_p75_ms": 3034.0, "inp_p75_ms": 396.0, "cls_p75": 0.90})

    assert result == {
        "lcp_assessment": "NEEDS_IMPROVEMENT",
        "inp_assessment": "NEEDS_IMPROVEMENT",
        "cls_assessment": "POOR",
        "cwv_assessment": "FAIL",
    }


def test_pagespeed_requests_portuguese_locale(monkeypatch) -> None:
    from rasai import m21_web_performance as m21

    captured: dict[str, str] = {}

    def request_json(*, service, request, timeout_seconds):
        captured["url"] = request.full_url
        return m21.HttpJsonResult(payload={}, http_status=200, duration_ms=1)

    monkeypatch.setattr(m21, "_request_json", request_json)
    client = m21.PageSpeedInsightsClient()
    client.run(
        url="https://example.test/",
        strategy="mobile",
        categories=("performance",),
        timeout_seconds=1.0,
    )

    query = parse_qs(urlparse(captured["url"]).query)
    assert query["locale"] == ["pt-BR"]


def test_first_party_apdex_scope_does_not_promote_unattributed_console_noise_to_frustration() -> None:
    from rasai import m25_apdex_experience as m25

    third_party_noise = SimpleNamespace(
        status="SUCCESS",
        javascript_error_count=0,
        console_error_count=2,
        request_failed_count=2,
        first_party_request_failed_count=0,
        http_error_count=0,
        first_party_http_error_count=0,
    )
    first_party_failure = SimpleNamespace(
        status="SUCCESS",
        javascript_error_count=0,
        console_error_count=0,
        request_failed_count=1,
        first_party_request_failed_count=1,
        http_error_count=0,
        first_party_http_error_count=0,
    )

    assert m25._qualifying_error(third_party_noise, "first-party") is False
    assert m25._qualifying_error(third_party_noise, "all") is True
    assert m25._qualifying_error(first_party_failure, "first-party") is True


def test_apdex_public_copy_matches_first_party_error_policy() -> None:
    from rasai import m25_reporting

    run = {"errors_affect_apdex": 1, "error_scope": "first-party"}
    note = m25_reporting._error_policy_note(run)
    contract = m25_reporting._measurement_contract_context({"error_scope": "first-party"})

    assert "recursos próprios" in note
    assert "Erros JavaScript e de console" in note
    assert "permanecem diagnósticos" in note
    assert "permanecem diagnósticos" in contract["runtime_errors"]
    assert "recursos próprios" in contract["request_errors"]


def test_semantic_rule_and_expected_condition_copy_is_canonical_pt_br() -> None:
    from rasai import m7
    from rasai import m16_root_cause as m16

    rule = next(item for item in m7._M7_DEFINITIONS if item.rule_id == "BR-GEO-041")

    assert rule.name == "Afirmações factuais materiais devem ser explicitamente identificáveis"
    assert m7._EXPECTED["BR-GEO-043"] == "afirmações numéricas, temporais e quantitativas contêm os qualificadores necessários"
    assert "claims" not in m16._CAUSE_SUMMARY["BR-GEO-043"].casefold()
    assert "publisher" not in m16._CAUSE_SUMMARY["BR-GEO-046"].casefold()


def test_limited_improvement_result_is_required_retryable_fulfillment(tmp_path: Path) -> None:
    from rasai import improvement_intelligence_runtime as runtime

    audit_id = "AUD-IMPROVEMENT-LIMITED"
    workspace = _workspace(tmp_path, audit_id)
    config = SimpleNamespace(
        provider="AUTO",
        model="",
        reasoning="auto",
        domains=("PERFORMANCE", "ACCESSIBILITY"),
        max_recommendations=30,
        language="pt-BR",
    )

    runtime._register_required_fulfillment(workspace, audit_id, config)
    runtime._project_fulfillment_result(
        workspace,
        audit_id,
        status="COMPLETE_WITH_LIMITATIONS",
        reason="AI_PROVIDER_UNAVAILABLE",
    )

    item = next(item for item in list_work_items(workspace, audit_id) if item.component == "IMPROVEMENT_INTELLIGENCE")
    assert item.required is True
    assert item.status == "FAILED_RETRYABLE"
    assert item.last_error_code == "COMPLETE_WITH_LIMITATIONS"
    assert item.last_error_message == "AI_PROVIDER_UNAVAILABLE"