from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from rasai.persistence import AuditWorkspace
from rasai.semantic import SemanticSchemaError
from rasai.semantic_coherence import (
    CoherenceResult,
    PAGE_COHERENCE_IDS,
    PROPERTY_SIGNAL_NAMES,
    PageCoherenceAssessment,
    PropertySemanticSignal,
)
from rasai.semantic_coherence_persistence import aggregate_property_coherence, persist_page_coherence
from rasai.semantic_coherence_runtime import install


def _raw_coherence(evidence_id: str = "EV-1") -> list[dict]:
    return [
        {
            "criterion_id": criterion_id,
            "result": "COHERENT",
            "confidence": 0.9,
            "declared_context": "auto",
            "observed_context": "observable page context",
            "evidence_ids": [evidence_id],
            "reasoning_summary": "Evidence supports coherence.",
        }
        for criterion_id in PAGE_COHERENCE_IDS
    ]


def _raw_signals(evidence_id: str = "EV-1") -> list[dict]:
    return [
        {
            "signal_name": name,
            "value": "ACME" if name == "organization_identity" else f"observed {name}",
            "confidence": 0.8,
            "evidence_ids": [evidence_id],
        }
        for name in PROPERTY_SIGNAL_NAMES
    ]


def _base_payload() -> dict:
    return {
        "assessments": [],
        "entities": [],
        "primary_intent": None,
        "secondary_intents": [],
    }


def test_semantic_normalizer_accepts_complete_coherence_without_new_provider_path() -> None:
    install()
    from rasai import semantic

    payload = {
        **_base_payload(),
        "coherence_assessments": _raw_coherence(),
        "property_signals": _raw_signals(),
    }
    response = semantic.normalize_provider_payload(
        payload,
        frozenset({"EV-1"}),
        provider="FAKE",
        model="fake-model",
        configuration_version="1",
        prompt_id="test",
        prompt_version="1",
    )

    assert tuple(item.criterion_id for item in response.coherence_assessments) == PAGE_COHERENCE_IDS
    assert tuple(item.signal_name for item in response.property_signals) == PROPERTY_SIGNAL_NAMES
    assert response.provider == "FAKE"


def test_semantic_normalizer_rejects_partial_coherence_but_existing_semantics_can_degrade_cleanly() -> None:
    install()
    from rasai import semantic

    old_response = semantic.normalize_provider_payload(
        _base_payload(),
        frozenset(),
        provider="FAKE",
        model=None,
        configuration_version="1",
        prompt_id="test",
        prompt_version="1",
    )
    assert old_response.coherence_assessments == ()
    assert old_response.property_signals == ()

    with pytest.raises(SemanticSchemaError, match="partially missing"):
        semantic.normalize_provider_payload(
            {**_base_payload(), "coherence_assessments": _raw_coherence()},
            frozenset({"EV-1"}),
            provider="FAKE",
            model=None,
            configuration_version="1",
            prompt_id="test",
            prompt_version="1",
        )


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, "AUD-COHERENCE")
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute("CREATE TABLE IF NOT EXISTS audits(audit_id TEXT PRIMARY KEY)")
            connection.execute("CREATE TABLE IF NOT EXISTS snapshots(snapshot_id TEXT PRIMARY KEY)")
            connection.execute("INSERT OR IGNORE INTO audits VALUES('AUD-COHERENCE')")
            connection.execute("INSERT OR IGNORE INTO snapshots VALUES('S1')")
            connection.execute("INSERT OR IGNORE INTO snapshots VALUES('S2')")
    finally:
        connection.close()
    return workspace


def _response(page_two: bool = False):
    assessments = []
    for criterion_id in PAGE_COHERENCE_IDS:
        result = CoherenceResult.COHERENT
        if page_two and criterion_id == "SC-P05":
            result = CoherenceResult.INCOHERENT
        assessments.append(
            PageCoherenceAssessment(
                criterion_id=criterion_id,
                result=result,
                confidence=0.9,
                declared_context="declared",
                observed_context="observed",
                evidence_ids=("EV-2" if page_two else "EV-1",),
                reasoning_summary="test",
            )
        )
    signals = tuple(
        PropertySemanticSignal(
            signal_name=name,
            value="ACME" if name == "organization_identity" else f"same {name}",
            confidence=0.8,
            evidence_ids=("EV-2" if page_two else "EV-1",),
        )
        for name in PROPERTY_SIGNAL_NAMES
    )
    return SimpleNamespace(
        provider="FAKE",
        model="fake-model",
        coherence_assessments=tuple(assessments),
        property_signals=signals,
    )


def test_property_aggregation_runs_only_from_persisted_page_outputs(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    persist_page_coherence(
        workspace=workspace,
        audit_id="AUD-COHERENCE",
        snapshot_id="S1",
        page_url="https://example.test/a",
        response=_response(False),
    )
    persist_page_coherence(
        workspace=workspace,
        audit_id="AUD-COHERENCE",
        snapshot_id="S2",
        page_url="https://example.test/b",
        response=_response(True),
    )

    aggregate_property_coherence(workspace=workspace, audit_id="AUD-COHERENCE")

    connection = sqlite3.connect(workspace.database)
    try:
        identity = connection.execute(
            "SELECT result,observation_count FROM property_semantic_summaries WHERE criterion_id='SC-X01'"
        ).fetchone()
        offering = connection.execute(
            "SELECT result,observation_count FROM property_semantic_summaries WHERE criterion_id='SC-X02'"
        ).fetchone()
        page_count = connection.execute(
            "SELECT COUNT(*) FROM semantic_coherence_assessments WHERE audit_id='AUD-COHERENCE'"
        ).fetchone()[0]
    finally:
        connection.close()

    assert identity == ("COHERENT", 2)
    assert offering == ("INCOHERENT", 2)
    assert page_count == len(PAGE_COHERENCE_IDS) * 2
