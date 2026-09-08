"""Configuration and preflight rules for the optional interactive console."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import sys
from typing import Mapping

from rasai.cli import validate_target
from rasai.content_context import CONTENT_CONTEXT_ENV_NAMES, configured_content_analysis_context
from rasai.provider_registry import auto_provider_ids, get_provider_registration, provider_environment_names, provider_registrations
from rasai.provider_runtime_policy import (
    AI_TIMEOUT_ENV,
    DEFAULT_AI_TIMEOUT_SECONDS,
    DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS,
    EXTENSION_REASONING_ENV,
    REASONING_OPTIONS,
    SIMPLE_DEFAULT_MODELS,
    WEB_PERFORMANCE_TIMEOUT_ENV,
    configured_reasoning,
    provider_reasoning_env,
)
from rasai.url_utils import normalize_url, normalized_origin

_REGISTRATIONS = provider_registrations()
PROVIDERS = {item.id: item.provider_name for item in _REGISTRATIONS}
KEY_ENV = {item.provider_name: item.key_env for item in _REGISTRATIONS}
MODEL_ENV = {item.provider_name: item.model_env for item in _REGISTRATIONS}
DEFAULT_MODELS = dict(SIMPLE_DEFAULT_MODELS)
SUPPORTED_MODELS = {item.provider_name: item.supported_models for item in _REGISTRATIONS}
REASONING_ENV = {item.provider_name: provider_reasoning_env(item.provider_name) for item in _REGISTRATIONS if provider_reasoning_env(item.provider_name)}
PROVIDER_MENU_CHOICES = ("none", *(item.id for item in _REGISTRATIONS), "auto")

_BASE_ENV_NAMES = (
    "RASAI_CONFIG", "RASAI_LOG_LEVEL", "RASAI_DEVICE_CONTEXT", AI_TIMEOUT_ENV,
    "RASAI_AI_CONTENT_REMEDIATION", "RASAI_AI_TECHNICAL_REMEDIATION", *CONTENT_CONTEXT_ENV_NAMES,
    "RASAI_WEB_PERFORMANCE",
    "RASAI_WEB_PERFORMANCE_MAX_PAGES", WEB_PERFORMANCE_TIMEOUT_ENV,
    "RASAI_WEB_PERFORMANCE_FIELD_SOURCE", "RASAI_LIGHTHOUSE_CATEGORIES",
    "RASAI_PAGESPEED_API_KEY", "RASAI_CRUX_API_KEY",
    *EXTENSION_REASONING_ENV.values(), "RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE",
)
ENV_NAMES = tuple(dict.fromkeys((*_BASE_ENV_NAMES, *provider_environment_names())))
SECRET_NAMES = frozenset({*(item.key_env for item in _REGISTRATIONS), "RASAI_PAGESPEED_API_KEY", "RASAI_CRUX_API_KEY"})


@dataclass(frozen=True, slots=True)
class Capability:
    available: bool
    reason: str


@dataclass(slots=True)
class State:
    input_mode: str = "url"
    target: str = ""
    project: str = ""
    language: str = "pt-BR"
    market: str = "BR"
    max_pages: int = 100
    audits_root: str = "audits"
    device: str = "mobile"
    ai_provider: str = "none"
    ai_model: str | None = None
    ai_reasoning: str | None = None
    ai_timeout: float = DEFAULT_AI_TIMEOUT_SECONDS
    content_remediation: bool = False
    technical_remediation: bool = False
    web_performance: bool = False
    web_max_pages: int = 10
    web_timeout: float = DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS
    field_source: str = "auto"
    lighthouse_categories: str = "performance,accessibility,best-practices,seo"
    status: str = "READY"
    current_url: str = "-"
    current_device: str = "MOBILE"
    operation: str = "LOCAL:MENU"
    error: str = ""
    audit_id: str = ""
    output: list[str] = field(default_factory=list)
    runtime_blocks: dict[str, str] = field(default_factory=dict)


def apply_environment_defaults(state: State, env: Mapping[str, str] | None = None, names: set[str] | None = None) -> tuple[str, ...]:
    environment = env if env is not None else os.environ
    issues: list[str] = []
    active = lambda name: names is None or name in names

    def boolean(name: str, default: bool) -> bool:
        raw = (environment.get(name) or "").strip().casefold()
        if not raw: return default
        if raw in {"1", "true", "yes", "on"}: return True
        if raw in {"0", "false", "no", "off"}: return False
        issues.append(f"{name}: booleano inválido")
        return default

    if active("RASAI_DEVICE_CONTEXT"):
        raw = (environment.get("RASAI_DEVICE_CONTEXT") or "").strip().casefold()
        if not raw: state.device, state.current_device = "mobile", "MOBILE"
        elif raw in {"mobile", "desktop", "both"}: state.device, state.current_device = raw, raw.upper()
        else: issues.append("RASAI_DEVICE_CONTEXT: use mobile, desktop ou both")
    if active(AI_TIMEOUT_ENV):
        raw = (environment.get(AI_TIMEOUT_ENV) or "").strip()
        try:
            state.ai_timeout = DEFAULT_AI_TIMEOUT_SECONDS if not raw else float(raw)
            if state.ai_timeout <= 0: raise ValueError
        except ValueError: issues.append(f"{AI_TIMEOUT_ENV}: use número > 0")
    if active("RASAI_AI_CONTENT_REMEDIATION"): state.content_remediation = boolean("RASAI_AI_CONTENT_REMEDIATION", False)
    if active("RASAI_AI_TECHNICAL_REMEDIATION"): state.technical_remediation = boolean("RASAI_AI_TECHNICAL_REMEDIATION", False)
    if active("RASAI_WEB_PERFORMANCE"): state.web_performance = boolean("RASAI_WEB_PERFORMANCE", False)
    if active("RASAI_WEB_PERFORMANCE_MAX_PAGES"):
        raw = (environment.get("RASAI_WEB_PERFORMANCE_MAX_PAGES") or "").strip()
        try:
            state.web_max_pages = 10 if not raw else int(raw)
            if state.web_max_pages < 0: raise ValueError
        except ValueError: issues.append("RASAI_WEB_PERFORMANCE_MAX_PAGES: use inteiro >= 0")
    if active(WEB_PERFORMANCE_TIMEOUT_ENV):
        raw = (environment.get(WEB_PERFORMANCE_TIMEOUT_ENV) or "").strip()
        try:
            state.web_timeout = DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS if not raw else float(raw)
            if state.web_timeout <= 0: raise ValueError
        except ValueError: issues.append(f"{WEB_PERFORMANCE_TIMEOUT_ENV}: use número > 0")
    if active("RASAI_WEB_PERFORMANCE_FIELD_SOURCE"):
        raw = (environment.get("RASAI_WEB_PERFORMANCE_FIELD_SOURCE") or "").strip().casefold()
        if not raw: state.field_source = "auto"
        elif raw in {"auto", "pagespeed", "crux", "none"}: state.field_source = raw
        else: issues.append("RASAI_WEB_PERFORMANCE_FIELD_SOURCE: valor inválido")
    if active("RASAI_LIGHTHOUSE_CATEGORIES"):
        state.lighthouse_categories = (environment.get("RASAI_LIGHTHOUSE_CATEGORIES") or "").strip() or "performance,accessibility,best-practices,seo"
    if any(active(name) for name in CONTENT_CONTEXT_ENV_NAMES):
        try:
            configured_content_analysis_context(environment)
        except ValueError as exc:
            issues.append(str(exc))
    if state.ai_provider in PROVIDERS:
        provider = PROVIDERS[state.ai_provider]
        variable = provider_reasoning_env(provider)
        if names is None or (variable and variable in names):
            try: state.ai_reasoning = configured_reasoning(provider, environment)
            except ValueError as exc: issues.append(str(exc))
    return tuple(issues)


def is_secret(name: str) -> bool:
    upper = name.upper()
    return name in SECRET_NAMES or any(token in upper for token in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))


def environment_summary(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    environment = env if env is not None else os.environ
    names = set(ENV_NAMES) | {name for name in environment if name.startswith("RASAI_")}
    items: list[str] = []
    for name in sorted(names):
        value = (environment.get(name) or "").strip()
        if value:
            shown = "[SET]" if is_secret(name) else value.replace("\n", " ")[:48]
            items.append(f"{name}={shown}")
    return tuple(items)


def provider_capabilities(env: Mapping[str, str] | None = None, blocks: Mapping[str, str] | None = None) -> dict[str, Capability]:
    environment = env if env is not None else os.environ
    blocked = blocks or {}
    result: dict[str, Capability] = {"none": Capability(True, "sem IA")}
    auto_ready: list[str] = []
    for registration in _REGISTRATIONS:
        provider_id, name = registration.id, registration.provider_name
        key = (environment.get(registration.key_env) or "").strip()
        model = (environment.get(registration.model_env) or SIMPLE_DEFAULT_MODELS[name]).strip()
        if blocked.get(provider_id): capability = Capability(False, f"bloqueado após erro: {blocked[provider_id]}")
        elif not key: capability = Capability(False, f"{registration.key_env} não configurada" + (f" | {registration.qualification} | explicit-only" if registration.explicit_only else ""))
        elif registration.required_key_prefixes and not key.startswith(registration.required_key_prefixes): capability = Capability(False, f"{registration.display_name} exige chave compatível ({' ou '.join(registration.required_key_prefixes)}...)")
        elif model not in registration.supported_models: capability = Capability(False, f"modelo inválido em {registration.model_env}: {model}")
        else:
            try: effort = configured_reasoning(name, environment)
            except ValueError as exc: capability = Capability(False, str(exc))
            else: capability = Capability(True, f"{registration.display_name}/{model} | esforço={effort} | {registration.qualification}" + (" | explicit-only" if registration.explicit_only else ""))
        result[provider_id] = capability
        for alias in registration.aliases: result[alias] = capability
        if registration.auto_eligible and capability.available: auto_ready.append(provider_id)
    chain = " -> ".join(item.upper() for item in auto_provider_ids())
    result["auto"] = Capability(bool(auto_ready), f"{len(auto_ready)} provider(s) elegível(is); cadeia homologada {chain}" if auto_ready else f"nenhum provider AUTO elegível; cadeia homologada {chain}")
    return result


def _registration_by_env(name: str):
    for registration in _REGISTRATIONS:
        if name in {registration.key_env, registration.model_env, registration.endpoint_env, provider_reasoning_env(registration.provider_name)}: return registration
    return None


def validate_env_value(name: str, value: str) -> str:
    value = value.strip()
    if not value: raise ValueError("valor vazio; remova a variável em vez de gravar vazio")
    registration = _registration_by_env(name)
    if registration is not None:
        if name == registration.key_env:
            if registration.required_key_prefixes and not value.startswith(registration.required_key_prefixes): raise ValueError(f"{registration.display_name} exige chave compatível ({' ou '.join(registration.required_key_prefixes)}...)")
            return value
        if name == registration.model_env:
            if value not in registration.supported_models: raise ValueError(f"modelos suportados: {', '.join(registration.supported_models)}")
            return value
        if name == provider_reasoning_env(registration.provider_name):
            value = value.upper()
            if value not in REASONING_OPTIONS[registration.provider_name]: raise ValueError("reasoning effort não suportado; use " + ", ".join(REASONING_OPTIONS[registration.provider_name]))
            return value
        if name == registration.endpoint_env: return value
    if name in CONTENT_CONTEXT_ENV_NAMES:
        candidate = dict(os.environ)
        candidate[name] = value.casefold()
        configured_content_analysis_context(candidate)
        return value.casefold()
    if name in {"RASAI_AI_CONTENT_REMEDIATION", "RASAI_AI_TECHNICAL_REMEDIATION", "RASAI_WEB_PERFORMANCE"} and value.casefold() not in {"true", "false", "1", "0", "yes", "no", "on", "off"}: raise ValueError("booleano inválido")
    if name == "RASAI_DEVICE_CONTEXT":
        value = value.casefold()
        if value not in {"mobile", "desktop", "both"}: raise ValueError("use mobile, desktop ou both")
    if name in {AI_TIMEOUT_ENV, WEB_PERFORMANCE_TIMEOUT_ENV} and float(value) <= 0: raise ValueError("valor deve ser > 0")
    if name == "RASAI_WEB_PERFORMANCE_MAX_PAGES" and int(value) < 0: raise ValueError("valor deve ser >= 0")
    if name == "RASAI_WEB_PERFORMANCE_FIELD_SOURCE":
        value = value.casefold()
        if value not in {"auto", "pagespeed", "crux", "none"}: raise ValueError("use auto, pagespeed, crux ou none")
        if value == "crux" and not (os.environ.get("RASAI_CRUX_API_KEY") or "").strip(): raise ValueError("crux exige RASAI_CRUX_API_KEY")
    if name == "RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE" and not Path(value).is_file(): raise ValueError("arquivo Chromium configurado não existe")
    return value


def preflight(state: State, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    environment = env if env is not None else os.environ
    if state.max_pages <= 0 or state.web_max_pages < 0 or state.web_timeout <= 0 or state.ai_timeout <= 0: raise ValueError("limites/timeout inválidos")
    configured_content_analysis_context(environment)
    if state.input_mode == "url":
        if not state.target.strip(): raise ValueError("informe uma URL/domínio")
        targets = (validate_target(state.target),)
    elif state.input_mode == "file":
        path = Path(state.target)
        if not path.is_file(): raise ValueError(f"TXT não encontrado: {path}")
        targets = tuple(validate_target(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#"))
        if not targets: raise ValueError("TXT não contém targets")
    else: raise ValueError("modo de entrada inválido")
    normalized = tuple(dict.fromkeys(normalize_url(item) for item in targets))
    if len({normalized_origin(item) for item in normalized}) != 1: raise ValueError("todos os targets devem pertencer à mesma origem normalizada")
    if state.input_mode == "file" and len(normalized) > state.max_pages: raise ValueError(f"TXT possui {len(normalized)} URLs únicas e max-pages={state.max_pages}")
    capability = provider_capabilities(environment, state.runtime_blocks).get(get_provider_registration(state.ai_provider).id if get_provider_registration(state.ai_provider) else state.ai_provider)
    if not capability or not capability.available: raise ValueError(f"provider {state.ai_provider} indisponível: {capability.reason if capability else 'inválido'}")
    if state.ai_provider == "none" and (state.content_remediation or state.technical_remediation): raise ValueError("remediações de IA exigem provider de IA apto")
    if state.ai_provider == "auto" and state.ai_model: raise ValueError("AUTO não aceita --ai-model")
    if state.web_performance and state.field_source == "crux" and not (environment.get("RASAI_CRUX_API_KEY") or "").strip(): raise ValueError("field source crux exige RASAI_CRUX_API_KEY")
    browser = (environment.get("RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE") or "").strip()
    if browser and not Path(browser).is_file(): raise ValueError("RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE não existe")
    return normalized


def build_command(state: State) -> list[str]:
    command = [sys.executable, "-m", "rasai", "audit"]
    command += ["--urls-file", state.target] if state.input_mode == "file" else [state.target]
    if state.project: command += ["--project", state.project]
    command += ["--language", state.language, "--market", state.market, "--max-pages", str(state.max_pages), "--audits-root", state.audits_root, "--device-context", state.device, "--ai-provider", state.ai_provider]
    if get_provider_registration(state.ai_provider) is not None and state.ai_model: command += ["--ai-model", state.ai_model]
    command += ["--ai-content-remediation" if state.content_remediation else "--no-ai-content-remediation"]
    command += ["--ai-technical-remediation" if state.technical_remediation else "--no-ai-technical-remediation"]
    command += ["--web-performance" if state.web_performance else "--no-web-performance"]
    if state.web_performance: command += ["--web-performance-max-pages", str(state.web_max_pages), "--web-performance-timeout-seconds", str(state.web_timeout), "--web-performance-field-source", state.field_source, "--lighthouse-categories", state.lighthouse_categories]
    return command