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
        if name == "none":
            status = "SEM IA"
        elif capability.available:
            status = "APTO"
        else:
            status = "CONFIGURAR"
        print(f" {index}. {name:<18} [{status}] {capability.reason}")
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
    """Remove the current-session key and Windows/User persistence when available."""
    os.environ.pop(key_env, None)
    state.runtime_blocks.pop(provider_id, None)
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
    elif not state.error:
        state.error = ""


def _manage_provider(state: Any, console: Any, provider_id: str) -> str:
    """Manage one provider. Return use, disabled or back."""
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
        print(f"Estado execução     : {'APTO' if capability.available else 'INDISPONÍVEL'}")
        print(f"Motivo              : {capability.reason}")
        print(f"Credencial          : {key_env}")
        print(f"Sessão atual        : {'[SET]' if session_key else '<não definida>'}")
        print(f"Windows / User      : {'[PERSISTIDA]' if user_key else '<não persistida>'}")
        print(f"Windows / Machine   : {'[PERSISTIDA]' if machine_key else '<não persistida>'}")
        if registration.auto_eligible:
            print(f"Pool AUTO           : {'EXCLUÍDO' if excluded else 'INCLUÍDO'}")
        print("\nS. Setar/alterar Key na sessão")
        print("P. Persistir/remover Key no Windows/User")
        print("L. Limpar Key somente da sessão")
        print("X. Excluir Key da sessão e do Windows/User")
        if registration.auto_eligible:
            print("A. Incluir/excluir do AUTO sem apagar a Key")
        print("U. Usar este provider nesta auditoria")
        print("D. Desabilitar IA nesta auditoria sem apagar a Key")
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
            state.runtime_blocks.pop(registration.id, None)
            console._sync_secret_volatility(state, key_env)
            state.error = ""
            continue
        if action == "P":
            console._secret_persistence_action(state, key_env)
            continue
        if action == "L":
            os.environ.pop(key_env, None)
            state.runtime_blocks.pop(registration.id, None)
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
        if action == "D":
            state.ai_provider = "none"
            state.ai_model = None
            state.ai_reasoning = None
            state.content_remediation = False
            state.technical_remediation = False
            state.error = ""
            return "disabled"
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
        # Reuse the canonical AUTO-pool editor. Unlike concrete providers, AUTO has no
        # credential of its own; credentials are managed on each concrete provider.
        from rasai.documented_contract_reconciliation import _configure_auto_pool

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


def install() -> None:
    """Install the provider manager after the existing console adapters compose."""
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import interactive_console

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
