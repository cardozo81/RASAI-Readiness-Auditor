"""Final audit-catalog configuration refinements for the interactive console.

This layer is intentionally narrow. It improves the operator-facing catalog configuration
surface without changing collectors, scoring, readiness rules, provider routing or secret
handling:

- persist the selected CAT-* plan and optional-AI choice in ``rasai-console.ini``;
- keep CAT-05 execution inputs visibly separate from reusable source configuration;
- group CAT-05 settings by SERP, GSC, CrUX History, Clarity and Common Crawl;
- keep Dynatrace-specific Experience Apdex settings together and at the end;
- keep configuration columns aligned even when a friendly label is long.
"""
from __future__ import annotations

import builtins
import re
from types import ModuleType
from typing import Any

from rasai.console_ui import DIM, paint

_INSTALLED = False
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_LABEL_WIDTH = 46
_VALUE_WIDTH = 22


def _plain(value: object) -> str:
    return _ANSI_RE.sub("", str(value))


def _fit_cell(value: object, width: int) -> str:
    """Fit one plain-text table cell without letting later columns drift."""
    text = str(value)
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1].rstrip() + "…"


def _plan_snapshot(state: Any) -> tuple[tuple[str, ...], bool]:
    """Read the catalog plan without creating a stale plan during INI loading."""
    from rasai.audit_catalog import CATALOGS
    from rasai import console_catalog_plan as plan

    entry = plan._PLANS.get(id(state))  # noqa: SLF001 - same-process console state owner
    if entry is not None and entry[0] is state:
        selected = set(entry[1].selected)
        ai_enabled = bool(entry[1].ai_enabled)
    else:
        selected: set[str] = set()
        if bool(getattr(state, "web_performance", False)):
            selected.add("CAT-04")
        if tuple(getattr(state, "search_queries", ()) or ()):
            selected.add("CAT-05")
        if bool(getattr(state, "synthetic_apdex", False)):
            selected.add("CAT-06")
        if bool(getattr(state, "apdex_experience", False)):
            selected.update(("CAT-06", "CAT-07"))
        if bool(getattr(state, "improvement_enabled", False)):
            selected.add("CAT-08")
        if bool(
            getattr(state, "content_remediation", False)
            or getattr(state, "technical_remediation", False)
        ):
            selected.add("CAT-09")
        ai_enabled = bool(
            getattr(state, "improvement_enabled", False)
            or getattr(state, "content_remediation", False)
            or getattr(state, "technical_remediation", False)
        )
    ordered = tuple(item.id for item in CATALOGS if item.id in selected)
    return ordered, ai_enabled


def _install_catalog_ini_persistence() -> None:
    from rasai import console_settings as settings

    if getattr(settings, "_rasai_catalog_plan_persistence", False):
        return

    previous_values = settings._state_values
    previous_assign = settings._assign

    def state_values(state: Any) -> dict[str, dict[str, str]]:
        result = previous_values(state)
        selected, ai_enabled = _plan_snapshot(state)
        result["audit_catalog"] = {
            "selected": ", ".join(selected),
            "ai_enabled": "true" if ai_enabled else "false",
        }
        return result

    def assign(state: Any, section: str, option: str, raw: str) -> None:
        if section != "audit_catalog":
            return previous_assign(state, section, option, raw)

        from rasai import console_catalog_plan as plan

        if option == "selected":
            selected = [
                item.strip().upper()
                for item in re.split(r"[,;]", raw)
                if item.strip()
            ]
            plan.set_selected_catalog_ids(state, selected)
            return None
        if option == "ai_enabled":
            enabled = settings._parse_bool(raw)
            if enabled or not plan.ai_required(state):
                plan.set_ai_execution_enabled(state, enabled)
            return None
        return None

    settings._state_values = state_values
    settings._assign = assign
    settings._rasai_catalog_plan_persistence = True


def _install_aligned_rows() -> None:
    from rasai import console_configuration_presentation as presentation
    from rasai.console_ui_catalog import configuration_id, origin_for

    current = presentation.format_configuration_row
    if getattr(current, "_rasai_catalog_aligned_rows", False):
        return

    def format_configuration_row(
        state: Any,
        spec: Any,
        *,
        prefix: str | None = None,
        tail: str = "",
    ) -> str:
        row_prefix = prefix if prefix is not None else configuration_id(spec.name)
        label = _fit_cell(presentation.friendly_label(spec), _LABEL_WIDTH)
        value = _fit_cell(presentation.friendly_value(spec), _VALUE_WIDTH)
        value_cell = paint(
            f"{value:<{_VALUE_WIDTH}}",
            presentation._value_color(spec),  # noqa: SLF001 - presentation owner
            bold=value != "NÃO CONFIGURADO",
        )
        cleaned_tail = presentation._ORIGIN_PATTERN.sub("", str(tail)).strip()  # noqa: SLF001
        suffix = f" {cleaned_tail}" if cleaned_tail else ""
        return (
            f"{row_prefix:<10} {label:<{_LABEL_WIDTH}} {value_cell} "
            f"[{origin_for(state, spec)}]{suffix}"
        )

    format_configuration_row._rasai_catalog_aligned_rows = True  # type: ignore[attr-defined]
    format_configuration_row._rasai_original = current  # type: ignore[attr-defined]
    presentation.format_configuration_row = format_configuration_row


def _install_functional_groups() -> None:
    from rasai import console_configuration_context_presentation as context

    current = context._functional_group
    if getattr(current, "_rasai_catalog_source_groups", False):
        return

    def functional_group(spec: Any) -> tuple[str, str | None]:
        name = str(getattr(spec, "name", "") or "").upper()
        if name.startswith("RASAI_CRUX_HISTORY_"):
            return "CrUX History — experiência real histórica", None
        if name.startswith("RASAI_CLARITY_"):
            return "Microsoft Clarity — comportamento real", None
        if name.startswith("RASAI_COMMON_CRAWL_"):
            return "Common Crawl — histórico público", None
        if "DYNATRACE" in name:
            return "Dynatrace — calibração/importação opcional", None
        return current(spec)

    functional_group._rasai_catalog_source_groups = True  # type: ignore[attr-defined]
    functional_group._rasai_original = current  # type: ignore[attr-defined]
    context._functional_group = functional_group


def _source_rank(catalog_id: str, major: str, first_position: int) -> tuple[int, int]:
    if catalog_id == "CAT-05":
        ordered = (
            "SERP — resultados públicos por termo",
            "Google Search Console — dados da property autenticada",
            "CrUX History — experiência real histórica",
            "Microsoft Clarity — comportamento real",
            "Common Crawl — histórico público",
        )
        for index, label in enumerate(ordered):
            if major == label:
                return index, first_position
        return len(ordered), first_position
    if catalog_id == "CAT-07" and major.startswith("Dynatrace"):
        return 999, first_position
    return 0, first_position


def sort_related_specs(catalog_id: str, rows: tuple[Any, ...]) -> tuple[Any, ...]:
    """Group related rows by functional owner while preserving a stable source order."""
    from rasai import console_configuration_context_presentation as context
    from rasai import console_configuration_presentation as presentation

    rows = tuple(rows)
    first: dict[str, int] = {}
    for index, spec in enumerate(rows):
        major, _ = context._functional_group(spec)
        first.setdefault(major, index)

    return tuple(
        sorted(
            rows,
            key=lambda spec: (
                *_source_rank(
                    catalog_id,
                    context._functional_group(spec)[0],
                    first[context._functional_group(spec)[0]],
                ),
                (context._functional_group(spec)[1] or "").casefold(),
                presentation.friendly_label(spec).casefold(),
                str(spec.name).casefold(),
            ),
        )
    )


def _install_related_ordering() -> None:
    from rasai import console_catalog_ui as catalog_ui

    current = catalog_ui._related_specs
    if getattr(current, "_rasai_catalog_grouped_order", False):
        return

    def related_specs(catalog: Any) -> tuple[Any, ...]:
        rows = tuple(current(catalog))
        return sort_related_specs(str(getattr(catalog, "id", "")), rows)

    related_specs._rasai_catalog_grouped_order = True  # type: ignore[attr-defined]
    related_specs._rasai_original = current  # type: ignore[attr-defined]
    catalog_ui._related_specs = related_specs


def _install_catalog_copy() -> None:
    from rasai import console_catalog_ui as catalog_ui

    current = catalog_ui.catalog_menu
    if getattr(current, "_rasai_catalog_configuration_copy", False):
        return

    def catalog_menu(console_module: ModuleType, state: Any, catalog: Any) -> None:
        catalog_id = str(getattr(catalog, "id", ""))
        previous_print = builtins.print

        def refined_print(*args: Any, **kwargs: Any) -> None:
            if len(args) == 1 and isinstance(args[0], str):
                raw = args[0]
                plain = _plain(raw).strip()
                if plain == "1. Configurar parâmetros próprios deste catálogo":
                    labels = {
                        "CAT-05": "1. Configurar O QUE PESQUISAR (termos, localidade, profundidade, dispositivo e concorrentes)",
                        "CAT-06": "1. Configurar parâmetros do Apdex de navegação",
                        "CAT-07": "1. Configurar parâmetros do Apdex de experiência",
                    }
                    previous_print(labels.get(catalog_id, raw), **kwargs)
                    return
                if catalog_id == "CAT-05" and plain == "[ CONFIGURAÇÕES RELACIONADAS ]":
                    previous_print(raw, **kwargs)
                    previous_print(
                        paint(
                            "A ação 1 edita O QUE PESQUISAR. Os IDs abaixo editam configuração reutilizável de cada fonte/serviço.",
                            DIM,
                        )
                    )
                    return
                if plain.startswith("Variáveis editáveis usam sessão ou arquivo"):
                    previous_print(
                        "Configurações não sensíveis deste catálogo podem ser salvas no rasai-console.ini; secrets usam Windows/User e nunca entram no INI.",
                        **kwargs,
                    )
                    return
                if plain.startswith("A seleção CAT-* pertence somente"):
                    previous_print(
                        "A seleção CAT-* também é salva no INI ao usar Salvar configuração; o snapshot do AUD congela o plano efetivamente executado.",
                        **kwargs,
                    )
                    return
            previous_print(*args, **kwargs)

        builtins.print = refined_print
        try:
            return current(console_module, state, catalog)
        finally:
            builtins.print = previous_print

    catalog_menu._rasai_catalog_configuration_copy = True  # type: ignore[attr-defined]
    catalog_menu._rasai_original = current  # type: ignore[attr-defined]
    catalog_ui.catalog_menu = catalog_menu

    try:
        from rasai import console_catalog_workflow as workflow

        workflow.catalog_menu = catalog_menu
        workflow._catalog_menu = catalog_menu
    except ImportError:
        pass


def install() -> None:
    """Install after the existing catalog/search/context presentation layers."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_catalog_ini_persistence()
    _install_aligned_rows()
    _install_functional_groups()
    _install_related_ordering()
    _install_catalog_copy()
    _INSTALLED = True
