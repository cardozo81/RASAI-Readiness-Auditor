"""Choice round-trip and explicit abstention on legacy profiles."""
import pytest
from rasai.architecture_choice import ArchitectureChoice, read_choice, write_choice
from rasai.architecture_context import CLASSES


@pytest.mark.parametrize("choice", [
    ArchitectureChoice(),
    ArchitectureChoice(mode="AUTO"),
    *[ArchitectureChoice(mode="DECLARED", declared_architecture=name)
      for name in sorted(CLASSES - {"UNKNOWN"})],
])
def test_round_trip_without_mutating_input(choice):
    original = {"existing_configuration": {"kpm": "LOAD_EVENT_END"}}
    projected = write_choice(original, choice)
    assert read_choice(projected) == choice
    assert original == {"existing_configuration": {"kpm": "LOAD_EVENT_END"}}
    assert projected["existing_configuration"] is original["existing_configuration"]


def test_missing_legacy_choice_remains_unforced():
    assert read_choice({"legacy": True}) == ArchitectureChoice()


@pytest.mark.parametrize("bad", [
    {"architecture_choice": None},
    {"architecture_choice": {"mode": "AUTO"}},
    {"architecture_choice": {"contract_version": "other", "mode": "AUTO",
                             "declared_architecture": None}},
    {"architecture_choice": {"contract_version": "architecture-choice-v1",
                             "mode": "DECLARED", "declared_architecture": "UNKNOWN"}},
    {"architecture_choice": {"contract_version": "architecture-choice-v1",
                             "mode": "AUTO", "declared_architecture": "CSR_SPA"}},
])
def test_malformed_explicit_choice_fails_closed(bad):
    with pytest.raises(ValueError):
        read_choice(bad)
