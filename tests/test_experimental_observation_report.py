"""#322/#652 supplementary HTML: verified source, no canonical rewrite or unsafe content."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

import pytest

from rasai.apdex_readiness_sidecar import write_readiness_sidecar
from rasai.experimental_observation_report import render_experimental_observation_report
from rasai.same_sample_observation import _seal
from tests.test_faq_aud_receipt_binding import _BEFORE, _AFTER, _KEY, _URL, _receipt
from tests.test_apdex_readiness_sidecar import aud, observed


@pytest.fixture(autouse=True)
def allow_offline_catalog_source(monkeypatch):
    # The real production path still verifies the complete sealed manifest.
    monkeypatch.setattr(
        "rasai.catalog_report_site.catalog_report_is_fresh",
        lambda *, audit_id, workspace: True,
    )


def _aud_with_samples(tmp_path):
    root = aud(tmp_path)
    with sqlite3.connect(root / "audit.db") as db:
        db.execute(
            "CREATE TABLE synthetic_ux_apdex_samples "
            "(audit_id TEXT, sample_id TEXT, page_id TEXT, device TEXT)"
        )
        db.execute(
            "INSERT INTO synthetic_ux_apdex_samples VALUES (?,?,?,?)",
            (root.name, "M25-1", "PAGE-1", "MOBILE"),
        )
    return root


def test_additive_report_renders_cat06_cat07_with_no_new_aud_bytes(tmp_path):
    root = _aud_with_samples(tmp_path)
    database = (root / "audit.db").read_bytes()
    manifest = (root / "report-catalog" / "manifest.json").read_bytes()
    # The sidecar is already bound to the source before it may be displayed.
    write_readiness_sidecar(root, observed())
    rendered = render_experimental_observation_report(root)
    assert rendered is not None
    assert rendered.parent == tmp_path / ".rasai-experimental-reports" / root.name
    assert re.fullmatch(r"[a-f0-9]{64}\.html", rendered.name)
    payload = rendered.read_text(encoding="utf-8")
    assert sha256(rendered.read_bytes()).hexdigest() + ".html" == rendered.name
    assert "CAT-06" in payload and "CAT-07" in payload and "FAQ" in payload
    assert "190.0 ms" in payload
    assert "Prontidão posterior ao load" in payload
    assert "não são métricas equivalentes" in payload
    assert "Sem interação registrada" in payload
    assert "<script" not in payload
    assert render_experimental_observation_report(root) == rendered
    assert (root / "audit.db").read_bytes() == database
    assert (root / "report-catalog" / "manifest.json").read_bytes() == manifest
    assert not (root / "report-catalog" / rendered.name).exists()


def test_censored_result_never_implies_ready(tmp_path):
    root = _aud_with_samples(tmp_path)
    write_readiness_sidecar(
        root,
        observed(
            status="TIMEOUT", reason="bounded_window_expired",
            primary_content_ms=None, post_load_delta_ms=None,
        ),
    )
    html = render_experimental_observation_report(root).read_text(encoding="utf-8")
    assert "TIMEOUT" in html
    assert "Não observada ou não aplicável" in html
    assert "N/D" in html
    assert "Prontidão posterior ao load" not in html


def test_no_sidecar_has_no_report_and_source_mutation_invalidates_evidence(tmp_path):
    root = _aud_with_samples(tmp_path)
    assert render_experimental_observation_report(root) is None
    write_readiness_sidecar(root, observed())
    (root / "report-catalog" / "manifest.json").write_text(
        '{"contract":"MODIFIED"}', encoding="utf-8",
    )
    # Immutable source link fails; renderer cannot display a valid readiness.
    result = render_experimental_observation_report(root)
    assert "Recusados por integridade: 1" in result.read_text(encoding="utf-8")
    assert "Prontidão posterior ao load" not in result.read_text(encoding="utf-8")


def test_faq_digest_only_never_renders_untrusted_html_or_claims_attestation(tmp_path):
    root = _aud_with_samples(tmp_path)
    folder = tmp_path / ".rasai-faq-sidecars" / root.name
    folder.mkdir(parents=True)
    obj = {
        "contract_version": "RASAI-FAQ-SAME-SAMPLE-SIDECAR-001",
        "scope": {
            "audit_id": root.name, "page_id": "<img src=x onerror=alert(1)>",
            "snapshot_id": "SNP-1", "device": "DESKTOP",
        },
        "advisory_only": True,
        "same_persisted_browser_session_independently_attested": False,
        "crawler_discovery_verified": False, "score_change_authorized": False,
        "later_html": "<script>steal-secret()</script>",
    }
    raw = (json.dumps(obj, sort_keys=True) + "\n").encode()
    (folder / (sha256(raw).hexdigest() + ".json")).write_bytes(raw)
    html = render_experimental_observation_report(root).read_text(encoding="utf-8")
    assert "Após clique (recibo autenticado localmente" not in html
    assert "Recibos FAQ não elegíveis: 1" in html
    assert "independente" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" not in html
    assert "<img src=x onerror" not in html
    assert "steal-secret()" not in html
    assert "<script>" not in html
    assert "Sem evidência elegível" in html


def test_tampered_or_symlinked_faq_and_readiness_rejected(tmp_path):
    root = _aud_with_samples(tmp_path)
    write_readiness_sidecar(root, observed())
    folder = tmp_path / ".rasai-faq-sidecars" / root.name
    folder.mkdir(parents=True)
    (folder / ("0" * 64 + ".json")).write_text('{"fake":true}')
    report = render_experimental_observation_report(root).read_text(encoding="utf-8")
    assert "Recibos FAQ não elegíveis: 1" in report
    swapped = tmp_path / "fake-folder"
    swapped.mkdir()
    folder.rename(tmp_path / "old-faq")
    try:
        folder.symlink_to(swapped, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation unavailable on this platform")
    with pytest.raises(ValueError, match="untrusted FAQ folder"):
        render_experimental_observation_report(root)


def test_digest_valid_but_nonexistent_sample_is_rejected(tmp_path):
    root = _aud_with_samples(tmp_path)
    write_readiness_sidecar(
        root, observed(sample_id="FORGED-UNPERSISTED-SAMPLE")
    )
    supplemental = render_experimental_observation_report(root)
    html = supplemental.read_text(encoding="utf-8")
    assert "Recusados por integridade: 1" in html
    assert "Prontidão posterior ao load" not in html
    assert "Nenhuma prontidão experimental verificada" in html

def test_signed_faq_only_claims_local_authentication_after_key_and_aud_match(tmp_path):
    root = _aud_with_samples(tmp_path)
    artifact = root / "artifacts/rendered/faq.html"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(_BEFORE, encoding="utf-8")
    with sqlite3.connect(root / "audit.db") as db:
        db.executescript(
            "CREATE TABLE pages(page_id TEXT,audit_id TEXT);"
            "CREATE TABLE page_snapshots(snapshot_id TEXT,page_id TEXT,"
            "rendered_artifact_ref TEXT,requested_url TEXT,final_url TEXT,device TEXT);"
        )
        db.execute("INSERT INTO pages VALUES (?,?)", ("PAGE-FAQ", root.name))
        db.execute("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
                   ("SNP-FAQ","PAGE-FAQ","artifacts/rendered/faq.html",
                    _URL,_URL,"mobile"))
    scope = dict(
        audit_id=root.name, page_id="PAGE-FAQ", snapshot_id="SNP-FAQ",
        sample_id="M3-SNP-FAQ", context_id="CTX-SNP-FAQ",
        requested_url=_URL, final_url=_URL, device="MOBILE", architecture="UNKNOWN",
    )
    receipt, mac = _receipt()
    signed = {
        "contract_version": "RASAI-LIVE-SAME-PAGE-WITNESS-001",
        "scope": scope, "collector_id": "TEST-ISOLATED-COLLECTOR",
        "receipt_sha256": sha256(mac.encode()).hexdigest(),
        "readiness": {}, "same_live_page_observed_by_collector": True,
        "same_persisted_aud_session_independently_attested": False,
        "crawler_discovery_verified": False, "score_change_authorized": False,
    }
    obj = {
        "contract_version": "RASAI-FAQ-SAME-SAMPLE-SIDECAR-001",
        "scope": scope, "receipt": receipt, "receipt_mac": mac,
        "signed_witness": signed, "witness_mac": _seal(signed, _KEY),
        "later_html": _AFTER, "verification": {}, "advisory_only": True,
        "same_persisted_browser_session_independently_attested": False,
        "crawler_discovery_verified": False, "score_change_authorized": False,
    }
    raw = (json.dumps(obj, sort_keys=True) + "\n").encode()
    folder = tmp_path / ".rasai-faq-sidecars" / root.name
    folder.mkdir(parents=True)
    (folder / (sha256(raw).hexdigest() + ".json")).write_bytes(raw)
    db_bytes = (root / "audit.db").read_bytes()
    declared = render_experimental_observation_report(root).read_text(encoding="utf-8")
    assert "Não verificado (recibo presente, assinatura não conferida)" in declared
    verified = render_experimental_observation_report(
        root, faq_trusted_key=_KEY, faq_collector_id="TEST-ISOLATED-COLLECTOR",
    ).read_text(encoding="utf-8")
    assert "Após clique (recibo autenticado localmente; homologação pendente)" in verified
    assert (root / "audit.db").read_bytes() == db_bytes
    wrong_key = render_experimental_observation_report(
        root, faq_trusted_key=b"wrong-secret-for-offline-collector-2026-10-20",
        faq_collector_id="TEST-ISOLATED-COLLECTOR",
    ).read_text(encoding="utf-8")
    assert "Recibos FAQ não elegíveis: 1" in wrong_key
    artifact.write_text(_BEFORE + "<p>changed</p>", encoding="utf-8")
    changed_dom = render_experimental_observation_report(
        root, faq_trusted_key=_KEY, faq_collector_id="TEST-ISOLATED-COLLECTOR",
    ).read_text(encoding="utf-8")
    assert "Recibos FAQ não elegíveis: 1" in changed_dom


def test_faq_trusted_mode_requires_exact_key_and_collector_pair(tmp_path):
    root = _aud_with_samples(tmp_path)
    with pytest.raises(ValueError, match="together"):
        render_experimental_observation_report(root, faq_trusted_key=_KEY)
    with pytest.raises(ValueError, match="trust configuration"):
        render_experimental_observation_report(
            root, faq_trusted_key=b"short", faq_collector_id="TEST-ISOLATED-COLLECTOR",
        )

def test_supplement_shows_probe_active_wall_but_not_a_b_approval(tmp_path):
    from tests.test_apdex_readiness_sidecar import cost_for
    root = _aud_with_samples(tmp_path)
    old = (root / "audit.db").read_bytes()
    point = observed()
    write_readiness_sidecar(root, point, probe_cost=cost_for(point))
    html = render_experimental_observation_report(root).read_text(encoding="utf-8")
    assert "Custo ativo da sonda" in html
    assert "10.0 ms" in html
    assert "não demonstra comparação A/B" in html
    assert (root / "audit.db").read_bytes() == old
