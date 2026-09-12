"""Safe cancellation and reset UX for interactive-console configuration.

This module is deliberately a presentation/runtime adapter over the canonical
EnvironmentSpec catalog. It does not introduce a second configuration contract.

Reset semantics:
- scope is a functional EnvironmentSpec category or the complete known catalog;
- session values are removed/reset first;
- optional INI persistence uses the canonical console writer and never stores secrets;
- optional OS cleanup is limited to Windows/User, the only OS persistence scope managed
  by RASAi;
- Windows/Machine is never modified and is reported as preserved.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Callable

from rasai.console_session import get_config_path
from rasai.console_settings import resolve_config_path, save_console_config
from rasai.windows_environment import (
    machine_environment_value,
    remove_user_environment,
    user_environment_value,
)


@dataclass(frozen=True, slots=True)
class ResetResult:
    session_removed: int
    user_removed: int
    machine_preserved: tuple[str, ...]
    issues: tuple[str, ...]


def _unique_specs(specs: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple({spec.name: spec for spec in specs}.values())


def _staged_secret_value(
    *,
    state: Any,
    name: str,
    reader: Callable[[str], str],
    validator: Callable[[str, str], str],
) -> str | None:
    """Read and validate a secret without mutating the environment until confirmed."""
    print("Digite/cole o novo valor. Após Enter, confirme ou cancele sem alterar o valor atual.")
    raw = reader(f"{name}: ")
    try:
        validated = validator(name, raw)
    except (ValueError, OverflowError) as exc:
        state.error = str(exc)
        return None
    print(f"Valor recebido: {len(raw)} caractere(s); conteúdo permanece oculto.")
    print("C. Confirmar alteração")
    print("V. Cancelar e manter o valor atual")
    while True:
        action = input("Escolha: ").strip().upper()
        if action == "C":
            state.error = ""
            return validated
        if action == "V":
            state.error = ""
            state.operation = "LOCAL:SECRET_EDIT_CANCELLED"
            return None
        print("Opção inválida. Use C para confirmar ou V para cancelar.")


def _reset_preview(specs: tuple[Any, ...]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    unique = _unique_specs(specs)
    session = tuple(spec.name for spec in unique if spec.name in os.environ)
    user = tuple(spec.name for spec in unique if user_environment_value(spec.name) is not None)
    machine = tuple(spec.name for spec in unique if machine_environment_value(spec.name) is not None)
    return session, user, machine


def _reset_specs(
    facade: Any,
    state: Any,
    specs: tuple[Any, ...],
    *,
    persist_ini: bool,
    remove_user_persisted: bool,
) -> ResetResult:
    """Reset known environment overrides without ever deleting Machine scope."""
    unique = _unique_specs(specs)
    _, _, machine = _reset_preview(unique)
    session_removed = 0
    user_removed = 0
    issues: list[str] = []

    for spec in unique:
        if spec.name in os.environ:
            os.environ.pop(spec.name, None)
            session_removed += 1

        if remove_user_persisted and user_environment_value(spec.name) is not None:
            try:
                if remove_user_environment(spec.name):
                    user_removed += 1
            except (OSError, ValueError) as exc:
                issues.append(f"{spec.name}: {type(exc).__name__}: {exc}")

        if facade.base_environment._is_sensitive_spec(spec):
            facade.base_environment._sync_secret_state(state, spec.name)
        facade.base_environment._apply_change(state, spec.name)
        runtime_issue = str(getattr(state, "error", "") or "").strip()
        if runtime_issue:
            issues.append(f"{spec.name}: {runtime_issue}")

    # Recompose dependent provider/model metadata after the scope was reset.
    facade.refresh_specs()

    if persist_ini:
        try:
            destination = get_config_path(state) or resolve_config_path()
            save_console_config(state, destination)
        except (OSError, ValueError) as exc:
            issues.append(f"rasai-console.ini: {type(exc).__name__}: {exc}")

    unique_issues = tuple(dict.fromkeys(issues))
    state.error = "; ".join(unique_issues)
    state.operation = (
        "LOCAL:CONFIG_RESET_SESSION_USER"
        if remove_user_persisted
        else "LOCAL:CONFIG_RESET_SESSION_INI" if persist_ini else "LOCAL:CONFIG_RESET_SESSION"
    )
    return ResetResult(session_removed, user_removed, machine, unique_issues)


def _reset_scope(facade: Any, state: Any, title: str, specs: tuple[Any, ...]) -> None:
    session, user, machine = _reset_preview(specs)
    facade.base_environment.render_header(state)
    facade._breadcrumb("Reset de variáveis", title)
    print("RESET SEGURO DE VARIÁVEIS\n")
    print(f"Escopo                    : {title}")
    print(f"Definidas na sessão       : {len(session)}")
    print(f"Persistidas Windows/User  : {len(user) if os.name == 'nt' else 'n/a'}")
    print(f"Persistidas Windows/Machine: {len(machine) if os.name == 'nt' else 'n/a'}")
    print()
    print("O reset atua somente nas variáveis conhecidas do catálogo RASAi deste escopo.")
    print("Windows/Machine nunca é alterado pelo console.")
    print("Reset de INI usa o writer canônico e continua excluindo secrets.")
    print("Variáveis ligadas ao estado do console retornam ao default/auto efetivo.")
    print("\n1. Resetar somente a sessão atual")
    print("2. Resetar sessão e persistir o estado resetado no rasai-console.ini")
    if os.name == "nt":
        print("3. Resetar sessão + INI + remover também Windows/User")
    print("V. Voltar sem alterar")

    action = input("Escolha: ").strip().upper()
    if action == "V":
        state.error = ""
        state.operation = "LOCAL:CONFIG_RESET_CANCELLED"
        return
    if action not in {"1", "2", "3"} or (action == "3" and os.name != "nt"):
        state.error = "opção de reset inválida"
        return

    persist_ini = action in {"2", "3"}
    remove_user = action == "3"
    affected = set(session)
    if remove_user:
        affected.update(user)
    if persist_ini:
        # Even with no current process value, persisting defaults may be the desired reset.
        affected.update(spec.name for spec in specs)

    if not affected:
        state.error = ""
        state.operation = "LOCAL:CONFIG_RESET_NOOP"
        return

    print()
    print(f"Serão resetadas {len(affected)} variável(is)/defaults deste escopo.")
    if remove_user and machine:
        print(
            f"ATENÇÃO: {len(machine)} valor(es) em Windows/Machine serão preservados e podem "
            "voltar a ser herdados por um novo processo."
        )
    if input("Para confirmar, digite RESETAR: ").strip().upper() != "RESETAR":
        state.error = ""
        state.operation = "LOCAL:CONFIG_RESET_CANCELLED"
        return

    result = _reset_specs(
        facade,
        state,
        specs,
        persist_ini=persist_ini,
        remove_user_persisted=remove_user,
    )
    if not result.issues:
        state.error = ""


def _reset_menu(facade: Any, state: Any) -> None:
    facade.refresh_specs()
    grouped = {
        category: tuple(spec for spec in facade.SPECS if spec.category == category)
        for category in facade.CATEGORIES
    }
    while True:
        facade.base_environment.render_header(state)
        facade._breadcrumb("Reset de variáveis")
        print("Escolha o escopo funcional. Nenhuma exclusão ocorre sem confirmação explícita.\n")
        choices: dict[str, str] = {}
        for index, category in enumerate(facade.CATEGORIES, 1):
            print(f" {index:2d}. {category}")
            choices[str(index)] = category
        print("\n A. Todas as variáveis conhecidas")
        print(" V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return
        if raw == "A":
            _reset_scope(facade, state, "Todas", facade.SPECS)
            return
        category = choices.get(raw)
        if category:
            _reset_scope(facade, state, category, grouped[category])
            return
        state.error = "grupo de reset inválido"


def _install_environment_facade() -> None:
    from rasai import console_provider_environment as facade

    if getattr(facade, "_rasai_safe_reset_cancel", False):
        return

    def variable_menu(state: Any, spec: Any) -> None:
        while True:
            spec = facade.normalize_spec(spec)
            facade.base_environment.render_header(state)
            facade._breadcrumb(spec.category, facade.context_for(spec), spec.name)
            facade.base_environment._render_detail(spec)
            facade.render_enrichment(spec)
            sensitive = facade.base_environment._is_sensitive_spec(spec)
            print()
            print(f"Estado de decisão: {facade.decision_badge(spec)} | {facade._selection_state(spec)}")
            if sensitive:
                print(facade.paint("Secret: use sessão/Windows User; nunca será gravado no rasai-console.ini.", facade.YELLOW))
            elif spec.default is not None and not (os.environ.get(spec.name) or "").strip():
                print(facade.paint("Nenhuma ação é necessária para manter o default mostrado acima.", facade.DIM))

            if sensitive:
                print("\nAÇÕES\nS. Definir/alterar na sessão\nR. Remover da sessão\nP. Persistência Windows/User\nD. Documentação\nV. Voltar")
            else:
                print("\nAÇÕES\nS. Definir/alterar override\nR. Remover override e voltar ao default/auto\nD. Documentação\nV. Voltar")
            action = input("Escolha: ").strip().upper()
            if action == "V":
                return
            if action == "D":
                facade.base_environment._open_docs(state)
                continue
            if action == "P" and sensitive:
                try:
                    facade.base_environment._persist_secret(state, spec)
                except (OSError, ValueError) as exc:
                    state.error = f"falha de persistência: {type(exc).__name__}: {exc}"
                continue
            if action == "R":
                os.environ.pop(spec.name, None)
                if sensitive:
                    facade.base_environment._sync_secret_state(state, spec.name)
                facade.base_environment._apply_change(state, spec.name)
                state.operation = "LOCAL:CONFIG_OVERRIDE_REMOVED"
                continue
            if action != "S":
                state.error = "ação inválida"
                continue

            try:
                if spec.accepted:
                    raw = facade.prompt_guided_value(spec)
                    if raw is None:
                        continue
                    validated = facade._validate(spec.name, raw)
                elif sensitive:
                    validated = _staged_secret_value(
                        state=state,
                        name=spec.name,
                        reader=facade.getpass,
                        validator=facade._validate,
                    )
                    if validated is None:
                        continue
                else:
                    raw = input(f"{spec.name}: ")
                    validated = facade._validate(spec.name, raw)
                os.environ[spec.name] = validated
                if sensitive:
                    facade.base_environment._sync_secret_state(state, spec.name)
                facade.base_environment._apply_change(state, spec.name)
                state.operation = "LOCAL:CONFIG_UPDATED"
                facade.refresh_specs()
            except (ValueError, OverflowError) as exc:
                state.error = str(exc)

    def environment_menu(state: Any) -> None:
        facade.refresh_specs()
        while True:
            grouped = {
                category: tuple(spec for spec in facade.SPECS if spec.category == category)
                for category in facade.CATEGORIES
            }
            facade.base_environment.render_header(state)
            facade._breadcrumb("Configuração avançada")
            print("FLUXO RECOMENDADO")
            print("  1. Use o menu principal para Entrada, Device, IA, Web Performance e Apdex.")
            print("  2. Use esta área para integrações, credenciais e overrides avançados.")
            print("  3. Dentro de cada grupo, variáveis relacionadas aparecem juntas por contexto/recurso.")
            print("  4. Valores fechados são selecionados de listas; texto livre fica restrito a dados realmente abertos.")
            print("  5. Secrets podem ser cancelados depois da digitação, antes de alterar o valor atual.")
            print("  6. Reset pode atuar por grupo ou em todo o catálogo, com remoção opcional de Windows/User.")
            print("  7. Antes de executar, revise o preflight; integração ausente não vira finding do website.\n")
            print(facade.paint("AUTO/Padrão significa deixar o runtime resolver pelo registry e requisitos; não é necessário repetir defaults.", facade.DIM))
            print(facade.paint("Secrets nunca entram no INI. Windows/User exige ação explícita do operador; Windows/Machine nunca é removido pelo console.", facade.YELLOW))
            print()

            choices: dict[str, str] = {}
            for index, category in enumerate(facade.CATEGORIES, 1):
                specs = grouped[category]
                configured = sum(1 for spec in specs if (os.environ.get(spec.name) or "").strip())
                marker = facade.paint(f"{configured}/{len(specs)} definidos", facade.GREEN if configured else facade.DIM)
                print(f" {index:2d}. {category:<36} {marker}")
                choices[str(index)] = category
            print("\n A. Todas as variáveis")
            print(" R. Resetar variáveis por grupo ou todas")
            print(f" D. Abrir documentação detalhada (docs/{facade.DOCUMENT_NAME})")
            print(" V. Voltar")
            raw = input("Escolha: ").strip().upper()
            if raw == "V":
                return
            if raw == "D":
                facade.base_environment._open_docs(state)
                continue
            if raw == "R":
                _reset_menu(facade, state)
                continue
            if raw == "A":
                facade._category_menu(state, "Todas", facade.SPECS)
                continue
            category = choices.get(raw)
            if category:
                facade._category_menu(state, category, grouped[category])
            else:
                state.error = "grupo inválido"

    facade._variable_menu = variable_menu
    facade.environment_menu = environment_menu
    facade._rasai_safe_reset_cancel = True


def _install_ai_provider_secret_cancellation() -> None:
    from rasai import ai_provider_console_management as manager
    from rasai import interactive_console as console

    if getattr(manager, "_rasai_secret_cancel", False):
        return
    original_manage = manager._manage_provider

    def manage_provider(state: Any, console_module: Any, provider_id: str) -> str:
        # Keep the canonical manager for every action except secret replacement. The
        # copied loop below mirrors the current public contract so the secret is staged
        # and committed only after explicit confirmation.
        registration = manager.get_provider_registration(provider_id)
        if registration is None:
            state.error = f"provider desconhecido: {provider_id}"
            return "back"
        key_env = registration.key_env

        while True:
            capabilities = console_module.provider_capabilities(blocks=state.runtime_blocks)
            capability = capabilities[registration.id]
            excluded = registration.id in set(manager.configured_auto_exclusions())
            session_key = bool((os.environ.get(key_env) or "").strip())
            user_key = console_module.user_environment_value(key_env) is not None
            machine_key = console_module.machine_environment_value(key_env) is not None

            console_module.render_header(state)
            print(f"GERENCIAR IA - {registration.display_name}\n")
            print(f"Estado execução     : {manager._provider_status_badge(console_module, registration.id, capability)}")
            print(f"Motivo              : {manager._provider_reason(console_module, registration.id, capability)}")
            print(f"Credencial          : {key_env}")
            print(f"Sessão atual        : {manager._presence_badge(console_module, session_key, yes='[SET]', no='<não definida>')}")
            print(f"Windows / User      : {manager._presence_badge(console_module, user_key, yes='[PERSISTIDA]', no='<não persistida>')}")
            print(f"Windows / Machine   : {manager._presence_badge(console_module, machine_key, yes='[PERSISTIDA]', no='<não persistida>')}")
            if registration.auto_eligible:
                print(f"Pool AUTO           : {manager._auto_membership_badge(console_module, excluded)}")
            print("\nS. Setar/alterar Key na sessão")
            print("P. Persistir/remover Key no Windows/User")
            print("L. Limpar Key somente da sessão")
            print("X. Excluir Key da sessão e do Windows/User")
            if registration.auto_eligible:
                print("A. Habilitar/desabilitar no AUTO sem apagar a Key")
            print("U. Usar este provider nesta auditoria")
            print("V. Voltar")
            action = input("Escolha: ").strip().upper()

            if action == "V":
                return "back"
            if action == "S":
                validated = _staged_secret_value(
                    state=state,
                    name=key_env,
                    reader=console_module.getpass,
                    validator=console_module.validate_env_value,
                )
                if validated is None:
                    continue
                os.environ[key_env] = validated
                manager._refresh_provider_after_credential_change(state, key_env)
                console_module._sync_secret_volatility(state, key_env)
                state.error = ""
                continue
            if action == "P":
                console_module._secret_persistence_action(state, key_env)
                manager._refresh_provider_after_credential_change(state, key_env)
                continue
            if action == "L":
                os.environ.pop(key_env, None)
                manager._refresh_provider_after_credential_change(state, key_env)
                console_module._sync_secret_volatility(state, key_env)
                state.error = ""
                continue
            if action == "X":
                manager._delete_provider_key(state, console_module, key_env, registration.id)
                continue
            if action == "A" and registration.auto_eligible:
                manager._set_auto_membership(registration.id, included=excluded)
                state.error = ""
                continue
            if action == "U":
                capability = console_module.provider_capabilities(blocks=state.runtime_blocks)[registration.id]
                if not capability.available:
                    state.error = (
                        f"{registration.display_name} ainda indisponível: {capability.reason}. "
                        "Configure uma Key válida antes de usar."
                    )
                    continue
                state.ai_provider = registration.id
                state.ai_model = None
                state.ai_reasoning = None
                state.error = ""
                return "use"
            state.error = "opção inválida para gerenciamento do provider"

    manage_provider._rasai_original = original_manage
    manager._manage_provider = manage_provider
    manager._rasai_secret_cancel = True


def install_environment_reset() -> None:
    _install_environment_facade()


def install_ai_secret_cancellation() -> None:
    _install_ai_provider_secret_cancellation()
