"""Interactive-console adapter for reusable AUD configurations."""
from __future__ import annotations

import math
import os
from dataclasses import fields, is_dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from rasai.console_input_contract import EditCancelled, prompt_text
from rasai.audit_configuration_reuse import (
    KIND_CONSOLE,
    ReusableAuditConfiguration,
    changed_fields,
    configuration_hash,
    load_reusable_audit_configuration,
)
from rasai.audit_configuration_reuse_runtime import configuration_context

_INSTALLED = False
_SESSION_SOURCE: dict[int, ReusableAuditConfiguration] = {}
_ARCHITECTURE_SELECTION: dict[int, object] = {}


def _search_execution_settings(state: Any) -> dict[str, Any] | None:
    if not hasattr(state, "search_queries"):
        return None
    queries = tuple(getattr(state, "search_queries", ()) or ())
    return {
        "enabled": bool(queries),
        "queries": list(queries),
        "depth": int(getattr(state, "search_depth", 20)),
        "region": str(getattr(state, "search_region", "") or ""),
        "device": str(getattr(state, "search_device", "mobile") or "mobile"),
        "competitive": bool(getattr(state, "search_competitive", True)),
        "compare_content": bool(getattr(state, "search_compare_content", False)),
        "max_content_pages": int(getattr(state, "search_max_content_pages", 3)),
        "content_timeout_seconds": float(getattr(state, "search_content_timeout_seconds", 10.0)),
        "content_max_bytes": int(getattr(state, "search_content_max_bytes", 2_000_000)),
        "content_max_redirects": int(getattr(state, "search_content_max_redirects", 5)),
        "ai_competitive": bool(getattr(state, "search_ai_competitive", False)),
        "ymyl_mode": str(getattr(state, "search_ymyl_mode", "AUTO") or "AUTO").upper(),
    }


def _capture_environment(names: set[str]) -> dict[str, tuple[bool, str | None]]:
    return {name: (name in os.environ, os.environ.get(name)) for name in names}


def _restore_environment(snapshot: Mapping[str, tuple[bool, str | None]]) -> None:
    for name, (existed, value) in snapshot.items():
        if existed and value is not None:
            os.environ[name] = value
        else:
            os.environ.pop(name, None)


def _export_settings(state: Any, targets: tuple[str, ...] | list[str]) -> dict[str, Any]:
    """Export one effective secret-free execution snapshot without changing the session.

    ``console_settings`` uses process environment variables as an adapter surface for
    several non-secret settings. Building a reusable AUD snapshot must not promote an
    execution-only profile overlay into the parent console environment, so every key
    touched by that projection is restored exactly after serialization.
    """
    from rasai import console_settings

    projection = console_settings._runtime_environment_projection(state)
    names = set(console_settings._known_nonsecret_environment_names()) | set(projection)
    environment_snapshot = _capture_environment(names)
    try:
        console_settings.sync_nonsecret_runtime_environment(state)
        parser = console_settings._parser_for_state(state)
        settings = {
            section: {name: value for name, value in parser.items(section, raw=True)}
            for section in parser.sections()
        }
    finally:
        _restore_environment(environment_snapshot)

    # Filesystem placement and the original URL/TXT representation are operational
    # details. The effective normalized target set is the reproducible input.
    console = settings.get("console", {})
    console.pop("target", None)
    console.pop("input_mode", None)
    console.pop("audits_root", None)
    payload: dict[str, Any] = {"settings": settings, "targets": list(targets)}
    search = _search_execution_settings(state)
    if search is not None:
        payload["search_intelligence"] = search
    return payload


def _execution_profile_metadata(session: Any) -> dict[str, Any]:
    return {
        "profile_id": str(getattr(session, "profile_id", "") or ""),
        "label": str(getattr(session, "label", "") or ""),
        "modules": list(tuple(getattr(session, "modules", ()) or ())),
        "ai_mode": str(getattr(session, "ai_mode", "") or ""),
        "manual_overrides": sorted(str(item) for item in (getattr(session, "manual_overrides", set()) or set())),
    }


def _effective_execution_snapshot(
    state: Any,
    preflight: Any,
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Resolve the exact profile/user state used by the next audit subprocess.

    Profile projection is deliberately temporary. The same ``effective_profile``
    context used by execution is used here for preflight and serialization, then the
    parent session is restored before the real runner applies the profile again.
    """
    from rasai.console_execution_profiles import active_profile, effective_profile

    session = active_profile(state)
    if session is None:
        targets = tuple(preflight(state))
        return targets, _export_settings(state, targets)

    with effective_profile(state, session):
        targets = tuple(preflight(state))
        effective = _export_settings(state, targets)
        effective["execution_profile"] = _execution_profile_metadata(session)
    return targets, effective


def _as_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in {"1", "true", "yes", "on", "sim", "s"}:
        return True
    if normalized in {"0", "false", "no", "off", "nao", "não", "n"}:
        return False
    return default


def _strict_nonnegative_integer(value: Any) -> int:
    """Reject bool, fractional values and non-finite numbers on AUD restore."""
    if isinstance(value, bool):
        raise ValueError("boolean is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError("non-integral numeric value")
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or not stripped.isascii() or not stripped.isdecimal():
            raise ValueError("invalid decimal integer")
        return int(stripped)
    raise ValueError("unsupported integer type")


def _apply_search_settings(state: Any, configuration: Mapping[str, Any], warnings: list[str]) -> None:
    search = configuration.get("search_intelligence")
    if search is None:
        return
    if not isinstance(search, Mapping):
        warnings.append("search_intelligence: bloco inválido")
        return
    if not hasattr(state, "search_queries"):
        warnings.append("search_intelligence: console atual não expõe Search Intelligence")
        return

    raw_queries = search.get("queries", [])
    if (not isinstance(raw_queries, list)
            or len(raw_queries) > 100
            or any(not isinstance(value, str) or len(value) > 500
                   or any(ord(ch) < 32 and ch not in "\\t\\n\\r" for ch in value)
                   for value in raw_queries)):
        warnings.append("search_intelligence.queries: lista inválida")
        # An invalid historical payload must never erase the current session's
        # explicit search inputs or convert arbitrary objects into paid queries.
    else:
        queries = tuple(dict.fromkeys(
            " ".join(value.strip().split()) for value in raw_queries
            if value.strip()
        ))
        raw_enabled = search.get("enabled", bool(queries))
        if isinstance(raw_enabled, bool):
            enabled = raw_enabled
        elif isinstance(raw_enabled, str) and raw_enabled.strip().casefold() in {
            "1", "true", "yes", "on", "sim", "s", "0", "false", "no", "off", "nao", "não", "n"
        }:
            enabled = _as_bool(raw_enabled, default=False)
        else:
            warnings.append("search_intelligence.enabled: valor inválido")
            enabled = None
        if enabled is not None:
            state.search_queries = queries if enabled else ()

    try:
        candidate = search.get("depth", getattr(state, "search_depth", 20))
        depth = _strict_nonnegative_integer(candidate)
        if depth <= 0:
            raise ValueError
        state.search_depth = depth
    except (TypeError, ValueError, OverflowError):
        warnings.append("search_intelligence.depth: use inteiro > 0")

    raw_device = search.get("device", getattr(state, "search_device", "mobile"))
    if isinstance(raw_device, str) and raw_device.strip().casefold() in {"mobile", "desktop"}:
        state.search_device = raw_device.strip().casefold()
    else:
        warnings.append("search_intelligence.device: use mobile ou desktop")
    raw_region = search.get("region", "")
    if isinstance(raw_region, str) and len(raw_region) <= 200:
        state.search_region = raw_region.strip()
    else:
        warnings.append("search_intelligence.region: use texto até 200 caracteres")
    state.search_competitive = _as_bool(
        search.get("competitive"),
        default=bool(getattr(state, "search_competitive", True)),
    )
    state.search_compare_content = _as_bool(
        search.get("compare_content"),
        default=bool(getattr(state, "search_compare_content", False)),
    )
    state.search_ai_competitive = _as_bool(
        search.get("ai_competitive"),
        default=bool(getattr(state, "search_ai_competitive", False)),
    )
    try:
        candidate = search.get("max_content_pages", getattr(state, "search_max_content_pages", 3))
        value = _strict_nonnegative_integer(candidate)
        if value < 0:
            raise ValueError
        state.search_max_content_pages = value
    except (TypeError, ValueError, OverflowError):
        warnings.append("search_intelligence.max_content_pages: use inteiro >= 0")
    try:
        raw_timeout = search.get("content_timeout_seconds", getattr(state, "search_content_timeout_seconds", 10.0))
        if isinstance(raw_timeout, bool):
            raise ValueError
        value = float(raw_timeout)
        if not math.isfinite(value) or value <= 0:
            raise ValueError
        state.search_content_timeout_seconds = value
    except (TypeError, ValueError):
        warnings.append("search_intelligence.content_timeout_seconds: use número finito > 0")
    try:
        candidate = search.get("content_max_bytes", getattr(state, "search_content_max_bytes", 2_000_000))
        value = _strict_nonnegative_integer(candidate)
        if value <= 0:
            raise ValueError
        state.search_content_max_bytes = value
    except (TypeError, ValueError, OverflowError):
        warnings.append("search_intelligence.content_max_bytes: use inteiro > 0")
    try:
        candidate = search.get("content_max_redirects", getattr(state, "search_content_max_redirects", 5))
        value = _strict_nonnegative_integer(candidate)
        if value < 0:
            raise ValueError
        state.search_content_max_redirects = value
    except (TypeError, ValueError, OverflowError):
        warnings.append("search_intelligence.content_max_redirects: use inteiro >= 0")
    raw_ymyl = search.get("ymyl_mode", getattr(state, "search_ymyl_mode", "AUTO"))
    ymyl_mode = raw_ymyl.strip().upper() if isinstance(raw_ymyl, str) else None
    if ymyl_mode in {"AUTO", "ON", "OFF"}:
        state.search_ymyl_mode = ymyl_mode
    else:
        warnings.append("search_intelligence.ymyl_mode: use AUTO, ON ou OFF")
    if state.search_ai_competitive and not state.search_compare_content:
        warnings.append("search_intelligence.ai_competitive: exige compare_content=true")
        state.search_ai_competitive = False
    if state.search_queries:
        state.search_last_status = "PENDING"
        state.search_last_detail = f"{len(state.search_queries)} termo(s) restaurados do AUD de origem"
    else:
        state.search_last_status = "NOT_REQUESTED"
        state.search_last_detail = ""
        state.search_last_report = ""
        state.search_last_duration_seconds = None


def _apply_settings(state: Any, configuration: Mapping[str, Any], source_audit_id: str) -> tuple[str, ...]:
    from rasai import console_settings

    raw_settings = configuration.get("settings")
    raw_targets = configuration.get("targets")
    if not isinstance(raw_settings, Mapping) or not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("snapshot de console incompleto: settings/targets ausentes")
    # A historical snapshot must not silently restore a partial typed section.
    # Its explicit keys are applied independently below, but unknown sections
    # must not be treated as proof that the operator's current state was saved.
    if not isinstance(raw_settings.get("console"), Mapping):
        raise ValueError("snapshot de console sem seção console válida")
    if any(not isinstance(value, str) for value in raw_targets):
        raise ValueError("snapshot de console possui target não textual")
    targets = tuple(value.strip() for value in raw_targets if value.strip())
    if not targets:
        raise ValueError("snapshot de console não possui targets válidos")
    if len(targets) != 1:
        raise ValueError(
            f"{source_audit_id}: configuração histórica possui {len(targets)} targets; "
            "novas AUDs exigem exatamente uma URL. Selecione uma URL explicitamente antes de executar."
        )

    # Restore only the audited, canonical architecture choice. Historical
    # configurations without the field never invent an operator preference.
    from rasai.architecture_choice import CHOICE_KEY
    choice = None
    if CHOICE_KEY in configuration:
        from rasai.architecture_choice_audit_adapter import read_sealed_audit_choice
        choice = read_sealed_audit_choice(
            configuration, expected_hash=configuration_hash(configuration)
        ).choice
    # Do not mutate the selected policy until the rest of the restore succeeds.

    warnings: list[str] = []
    allowed_environment = set(console_settings._known_nonsecret_environment_names())
    environment = raw_settings.get("environment", {})
    if not isinstance(environment, Mapping):
        raise ValueError("snapshot de console possui seção environment inválida")

    # Preserve the process-session projection until all steps succeed.
    # No second persistence source is created, and secrets stay in memory.
    previous_environment = dict(os.environ)
    previous_state = {}
    if is_dataclass(state):
        previous_state.update({item.name: getattr(state, item.name)
                               for item in fields(state)})
    if hasattr(state, "__dict__"):
        previous_state.update(vars(state))

    try:
        # Historical non-secret settings override the current non-secret session only after
        # the operator explicitly chooses to load that AUD. Secrets remain outside this
        # allowlist and continue resolved from the current OS/session.
        for name in allowed_environment:
            raw = environment.get(name)
            if raw is None or not str(raw).strip():
                os.environ.pop(name, None)
            else:
                os.environ[name] = str(raw).strip()

        for section, known_values in console_settings._state_values(state).items():
            values = raw_settings.get(section, {})
            if not isinstance(values, Mapping):
                continue
            for option in known_values:
                if option == "config_version" or option not in values:
                    continue
                try:
                    console_settings._assign(state, section, option, str(values[option]))
                except (TypeError, ValueError) as exc:
                    warnings.append(f"{section}.{option}: {exc}")

        _apply_search_settings(state, configuration, warnings)

        state.input_mode = "url"
        state.target = targets[0]

        console_settings.sync_nonsecret_runtime_environment(state)
        if choice is None:
            _ARCHITECTURE_SELECTION.pop(id(state), None)
        else:
            _ARCHITECTURE_SELECTION[id(state)] = choice
    except BaseException:
        # A rejected restore must not leave a mixture of two AUD configurations.
        for name in set(previous_environment) | set(os.environ):
            if os.environ.get(name) != previous_environment.get(name):
                if name in previous_environment:
                    os.environ[name] = previous_environment[name]
                else:
                    os.environ.pop(name, None)
        for name, value in previous_state.items():
            setattr(state, name, value)
        raise
    return tuple(warnings)


def _dependency_warnings(state: Any, console_module: ModuleType | None = None) -> tuple[str, ...]:
    """Reconcile a restored non-secret configuration with current credentials/runtime."""
    warnings: list[str] = []
    try:
        from rasai.console_config import provider_capabilities
        provider = str(getattr(state, "ai_provider", "none") or "none")
        capability = provider_capabilities(blocks=getattr(state, "runtime_blocks", {})).get(provider)
        if provider != "none" and capability is not None and not capability.available:
            warnings.append(f"IA/{provider}: {capability.reason}")
    except (KeyError, TypeError, ValueError):
        pass

    if tuple(getattr(state, "search_queries", ()) or ()):
        try:
            from rasai.console_search_intelligence import validate_search_readiness
            ready, reason = validate_search_readiness(state)
            if not ready:
                warnings.append(f"Search Intelligence: {reason}")
        except (OSError, TypeError, ValueError) as exc:
            warnings.append(f"Search Intelligence: {exc}")

    if (
        bool(getattr(state, "web_performance", False))
        and str(getattr(state, "field_source", "auto")).casefold() == "crux"
        and not (os.environ.get("RASAI_CRUX_API_KEY") or "").strip()
    ):
        warnings.append("Web Performance/CrUX: RASAI_CRUX_API_KEY não configurada")

    if console_module is not None:
        try:
            ready, reason = console_module._execution_readiness(state)
            if not ready and reason:
                warnings.append(f"Preflight: {reason}")
        except (AttributeError, OSError, TypeError, ValueError):
            pass
    return tuple(dict.fromkeys(warnings))


def load_source_configuration(
    state: Any,
    audit_id: str,
    *,
    console_module: ModuleType | None = None,
) -> ReusableAuditConfiguration | None:
    """Load one AUD snapshot into the current session without copying credentials."""
    from rasai.console_session import mark_dirty

    normalized = str(audit_id or "").strip().upper()
    if not normalized:
        return None
    try:
        source = load_reusable_audit_configuration(
            state.audits_root,
            normalized,
            expected_kind=KIND_CONSOLE,
        )
        warnings = list(_apply_settings(state, source.configuration, source.audit_id))
        warnings.extend(_dependency_warnings(state, console_module))
    except (FileNotFoundError, OSError, ValueError) as exc:
        state.status = "CONFIG_SOURCE_REJECTED"
        state.operation = "LOCAL:AUD_CONFIG_REUSE"
        state.error = str(exc)
        return None
    _SESSION_SOURCE[id(state)] = source
    mark_dirty(state)
    state.status = "READY"
    state.operation = "LOCAL:AUD_CONFIG_REUSE"
    message = (
        f"Configuração carregada de {source.audit_id}. Revise e altere se necessário; "
        "a próxima execução criará um novo AUD."
    )
    if warnings:
        message += " ATENÇÃO: " + "; ".join(tuple(dict.fromkeys(warnings)))
    state.error = message
    return source


def _load_source(state: Any, console_module: ModuleType | None = None) -> None:
    try:
        audit_id = prompt_text(
            "Audit ID de origem (AUD-*)",
            empty_keeps_current=False,
        ).strip().upper()
    except EditCancelled:
        state.error = ""
        state.operation = "LOCAL:AUD_CONFIG_REUSE_CANCELLED"
        return
    load_source_configuration(state, audit_id, console_module=console_module)


def describe_session_architecture_choice(state: Any) -> str:
    """Visible session selection; never present a declaration as measured fact."""
    from rasai.architecture_choice import ArchitectureChoice

    selected = _ARCHITECTURE_SELECTION.get(id(state))
    if selected is None:
        return "NÃO SELECIONADA (padrão anterior; sem aplicação automática)"
    if not isinstance(selected, ArchitectureChoice):
        raise ValueError("Invalid session architecture selection")
    if selected.mode == "UNFORCED":
        return "SEM FORÇAR (escolha explícita; sem aplicação automática)"
    if selected.mode == "AUTO":
        return "AUTOMÁTICA (depende de evidência e consumidor autorizado)"
    return f"DECLARADA: {selected.declared_architecture} (informada, não descoberta)"


def install(interactive_console: ModuleType) -> None:
    """Install a top-level reuse shortcut and bind the final console execution state."""
    global _INSTALLED
    if _INSTALLED:
        return

    import builtins
    from rasai.console_config import preflight

    original_menu = interactive_console._menu
    original_configure = interactive_console._configure
    original_run = interactive_console.run_audit_from_console

    def menu_with_visible_reuse(state: Any) -> str:
        original_input = builtins.input

        def input_with_hint(prompt: str = "") -> str:
            if prompt == "Escolha: ":
                print("L. Carregar configuração de AUD [NOVA EXECUÇÃO]")
                print("Y. Arquitetura para esta auditoria [SEM ALTERAR OS ÍNDICES]")
                print("   Atual: " + describe_session_architecture_choice(state))
            return original_input(prompt)

        builtins.input = input_with_hint
        try:
            return original_menu(state)
        finally:
            builtins.input = original_input

    def configure_with_reuse(state: Any, choice: str) -> None:
        if choice == "Y":
            from rasai.architecture_choice import ArchitectureChoice
            print("Arquitetura da auditoria (opção consultiva; não modifica pontuação)")
            print("Seleção atual: " + describe_session_architecture_choice(state))
            print("1. Sem forçar arquitetura")
            print("2. Automática, baseada na descoberta")
            print("3. Definida por você")
            selected = builtins.input("Opção (V para voltar): ").strip().upper()
            if selected in {"V", ""}:
                return
            if selected == "1":
                selection = ArchitectureChoice("UNFORCED")
            elif selected == "2":
                selection = ArchitectureChoice("AUTO")
            elif selected == "3":
                options = {
                    "1": "STATIC_OR_SSR", "2": "HYDRATED",
                    "3": "CSR_SPA", "4": "MIXED",
                }
                print("1. Estática ou renderizada no servidor")
                print("2. Renderizada com hidratação")
                print("3. Aplicação de página única (SPA)")
                print("4. Arquitetura mista")
                arch = options.get(builtins.input("Tipo (V para voltar): ").strip())
                if arch is None:
                    return
                selection = ArchitectureChoice("DECLARED", arch)
            else:
                return
            _ARCHITECTURE_SELECTION[id(state)] = selection
            from rasai.console_session import mark_dirty
            mark_dirty(state)
            state.error = "Preferência de arquitetura registrada para esta sessão; os índices não foram alterados."
            return
        if choice == "L":
            _load_source(state, console_module=interactive_console)
            return
        original_configure(state, choice)

    def run_with_configuration(state: Any) -> int:
        try:
            targets, effective = _effective_execution_snapshot(state, preflight)
        except (OSError, UnicodeError, ValueError):
            # Preserve the final console runtime as the authority for validation and
            # user-facing error handling. No audit => no snapshot to persist.
            return original_run(state)

        source = _SESSION_SOURCE.get(id(state))
        # The provenance diff must describe the same effective payload that
        # is sealed for execution, including explicit architecture selection.
        from rasai.architecture_choice_audit_adapter import prepare_audit_choice_configuration
        choice = _ARCHITECTURE_SELECTION.get(id(state))
        sealed_effective = prepare_audit_choice_configuration(effective, choice=choice)
        # Advisory AUTO discovery is a separate operation: never part of the
        # sealed configuration, scoring, audit capture, RPR or complements.
        if getattr(choice, "mode", None) == "AUTO" and len(targets) == 1:
            from rasai.architecture_acquisition_preferences import read_mode, SKIP
            acquisition_mode = read_mode()
            if acquisition_mode != SKIP:
                from rasai.domain import DeviceContext
                from rasai.architecture_choice_audit_adapter import observe_auto_architecture_before_audit
                try:
                    device = DeviceContext(str(getattr(state, "device", "MOBILE")).upper())
                    observed = observe_auto_architecture_before_audit(
                        targets[0], device, mode=acquisition_mode,
                        consent=lambda _: False,  # AUD must never install Docker.
                    )
                    print("Descoberta consultiva na nova AUD: "
                          + observed.assessment.architecture.value)
                    if observed.assessment.limitation:
                        print("Limitação da descoberta: " + observed.assessment.limitation)
                except (OSError, RuntimeError, ValueError):
                    print("Descoberta consultiva indisponível; AUD independente preservada.")
        differences = changed_fields(source.configuration, sealed_effective) if source else ()
        with configuration_context(
            kind=KIND_CONSOLE,
            configuration=effective,
            architecture_choice=choice,
            source_audit_id=source.audit_id if source else None,
            source_configuration_hash=source.configuration_hash if source else None,
            changed_fields=differences,
            execution_series_id=source.execution_series_id if source else None,
            scope={
                "surface": "console",
                "profile_effective": bool(effective.get("execution_profile")),
                "targets": len(targets),
            },
        ):
            return original_run(state)

    interactive_console._menu = menu_with_visible_reuse
    interactive_console._configure = configure_with_reuse
    interactive_console.run_audit_from_console = run_with_configuration
    _INSTALLED = True
