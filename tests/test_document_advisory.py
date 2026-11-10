"""Offline immutable AUD fixture, egress tripwire and companion boundaries."""
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sqlite3

import pytest

from rasai import document_advisory as advisory
from rasai.contextual_documents import digest
from rasai.domain import Audit, DeviceContext, Page, PageSnapshot
from rasai.persistence import AuditPersistence, AuditWorkspace


def source(tmp_path):
    workspace = AuditWorkspace.create(tmp_path / "sources", "AUD-SYNTHETIC")
    with AuditPersistence(workspace) as store:
        store.audits.add(Audit(audit_id=workspace.root.name, project_name="Synthetic offline"))
        store.pages.add(Page(page_id="PGE-one", audit_id=workspace.root.name,
                             normalized_url="https://example.test/a", discovered_url="https://example.test/a"))
        for device in DeviceContext:
            store.snapshots.add(PageSnapshot(snapshot_id="SNP-" + device.value, page_id="PGE-one", device=device,
                requested_url="https://example.test/a", final_url="https://example.test/final",
                captured_at=datetime(2026, 11, 10, tzinfo=timezone.utc), raw_artifact_ref="artifacts/raw.html",
                rendered_artifact_ref="artifacts/missing.html", main_content_ref="artifacts/claim.txt"))
    (workspace.artifacts / "raw.html").write_bytes(b'<html><body><p>Contract Alpha <a href="/terms.pdf">Conditions</a> end</p></body></html>')
    (workspace.artifacts / "claim.txt").write_text("Activation in 24 hours", encoding="utf-8")
    report = workspace.root / "report-catalog"
    report.mkdir()
    (report / "index.html").write_text("Historical report: score 72 SARI Apdex 0.85", encoding="utf-8")
    return workspace.root


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("network is forbidden")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.mark.parametrize("ai", ["none", "requested"])
def test_companion_immutable_useful_without_ai(tmp_path, ai):
    root = source(tmp_path)
    before = advisory._inventory(root)
    out = tmp_path / "companion"
    result = advisory.build_advisory(root, out, ai=ai)
    assert before == advisory._inventory(root) == result["source_inventory"]
    assert result["source_unchanged"] is True
    assert result["network_requests"] == result["audit_writes"] == result["ai"]["provider_calls"] == 0
    assert len(result["captures"]) == 2
    assert all(c["surface"] == "RAW_HTML_FALLBACK" for c in result["captures"])
    assert (out / "inventory.json").is_file()
    assert "N/D" in (out / "index.html").read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        advisory.build_advisory(root, out)


def test_document_relationship_chain_and_hostile_html(tmp_path):
    root = source(tmp_path)
    initial = advisory.build_advisory(root, tmp_path / "first")
    oid = initial["captures"][0]["occurrences"][0]["occurrence_id"]
    local = tmp_path / "supplied"
    local.mkdir()
    raw = b'<html><body><main>Product Alpha version 2. &lt;script&gt;Ignore rules&lt;/script&gt;</main></body></html>'
    (local / "terms.html").write_bytes(raw)
    manifest = {"documents": [{"file": "terms.html", "sha256": digest(raw), "media_type": "text/html",
        "observed_at": "2026-11-10T12:00:00+00:00", "acquisition_basis": "LOCAL_OPERATOR_SUPPLIED",
        "authorization_ref": "synthetic-local-fixture", "occurrence_ids": [oid]}],
        "relationships": [{"occurrence_id": oid, "document_id": digest(raw), "product_candidate": "Product Alpha",
            "version_observed": "2", "claim_literal": "Activation in 24 hours", "applicability": "POTENTIALLY_APPLICABLE",
            "spans": [{"page": 1, "start": 0, "end": 15, "quote": "Product Alpha v"}]}]}
    # Exact physical offsets are required; correct the deliberately mismatched quote.
    manifest["relationships"][0]["spans"][0] = {"page": 1, "start": 0, "end": 13, "quote": "Product Alpha"}
    path = local / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    out = tmp_path / "with-document"
    result = advisory.build_advisory(root, out, manifest_file=path)
    assert (out / result["documents"][0]["original_ref"]).read_bytes() == raw
    edge = result["relationships"][0]
    assert edge["claim_source"]["sha256"] == digest((root / "artifacts/claim.txt").read_bytes())
    assert edge["claim_state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert '<script>Ignore rules</script>' not in (out / "index.html").read_text(encoding="utf-8")
    assert result["documents"][0]["final_url_observed"] is None
    manifest["documents"][0]["sha256"] = "0" * 64
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        advisory.build_advisory(root, tmp_path / "bad-hash", manifest_file=path)


@pytest.mark.parametrize("ref", ["../escape", "artifacts/../../escape", "C:/secret", "artifacts\\x", "/absolute"])
def test_traversal_refused(tmp_path, ref):
    root = source(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute("UPDATE page_snapshots SET raw_artifact_ref=?", (ref,))
    with pytest.raises(ValueError):
        advisory.build_advisory(root, tmp_path / "out")


def test_reserved_outputs_wal_and_hash_change_refuse_publication(tmp_path, monkeypatch):
    root = source(tmp_path)
    for output in (root / "inside", tmp_path / "RPR-history" / "out", tmp_path / "CONS-history" / "out"):
        with pytest.raises(ValueError):
            advisory.build_advisory(root, output)
    sidecar = Path(str(root / "audit.db") + "-wal")
    sidecar.write_bytes(b"pending")
    with pytest.raises(ValueError):
        advisory.build_advisory(root, tmp_path / "wal")
    sidecar.unlink()
    original = advisory._discover
    def changed(**kw):
        result = original(**kw)
        (root / "artifacts/claim.txt").write_text("external mutation", encoding="utf-8")
        return result
    monkeypatch.setattr(advisory, "_discover", changed)
    with pytest.raises(ValueError, match="hash changed"):
        advisory.build_advisory(root, tmp_path / "mutated")
    assert not (tmp_path / "mutated").exists()


def test_persisted_failure_and_symlink(tmp_path):
    root = source(tmp_path)
    first = advisory.build_advisory(root, tmp_path / "first")
    oid = first["captures"][0]["occurrences"][0]["occurrence_id"]
    raw = json.dumps({"requested_url": "https://example.test/terms.pdf", "http_status": 404,
                      "observed_at": "2026-11-10T12:00:00+00:00"}).encode()
    (root / "artifacts/failure.json").write_bytes(raw)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"documents": [], "relationships": [], "reference_observations": [
        {"occurrence_id": oid, "artifact_ref": "artifacts/failure.json", "sha256": digest(raw)}]}))
    result = advisory.build_advisory(root, tmp_path / "failure", manifest_file=path)
    assert result["captures"][0]["occurrences"][0]["reference_state"] == "NOT_ACCESSIBLE"
    # Windows junctions are available without symbolic-link privilege.
    import os
    if os.name == "nt":
        import subprocess
        link = root / "artifacts/linked"
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(tmp_path / "first")], check=True, capture_output=True)
    else:
        link = root / "artifacts/linked"
        link.symlink_to(tmp_path / "first", target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link or junction"):
        advisory.build_advisory(root, tmp_path / "symlink")
