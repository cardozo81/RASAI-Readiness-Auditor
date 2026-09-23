"""User-facing presentation for console configuration variables.

Presentation only: runtime/configuration keys remain unchanged. Normal console views use
stable numeric IDs, human labels, effective values and origins. The technical identifier
is kept visible as secondary reference without becoming the primary operator label.
"""
from __future__ import annotations

from rasai.configuration_value_labels import configuration_value_info
from rasai.console_input_contract import EditCancelled, prompt_secret, prompt_text

import builtins
from contextlib import contextmanager
from rasai.console_secret_input import masked_secret_input as getpass
import os
import re
from types import ModuleType
from typing import Any, Callable, Iterator

from rasai.console_ui import CYAN, DIM, GRAY, GREEN, RED, paint

_OUTPUT_DEPTH = 0
_TECHNICAL_DEPTH = 0

_LABEL_OVERRIDES = {
    "RASAI_APDEX_ACQUISITION_MODE": "Modo de aquisição do Apdex",
    "RASAI_APDEX_CONCURRENCY": "Navegações simultâneas",
    "RASAI_APDEX_DELAY_SECONDS": "Intervalo entre amostras",
    "RASAI_APDEX_DESKTOP_CLIENT_PROFILE": "Perfil de cliente Desktop",
    "RASAI_APDEX_DESKTOP_HARDWARE_PROFILE": "Perfil de hardware Desktop",
    "RASAI_APDEX_DESKTOP_NETWORK_PROFILE": "Perfil de rede Desktop",
    "RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT": "Máximo de tentativas por contexto",
    "RASAI_APDEX_MAX_PAGES": "Máximo de páginas analisadas",
    "RASAI_APDEX_MOBILE_CLIENT_PROFILE": "Perfil de cliente Mobile",
    "RASAI_APDEX_MOBILE_HARDWARE_PROFILE": "Perfil de hardware Mobile",
    "RASAI_APDEX_MOBILE_NETWORK_PROFILE": "Perfil de rede Mobile",
    "RASAI_APDEX_SAMPLES_PER_CONTEXT": "Amostras por contexto",
    "RASAI_APDEX_TABLET_CLIENT_PROFILE": "Perfil de cliente Tablet",
    "RASAI_APDEX_TABLET_HARDWARE_PROFILE": "Perfil de hardware Tablet",
    "RASAI_APDEX_TABLET_NETWORK_PROFILE": "Perfil de rede Tablet",
    "RASAI_APDEX_THRESHOLD_SECONDS": "Limite de experiência satisfatória",
    "RASAI_APDEX_TIMEOUT_SECONDS": "Tempo máximo de espera do Apdex",
    "RASAI_SYNTHETIC_APDEX": "Apdex sintético de navegação",
    "RASAI_WEB_PERFORMANCE": "Coleta de Web Performance",
    "RASAI_WEB_PERFORMANCE_MAX_PAGES": "Máximo de páginas em Web Performance",
    "RASAI_WEB_PERFORMANCE_FIELD_SOURCE": "Fonte de dados de campo",
    "RASAI_LIGHTHOUSE_CATEGORIES": "Categorias do Lighthouse",
    "RASAI_SERP_MODE": "Modo de coleta SERP",
    "RASAI_SERP_PROVIDER": "Provedor de SERP",
    "RASAI_SERP_MAX_DEPTH": "Profundidade máxima de SERP",
    "RASAI_SERP_MAX_QUERIES": "Máximo de termos por execução",
    "RASAI_SERP_MAX_REQUESTS": "Máximo de requisições SERP",
    "RASAI_SERP_RETRIES": "Tentativas adicionais de SERP",
    "RASAI_SERP_TIMEOUT_SECONDS": "Tempo máximo de espera da SERP",
    "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL": "Property do Google Search Console",
    "RASAI_GSC_SITE_URL": "Property do Google Search Console",
    "RASAI_AI_ANALYSIS_LANGUAGE": "Idioma das análises por IA",
    "RASAI_AI_CONTENT_REMEDIATION": "Enriquecimento de remediação de conteúdo por IA",
    "RASAI_AI_TECHNICAL_REMEDIATION": "Enriquecimento de remediação técnica por IA",
    "RASAI_DEVICE_CONTEXT": "Device padrão da auditoria",
    "RASAI_LOG_LEVEL": "Nível de detalhamento dos logs",
    "RASAI_CONSOLE_MODE": "Modo de operação do console",
    "RASAI_CONSOLE_INI": "Arquivo de configuração do console",
}

_VALUE_LABELS = {
    "true": "Habilitado",
    "false": "Desabilitado",
    "auto": "Automático",
    "none": "Nenhum",
    "shared": "Compartilhado",
    "isolated": "Isolado",
    "mobile": "Mobile",
    "desktop": "Desktop",
    "both": "Mobile + Desktop",
    "disabled": "Desabilitado",
    "live": "Ao vivo",
    "fixture": "Fixture local",
}

_LEADING_VERBS = (
    "Habilita ", "Define ", "Controla ", "Seleciona ", "Configura ", "Força ",
    "Limita ", "Informa ", "Aponta ", "Determina ", "Usa ",
)
_ORIGIN_PATTERN = re.compile(
    r"\[(?:ARQUIVO|SESSÃO|DEFAULT|NÃO CONFIGURADO|WINDOWS/[^\]]+|SO:[^\]]+)\]",
    re.IGNORECASE,
)


def _clean_purpose(value: str) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return "Configuração avançada"
    text = text.split(";", 1)[0].rstrip(". ")
    for prefix in _LEADING_VERBS:
        if text.startswith(prefix) and len(text) > len(prefix) + 4:
            text = text[len(prefix):]
            break
    if len(text) > 58:
        text = text[:55].rstrip() + "…"
    return text[:1].upper() + text[1:]


def _provider_label(name: str) -> str:
    tokens = name.upper().removeprefix("RASAI_").split("_")
    known = {
        "OPENAI": "OpenAI", "DEEPSEEK": "DeepSeek", "MIMO": "MiMo", "XAI": "xAI",
        "QWEN": "Qwen", "GEMINI": "Gemini", "ANTHROPIC": "Anthropic",
        "SERPAPI": "SerpApi", "ZENSERP": "Zenserp", "SCRAPINGDOG": "ScrapingDog",
        "PAGESPEED": "PageSpeed", "CRUX": "CrUX", "DYNATRACE": "Dynatrace",
        "CLARITY": "Microsoft Clarity", "GSC": "Google Search Console",
    }
    for token in tokens:
        if token in known:
            return known[token]
    if "GOOGLE_SEARCH_CONSOLE" in name.upper():
        return "Google Search Console"
    return "integração"


def friendly_label(spec: Any) -> str:
    """Return the stable user-facing label for any canonical configuration spec."""
    name = str(getattr(spec, "name", "") or "").strip().upper()
    if name in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[name]
    provider = _provider_label(name)
    if name.endswith("_API_KEY") or name.endswith("_KEY"):
        return f"Chave de API — {provider}"
    if name.endswith("_ACCESS_TOKEN"):
        return f"Token de acesso — {provider}"
    if name.endswith("_REFRESH_TOKEN"):
        return f"Token de renovação — {provider}"
    if name.endswith("_CLIENT_ID"):
        return f"ID do cliente — {provider}"
    if name.endswith("_CLIENT_SECRET") or name.endswith("_SESSION_SECRET"):
        return f"Segredo de autenticação — {provider}"
    if name.endswith("_BASE_URL") or name.endswith("_ENDPOINT"):
        return f"Endpoint — {provider}"
    if name.endswith("_MODEL"):
        return f"Modelo — {provider}"
    if name.endswith("_REASONING"):
        return f"Nível de raciocínio — {provider}"
    return _clean_purpose(str(getattr(spec, "purpose", "") or ""))


def _is_secret(spec: Any) -> bool:
    try:
        from rasai import console_environment as base
        return bool(base._is_sensitive_spec(spec))
    except (ImportError, AttributeError):
        return bool(getattr(spec, "sensitive", False))


def raw_effective_value(spec: Any) -> str | None:
    raw = (os.environ.get(str(spec.name)) or "").strip()
    if raw:
        return raw
    default = getattr(spec, "default", None)
    return None if default is None else str(default).strip()


def friendly_value(spec: Any) -> str:
    """Render the effective value without ever exposing secret material."""
    raw_env = (os.environ.get(str(spec.name)) or "").strip()
    if _is_secret(spec):
        return "CONFIGURADO" if raw_env else "NÃO CONFIGURADO"
    raw = raw_effective_value(spec)
    if raw is None or raw == "":
        return "NÃO CONFIGURADO"
    mapped = _VALUE_LABELS.get(raw.casefold())
    if mapped is not None:
        return mapped
    name = str(spec.name).upper()
    value_type = str(getattr(spec, "value_type", "") or "").casefold()
    if "SECONDS" in name or "segundo" in value_type or name.endswith("_TIMEOUT") or name.endswith("_DELAY"):
        try:
            number = float(raw)
        except ValueError:
            pass
        else:
            return f"{number:g} s"
    return raw


def _value_color(spec: Any) -> str:
    raw = (os.environ.get(str(spec.name)) or "").strip()
    if raw:
        return GREEN
    if getattr(spec, "default", None) is not None:
        return CYAN
    required = str(getattr(spec, "required_when", "") or "").strip().casefold()
    required_now = bool(required and not required.startswith("nunca") and "opcional" not in required)
    return RED if required_now else DIM


def format_configuration_row(state: Any, spec: Any, *, prefix: str | None = None, tail: str = "") -> str:
    """Format a public configuration row as ID/label/value/origin."""
    from rasai.console_ui_catalog import configuration_id, origin_for

    row_prefix = prefix if prefix is not None else configuration_id(spec.name)
    label = friendly_label(spec)
    value = friendly_value(spec)
    if len(value) > 22:
        value = value[:19].rstrip() + "…"
    value_cell = paint(f"{value:<22}", _value_color(spec), bold=value != "NÃO CONFIGURADO")
    cleaned_tail = _ORIGIN_PATTERN.sub("", str(tail)).strip()
    suffix = f" {cleaned_tail}" if cleaned_tail else ""
    return (
        f"{row_prefix:<10} {label:<46} {value_cell} [{origin_for(state, spec)}]{suffix}"
        + "\n"
        + paint(f"{'':<10} Variável técnica: {spec.name}", GRAY)
    )


def _spec_map() -> tuple[dict[str, Any], tuple[str, ...]]:
    from rasai import console_provider_environment as env
    specs = tuple(env.refresh_specs())
    by_name = {str(spec.name): spec for spec in specs}
    names = tuple(sorted(by_name, key=len, reverse=True))
    return by_name, names


def _rewrite_line(text: str, state: Any, by_name: dict[str, Any], names: tuple[str, ...]) -> str:
    if _TECHNICAL_DEPTH:
        return text
    result = str(text)
    if "Variável técnica:" in result:
        # Technical identifiers are always secondary operator context.
        # Preserve an already-colored line; otherwise enforce the canonical gray.
        return result if "\x1b[" in result else paint(result, GRAY)
    for name in names:
        if name not in result:
            continue
        spec = by_name[name]
        before, after = result.split(name, 1)
        stripped_before = before.strip()
        row_like = bool(re.fullmatch(r"(?:\d+\.)?\s*\d{0,8}", stripped_before)) and "·" not in before
        if row_like:
            return format_configuration_row(state, spec, prefix=stripped_before, tail=after)
        result = before + friendly_label(spec) + after
    return result


@contextmanager
def user_facing_output(state: Any) -> Iterator[None]:
    """Humanize normal console surfaces while preserving secondary technical references."""
    global _OUTPUT_DEPTH
    if _OUTPUT_DEPTH:
        yield
        return
    by_name, names = _spec_map()
    original_print = builtins.print
    original_input = builtins.input

    def friendly_print(*args: Any, **kwargs: Any) -> None:
        rewritten = tuple(_rewrite_line(arg, state, by_name, names) if isinstance(arg, str) else arg for arg in args)
        original_print(*rewritten, **kwargs)

    def friendly_input(prompt: str = "") -> str:
        return original_input(_rewrite_line(prompt, state, by_name, names))

    _OUTPUT_DEPTH += 1
    builtins.print = friendly_print
    builtins.input = friendly_input
    try:
        yield
    finally:
        builtins.print = original_print
        builtins.input = original_input
        _OUTPUT_DEPTH -= 1


@contextmanager
def _technical_output() -> Iterator[None]:
    global _TECHNICAL_DEPTH
    _TECHNICAL_DEPTH += 1
    try:
        yield
    finally:
        _TECHNICAL_DEPTH -= 1


def _technical_details(state: Any, spec: Any) -> None:
    from rasai.console_ui_catalog import configuration_id, info, origin_for, section
    with _technical_output():
        section("DETALHES TÉCNICOS")
        info("ID público", configuration_id(spec.name))
        info("Variável", spec.name)
        if _is_secret(spec):
            raw_display = "CONFIGURADO (oculto)" if (os.environ.get(spec.name) or "").strip() else "NÃO CONFIGURADO"
        else:
            raw_display = raw_effective_value(spec) or "<não configurado>"
        info("Valor bruto", raw_display)
        info("Tipo", getattr(spec, "value_type", "-"))
        info("Default", getattr(spec, "default", None) if getattr(spec, "default", None) is not None else "<sem default>")
        info("Origem efetiva", origin_for(state, spec))
        info("Categoria", getattr(spec, "category", "-"))
        info("Fonte", getattr(spec, "source", "-"))
    input("ENTER para voltar...")


def variable_editor(console_module: ModuleType, state: Any, spec: Any) -> None:
    """Edit one configuration using human terminology; technical key is opt-in only."""
    from rasai import console_provider_environment as env
    from rasai.console_configuration_guidance import context_for, prompt_guided_value, render_enrichment
    from rasai.console_ui_catalog import _apply, _destination, configuration_id, info, origin_for, owner_for, section

    while True:
        spec = env.normalize_spec(spec)
        env.base_environment.render_header(state)
        print(paint(f"CONFIGURAÇÃO > {owner_for(spec)}", CYAN, bold=True))
        print(paint(f"\n{configuration_id(spec.name)} · {friendly_label(spec)}", CYAN, bold=True))
        print(paint(f"Variável técnica: {spec.name}", GRAY))
        section("INFORMAÇÃO")
        info("Para que serve", spec.purpose)
        info("Contexto", context_for(spec))
        info("Necessário quando", spec.required_when)
        info("Impacto", spec.impact)
        if spec.notes:
            info("Observação", spec.notes)
        section("ESTADO ATUAL")
        info("Valor efetivo", friendly_value(spec))
        info("Origem", origin_for(state, spec))
        info("Estado", env.decision_badge(spec))
        section("COMO PREENCHER")
        if spec.accepted:
            info("Opções aceitas", ", ".join(configuration_value_info(spec.name, value) for value in spec.accepted))
        else:
            info("Formato", spec.value_type)
        if getattr(spec, "example", ""):
            info("Exemplo", spec.example)
        render_enrichment(spec)
        secret = _is_secret(spec)
        from rasai.console_ui_catalog import section as ui_section
        ui_section("AÇÕES")
        print("S. Definir / alterar")
        print("L. Limpar override somente desta sessão")
        print("R. Restaurar estado canônico")
        if secret:
            print("P. Gerenciar persistência Windows/User")
        print("T. Detalhes técnicos")
        print("D. Documentação")
        print("V. Voltar")
        action = input("Escolha: ").strip().upper()
        if action == "V":
            return
        if action == "T":
            _technical_details(state, spec)
            continue
        if action == "D":
            env.base_environment._open_docs(state)
            continue
        if action == "P" and secret:
            try:
                env.base_environment._persist_secret(state, spec)
            except (OSError, ValueError) as exc:
                state.error = f"falha de persistência: {type(exc).__name__}: {exc}"
            continue
        if action in {"L", "R"}:
            _apply(state, spec, None)
            state.error = ""
            state.operation = "LOCAL:CONFIG_RESTORED" if action == "R" else "LOCAL:CONFIG_OVERRIDE_CLEARED"
            if action == "R" and not secret:
                console_module._save_configuration(state)
            continue
        if action != "S":
            state.error = "ação inválida"
            continue
        try:
            if spec.accepted:
                raw = prompt_guided_value(spec)
                if raw is None:
                    continue
            elif secret:
                raw = prompt_secret(
                    f"Novo valor - {friendly_label(spec)}",
                    input_fn=getpass,
                )
            else:
                raw = prompt_text(
                    f"Novo valor - {friendly_label(spec)}",
                    current=raw_effective_value(spec) or "",
                    empty_keeps_current=False,
                )
            validated = env._validate(spec.name, raw)
        except EditCancelled:
            state.error = ""
            state.operation = "LOCAL:CONFIG_EDIT_CANCELLED"
            continue
        except (ValueError, OverflowError) as exc:
            state.error = str(exc)
            continue
        section("ALTERAÇÃO")
        info("Configuração", friendly_label(spec))
        print(paint(f"{'Variável técnica':<20}: {spec.name}", GRAY))
        info(
            "Novo valor",
            "CONFIGURADO (oculto)" if secret else configuration_value_info(spec.name, validated),
        )
        destination = _destination(secret)
        if destination == "V":
            continue
        try:
            _apply(state, spec, validated)
            state.error = ""
            state.operation = "LOCAL:CONFIG_UPDATED"
            if destination == "2":
                env.base_environment._persist_secret(state, spec) if secret else console_module._save_configuration(state)
        except (OSError, ValueError, OverflowError) as exc:
            state.error = str(exc)


def _wrap_surface(fn: Callable[..., Any]) -> Callable[..., Any]:
    if bool(getattr(fn, "_rasai_friendly_configuration_surface", False)):
        return fn

    def wrapped(state: Any, *args: Any, **kwargs: Any):
        with user_facing_output(state):
            return fn(state, *args, **kwargs)

    wrapped._rasai_friendly_configuration_surface = True  # type: ignore[attr-defined]
    wrapped._rasai_original = fn  # type: ignore[attr-defined]
    return wrapped


def install(console_module: ModuleType) -> None:
    """Install presentation wrappers without changing configuration/runtime semantics."""
    if getattr(console_module, "_rasai_friendly_configuration_labels", False):
        return

    from rasai import console_catalog_ui
    from rasai import console_ui_catalog as ui_catalog
    from rasai import console_ui_refactor as refactor
    from rasai import console_navigation as navigation

    ui_catalog.variable_editor = variable_editor
    refactor.variable_editor = variable_editor
    console_catalog_ui.variable_editor = variable_editor

    console_module._environment_menu = _wrap_surface(console_module._environment_menu)
    console_module._configure = _wrap_surface(console_module._configure)
    navigation._preparation_menu = _wrap_surface(navigation._preparation_menu)

    console_module._rasai_friendly_configuration_labels = True
