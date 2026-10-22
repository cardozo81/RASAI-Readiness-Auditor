"""Offline preflight of FAQ controls from each independently acquired DOM."""
from __future__ import annotations

import json

from rasai.faq_target_inventory import inspect_faq_target_candidates, main

URL = "https://controlled.example.test/faq"


def inspect(html: str, *, final: str = URL):
    return inspect_faq_target_candidates(
        html, requested_url=URL, final_url=final, device="DESKTOP",
    )


def test_faq_inventory_discovers_per_page_unique_eligible_control_without_click():
    html = ('<button type="button" aria-controls="faq-42" aria-expanded="false">'
            'Qual a cobertura?</button><main id="unrelated"></main>')
    observed = inspect(html)
    assert observed["status"] == "PASSIVE_INVENTORY_ONLY"
    assert observed["candidate_count"] == 1
    assert observed["candidates"][0]["target_id"] == "faq-42"
    assert observed["candidates"][0]["eligibility"] == (
        "CURRENT_BUTTON_POLICY_ELIGIBLE_NOT_AUTHORIZED"
    )
    assert observed["automatic_target_selection"] is False
    assert observed["click_authorized"] is False
    assert observed["action_performed"] is False
    assert observed["same_aud_sample_verified"] is False
    assert observed["audit_writes"] == observed["provider_requests"] == 0
    assert URL not in str(observed)  # emit only hashes of URL scope


def test_faq_inventory_does_not_assume_same_target_across_urls():
    first = inspect('<button aria-controls="faq-one" aria-expanded="false">Q</button>')
    next_page = inspect_faq_target_candidates(
        '<button aria-controls="faq-other" aria-expanded="false">Q</button>',
        requested_url="https://controlled.example.test/faq/other",
        final_url="https://controlled.example.test/faq/other",
        device="MOBILE",
    )
    assert first["candidates"][0]["target_id"] == "faq-one"
    assert next_page["candidates"][0]["target_id"] == "faq-other"
    assert first["requested_url_sha256"] != next_page["requested_url_sha256"]
    assert first["observed_dom_sha256"] != next_page["observed_dom_sha256"]
    assert next_page["action_performed"] is False


def test_faq_inventory_flags_nonsemantic_ids_and_unsupported_structures():
    html = (
        '<section><button aria-controls="panel-4" aria-expanded="false">Q</button>'
        '<details><summary>Other Q</summary><p>Answer</p></details>'
        '<div role="button" aria-controls="faq-other">Q</div>'
        '<button aria-expanded="false">Third Q</button></section>'
    )
    observed = inspect(html)
    assert observed["candidates"][0]["eligibility"] == (
        "NONSEMANTIC_ID_REQUIRES_SEPARATE_ADAPTER_REVIEW"
    )
    assert observed["details_summary_controls_unsupported"] == 1
    assert observed["nonbutton_disclosures_unsupported"] == 1
    assert observed["expanded_buttons_without_target_unsupported"] == 1
    assert observed["automatic_target_selection"] is False


def test_faq_inventory_rejects_duplicate_unsafe_or_ambiguous_controls():
    duplicate = inspect(
        '<button aria-controls="faq-a" aria-expanded="false">Q</button>'
        '<button aria-controls="faq-a" aria-expanded="false">Q2</button>'
    )
    assert duplicate["candidate_count"] == 1
    assert duplicate["candidates"][0]["eligibility"] == "DUPLICATE_CONTROL"
    unsafe = inspect('<form><button type="submit" aria-controls="faq-b" '
                     'aria-expanded="false" onclick="submit()">Q</button></form>')
    assert unsafe["candidates"][0]["eligibility"] == "UNSAFE_OR_AMBIGUOUS_BUTTON"
    multi = inspect(
        '<button aria-controls="faq-c faq-d" aria-expanded="false">Q</button>'
    )
    assert multi["candidates"][0]["eligibility"] == "AMBIGUOUS_OR_MULTIPLE_IDREFS"
    assert all(row["action_authorized"] is False for row in duplicate["candidates"])


def test_faq_inventory_refuses_untrusted_scope_and_oversize():
    assert inspect_faq_target_candidates(
        "x", requested_url="https://user:pass@example.test/faq",
        final_url=URL, device="DESKTOP",
    )["status"] == "NOT_VERIFIABLE"
    assert inspect_faq_target_candidates(
        "<p>x</p>", requested_url=URL, final_url=URL, device="UNKNOWN",
    )["status"] == "NOT_VERIFIABLE"
    flood = inspect("".join(
        f'<button aria-controls="faq-{i}" aria-expanded="false">Q</button>'
        for i in range(101)
    ))
    assert flood["status"] == "NOT_VERIFIABLE"
    assert flood["reason"] == "CANDIDATE_LIMIT_EXCEEDED"
    assert flood["candidates"] == []
    invalid_unicode = inspect(chr(0xD800))
    assert invalid_unicode["status"] == "NOT_VERIFIABLE"


def test_faq_inventory_cli_reads_local_html_without_network(tmp_path, capsys):
    path = tmp_path / "page.html"
    path.write_text(
        '<button aria-controls="faq-z" aria-expanded="false">Q</button>',
        encoding="utf-8",
    )
    args = ["--html-file", str(path), "--requested-url", URL,
            "--final-url", URL, "--device", "DESKTOP"]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["candidate_count"] == 1
    assert result["action_performed"] is False
    path.unlink()
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "NOT_VERIFIABLE"
