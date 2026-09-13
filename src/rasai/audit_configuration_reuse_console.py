"""Interactive-console adapter for reusable completed-AUD configurations."""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from rasai.audit_configuration_reuse import (
    KIND_CONSOLE,
    ReusableAuditConfiguration,
    changed_fields,
    load_reusable_audit_configuration,
    persist_audit_configuration,
)

_INSTALLED = False
_SESSION_SOURCE: dict[int, ReusableAuditConfiguration] = {}


def _export_settings(state: Any, targets: tuple[str, ...] | list[str]) -> dict[str, Any]:
    """Export the same non-secret surface as the INI, but canonicalize targets."""
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
    return {"settings": settings, "targets": list(targets)}


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
    # are outside this allowlist and therefore remain resolved from the current OS/session.
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


def _executed_targets(workspace: Path, audit_id: str) -> tuple[str, ...]:
    """Read the persisted effective input set instead of re-reading mutable user files."""
    database = workspace / "audit.db"
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=1.0)
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "audit_input_urls" in tables:
            columns = {
                str(row[1])
                for row in connection.execute('PRAGMA table_info("audit_input_urls")').fetchall()
            }
            if {"audit_id", "normalized_url"} <= columns:
                rows = connection.execute(
                    "SELECT DISTINCT normalized_url FROM audit_input_urls WHERE audit_id=? ORDER BY normalized_url",
                    (audit_id,),
                ).fetchall()
                targets = tuple(str(row[0]) for row in rows if row and row[0])
                if targets:
                    return targets
        if "pages" in tables:
            columns = {
                str(row[1]) for row in connection.execute('PRAGMA table_info("pages")').fetchall()
            }
            if {"audit_id", "normalized_url"} <= columns:
                rows = connection.execute(
                    "SELECT DISTINCT normalized_url FROM pages WHERE audit_id=? ORDER BY normalized_url",
                    (audit_id,),
                ).fetchall()
                return tuple(str(row[0]) for row in rows if row and row[0])
        return ()
    finally:
        connection.close()


def _persist_console_snapshot(workspace: Path, state: Any) -> None:
    audit_id = str(getattr(state, "audit_id", "") or "")
    if not audit_id:
        return
    targets = _executed_targets(workspace, audit_id)
    if not targets:
        return
    effective = _export_settings(state, targets)
    source = _SESSION_SOURCE.get(id(state))
    if source is None:
        persist_audit_configuration(
            workspace,
            audit_id=audit_id,
            kind=KIND_CONSOLE,
            configuration=effective,
            scope={"surface": "console"},
        )
        return
    persist_audit_configuration(
        workspace,
        audit_id=audit_id,
        kind=KIND_CONSOLE,
        configuration=effective,
        source_audit_id=source.audit_id,
        source_configuration_hash=source.configuration_hash,
        changed=changed_fields(source.configuration, effective),
        execution_series_id=source.execution_series_id,
        scope={"surface": "console"},
    )


def _load_source(state: Any) -> None:
    from rasai.console_session import mark_dirty

    audit_id = input("Audit ID de origem (AUD-*): ").strip().upper()
    if not audit_id:
        return
    try:
        source = load_reusable_audit_configuration(
            state.audits_root,
            audit_id,
            expected_kind=KIND_CONSOLE,
        )
        warnings = _apply_settings(state, source.configuration, source.audit_id)
    except (FileNotFoundError, OSError, ValueError) as exc:
        state.status = "CONFIG_SOURCE_REJECTED"
        state.operation = "LOCAL:AUD_CONFIG_REUSE"
        state.error = str(exc)
        return
    _SESSION_SOURCE[id(state)] = source
    mark_dirty(state)
    state.status = "READY"
    state.operation = "LOCAL:AUD_CONFIG_REUSE"
    state.error = (
        f"Configuração carregada de {source.audit_id}. Revise e altere se necessário; "
        "a próxima execução criará um novo AUD."
        + (" Avisos: " + "; ".join(warnings) if warnings else "")
    )


def install(interactive_console: Any) -> None:
    """Install one top-level shortcut and persist effective console configuration."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import console_runtime
    import builtins

    original_menu = interactive_console._menu
    original_configure = interactive_console._configure
    original_projection = console_runtime.persist_execution_projection

    def menu_with_visible_reuse(state: Any) -> str:
        original_input = builtins.input

        def input_with_hint(prompt: str = "") -> str:
            if prompt == "Escolha: ":
                print("L. Carregar configuração de AUD concluído [NOVA EXECUÇÃO]")
            return original_input(prompt)

        builtins.input = input_with_hint
        try:
            return original_menu(state)
        finally:
            builtins.input = original_input

    def configure_with_reuse(state: Any, choice: str) -> None:
        if choice == "L":
            _load_source(state)
            return
        original_configure(state, choice)

    def projection_with_snapshot(
        workspace: Path | None,
        state: Any,
        estimate: Any,
        **kwargs: Any,
    ) -> bool:
        persisted = original_projection(workspace, state, estimate, **kwargs)
        if workspace is not None:
            try:
                _persist_console_snapshot(workspace, state)
            except (OSError, sqlite3.Error, ValueError):
                # Derived lineage must never change the outcome of an otherwise valid
                # audit. A missing snapshot will fail closed on a later reuse attempt.
                pass
        return persisted

    interactive_console._menu = menu_with_visible_reuse
    interactive_console._configure = configure_with_reuse
    console_runtime.persist_execution_projection = projection_with_snapshot
    _INSTALLED = True
