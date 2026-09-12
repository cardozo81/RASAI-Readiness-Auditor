"""Interactive-console integration for one-URL Improvement Intelligence.

The console persists only non-secret choices in rasai-console.ini. The analysis provider
reuses an already configured credential and runs after the normal audit/Search extension,
so SERP evidence from the same session can participate without duplicating paid calls.
"""
from __future__ import annotations

from dataclasses import dataclass
import builtins
import os
from pathlib import Path
from types import ModuleType
from typing import Any

from rasai.console_artifacts import audit_workspace
from rasai.improvement_intelligence import (
    AI_ANALYSIS_LANGUAGE_ENV,
    DEFAULT_DOMAINS,
    DOMAIN_LABELS,
    ENABLED_ENV,
    ImprovementConfig,
    execute_improvement_intelligence,
    parse_domains,
    validate_analysis_language,
)
from rasai.provider_registry import get_provider_registration, provider_registrations

_INSTALLED_ENV = False
_INSTALLED_CONSOLE = False


def install_environment() -> None:
    """Expose the global AI reading/response language in the existing environment UI."""
    global _INSTALLED_ENV
    if _INSTALLED_ENV:
        return
    from rasai import console_environment as base

    spec = base.EnvironmentSpec(
        AI_ANALYSIS_LANGUAGE_ENV,
        "IA - contexto editorial / YMYL",
        (
            "Idioma preferencial para leitura/explicação e textos sugeridos pela IA. "
            "auto usa o idioma da auditoria; não substitui a detecção real do idioma da página."
        ),
        "tag BCP-47 ou auto",
        default="auto",
        impact="Sem custo externo direto; orienta apenas o idioma das respostas/sugestões.",
        example=f"{AI_ANALYSIS_LANGUAGE_ENV}=pt-BR",
        source="docs/IMPROVEMENT_INTELLIGENCE.md",
    )
    if AI_ANALYSIS_LANGUAGE_ENV not in base.ENV_NAMES:
        base.ENV_NAMES = tuple(dict.fromkeys((*base.ENV_NAMES, AI_ANALYSIS_LANGUAGE_ENV)))
    by_name = {item.name: item for item in base.SPECS}
    by_name[AI_ANALYSIS_LANGUAGE_ENV] = spec
    base.SPECS = tuple(by_name[name] for name in base.ENV_NAMES if name in by_name)
    base.SPEC_BY_NAME = {item.name: item for item in base.SPECS}
    original_validate = base._validate

    def validate(name: str, raw: str) -> str:
        if name == AI_ANALYSIS_LANGUAGE_ENV:
            return validate_analysis_language(raw)
        return original_validate(name, raw)

    base._validate = validate

    # The provider-aware environment surface is the one wired into the public console.
    try:
        from rasai import console_provider_environment as provider_env
        if AI_ANALYSIS_LANGUAGE_ENV not in provider_env.ENV_NAMES:
            provider_env.ENV_NAMES = tuple(dict.fromkeys((*provider_env.ENV_NAMES, AI_ANALYSIS_LANGUAGE_ENV)))
        p_by_name = {item.name: item for item in provider_env.SPECS}
        p_by_name[AI_ANALYSIS_LANGUAGE_ENV] = spec
        provider_env.SPECS = tuple(p_by_name[name] for name in provider_env.ENV_NAMES if name in p_by_name)
        provider_env.SPEC_BY_NAME = {item.name: item for item in provider_env.SPECS}
        provider_validate = provider_env._validate

        def validate_provider(name: str, raw: str) -> str:
            if name == AI_ANALYSIS_LANGUAGE_ENV:
                return validate_analysis_language(raw)
            return provider_validate(name, raw)

        provider_env._validate = validate_provider
    except Exception:
        pass

    _INSTALLED_ENV = True


def _install_settings(console_module: ModuleType) -> None:
    from rasai import console_settings as settings

    if getattr(settings, "_rasai_improvement_intelligence_settings", False):
        return
    original_values = settings._state_values
    original_assign = settings._assign

    def state_values(state: Any) -> dict[str, dict[str, str]]:
        values = dict(original_values(state))
        values["improvement_intelligence"] = {
            "enabled": "true" if bool(getattr(state, "improvement_enabled", False)) else "false",
            "provider": str(getattr(state, "improvement_provider", "")),
            "model": str(getattr(state, "improvement_model", "")),
            "reasoning_effort": str(getattr(state, "improvement_reasoning", "")),
            "domains": ",".join(getattr(state, "improvement_domains", DEFAULT_DOMAINS)),
            "max_recommendations": str(int(getattr(state, "improvement_max_recommendations", 30))),
            "timeout_seconds": f"{float(getattr(state, 'improvement_timeout', 240.0)):g}",
        }
        return values

    def assign(state: Any, section: str, option: str, raw: str) -> None:
        if section != "improvement_intelligence":
            original_assign(state, section, option, raw)
            return
        if option == "enabled":
            state.improvement_enabled = settings._parse_bool(raw)
        elif option == "provider":
            state.improvement_provider = raw.strip().casefold()
        elif option == "model":
            state.improvement_model = raw.strip()
        elif option == "reasoning_effort":
            state.improvement_reasoning = raw.strip().upper()
        elif option == "domains":
            state.improvement_domains = parse_domains(raw)
        elif option == "max_recommendations":
            value = int(raw)
            if value < 1 or value > 100:
                raise ValueError("use inteiro entre 1 e 100")
            state.improvement_max_recommendations = value
        elif option == "timeout_seconds":
            value = float(raw)
            if value <= 0:
                raise ValueError("use número > 0")
            state.improvement_timeout = value

    settings._state_values = state_values
    settings._assign = assign
    settings._rasai_improvement_intelligence_settings = True


def _config_from_state(state: Any) -> ImprovementConfig:
    return ImprovementConfig(
        enabled=bool(getattr(state, "improvement_enabled", False)),
        provider=str(getattr(state, "improvement_provider", "")),
        model=str(getattr(state, "improvement_model", "")),
        reasoning=str(getattr(state, "improvement_reasoning", "")),
        domains=tuple(getattr(state, "improvement_domains", DEFAULT_DOMAINS)),
        max_recommendations=int(getattr(state, "improvement_max_recommendations", 30)),
        timeout_seconds=float(getattr(state, "improvement_timeout", 240.0)),
        language=(os.environ.get(AI_ANALYSIS_LANGUAGE_ENV) or "auto"),
    ).validate()


def _single_url_ready(state: Any) -> tuple[bool, str]:
    if not bool(getattr(state, "improvement_enabled", False)):
        return True, "análise profunda desabilitada"
    if str(getattr(state, "input_mode", "url")) != "url":
        return False, "Análise profunda exige Entrada=URL única; arquivo TXT/múltiplas URLs não é permitido"
    if not str(getattr(state, "target", "")).strip():
        return False, "Análise profunda exige uma URL explícita"
    provider = str(getattr(state, "improvement_provider", "")).casefold()
    if provider in {"", "none", "auto"}:
        return False, "Análise profunda exige uma IA explícita independente da IA padrão"
    capabilities = console_module_provider_capabilities(state)
    capability = capabilities.get(provider)
    if capability is None or not capability.available:
        reason = capability.reason if capability is not None else "provider desconhecido"
        return False, f"IA da análise profunda indisponível: {reason}"
    try:
        _config_from_state(state)
    except ValueError as exc:
        return False, str(exc)
    return True, "análise profunda pronta para URL única"


def console_module_provider_capabilities(state: Any):
    from rasai.console_config import provider_capabilities
    return provider_capabilities(blocks=getattr(state, "runtime_blocks", {}))


def _select_provider(console_module: ModuleType, state: Any) -> str | None:
    capabilities = console_module.provider_capabilities(blocks=state.runtime_blocks)
    options = []
    for registration in provider_registrations():
        capability = capabilities.get(registration.id)
        available = bool(capability and capability.available)
        reason = capability.reason if capability is not None else "indisponível"
        options.append((registration.id, available, reason))
    return console_module._select(
        state,
        "IA exclusiva da análise profunda - reutiliza a key/token já configurada",
        options,
    )


def configure(console_module: ModuleType, state: Any) -> None:
    console_module.render_header(state)
    print("ANÁLISE PROFUNDA E MELHORIAS\n")
    print("Executa uma análise evidence-bound após a auditoria e, quando configurado, após a coleta SERP da mesma sessão.")
    print("Obrigatório: uma única URL de entrada. O crawl pode coletar páginas auxiliares, mas a análise profunda permanece vinculada à URL explícita.")
    print("Segurança é somente passiva; não há exploração/pentest. A IA não altera SARI/SCORE-GEO e não promete posição de ranking.")
    print("A configuração abaixo é independente da IA padrão e pode usar modelo/esforço mais profundo, reutilizando a mesma credencial do provider.\n")
    current = bool(getattr(state, "improvement_enabled", False))
    raw = input(f"Habilitar análise profunda? [{'S/n' if current else 's/N'}]: ").strip().casefold()
    enabled = current if not raw else raw in {"s", "sim", "y", "yes", "1", "true", "on"}
    if not enabled:
        state.improvement_enabled = False
        state.error = ""
        return
    if state.input_mode != "url":
        state.error = "Análise profunda só pode ser habilitada com Entrada=URL única"
        return
    provider = _select_provider(console_module, state)
    if not provider:
        return
    registration = get_provider_registration(provider)
    assert registration is not None
    state.improvement_provider = provider
    current_model = state.improvement_model if state.improvement_model in registration.supported_models else registration.public_default_model
    chosen_model = console_module._select(
        state,
        f"Modelo {registration.display_name} para análise profunda",
        [(item, True, "atual" if item == current_model else "suportado") for item in registration.supported_models],
    )
    state.improvement_model = chosen_model or current_model
    efforts = registration.reasoning_values
    current_effort = state.improvement_reasoning if state.improvement_reasoning in efforts else efforts[-1]
    if len(efforts) == 1:
        state.improvement_reasoning = efforts[0]
    else:
        effort = console_module._select(
            state,
            f"Esforço/profundidade {registration.display_name} para esta análise",
            [(item, True, "atual" if item == current_effort else "suportado") for item in efforts],
        )
        state.improvement_reasoning = effort or current_effort

    print("\nDomínios disponíveis:")
    for index, domain in enumerate(DEFAULT_DOMAINS, 1):
        marker = "*" if domain in set(getattr(state, "improvement_domains", DEFAULT_DOMAINS)) else " "
        print(f" {index:2d}. [{marker}] {DOMAIN_LABELS[domain]} ({domain})")
    raw_domains = input("Selecione números separados por vírgula [ENTER=manter atuais; 'todos'=todos]: ").strip().casefold()
    if raw_domains:
        if raw_domains in {"todos", "all", "*"}:
            state.improvement_domains = DEFAULT_DOMAINS
        else:
            selected: list[str] = []
            for token in raw_domains.replace(";", ",").split(","):
                index = int(token.strip())
                if index < 1 or index > len(DEFAULT_DOMAINS):
                    raise ValueError("domínio fora da lista")
                selected.append(DEFAULT_DOMAINS[index - 1])
            state.improvement_domains = tuple(dict.fromkeys(selected))
            parse_domains(state.improvement_domains)

    maximum = input(f"Máximo de recomendações [{state.improvement_max_recommendations}]: ").strip()
    if maximum:
        value = int(maximum)
        if value < 1 or value > 100:
            raise ValueError("máximo de recomendações deve estar entre 1 e 100")
        state.improvement_max_recommendations = value
    timeout = input(f"Timeout da chamada profunda em segundos [{state.improvement_timeout:g}]: ").strip()
    if timeout:
        value = float(timeout)
        if value <= 0:
            raise ValueError("timeout deve ser > 0")
        state.improvement_timeout = value
    state.improvement_enabled = True
    _config_from_state(state)
    state.error = ""


def _render_menu_extension(console_module: ModuleType, state: Any) -> None:
    from rasai.console_ui import DIM, GREEN, RED, paint
    enabled = bool(getattr(state, "improvement_enabled", False))
    provider = str(getattr(state, "improvement_provider", "")) or "-"
    model = str(getattr(state, "improvement_model", "")) or "-"
    reasoning = str(getattr(state, "improvement_reasoning", "")) or "-"
    domains = len(tuple(getattr(state, "improvement_domains", DEFAULT_DOMAINS)))
    ready, reason = _single_url_ready(state)
    if enabled:
        state_text = paint("ON", GREEN if ready else RED, bold=True)
        detail = (
            f"provider={provider} | modelo={model} | esforço={reasoning} | domínios={domains} | "
            f"idioma IA={os.environ.get(AI_ANALYSIS_LANGUAGE_ENV, 'auto')} | até 2 tentativas estruturadas"
        )
        if not ready:
            detail += " | " + paint(reason, RED, bold=True)
    else:
        state_text = paint("OFF", DIM)
        detail = "somente URL única; chamada IA adicional; segurança passiva; advisory/non-scoring"
    print(f"13. Análise profunda URL  : {state_text} | {detail}")


def _install_progress_projection() -> None:
    from rasai import console_runtime
    if getattr(console_runtime, "_rasai_improvement_progress_projection", False):
        return
    original = console_runtime._synthetic_progress_projection

    def projection(state: Any, label: str, percent: float | None):
        bounded = console_runtime._bounded_percent(percent)
        if state.status.upper() == "IMPROVEMENT_INTELLIGENCE" and bounded is not None:
            # Deep analysis is an optional terminal enrichment after audit/Search.
            return bounded, 94.0 + (bounded / 100.0) * 5.0
        return original(state, label, percent)

    console_runtime._synthetic_progress_projection = projection
    console_runtime._PHASE_PROGRESS["IMPROVEMENT_INTELLIGENCE"] = ("Análise profunda e melhorias", 94.0)
    console_runtime._rasai_improvement_progress_projection = True


def install(console_module: ModuleType) -> None:
    global _INSTALLED_CONSOLE
    if _INSTALLED_CONSOLE or getattr(console_module, "_improvement_intelligence_console_installed", False):
        return
    install_environment()
    _install_progress_projection()

    base_state = console_module.State
    if "improvement_enabled" not in getattr(base_state, "__dataclass_fields__", {}):
        @dataclass(slots=True)
        class ImprovementConsoleState(base_state):
            improvement_enabled: bool = False
            improvement_provider: str = ""
            improvement_model: str = ""
            improvement_reasoning: str = ""
            improvement_domains: tuple[str, ...] = DEFAULT_DOMAINS
            improvement_max_recommendations: int = 30
            improvement_timeout: float = 240.0
            improvement_last_status: str = "NOT_REQUESTED"
            improvement_last_detail: str = ""
            improvement_last_report: str = ""

        console_module.State = ImprovementConsoleState

    _install_settings(console_module)
    original_menu = console_module._menu
    original_configure = console_module._configure
    original_readiness = console_module._execution_readiness
    original_run = console_module.run_audit_from_console

    def menu(state: Any) -> str:
        original_input = builtins.input
        printed = False

        def intercepted(prompt: str = "") -> str:
            nonlocal printed
            if prompt.strip().casefold().startswith("escolha") and not printed:
                _render_menu_extension(console_module, state)
                printed = True
            return original_input(prompt)

        builtins.input = intercepted
        try:
            return original_menu(state)
        finally:
            builtins.input = original_input

    def configure_state(state: Any, choice: str) -> None:
        if choice != "13":
            original_configure(state, choice)
            return
        try:
            configure(console_module, state)
        except (TypeError, ValueError, OverflowError) as exc:
            state.error = f"Análise profunda: {exc}"

    def readiness(state: Any) -> tuple[bool, str]:
        ready, reason = original_readiness(state)
        if not ready:
            return ready, reason
        return _single_url_ready(state)

    def run(state: Any) -> int:
        # The interactive console owns this feature through item 13. Temporarily force
        # the env-driven CLI/SaaS wrapper OFF while the base audit runs so an advanced
        # environment override cannot execute the deep analysis invisibly or twice.
        previous_runtime_toggle = os.environ.get(ENABLED_ENV)
        os.environ[ENABLED_ENV] = "false"
        try:
            code = int(original_run(state) or 0)
        finally:
            if previous_runtime_toggle is None:
                os.environ.pop(ENABLED_ENV, None)
            else:
                os.environ[ENABLED_ENV] = previous_runtime_toggle

        if code != 0 or not bool(getattr(state, "improvement_enabled", False)):
            return code
        workspace_path = audit_workspace(state)
        if workspace_path is None:
            state.improvement_last_status = "UNAVAILABLE"
            state.improvement_last_detail = "workspace AUD da sessão não encontrado"
            return code

        from rasai import console_runtime
        from rasai.persistence import AuditWorkspace
        from rasai.report_completion import finalize_audit_report_site

        timing = console_runtime._RUN_TIMINGS.get(id(state))
        if timing is not None:
            # Base audit/Search may have marked the clock complete; reopen the same
            # timing interval so final duration includes this terminal enrichment.
            timing.finished_at = None
            timing.duration_seconds = None

        workspace = AuditWorkspace.open(workspace_path)
        config = _config_from_state(state)
        state.status = "IMPROVEMENT_INTELLIGENCE"
        state.operation = f"API:{config.provider.upper()}/{config.model}"

        def progress(stage: str, percent: float, detail: str) -> None:
            state.status = "IMPROVEMENT_INTELLIGENCE"
            state.operation = f"API:{config.provider.upper()}/{config.model}"
            console_runtime.set_runtime_progress(
                state,
                "Análise profunda e melhorias",
                percent,
                detail=f"{stage}: {detail}",
                exact=True,
            )
            console_module.render_header(state)
            if state.audit_id:
                print(f"Audit ID    : {state.audit_id}")
            print(f"Log técnico: {Path(workspace.root) / 'logs' / 'audit.log'}")

        try:
            result = execute_improvement_intelligence(
                audit_id=state.audit_id,
                workspace=workspace,
                config=config,
                progress=progress,
            )
            # Rebuild read-only projections so ai-usage.html includes this request and
            # the canonical mini-site receives the analyzed Improvement Intelligence page.
            # Keep the env-driven wrapper disabled during this rebuild: item 13 already
            # performed the analysis and must remain the single authority in the console.
            previous_runtime_toggle = os.environ.get(ENABLED_ENV)
            os.environ[ENABLED_ENV] = "false"
            try:
                finalize_audit_report_site(audit_id=state.audit_id, workspace=workspace)
            finally:
                if previous_runtime_toggle is None:
                    os.environ.pop(ENABLED_ENV, None)
                else:
                    os.environ[ENABLED_ENV] = previous_runtime_toggle
            report = Path(workspace.root) / "report" / "improvement-intelligence.html"
            state.improvement_last_report = str(report) if report.is_file() else ""
            state.improvement_last_status = result.status
            state.improvement_last_detail = (
                f"{result.findings_count} finding(s); {result.recommendations_count} recomendação(ões); "
                f"provider={result.provider}/{result.model}; reused={result.reused}"
            )
            final_status = "COMPLETE_WITH_LIMITATIONS" if result.status == "COMPLETE_WITH_LIMITATIONS" else "COMPLETE"
            state.status = final_status
            state.operation = "LOCAL:DONE"
            state.current_url = result.target_url or state.current_url
            console_runtime.set_runtime_progress(
                state,
                "Concluído com limitações" if final_status == "COMPLETE_WITH_LIMITATIONS" else "Concluído",
                100.0,
                detail=state.improvement_last_detail + (f"; {result.reason}" if result.reason else ""),
                exact=True,
            )
        except Exception as exc:
            state.improvement_last_status = "COMPLETE_WITH_LIMITATIONS"
            state.improvement_last_detail = f"{type(exc).__name__}: {str(exc)[:400]}"
            state.status = "COMPLETE_WITH_LIMITATIONS"
            state.operation = "LOCAL:IMPROVEMENT_FAIL_OPEN"
            state.error = "Análise profunda incompleta; auditoria principal preservada: " + state.improvement_last_detail
            try:
                previous_runtime_toggle = os.environ.get(ENABLED_ENV)
                os.environ[ENABLED_ENV] = "false"
                try:
                    finalize_audit_report_site(audit_id=state.audit_id, workspace=workspace)
                finally:
                    if previous_runtime_toggle is None:
                        os.environ.pop(ENABLED_ENV, None)
                    else:
                        os.environ[ENABLED_ENV] = previous_runtime_toggle
            except Exception:
                pass
            console_runtime.set_runtime_progress(
                state,
                "Concluído com limitações",
                100.0,
                detail="auditoria principal preservada; análise profunda falhou e foi registrada como limitação",
                exact=True,
            )
        finally:
            console_runtime._finish_timing(state)
        console_module.render_header(state)
        return code

    console_module._menu = menu
    console_module._configure = configure_state
    console_module._execution_readiness = readiness
    console_module.run_audit_from_console = run
    console_module._improvement_intelligence_console_installed = True
    _INSTALLED_CONSOLE = True
