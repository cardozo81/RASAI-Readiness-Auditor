"""Evidence Manager for M4 - Extraction + Evidence."""

from __future__ import annotations

from typing import Any

from rasai.domain import DeviceContext, Evidence, EvidenceType, new_id, utc_now
from rasai.persistence import AuditPersistence


class EvidenceManager:
    """Create and persist first-class evidence with explicit provenance."""

    def __init__(self, persistence: AuditPersistence) -> None:
        self._persistence = persistence

    def record(
        self,
        *,
        audit_id: str,
        page_id: str | None,
        snapshot_id: str | None,
        device: DeviceContext | None,
        evidence_type: EvidenceType,
        source: str,
        observed_value: Any,
        artifact_reference: str | None = None,
    ) -> Evidence:
        evidence = Evidence(
            evidence_id=new_id("EV-GEO"),
            audit_id=audit_id,
            page_id=page_id,
            snapshot_id=snapshot_id,
            device=device,
            evidence_type=evidence_type,
            source=source,
            observed_value=observed_value,
            artifact_reference=artifact_reference,
            captured_at=utc_now(),
        )
        self._persistence.evidence.add(evidence)
        return evidence
