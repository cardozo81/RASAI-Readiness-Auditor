from types import SimpleNamespace

from rasai.console_operator_navigation_refinements import (
    _choose_audit_factory,
    _repair_service_toggle_domains,
)


def test_manual_audit_id_accepts_v_as_clean_cancel(monkeypatch):
    from rasai import console_navigation as navigation

    monkeypatch.setattr(navigation, "_audit_directories", lambda _root: [])
    answers = iter(("I", "V", "V"))
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    state = SimpleNamespace(audits_root="audits", error="erro anterior")
    console = SimpleNamespace(render_header=lambda _state: None)

    assert _choose_audit_factory(console)(state) is None
    assert state.error == ""


def test_service_toggle_ui_domain_matches_boolean_runtime_contract():
    from rasai import console_provider_environment as facade
    from rasai.standards_console_runtime import install as install_standards_console_runtime

    install_standards_console_runtime()
    _repair_service_toggle_domains()

    spec = next(
        item for item in facade.refresh_specs()
        if item.name == "RASAI_GSC_ENABLED"
    )
    assert spec.value_type == "booleano"
    assert tuple(spec.accepted) == ("true", "false")
