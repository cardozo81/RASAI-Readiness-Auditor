"""Regression: console configuration reuse restores only an explicit architecture choice."""
from types import SimpleNamespace

from rasai.architecture_choice import ArchitectureChoice
from rasai.architecture_choice_audit_adapter import prepare_audit_choice_configuration
from rasai.audit_configuration_reuse_console import _apply_settings, _ARCHITECTURE_SELECTION


def _state():
    return SimpleNamespace(target="", input_mode="", architecture_choice=None,
                           search_queries=())


def test_reuse_explicit_architecture_choice(monkeypatch):
    from rasai import console_settings
    monkeypatch.setattr(console_settings, "_known_nonsecret_environment_names", lambda: ())
    monkeypatch.setattr(console_settings, "_state_values", lambda state: {})
    monkeypatch.setattr(console_settings, "sync_nonsecret_runtime_environment", lambda state: None)
    state = _state()
    config = prepare_audit_choice_configuration(
        {"settings": {}, "targets": ["https://example.org"]},
        choice=ArchitectureChoice("DECLARED", "HYDRATED"),
    )
    try:
        assert _apply_settings(state, config, "AUD-TEST") == ()
        assert _ARCHITECTURE_SELECTION[id(state)] == ArchitectureChoice("DECLARED", "HYDRATED")
    finally:
        # The adapter maintains process-session mappings. Do not leak the
        # state id between tests, where Python may reuse it for a new object.
        _ARCHITECTURE_SELECTION.pop(id(state), None)


def test_reuse_legacy_source_clears_previous_architecture(monkeypatch):
    from rasai import console_settings
    monkeypatch.setattr(console_settings, "_known_nonsecret_environment_names", lambda: ())
    monkeypatch.setattr(console_settings, "_state_values", lambda state: {})
    monkeypatch.setattr(console_settings, "sync_nonsecret_runtime_environment", lambda state: None)
    state = _state()
    state.architecture_choice = ArchitectureChoice("AUTO")
    _apply_settings(state, {"settings": {}, "targets": ["https://example.org"]}, "AUD-OLD")
    assert id(state) not in _ARCHITECTURE_SELECTION


def test_failed_restore_does_not_replace_architecture_choice(monkeypatch):
    from rasai import console_settings
    import pytest
    monkeypatch.setattr(console_settings, "_known_nonsecret_environment_names", lambda: ())
    state = _state()
    prior = ArchitectureChoice("AUTO")
    _ARCHITECTURE_SELECTION[id(state)] = prior
    config = prepare_audit_choice_configuration(
        {"settings": {"environment": "not-a-mapping"}, "targets": ["https://example.org/"]},
        choice=ArchitectureChoice("DECLARED", "HYDRATED"),
    )
    try:
        with pytest.raises(ValueError, match="environment"):
            _apply_settings(state, config, "AUD-INVALID")
        assert _ARCHITECTURE_SELECTION[id(state)] == prior
    finally:
        _ARCHITECTURE_SELECTION.pop(id(state), None)


def test_architecture_session_label_never_claims_declaration_was_observed():
    from rasai.audit_configuration_reuse_console import describe_session_architecture_choice
    state = _state()
    assert "NÃO SELECIONADA" in describe_session_architecture_choice(state)
    try:
        _ARCHITECTURE_SELECTION[id(state)] = ArchitectureChoice("DECLARED", "CSR_SPA")
        label = describe_session_architecture_choice(state)
        assert "CSR_SPA" in label and "informada, não descoberta" in label
        _ARCHITECTURE_SELECTION[id(state)] = ArchitectureChoice("AUTO")
        assert "evidência" in describe_session_architecture_choice(state)
        _ARCHITECTURE_SELECTION[id(state)] = ArchitectureChoice("UNFORCED")
        assert "SEM FORÇAR" in describe_session_architecture_choice(state)
    finally:
        _ARCHITECTURE_SELECTION.pop(id(state), None)


def test_selector_displays_current_choice_and_cancel_preserves_it(monkeypatch, capsys):
    import builtins
    from types import ModuleType
    from rasai import audit_configuration_reuse_console as adapter

    console = ModuleType("isolated_architecture_choice_console")
    console._menu = lambda _state: builtins.input("Escolha: ")
    console._configure = lambda *_args: None
    console.run_audit_from_console = lambda _state: 0
    # Production console supplies this renderer; isolated test double must too.
    console.render_header = lambda _state: None
    monkeypatch.setattr(adapter, "_INSTALLED", False)
    adapter.install(console)
    state = _state()
    try:
        adapter._ARCHITECTURE_SELECTION[id(state)] = ArchitectureChoice(
            "DECLARED", "HYDRATED"
        )
        monkeypatch.setattr(builtins, "input", lambda _prompt="": "V")
        assert console._menu(state) == "V"
        assert "DECLARADA: HYDRATED (informada, não descoberta)" in capsys.readouterr().out
        console._configure(state, "Y")
        assert adapter._ARCHITECTURE_SELECTION[id(state)] == ArchitectureChoice(
            "DECLARED", "HYDRATED"
        )
        assert "Seleção atual: DECLARADA: HYDRATED" in capsys.readouterr().out
    finally:
        adapter._ARCHITECTURE_SELECTION.pop(id(state), None)


def test_failed_runtime_reprojection_rolls_back_session_and_environment(monkeypatch):
    """A rejected source cannot partially replace the live operator state."""
    import os
    import pytest
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai import console_settings

    state = SearchConsoleState()
    state.target = "https://operator.example/"
    state.device = "mobile"
    state.search_queries = ("current query stays local",)
    original_target, original_device = state.target, state.device
    original_queries = state.search_queries
    key = "RASAI_APDEX_SAMPLES_PER_CONTEXT"
    monkeypatch.setenv(key, "13")
    original_env = os.environ[key]
    config = {
        "targets": ["https://source.example/"],
        "settings": {
            "console": {"device": "desktop"},
            "environment": {key: "17"},
        },
        "search_intelligence": {"queries": ["imported query"], "enabled": True},
    }

    def fail_sync(_state):
        os.environ[key] = "999"
        raise ValueError("synthetic runtime projection rejected")

    monkeypatch.setattr(console_settings, "sync_nonsecret_runtime_environment", fail_sync)
    with pytest.raises(ValueError, match="runtime projection rejected"):
        _apply_settings(state, config, "AUD-TEST")
    assert state.target == original_target
    assert state.device == original_device
    assert state.search_queries == original_queries
    assert os.environ[key] == original_env
    assert id(state) not in _ARCHITECTURE_SELECTION



def _compose_architecture_console_for_cancel(monkeypatch, tmp_path):
    """Compose the real architecture and persistence wrappers in production order."""
    import builtins
    from types import ModuleType
    from rasai import audit_configuration_reuse_console as reuse
    from rasai import console_ui_refactor as refactor
    from rasai.console_search_intelligence import SearchConsoleState

    console = ModuleType("architecture_669_wrapped_console")
    console._menu = lambda _state: "Q"
    console._configure = lambda _state, _choice: None
    console.run_audit_from_console = lambda _state: 0
    console.render_header = lambda _state: None
    console.mark_dirty = lambda _state, value=True: None
    ini = tmp_path / "rasai-console.ini"
    ini.write_text("[test]\nvalue = unchanged\n", encoding="utf-8")
    saved = []

    def save(_state):
        saved.append(True)
        ini.write_text("[test]\nvalue = changed\n", encoding="utf-8")
        return True

    console._save_configuration = save
    monkeypatch.setattr(reuse, "_INSTALLED", False)
    reuse.install(console)
    refactor._install_configure_persistence(console)

    state = SearchConsoleState()
    state.device = "mobile"
    # Trigger the exact unwanted _ensure_mix side effect observed in Windows.
    state.apdex_experience_device_mix = "mobile=50,desktop=50,tablet=0"
    refactor._set_mix_inherited(state, False)
    return console, state, ini, saved


def test_architecture_cancel_v_never_prompts_or_changes_apdex_or_ini(
    monkeypatch, tmp_path,
):
    """#669: real wrapper composition must not open a secondary save menu."""
    import builtins
    import os
    from contextlib import redirect_stdout
    from io import StringIO
    import pytest
    from rasai.architecture_choice import ArchitectureChoice
    from rasai import audit_configuration_reuse_console as reuse
    from rasai import console_ui_refactor as refactor

    console, state, ini, saved = _compose_architecture_console_for_cancel(
        monkeypatch, tmp_path
    )
    original_mix = state.apdex_experience_device_mix
    original_ini = ini.read_bytes()
    original_environment = dict(os.environ)
    initial_fingerprint = refactor._fingerprint(state)
    inherited = refactor._mix_inherited(state)
    def answer(prompt=""):
        assert prompt == "Opção (V para voltar): ", (
            "Cancelamento não pode solicitar DESTINO DA ALTERAÇÃO: " + prompt
        )
        return "v"

    monkeypatch.setattr(builtins, "input", answer)
    try:
        for selection in (
            ArchitectureChoice("UNFORCED"),
            ArchitectureChoice("AUTO"),
            ArchitectureChoice("DECLARED", "CSR_SPA"),
        ):
            reuse._ARCHITECTURE_SELECTION[id(state)] = selection
            fingerprint = refactor._fingerprint(state)
            output = StringIO()
            with redirect_stdout(output):
                console._configure(state, "Y")
            assert reuse._ARCHITECTURE_SELECTION[id(state)] == selection
            assert refactor._fingerprint(state) == fingerprint
            assert state.apdex_experience_device_mix == original_mix
            assert refactor._mix_inherited(state) is inherited
            assert dict(os.environ) == original_environment
            assert ini.read_bytes() == original_ini
            assert not saved
            assert "DESTINO DA ALTERAÇÃO" not in output.getvalue()
        assert initial_fingerprint != ""  # valid real fingerprint
    finally:
        reuse._ARCHITECTURE_SELECTION.pop(id(state), None)
        refactor._SESSION_META.clear()


def test_architecture_actual_choice_prompts_only_on_change(monkeypatch, tmp_path):
    import builtins
    from contextlib import redirect_stdout
    from io import StringIO
    from rasai.architecture_choice import ArchitectureChoice
    from rasai import audit_configuration_reuse_console as reuse
    from rasai import console_ui_refactor as refactor

    console, state, ini, saved = _compose_architecture_console_for_cancel(
        monkeypatch, tmp_path
    )
    try:
        for option, mode in (("1", "UNFORCED"), ("2", "AUTO"), ("3", "DECLARED")):
            reuse._ARCHITECTURE_SELECTION[id(state)] = ArchitectureChoice("AUTO") if mode != "AUTO" else ArchitectureChoice("UNFORCED")
            count = []
            def answer(prompt=""):
                if prompt == "Opção (V para voltar): ":
                    return option
                if prompt == "Tipo (V para voltar): ":
                    return "3"  # CSR_SPA
                if prompt == "Escolha: ":
                    count.append(prompt)
                    return "1"  # do not persist test choice to INI
                raise AssertionError(f"Unexpected input prompt: {prompt!r}")
            monkeypatch.setattr(builtins, "input", answer)
            output = StringIO()
            with redirect_stdout(output):
                console._configure(state, "Y")
            assert reuse._ARCHITECTURE_SELECTION[id(state)].mode == mode
            assert count == ["Escolha: "]
            assert "DESTINO DA ALTERAÇÃO" in output.getvalue()
            assert not saved
            assert ini.read_text(encoding="utf-8") == "[test]\nvalue = unchanged\n"
    finally:
        reuse._ARCHITECTURE_SELECTION.pop(id(state), None)
        refactor._SESSION_META.clear()
