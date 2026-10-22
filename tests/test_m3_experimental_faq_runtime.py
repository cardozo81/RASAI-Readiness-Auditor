"""#652: explicit M3 isolated-worker one-shot FAQ, hashes and safe post-seal sidecar."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import time

import pytest
from playwright.sync_api import sync_playwright

from rasai import m3_experimental_faq_runtime as faq
from rasai.same_sample_observation import LiveWitness

_URL = "https://faq-one-shot.test/questions"
_KEY = b"independent-offline-test-collector-key-2026-10-20"
_BEFORE = """<!doctype html><html><body><button type="button"
 aria-controls="faq-panel" aria-expanded="false">FAQ?</button>
<script>document.querySelector('button').addEventListener('click', () => {
 document.querySelector('button').setAttribute('aria-expanded','true');
 const p=document.createElement('div');p.id='faq-panel';
 p.textContent='FAQ response';document.body.appendChild(p);
});</script></body></html>"""


@pytest.fixture(autouse=True)
def reset_policy():
    faq.abort_pending_faq()
    faq.discard_private_witness()
    yield
    faq.abort_pending_faq()
    faq.discard_private_witness()


def _policy(tmp_path, **updates):
    key = tmp_path / "collector.key"
    key.write_bytes(_KEY)
    data = dict(
        requested_url=_URL, allowed_final_url=_URL,
        device="DESKTOP", target_id="faq-panel",
        collector_id="OFFLINE-COLLECTOR", trusted_key_file=key,
        explicit_operator_consent=True,
        operator_network_boundary_acknowledged=True,
    )
    data.update(updates)
    return data


def _snapshot():
    return dict(audit_id="AUD-FAQ-ONE-SHOT", page_id="PAGE-1",
                requested_url=_URL, device="DESKTOP", snapshot_id="SNP-ONE")


def test_grant_is_exact_scope_and_consumed_once(tmp_path):
    opts = _policy(tmp_path)
    with pytest.raises(ValueError, match="consent"):
        faq.configure_one_shot_faq(**{**opts, "explicit_operator_consent": False})
    faq.configure_one_shot_faq(**opts)
    assert faq.claim_for_snapshot(**{**_snapshot(), "device": "MOBILE"}) is None
    assert faq.claim_for_snapshot(**{**_snapshot(), "requested_url": _URL + "?x=1"}) is None
    claimed = faq.claim_for_snapshot(**_snapshot())
    assert claimed["trusted_key"] == _KEY
    assert claimed["snapshot_id"] == "SNP-ONE"
    assert faq.claim_for_snapshot(**_snapshot()) is None


def test_refuse_wrong_final_url_before_any_click(tmp_path):
    faq.configure_one_shot_faq(**_policy(tmp_path))
    claimed = faq.claim_for_snapshot(**_snapshot())
    probe = faq.isolated_worker_faq_observer(claimed)
    state = probe(
        page=None, captured_html_sha256="0" * 64,
        requested_url=_URL, final_url="https://other.test/",
        device="DESKTOP", navigation_started_monotonic_ns=1, load_ms=0.0,
    )
    assert state["status"] == "FAQ_EXPLICIT_SCOPE_MISMATCH"


def test_physical_one_context_signed_sidecar_readonly(tmp_path, monkeypatch):
    """One existing page: browser action produces an offline verifiable receipt."""
    faq.configure_one_shot_faq(**_policy(tmp_path))
    policy = faq.claim_for_snapshot(**_snapshot())
    audit = tmp_path / "AUD-FAQ-ONE-SHOT"
    artifact = audit / "artifacts" / "rendered" / "SNP-ONE.html"
    artifact.parent.mkdir(parents=True)
    with sync_playwright() as pw:
        import os
        browser = pw.chromium.launch(
            channel=os.environ.get("RASAI_322_CHROME_CHANNEL") or None,
            headless=True,
        )
        try:
            context = browser.new_context(service_workers="block")
            seen = []
            def local(route):
                seen.append(route.request.url)
                if route.request.url == _URL:
                    route.fulfill(status=200, content_type="text/html", body=_BEFORE)
                else:
                    route.abort()
            context.route("**/*", local)
            page = context.new_page()
            started = time.monotonic_ns()
            page.goto(_URL, wait_until="load")
            before = page.content()
            artifact.write_text(before, encoding="utf-8")
            observer = faq.isolated_worker_faq_observer(policy)
            result = observer(
                page=page, captured_html_sha256=sha256(before.encode()).hexdigest(),
                requested_url=_URL, final_url=_URL, device="DESKTOP",
                navigation_started_monotonic_ns=started, load_ms=0.0,
            )
            assert result["status"] == "LOCAL_FAQ_ACTION_OBSERVED_NOT_ATTESTED"
            witness = result["_private_witness"]
            assert isinstance(witness, LiveWitness)
            assert witness.scope["snapshot_id"] == "SNP-ONE"
            assert witness.faq_result["after_state"] == "EXPANDED_DOM_TEXT"
            assert len(seen) == 1
            context.close()
        finally:
            browser.close()
    with sqlite3.connect(audit / "audit.db") as db:
        db.executescript(
            "CREATE TABLE pages(page_id TEXT,audit_id TEXT);"
            "CREATE TABLE page_snapshots(snapshot_id TEXT,page_id TEXT,"
            "rendered_artifact_ref TEXT,requested_url TEXT,final_url TEXT,device TEXT);"
        )
        db.execute("INSERT INTO pages VALUES('PAGE-1','AUD-FAQ-ONE-SHOT')")
        db.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
            ("SNP-ONE","PAGE-1","artifacts/rendered/SNP-ONE.html",
             _URL,_URL,"desktop"),
        )
    import rasai.apdex_readiness_sidecar as sidecar
    monkeypatch.setattr(sidecar, "_original", lambda root, **kwargs:
                        ("AUD-FAQ-ONE-SHOT", "a" * 64, "b" * 64))
    faq.keep_private_witness(
        audit_id=audit.name, witness=witness,
        trusted_key=_KEY, collector_id="OFFLINE-COLLECTOR",
    )
    before_db = (audit / "audit.db").read_bytes()
    verdict = faq.publish_faq_after_seal(audit_id=audit.name, aud_dir=audit)
    assert {key: verdict[key] for key in ("eligible", "published", "rejected")} == {
        "eligible": 1, "published": 1, "rejected": 0,
    }
    assert verdict["rejection_reasons"] == []
    files = list((tmp_path / ".rasai-faq-sidecars" / audit.name).glob("*.json"))
    assert len(files) == 1
    evidence = json.loads(files[0].read_text(encoding="utf-8"))
    assert evidence["contract_version"] == "RASAI-FAQ-SAME-SAMPLE-SIDECAR-001"
    assert evidence["verification"]["signed_live_page_witness_valid"] is True
    assert evidence["verification"]["persisted_dom_bytes_match_signed_receipt"] is True
    assert evidence["same_persisted_browser_session_independently_attested"] is False
    assert (audit / "audit.db").read_bytes() == before_db
    assert artifact.read_bytes() == before.encode()
    assert faq.publish_faq_after_seal(audit_id=audit.name, aud_dir=audit)["eligible"] == 0


def test_no_physical_gesture_without_separate_network_ack(tmp_path):
    opts = _policy(tmp_path)
    with pytest.raises(ValueError, match="network containment"):
        faq.configure_one_shot_faq(**{
            **opts, "operator_network_boundary_acknowledged": False,
        })
    assert faq.claim_for_snapshot(**_snapshot()) is None


def test_webrtc_websocket_eventsource_are_denied_by_optional_init_script():
    """Browser-only verification. OS-level egress remains separately gated."""
    import os
    from rasai.device_context_capture import _FAQ_EGRESS_INIT_SCRIPT
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            channel=os.environ.get("RASAI_322_CHROME_CHANNEL") or None,
            headless=True,
        )
        try:
            context = browser.new_context(service_workers="block")
            context.add_init_script(_FAQ_EGRESS_INIT_SCRIPT)
            context.route("**/*", lambda route: route.fulfill(
                status=200, content_type="text/html",
                body="<html><body>FAQ test</body></html>",
            ))
            page = context.new_page()
            page.goto(_URL, wait_until="load")
            types = page.evaluate("""() => ({
                rtc: typeof RTCPeerConnection,
                socket: typeof WebSocket,
                eventSource: typeof EventSource
            })""")
            assert types == {
                "rtc": "undefined", "socket": "undefined",
                "eventSource": "undefined",
            }
            context.close()
        finally:
            browser.close()
