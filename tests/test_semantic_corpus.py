from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rasai.persistence import AuditWorkspace
from rasai.semantic import ProviderCallResult, ProviderState, SemanticInput
from rasai.semantic_corpus import CorpusGuardProvider, SemanticCorpusManifest, prepare_semantic_corpus


class _Repo:
    def __init__(self, values):
        self._values = values

    def get(self, key):
        return self._values.get(key)


class _Provider:
    name = "FAKE"

    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, semantic_input: SemanticInput) -> ProviderCallResult:
        self.calls += 1
        return ProviderCallResult(ProviderState.NOT_CONFIGURED, reason="TEST")


def _semantic_input(snapshot_id: str) -> SemanticInput:
    return SemanticInput(
        snapshot_id=snapshot_id,
        page_url="https://example.test/",
        title="Example",
        main_content="Example content",
        structured_data=[],
        primary_language="pt-BR",
        market="BR",
        evidence=(),
    )


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, "AUD-CORPUS")
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute("CREATE TABLE IF NOT EXISTS audits(audit_id TEXT PRIMARY KEY)")
            connection.execute("INSERT OR IGNORE INTO audits VALUES ('AUD-CORPUS')")
    finally:
        connection.close()
    return workspace


def test_corpus_guard_never_delegates_for_unprepared_snapshot() -> None:
    manifest = SemanticCorpusManifest(
        audit_id="AUD-1",
        page_ids=("P1",),
        snapshot_ids=("S1",),
        extraction_evidence_ids=(),
        corpus_hash="hash",
        created_at="2026-09-17T10:00:00Z",
    )
    provider = _Provider()
    guarded = CorpusGuardProvider(provider, manifest)

    result = guarded.analyze(_semantic_input("S2"))

    assert result.state is ProviderState.UNAVAILABLE
    assert result.reason and result.reason.startswith("AI_CONTEXT_NOT_READY:")
    assert provider.calls == 0


def test_prepare_semantic_corpus_freezes_all_snapshots_before_provider_use(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setenv("RASAI_PROPERTY_BUSINESS_SECTOR", "Software B2B")
    monkeypatch.setenv("RASAI_PAGE_PURPOSE", "product-service")

    audit = SimpleNamespace(audit_id="AUD-CORPUS")
    page_a = SimpleNamespace(page_id="P1", audit_id="AUD-CORPUS")
    page_b = SimpleNamespace(page_id="P2", audit_id="AUD-CORPUS")
    snapshot_a = SimpleNamespace(snapshot_id="S1", page_id="P1")
    snapshot_b = SimpleNamespace(snapshot_id="S2", page_id="P2")
    persistence = SimpleNamespace(
        audits=_Repo({"AUD-CORPUS": audit}),
        pages=_Repo({"P1": page_a, "P2": page_b}),
        snapshots=_Repo({"S1": snapshot_a, "S2": snapshot_b}),
    )
    m3 = SimpleNamespace(snapshot_ids={"P1": {"DESKTOP": "S1"}, "P2": {"DESKTOP": "S2"}})
    m4 = SimpleNamespace(evidence_ids={"S1": ("EV-1",), "S2": ("EV-2",)}, failures=())

    manifest = prepare_semantic_corpus(
        audit_id="AUD-CORPUS",
        m3_result=m3,
        m4_result=m4,
        persistence=persistence,
        workspace=workspace,
    )

    assert manifest.ready is True
    assert manifest.snapshot_ids == ("S1", "S2")
    assert manifest.extraction_evidence_ids == ("EV-1", "EV-2")
    assert len(manifest.corpus_hash) == 64

    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT status,corpus_hash FROM semantic_corpus_manifests WHERE audit_id='AUD-CORPUS'"
        ).fetchone()
        profile = connection.execute(
            "SELECT business_sector FROM property_semantic_contexts WHERE audit_id='AUD-CORPUS'"
        ).fetchone()
        content = connection.execute(
            "SELECT page_purpose FROM content_analysis_contexts WHERE audit_id='AUD-CORPUS'"
        ).fetchone()
    finally:
        connection.close()
    assert row == ("READY", manifest.corpus_hash)
    assert profile == ("Software B2B",)
    assert content == ("product-service",)
