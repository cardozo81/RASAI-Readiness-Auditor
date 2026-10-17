"""Versioned, immutable architecture selection snapshot for offline audit handoff.

Pure JSON codec. Callers own persistence; this module never accesses host INI,
database, session state or network.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping

from rasai.architecture_choice import ArchitectureChoice, read_choice, write_choice
from rasai.architecture_choice_precedence import resolve_choice_precedence

SNAPSHOT_VERSION = "architecture-choice-snapshot-v1"


@dataclass(frozen=True)
class ChoiceSnapshot:
    audit_id: str
    choice: ArchitectureChoice
    selected_from: str
    contract_version: str = SNAPSHOT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.audit_id, str) or not self.audit_id.strip():
            raise ValueError("Snapshot requires a non-empty audit ID")
        if self.selected_from not in {"SNAPSHOT", "SESSION", "BASE", "LEGACY_ABSENT"}:
            raise ValueError("Unknown snapshot source")
        if self.contract_version != SNAPSHOT_VERSION:
            raise ValueError("Unsupported snapshot version")

    def to_json(self) -> str:
        return json.dumps({
            "contract_version": self.contract_version,
            "audit_id": self.audit_id,
            "selected_from": self.selected_from,
            "choice": self.choice.as_record(),
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def freeze_choice(
    audit_id: str, *,
    base: Mapping[str, object] | None = None,
    session: Mapping[str, object] | None = None,
    snapshot: Mapping[str, object] | None = None,
) -> ChoiceSnapshot:
    resolved = resolve_choice_precedence(base=base, session=session, snapshot=snapshot)
    return ChoiceSnapshot(audit_id, resolved.choice, resolved.source)


def restore_choice(payload: str, *, expected_audit_id: str) -> ChoiceSnapshot:
    """Reject ambiguous JSON, unknown fields and cross-audit replay."""
    def unique_pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    try:
        data = json.loads(payload, object_pairs_hook=unique_pairs)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid snapshot JSON") from exc
    if not isinstance(data, dict) or set(data) != {
        "contract_version", "audit_id", "selected_from", "choice"
    }:
        raise ValueError("Unexpected snapshot fields")
    if data["audit_id"] != expected_audit_id:
        raise ValueError("Snapshot belongs to another audit")
    choice = read_choice({"architecture_choice": data["choice"]})
    return ChoiceSnapshot(
        audit_id=data["audit_id"], choice=choice,
        selected_from=data["selected_from"], contract_version=data["contract_version"],
    )
