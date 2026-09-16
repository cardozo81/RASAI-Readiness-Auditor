"""Presentation-only grouping for Search Intelligence and Google Search Console settings.

The runtime contracts for SERP and GSC are independent.  This module makes that
independence visible to the operator without changing validation, persistence, provider
selection, request budgets, OAuth behavior or audit execution.
"""
from __future__ import annotations

import builtins
import re
from dataclasses import replace
from typing import Any

from rasai.console_ui import CYAN, DIM, paint

_INSTALLED = False
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_ROW_RE = re.compile(r"^\s*(\d{8})\s{2,}")

GSC_CONFIGURATION_NAMES = frozenset(
    {
        "RASAI_GSC_ENABLED",
        "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN",
        "RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID",
        "RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET",
        "RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN",
        "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL",
        "RASAI_GSC_SEARCH_ANALYTICS_DAYS",
        "RASAI_GSC_SEARCH_MAX_ROWS",
        "RASAI_GSC_FINAL_DATA_LAG_DAYS",
    }
)

_GSC_SUBGROUPS = {
    "RASAI_GSC_ENABLED": (0, "Ativação"),
    "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN": (1, "OAuth temporário — teste/uso pontual"),
    "RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID": (2, "OAuth durável — recomendado"),
    "RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_SECRET": (2, "OAuth durável — recomendado"),
    "RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN": (2, "OAuth durável — recomendado"),
    "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL": (3, "Property e cobertura da URL auditada"),
    "RASAI_GSC_SEARCH_ANALYTICS_DAYS": (4, "Search Analytics — janela e volume"),
    "RASAI_GSC_SEARCH_MAX_ROWS": (4, "Search Analytics — janela e volume"),
    "RASAI_GSC_FINAL_DATA_LAG_DAYS": (4, "Search Analytics — janela e volume"),
}

_SERP_SUBGROUPS = {
    "RASAI_SERP_MODE": (0, "Ativação e modo de coleta"),
    "RASAI_SERP_PROVIDER": (1, "Provider e credencial"),
    "RASAI_SERP_FIXTURE_PATH": (5, "Fixture / teste offline"),
    "RASAI_SERP_MAX_QUERIES": (2, "Escopo e limites de coleta"),
    "RASAI_SERP_MAX_REQUESTS": (2, "Escopo e limites de coleta"),
    "RASAI_SERP_MAX_DEPTH": (2, "Escopo e limites de coleta"),
    "RASAI_SERP_MAX_COMPETITORS": (2, "Escopo e limites de coleta"),
    "RASAI_SERP_TIMEOUT_SECONDS": (3, "Rede, retries e ritmo"),
    "RASAI_SERP_RETRIES": (3, "Rede, retries e ritmo"),
    "RASAI_SERP_MIN_INTERVAL_SECONDS": (3, "Rede, retries e ritmo"),
}

_LABELS = {
    "RASAI_GSC_ENABLED": "Uso do Google Search Console",
    "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN": "Token OAuth temporário — Google Search Console",
    "RASAI_GSC_SEARCH_ANALYTICS_DAYS": "Janela de Search Analytics",
    "RASAI_GSC_SEARCH_MAX_ROWS": "Máximo de linhas do Search Analytics",
    "RASAI_GSC_FINAL_DATA_LAG_DAYS": "Defasagem para dados finalizados",
    "RASAI_SERP_FIXTURE_PATH": "Arquivo fixture de SERP",
    "RASAI_SERP_MAX_COMPETITORS": "Máximo de concorrentes observados",
    "RASAI_SERP_MIN_INTERVAL_SECONDS": "Intervalo mínimo entre requests SERP",
}


def _plain(value: object) -> str:
    return _ANSI_RE.sub("", str(value))


def _is_gsc(name: str) -> bool:
    normalized = str(name).upper()
    return normalized.startswith("RASAI_GSC_") or normalized.startswith(
        "RASAI_GOOGLE_SEARCH_CONSOLE_"
    )


def _is_serp(name: str) -> bool:
    normalized = str(name).upper()
    if normalized.startswith("RASAI_SERP"):
        return True
    try:
        from rasai.search_intelligence.provider_catalog import serp_provider_key_envs

        return normalized in {item.upper() for item in serp_provider_key_envs()}
    except ImportError:
        return normalized in {
            "RASAI_ZENSERP_API_KEY",
            "RASAI_SCRAPINGDOG_API_KEY",
        }


def context_label_for_name(name: str) -> str | None:
    """Return the operator-facing subgroup for one Search/GSC configuration key."""
    normalized = str(name).upper()
    if _is_gsc(normalized):
        return "Google Search Console / " + _GSC_SUBGROUPS.get(
            normalized, (9, "Outras opções")
        )[1]
    if _is_serp(normalized):
        if normalized.endswith("_API_KEY"):
            return "SERP / Provider e credencial"
        return "SERP / " + _SERP_SUBGROUPS.get(
            normalized, (9, "Outras opções")
        )[1]
    return None


def _group(spec: Any) -> tuple[int, int, str, str]:
    name = str(spec.name).upper()
    if _is_serp(name):
        order, subgroup = (
            (1, "Provider e credencial")
            if name.endswith("_API_KEY")
            else _SERP_SUBGROUPS.get(name, (9, "Outras opções"))
        )
        return 0, order, "SERP — resultados públicos por termo", subgroup
    if _is_gsc(name):
        order, subgroup = _GSC_SUBGROUPS.get(name, (9, "Outras opções"))
        return 1, order, "GOOGLE SEARCH CONSOLE — dados da property autenticada", subgroup
    try:
        from rasai.console_configuration_guidance import context_for

        context = str(context_for(spec))
    except (ImportError, AttributeError):
        context = str(getattr(spec, "category", "Outras configurações"))
    return 2, 0, "OUTRAS FONTES DO CAT-05", context


def _install_context_grouping() -> None:
    from rasai import console_configuration_guidance as guidance
    from rasai import console_provider_environment as facade

    original = guidance.context_for
    if getattr(original, "_rasai_search_context_groups", False):
        return

    def context_for(spec: Any) -> str:
        label = context_label_for_name(str(spec.name))
        return label or original(spec)

    context_for._rasai_search_context_groups = True  # type: ignore[attr-defined]
    context_for._rasai_original = original  # type: ignore[attr-defined]
    guidance.context_for = context_for
    # The provider facade imports context_for by value.
    facade.context_for = context_for

    original_normalize = guidance.normalize_spec

    def normalize_spec(spec: Any):
        normalized = original_normalize(spec)
        if str(normalized.name) != "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN":
            return normalized
        return replace(
            normalized,
            purpose=(
                "Token OAuth temporário para chamadas ao Google Search Console; é uma "
                "alternativa pontual ao fluxo durável com Client ID + Client Secret + Refresh Token."
            ),
            required_when=(
                "Use este token OU o fluxo OAuth durável. Não é necessário quando Client ID, "
                "Client Secret e Refresh Token estão configurados."
            ),
            impact=(
                "Credencial sensível e temporária; nunca entra no INI. Para uso repetido, "
                "prefira o fluxo OAuth durável."
            ),
        )

    normalize_spec._rasai_search_context_groups = True  # type: ignore[attr-defined]
    normalize_spec._rasai_original = original_normalize  # type: ignore[attr-defined]
    guidance.normalize_spec = normalize_spec
    guidance.normalize_specs = lambda specs: tuple(normalize_spec(spec) for spec in specs)
    # The facade also imported these helpers by value.
    facade.normalize_spec = normalize_spec
    facade.normalize_specs = guidance.normalize_specs
    facade.refresh_specs()


def _install_friendly_labels() -> None:
    try:
        from rasai import console_configuration_presentation as presentation
    except ImportError:
        return
    presentation._LABEL_OVERRIDES.update(_LABELS)


def _install_catalog_grouping() -> None:
    from rasai import console_catalog_ui as catalog_ui
    from rasai.console_configuration_presentation import friendly_label
    from rasai.console_ui_catalog import configuration_id

    original_related = catalog_ui._related_specs
    if getattr(original_related, "_rasai_search_context_groups", False):
        return

    def related_specs(catalog: Any) -> tuple[Any, ...]:
        rows = tuple(original_related(catalog))
        if str(getattr(catalog, "id", "")) != "CAT-05":
            return rows
        return tuple(
            sorted(
                rows,
                key=lambda spec: (
                    _group(spec)[0],
                    _group(spec)[1],
                    friendly_label(spec).casefold(),
                    str(spec.name).casefold(),
                ),
            )
        )

    related_specs._rasai_search_context_groups = True  # type: ignore[attr-defined]
    related_specs._rasai_original = original_related  # type: ignore[attr-defined]
    catalog_ui._related_specs = related_specs

    original_menu = catalog_ui.catalog_menu
    if getattr(original_menu, "_rasai_search_context_groups", False):
        return

    def catalog_menu(console_module: Any, state: Any, catalog: Any) -> None:
        if str(getattr(catalog, "id", "")) != "CAT-05":
            return original_menu(console_module, state, catalog)

        specs = related_specs(catalog)
        groups = {
            configuration_id(spec.name): _group(spec)
            for spec in specs
        }
        previous_print = builtins.print
        in_related = False
        last_major: str | None = None
        last_subgroup: str | None = None

        def grouped_print(*args: Any, **kwargs: Any) -> None:
            nonlocal in_related, last_major, last_subgroup
            if len(args) == 1 and isinstance(args[0], str):
                raw = args[0]
                plain = _plain(raw).strip()
                if plain == "[ CONFIGURAÇÃO EFETIVA ]":
                    raw = raw.replace("CONFIGURAÇÃO EFETIVA", "ESCOPO DESTA EXECUÇÃO")
                    previous_print(raw, **kwargs)
                    previous_print(
                        paint(
                            "Termos, região, profundidade e device SERP pertencem ao pedido desta próxima execução; configurações de serviço ficam separadas abaixo.",
                            DIM,
                        )
                    )
                    return
                if plain == "[ CONFIGURAÇÕES RELACIONADAS ]":
                    in_related = True
                    last_major = None
                    last_subgroup = None
                    previous_print(raw, **kwargs)
                    previous_print(
                        paint(
                            "SERP e Google Search Console são fontes independentes: configurar uma não configura nem autentica a outra.",
                            DIM,
                        )
                    )
                    previous_print(
                        paint(
                            "No GSC, escolha uma forma de OAuth: token temporário OU fluxo durável (Client ID + Client Secret + Refresh Token).",
                            DIM,
                        )
                    )
                    return
                if in_related and plain == "[ PERSISTÊNCIA ]":
                    in_related = False
                    last_major = None
                    last_subgroup = None
                    previous_print(raw, **kwargs)
                    return
                if in_related:
                    match = _ROW_RE.match(plain)
                    if match and match.group(1) in groups:
                        _major_order, _sub_order, major, subgroup = groups[match.group(1)]
                        if major != last_major:
                            previous_print("\n" + paint(f"  {major}", CYAN, bold=True))
                            last_major = major
                            last_subgroup = None
                        if subgroup != last_subgroup:
                            previous_print(paint(f"    {subgroup}", DIM))
                            last_subgroup = subgroup
            previous_print(*args, **kwargs)

        builtins.print = grouped_print
        try:
            return original_menu(console_module, state, catalog)
        finally:
            builtins.print = previous_print

    catalog_menu._rasai_search_context_groups = True  # type: ignore[attr-defined]
    catalog_menu._rasai_original = original_menu  # type: ignore[attr-defined]
    catalog_ui.catalog_menu = catalog_menu

    # Keep already-imported compatibility aliases aligned with the public owner.
    try:
        from rasai import console_catalog_workflow as workflow

        workflow.catalog_menu = catalog_menu
        workflow._catalog_menu = catalog_menu
    except ImportError:
        pass


def install() -> None:
    """Install the final Search/GSC information architecture."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_context_grouping()
    _install_friendly_labels()
    _install_catalog_grouping()
    _INSTALLED = True
