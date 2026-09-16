from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from types import ModuleType, SimpleNamespace

from rasai import console_operator_ux_consistency as ux


def _state(**overrides):
    values = {"error": "", "operation": "LOCAL:MENU"}
    values.update(overrides)
    return SimpleNamespace(**values)


def test_configuration_actions_explain_scope_and_persistence() -> None:
    state = _state()
    assert ux._rewrite_line(state, "S. Definir / alterar") == (
        "S. Definir / alterar valor — depois escolha sessão ou persistência"
    )
    assert "arquivo/Windows permanecem inalterados" in ux._rewrite_line(
        state, "L. Limpar override somente desta sessão"
    )
    assert "nunca no INI" in ux._rewrite_line(
        state, "P. Gerenciar persistência Windows/User"
    )


def test_catalog_and_history_actions_state_their_effect() -> None:
    state = _state()
    assert "plano da próxima auditoria" in ux._rewrite_line(
        state, "D. Remover este catálogo do plano"
    )
    reuse = ux._rewrite_line(state, "2. Carregar esta configuração para uma nova auditoria")
    assert "NOVA auditoria" in reuse
    assert "AUD de origem não é alterada" in reuse
    assert "arquivos e artefatos" in ux._rewrite_line(state, "3. Mostrar caminhos de artefatos")


def test_integration_validation_actions_warn_about_possible_quota_use() -> None:
    state = _state()
    individual = ux._rewrite_line(state, "T. Validar / retestar integração")
    bulk = ux._rewrite_line(state, "T. Validar todas as integrações configuradas com probe seguro")
    assert "pode consumir quota técnica" in individual
    assert "somente probes seguros" in bulk
    assert "pode consumir quota" in bulk


def test_semantic_messages_use_one_operator_vocabulary() -> None:
    state = _state()
    assert ux._rewrite_line(state, "ATENÇÃO: haverá impacto") == "ALERTA     : haverá impacto"
    assert ux._rewrite_line(state, "Observação: somente contexto") == "INFO       : somente contexto"
    assert ux._rewrite_line(state, "A alteração já está ativa nesta sessão.") == (
        "OK         : Alteração aplicada nesta sessão."
    )
    assert ux._rewrite_line(state, "Ainda não validado.") == (
        "INFO       : Integração ainda não validada. Use T para validar/retestar."
    )


def test_generic_errors_are_actionable_instead_of_opaque() -> None:
    state = _state()
    rendered = ux._rewrite_line(state, "Erro        : ação inválida")
    assert rendered.startswith("ERRO")
    assert "Ação não reconhecida" in rendered
    assert "seção AÇÕES" in rendered

    rendered = ux._rewrite_line(state, "Erro        : ID/ação inválido")
    assert "ID ou ação não reconhecido" in rendered
    assert "ID exibido" in rendered


def test_restore_warnings_are_not_presented_as_errors() -> None:
    state = _state(operation="LOCAL:RESTORE_SYSTEM_DEFAULTS")
    rendered = ux._rewrite_line(state, "Erro        : Windows/Machine preservado")
    assert rendered.startswith("ALERTA")
    assert "Windows/Machine preservado" in rendered


def test_multiline_action_blocks_are_rewritten_without_changing_navigation() -> None:
    state = _state()
    text = (
        "S. Salvar configuração no arquivo [SEM SECRETS]\n"
        "L. Carregar configuração de AUD [NOVA EXECUÇÃO]\n"
        "V. Voltar ao início\n"
    )
    rendered = ux._rewrite_text(state, text)
    assert "SECRETS NÃO SÃO GRAVADOS" in rendered
    assert "CRIA NOVA EXECUÇÃO" in rendered
    assert "V. Voltar ao início" in rendered
    assert rendered.endswith("\n")


def test_install_wraps_public_boundaries_without_changing_return_values() -> None:
    console = ModuleType("test_console_operator_ux")

    def menu(state):
        print("Erro        : ação inválida")
        print("S. Definir / alterar")
        return "V"

    console._menu = menu
    console._configure = lambda state, choice: None
    console._environment_menu = lambda state: None
    console.run_audit_from_console = lambda state: 7
    console._post_run_actions = lambda state: False

    ux.install(console)
    state = _state()
    with redirect_stdout(StringIO()) as output:
        result = console._menu(state)

    assert result == "V"
    rendered = output.getvalue()
    assert "Ação não reconhecida" in rendered
    assert "depois escolha sessão ou persistência" in rendered
    assert console.run_audit_from_console(state) == 7
    assert console._post_run_actions(state) is False
