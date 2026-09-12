"""Guided configuration UX shared by the interactive environment console.

This module is presentation-only. It never changes runtime defaults, scoring, provider
selection or secret handling. Its role is to make the configuration contract explicit:
closed domains become guided choices, variables are grouped by operational context,
and official references are surfaced next to the value being configured.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
import os
from typing import Callable, Iterable, Sequence

from rasai.console_ui import CYAN, DIM, GREEN, YELLOW, paint
from rasai.provider_registry import get_provider_registration, provider_registrations
from rasai.search_intelligence.provider_catalog import SERP_PROVIDER_REGISTRY
from rasai.standards_service_registry import services

_BOOLEAN_VALUES = ("true", "false")
_OIDC_ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512")
_GSC_DOC_URL = "https://developers.google.com/webmaster-tools/v1/api_reference_index"
_GOOGLE_CREDENTIAL_URL = "https://console.cloud.google.com/apis/credentials"


def _ai_registration_for_env(name: str):
    for registration in provider_registrations():
        if name in {
            registration.key_env,
            registration.model_env,
            registration.endpoint_env,
        } or name == f"RASAI_{registration.provider_name}_REASONING_EFFORT":
            return registration
    return None


def _serp_registrations_for_env(name: str) -> tuple[object, ...]:
    return tuple(item for item in SERP_PROVIDER_REGISTRY if item.key_env == name)


def _service_for_env(name: str):
    for item in services():
        if name == item.enabled_env or name in item.credential_envs or name in item.config_envs:
            return item
    return None


def _improvement_provider_registration():
    provider = (os.environ.get("RASAI_IMPROVEMENT_AI_PROVIDER") or "").strip().casefold()
    return get_provider_registration(provider) if provider else None


def normalize_spec(spec):
    """Complete known/dependent closed domains without changing runtime semantics."""
    accepted = tuple(spec.accepted)
    value_type = str(spec.value_type)
    normalized_type = value_type.casefold()

    if normalized_type == "booleano" and not accepted:
        accepted = _BOOLEAN_VALUES
    elif spec.name == "RASAI_OIDC_ALGORITHMS" and not accepted:
        accepted = _OIDC_ALGORITHMS
    elif spec.name == "RASAI_AI_AUTO_EXCLUDE" and not accepted:
        accepted = tuple(
            registration.id
            for registration in provider_registrations()
            if registration.auto_eligible
        )
        value_type = "lista CSV"
    elif spec.name in {"RASAI_IMPROVEMENT_AI_MODEL", "RASAI_IMPROVEMENT_AI_REASONING"}:
        registration = _improvement_provider_registration()
        if registration is not None:
            if spec.name.endswith("_MODEL"):
                accepted = tuple(registration.supported_models)
            else:
                accepted = tuple(registration.reasoning_values)
            value_type = "enum"

    if accepted != tuple(spec.accepted) or value_type != spec.value_type:
        return replace(spec, accepted=accepted, value_type=value_type)
    return spec


def normalize_specs(specs: Iterable[object]) -> tuple[object, ...]:
    return tuple(normalize_spec(spec) for spec in specs)


def context_for(spec) -> str:
    """Return a user-facing operational context for grouping related variables."""
    name = spec.name
    ai = _ai_registration_for_env(name)
    if ai is not None:
        return f"IA / {ai.display_name}"
    if name.startswith("RASAI_GSC_") or name.startswith("RASAI_GOOGLE_SEARCH_CONSOLE_"):
        return "Google Search Console"
    if name.startswith("RASAI_SERP") or name in {
        "RASAI_ZENSERP_API_KEY",
        "RASAI_SCRAPINGDOG_API_KEY",
        "RASAI_SEARCH_AI_PROVIDER",
    }:
        return "SERP / Search Intelligence"
    if "PAGESPEED" in name or "LIGHTHOUSE" in name:
        return "Google PageSpeed / Lighthouse"
    if "CRUX" in name:
        return "Google Chrome UX Report (CrUX)"
    if name.startswith("RASAI_APDEX_EXPERIENCE"):
        return "Synthetic User Experience Apdex"
    if name.startswith("RASAI_APDEX_DYNATRACE") or name.startswith("RASAI_DYNATRACE") or name == "DYNATRACE_API_TOKEN":
        return "Dynatrace / calibração Apdex"
    if name.startswith("RASAI_APDEX_") or name == "RASAI_SYNTHETIC_APDEX":
        return "Synthetic Navigation Apdex"
    if name.startswith("RASAI_CONTENT_") or name in {
        "RASAI_YMYL_CATEGORY",
        "RASAI_PAGE_PURPOSE",
        "RASAI_INTENDED_AUDIENCE",
        "RASAI_EXPERIENCE_REQUIREMENT",
        "RASAI_FRESHNESS_SENSITIVITY",
        "RASAI_AI_ANALYSIS_LANGUAGE",
    }:
        return "Contexto editorial / YMYL"
    if name.startswith("RASAI_IMPROVEMENT_"):
        return "Improvement Intelligence"
    if name.startswith("RASAI_OIDC_") or name.startswith("RASAI_API_AUTH_"):
        return "OIDC / Identity"
    if name.startswith("RASAI_API_"):
        return "Web API"
    if name.startswith("RASAI_REMOTE_"):
        return "Remote control plane"
    if name.startswith("RASAI_PLATFORM_"):
        return "Control plane / banco"
    if name.startswith("RASAI_PLAYWRIGHT_") or name.startswith("RASAI_BROWSER_"):
        return "Browser / Playwright"
    service = _service_for_env(name)
    if service is not None:
        return service.label
    return spec.category


def grouped_by_context(specs: Sequence[object]) -> tuple[tuple[str, tuple[tuple[int, object], ...]], ...]:
    """Group variables by context while preserving their stable numeric index."""
    groups: OrderedDict[str, list[tuple[int, object]]] = OrderedDict()
    for index, spec in enumerate(specs, 1):
        groups.setdefault(context_for(spec), []).append((index, spec))
    return tuple((context, tuple(rows)) for context, rows in groups.items())


def reference_lines(spec) -> tuple[str, ...]:
    """Return authoritative resource/credential links relevant to a variable."""
    lines: list[str] = []
    ai = _ai_registration_for_env(spec.name)
    if ai is not None:
        if ai.documentation_url:
            lines.append(f"Documentação oficial: {ai.documentation_url}")
        if spec.name == ai.key_env and ai.credential_url:
            lines.append(f"Credencial/login: {ai.credential_url}")

    serp = _serp_registrations_for_env(spec.name)
    for item in serp:
        if item.documentation_url:
            lines.append(f"Documentação {item.display_name}: {item.documentation_url}")
        if item.credential_url:
            lines.append(f"Credencial/login {item.display_name}: {item.credential_url}")

    service = _service_for_env(spec.name)
    if service is not None:
        if service.documentation_url:
            lines.append(f"Documentação oficial: {service.documentation_url}")
        if service.credential_url and (
            spec.name in service.credential_envs or spec.name == service.enabled_env
        ):
            lines.append(f"Credencial/configuração: {service.credential_url}")

    if spec.name.startswith("RASAI_GSC_") or spec.name.startswith("RASAI_GOOGLE_SEARCH_CONSOLE_"):
        lines.append(f"Documentação Google Search Console: {_GSC_DOC_URL}")
        lines.append(f"Credenciais Google Cloud: {_GOOGLE_CREDENTIAL_URL}")
    if spec.name.startswith("RASAI_OIDC_") or spec.name.startswith("RASAI_API_AUTH_"):
        lines.append("Referência OIDC: https://openid.net/specs/openid-connect-core-1_0.html")
    if spec.name.startswith("RASAI_PLATFORM_"):
        lines.append("Referência PostgreSQL/libpq: https://www.postgresql.org/docs/current/libpq-connect.html")
    if spec.name.startswith("RASAI_PLAYWRIGHT_") or spec.name.startswith("RASAI_BROWSER_"):
        lines.append("Documentação Playwright: https://playwright.dev/python/docs/browsers")

    return tuple(dict.fromkeys(lines))


def _single_choice(spec, input_fn: Callable[[str], str]) -> str | None:
    current = (os.environ.get(spec.name) or "").strip()
    print("\nValores válidos:")
    for index, item in enumerate(spec.accepted, 1):
        markers: list[str] = []
        if item == current:
            markers.append("atual")
        if item == spec.default:
            markers.append("default")
        label = item
        if str(spec.value_type).casefold() == "booleano":
            label = paint(item, GREEN if item == "true" else DIM, bold=item == "true")
        suffix = f" [{' / '.join(markers)}]" if markers else ""
        print(f" {index}. {label}{suffix}")
    print(" V. Voltar")
    raw = input_fn("Escolha: ").strip()
    if raw.upper() == "V":
        return None
    if raw in spec.accepted:
        return raw
    try:
        return spec.accepted[int(raw) - 1]
    except (ValueError, IndexError) as exc:
        raise ValueError("opção inválida; selecione um dos valores apresentados") from exc


def _multi_choice(spec, input_fn: Callable[[str], str]) -> str | None:
    current_raw = (os.environ.get(spec.name) or spec.default or "").strip()
    current = {item.strip() for item in current_raw.split(",") if item.strip()}
    print("\nValores válidos (seleção múltipla):")
    for index, item in enumerate(spec.accepted, 1):
        marker = " [selecionado]" if item in current else ""
        print(f" {index}. {item}{marker}")
    print(" Digite números ou valores separados por vírgula; 'todos' seleciona todos; V volta.")
    raw = input_fn("Escolha: ").strip()
    if raw.upper() == "V":
        return None
    if raw.casefold() in {"todos", "all", "*"}:
        return ",".join(spec.accepted)
    tokens = [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]
    if not tokens:
        raise ValueError("selecione ao menos um valor")
    selected: list[str] = []
    for token in tokens:
        if token in spec.accepted:
            value = token
        else:
            try:
                value = spec.accepted[int(token) - 1]
            except (ValueError, IndexError) as exc:
                raise ValueError(f"opção inválida: {token}") from exc
        if value not in selected:
            selected.append(value)
    return ",".join(selected)


def prompt_guided_value(spec, input_fn: Callable[[str], str] = input) -> str | None:
    """Prompt only from the canonical allowed domain when one is known."""
    if not spec.accepted:
        raise ValueError("variável não possui domínio fechado conhecido")
    if str(spec.value_type).casefold() in {"lista csv", "lista", "csv"}:
        return _multi_choice(spec, input_fn)
    return _single_choice(spec, input_fn)


def decision_badge(spec) -> str:
    """Render decision state with the established console color semantics."""
    raw = (os.environ.get(spec.name) or "").strip()
    if raw:
        if str(spec.value_type).casefold() == "booleano" and raw.casefold() in {"false", "0", "no", "off"}:
            return paint("DESABILITADA", DIM)
        return paint("DEFINIDO", GREEN, bold=True)
    if spec.default is not None:
        return paint("PADRÃO", DIM)
    required = str(spec.required_when or "").strip().casefold()
    if required and not required.startswith("nunca") and "opcional" not in required:
        return paint("CONFIGURAR", YELLOW, bold=True)
    return paint("OPCIONAL", DIM)


def render_enrichment(spec) -> None:
    print(f"Contexto       : {paint(context_for(spec), CYAN, bold=True)}")
    if spec.accepted:
        mode = "seleção múltipla" if str(spec.value_type).casefold() in {"lista csv", "lista", "csv"} else "seleção única"
        print(f"Como preencher : {mode}; escolha somente entre os valores apresentados pelo console.")
    else:
        print("Como preencher : entrada específica; siga tipo, exemplo, dependências e validação exibidos acima.")
    references = reference_lines(spec)
    if references:
        print("Referências     :")
        for line in references:
            print(f"  - {line}")
