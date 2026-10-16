"""Architecture choice precedence is strict and side-effect free."""
import pytest

from rasai.architecture_choice import ArchitectureChoice, write_choice
from rasai.architecture_choice_precedence import resolve_choice_precedence


def layer(mode, architecture=None):
    return write_choice({}, ArchitectureChoice(mode, architecture))


def test_snapshot_overrides_session_and_base_without_merging():
    base = layer("DECLARED", "CSR_SPA")
    session = layer("AUTO")
    snapshot = layer("UNFORCED")
    result = resolve_choice_precedence(base=base, session=session, snapshot=snapshot)
    assert (result.choice.mode, result.source, result.explicitly_configured) == (
        "UNFORCED", "SNAPSHOT", True)
    assert base["architecture_choice"]["declared_architecture"] == "CSR_SPA"


def test_session_overrides_base_when_snapshot_absent():
    result = resolve_choice_precedence(
        base=layer("AUTO"), session=layer("DECLARED", "HYDRATED"), snapshot={})
    assert result.choice == ArchitectureChoice("DECLARED", "HYDRATED")
    assert result.source == "SESSION"


def test_base_used_when_no_higher_explicit_choice():
    result = resolve_choice_precedence(base=layer("AUTO"), session={}, snapshot={})
    assert result.choice.mode == "AUTO"
    assert result.source == "BASE"


def test_legacy_absence_is_not_automatic():
    result = resolve_choice_precedence(base={"legacy": True})
    assert result == resolve_choice_precedence()
    assert result.choice.mode == "UNFORCED"
    assert not result.explicitly_configured


def test_corrupt_higher_layer_does_not_fall_back():
    with pytest.raises(ValueError):
        resolve_choice_precedence(
            base=layer("AUTO"), snapshot={"architecture_choice": {"mode": "AUTO"}})


def test_non_mapping_layer_fails_closed():
    with pytest.raises(ValueError):
        resolve_choice_precedence(session="AUTO")


def test_explicit_unforced_clears_older_declaration():
    result = resolve_choice_precedence(
        base=layer("DECLARED", "STATIC_OR_SSR"), session=layer("UNFORCED"))
    assert result.choice.declared_architecture is None
    assert result.source == "SESSION"
