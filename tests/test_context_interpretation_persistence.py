from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rasai.context_interpretation_persistence import persist_context_interpretations
from rasai.persistence import AuditWorkspace


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace=AuditWorkspace.create(tmp_path,"AUD-CTX")
    connection=sqlite3.connect(workspace.database)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS audits(audit_id TEXT PRIMARY KEY)")
        connection.execute("INSERT OR IGNORE INTO audits VALUES ('AUD-CTX')")
        connection.commit()
    finally:connection.close()
    return workspace


def test_auto_context_inference_is_durable_idempotent_and_not_canonical_config(tmp_path: Path) -> None:
    workspace=_workspace(tmp_path)
    interpretation=SimpleNamespace(
        sequence_no=3,
        provider="OPENAI",
        model="gpt-test",
        snapshot_id="S1",
        page_url="https://example.test/finance",
        fields={
            "risk_profile": {
                "status":"INTERPRETED",
                "value":"ymyl",
                "confidence":0.87,
                "rationale":"Conteúdo financeiro material observado.",
                "evidence_ids":["EV-1","EV-2"],
            },
            "page_purpose": {
                "status":"NOT_DETERMINABLE",
                "value":None,
                "confidence":0.30,
                "rationale":"Evidência insuficiente.",
                "evidence_ids":["EV-2"],
            },
        },
    )
    exchange=SimpleNamespace(sequence_no=3,finished_at="2026-09-17T10:15:00+00:00")
    recorder=SimpleNamespace(context_interpretations=(interpretation,),exchanges=(exchange,))

    first=persist_context_interpretations(audit_id="AUD-CTX",workspace=workspace,recorder=recorder)
    second=persist_context_interpretations(audit_id="AUD-CTX",workspace=workspace,recorder=recorder)

    assert first==2
    assert second==0
    connection=sqlite3.connect(workspace.database);connection.row_factory=sqlite3.Row
    try:
        rows=connection.execute("SELECT * FROM content_context_interpretations ORDER BY field_name").fetchall()
        assert len(rows)==2
        risk=next(row for row in rows if row["field_name"]=="risk_profile")
        assert risk["interpreted_value"]=="ymyl"
        assert risk["interpretation_type"]=="AI_INFERENCE"
        assert risk["affects_scoring"]==0
        assert risk["provider"]=="OPENAI"
        assert risk["created_at"]=="2026-09-17T10:15:00+00:00"
        # The inference layer does not create or overwrite the canonical context table.
        canonical=connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_analysis_contexts'").fetchone()
        assert canonical is None
    finally:connection.close()
