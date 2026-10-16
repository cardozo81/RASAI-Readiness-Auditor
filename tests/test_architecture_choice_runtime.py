"""Optional architecture choice integration with canonical audit configuration handoff."""
import sqlite3

import pytest

from rasai.architecture_choice import ArchitectureChoice
from rasai.architecture_choice_audit_adapter import read_sealed_audit_choice
from rasai.audit_configuration_reuse import (
    KIND_CONSOLE, configuration_hash, persist_audit_configuration,
    load_reusable_audit_configuration,
)
from rasai.audit_configuration_reuse_runtime import (
    configuration_context, current_configuration, load_subprocess_configuration_handoff,
)


def test_default_context_retains_legacy_config_and_hash():
    config = {"settings": {}, "targets": ["https://example.org"]}
    with configuration_context(kind=KIND_CONSOLE, configuration=config):
        pending = current_configuration()
        assert pending.configuration == config
        assert configuration_hash(pending.configuration) == configuration_hash(config)
        restored = load_subprocess_configuration_handoff()
        assert restored.configuration == config
    assert current_configuration() is None


def test_opt_in_is_carried_by_real_console_handoff_and_isolated():
    original = {"settings": {}, "targets": ["https://example.org"]}
    with configuration_context(
        kind=KIND_CONSOLE, configuration=original,
        architecture_choice=ArchitectureChoice("DECLARED", "HYDRATED"),
    ):
        pending = current_configuration()
        subprocess_copy = load_subprocess_configuration_handoff()
        assert subprocess_copy.configuration == pending.configuration
        assert read_sealed_audit_choice(
            subprocess_copy.configuration,
            expected_hash=configuration_hash(subprocess_copy.configuration),
        ).choice == ArchitectureChoice("DECLARED", "HYDRATED")
        assert "architecture_choice" not in original
    assert current_configuration() is None


def test_invalid_explicit_choice_cannot_enter_handoff():
    with pytest.raises(ValueError):
        with configuration_context(
            kind=KIND_CONSOLE, configuration={}, architecture_choice="CSR_SPA"
        ):
            pass
    assert current_configuration() is None


def test_database_round_trip_uses_existing_configuration_table(tmp_path):
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as con:
        con.execute("CREATE TABLE audits (audit_id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO audits VALUES ('AUD-TEST')")
    with configuration_context(
        kind=KIND_CONSOLE,
        configuration={"settings": {}, "targets": ["https://example.org"]},
        architecture_choice=ArchitectureChoice("AUTO"),
    ):
        pending = current_configuration()
        persisted = persist_audit_configuration(
            database, audit_id="AUD-TEST", kind=pending.kind,
            configuration=pending.configuration,
        )
    loaded = load_reusable_audit_configuration(tmp_path, "AUD-TEST")
    assert loaded.configuration_hash == persisted.configuration_hash
    assert read_sealed_audit_choice(
        loaded.configuration, expected_hash=loaded.configuration_hash,
    ).choice.mode == "AUTO"
