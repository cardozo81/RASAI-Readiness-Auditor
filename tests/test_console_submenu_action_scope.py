from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from types import ModuleType, SimpleNamespace

from rasai import console_submenu_action_scope as scope
from rasai.console_confirmation_contract import confirm_continue


def test_integration_submenu_hides_global_configuration_shortcuts(monkeypatch) -> None:
    state = SimpleNamespace(error="")

    def submenu(console_module, current_state):
        print("AÇÕES")
        print("T. Validar todas as integrações configuradas com probe seguro")
        print("C. Configuração avançada / todas as variáveis")
        print("V. Voltar")
        return input("Escolha: ")

    wrapped = scope._wrap_integration_surface(submenu)
    monkeypatch.setattr("builtins.input", lambda prompt="": "V")
    with redirect_stdout(StringIO()) as output:
        assert wrapped(ModuleType("console"), state) == "V"

    rendered = output.getvalue()
    assert "T. Validar todas" in rendered
    assert "V. Voltar" in rendered
    assert "Configuração avançada / todas as variáveis" not in rendered


def test_integration_global_shortcut_is_not_executable_from_nested_screen(monkeypatch) -> None:
    state = SimpleNamespace(error="")

    def submenu(console_module, current_state):
        print("C. Abrir catálogo completo de configuração")
        return input("Escolha: ")

    wrapped = scope._wrap_integration_surface(submenu)
    monkeypatch.setattr("builtins.input", lambda prompt="": "C")
    with redirect_stdout(StringIO()) as output:
        result = wrapped(ModuleType("console"), state)

    assert result == "__GLOBAL_CONFIG_ONLY_AT_HOME__"
    assert "INÍCIO > Todas as configurações" in state.error
    assert "Abrir catálogo completo" not in output.getvalue()


def test_normal_post_run_keeps_only_contextual_actions(monkeypatch) -> None:
    state = SimpleNamespace(error="")

    def post_run(current_state):
        print("AÇÕES DA AUDITORIA DESTA SESSÃO")
        print("P. Abrir pasta da auditoria")
        print("I. Abrir relatório HTML")
        print("V. Voltar ao menu")
        print("Q. Sair")
        return input("Escolha: ") == "Q"

    wrapped = scope._wrap_post_run_actions(post_run)
    monkeypatch.setattr("builtins.input", lambda prompt="": "Q")
    with redirect_stdout(StringIO()) as output:
        result = wrapped(state)

    rendered = output.getvalue()
    assert "Q. Sair" not in rendered
    assert "P. Abrir pasta" in rendered
    assert "I. Abrir relatório" in rendered
    assert "V. Voltar" in rendered
    assert result is False
    assert state.error == "Sair está disponível somente no menu INÍCIO."


def test_reprocess_result_hides_global_exit_and_maps_q_to_back(monkeypatch) -> None:
    state = SimpleNamespace(error="")

    def post_run(console_module, current_state):
        print("AÇÕES DO REPROCESSAMENTO")
        print("R. Reprocessar novamente")
        print("P. Abrir pasta da auditoria")
        print("I. Abrir relatório HTML")
        print("V. Voltar para a auditoria selecionada")
        print("Q. Sair")
        choice = input("Escolha: ")
        if choice == "V":
            return "BACK"
        print("opção inválida; use R, P, I, V ou Q")
        return "INVALID"

    wrapped = scope._wrap_reprocess_post_actions(post_run)
    monkeypatch.setattr("builtins.input", lambda prompt="": "Q")
    with redirect_stdout(StringIO()) as output:
        result = wrapped(ModuleType("console"), state)

    rendered = output.getvalue()
    assert result == "BACK"
    assert "Q. Sair" not in rendered
    assert "Sair" not in rendered
    assert state.error == "Sair está disponível somente no menu INÍCIO."


def test_integration_confirmation_accepts_uppercase_c_inside_scoped_surface(monkeypatch) -> None:
    state = SimpleNamespace(error="")

    def submenu(console_module, current_state):
        return confirm_continue(
            "Confirmar e executar teste",
            back_label="Voltar sem testar",
        )

    wrapped = scope._wrap_integration_surface(submenu)
    monkeypatch.setattr("builtins.input", lambda prompt="": "C")

    assert wrapped(ModuleType("console"), state) is True
    assert state.error == ""


def test_integration_confirmation_accepts_lowercase_c_inside_scoped_surface(monkeypatch) -> None:
    state = SimpleNamespace(error="")

    def submenu(console_module, current_state):
        return confirm_continue(
            "Confirmar e executar teste",
            back_label="Voltar sem testar",
        )

    wrapped = scope._wrap_integration_surface(submenu)
    monkeypatch.setattr("builtins.input", lambda prompt="": "c")

    assert wrapped(ModuleType("console"), state) is True
    assert state.error == ""


def test_integration_generic_c_remains_blocked_outside_confirmation_prompt(monkeypatch) -> None:
    state = SimpleNamespace(error="")

    def submenu(console_module, current_state):
        return input("Escolha: ")

    wrapped = scope._wrap_integration_surface(submenu)
    monkeypatch.setattr("builtins.input", lambda prompt="": "c")

    assert wrapped(ModuleType("console"), state) == "__GLOBAL_CONFIG_ONLY_AT_HOME__"
    assert "INÍCIO > Todas as configurações" in state.error
