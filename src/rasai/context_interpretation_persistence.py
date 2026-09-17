"""Persist transient AUTO-context interpretations as non-canonical execution inference.

The persisted rows make the exact interpretation used/exposed in one AUD reconstructible
without promoting it to operator configuration or deterministic evidence. Canonical
``content_analysis_contexts`` remains untouched; these rows are explicitly typed as
AI_INFERENCE and remain advisory/non-scoring.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Mapping

from rasai.persistence import AuditWorkspace

CONTEXT_INTERPRETATION_CONTRACT = "CONTENT-CONTEXT-INFERENCE-001"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _identifier(*parts: Any) -> str:
    payload="\x1f".join(str(part or "") for part in parts)
    return "CTXI-"+hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32].upper()


def _exchange_time(recorder: Any, sequence_no: int) -> str:
    for exchange in tuple(getattr(recorder,"exchanges",()) or ()):
        if int(getattr(exchange,"sequence_no",0) or 0)==int(sequence_no):
            value=str(getattr(exchange,"finished_at","") or "").strip()
            if value:return value
    return datetime.now(timezone.utc).isoformat()


def persist_context_interpretations(*, audit_id: str, workspace: AuditWorkspace, recorder: Any) -> int:
    """Persist normalized recorder interpretations idempotently; return inserted count."""
    interpretations=tuple(getattr(recorder,"context_interpretations",()) or ())
    if not interpretations:return 0
    connection=sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS content_context_interpretations (
                    interpretation_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    sequence_no INTEGER NOT NULL,
                    snapshot_id TEXT,
                    page_url TEXT,
                    field_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    interpreted_value TEXT,
                    confidence REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT,
                    interpretation_type TEXT NOT NULL,
                    affects_scoring INTEGER NOT NULL DEFAULT 0,
                    contract_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_context_interpretations_audit
                    ON content_context_interpretations(audit_id,field_name,snapshot_id);
                """
            )
            before=connection.total_changes
            for record in interpretations:
                sequence_no=int(getattr(record,"sequence_no",0) or 0)
                provider=str(getattr(record,"provider","") or "UNKNOWN")
                model=getattr(record,"model",None)
                snapshot_id=getattr(record,"snapshot_id",None)
                page_url=getattr(record,"page_url",None)
                fields=getattr(record,"fields",{})
                if not isinstance(fields,Mapping):continue
                for field_name,raw in sorted(fields.items(),key=lambda item:str(item[0])):
                    if not isinstance(raw,Mapping):continue
                    status=str(raw.get("status") or "NOT_DETERMINABLE").upper()
                    value=raw.get("value")
                    confidence=raw.get("confidence",0.0)
                    try:confidence=max(0.0,min(1.0,float(confidence)))
                    except (TypeError,ValueError):confidence=0.0
                    rationale=str(raw.get("rationale") or "").strip()
                    evidence_ids=raw.get("evidence_ids") or []
                    if not isinstance(evidence_ids,list):evidence_ids=[]
                    evidence_ids=[str(item) for item in evidence_ids if str(item).strip()]
                    interpretation_id=_identifier(
                        audit_id,sequence_no,snapshot_id,page_url,field_name,status,value,
                        confidence,rationale,_canonical(evidence_ids),provider,model,
                    )
                    connection.execute(
                        """INSERT OR IGNORE INTO content_context_interpretations(
                            interpretation_id,audit_id,sequence_no,snapshot_id,page_url,field_name,
                            status,interpreted_value,confidence,rationale,evidence_ids_json,
                            provider,model,interpretation_type,affects_scoring,contract_version,created_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            interpretation_id,audit_id,sequence_no,snapshot_id,page_url,str(field_name),
                            status,None if value is None else str(value),confidence,rationale,
                            _canonical(evidence_ids),provider,model,"AI_INFERENCE",0,
                            CONTEXT_INTERPRETATION_CONTRACT,_exchange_time(recorder,sequence_no),
                        ),
                    )
            return connection.total_changes-before
    finally:
        connection.close()


__all__=["CONTEXT_INTERPRETATION_CONTRACT","persist_context_interpretations"]
