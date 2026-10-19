"""Read-only M6 architecture evidence from a sealed historical AUD."""
import sqlite3

from rasai.architecture_m6_evidence import read_audit_architecture_observations
from rasai.architecture_context import resolve_architecture


def test_m6_history_can_be_reused_by_advisory_without_recollection(tmp_path):
    root = tmp_path / "audits"
    path = root / "AUD-1"
    path.mkdir(parents=True)
    with sqlite3.connect(path / "audit.db") as con:
        con.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
        con.execute("""CREATE TABLE page_snapshots(
            snapshot_id TEXT, page_id TEXT, device TEXT, requested_url TEXT,
            final_url TEXT, architecture_classification TEXT,
            raw_artifact_ref TEXT, rendered_artifact_ref TEXT)""")
        con.execute("INSERT INTO pages VALUES ('P-1', 'AUD-1')")
        con.execute("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?)",
                    ("S-1","P-1","MOBILE","https://example.org/a",
                     "https://example.org/a","CSR_SPA","raw/a.html","rendered/a.html"))
    before = (path / "audit.db").read_bytes()
    observations = read_audit_architecture_observations(root, "AUD-1")
    assert len(observations) == 1
    result = resolve_architecture(
        mode="AUTO", declared_architecture=None,
        observations=observations, requested_url="https://example.org/a",
        final_url="https://example.org/a", audit_id="AUD-1",
        page_id="P-1", device="MOBILE", snapshot_id="S-1",
        consumer_id="descriptive_report",
        advisory_consumers=frozenset({"descriptive_report"}),
    )
    assert result.effective_architecture == "CSR_SPA"
    assert (path / "audit.db").read_bytes() == before


def test_m6_history_abstains_if_rendered_evidence_missing(tmp_path):
    folder = tmp_path / "AUD-2"
    folder.mkdir()
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
        con.execute("""CREATE TABLE page_snapshots(
            snapshot_id TEXT, page_id TEXT, device TEXT, requested_url TEXT,
            final_url TEXT, architecture_classification TEXT,
            raw_artifact_ref TEXT, rendered_artifact_ref TEXT)""")
        con.execute("INSERT INTO pages VALUES ('P-2','AUD-2')")
        con.execute("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?)",
                    ("S-2","P-2","MOBILE","https://example.org/",
                     "https://example.org/","CSR_SPA","raw/a.html",None))
    assert read_audit_architecture_observations(tmp_path, "AUD-2") == ()


def test_m6_history_rejects_workspace_symlink(tmp_path):
    import os
    import pytest
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "audits").mkdir()
    try:
        os.symlink(outside, tmp_path / "audits" / "AUD-3", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable on host")
    assert read_audit_architecture_observations(tmp_path / "audits", "AUD-3") == ()


def test_historical_resolver_uses_same_scoped_advisory_policy(tmp_path, monkeypatch):
    from rasai.architecture_choice_audit_adapter import resolve_historical_architecture_for_consumer
    from rasai.architecture_context import ArchitectureObservation
    from rasai.architecture_choice_precedence import ResolvedChoice
    from rasai.architecture_choice import ArchitectureChoice
    monkeypatch.setattr("rasai.architecture_choice_audit_adapter.read_architecture_choice_for_reprocess",
                        lambda *_: ResolvedChoice(ArchitectureChoice("AUTO"), "SNAPSHOT", True))
    obs = (ArchitectureObservation("CSR_SPA", "https://example.org/a", "MOBILE",
                                   "S-1", "raw/a.html", audit_id="AUD-1",
                                   page_id="P-1", final_url="https://example.org/a"),)
    monkeypatch.setattr("rasai.architecture_m6_evidence.read_audit_architecture_observations",
                        lambda *_: obs)
    identity = dict(requested_url="https://example.org/a", final_url="https://example.org/a",
                    device="MOBILE", page_id="P-1", snapshot_id="S-1")
    allowed = resolve_historical_architecture_for_consumer(
        tmp_path, "AUD-1", consumer_id="descriptive_report", **identity)
    assert allowed.effective_architecture == "CSR_SPA"
    denied = resolve_historical_architecture_for_consumer(
        tmp_path, "AUD-1", consumer_id="scoring", **identity)
    assert denied.effective_architecture is None
    assert denied.abstention_reason == "CONSUMER_NOT_APPROVED"
    mismatched = resolve_historical_architecture_for_consumer(
        tmp_path, "AUD-1", consumer_id="descriptive_report",
        **dict(identity, device="DESKTOP"))
    assert mismatched.effective_architecture is None


def test_duplicate_m6_identity_abstains_instead_of_selecting_first(tmp_path):
    root = tmp_path / "audits"
    folder = root / "AUD-9"
    folder.mkdir(parents=True)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
        con.execute("""CREATE TABLE page_snapshots(
            snapshot_id TEXT, page_id TEXT, device TEXT, requested_url TEXT,
            final_url TEXT, architecture_classification TEXT,
            raw_artifact_ref TEXT, rendered_artifact_ref TEXT)""")
        con.execute("INSERT INTO pages VALUES ('P-9', 'AUD-9')")
        rows = [("S-9","P-9","MOBILE","https://example.org/",
                 "https://example.org/", arch, "raw/a.html","render/a.html")
                for arch in ("CSR_SPA", "STATIC_OR_SSR")]
        con.executemany("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?)", rows)
    assert read_audit_architecture_observations(root, "AUD-9") == ()


def test_historical_m6_rejects_unsafe_artifact_references(tmp_path):
    root = tmp_path / "audits"
    folder = root / "AUD-10"
    folder.mkdir(parents=True)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
        con.execute("""CREATE TABLE page_snapshots(
            snapshot_id TEXT, page_id TEXT, device TEXT, requested_url TEXT,
            final_url TEXT, architecture_classification TEXT,
            raw_artifact_ref TEXT, rendered_artifact_ref TEXT)""")
        con.execute("INSERT INTO pages VALUES ('P-10','AUD-10')")
        bad_refs = ("../raw/a.html", "/tmp/raw/a.html", "C:/raw/a.html",
                    "raw/../secret.html", "raw//a.html",
                    "raw/\\\\secret.html", "raw/a.html\\n")
        for i, ref in enumerate(bad_refs):
            con.execute("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?)",
                        (f"S-{i}", "P-10", "MOBILE", "https://example.org/",
                         "https://example.org/", "CSR_SPA", ref, "rendered/a.html"))
        con.execute("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?)",
                    ("S-good", "P-10", "MOBILE", "https://example.org/",
                     "https://example.org/", "CSR_SPA", "raw/a.html", "rendered/a.html"))
    before = (folder / "audit.db").read_bytes()
    observations = read_audit_architecture_observations(root, "AUD-10")
    assert len(observations) == 1
    assert observations[0].snapshot_id == "S-good"
    assert (folder / "audit.db").read_bytes() == before


def test_snapshot_id_reused_across_urls_abstains_for_both_scopes(tmp_path):
    folder = tmp_path / "AUD-11"
    folder.mkdir()
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
        con.execute("""CREATE TABLE page_snapshots(
            snapshot_id TEXT, page_id TEXT, device TEXT, requested_url TEXT,
            final_url TEXT, architecture_classification TEXT,
            raw_artifact_ref TEXT, rendered_artifact_ref TEXT)""")
        con.execute("INSERT INTO pages VALUES ('P-11','AUD-11')")
        con.executemany("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?)", [
            ("S-11", "P-11", "MOBILE", url, url, arch,
             "raw/a.html", "rendered/a.html")
            for url, arch in [
                ("https://example.org/a", "CSR_SPA"),
                ("https://example.org/b", "STATIC_OR_SSR"),
            ]
        ])
    original = (folder / "audit.db").read_bytes()
    assert read_audit_architecture_observations(tmp_path, "AUD-11") == ()
    assert (folder / "audit.db").read_bytes() == original


def test_physical_artifact_inspection_is_explicitly_unattested(tmp_path):
    from hashlib import sha256
    from rasai.architecture_m6_evidence import inspect_architecture_artifact_pair
    folder = tmp_path / "AUD-12"
    (folder / "artifacts").mkdir(parents=True)
    raw = folder / "artifacts" / "raw.html"
    rendered = folder / "artifacts" / "rendered.html"
    raw.write_bytes(b"<html>raw</html>")
    rendered.write_bytes(b"<html>rendered</html>")
    result = inspect_architecture_artifact_pair(
        tmp_path, "AUD-12", "artifacts/raw.html", "artifacts/rendered.html")
    assert result.status == "PRESENT_UNATTESTED"
    assert result.manifest_attested is False
    assert result.raw_sha256 == sha256(raw.read_bytes()).hexdigest()
    assert result.rendered_sha256 == sha256(rendered.read_bytes()).hexdigest()
    assert inspect_architecture_artifact_pair(
        tmp_path, "AUD-12", "../secret", "artifacts/rendered.html"
    ).status == "INVALID_REFERENCE"
    rendered.unlink()
    assert inspect_architecture_artifact_pair(
        tmp_path, "AUD-12", "artifacts/raw.html", "artifacts/rendered.html"
    ).status == "ARTIFACT_UNAVAILABLE"


def test_physical_artifact_inspection_blocks_symlinks(tmp_path):
    import os
    import pytest
    from rasai.architecture_m6_evidence import inspect_architecture_artifact_pair
    folder = tmp_path / "AUD-13"
    (folder / "artifacts").mkdir(parents=True)
    (folder / "artifacts" / "safe.html").write_bytes(b"safe")
    outside = tmp_path / "outside.html"
    outside.write_bytes(b"secret")
    try:
        os.symlink(outside, folder / "artifacts" / "linked.html")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported")
    result = inspect_architecture_artifact_pair(
        tmp_path, "AUD-13", "artifacts/safe.html", "artifacts/linked.html")
    assert result.status == "UNSAFE_SYMLINK"
    assert result.raw_sha256 is None


def test_scoped_physical_snapshot_diagnostic_rejects_cross_url(tmp_path):
    from rasai.architecture_m6_evidence import inspect_historical_snapshot_artifacts
    folder = tmp_path / "AUD-14"
    (folder / "artifacts").mkdir(parents=True)
    (folder / "artifacts" / "raw.html").write_bytes(b"raw")
    (folder / "artifacts" / "rendered.html").write_bytes(b"rendered")
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
        con.execute("""CREATE TABLE page_snapshots(
            snapshot_id TEXT, page_id TEXT, device TEXT, requested_url TEXT,
            final_url TEXT, architecture_classification TEXT,
            raw_artifact_ref TEXT, rendered_artifact_ref TEXT)""")
        con.execute("INSERT INTO pages VALUES ('P-14','AUD-14')")
        con.execute("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?)",
                    ("S-14", "P-14", "MOBILE", "https://example.org/a",
                     "https://example.org/a", "CSR_SPA",
                     "artifacts/raw.html", "artifacts/rendered.html"))
    before = (folder / "audit.db").read_bytes()
    scope = dict(page_id="P-14", snapshot_id="S-14", device="MOBILE",
                 requested_url="https://example.org/a",
                 final_url="https://example.org/a")
    good = inspect_historical_snapshot_artifacts(tmp_path, "AUD-14", **scope)
    assert good.status == "PRESENT_UNATTESTED"
    assert good.manifest_attested is False
    bad = inspect_historical_snapshot_artifacts(
        tmp_path, "AUD-14", **dict(scope, requested_url="https://example.org/b"))
    assert bad.status == "MISSING_OR_AMBIGUOUS_IDENTITY"
    assert (folder / "audit.db").read_bytes() == before


def test_physical_artifact_inspection_enforces_bounded_hashing(tmp_path, monkeypatch):
    import rasai.architecture_m6_evidence as evidence
    folder = tmp_path / "AUD-15" / "artifacts"
    folder.mkdir(parents=True)
    (folder / "raw.html").write_bytes(b"x" * 9)
    (folder / "rendered.html").write_bytes(b"y" * 9)
    monkeypatch.setattr(evidence, "MAX_ARTIFACT_BYTES", 8)
    result = evidence.inspect_architecture_artifact_pair(
        tmp_path, "AUD-15", "artifacts/raw.html", "artifacts/rendered.html")
    assert result.status == "ARTIFACT_LIMIT_EXCEEDED"
    assert result.raw_sha256 is None
    assert result.manifest_attested is False


def test_new_m3_artifact_binding_is_verifiable_without_modifying_evidence(tmp_path):
    from rasai.architecture_m6_evidence import capture_artifact_binding, verify_artifact_binding
    root = tmp_path / "audits"
    workspace = root / "AUD-1"
    (workspace / "artifacts").mkdir(parents=True)
    raw = workspace / "artifacts" / "raw.html"
    rendered = workspace / "artifacts" / "rendered.html"
    raw.write_bytes(b"<main>raw</main>")
    rendered.write_bytes(b"<main>rendered</main>")
    before = (raw.read_bytes(), rendered.read_bytes())
    binding = capture_artifact_binding(workspace, "artifacts/raw.html", "artifacts/rendered.html")
    assert binding["raw_sha256"] and binding["rendered_sha256"]
    assert binding["manifest_attested"] is False
    assert verify_artifact_binding(root, "AUD-1", "artifacts/raw.html",
                                   "artifacts/rendered.html", binding) == "VERIFIED_EMBEDDED_DIGEST"
    assert (raw.read_bytes(), rendered.read_bytes()) == before
    rendered.write_bytes(b"<main>modified</main>")
    assert verify_artifact_binding(root, "AUD-1", "artifacts/raw.html",
                                   "artifacts/rendered.html", binding) == "DIGEST_MISMATCH"
    assert verify_artifact_binding(root, "AUD-1", "artifacts/raw.html",
                                   "artifacts/rendered.html", {}) == "UNVERIFIED_LEGACY"


def test_missing_artifact_never_becomes_a_trusted_digest(tmp_path):
    from rasai.architecture_m6_evidence import capture_artifact_binding
    workspace = tmp_path / "AUD-1"
    workspace.mkdir()
    binding = capture_artifact_binding(workspace, "artifacts/missing.html", None)
    assert binding["raw_sha256"] is None
    assert binding["rendered_sha256"] is None
    assert binding["manifest_attested"] is False


def test_m6_reader_refuses_tampered_canonically_bound_snapshot(tmp_path):
    from rasai.architecture_m6_evidence import (
        capture_artifact_binding, read_audit_architecture_observations,
    )
    import json
    root = tmp_path / "audits"
    workspace = root / "AUD-BIND"
    (workspace / "artifacts").mkdir(parents=True)
    raw = workspace / "artifacts" / "raw.html"
    rendered = workspace / "artifacts" / "rendered.html"
    raw.write_text("<html>raw</html>", encoding="utf-8")
    rendered.write_text("<html>rendered</html>", encoding="utf-8")
    binding = capture_artifact_binding(workspace, "artifacts/raw.html",
                                       "artifacts/rendered.html")
    with sqlite3.connect(workspace / "audit.db") as con:
        con.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
        con.execute(
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT,page_id TEXT,device TEXT,requested_url TEXT,"
            "final_url TEXT,architecture_classification TEXT,"
            "raw_artifact_ref TEXT,rendered_artifact_ref TEXT,browser_metadata TEXT)"
        )
        con.execute("INSERT INTO pages VALUES ('P-1', 'AUD-BIND')")
        con.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?,?)",
            ("S-1", "P-1", "MOBILE", "https://example.org/",
             "https://example.org/", "CSR_SPA", "artifacts/raw.html",
             "artifacts/rendered.html", json.dumps({"architecture_artifact_binding": binding})),
        )
    result = read_audit_architecture_observations(root, "AUD-BIND")
    assert len(result) == 1 and result[0].architecture == "CSR_SPA"
    rendered.write_text("<html>tampered</html>", encoding="utf-8")
    assert read_audit_architecture_observations(root, "AUD-BIND") == ()
