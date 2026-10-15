from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rasai import ai_execution_state
from rasai.ai_exchange_log import AiExchangeRecorder, ContextInterpretationRecord
from rasai.editorial_risk_context import build_editorial_risk_context, ymyl_prompt_directive
from rasai.improvement_intelligence import (
    _semantic_risk_findings,
    build_improvement_request_context,
)
from rasai.accepted_audit_refinements import (
    _repair_scope_findings,
    _ymyl_analysis_context_html,
)
from rasai.semantic_coherence_reporting import _ymyl_alignment_html
from rasai.faq_observation_601 import faq_observation_html, inspect_faq_html
from rasai import catalog_report_analysis



def test_faq_snapshot_distinguishes_collapsed_unmounted_from_absent_answer() -> None:
    html = (
        '<a role="button" aria-controls="FrequentlyAsked-question1" '
        'aria-expanded="false">Pergunta um</a>'
        '<a role="button" aria-controls="FrequentlyAsked-question2" '
        'aria-expanded="false">Pergunta dois</a>'
        '<div id="FrequentlyAsked-question2">Resposta existente no DOM</div>'
        '<a role="button" aria-controls="OtherAccordion-1" '
        'aria-expanded="false">Plano de cobertura</a>'
    )
    assert inspect_faq_html(html) == {
        "controls": 2, "ambiguous": 0, "collapsed": 2, "unmounted": 1, "mounted": 1,
        "mounted_with_text": 1, "mounted_without_text": 0,
    }



def test_faq_mounted_empty_panel_is_not_called_answered() -> None:
    html = (
        '<button aria-controls="faq-1" aria-expanded="false">Pergunta?</button>'
        '<div id="faq-1"><script>var answer = "not visible"</script>'
        '<span> </span></div>'
        '<button aria-controls="faq-2" aria-expanded="false">Pergunta dois?</button>'
        '<div id="faq-2"><span>Resposta recuperável</span></div>'
    )
    assert inspect_faq_html(html) == {
        "controls": 2, "ambiguous": 0, "collapsed": 2, "unmounted": 0, "mounted": 2,
        "mounted_with_text": 1, "mounted_without_text": 1,
    }




def test_faq_conflicting_accordion_states_do_not_invent_visibility() -> None:
    html = (
        '<button aria-controls="faq-x" aria-expanded="false">Pergunta?</button>'
        '<button aria-controls="faq-x" aria-expanded="true">Pergunta?</button>'
        '<div id="faq-x">Resposta DOM</div>'
        '<button aria-controls="faq-y" aria-expanded="false">Outra</button>'
    )
    assert inspect_faq_html(html) == {
        "controls": 2, "ambiguous": 1, "collapsed": 1,
        "unmounted": 1, "mounted": 0,
        "mounted_with_text": 0, "mounted_without_text": 0,
    }


def test_faq_duplicated_panel_ids_and_aria_attributes_are_ambiguous() -> None:
    html = (
        '<button aria-controls="faq-x" aria-expanded="false">Pergunta?</button>'
        '<div id="faq-x">Texto um</div>'
        '<div id="faq-x">Texto dois</div>'
        '<button aria-controls="faq-y" aria-expanded="false" '
        'aria-expanded="true">Pergunta y</button>'
    )
    assert inspect_faq_html(html) == {
        "controls": 2, "ambiguous": 2, "collapsed": 0,
        "unmounted": 0, "mounted": 0,
        "mounted_with_text": 0, "mounted_without_text": 0,
    }





def test_opted_in_faq_receipt_requires_signed_collector_source_and_matching_dom() -> None:
    import hmac
    import json
    from hashlib import sha256

    from rasai.faq_interaction_receipt_601 import verify_faq_interaction_receipt

    key = b"separately-configured-test-collector-key-2026"
    before = '<button aria-controls="faq-x" aria-expanded="false">Pergunta</button>'
    later = (
        '<button aria-controls="faq-x" aria-expanded="true">Pergunta</button>'
        '<div id="faq-x">Resposta efetivamente no DOM após ação.</div>'
    )
    receipt = {
        "receipt_id": "FAQ-EV-1",
        "collector_id": "COLLECTOR-APPROVED",
        "target_id": "faq-x",
        "document_url": "https://example.test/seguro",
        "before_sha256": sha256(before.encode("utf-8")).hexdigest(),
        "after_sha256": sha256(later.encode("utf-8")).hexdigest(),
        "before_utc": "2026-10-14T20:00:00Z",
        "after_utc": "2026-10-14T20:00:01Z",
        "action": "FAQ_DISCLOSURE_BUTTON_CLICK",
        "target_opt_in": True,
        "isolated_unauthenticated_context": True,
        "network_blocked_after_load": True,
    }
    def mac(r):
        encoded = json.dumps(
            r, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hmac.new(key, encoded, sha256).hexdigest()

    inputs = {
        "trusted_key": key,
        "permitted_collector_ids": frozenset({"COLLECTOR-APPROVED"}),
    }
    valid = mac(receipt)
    observed = verify_faq_interaction_receipt(
        before, later, receipt=receipt, receipt_mac=valid, **inputs,
    )
    assert observed["status"] == "ATTESTED_ISOLATED_FAQ_INTERACTION_OBSERVATION"
    assert observed["action_attested_by_trusted_collector"] is True
    assert observed["text_recoverable_after_action"] is True
    assert observed["before_state"] == "COLLAPSED_UNMOUNTED"
    assert observed["later_state"] == "EXPANDED_DOM_TEXT"
    assert not observed["crawler_discovery_verified"]
    assert not observed["score_change_authorized"]
    assert observed["audit_writes"] == observed["new_audit_requests"] == 0

    for tampered in (
        {**receipt, "after_sha256": "0" * 64},
        {**receipt, "target_opt_in": False},
        {**receipt, "collector_id": "COLLECTOR-UNAUTHORIZED"},
        {**receipt, "collector_id": []},
        {**receipt, "after_utc": "2026-10-14T20:20:00Z"},
        {**receipt, "network_blocked_after_load": False},
        {**receipt, "target_id": "faq-other"},
        {**receipt, "extra": "untrusted"},
    ):
        out = verify_faq_interaction_receipt(
            before, later, receipt=tampered, receipt_mac=valid, **inputs,
        )
        assert out["status"] == "INTERACTION_NOT_ATTESTED"
        assert not out["action_attested_by_trusted_collector"]
    assert verify_faq_interaction_receipt(
        before, later, receipt=receipt, receipt_mac="0" * 64, **inputs,
    )["status"] == "INTERACTION_NOT_ATTESTED"
    assert verify_faq_interaction_receipt(
        before, later + " ", receipt=receipt, receipt_mac=valid, **inputs,
    )["status"] == "INTERACTION_NOT_ATTESTED"

    no_answer = '<button aria-controls="faq-x" aria-expanded="true">Pergunta</button>'
    none_receipt = {
        **receipt, "after_sha256": sha256(no_answer.encode()).hexdigest(),
    }
    observed_none = verify_faq_interaction_receipt(
        before, no_answer, receipt=none_receipt,
        receipt_mac=mac(none_receipt), **inputs,
    )
    assert observed_none["status"] == "ATTESTED_ISOLATED_FAQ_INTERACTION_OBSERVATION"
    assert not observed_none["text_recoverable_after_action"]
    assert not observed_none["editorial_answer_absence_proven"]



def test_faq_paired_dom_text_does_not_certify_click_or_crawler_discovery() -> None:
    from rasai.faq_transition_policy_601 import compare_faq_dom_views as compare

    url = "https://example.test/seguro"
    before = (
        '<button aria-controls="faq-life" aria-expanded="false">'
        'Pergunta frequente</button>'
    )
    later = (
        '<button aria-controls="faq-life" aria-expanded="true">'
        'Pergunta frequente</button><div id="faq-life">Resposta no DOM posterior</div>'
    )
    result = compare(
        before, later, target_id="faq-life",
        before_url=url, later_url=url,
    )
    assert result["status"] == "DESCRIPTIVE_SNAPSHOT_PAIR_ONLY"
    assert result["before_state"] == "COLLAPSED_UNMOUNTED"
    assert result["later_state"] == "EXPANDED_DOM_TEXT"
    assert result["reason"] == "TEXT_PRESENT_IN_LATER_DOM_NOT_CLICK_PROOF"
    assert not result["action_or_click_verified"]
    assert not result["crawler_discovery_verified"]
    assert not result["editorial_answer_absence_proven"]
    assert not result["score_change_authorized"]


def test_faq_paired_dom_abstains_on_wrong_url_and_ambiguous_panel() -> None:
    from rasai.faq_transition_policy_601 import compare_faq_dom_views as compare

    pre = '<button aria-controls="faq-x" aria-expanded="false">Q</button>'
    post = (
        '<button aria-controls="faq-x" aria-expanded="true">Q</button>'
        '<div id="faq-x">Um</div><div id="faq-x">Dois</div>'
    )
    params = {"target_id": "faq-x", "before_url": "https://example.test/a",
              "later_url": "https://example.test/a"}
    assert compare(pre, post, **params)["reason"] == "DOM_CONTROL_OR_PANEL_AMBIGUOUS"
    assert compare(
        pre, post, **{**params, "later_url": "https://example.test/b"},
    )["status"] == "NOT_COMPARABLE"
    assert compare(
        pre, '<button aria-controls="faq-x" aria-expanded="false">Q</button>',
        **params,
    )["reason"] == "LATER_PANEL_NOT_EXPANDED"
    empty = '<button aria-controls="faq-x" aria-expanded="true">Q</button>'
    assert compare(pre, empty, **params)["reason"] == "LATER_DOM_WITHOUT_RECOVERABLE_TEXT"
    assert compare(pre, empty, **params)["editorial_answer_absence_proven"] is False



def test_faq_readonly_report_does_not_claim_editorial_absence(tmp_path: Path) -> None:
    db = tmp_path / "audit.db"
    artifact = tmp_path / "artifacts" / "rendered" / "P1" / "mobile" / "S1.html"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        '<a role="button" aria-controls="FrequentlyAsked-q1" '
        'aria-expanded="false">Uma pergunta</a>', encoding="utf-8",
    )
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
        connection.execute(
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT, page_id TEXT, rendered_artifact_ref TEXT)"
        )
        connection.execute("INSERT INTO pages VALUES('P1','AUD-1')")
        connection.execute(
            "INSERT INTO page_snapshots VALUES(?,?,?)",
            ("S1", "P1", "artifacts/rendered/P1/mobile/S1.html"),
        )
    previous_db = db.read_bytes()
    previous_html = artifact.read_bytes()
    report = faq_observation_html(db, "AUD-1")
    assert "1 painel(is) não estavam presentes no DOM" in report
    assert "não prova ausência editorial" in report
    assert "também não comprova acesso sem interação" in report
    assert "não altera BR-GEO-039, BR-GEO-049" in report
    assert "Proveniência por captura" in report
    assert "<code>S1</code>" in report
    assert "<td>1</td><td>0</td><td>1</td><td>1</td>" in report
    assert db.read_bytes() == previous_db
    assert artifact.read_bytes() == previous_html
    assert faq_observation_html(db, "AUD-OTHER") == ""


def test_faq_diagnostic_rejects_out_of_root_artifact(tmp_path: Path) -> None:
    from rasai.faq_observation_601 import _safe_rendered_file

    outside = tmp_path.parent / "outside-faq.html"
    assert _safe_rendered_file(tmp_path, "../outside-faq.html") is None
    assert _safe_rendered_file(tmp_path, "artifacts/rendered/../outside-faq.html") is None




def test_claim_verification_requires_attested_primary_source_exact_scope_and_version() -> None:
    from datetime import date
    from hashlib import sha256
    from rasai.claim_source_verification import classify_claim

    payload = "Condições do produto: ativação após 24 horas. Documento de teste.".encode("utf-8")
    when = date(2026, 10, 14)
    claim = "ativação em 24 horas"
    receipt = {
        "source_url": "https://example.test/condicoes-oficiais",
        "document_sha256": sha256(payload).hexdigest(),
        "effective_from": "2026-01-01",
        "effective_until": "2026-12-31",
        "reviewed_on": "2026-10-10",
        "product_scope": "SEG-VIDA-X",
        "claim_text": claim,
        "document_version": "2026-01",
        "issuer": "Seguradora de teste",
        "reviewer_receipt_id": "REV-001",
        "independent_source_authenticity_verified": True,
        "matched_excerpt": "ativação após 24 horas",
        "review_decision": "CORROBORATES",
    }
    kwargs = {
        "product_scope": "SEG-VIDA-X",
        "at_date": when,
        "primary_bytes": payload,
    }
    verified = classify_claim(claim, review=receipt, **kwargs)
    assert verified == {
        "state": "CLAIM_CORROBORATED",
        "basis": "INDEPENDENT_VERSIONED_SOURCE_REVIEW",
    }
    # Datetime subclasses date but must not raise on comparison with date-only
    # source validity intervals or promote unsupported input to corroboration.
    from datetime import datetime
    assert classify_claim(
        claim, review=receipt,
        **{**kwargs, "at_date": datetime(2026, 10, 14, 0, 0)},
    ) == {
        "state": "CLAIM_UNVERIFIED_EXTERNAL",
        "basis": "NO_VERIFIED_PRIMARY_SOURCE",
    }

    for altered in (
        {"product_scope": "OTHER-PRODUCT"},
        {"document_sha256": "invalid"},
        {"effective_until": "2025-01-01"},
        {"matched_excerpt": "not present in physical bytes"},
        {"independent_source_authenticity_verified": False},
        {"claim_text": "outra afirmação"},
        {"reviewer_receipt_id": ""},
        {"source_url": "http://example.test/unsafe"},
    ):
        source = {**receipt, **altered}
        assert classify_claim(claim, review=source, **kwargs)["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert classify_claim(claim, product_scope="SEG-VIDA-X", at_date=when)["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert classify_claim(
        claim, product_scope="SEG-VIDA-X", at_date=when,
        external_validation_required=False,
    )["state"] == "CLAIM_OBSERVED"
    contradiction = classify_claim(
        claim, review={**receipt, "review_decision": "CONTRADICTS"}, **kwargs,
    )
    assert contradiction["state"] == "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE"




def test_signed_claim_review_receipt_authenticates_entire_context_before_corrob() -> None:
    import hmac
    import json
    from datetime import date
    from hashlib import sha256

    from rasai.claim_review_receipt import verify_claim_review_receipt

    key = b"independent-review-fixture-signing-key-2026"
    allow = frozenset({"REVIEWER-APPROVED-1"})
    claim = "ativação em 24 horas"
    document = "Condições do produto: ativação após 24 horas.".encode("utf-8")
    receipt = {
        "source_url": "https://example.test/primary-v1",
        "document_sha256": sha256(document).hexdigest(),
        "effective_from": "2026-01-01",
        "effective_until": "2026-12-31",
        "reviewed_on": "2026-10-10",
        "product_scope": "VIDA-2026",
        "claim_text": claim,
        "document_version": "2026-01",
        "issuer": "Emissor de teste",
        "reviewer_receipt_id": "RCP-019",
        "reviewer_id": "REVIEWER-APPROVED-1",
        "matched_excerpt": "ativação após 24 horas",
        "review_decision": "CORROBORATES",
        "independent_source_authenticity_verified": True,
    }
    def mac(review: dict) -> str:
        payload = json.dumps(
            review, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        return hmac.new(key, payload, sha256).hexdigest()

    valid = mac(receipt)
    fields = {
        "product_scope": "VIDA-2026",
        "at_date": date(2026, 10, 14),
        "primary_bytes": document,
        "trusted_key": key,
        "trusted_reviewer_ids": allow,
    }
    result = verify_claim_review_receipt(
        claim, receipt=receipt, receipt_mac=valid, **fields,
    )
    assert result == {
        "state": "CLAIM_CORROBORATED",
        "basis": "INDEPENDENT_VERSIONED_SOURCE_REVIEW",
    }

    # A malformed allowlist must never authorize a blank reviewer identity,
    # even if a MAC was otherwise valid for the forged empty identifier.
    for empty_id in ("", "   "):
        blank = {**receipt, "reviewer_id": empty_id}
        denied = verify_claim_review_receipt(
            claim, receipt=blank, receipt_mac=mac(blank),
            **{**fields, "trusted_reviewer_ids": frozenset({empty_id})},
        )
        assert denied == {
            "state": "CLAIM_UNVERIFIED_EXTERNAL",
            "basis": "NO_AUTHENTICATED_REVIEW_RECEIPT",
        }

    for tampered in (
        {**receipt, "review_decision": "CONTRADICTS"},
        {**receipt, "document_version": "2026-02"},
        {**receipt, "reviewer_id": "REVIEWER-OTHER"},
        {**receipt, "product_scope": "OTHER"},
        {**receipt, "independent_source_authenticity_verified": False},
        {**receipt, "extra_field": "untrusted"},
    ):
        denied = verify_claim_review_receipt(
            claim, receipt=tampered, receipt_mac=valid, **fields,
        )
        assert denied["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
        assert denied["basis"] == "NO_AUTHENTICATED_REVIEW_RECEIPT"
    assert verify_claim_review_receipt(
        claim, receipt=receipt, receipt_mac="0" * 64, **fields,
    )["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert verify_claim_review_receipt(
        claim, receipt=receipt, receipt_mac=valid,
        **{**fields, "trusted_key": b""},
    )["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert verify_claim_review_receipt(
        claim, receipt=receipt, receipt_mac=valid,
        **{**fields, "primary_bytes": b"substituted-document"},
    )["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert verify_claim_review_receipt(
        claim, receipt=receipt, receipt_mac=valid,
        **{**fields, "at_date": date(2027, 1, 1)},
    )["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert verify_claim_review_receipt(
        "other claim", receipt=receipt, receipt_mac=valid, **fields,
    )["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert "trusted_key" not in repr(result)



def test_offline_claim_receipt_cli_requires_trusted_environment_and_no_mutation(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    import hmac
    import json
    from hashlib import sha256
    from rasai.claim_review_import_cli import main as verify_cli

    key = b"test-verified-primary-review-signer-2026-secret"
    claim = "ativação em 24 horas"
    raw = "Condições do produto: ativação após 24 horas.".encode("utf-8")
    claim_file, source_file, review_file = (
        tmp_path / "claim.txt",
        tmp_path / "source.txt",
        tmp_path / "receipt.json",
    )
    claim_file.write_text(claim, encoding="utf-8")
    source_file.write_bytes(raw)
    fields = {
        "source_url": "https://example.test/source",
        "document_sha256": sha256(raw).hexdigest(),
        "effective_from": "2026-01-01",
        "effective_until": "2026-12-31",
        "reviewed_on": "2026-10-10",
        "product_scope": "VIDA-2026",
        "claim_text": claim,
        "document_version": "2026-01",
        "issuer": "Emissor de teste",
        "reviewer_receipt_id": "RCP-019",
        "reviewer_id": "REVIEWER-APPROVED",
        "matched_excerpt": "ativação após 24 horas",
        "review_decision": "CORROBORATES",
        "independent_source_authenticity_verified": True,
    }
    signed = json.dumps(
        fields, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    receipt_mac = hmac.new(key, signed, sha256).hexdigest()
    review_file.write_text(
        json.dumps({"review": fields, "mac": receipt_mac}),
        encoding="utf-8",
    )
    sources = [item.read_bytes() for item in (claim_file, source_file, review_file)]
    argv = [
        "--claim-file", str(claim_file),
        "--document-file", str(source_file),
        "--receipt-file", str(review_file),
        "--product-scope", "VIDA-2026",
        "--at-date", "2026-10-14",
    ]
    monkeypatch.setenv("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX", key.hex())
    monkeypatch.setenv("RASAI_CLAIM_REVIEWER_ALLOWLIST", "REVIEWER-APPROVED")
    assert verify_cli(argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "CLAIM_CORROBORATED"
    assert result["basis"] == "INDEPENDENT_VERSIONED_SOURCE_REVIEW"
    assert not result["official_regulator_source_verified"]
    assert not result["legal_compliance_certified"]
    assert result["file_writes"] == result["provider_requests"] == 0
    assert all(
        item.read_bytes() == original
        for item, original in zip((claim_file, source_file, review_file), sources)
    )

    monkeypatch.delenv("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX")
    assert verify_cli(argv) == 0
    failed = json.loads(capsys.readouterr().out)
    assert failed["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert "RASAI_CLAIM_REVIEW_HMAC_KEY_HEX" not in str(failed)

    monkeypatch.setenv("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX", key.hex())
    review_file.write_text(
        '{"review":{"reviewer_id":"A","reviewer_id":"B"},"mac":"bad"}',
        encoding="utf-8",
    )
    assert verify_cli(argv) == 0
    failed_duplicate = json.loads(capsys.readouterr().out)
    assert failed_duplicate["state"] == "CLAIM_UNVERIFIED_EXTERNAL"



def _database(tmp_path: Path) -> Path:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE content_analysis_contexts(
                audit_id TEXT,
                risk_profile TEXT,
                ymyl_category TEXT,
                page_purpose TEXT,
                intended_audience TEXT,
                experience_requirement TEXT,
                freshness_sensitivity TEXT,
                content_origin TEXT
            );
            CREATE TABLE semantic_coherence_assessments(
                audit_id TEXT,
                criterion_id TEXT,
                snapshot_id TEXT,
                page_url TEXT,
                result TEXT,
                confidence REAL,
                declared_context TEXT,
                observed_context TEXT,
                evidence_ids_json TEXT,
                reasoning_summary TEXT,
                provider TEXT,
                model TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO content_analysis_contexts VALUES (?,?,?,?,?,?,?,?)",
            (
                "AUD-YMYL",
                "ymyl",
                "auto",
                "product-service",
                "auto",
                "auto",
                "low",
                "first-party",
            ),
        )
        rows = [
            (
                "AUD-YMYL", "SC-P11", "S1", "https://example.test/", "PARTIAL", 0.89,
                "YMYL financial-security", "Material claims have limited observable qualification.",
                '["EV-11"]', "Claim support is incomplete for the configured risk context.",
                "OPENAI", "gpt-test",
            ),
            (
                "AUD-YMYL", "SC-P12", "S1", "https://example.test/", "PARTIAL", 0.85,
                "YMYL financial-security", "Organization is identifiable but editorial responsibility is limited.",
                '["EV-12"]', "Responsibility support is incomplete for the configured risk context.",
                "OPENAI", "gpt-test",
            ),
            (
                "AUD-YMYL", "SC-P13", "S1", "https://example.test/", "NOT_DETERMINABLE", 0.94,
                "Low freshness sensitivity", "No sufficient publication/update signals were observed.",
                '["EV-13"]', "Freshness cannot be concluded from the available evidence.",
                "OPENAI", "gpt-test",
            ),
        ]
        connection.executemany(
            "INSERT INTO semantic_coherence_assessments VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        connection.commit()
    finally:
        connection.close()
    return database


def _install_live_category_interpretation() -> None:
    ai_execution_state.clear_current_ai_execution()
    recorder = AiExchangeRecorder()
    recorder._interpretations.append(
        ContextInterpretationRecord(
            sequence_no=2,
            provider="OPENAI",
            model="gpt-test",
            snapshot_id="S1",
            page_url="https://example.test/",
            fields={
                "ymyl_category": {
                    "status": "INTERPRETED",
                    "value": "financial-security",
                    "confidence": 0.96,
                    "rationale": "The page can materially affect a financial decision.",
                    "evidence_ids": ["EV-1"],
                }
            },
        )
    )
    ai_execution_state.set_current_ai_execution("PRIMARY", recorder)


def test_editorial_context_combines_user_config_auto_category_and_all_ymyl_criteria(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _install_live_category_interpretation()
    context = build_editorial_risk_context(
        SimpleNamespace(database=database, root=tmp_path),
        "AUD-YMYL",
        page_url="https://example.test/",
    )
    ymyl = context["ymyl"]
    assert ymyl["active"] is True
    assert ymyl["configured_risk_profile"] == "ymyl"
    assert ymyl["configured_category"] == "auto"
    assert ymyl["effective_category"] == "financial-security"
    assert ymyl["alignment_result"] == "PARTIAL"
    assert ymyl["content_change_required"] is True
    assert ymyl["configuration_relation"]["conflict"] is False
    assert "parametrização do usuário foi respeitada" in ymyl["configuration_relation"]["label"]
    assert {item["criterion_id"] for item in ymyl["coherence"]} == {"SC-P11", "SC-P12", "SC-P13"}
    assert set(ymyl["evidence_ids"]) == {"EV-1", "EV-11", "EV-12", "EV-13"}
    ai_execution_state.clear_current_ai_execution()


def test_improvement_request_requires_recommendations_for_actionable_ymyl_findings(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _install_live_category_interpretation()
    target = SimpleNamespace(
        url="https://example.test/",
        input_url="https://example.test/",
        device="DESKTOP",
        market="BR",
        title="Example",
        description="Example description",
        canonical="https://example.test/",
    )
    config = SimpleNamespace(domains=("CONTENT",), max_recommendations=30)
    finding = {
        "finding_id": "SEMANTIC-YMYL:SC-P11:S1",
        "source": "SEMANTIC_COHERENCE_YMYL",
        "evidence_ids": ["EV-11"],
    }
    request, instructions = build_improvement_request_context(
        audit_id="AUD-YMYL",
        workspace=SimpleNamespace(database=database, root=tmp_path),
        context=target,
        config=config,
        findings=[finding],
        evidence_context={"semantic": "persisted"},
        language="pt-BR",
    )
    assert request["editorial_risk_context"]["ymyl"]["effective_category"] == "financial-security"
    assert request["governance"]["required_ymyl_recommendation_finding_ids"] == [
        "SEMANTIC-YMYL:SC-P11:S1"
    ]
    assert "must receive exactly one evidence-bound recommendation" in instructions
    assert "legal/regulatory compliance" in instructions
    assert "hyphen" in instructions.casefold()
    ai_execution_state.clear_current_ai_execution()


def test_missing_required_ymyl_recommendation_is_added_to_repair_scope() -> None:
    findings = [
        {"finding_id": "SEMANTIC-YMYL:SC-P11:S1", "source": "SEMANTIC_COHERENCE_YMYL"},
        {"finding_id": "SEMANTIC-YMYL:SC-P12:S1", "source": "SEMANTIC_COHERENCE_YMYL"},
        {"finding_id": "OTHER", "source": "HTML_STRUCTURE"},
    ]
    accepted = [{"finding_id": "SEMANTIC-YMYL:SC-P12:S1"}]
    scope = _repair_scope_findings(findings, [], accepted)
    assert [item["finding_id"] for item in scope] == ["SEMANTIC-YMYL:SC-P11:S1"]


def test_ymyl_semantic_partial_gaps_become_improvement_findings(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _install_live_category_interpretation()
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        findings, summary = _semantic_risk_findings(
            connection,
            "AUD-YMYL",
            SimpleNamespace(url="https://example.test/"),
            SimpleNamespace(database=database, root=tmp_path),
        )
    finally:
        connection.close()
    ids = {item["finding_id"] for item in findings}
    assert ids == {"SEMANTIC-YMYL:SC-P11:S1", "SEMANTIC-YMYL:SC-P12:S1"}
    assert summary["active"] is True
    assert all(item["source"] == "SEMANTIC_COHERENCE_YMYL" for item in findings)
    ai_execution_state.clear_current_ai_execution()


def test_cat03_explains_user_parameterization_and_content_change(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _install_live_category_interpretation()

    class Evidence:
        @staticmethod
        def _table(headers, rows, **_kwargs):
            return "|".join(str(value) for row in rows for value in row)

        @staticmethod
        def _state_text(_raw, label):
            return label

    html = _ymyl_alignment_html(Evidence, database, "AUD-YMYL")
    assert "Contexto YMYL × conteúdo observado" in html
    assert "parametrização do usuário foi respeitada" in html
    assert "SC-P11, SC-P12 e SC-P13" in html
    assert "Há lacunas YMYL acionáveis" in html
    assert "Exatidão contratual ou regulatória das alegações" in html
    assert "Não verificada nesta análise" in html
    assert "não equivale a uma alegação corroborada por documento oficial" in html
    assert "não significa que a alegação seja falsa" in html
    ai_execution_state.clear_current_ai_execution()


def test_cat08_ymyl_block_explains_why_content_needs_change(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _install_live_category_interpretation()
    html = _ymyl_analysis_context_html(
        database,
        "AUD-YMYL",
        catalog_report_analysis,
    )
    assert "Parametrização × interpretação" in html
    assert "não de a IA ter sobrescrito ou rejeitado a parametrização do usuário" in html
    assert "SC-P11 - Suporte observável de claims" in html
    assert "SC-P12 - Autoria e responsabilidade" in html
    assert "Mudança recomendada" not in html
    assert "Remediação necessária ainda sem ação individual" in html
    ai_execution_state.clear_current_ai_execution()


def test_non_ymyl_context_does_not_force_ymyl_recommendations(tmp_path: Path) -> None:
    database = _database(tmp_path)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE content_analysis_contexts SET risk_profile='standard', ymyl_category='none'"
        )
        connection.commit()
    finally:
        connection.close()
    ai_execution_state.clear_current_ai_execution()
    context = build_editorial_risk_context(database, "AUD-YMYL")
    directive = ymyl_prompt_directive(context)
    assert context["ymyl"]["active"] is False
    assert "Do not invent a YMYL classification" in directive
