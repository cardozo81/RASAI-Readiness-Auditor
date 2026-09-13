"""Declarative AI pricing catalog loader for local runtime and SaaS control plane.

The pricing contract is data-driven. Provider/model commercial rules live in TOML (local)
or the same normalized mapping persisted by a SaaS control plane. This module validates
that document and exposes typed policies without embedding provider prices in code.
"""
from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import files
import os
from pathlib import Path
import shutil
import tomllib
from typing import Any, Mapping

PRICING_FILE_ENV = "RASAI_AI_PRICING_FILE"
PRICING_SOURCE_ENV = "RASAI_AI_PRICING_SOURCE"
CONSOLE_INI_ENV = "RASAI_CONSOLE_INI"
FACTORY_PRICING_RESOURCE = "config/ai-pricing-defaults.toml"
DEFAULT_USER_PRICING_FILE = "ai-pricing.toml"
DEFAULT_CONSOLE_INI = "rasai-console.ini"
SUPPORTED_SCHEMA_VERSION = 1

PRICING_MODELS = frozenset({"TOKEN_STANDARD", "TOKEN_CONTEXT_TIERED", "TOKEN_TIME_WINDOW"})
REASONING_BILLING_MODES = frozenset({"IN_OUTPUT", "ADD_REASONING_TO_OUTPUT"})
_WEEKDAYS = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}


@dataclass(frozen=True, slots=True)
class PricingCatalogMetadata:
    schema_version: int
    catalog_version: str
    reference_date: str
    verified_on: str
    review_recommended_on: str


@dataclass(frozen=True, slots=True)
class PricingCatalogRule:
    rule_id: str
    context: str
    priority: int
    effective_from: str
    effective_until: str | None
    input_price_per_million: float
    cached_input_price_per_million: float
    output_price_per_million: float
    input_tokens_gte: int | None = None
    input_tokens_gt: int | None = None
    input_tokens_lte: int | None = None
    input_tokens_lt: int | None = None
    weekdays_utc: tuple[int, ...] = ()
    time_windows_utc: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class PricingModelPolicy:
    provider: str
    model: str
    pricing_model: str
    reasoning_billing: str
    region: str
    source_reference: str
    currency: str
    rules: tuple[PricingCatalogRule, ...]


@dataclass(frozen=True, slots=True)
class PricingCatalog:
    metadata: PricingCatalogMetadata
    models: tuple[PricingModelPolicy, ...]
    source: str

    def model_policy(self, provider: str, model: str) -> PricingModelPolicy | None:
        key = (provider.strip().upper(), model.strip())
        return next((item for item in self.models if (item.provider, item.model) == key), None)

    def catalog_models(self) -> frozenset[tuple[str, str]]:
        return frozenset((item.provider, item.model) for item in self.models)


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"AI pricing: campo obrigatório ausente/vazio: {field}")
    return result


def _nonnegative_float(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"AI pricing: {field} deve ser numérico") from exc
    if result < 0:
        raise ValueError(f"AI pricing: {field} não pode ser negativo")
    return result


def _optional_int(raw: Mapping[str, Any], name: str) -> int | None:
    value = raw.get(name)
    if value is None:
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"AI pricing: {name} deve ser inteiro") from exc
    if result < 0:
        raise ValueError(f"AI pricing: {name} não pode ser negativo")
    return result


def _parse_instant(value: str, field: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"AI pricing: {field} deve ser ISO-8601 com timezone") from exc


def _time_minutes(value: str) -> int:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"AI pricing: horário UTC inválido: {value!r}") from exc
    if hour == 24 and minute == 0:
        return 24 * 60
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"AI pricing: horário UTC inválido: {value!r}")
    return hour * 60 + minute


def _parse_windows(values: Any) -> tuple[tuple[int, int], ...]:
    windows: list[tuple[int, int]] = []
    for raw in values or ():
        text = str(raw)
        try:
            start_text, end_text = text.split("-", 1)
        except ValueError as exc:
            raise ValueError(f"AI pricing: janela UTC inválida: {text!r}") from exc
        start, end = _time_minutes(start_text), _time_minutes(end_text)
        if start >= end:
            raise ValueError(f"AI pricing: janela UTC deve ter start < end: {text!r}")
        windows.append((start, end))
    return tuple(windows)


def _parse_weekdays(values: Any) -> tuple[int, ...]:
    result: list[int] = []
    for raw in values or ():
        key = str(raw).strip().upper()
        if key not in _WEEKDAYS:
            raise ValueError(f"AI pricing: weekday UTC inválido: {raw!r}")
        result.append(_WEEKDAYS[key])
    return tuple(result)


def _parse_rule(raw: Mapping[str, Any], *, provider: str, model: str) -> PricingCatalogRule:
    rule_id = _text(raw.get("rule_id"), f"{provider}/{model}.rule_id")
    effective_from = _text(raw.get("effective_from"), f"{rule_id}.effective_from")
    effective_until_raw = str(raw.get("effective_until") or "").strip() or None
    start = _parse_instant(effective_from, f"{rule_id}.effective_from")
    if effective_until_raw is not None:
        end = _parse_instant(effective_until_raw, f"{rule_id}.effective_until")
        if end <= start:
            raise ValueError(f"AI pricing: {rule_id}.effective_until deve ser posterior a effective_from")
    bounds = {
        "input_tokens_gte": _optional_int(raw, "input_tokens_gte"),
        "input_tokens_gt": _optional_int(raw, "input_tokens_gt"),
        "input_tokens_lte": _optional_int(raw, "input_tokens_lte"),
        "input_tokens_lt": _optional_int(raw, "input_tokens_lt"),
    }
    if bounds["input_tokens_gte"] is not None and bounds["input_tokens_gt"] is not None:
        raise ValueError(f"AI pricing: {rule_id} não pode combinar input_tokens_gte e input_tokens_gt")
    if bounds["input_tokens_lte"] is not None and bounds["input_tokens_lt"] is not None:
        raise ValueError(f"AI pricing: {rule_id} não pode combinar input_tokens_lte e input_tokens_lt")
    return PricingCatalogRule(
        rule_id=rule_id,
        context=_text(raw.get("context", "STANDARD"), f"{rule_id}.context").upper(),
        priority=int(raw.get("priority", 0)),
        effective_from=effective_from,
        effective_until=effective_until_raw,
        input_price_per_million=_nonnegative_float(raw.get("input_price_per_million"), f"{rule_id}.input_price_per_million"),
        cached_input_price_per_million=_nonnegative_float(raw.get("cached_input_price_per_million"), f"{rule_id}.cached_input_price_per_million"),
        output_price_per_million=_nonnegative_float(raw.get("output_price_per_million"), f"{rule_id}.output_price_per_million"),
        weekdays_utc=_parse_weekdays(raw.get("weekdays_utc")),
        time_windows_utc=_parse_windows(raw.get("time_windows_utc")),
        **bounds,
    )


def pricing_catalog_from_mapping(document: Mapping[str, Any], *, source: str = "SAAS") -> PricingCatalog:
    metadata_raw = document.get("metadata")
    if not isinstance(metadata_raw, Mapping):
        raise ValueError("AI pricing: seção [metadata] ausente")
    schema_version = int(metadata_raw.get("schema_version", 0))
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(f"AI pricing: schema_version={schema_version} incompatível; esperado {SUPPORTED_SCHEMA_VERSION}")
    metadata = PricingCatalogMetadata(
        schema_version=schema_version,
        catalog_version=_text(metadata_raw.get("catalog_version"), "metadata.catalog_version"),
        reference_date=_text(metadata_raw.get("reference_date"), "metadata.reference_date"),
        verified_on=_text(metadata_raw.get("verified_on"), "metadata.verified_on"),
        review_recommended_on=_text(metadata_raw.get("review_recommended_on"), "metadata.review_recommended_on"),
    )
    models_raw = document.get("models")
    if not isinstance(models_raw, list) or not models_raw:
        raise ValueError("AI pricing: ao menos um [[models]] é obrigatório")
    models: list[PricingModelPolicy] = []
    model_keys: set[tuple[str, str]] = set()
    rule_ids: set[str] = set()
    for raw in models_raw:
        if not isinstance(raw, Mapping):
            raise ValueError("AI pricing: cada models deve ser um objeto")
        provider = _text(raw.get("provider"), "models.provider").upper()
        model = _text(raw.get("model"), f"{provider}.model")
        key = (provider, model)
        if key in model_keys:
            raise ValueError(f"AI pricing: provider/model duplicado: {provider}/{model}")
        model_keys.add(key)
        pricing_model = _text(raw.get("pricing_model"), f"{provider}/{model}.pricing_model").upper()
        if pricing_model not in PRICING_MODELS:
            raise ValueError(f"AI pricing: pricing_model não suportado: {pricing_model}")
        reasoning_billing = _text(raw.get("reasoning_billing", "IN_OUTPUT"), f"{provider}/{model}.reasoning_billing").upper()
        if reasoning_billing not in REASONING_BILLING_MODES:
            raise ValueError(f"AI pricing: reasoning_billing não suportado: {reasoning_billing}")
        rules_raw = raw.get("rules")
        if not isinstance(rules_raw, list) or not rules_raw:
            raise ValueError(f"AI pricing: {provider}/{model} deve possuir ao menos uma regra")
        rules = tuple(_parse_rule(rule, provider=provider, model=model) for rule in rules_raw)
        for rule in rules:
            if rule.rule_id in rule_ids:
                raise ValueError(f"AI pricing: rule_id duplicado: {rule.rule_id}")
            rule_ids.add(rule.rule_id)
        models.append(PricingModelPolicy(
            provider=provider,
            model=model,
            pricing_model=pricing_model,
            reasoning_billing=reasoning_billing,
            region=_text(raw.get("region", "GLOBAL"), f"{provider}/{model}.region").upper(),
            source_reference=_text(raw.get("source_reference"), f"{provider}/{model}.source_reference"),
            currency=_text(raw.get("currency", "USD"), f"{provider}/{model}.currency").upper(),
            rules=rules,
        ))
    return PricingCatalog(metadata=metadata, models=tuple(models), source=source)


def _load_toml_bytes(payload: bytes, *, source: str) -> PricingCatalog:
    try:
        document = tomllib.loads(payload.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"AI pricing: TOML inválido em {source}: {exc}") from exc
    return pricing_catalog_from_mapping(document, source=source)


def load_factory_pricing_catalog() -> PricingCatalog:
    resource = files("rasai").joinpath("config").joinpath("ai-pricing-defaults.toml")
    return _load_toml_bytes(resource.read_bytes(), source="FACTORY")


def _console_ini_environment(*, env: Mapping[str, str], cwd: Path) -> dict[str, str]:
    configured = str(env.get(CONSOLE_INI_ENV) or "").strip()
    path = Path(configured).expanduser() if configured else cwd / DEFAULT_CONSOLE_INI
    if not path.is_absolute():
        path = cwd / path
    if not path.is_file():
        return {}
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        with path.open("r", encoding="utf-8") as stream:
            parser.read_file(stream)
    except (OSError, UnicodeError):
        return {}
    if not parser.has_section("environment"):
        return {}
    return {name: value.strip() for name, value in parser.items("environment", raw=True) if value.strip()}


def pricing_runtime_settings(*, env: Mapping[str, str] | None = None, cwd: Path | None = None) -> tuple[str, Path]:
    environment = env if env is not None else os.environ
    base = (cwd or Path.cwd()).resolve()
    ini_values = _console_ini_environment(env=environment, cwd=base)
    source = str(environment.get(PRICING_SOURCE_ENV) or ini_values.get(PRICING_SOURCE_ENV) or "factory").strip().casefold()
    if source not in {"factory", "file", "auto"}:
        raise ValueError(f"{PRICING_SOURCE_ENV}: use factory, file ou auto")
    configured = str(environment.get(PRICING_FILE_ENV) or ini_values.get(PRICING_FILE_ENV) or DEFAULT_USER_PRICING_FILE).strip()
    selected = Path(configured).expanduser()
    if not selected.is_absolute():
        selected = base / selected
    return source, selected.resolve()


def load_pricing_catalog(
    *,
    path: Path | str | None = None,
    document: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> PricingCatalog:
    """Load effective pricing from SaaS mapping, local file or factory catalog."""
    if document is not None:
        return pricing_catalog_from_mapping(document, source="SAAS")
    if path is not None:
        selected = Path(path).expanduser().resolve()
        if not selected.is_file():
            raise ValueError(f"AI pricing: arquivo não encontrado: {selected}")
        return _load_toml_bytes(selected.read_bytes(), source=str(selected))
    source, selected = pricing_runtime_settings(env=env, cwd=cwd)
    if source == "factory":
        return load_factory_pricing_catalog()
    if selected.is_file():
        return _load_toml_bytes(selected.read_bytes(), source=str(selected))
    if source == "auto":
        return load_factory_pricing_catalog()
    raise ValueError(f"AI pricing: {PRICING_SOURCE_ENV}=file mas arquivo não existe: {selected}")


def restore_factory_pricing_catalog(destination: Path | str) -> Path:
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    resource = files("rasai").joinpath("config").joinpath("ai-pricing-defaults.toml")
    with resource.open("rb") as source, target.open("wb") as output:
        shutil.copyfileobj(source, output)
    return target


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def rule_matches(rule: PricingCatalogRule, *, at: datetime, input_tokens: int) -> bool:
    instant = _utc(at)
    if instant < _parse_instant(rule.effective_from, f"{rule.rule_id}.effective_from"):
        return False
    if rule.effective_until is not None and instant >= _parse_instant(rule.effective_until, f"{rule.rule_id}.effective_until"):
        return False
    tokens = max(int(input_tokens), 0)
    if rule.input_tokens_gte is not None and tokens < rule.input_tokens_gte:
        return False
    if rule.input_tokens_gt is not None and tokens <= rule.input_tokens_gt:
        return False
    if rule.input_tokens_lte is not None and tokens > rule.input_tokens_lte:
        return False
    if rule.input_tokens_lt is not None and tokens >= rule.input_tokens_lt:
        return False
    if rule.weekdays_utc and instant.weekday() not in rule.weekdays_utc:
        return False
    if rule.time_windows_utc:
        minute = instant.hour * 60 + instant.minute
        if not any(start <= minute < end for start, end in rule.time_windows_utc):
            return False
    return True


def resolve_catalog_rule(
    catalog: PricingCatalog,
    provider: str,
    model: str,
    *,
    at: datetime,
    input_tokens: int,
) -> tuple[PricingModelPolicy, PricingCatalogRule] | None:
    policy = catalog.model_policy(provider, model)
    if policy is None:
        return None
    matches = [rule for rule in policy.rules if rule_matches(rule, at=at, input_tokens=input_tokens)]
    if not matches:
        return None
    selected = max(matches, key=lambda rule: (rule.priority, _parse_instant(rule.effective_from, f"{rule.rule_id}.effective_from"), rule.rule_id))
    return policy, selected
