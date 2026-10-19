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
