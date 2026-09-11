from __future__ import annotations

from types import SimpleNamespace


def _fake_console(**overrides):
    base = dict(
        GREEN="GREEN",
        YELLOW="YELLOW",
        RED="RED",
        DIM="DIM",
        CYAN="CYAN",
        paint=lambda text, color, bold=False: f"<{color}:{'B' if bold else 'N'}>{text}</{color}>",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_provider_status_colors_follow_console_semantics() -> None:
    from rasai import ai_provider_console_management as management
    from rasai.console_config import Capability

    console = _fake_console()

    assert "<DIM:N>DESABILITADA</DIM>" == management._provider_status_badge(
        console, "none", Capability(True, "sem IA")
    )
    assert "<GREEN:B>APTO</GREEN>" == management._provider_status_badge(
        console, "gemini", Capability(True, "Google Gemini/gemini-3.8-flash")
    )
    assert "<YELLOW:B>CONFIGURAR</YELLOW>" == management._provider_status_badge(
        console, "gemini", Capability(False, "GEMINI_API_KEY não configurada")
    )
    assert "<RED:B>INDISPONÍVEL</RED>" == management._provider_status_badge(
        console, "gemini", Capability(False, "bloqueado após erro: AUTHENTICATION_ERROR")
    )


def test_auto_membership_colors_use_green_and_dim() -> None:
    from rasai import ai_provider_console_management as management

    console = _fake_console()

    assert "<GREEN:B>INCLUÍDO NO AUTO</GREEN>" == management._auto_membership_badge(console, False)
    assert "<DIM:N>EXCLUÍDO DO AUTO</DIM>" == management._auto_membership_badge(console, True)


def test_unavailable_provider_remains_selectable_for_configuration(monkeypatch) -> None:
    from rasai import ai_provider_console_management as management
    from rasai.console_config import Capability

    fake = _fake_console(
        PROVIDER_MENU_CHOICES=("none", "gemini", "auto"),
        provider_capabilities=lambda blocks=None: {
            "none": Capability(True, "sem IA"),
            "gemini": Capability(False, "GEMINI_API_KEY não configurada"),
            "auto": Capability(False, "nenhum provider apto"),
        },
        render_header=lambda state: None,
    )
    state = SimpleNamespace(runtime_blocks={})
    answers = iter(("2",))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert management._choose_provider(state, fake) == "gemini"


def test_credential_change_clears_stale_provider_block(monkeypatch) -> None:
    from rasai.ai_provider_console_management import _refresh_provider_after_credential_change
    from rasai.console_config import State, provider_capabilities

    state = State()
    state.runtime_blocks["gemini"] = "AUTHENTICATION_ERROR"
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    assert provider_capabilities(blocks=state.runtime_blocks)["gemini"].available is False

    _refresh_provider_after_credential_change(state, "GEMINI_API_KEY")

    capability = provider_capabilities(blocks=state.runtime_blocks)["gemini"]
    assert "gemini" not in state.runtime_blocks
    assert capability.available is True


def test_auto_disable_does_not_delete_provider_key(monkeypatch) -> None:
    from rasai.ai_provider_console_management import _set_auto_membership
    from rasai.provider_runtime_policy import AUTO_EXCLUDE_ENV, configured_auto_exclusions

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.delenv(AUTO_EXCLUDE_ENV, raising=False)

    _set_auto_membership("openai", included=False)

    assert "openai" in configured_auto_exclusions()
    assert __import__("os").environ["OPENAI_API_KEY"] == "sk-test-openai"

    _set_auto_membership("openai", included=True)

    assert "openai" not in configured_auto_exclusions()
    assert __import__("os").environ["OPENAI_API_KEY"] == "sk-test-openai"
