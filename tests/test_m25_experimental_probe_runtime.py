"""#322: explicit M25 readiness gate, source identity and post-seal write."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from rasai import m25_experimental_probe_runtime as probe
from rasai.apdex_content_readiness_observation import (
    PrimaryContentReadiness, STRICT_PROVENANCE_VERSION,
)


@pytest.fixture(autouse=True)
def clear_experimental_state():
    probe.clear_pending_readiness()
    probe.forget_experimental_readiness()
    yield
    probe.clear_pending_readiness()
    probe.forget_experimental_readiness()


def _observed():
    return PrimaryContentReadiness(
        sample_id="UXA-1", context_id="UXC-1",
        page_id="PAGE-1", device="MOBILE", architecture="CSR_SPA",
        method_version=STRICT_PROVENANCE_VERSION,
        status="OBSERVED", load_ms=200.0,
        primary_content_ms=450.0, post_load_delta_ms=250.0,
        observation_window_ms=1200, reason="stable_primary_dom_text",
    )


def test_requires_explicit_one_shot_and_exact_bounds():
    with pytest.raises(ValueError):
        probe.configure_one_shot_readiness(architecture="CSR_SPA")
    with pytest.raises(ValueError):
        probe.configure_one_shot_readiness(
            architecture="CSR_SPA", window_ms=5000, operator_opt_in=True,
        )
    probe.configure_one_shot_readiness(architecture="CSR_SPA", operator_opt_in=True)
    with pytest.raises(ValueError):
        probe.configure_one_shot_readiness(architecture="CSR_SPA", operator_opt_in=True)
    assert probe.consume_one_shot_readiness() == ("CSR_SPA", 1200)
    assert probe.consume_one_shot_readiness() is None


def test_post_seal_requires_persisted_same_sample_id(tmp_path, monkeypatch):
    from rasai import apdex_readiness_sidecar as out
    source = tmp_path / "AUD-M25-TEST"
    source.mkdir()
    with sqlite3.connect(source / "audit.db") as db:
        db.execute(
            "CREATE TABLE synthetic_ux_apdex_samples "
            "(audit_id TEXT,sample_id TEXT,page_id TEXT,device TEXT)"
        )
        db.execute("INSERT INTO synthetic_ux_apdex_samples VALUES(?,?,?,?)",
                   (source.name,"UXA-1","PAGE-1","MOBILE"))
    monkeypatch.setattr(out, "_original", lambda root:
                        ("AUD-M25-TEST","a" * 64,"b" * 64))
    saved = []
    monkeypatch.setattr(out, "write_readiness_sidecar",
                        lambda root,row: saved.append((root,row.sample_id)))
    with probe._LOCK:
        probe._observations[source.name].extend([
            _observed(),
            replace(_observed(), sample_id="UXA-FAKE"),
            replace(_observed(), page_id="PAGE-WRONG"),
        ])
    before = (source / "audit.db").read_bytes()
    verdict = probe.publish_after_seal(audit_id=source.name, aud_dir=source)
    assert verdict == {"eligible":3,"published":1,"rejected":2}
    assert saved == [(source,"UXA-1")]
    assert (source / "audit.db").read_bytes() == before
    assert probe.publish_after_seal(audit_id=source.name, aud_dir=source)["eligible"] == 0


def test_same_page_observer_accepts_owned_adapters_and_rejects_foreign_context(monkeypatch):
    from types import SimpleNamespace
    from rasai.accepted_apdex_error_evidence import _PageProxy, _ContextProxy
    from rasai.synthetic_acquisition_engine import TimedPageProxy, TimedContextProxy
    from rasai import readiness_probe_cost_pilot as pilot

    context = SimpleNamespace(pages=[])
    page = SimpleNamespace(context=context, url="https://example.test/")
    context.pages.append(page)
    wrapped_page = TimedPageProxy(_PageProxy(page), {})
    wrapped_context = TimedContextProxy(_ContextProxy(context), {})
    calls = []
    timed = SimpleNamespace(observation=_observed())
    def measure(**kwargs):
        calls.append(kwargs)
        return timed
    monkeypatch.setattr(pilot, "measure_existing_playwright_probe_cost", measure)
    gateway = probe.experimental_gateway_factory(session_mode="cold", policy=("CSR_SPA", 1200))
    args = dict(page=wrapped_page, live_context=wrapped_context,
                requested_url=page.url, final_url=page.url, device="MOBILE",
                navigation_started_monotonic_ns=1, load_ms=200,
                audit_id="AUD-PROXY", page_id="PAGE-1", sample_id="UXA-1", context_id="UXC-1")
    assert gateway.advisory_same_page_observer(**args) is timed.observation
    assert calls[0]["page"] is page
    args["live_context"] = SimpleNamespace(pages=[page])
    assert gateway.advisory_same_page_observer(**args)["status"] == "EXPERIMENTAL_SAME_PAGE_SCOPE_NOT_VERIFIED"
    assert len(calls) == 1
