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


def test_provider_actions_explain_exact_credential_scope() -> None:
    state = _state()
    assert "somente nesta sessão" in ux._rewrite_line(state, "S. Setar/alterar Key na sessão")
    assert "nunca no INI" in ux._rewrite_line(state, "P. Persistir/remover Key no Windows/User")
    assert "Windows/User permanece inalterado" in ux._rewrite_line(
        state, "L. Limpar Key somente da sessão"
    )
    deleted = ux._rewrite_line(state, "X. Excluir Key da sessão e do Windows/User")
    assert "sessão + Windows/User" in deleted
    assert "Windows/Machine não é alterado" in deleted
    assert "não apaga a credencial" in ux._rewrite_line(
        state, "A. Habilitar/desabilitar no AUTO sem apagar a Key"
    )


def test_legacy_secret_actions_keep_the_same_storage_contract() -> None:
    state = _state()
    assert ux._rewrite_line(state, "S. Setar/alterar sessão") == (
        "S. Definir/alterar valor somente nesta sessão"
    )
    assert "persistência não é alterada" in ux._rewrite_line(state, "R. Remover da sessão")
    assert "Windows/User" in ux._rewrite_line(
        state, "P. Persistir/remover credencial no Windows"
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


def test_consolidated_result_actions_name_their_artifacts() -> None:
    state = _state()
    assert ux._rewrite_line(state, "A. Abrir relatório") == "A. Abrir relatório consolidado gerado"
    assert "arquivos deste relatório consolidado" in ux._rewrite_line(state, "P. Abrir pasta")


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
    assert ux._rewrite_line(state, "Atenção             : haverá impacto") == "ALERTA     : haverá impacto"
    assert ux._rewrite_line(state, "Observação: somente contexto") == "INFO       : somente contexto"
    assert ux._rewrite_line(state, "Observação          : somente contexto") == "INFO       : somente contexto"
    assert ux._rewrite_line(state, "A alteração já está ativa nesta sessão.") == (
        "OK         : Alteração aplicada nesta sessão."
    )
    assert ux._rewrite_line(state, "Ainda não validado.") == (
        "INFO       : Integração ainda não validada. Use T para validar/retestar."
    )


def test_save_exit_and_artifact_messages_use_semantic_severity() -> None:
    state = _state()
    saved = ux._rewrite_line(state, "Configuração salva em: C:/tmp/rasai-console.ini")
    assert saved.startswith("OK")
    assert "Configuração não sensível salva" in saved
    security = ux._rewrite_line(state, "Chaves/API tokens não são gravados no INI por segurança.")
    assert security.startswith("INFO")
    assert "Credenciais e tokens" in security
    dirty = ux._rewrite_line(state, "Há alterações de configuração ainda não salvas no arquivo INI.")
    assert dirty.startswith("ALERTA")
    opened = ux._rewrite_line(state, "Aberto: C:/audits/AUD-X/report/index.html")
    assert opened.startswith("OK")
    failed = ux._rewrite_line(state, "Não foi possível abrir: C:/audits/AUD-X/report/index.html")
    assert failed.startswith("ERRO")


def test_expected_user_cancellation_is_info_not_error() -> None:
    state = _state()
    rendered = ux._rewrite_line(state, "Erro        : persistência cancelada")
    assert rendered.startswith("INFO")
    rendered = ux._rewrite_line(state, "Erro        : artefato ainda não disponível para esta auditoria")
    assert rendered.startswith("INFO")


def test_consolidation_failures_and_filters_get_actionable_severity() -> None:
    state = _state()
    failure = ux._rewrite_line(state, "Falha na consolidação: ValueError: x")
    assert failure.startswith("ERRO")
    assert "Falha na consolidação" in failure
    invalid_filter = ux._rewrite_line(state, "Filtro inválido: data inicial posterior à final")
    assert invalid_filter.startswith("ERRO")
    assert "Corrija os valores" in invalid_filter
    reference = ux._rewrite_line(state, "A auditoria de referência deve ser anterior à auditoria atual.")
    assert reference.startswith("ALERTA")
    assert "Selecione outro par" in reference


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


def test_install_wraps_all_public_local_console_boundaries_without_changing_results() -> None:
    console = ModuleType("test_console_operator_ux")

    def menu(state):
        print("Erro        : ação inválida")
        print("S. Definir / alterar")
        return "V"

    console._menu = menu
    console._configure = lambda state, choice: None
    console._environment_menu = lambda state: None
    console._save_configuration = lambda state: True
    console._confirm_exit = lambda state: False
    console._artifact_action = lambda state, action: None
    console.render_help = lambda state: None
    console.render_m23_help = lambda state: None
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
    assert console._save_configuration(state) is True
    assert console._confirm_exit(state) is False
    assert console.run_audit_from_console(state) == 7
    assert console._post_run_actions(state) is False
    for name in (
        "_menu",
        "_configure",
        "_environment_menu",
        "_save_configuration",
        "_confirm_exit",
        "_artifact_action",
        "render_help",
        "render_m23_help",
        "run_audit_from_console",
        "_post_run_actions",
    ):
        assert getattr(getattr(console, name), "_rasai_operator_ux_consistency", False)
