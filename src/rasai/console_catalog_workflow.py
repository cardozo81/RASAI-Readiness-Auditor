"""Final composition of the catalog-driven interactive-console preparation flow."""
from __future__ import annotations

import builtins
from types import ModuleType
from typing import Any

from rasai.audit_catalog import CATALOG_VERSION
from rasai.console_ui import DIM
from rasai.console_catalog_plan import (
    _PLANS,
    catalog_snapshot,
    ai_execution_enabled,
    catalog_status,
    deselect_catalog,
    plan_status,
    project_plan,
    select_catalog,
    selected_catalog_ids,
    set_ai_execution_enabled,
    set_selected_catalog_ids,
)
from rasai.console_catalog_ui import catalog_menu, preparation_menu


def _rewrite_catalog_guidance(text: str) -> str:
    """Translate superseded menu-number guidance to the catalog-era public UX."""
    return (
        str(text)
        .replace("item 4", "INÍCIO > Inteligência Artificial")
        .replace("ITEM 4", "INÍCIO > INTELIGÊNCIA ARTIFICIAL")
        .replace("item 13", "CAT-08")
        .replace("ITEM 13", "CAT-08")
        .replace("item T", "CAT-05")
        .replace("ITEM T", "CAT-05")
        .replace("F. Perfil da execução", "CATÁLOGO DA AUDITORIA")
        .replace("F. PERFIL DA EXECUÇÃO", "CATÁLOGO DA AUDITORIA")
    )


def _install_catalog_guidance(console_module: ModuleType) -> None:
    """Keep legacy configurator copy aligned with the catalog navigation.

    These wrappers change presentation only. Existing configuration handlers, validation
    and runtime semantics remain untouched.
    """
    original_configure = console_module._configure
    if not bool(getattr(original_configure, "_rasai_catalog_guidance", False)):
        def configure(state: Any, choice: str) -> None:
            original_print = builtins.print

            def adjusted_print(*args: Any, **kwargs: Any) -> None:
                rewritten = tuple(
                    _rewrite_catalog_guidance(arg) if isinstance(arg, str) else arg
                    for arg in args
                )
                original_print(*rewritten, **kwargs)

            builtins.print = adjusted_print
            try:
                original_configure(state, choice)
            finally:
                builtins.print = original_print
            if isinstance(getattr(state, "error", None), str):
                state.error = _rewrite_catalog_guidance(state.error)

        configure._rasai_catalog_guidance = True  # type: ignore[attr-defined]
        configure._rasai_original = original_configure  # type: ignore[attr-defined]
        console_module._configure = configure

    try:
        from rasai import improvement_intelligence_console as improvement
    except ImportError:
        return

    original_ready = improvement._single_url_ready
    if not bool(getattr(original_ready, "_rasai_catalog_guidance", False)):
        def single_url_ready(state: Any):
            ready, detail = original_ready(state)
            return ready, _rewrite_catalog_guidance(detail)

        single_url_ready._rasai_catalog_guidance = True  # type: ignore[attr-defined]
        single_url_ready._rasai_original = original_ready  # type: ignore[attr-defined]
        improvement._single_url_ready = single_url_ready

    original_improvement_configure = improvement.configure
    if not bool(getattr(original_improvement_configure, "_rasai_catalog_guidance", False)):
        def improvement_configure(console: ModuleType, state: Any) -> None:
            original_print = builtins.print

            def adjusted_print(*args: Any, **kwargs: Any) -> None:
                rewritten = tuple(
                    _rewrite_catalog_guidance(arg) if isinstance(arg, str) else arg
                    for arg in args
                )
                original_print(*rewritten, **kwargs)

            builtins.print = adjusted_print
            try:
                original_improvement_configure(console, state)
            finally:
                builtins.print = original_print
            if isinstance(getattr(state, "error", None), str):
                state.error = _rewrite_catalog_guidance(state.error)

        improvement_configure._rasai_catalog_guidance = True  # type: ignore[attr-defined]
        improvement_configure._rasai_original = original_improvement_configure  # type: ignore[attr-defined]
        improvement.configure = improvement_configure


def _install_configuration_reuse_contract() -> None:
    """Persist/restore CAT-* selection in the existing secret-free AUD snapshot."""
    try:
        from rasai import audit_configuration_reuse_console as reuse
    except ImportError:
        return
    if getattr(reuse, "_rasai_audit_catalog_snapshot", False):
        return
    original_effective = reuse._effective_execution_snapshot
    original_apply = reuse._apply_settings

    def effective_execution_snapshot(state: Any, preflight: Any):
        targets, effective = original_effective(state, preflight)
        effective.pop("execution_profile", None)
        rows = tuple(row for row in catalog_snapshot(state) if row["selected"])
        effective["audit_catalog"] = {
            "version": CATALOG_VERSION,
            "selected": list(selected_catalog_ids(state)),
            "ai_enabled": ai_execution_enabled(state),
            "items": list(rows),
        }
        return targets, effective

    def apply_settings(state: Any, configuration: Any, source_audit_id: str):
        warnings = list(original_apply(state, configuration, source_audit_id))
        raw = configuration.get("audit_catalog") if hasattr(configuration, "get") else None
        if raw is None:
            _PLANS.pop(id(state), None)
            return tuple(warnings)
        if not hasattr(raw, "get"):
            warnings.append("audit_catalog: bloco inválido")
            return tuple(warnings)
        selected = raw.get("selected", [])
        if not isinstance(selected, list):
            warnings.append("audit_catalog.selected: lista inválida")
            return tuple(warnings)
        try:
            set_selected_catalog_ids(state, [str(item) for item in selected])
            set_ai_execution_enabled(state, bool(raw.get("ai_enabled", False)))
        except ValueError as exc:
            warnings.append(f"audit_catalog: {exc}")
        return tuple(warnings)

    reuse._effective_execution_snapshot = effective_execution_snapshot
    reuse._apply_settings = apply_settings
    reuse._rasai_audit_catalog_snapshot = True


def _install_execution_projection(console_module: ModuleType) -> None:
    if getattr(console_module, "_rasai_catalog_execution_projection", False):
        return
    original_run = console_module.run_audit_from_console

    def run(state: Any) -> int:
        status, detail = plan_status(state)
        if status == "BLOQUEADO":
            state.error = detail
            return 2
        with project_plan(state):
            return int(original_run(state) or 0)

    console_module.run_audit_from_console = run
    console_module._rasai_catalog_execution_projection = True


def install(console_module: ModuleType) -> None:
    if getattr(console_module, "_rasai_catalog_workflow_installed", False):
        return
    from rasai import console_navigation as navigation
    from rasai import console_ui_catalog as ui_catalog
    from rasai import console_configuration_transaction as configuration_transaction

    ui_catalog._STATUS_COLORS["NÃO SELECIONADO"] = DIM
    configuration_transaction.install(ui_catalog)
    navigation._preparation_menu = preparation_menu
    _install_catalog_guidance(console_module)
    _install_configuration_reuse_contract()
    _install_execution_projection(console_module)

    # Presentation-only layer: friendly labels/value/origin are the public surface;
    # technical environment names remain available through an explicit details action.
    from rasai import console_configuration_presentation as configuration_presentation
    configuration_presentation.install(console_module)

    console_module._rasai_catalog_workflow_installed = True


# Stable compatibility/test aliases within the new catalog architecture.
_select = select_catalog
_deselect = deselect_catalog
_catalog_menu = catalog_menu
_catalog_status = catalog_status
_plan_status = plan_status
_project_plan = project_plan
_project_execution_plan = project_plan
