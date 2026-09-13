"""Interactive-console adapter for reusable AUD configurations."""
from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from rasai.audit_configuration_reuse import (
    KIND_CONSOLE,
    ReusableAuditConfiguration,
    changed_fields,
    load_reusable_audit_configuration,
)
from rasai.audit_configuration_reuse_runtime import configuration_context

_INSTALLED = False
_SESSION_SOURCE: dict[int, ReusableAuditConfiguration] = {}


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
    }


def _export_settings(state: Any, targets: tuple[str, ...] | list[str]) -> dict[str, Any]:
    """Export the effective non-secret console configuration for one AUD."""
    from rasai import console_settings

    console_settings.sync_nonsecret_runtime_environment(state)
    parser = console_settings._parser_for_state(state)
    settings = {
        section: {name: value for name, value in parser.items(section, raw=True)}
        for section in parser.sections()
    }
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


def _as_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in {"1", "true", "yes", "on", "sim", "s"}:
        return True
    if normalized in {"0", "false", "no", "off", "nao", "não", "n"}:
        return False
    return default


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
    if not isinstance(raw_queries, list):
        warnings.append("search_intelligence.queries: lista inválida")
        raw_queries = []
    queries = tuple(
        dict.fromkeys(
            " ".join(str(value).strip().split())
            for value in raw_queries
            if str(value).strip()
        )
    )
    enabled = _as_bool(search.get("enabled"), default=bool(queries))
    state.search_queries = queries if enabled else ()

    try:
        depth = int(search.get("depth", getattr(state, "search_depth", 20)))
        if depth <= 0:
            raise ValueError
        state.search_depth = depth
    except (TypeError, ValueError):
        warnings.append("search_intelligence.depth: use inteiro > 0")

    device = str(search.get("device", getattr(state, "search_device", "mobile"))).strip().casefold()
    if device in {"mobile", "desktop"}:
        state.search_device = device
    else:
        warnings.append("search_intelligence.device: use mobile ou desktop")
    state.search_region = str(search.get("region", "") or "").strip()
    state.search_competitive = _as_bool(
        search.get("competitive"),
        default=bool(getattr(state, "search_competitive", True)),
    )
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
    targets = tuple(str(value).strip() for value in raw_targets if str(value).strip())
    if not targets:
        raise ValueError("snapshot de console não possui targets válidos")

    warnings: list[str] = []
    allowed_environment = set(console_settings._known_nonsecret_environment_names())
    environment = raw_settings.get("environment", {})
    if not isinstance(environment, Mapping):
        raise ValueError("snapshot de console possui seção environment inválida")

    # Historical non-secret settings override the current non-secret session. Secrets
    # remain outside this allowlist and continue resolved from the current OS/session.
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

    if len(targets) == 1:
        state.input_mode = "url"
        state.target = targets[0]
    else:
        reuse_root = Path(state.audits_root) / ".reused-inputs"
        reuse_root.mkdir(parents=True, exist_ok=True)
        target_file = reuse_root / f"{source_audit_id}.txt"
        target_file.write_text("\n".join(targets) + "\n", encoding="utf-8", newline="\n")
        state.input_mode = "file"
        state.target = str(target_file)

    console_settings.sync_nonsecret_runtime_environment(state)
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
    audit_id = input("Audit ID de origem (AUD-*): ").strip().upper()
    load_source_configuration(state, audit_id, console_module=console_module)


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
            return original_input(prompt)

        builtins.input = input_with_hint
        try:
            return original_menu(state)
        finally:
            builtins.input = original_input

    def configure_with_reuse(state: Any, choice: str) -> None:
        if choice == "L":
            _load_source(state, console_module=interactive_console)
            return
        original_configure(state, choice)

    def run_with_configuration(state: Any) -> int:
        try:
            targets = tuple(preflight(state))
        except (OSError, UnicodeError, ValueError):
            # Preserve the final console runtime as the authority for validation and
            # user-facing error handling. No audit => no snapshot to persist.
            return original_run(state)

        effective = _export_settings(state, targets)
        source = _SESSION_SOURCE.get(id(state))
        differences = changed_fields(source.configuration, effective) if source else ()
        with configuration_context(
            kind=KIND_CONSOLE,
            configuration=effective,
            source_audit_id=source.audit_id if source else None,
            source_configuration_hash=source.configuration_hash if source else None,
            changed_fields=differences,
            execution_series_id=source.execution_series_id if source else None,
            scope={"surface": "console"},
        ):
            return original_run(state)

    interactive_console._menu = menu_with_visible_reuse
    interactive_console._configure = configure_with_reuse
    interactive_console.run_audit_from_console = run_with_configuration
    _INSTALLED = True
