"""Versioned system-default profile and restore flow for the local interactive console.

The packaged ``config/rasai-defaults.ini`` is a product policy layer, not a secret store.
Normal precedence remains: explicit process/OS environment > user ``rasai-console.ini`` >
system defaults > defensive code fallback. Restoring defaults deliberately removes known
non-secret overrides from the current session and Windows/User so the restored INI can
actually become effective; Windows/Machine is never modified.
"""
from __future__ import annotations

import builtins
from configparser import ConfigParser
from dataclasses import dataclass, replace
from importlib.resources import files
import math
import os
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from rasai.console_config import is_secret
from rasai.console_session import mark_dirty, set_config_path
from rasai.windows_environment import (
    machine_environment_value,
    remove_user_environment,
    user_environment_value,
)

SYSTEM_DEFAULTS_RESOURCE = "config/rasai-defaults.ini"
SYSTEM_DEFAULTS_VERSION = "1"
BOOTSTRAP_ENV_NAMES = frozenset({"RASAI_CONSOLE_INI", "RASAI_CONFIG"})
REPRESENTATIVE_APDEX_SAMPLES = 100
LOW_LOAD_NAVIGATION_SAMPLES = 1
LOW_LOAD_EXPERIENCE_SAMPLES = 20
DYNATRACE_COMPAT_THRESHOLD_SECONDS = 3.0


@dataclass(frozen=True, slots=True)
class RestoreDefaultsResult:
    nonsecret_session_removed: int
    nonsecret_user_removed: int
    credentials_session_removed: int
    credentials_user_removed: int
    machine_preserved: tuple[str, ...]
    warnings: tuple[str, ...]
    path: Path


def load_system_defaults() -> ConfigParser:
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    resource = files("rasai").joinpath("config").joinpath("rasai-defaults.ini")
    with resource.open("r", encoding="utf-8") as stream:
        parser.read_file(stream)
    version = parser.get("metadata", "system_defaults_version", fallback="").strip()
    if version != SYSTEM_DEFAULTS_VERSION:
        raise ValueError(
            f"rasai-defaults.ini incompatível: esperado version={SYSTEM_DEFAULTS_VERSION}, recebido={version or '<vazio>'}"
        )
    return parser


def _system_environment_defaults() -> dict[str, str]:
    parser = load_system_defaults()
    if not parser.has_section("environment"):
        return {}
    return {
        name: raw.strip()
        for name, raw in parser.items("environment", raw=True)
        if raw.strip()
    }


def _read_user_environment(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        with path.open("r", encoding="utf-8") as stream:
            parser.read_file(stream)
    except (OSError, UnicodeError):
        return {}
    if not parser.has_section("environment"):
        return {}
    return {
        name: raw.strip()
        for name, raw in parser.items("environment", raw=True)
        if raw.strip()
    }


def apply_structured_defaults(state: Any, *, include_presentation: bool = True) -> tuple[str, ...]:
    """Apply packaged non-secret structured defaults to an existing console state."""
    from rasai import console_settings as settings

    parser = load_system_defaults()
    known_sections = set(settings._state_values(state))
    warnings: list[str] = []
    for section in parser.sections():
        if section in {"metadata", "environment"} or section not in known_sections:
            continue
        if section == "presentation" and not include_presentation:
            continue
        for option, raw in parser.items(section, raw=True):
            if option == "config_version":
                continue
            try:
                settings._assign(state, section, option, raw)
            except (TypeError, ValueError, OverflowError) as exc:
                warnings.append(f"system-default {section}.{option}: {exc}")
    return tuple(warnings)


def _apply_system_environment_defaults(
    *,
    external: Mapping[str, str] | None = None,
    user_ini: Mapping[str, str] | None = None,
    force: bool = False,
) -> tuple[str, ...]:
    """Materialize advanced defaults without outranking user/OS overrides."""
    external_values = external or {}
    user_values = user_ini or {}
    warnings: list[str] = []
    for name, value in _system_environment_defaults().items():
        if name in BOOTSTRAP_ENV_NAMES:
            continue
        if is_secret(name):
            warnings.append(f"system-default rejeitado por segurança: {name}")
            continue
        if not force and (name in external_values or name in user_values):
            continue
        if force or not (os.environ.get(name) or "").strip():
            os.environ[name] = value
    return tuple(warnings)


def _restore_explicit_environment(values: Mapping[str, str]) -> None:
    """Restore process/OS overrides after writers project structured state to os.environ."""
    for name, value in values.items():
        os.environ[name] = value


def load_console_config_with_system_defaults(state: Any, path: Path | None = None):
    """Load system baseline first, then the existing user-INI/environment contract."""
    from rasai import console_settings as settings

    source = path or settings.resolve_config_path()
    external = {
        name: str(value)
        for name, value in os.environ.items()
        if str(value).strip()
    }
    user_ini = _read_user_environment(source)

    warnings = list(apply_structured_defaults(state, include_presentation=False))
    result = settings.load_console_config(state, source)
    warnings.extend(result.warnings)
    _restore_explicit_environment(external)
    warnings.extend(
        _apply_system_environment_defaults(
            external=external,
            user_ini=user_ini,
            force=False,
        )
    )

    if result.created:
        try:
            settings.save_console_config(state, result.path)
        except (OSError, UnicodeError, ValueError) as exc:
            warnings.append(f"system-default save: {type(exc).__name__}: {exc}")
        finally:
            _restore_explicit_environment(external)

    return settings.ConfigLoadResult(result.path, result.created, tuple(dict.fromkeys(warnings)))


def _sensitive(spec: Any) -> bool:
    return bool(getattr(spec, "sensitive", False)) or is_secret(str(spec.name))


def restore_program_defaults(
    state: Any,
    *,
    clear_credentials: bool,
    path: Path | None = None,
) -> RestoreDefaultsResult:
    """Restore canonical defaults and persist them through the normal INI writer."""
    from rasai import console_provider_environment as facade
    from rasai import console_settings as settings

    facade.refresh_specs()
    destination = path or settings.resolve_config_path()
    nonsecret_session_removed = 0
    nonsecret_user_removed = 0
    credentials_session_removed = 0
    credentials_user_removed = 0
    machine: list[str] = []
    warnings: list[str] = []

    unique = {spec.name: spec for spec in facade.SPECS}
    for name, spec in unique.items():
        if name in BOOTSTRAP_ENV_NAMES:
            continue
        sensitive = _sensitive(spec)
        machine_value = machine_environment_value(name)
        if machine_value is not None:
            machine.append(name)

        if sensitive:
            if not clear_credentials:
                continue
            if name in os.environ:
                os.environ.pop(name, None)
                credentials_session_removed += 1
            if os.name == "nt" and user_environment_value(name) is not None:
                try:
                    if remove_user_environment(name):
                        credentials_user_removed += 1
                except (OSError, ValueError) as exc:
                    warnings.append(f"{name}: {type(exc).__name__}: {exc}")
            continue

        if name in os.environ:
            os.environ.pop(name, None)
            nonsecret_session_removed += 1
        if os.name == "nt" and user_environment_value(name) is not None:
            try:
                if remove_user_environment(name):
                    nonsecret_user_removed += 1
            except (OSError, ValueError) as exc:
                warnings.append(f"{name}: {type(exc).__name__}: {exc}")

    warnings.extend(apply_structured_defaults(state, include_presentation=True))
    warnings.extend(_apply_system_environment_defaults(force=True))

    try:
        saved = settings.save_console_config(state, destination)
    except (OSError, UnicodeError, ValueError) as exc:
        warnings.append(f"rasai-console.ini: {type(exc).__name__}: {exc}")
        saved = destination

    set_config_path(state, saved)
    mark_dirty(state, False)
    facade.refresh_specs()
    state.operation = "LOCAL:RESTORE_SYSTEM_DEFAULTS"
    state.error = "; ".join(tuple(dict.fromkeys(warnings)))
    return RestoreDefaultsResult(
        nonsecret_session_removed,
        nonsecret_user_removed,
        credentials_session_removed,
        credentials_user_removed,
        tuple(sorted(set(machine))),
        tuple(dict.fromkeys(warnings)),
        saved,
    )


def _restore_menu(console_module: ModuleType, state: Any) -> None:
    console_module.render_header(state)
    print("RESTAURAR PADRÕES DO RASAi\n")
    print("A configuração será reconstruída a partir do rasai-defaults.ini desta versão e salva no rasai-console.ini.")
    print("Overrides não secretos conhecidos serão limpos da sessão e, no Windows, de Windows/User.")
    print("Windows/Machine nunca é alterado automaticamente.\n")
    print("1. Restaurar padrões e PRESERVAR credenciais")
    if os.name == "nt":
        print("2. Restaurar padrões e REMOVER todas as credenciais gerenciadas de sessão + Windows/User")
    else:
        print("2. Restaurar padrões e REMOVER credenciais da sessão (persistência de SO gerenciada é exclusiva do Windows)")
    print("V. Voltar sem alterar")
    action = input("Escolha: ").strip().upper()
    if action == "V":
        state.operation = "LOCAL:RESTORE_SYSTEM_DEFAULTS_CANCELLED"
        state.error = ""
        return
    if action not in {"1", "2"}:
        state.error = "opção de restauração inválida"
        return

    clear_credentials = action == "2"
    print()
    print("Credenciais: " + ("REMOVER" if clear_credentials else "PRESERVAR"))
    print("Auditorias, relatórios, audit.db, banco do control plane e arquivos de projeto não serão apagados.")
    if input("Para confirmar, digite RESTAURAR: ").strip().upper() != "RESTAURAR":
        state.operation = "LOCAL:RESTORE_SYSTEM_DEFAULTS_CANCELLED"
        state.error = ""
        return

    result = restore_program_defaults(state, clear_credentials=clear_credentials)
    console_module.render_header(state)
    print("PADRÕES RESTAURADOS\n")
    print(f"INI reconstruído          : {result.path}")
    print(f"Overrides sessão removidos: {result.nonsecret_session_removed}")
    if os.name == "nt":
        print(f"Overrides Windows/User    : {result.nonsecret_user_removed}")
        if clear_credentials:
            print(f"Credenciais Windows/User  : {result.credentials_user_removed}")
    if result.machine_preserved:
        print(
            f"ATENÇÃO: {len(result.machine_preserved)} override(s) Windows/Machine permanecem e podem voltar a prevalecer em um novo processo."
        )
        for name in result.machine_preserved:
            print(f"- {name}")
    if result.warnings:
        print("\nRestauração concluída com ressalvas:")
        for warning in result.warnings:
            print(f"- {warning}")
    input("\nENTER para continuar...")


def _patch_environment_catalog() -> None:
    from rasai import console_provider_environment as facade

    if getattr(facade, "_rasai_system_default_catalog", False):
        return
    original_refresh = facade.refresh_specs

    explicit = {
        "RASAI_SYNTHETIC_APDEX": "true",
        "RASAI_APDEX_THRESHOLD_SECONDS": "3",
        "RASAI_APDEX_SAMPLES_PER_CONTEXT": "1",
        "RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT": "2",
        "RASAI_APDEX_EXPERIENCE": "true",
        "RASAI_APDEX_EXPERIENCE_SAMPLES": "20",
        "RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS": "25",
    }
    explicit.update(_system_environment_defaults())

    def apply_current() -> None:
        facade.SPECS = tuple(
            replace(spec, default=explicit[spec.name]) if spec.name in explicit else spec
            for spec in facade.SPECS
        )
        facade.SPEC_BY_NAME = {spec.name: spec for spec in facade.SPECS}

    def refresh_specs() -> tuple[Any, ...]:
        original_refresh()
        apply_current()
        return facade.SPECS

    facade.refresh_specs = refresh_specs
    refresh_specs()
    facade._rasai_system_default_catalog = True


def _patch_apdex_guidance() -> None:
    from rasai import console_apdex_configuration as apdex_ui

    if getattr(apdex_ui, "_rasai_system_default_guidance", False):
        return

    apdex_ui.DEFAULT_UX_SAMPLES = LOW_LOAD_EXPERIENCE_SAMPLES

    def show_experience_defaults() -> None:
        print(apdex_ui.paint("\n  Defaults e variáveis do Synthetic User Experience Apdex:", apdex_ui.DIM))
        rows = (
            (apdex_ui.UX_ENABLED_ENV, "true", "padrão do sistema RASAi"),
            (apdex_ui.UX_SAMPLES_ENV, LOW_LOAD_EXPERIENCE_SAMPLES, "baixa carga; recomendado >=100 para grupo normal/representativo"),
            (apdex_ui.UX_MAX_ATTEMPTS_ENV, "25 no baseline; derivado ceil(1.25 × samples)", "RASAi"),
            (apdex_ui.UX_MAX_PAGES_ENV, apdex_ui.DEFAULT_UX_MAX_PAGES, "RASAi"),
            (apdex_ui.UX_DEVICE_MIX_ENV, apdex_ui.DEFAULT_UX_DEVICE_MIX, "RASAi; sem equivalente Dynatrace RUM"),
            (apdex_ui.UX_SESSION_MODE_ENV, apdex_ui.DEFAULT_UX_SESSION_MODE, "RASAi; sem equivalente RUM"),
            (apdex_ui.UX_KPM_ENV, apdex_ui.DEFAULT_UX_KPM, f"fallback compatível; Dynatrace Load prefere {apdex_ui.DYNATRACE_LOAD_PRIMARY_KPM}"),
            (apdex_ui.UX_SATISFIED_ENV, f"{apdex_ui.DEFAULT_UX_SATISFIED_SECONDS:g}s", "Dynatrace Load fallback/reference"),
            (apdex_ui.UX_FRUSTRATED_ENV, f"{apdex_ui.DEFAULT_UX_FRUSTRATED_SECONDS:g}s", "Dynatrace Load fallback/reference"),
            (apdex_ui.UX_ERRORS_ENV, "true", "erros qualificáveis podem forçar Frustrated"),
            (apdex_ui.UX_ERROR_SCOPE_ENV, apdex_ui.DEFAULT_UX_ERROR_SCOPE, "RASAi conservador"),
            (apdex_ui.UX_SETTLE_ENV, f"{apdex_ui.DEFAULT_UX_SETTLE_SECONDS:g}s", "RASAi"),
            (apdex_ui.UX_DELAY_ENV, f"{apdex_ui.DEFAULT_UX_DELAY_SECONDS:g}s", "RASAi"),
            (apdex_ui.UX_CONCURRENCY_ENV, apdex_ui.DEFAULT_UX_CONCURRENCY, "RASAi"),
            (apdex_ui.DYNATRACE_IMPORT_ENV, "false", "live import exige credencial/configuração"),
            (apdex_ui.DYNATRACE_BASE_URL_ENV, "vazio", "somente importação live"),
            (apdex_ui.DYNATRACE_APPLICATION_ID_ENV, "vazio", "somente importação live"),
            (apdex_ui.DYNATRACE_CONFIG_JSON_ENV, "vazio", "importação offline/reproduzível"),
        )
        for name, default, source in rows:
            print(apdex_ui.paint(f"    {name} = {default}  [{source}]", apdex_ui.DIM))
        print(apdex_ui.paint("    DYNATRACE_API_TOKEN = secret de ambiente; nunca persistido no INI/report.", apdex_ui.DIM))

    def configure_navigation(state: Any) -> None:
        print("\nSynthetic Navigation Apdex")
        print(
            "Baseline RASAi: habilitado, T=3s Dynatrace-compatible, 1 amostra/contexto para baixa carga. "
            "Use o SLO real quando conhecido; >=100 amostras/contexto é o alvo recomendado para resultado representativo.\n"
        )
        enabled = apdex_ui._yes_no(
            "Habilitar Synthetic Navigation Apdex? Gera tráfego HTTP real contra o alvo",
            state.synthetic_apdex,
        )
        state.synthetic_apdex = enabled
        if not enabled:
            state.apdex_experience = False
            return

        state.apdex_threshold = apdex_ui._required_positive(
            "Threshold T em segundos", state.apdex_threshold
        )
        state.apdex_samples = int(apdex_ui._number(
            "Amostras válidas por URL/dispositivo",
            state.apdex_samples,
            minimum=1,
            integer=True,
            help_text="padrão baixa carga=1; 1-99 é small-group/diagnóstico; recomendado >=100 para grupo normal/representativo.",
        ))
        suggested_attempts = max(
            state.apdex_samples,
            int(math.ceil(state.apdex_samples * 1.25)),
        )
        if state.apdex_max_attempts < state.apdex_samples:
            state.apdex_max_attempts = suggested_attempts
        state.apdex_max_attempts = int(apdex_ui._number(
            "Máximo de tentativas por URL/dispositivo",
            state.apdex_max_attempts,
            minimum=state.apdex_samples,
            integer=True,
            help_text="permite repor amostras inválidas; referência derivada ceil(1.25 × amostras).",
        ))
        state.apdex_max_pages = int(apdex_ui._number(
            "Máximo de páginas (0=todas)",
            state.apdex_max_pages,
            minimum=0,
            integer=True,
            help_text="baseline=1 para conter carga; amplie deliberadamente quando precisar de cobertura maior.",
        ))
        minimum_timeout = 4.0 * state.apdex_threshold
        recommended_timeout = max(45.0, minimum_timeout + 5.0)
        if state.apdex_timeout <= minimum_timeout:
            state.apdex_timeout = recommended_timeout
        state.apdex_timeout = float(apdex_ui._number(
            "Timeout por navegação (deve ser > 4T)",
            state.apdex_timeout,
            minimum=0.000001,
            help_text="evita truncar artificialmente a faixa Frustrated.",
        ))
        state.apdex_delay = float(apdex_ui._number(
            "Delay mínimo entre inícios",
            state.apdex_delay,
            minimum=0.0,
            help_text="valores maiores reduzem a pressão sobre o alvo e aumentam a duração.",
        ))
        state.apdex_concurrency = int(apdex_ui._number(
            "Concorrência (1-2)",
            state.apdex_concurrency,
            minimum=1,
            integer=True,
            help_text="1 é o default conservador; 2 aumenta a carga concorrente.",
        ))
        apdex_ui.config_from_state(state)

    apdex_ui._show_experience_defaults = show_experience_defaults
    apdex_ui._configure_navigation = configure_navigation
    apdex_ui._rasai_system_default_guidance = True


def install(console_module: ModuleType) -> None:
    """Install system-default loading, restore UX and aligned catalog/help metadata."""
    if getattr(console_module, "_rasai_system_defaults_installed", False):
        return

    _patch_environment_catalog()
    _patch_apdex_guidance()

    original_menu = console_module._menu
    original_configure = console_module._configure
    console_module.load_console_config = load_console_config_with_system_defaults

    def menu(state: Any) -> str:
        original_input = builtins.input
        printed = False

        def decorated_input(prompt: str = "") -> str:
            nonlocal printed
            if not printed and prompt.strip().casefold().startswith("escolha"):
                print("\nCONFIGURAÇÃO DO PROGRAMA")
                print("D. Restaurar padrões do RASAi")
                printed = True
            return original_input(prompt)

        builtins.input = decorated_input
        try:
            return original_menu(state)
        finally:
            builtins.input = original_input

    def configure(state: Any, choice: str) -> None:
        if choice == "D":
            _restore_menu(console_module, state)
            return
        original_configure(state, choice)

    console_module._menu = menu
    console_module._configure = configure
    console_module._rasai_system_defaults_installed = True
