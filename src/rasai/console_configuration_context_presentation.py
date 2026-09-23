"""Final functional grouping and label disambiguation for console configuration lists.

Presentation-only contract:
- no normal operator surface may show two indistinguishable labels in the same list;
- generic registry metadata is converted into a human label derived from the setting purpose;
- configuration rows are grouped by functional context (SERP, GSC, CrUX, PageSpeed,
  Apdex, IA, browser, reports, platform, and so on) instead of one flat mixed list;
- technical environment-variable names remain visible as secondary references while the
  humanized label stays primary; they are never used as the main operator label.

Runtime keys, validation, persistence, scoring and execution semantics are untouched.
"""
from __future__ import annotations

import builtins
from collections import Counter
from contextlib import contextmanager
import re
from types import ModuleType
from typing import Any, Iterator

from rasai.console_ui import CYAN, DIM, paint

_INSTALLED = False
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_ROW_RE = re.compile(r"^\s*(\d{8})\s{2,}")
_GENERIC_LABEL_PREFIXES = (
    "variável reconhecida pelo rasai",
    "configuração avançada",
)

_REDUNDANT_SEARCH_HEADINGS = {
    "SERP — resultados públicos por termo",
    "GOOGLE SEARCH CONSOLE — dados da property autenticada",
    "OUTRAS FONTES DO CAT-05",
    "Ativação e modo de coleta",
    "Provider e credencial",
    "Escopo e limites de coleta",
    "Rede, retries e ritmo",
    "Fixture / teste offline",
    "Ativação",
    "OAuth temporário — teste/uso pontual",
    "OAuth durável — recomendado",
    "Property e cobertura da URL auditada",
    "Search Analytics — janela e volume",
}

_TOKEN_WORDS = {
    "AI": "IA",
    "API": "API",
    "APDEX": "Apdex",
    "AUD": "auditoria",
    "AUDIT": "auditoria",
    "BROWSER": "navegador",
    "CLIENT": "cliente",
    "CONFIG": "configuração",
    "CONSOLE": "console",
    "CONTENT": "conteúdo",
    "CRUX": "CrUX",
    "DATA": "dados",
    "DEVICE": "dispositivo",
    "EXPERIENCE": "experiência",
    "GSC": "GSC",
    "HTML": "HTML",
    "HTTP": "HTTP",
    "LANGUAGE": "idioma",
    "LIGHTHOUSE": "Lighthouse",
    "LOG": "logs",
    "MARKET": "mercado",
    "MOBILE": "Mobile",
    "NAVIGATION": "navegação",
    "NETWORK": "rede",
    "PAGE": "página",
    "PAGES": "páginas",
    "PAGESPEED": "PageSpeed",
    "PLAYWRIGHT": "Playwright",
    "PROVIDER": "provider",
    "REMOTE": "remoto",
    "REPORT": "relatório",
    "REPORTS": "relatórios",
    "SEARCH": "Search",
    "SERP": "SERP",
    "STORAGE": "armazenamento",
    "TABLET": "Tablet",
    "TIMEZONE": "fuso horário",
    "URL": "URL",
    "WEB": "Web",
    "WINDOWS": "Windows",
    "YMYL": "YMYL",
}


def _plain(value: object) -> str:
    return _ANSI_RE.sub("", str(value))


def _subject(tokens: list[str]) -> str:
    words = [_TOKEN_WORDS.get(token, token.replace("_", " ").lower()) for token in tokens]
    value = " ".join(word for word in words if word).strip()
    return value[:1].upper() + value[1:] if value else "Configuração"


def _humanize_name(name: str) -> str:
    """Create a human fallback without exposing the raw environment-variable key."""
    normalized = str(name or "").strip().upper()
    tokens = normalized.removeprefix("RASAI_").split("_")

    suffixes: tuple[tuple[tuple[str, ...], str], ...] = (
        (("TIMEOUT", "SECONDS"), "Tempo máximo de espera"),
        (("DELAY", "SECONDS"), "Intervalo entre operações"),
        (("MIN", "INTERVAL", "SECONDS"), "Intervalo mínimo entre operações"),
        (("MAX", "PAGES"), "Máximo de páginas"),
        (("MAX", "ROWS"), "Máximo de linhas"),
        (("MAX", "REQUESTS"), "Máximo de requisições"),
        (("MAX", "QUERIES"), "Máximo de termos"),
        (("MAX", "DEPTH"), "Profundidade máxima"),
        (("MAX", "COMPETITORS"), "Máximo de concorrentes"),
        (("RETRIES",), "Tentativas adicionais"),
        (("ENABLED",), "Uso"),
        (("MODE",), "Modo"),
        (("PROVIDER",), "Provider"),
        (("MODEL",), "Modelo"),
        (("PATH",), "Arquivo ou caminho"),
        (("DIR",), "Diretório"),
        (("URL",), "URL"),
    )
    for suffix, label in suffixes:
        if len(tokens) >= len(suffix) and tuple(tokens[-len(suffix):]) == suffix:
            subject = _subject(tokens[:-len(suffix)])
            return f"{label} — {subject}" if subject != "Configuração" else label

    return _subject(tokens)


def _functional_group(spec: Any) -> tuple[str, str | None]:
    """Return a stable functional major/subgroup for one setting."""
    from rasai.console_configuration_guidance import context_for

    name = str(getattr(spec, "name", "") or "").upper()
    context = str(context_for(spec) or "").strip()

    if context.startswith("SERP / "):
        return "SERP — resultados públicos por termo", context.split(" / ", 1)[1]
    if context.startswith("Google Search Console / "):
        return "Google Search Console — dados da property autenticada", context.split(" / ", 1)[1]
    if "CRUX" in name or "Chrome UX Report" in context:
        return "Chrome UX Report (CrUX) — experiência real de usuários", None
    if "PAGESPEED" in name or "LIGHTHOUSE" in name or context == "Google PageSpeed / Lighthouse":
        return "PageSpeed / Lighthouse — laboratório e performance", None
    if name.startswith("RASAI_APDEX_EXPERIENCE"):
        return "Apdex de experiência", None
    if name.startswith("RASAI_APDEX_") or name == "RASAI_SYNTHETIC_APDEX":
        return "Apdex de navegação", None
    if name.startswith("RASAI_WEB_FEATURES") or any(token in name for token in ("W3C", "MDN", "WEB_PLATFORM")):
        return "Padrões e recursos da Web", None
    if name.startswith("RASAI_BROWSER_") or name.startswith("RASAI_PLAYWRIGHT_"):
        return "Navegador / Playwright", None
    if name.startswith("RASAI_REPORT_") or name.startswith("RASAI_HTML_"):
        return "Relatórios e apresentação", None
    if name.startswith("RASAI_LOG_"):
        return "Logs e diagnóstico", None
    if name.startswith("RASAI_CONSOLE_") or name == "RASAI_CONFIG":
        return "Console e configuração local", None
    if name.startswith("RASAI_PLATFORM_") or name.startswith("RASAI_REMOTE_"):
        return "Plataforma / control plane", None
    if name.startswith("RASAI_OIDC_") or name.startswith("RASAI_API_AUTH_"):
        return "Identidade e autenticação", None
    if name.startswith("RASAI_CONTENT_") or name.startswith("RASAI_YMYL_"):
        return "Conteúdo, semântica e YMYL", None
    if name.startswith("RASAI_AI_") or str(getattr(spec, "category", "")).startswith("IA"):
        return "Inteligência Artificial", context if context and context != "Inteligência Artificial" else None

    if context and context not in {"Aplicação e execução", "Outras configurações"}:
        return context, None

    # Generic application/runtime settings still receive a useful namespace instead of
    # falling into one large undifferentiated bucket.
    namespace = next((token for token in name.removeprefix("RASAI_").split("_") if token), "GERAL")
    namespace_label = _TOKEN_WORDS.get(namespace, namespace.title())
    return f"Configuração geral / {namespace_label}", None


def _build_label_map(specs: tuple[Any, ...], original_label: Any) -> dict[str, str]:
    base: dict[str, str] = {}
    for spec in specs:
        name = str(spec.name)
        label = str(original_label(spec) or "").strip()
        if not label or label.casefold().startswith(_GENERIC_LABEL_PREFIXES):
            label = _humanize_name(name)
        base[name] = label

    counts = Counter(value.casefold() for value in base.values())
    result: dict[str, str] = {}
    provisional: dict[str, str] = {}
    for spec in specs:
        name = str(spec.name)
        label = base[name]
        if counts[label.casefold()] == 1:
            provisional[name] = label
            continue
        major, subgroup = _functional_group(spec)
        context = subgroup or major
        provisional[name] = f"{label} — {context}"

    second_counts = Counter(value.casefold() for value in provisional.values())
    for spec in specs:
        name = str(spec.name)
        candidate = provisional[name]
        if second_counts[candidate.casefold()] > 1:
            candidate = f"{base[name]} — {_humanize_name(name)}"
        result[name] = candidate

    # Last-resort deterministic guard. It should rarely trigger, but guarantees that a
    # single screen cannot contain two indistinguishable public labels.
    final_counts = Counter(value.casefold() for value in result.values())
    if any(count > 1 for count in final_counts.values()):
        from rasai.console_ui_catalog import configuration_id

        for name, value in tuple(result.items()):
            if final_counts[value.casefold()] > 1:
                result[name] = f"{value} · ref. {configuration_id(name)}"
    return result


def _install_unique_labels() -> None:
    from rasai import console_configuration_presentation as presentation
    from rasai import console_provider_environment as environment

    current = presentation.friendly_label
    if getattr(current, "_rasai_context_unique_labels", False):
        return
    specs = tuple(environment.refresh_specs())
    labels = _build_label_map(specs, current)

    def friendly_label(spec: Any) -> str:
        name = str(getattr(spec, "name", "") or "")
        if name in labels:
            return labels[name]
        label = str(current(spec) or "").strip()
        if not label or label.casefold().startswith(_GENERIC_LABEL_PREFIXES):
            return _humanize_name(name)
        return label

    friendly_label._rasai_context_unique_labels = True  # type: ignore[attr-defined]
    friendly_label._rasai_original = current  # type: ignore[attr-defined]
    presentation.friendly_label = friendly_label


def _status_for(spec: Any) -> str:
    import os
    from rasai.console_ui_catalog import is_pending

    if is_pending(spec):
        return "CONFIGURAR"
    if (os.environ.get(str(spec.name)) or "").strip() or getattr(spec, "default", None) is not None:
        return "APTO"
    return "OPCIONAL"


def _install_all_configuration_rows() -> None:
    from rasai import console_configuration_presentation as presentation
    from rasai import console_ui_catalog as catalog

    if getattr(catalog._rows, "_rasai_functional_context_rows", False):
        return

    def rows(state: Any, rows_value: tuple[Any, ...], grouped: bool) -> None:
        rows_tuple = tuple(rows_value)
        if grouped:
            rows_tuple = tuple(
                sorted(
                    rows_tuple,
                    key=lambda spec: (
                        _functional_group(spec)[0].casefold(),
                        (_functional_group(spec)[1] or "").casefold(),
                        presentation.friendly_label(spec).casefold(),
                    ),
                )
            )

        last_major: str | None = None
        last_subgroup: str | None = None
        for spec in rows_tuple:
            if grouped:
                major, subgroup = _functional_group(spec)
                if major != last_major:
                    print("\n" + paint(f"[ {major} ]", CYAN, bold=True))
                    last_major = major
                    last_subgroup = None
                if subgroup and subgroup != last_subgroup:
                    print(paint(f"  {subgroup}", DIM))
                    last_subgroup = subgroup
            print(
                presentation.format_configuration_row(
                    state,
                    spec,
                    tail=catalog.badge(_status_for(spec)),
                )
            )

    rows._rasai_functional_context_rows = True  # type: ignore[attr-defined]
    rows._rasai_original = catalog._rows  # type: ignore[attr-defined]
    catalog._rows = rows


@contextmanager
def _grouped_context_rows(state: Any, specs: tuple[Any, ...]) -> Iterator[None]:
    """Insert functional headings around contextual catalog/capability variable lists."""
    from rasai.console_ui_catalog import configuration_id

    id_to_spec = {configuration_id(spec.name): spec for spec in specs}
    if not id_to_spec:
        yield
        return

    original_print = builtins.print
    last_major: str | None = None
    last_subgroup: str | None = None

    def grouped_print(*args: Any, **kwargs: Any) -> None:
        nonlocal last_major, last_subgroup
        if len(args) == 1 and isinstance(args[0], str):
            raw = args[0]
            plain = _plain(raw).strip()
            if plain in _REDUNDANT_SEARCH_HEADINGS:
                return
            if plain.startswith("[") and plain.endswith("]"):
                last_major = None
                last_subgroup = None
            match = _ROW_RE.match(_plain(raw))
            if match and match.group(1) in id_to_spec:
                major, subgroup = _functional_group(id_to_spec[match.group(1)])
                if major != last_major:
                    original_print("\n" + paint(f"  {major}", CYAN, bold=True))
                    last_major = major
                    last_subgroup = None
                if subgroup and subgroup != last_subgroup:
                    original_print(paint(f"    {subgroup}", DIM))
                    last_subgroup = subgroup
        original_print(*args, **kwargs)

    builtins.print = grouped_print
    try:
        yield
    finally:
        builtins.print = original_print


def _install_catalog_context_wrapper() -> None:
    from rasai import console_catalog_ui as catalog_ui

    current = catalog_ui.catalog_menu
    if getattr(current, "_rasai_functional_context_groups", False):
        return

    def catalog_menu(console_module: ModuleType, state: Any, catalog: Any) -> None:
        specs = tuple(catalog_ui._related_specs(catalog))
        with _grouped_context_rows(state, specs):
            return current(console_module, state, catalog)

    catalog_menu._rasai_functional_context_groups = True  # type: ignore[attr-defined]
    catalog_menu._rasai_original = current  # type: ignore[attr-defined]
    catalog_ui.catalog_menu = catalog_menu

    try:
        from rasai import console_catalog_workflow as workflow

        workflow.catalog_menu = catalog_menu
        workflow._catalog_menu = catalog_menu
    except ImportError:
        pass


def _install_capability_context_wrapper() -> None:
    from rasai import console_ui_catalog as catalog

    current = catalog.capability_menu
    if getattr(current, "_rasai_functional_context_groups", False):
        return

    def capability_menu(console_module: ModuleType, state: Any, capability: Any) -> str | None:
        specs = tuple(catalog.capability_specs(capability.key))
        with _grouped_context_rows(state, specs):
            return current(console_module, state, capability)

    capability_menu._rasai_functional_context_groups = True  # type: ignore[attr-defined]
    capability_menu._rasai_original = current  # type: ignore[attr-defined]
    catalog.capability_menu = capability_menu

    try:
        from rasai import console_ui_refactor as refactor

        refactor.capability_menu = capability_menu
    except ImportError:
        pass


def install(console_module: ModuleType | None = None) -> None:
    """Install after all feature-specific console overlays."""
    del console_module
    global _INSTALLED
    if _INSTALLED:
        return
    _install_unique_labels()
    _install_all_configuration_rows()
    _install_catalog_context_wrapper()
    _install_capability_context_wrapper()
    _INSTALLED = True
