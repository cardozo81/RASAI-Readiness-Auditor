"""Isolated audit-scoped architecture choice snapshot tests."""
import json
import pytest

from rasai.architecture_choice import ArchitectureChoice, write_choice
from rasai.architecture_choice_snapshot import freeze_choice, restore_choice


@pytest.mark.parametrize("mode,architecture", [
    ("UNFORCED", None), ("AUTO", None),
    ("DECLARED", "STATIC_OR_SSR"), ("DECLARED", "CSR_SPA"),
    ("DECLARED", "HYDRATED"), ("DECLARED", "MIXED"),
])
def test_freeze_restore_roundtrip(mode, architecture):
    base = write_choice({}, ArchitectureChoice(mode, architecture))
    frozen = freeze_choice("AUD-01", base=base)
    restored = restore_choice(frozen.to_json(), expected_audit_id="AUD-01")
    assert restored == frozen
    assert json.loads(frozen.to_json())["choice"]["mode"] == mode


def test_cross_audit_replay_rejected():
    frozen = freeze_choice("AUD-01").to_json()
    with pytest.raises(ValueError, match="another audit"):
        restore_choice(frozen, expected_audit_id="AUD-02")


def test_snapshot_supersedes_session_without_touching_session():
    session = write_choice({}, ArchitectureChoice("DECLARED", "MIXED"))
    snapshot = write_choice({}, ArchitectureChoice("UNFORCED"))
    frozen = freeze_choice("AUD-01", session=session, snapshot=snapshot)
    assert frozen.selected_from == "SNAPSHOT"
    assert frozen.choice.mode == "UNFORCED"
    assert session["architecture_choice"]["mode"] == "DECLARED"


def test_legacy_absence_remains_unforced():
    frozen = freeze_choice("AUD-01", base={"old": "value"})
    assert frozen.choice.mode == "UNFORCED"
    assert frozen.selected_from == "LEGACY_ABSENT"


@pytest.mark.parametrize("payload", [
    '{"contract_version":"architecture-choice-snapshot-v1","audit_id":"A","audit_id":"A","selected_from":"BASE","choice":{}}',
    '{}', '[]', 'null',
    '{"unexpected":true}',
])
def test_reject_malformed_payload(payload):
    with pytest.raises(ValueError):
        restore_choice(payload, expected_audit_id="A")


def test_explicit_invalid_choice_does_not_restore_defaults():
    raw = freeze_choice("AUD-01").to_json()
    data = json.loads(raw)
    data["choice"]["mode"] = "DECLARED"
    with pytest.raises(ValueError):
        restore_choice(json.dumps(data), expected_audit_id="AUD-01")
