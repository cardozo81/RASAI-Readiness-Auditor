"""Semantic-corpus gate for CAT-03 AI analysis.

The gate is intentionally upstream of every semantic provider call. It freezes the
operator-declared property profile and page editorial/risk context, verifies the full M3
snapshot set is materialized, records the M4 extraction attempt surface, and persists a
hashable manifest. Provider calls may then happen page-by-page, but never before the
whole audit corpus required by CAT-03 has reached this READY boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import sqlite3
from typing import Any

from rasai.content_context import configured_content_analysis_context
from rasai.content_context_persistence import persist_content_analysis_context
from rasai.domain import utc_now
from rasai.persistence import AuditWorkspace
from rasai.property_semantic_profile import configured_property_semantic_profile
from rasai.property_semantic_profile_persistence import persist_property_semantic_profile
from rasai.semantic import ProviderCallResult, ProviderState, SemanticAnalysisProvider, SemanticInput


@dataclass(frozen=True, slots=True)
class SemanticCorpusManifest:
    audit_id: str
    page_ids: tuple[str, ...]
    snapshot_ids: tuple[str, ...]
    extraction_evidence_ids: tuple[str, ...]
    corpus_hash: str
    created_at: str
    ready: bool = True

    def require_snapshot(self, snapshot_id: str) -> None:
        if not self.ready:
            raise RuntimeError("semantic corpus is not READY")
        if snapshot_id not in set(self.snapshot_ids):
            raise RuntimeError(f"snapshot is outside prepared semantic corpus: {snapshot_id}")


class CorpusGuardProvider:
    """Mechanical guard around the already-selected canonical provider/orchestrator."""

    def __init__(self, delegate: SemanticAnalysisProvider, manifest: SemanticCorpusManifest) -> None:
        self._delegate = delegate
        self._manifest = manifest
        self.name = str(getattr(delegate, "name", type(delegate).__name__))

    @property
    def manifest(self) -> SemanticCorpusManifest:
        return self._manifest

    def analyze(self, semantic_input: SemanticInput) -> ProviderCallResult:
        try:
            self._manifest.require_snapshot(semantic_input.snapshot_id)
        except RuntimeError as exc:
            return ProviderCallResult(
                ProviderState.UNAVAILABLE,
                reason=f"AI_CONTEXT_NOT_READY:{exc}",
            )
        return self._delegate.analyze(semantic_input)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _corpus_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def prepare_semantic_corpus(
    *,
    audit_id: str,
    m3_result: Any,
    m4_result: Any,
    persistence: Any,
    workspace: AuditWorkspace,
) -> SemanticCorpusManifest:
    """Freeze CAT-03 context and prove all discovered snapshots are materialized first."""
    audit = persistence.audits.get(audit_id)
    if audit is None:
        raise ValueError(f"audit not found: {audit_id}")

    page_ids: list[str] = []
    snapshot_ids: list[str] = []
    extraction_ids: list[str] = []
    for page_id, per_device in m3_result.snapshot_ids.items():
        page = persistence.pages.get(page_id)
        if page is None or page.audit_id != audit_id:
            raise ValueError(f"semantic corpus references page outside audit: {page_id}")
        page_ids.append(page_id)
        for _device, snapshot_id in per_device.items():
            snapshot = persistence.snapshots.get(snapshot_id)
            if snapshot is None or snapshot.page_id != page_id:
                raise ValueError(f"semantic corpus snapshot is not materialized: {snapshot_id}")
            snapshot_ids.append(snapshot_id)
            extraction_ids.extend(tuple(m4_result.evidence_ids.get(snapshot_id, ())))

    if not snapshot_ids:
        raise ValueError("semantic corpus has no materialized snapshots")

    content_context = configured_content_analysis_context()
    property_profile = configured_property_semantic_profile()
    created_at = str(utc_now())
    persist_content_analysis_context(
        workspace=workspace,
        audit_id=audit_id,
        context=content_context,
        created_at=created_at,
    )
    persist_property_semantic_profile(
        workspace=workspace,
        audit_id=audit_id,
        profile=property_profile,
        created_at=created_at,
    )

    payload = {
        "audit_id": audit_id,
        "page_ids": sorted(set(page_ids)),
        "snapshot_ids": sorted(set(snapshot_ids)),
        "extraction_evidence_ids": sorted(set(extraction_ids)),
        "content_analysis_context": content_context.provider_payload(),
        "property_semantic_profile": property_profile.provider_payload(),
        "m4_failure_count": len(tuple(getattr(m4_result, "failures", ()) or ())),
    }
    digest = _corpus_hash(payload)

    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_corpus_manifests (
                    audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    corpus_hash TEXT NOT NULL,
                    page_ids_json TEXT NOT NULL,
                    snapshot_ids_json TEXT NOT NULL,
                    extraction_evidence_ids_json TEXT NOT NULL,
                    content_context_json TEXT NOT NULL,
                    property_context_json TEXT NOT NULL,
                    m4_failure_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO semantic_corpus_manifests VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(audit_id) DO NOTHING
                """,
                (
                    audit_id,
                    "READY",
                    digest,
                    _canonical_json(payload["page_ids"]),
                    _canonical_json(payload["snapshot_ids"]),
                    _canonical_json(payload["extraction_evidence_ids"]),
                    _canonical_json(payload["content_analysis_context"]),
                    _canonical_json(payload["property_semantic_profile"]),
                    int(payload["m4_failure_count"]),
                    created_at,
                ),
            )
    finally:
        connection.close()

    return SemanticCorpusManifest(
        audit_id=audit_id,
        page_ids=tuple(payload["page_ids"]),
        snapshot_ids=tuple(payload["snapshot_ids"]),
        extraction_evidence_ids=tuple(payload["extraction_evidence_ids"]),
        corpus_hash=digest,
        created_at=created_at,
        ready=True,
    )
