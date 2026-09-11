"""Interactive AI-provider credential management for the local console.

Execution readiness and configurability are intentionally separate concepts. A provider
with no key must remain selectable so the operator can configure, replace, clear or
remove its credential without leaving the AI menu.
"""
from __future__ import annotations

import os
from typing import Any

from rasai.provider_registry import get_provider_registration, provider_registrations
from rasai.provider_runtime_policy import (
    AI_TIMEOUT_ENV,
    AUTO_EXCLUDE_ENV,
    REASONING_OPTIONS,
    apply_console_reasoning_environment,
    configured_auto_exclusions,
    configured_reasoning,
)

_INSTALLED = False


def _registration_for_key(name: str):
    for registration in provider_registrations():
        if registration.key_env == name:
            return registration
    return None


def _refresh_provider_after_credential_change(state: Any, key_env: str) -> None:
    """Invalidate stale runtime failures after a credential/configuration change."""
    registration = _registration_for_key(key_env)
    if registration is not None:
        getattr(state, "runtime_blocks", {}).pop(registration.id, None)
        for alias in registration.aliases:
            getattr(state, "runtime_blocks", {}).pop(alias, None)


def _needs_configuration(capability: Any) -> bool:
    reason = str(getattr(capability, "reason", "")).casefold()
    return any(token in reason for token in ("não configurada", "nao configurada", "not configured"))


def _provider_status_badge(console: Any, name: str, capability: Any) -> str:
    """Render provider state using the same semantic colors as the rest of the console."""
    if name == "none":
        return console.paint("DESABILITADA", console.DIM)
    if bool(getattr(capability, "available", False)):
        return console.paint("APTO", console.GREEN, bold=True)
    if name != "auto" and _needs_configuration(capability):
        return console.paint("CONFIGURAR", console.YELLOW, bold=True)
    return console.paint("INDISPONÍVEL", console.RED, bold=True)


def _provider_reason(console: Any, name: str, capability: Any) -> str:
    reason = str(getattr(capability, "reason", ""))
    if name == "none":
        return console.paint(reason, console.DIM)
    if bool(getattr(capability, "available", False)):
        return console.paint(reason, console.CYAN)
    if name != "auto" and _needs_configuration(capability):
        return console.paint(reason, console.YELLOW)
    return console.paint(reason, console.RED)


def _presence_badge(console: Any, active: bool, *, yes: str, no: str) -> str:
    return console.paint(yes if active else no, console.GREEN if active else console.DIM, bold=active)


def _auto_membership_badge(console: Any, excluded: bool) -> str:
    return console.paint(
        "EXCLUÍDO DO AUTO" if excluded else "INCLUÍDO NO AUTO",
        console.DIM if excluded else console.GREEN,
        bold=not excluded,
    )


def _set_auto_membership(provider_id: str, *, included: bool) -> None:
    excluded = set(configured_auto_exclusions())
    if included:
        excluded.discard(provider_id)
    else:
        excluded.add(provider_id)
    ordered = [
        registration.id
        for registration in provider_registrations()
        if registration.auto_eligible and registration.id in excluded
    ]
    if ordered:
        os.environ[AUTO_EXCLUDE_ENV] = ",".join(ordered)
    else:
        os.environ.pop(AUTO_EXCLUDE_ENV, None)


def _choose_provider(state: Any, console: Any) -> str | None:
    """Show execution readiness but keep every provider selectable for configuration."""
    console.render_header(state)
    capabilities = console.provider_capabilities(blocks=state.runtime_blocks)
    print("Provider de IA - disponibilidade indica aptidão para executar, não bloqueia configuração")
    print("Selecione qualquer provider para configurar/alterar/remover sua credencial.\n")
    for index, name in enumerate(console.PROVIDER_MENU_CHOICES, 1):
        capability = capabilities[name]
        status = _provider_status_badge(console, name, capability)
        reason = _provider_reason(console, name, capability)
        print(f" {index}. {name:<18} [{status}] {reason}")
    print("\n V. Voltar")
    while True:
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return None
        try:
            index = int(raw) - 1
            if index < 0:
                raise IndexError
            return console.PROVIDER_MENU_CHOICES[index]
        except (ValueError, IndexError):
            print(console.paint("Opção inválida.", console.RED, bold=True))


def _delete_provider_key(state: Any, console: Any, key_env: str, provider_id: str) -> None:
    """Remove current-session key and Windows/User persistence when available."""
    state.error = ""
    os.environ.pop(key_env, None)
    _refresh_provider_after_credential_change(state, key_env)
    user_value = console.user_environment_value(key_env)
    machine_value = console.machine_environment_value(key_env)
    if user_value is not None:
        if os.name == "nt":
            console.remove_user_environment(key_env)
        else:
            state.error = f"{key_env}: persistência User só pode ser removida automaticamente no Windows"
    console._sync_secret_volatility(state, key_env)
    if machine_value:
        state.error = (
            f"{key_env} removida da sessão/User, mas existe no escopo Windows/Machine; "
            "remova-a administrativamente para exclusão permanente"
        )


def _manage_provider(state: Any, console: Any, provider_id: str) -> str:
    """Manage one provider. Return use or back."""
    registration = get_provider_registration(provider_id)
    if registration is None:
        state.error = f"provider desconhecido: {provider_id}"
        return "back"
    key_env = registration.key_env

    while True:
        capabilities = console.provider_capabilities(blocks=state.runtime_blocks)
        capability = capabilities[registration.id]
        excluded = registration.id in set(configured_auto_exclusions())
        session_key = bool((os.environ.get(key_env) or "").strip())
        user_key = console.user_environment_value(key_env) is not None
        machine_key = console.machine_environment_value(key_env) is not None

        console.render_header(state)
        print(f"GERENCIAR IA - {registration.display_name}\n")
        print(f"Estado execução     : {_provider_status_badge(console, registration.id, capability)}")
        print(f"Motivo              : {_provider_reason(console, registration.id, capability)}")
        print(f"Credencial          : {key_env}")
        print(f"Sessão atual        : {_presence_badge(console, session_key, yes='[SET]', no='<não definida>')}")
        print(f"Windows / User      : {_presence_badge(console, user_key, yes='[PERSISTIDA]', no='<não persistida>')}")
        print(f"Windows / Machine   : {_presence_badge(console, machine_key, yes='[PERSISTIDA]', no='<não persistida>')}")
        if registration.auto_eligible:
            print(f"Pool AUTO           : {_auto_membership_badge(console, excluded)}")
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
            raw = console.getpass(f"{key_env}: ")
            try:
                os.environ[key_env] = console.validate_env_value(key_env, raw)
            except (ValueError, OverflowError) as exc:
                state.error = str(exc)
                continue
            _refresh_provider_after_credential_change(state, key_env)
            console._sync_secret_volatility(state, key_env)
            state.error = ""
            continue
        if action == "P":
            console._secret_persistence_action(state, key_env)
            _refresh_provider_after_credential_change(state, key_env)
            continue
        if action == "L":
            os.environ.pop(key_env, None)
            _refresh_provider_after_credential_change(state, key_env)
            console._sync_secret_volatility(state, key_env)
            state.error = ""
            continue
        if action == "X":
            _delete_provider_key(state, console, key_env, registration.id)
            continue
        if action == "A" and registration.auto_eligible:
            _set_auto_membership(registration.id, included=excluded)
            state.error = ""
            continue
        if action == "U":
            capability = console.provider_capabilities(blocks=state.runtime_blocks)[registration.id]
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


def _configure_auto_pool(state: Any, console: Any) -> bool:
    """Configure AUTO membership with the same status colors used by provider management."""
    excluded = set(configured_auto_exclusions())
    auto_registrations = tuple(registration for registration in provider_registrations() if registration.auto_eligible)
    while True:
        capabilities = console.provider_capabilities(blocks=state.runtime_blocks)
        console.render_header(state)
        print("POOL AI=AUTO - a chave continua configurada mesmo quando o provider é excluído do AUTO\n")
        for index, registration in enumerate(auto_registrations, 1):
            capability = capabilities[registration.id]
            status = _provider_status_badge(console, registration.id, capability)
            member = _auto_membership_badge(console, registration.id in excluded)
            reason = _provider_reason(console, registration.id, capability)
            print(f" {index}. {registration.display_name:<20} [{status}] [{member}] {reason}")
        print("\nDigite o número para alternar inclusão. A = incluir todas. V = concluir.")
        choice = input("Escolha: ").strip().upper()
        if choice == "A":
            excluded.clear()
            os.environ.pop(AUTO_EXCLUDE_ENV, None)
            continue
        if choice == "V":
            ready = [
                registration.id
                for registration in auto_registrations
                if registration.id not in excluded and capabilities[registration.id].available
            ]
            if not ready:
                state.error = "AI=AUTO exige ao menos um provider APTO incluído no pool"
                return False
            state.error = ""
            return True
        try:
            registration = auto_registrations[int(choice) - 1]
        except (ValueError, IndexError):
            state.error = "opção inválida para pool AUTO"
            continue
        included = registration.id in excluded
        _set_auto_membership(registration.id, included=included)
        excluded = set(configured_auto_exclusions())


def _configure_model_reasoning_timeout(state: Any, console: Any, provider_id: str) -> None:
    provider_name = console.PROVIDERS[provider_id]
    default = os.environ.get(console.MODEL_ENV[provider_name], console.DEFAULT_MODELS[provider_name])
    chosen = console._select(
        state,
        f"Modelo {provider_name} - o default público privilegia menor custo/complexidade",
        [
            (model, True, "default" if model == default else "suportado")
            for model in console.SUPPORTED_MODELS[provider_name]
        ],
    )
    state.ai_model = chosen or default
    effort_default = configured_reasoning(provider_name)
    efforts = REASONING_OPTIONS[provider_name]
    if len(efforts) == 1:
        state.ai_reasoning = efforts[0]
    else:
        effort = console._select(
            state,
            f"Esforço/profundidade {provider_name} - menor nível reduz latência/tokens",
            [
                (item, True, "default mínimo" if item == effort_default else "suportado")
                for item in efforts
            ],
        )
        state.ai_reasoning = effort or effort_default
        apply_console_reasoning_environment(provider_name, state.ai_reasoning)
    state.ai_timeout = float(
        console._number(
            "Timeout por tentativa de IA",
            state.ai_timeout,
            minimum=1,
            help_text="limite de espera de cada chamada ao provider. Não é o tempo máximo da auditoria inteira.",
        )
    )
    os.environ[AI_TIMEOUT_ENV] = f"{state.ai_timeout:g}"
    state.error = ""


def _configure_ai(state: Any, console: Any) -> None:
    selection = _choose_provider(state, console)
    if selection is None:
        return
    if selection == "none":
        state.ai_provider = "none"
        state.ai_model = None
        state.ai_reasoning = None
        state.content_remediation = False
        state.technical_remediation = False
        state.error = ""
        return
    if selection == "auto":
        if _configure_auto_pool(state, console):
            state.ai_provider = "auto"
            state.ai_model = None
            state.ai_reasoning = None
            state.ai_timeout = float(
                console._number(
                    "Timeout por tentativa de IA",
                    state.ai_timeout,
                    minimum=1,
                    help_text="limite de espera de cada chamada ao provider. Não é o tempo máximo da auditoria inteira.",
                )
            )
            os.environ[AI_TIMEOUT_ENV] = f"{state.ai_timeout:g}"
        return

    outcome = _manage_provider(state, console, selection)
    if outcome != "use":
        return
    _configure_model_reasoning_timeout(state, console, selection)


def _install_persistence_refresh() -> None:
    """Make both credential UIs invalidate stale provider blocks after persistence."""
    from rasai import console_environment, interactive_console

    original_grouped = console_environment._persist_secret
    if not getattr(original_grouped, "_rasai_provider_refresh", False):
        def persist_secret(state: Any, spec: Any) -> None:
            original_grouped(state, spec)
            _refresh_provider_after_credential_change(state, spec.name)
            console_environment._apply_change(state, spec.name)

        persist_secret._rasai_provider_refresh = True
        persist_secret._rasai_original = original_grouped
        console_environment._persist_secret = persist_secret

    original_simple = interactive_console._secret_persistence_action
    if not getattr(original_simple, "_rasai_provider_refresh", False):
        def persist_simple(state: Any, name: str) -> None:
            original_simple(state, name)
            _refresh_provider_after_credential_change(state, name)

        persist_simple._rasai_provider_refresh = True
        persist_simple._rasai_original = original_simple
        interactive_console._secret_persistence_action = persist_simple


def install() -> None:
    """Install provider management after the existing console adapters compose."""
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import interactive_console

    _install_persistence_refresh()
    original = interactive_console._configure
    if getattr(original, "_rasai_provider_management", False):
        _INSTALLED = True
        return

    def configure(state: Any, choice: str) -> None:
        if choice != "4":
            return original(state, choice)
        return _configure_ai(state, interactive_console)

    configure._rasai_provider_management = True
    configure._rasai_original = original
    interactive_console._configure = configure
    _INSTALLED = True
