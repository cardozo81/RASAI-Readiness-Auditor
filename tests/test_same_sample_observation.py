"""#652/#322: one LIVE page, bounded readiness, signed FAQ and physical AUD binding."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import time

import pytest
from playwright.sync_api import sync_playwright

from rasai.same_sample_observation import (
    observe_same_browser_sample, verify_bound_live_witness,
)

_URL = "https://same-sample-fixture.test/faq"
_KEY = b"trusted-physical-observer-test-signing-key-2026"
_COLLECTOR = "M3-EXPLICIT-TEST-COLLECTOR"
_HTML = """<!doctype html><html><body>
<main><h1>Resumo do seguro e condicoes</h1><p>""" + ("Coberturas e limites claros. " * 25) + """</p></main>
<button id="faq" type="button" aria-controls="faq-answer"
 aria-expanded="false">Abrir FAQ</button>
<script>
document.getElementById('faq').addEventListener('click', () => {
  document.getElementById('faq').setAttribute('aria-expanded', 'true');
  const e = document.createElement('div');
  e.id = 'faq-answer';
  e.textContent = 'Resposta observada depois do clique';
  document.body.appendChild(e);
});
</script></body></html>"""


def _scope():
    return {
        "audit_id": "AUD-SAME-SAMPLE", "page_id": "PAGE-1",
        "snapshot_id": "SNP-1", "sample_id": "LIVE-NAV-1",
        "context_id": "CTX-1", "requested_url": _URL,
        "final_url": _URL, "device": "DESKTOP", "architecture": "CSR_SPA",
    }


def _run(page, frozen, started_ns, load_ms, **extra):
    opts = dict(
        page=page, scope=_scope(),
        navigation_started_monotonic_ns=started_ns,
        load_ms=load_ms, faq_target_id="faq-answer",
        captured_dom_sha256=sha256(frozen.encode()).hexdigest(),
        signing_key=_KEY, collector_id=_COLLECTOR,
        trusted_collectors=frozenset({_COLLECTOR}),
        explicit_faq_opt_in=True,
        isolated_context_acknowledged=True,
        readiness_opt_in=True, readiness_window_ms=450,
    )
    opts.update(extra)
    return observe_same_browser_sample(**opts)


def _physical_aud(tmp_path: Path, frozen: str):
    root = tmp_path / "AUD-SAME-SAMPLE"
    artifact = root / "artifacts" / "rendered" / "SNP-1.html"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(frozen, encoding="utf-8")
    with sqlite3.connect(root / "audit.db") as db:
        db.executescript(
            "CREATE TABLE pages(page_id TEXT,audit_id TEXT);"
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT,page_id TEXT,rendered_artifact_ref TEXT,"
            "requested_url TEXT,final_url TEXT,device TEXT);"
        )
        db.execute("INSERT INTO pages VALUES ('PAGE-1','AUD-SAME-SAMPLE')")
        db.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
            ("SNP-1", "PAGE-1", "artifacts/rendered/SNP-1.html",
             _URL, _URL, "desktop"),
        )
    return root, artifact


def test_real_playwright_one_context_two_distinct_advisories_no_aud_mutation(tmp_path):
    """An already navigated page is never opened again to produce the FAQ receipt."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel=os.environ.get("RASAI_322_CHROME_CHANNEL") or None,
            headless=True,
        )
        try:
            context = browser.new_context(service_workers="block")
            seen = []

            def local_only(route):
                seen.append(route.request.url)
                if route.request.url == _URL:
                    route.fulfill(
                        status=200, content_type="text/html", body=_HTML,
                    )
                else:
                    route.abort()

            context.route("**/*", local_only)
            page = context.new_page()
            started = time.monotonic_ns()
            page.goto(_URL, wait_until="load")
            load_ms = (time.monotonic_ns() - started) / 1_000_000
            frozen = page.content()
            root, artifact = _physical_aud(tmp_path, frozen)
            db_bytes = (root / "audit.db").read_bytes()
            dom_bytes = artifact.read_bytes()
            witness = _run(page, frozen, started, load_ms)
            assert witness.readiness.status in {"OBSERVED", "NOT_OBSERVED", "TIMEOUT"}
            assert witness.readiness.sample_id == "LIVE-NAV-1"
            assert witness.readiness.context_id == "CTX-1"
            assert witness.readiness.page_id == "PAGE-1"
            assert witness.readiness.device == "DESKTOP"
            assert witness.faq_result["status"] == "LOCAL_FAQ_ACTION_OBSERVED_NOT_ATTESTED"
            assert witness.receipt is not None
            assert witness.receipt_mac is not None
            assert witness.signed_witness["same_live_page_observed_by_collector"] is True
            linked = verify_bound_live_witness(
                witness, aud_dir=root,
                trusted_key=_KEY, permitted_collector_ids=frozenset({_COLLECTOR}),
            )
            assert linked["status"] == "LIVE_COLLECTOR_AND_AUD_DOM_LINKED_NOT_INDEPENDENTLY_ATTESTED"
            assert linked["signed_live_page_witness_valid"] is True
            assert linked["persisted_dom_bytes_match_signed_receipt"] is True
            assert linked["same_aud_sample_verified"] is False
            assert linked["same_browser_session_independently_attested"] is False
            assert linked["crawler_discovery_verified"] is False
            assert linked["score_change_authorized"] is False
            assert (root / "audit.db").read_bytes() == db_bytes
            assert artifact.read_bytes() == dom_bytes
            assert seen == [_URL]  # one navigation, no click-related network
            assert len(context.pages) == 1
            assert page.url == _URL

            rejected = verify_bound_live_witness(
                replace(witness, witness_mac="0" * 64), aud_dir=root,
                trusted_key=_KEY, permitted_collector_ids=frozenset({_COLLECTOR}),
            )
            assert rejected["status"] == "SAME_SAMPLE_PHYSICAL_EVIDENCE_NOT_VERIFIED"
            tampered = verify_bound_live_witness(
                replace(witness, scope={**witness.scope, "sample_id": "FAKE"}),
                aud_dir=root, trusted_key=_KEY,
                permitted_collector_ids=frozenset({_COLLECTOR}),
            )
            assert tampered["signed_live_page_witness_valid"] is False
            context.close()
        finally:
            browser.close()


def test_absent_consent_and_frozen_dom_mismatch_never_click(tmp_path):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel=os.environ.get("RASAI_322_CHROME_CHANNEL") or None,
            headless=True,
        )
        try:
            context = browser.new_context(service_workers="block")
            context.route("**/*", lambda route: route.fulfill(
                status=200, body=_HTML, content_type="text/html"
            ))
            page = context.new_page()
            started = time.monotonic_ns()
            page.goto(_URL, wait_until="load")
            load_ms = (time.monotonic_ns() - started) / 1_000_000
            before = page.content()
            with pytest.raises(ValueError, match="opt-in"):
                _run(page, before, started, load_ms, explicit_faq_opt_in=False)
            with pytest.raises(ValueError, match="frozen canonical"):
                _run(page, before + "CHANGED", started, load_ms)
            assert page.locator("#faq").get_attribute("aria-expanded") == "false"
            assert page.content() == before
            context.close()
        finally:
            browser.close()
