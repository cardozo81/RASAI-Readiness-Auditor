"""Declarative AI model catalog for RASAi runtime and control-plane consumers.

Provider adapters remain code. This catalog defines which models an already-integrated
provider may expose, their defaults, reasoning contract and AUTO eligibility. The local
runtime supports a packaged factory catalog or one operator-managed TOML using the same
source-selection contract as AI pricing.
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

MODEL_FILE_ENV = "RASAI_AI_MODELS_FILE"
MODEL_SOURCE_ENV = "RASAI_AI_MODELS_SOURCE"
CONSOLE_INI_ENV = "RASAI_CONSOLE_INI"
FACTORY_MODEL_RESOURCE = "config/ai-models-defaults.toml"
DEFAULT_USER_MODEL_FILE = "ai-models.toml"
DEFAULT_CONSOLE_INI = "rasai-console.ini"
SUPPORTED_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ModelCatalogMetadata:
    schema_version: int
    catalog_version: str
    reference_date: str
    verified_on: str
    review_recommended_on: str


@dataclass(frozen=True, slots=True)
class AiModelDefinition:
    provider: str
    model: str
    enabled: bool
    selectable: bool
    adapter_default: bool
    public_default: bool
    auto_eligible: bool
    qualification: str
    rasai_class: str
    rank: int
    recommended_depth: str
    recommended_use: str
    reasoning_values: tuple[str, ...]
    default_reasoning: str
    capabilities: tuple[str, ...]
    context_window: int | None
    max_output_tokens: int | None
    effective_from: str | None
    effective_until: str | None
    source_reference: str

    def is_effective(self, at: datetime | None = None) -> bool:
        instant = _utc(at or datetime.now(timezone.utc))
        if self.effective_from is not None and instant < _parse_instant(self.effective_from, f"{self.provider}/{self.model}.effective_from"):
            return False
        if self.effective_until is not None and instant >= _parse_instant(self.effective_until, f"{self.provider}/{self.model}.effective_until"):
            return False
        return True


@dataclass(frozen=True, slots=True)
class AiModelCatalog:
    metadata: ModelCatalogMetadata
    models: tuple[AiModelDefinition, ...]
    source: str

    def model_definition(self, provider: str, model: str) -> AiModelDefinition | None:
        key = (provider.strip().upper(), model.strip())
        return next((item for item in self.models if (item.provider, item.model) == key), None)

    def provider_models(
        self,
        provider: str,
        *,
        enabled_only: bool = True,
        effective_only: bool = True,
        at: datetime | None = None,
    ) -> tuple[AiModelDefinition, ...]:
        name = provider.strip().upper()
        items = tuple(item for item in self.models if item.provider == name)
        if enabled_only:
            items = tuple(item for item in items if item.enabled)
        if effective_only:
            items = tuple(item for item in items if item.is_effective(at))
        return items

    def provider_names(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.provider for item in self.models))

    def catalog_models(self) -> frozenset[tuple[str, str]]:
        return frozenset((item.provider, item.model) for item in self.models)

    def adapter_default(self, provider: str) -> AiModelDefinition | None:
        return next((item for item in self.provider_models(provider) if item.adapter_default), None)

    def public_default(self, provider: str) -> AiModelDefinition | None:
        return next((item for item in self.provider_models(provider) if item.public_default), None)


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"AI models: campo obrigatório ausente/vazio: {field}")
    return result


def _bool(value: Any, field: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    token = str(value).strip().casefold()
    if token in {"true", "1", "yes", "on"}:
        return True
    if token in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"AI models: {field} deve ser booleano")


def _optional_positive_int(value: Any, field: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"AI models: {field} deve ser inteiro") from exc
    if parsed <= 0:
        raise ValueError(f"AI models: {field} deve ser > 0")
    return parsed


def _tokens(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"AI models: {field} deve ser uma lista não vazia")
    result = tuple(dict.fromkeys(_text(item, field).upper() for item in value))
    if not result:
        raise ValueError(f"AI models: {field} deve possuir ao menos um valor")
    return result


def _parse_instant(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"AI models: {field} deve ser ISO-8601 com timezone") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"AI models: {field} deve possuir timezone")
    return parsed.astimezone(timezone.utc)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_model(raw: Mapping[str, Any]) -> AiModelDefinition:
    provider = _text(raw.get("provider"), "models.provider").upper()
    model = _text(raw.get("model"), f"{provider}.model")
    reasoning_values = _tokens(raw.get("reasoning_values"), f"{provider}/{model}.reasoning_values")
    default_reasoning = _text(raw.get("default_reasoning"), f"{provider}/{model}.default_reasoning").upper()
    if default_reasoning not in reasoning_values:
        raise ValueError(
            f"AI models: {provider}/{model}.default_reasoning={default_reasoning} não está em reasoning_values"
        )
    enabled = _bool(raw.get("enabled"), f"{provider}/{model}.enabled", default=True)
    selectable = _bool(raw.get("selectable"), f"{provider}/{model}.selectable", default=True)
    adapter_default = _bool(raw.get("adapter_default"), f"{provider}/{model}.adapter_default")
    public_default = _bool(raw.get("public_default"), f"{provider}/{model}.public_default")
    auto_eligible = _bool(raw.get("auto_eligible"), f"{provider}/{model}.auto_eligible")
    if not enabled and (selectable or adapter_default or public_default or auto_eligible):
        raise ValueError(
            f"AI models: {provider}/{model} desabilitado não pode ser selecionável/default/AUTO"
        )
    if public_default and not selectable:
        raise ValueError(f"AI models: {provider}/{model} public_default exige selectable=true")
    if auto_eligible and not selectable:
        raise ValueError(f"AI models: {provider}/{model} auto_eligible exige selectable=true")
    effective_from = str(raw.get("effective_from") or "").strip() or None
    effective_until = str(raw.get("effective_until") or "").strip() or None
    if effective_from is not None:
        start = _parse_instant(effective_from, f"{provider}/{model}.effective_from")
    else:
        start = None
    if effective_until is not None:
        end = _parse_instant(effective_until, f"{provider}/{model}.effective_until")
        if start is not None and end <= start:
            raise ValueError(f"AI models: {provider}/{model}.effective_until deve ser posterior a effective_from")
    rank = int(raw.get("rank", 9999))
    if rank < 0:
        raise ValueError(f"AI models: {provider}/{model}.rank não pode ser negativo")
    raw_capabilities = raw.get("capabilities", [])
    if not isinstance(raw_capabilities, list):
        raise ValueError(f"AI models: {provider}/{model}.capabilities deve ser uma lista")
    capabilities = tuple(dict.fromkeys(str(item).strip().upper() for item in raw_capabilities if str(item).strip()))
    return AiModelDefinition(
        provider=provider,
        model=model,
        enabled=enabled,
        selectable=selectable,
        adapter_default=adapter_default,
        public_default=public_default,
        auto_eligible=auto_eligible,
        qualification=_text(raw.get("qualification", "PROVISIONAL"), f"{provider}/{model}.qualification").upper(),
        rasai_class=_text(raw.get("rasai_class", "PROVISIONAL"), f"{provider}/{model}.rasai_class").upper(),
        rank=rank,
        recommended_depth=_text(raw.get("recommended_depth", default_reasoning), f"{provider}/{model}.recommended_depth").upper(),
        recommended_use=_text(raw.get("recommended_use", "configurável"), f"{provider}/{model}.recommended_use"),
        reasoning_values=reasoning_values,
        default_reasoning=default_reasoning,
        capabilities=capabilities,
        context_window=_optional_positive_int(raw.get("context_window"), f"{provider}/{model}.context_window"),
        max_output_tokens=_optional_positive_int(raw.get("max_output_tokens"), f"{provider}/{model}.max_output_tokens"),
        effective_from=effective_from,
        effective_until=effective_until,
        source_reference=_text(raw.get("source_reference"), f"{provider}/{model}.source_reference"),
    )


def model_catalog_from_mapping(document: Mapping[str, Any], *, source: str = "SAAS") -> AiModelCatalog:
    metadata_raw = document.get("metadata")
    if not isinstance(metadata_raw, Mapping):
        raise ValueError("AI models: seção [metadata] ausente")
    schema_version = int(metadata_raw.get("schema_version", 0))
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"AI models: schema_version={schema_version} incompatível; esperado {SUPPORTED_SCHEMA_VERSION}"
        )
    metadata = ModelCatalogMetadata(
        schema_version=schema_version,
        catalog_version=_text(metadata_raw.get("catalog_version"), "metadata.catalog_version"),
        reference_date=_text(metadata_raw.get("reference_date"), "metadata.reference_date"),
        verified_on=_text(metadata_raw.get("verified_on"), "metadata.verified_on"),
        review_recommended_on=_text(metadata_raw.get("review_recommended_on"), "metadata.review_recommended_on"),
    )
    raw_models = document.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ValueError("AI models: ao menos um [[models]] é obrigatório")
    models = tuple(_parse_model(raw) for raw in raw_models if isinstance(raw, Mapping))
    if len(models) != len(raw_models):
        raise ValueError("AI models: cada [[models]] deve ser um objeto")
    keys: set[tuple[str, str]] = set()
    for item in models:
        key = (item.provider, item.model)
        if key in keys:
            raise ValueError(f"AI models: provider/model duplicado: {item.provider}/{item.model}")
        keys.add(key)
    for provider in tuple(dict.fromkeys(item.provider for item in models)):
        enabled = tuple(item for item in models if item.provider == provider and item.enabled)
        if not enabled:
            continue
        adapter_defaults = tuple(item for item in enabled if item.adapter_default)
        public_defaults = tuple(item for item in enabled if item.public_default)
        if len(adapter_defaults) != 1:
            raise ValueError(f"AI models: {provider} deve possuir exatamente um adapter_default habilitado")
        if len(public_defaults) != 1:
            raise ValueError(f"AI models: {provider} deve possuir exatamente um public_default habilitado")
    return AiModelCatalog(metadata=metadata, models=models, source=source)


def _load_toml_bytes(payload: bytes, *, source: str) -> AiModelCatalog:
    try:
        document = tomllib.loads(payload.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"AI models: TOML inválido em {source}: {exc}") from exc
    return model_catalog_from_mapping(document, source=source)


def load_factory_model_catalog() -> AiModelCatalog:
    resource = files("rasai").joinpath("config").joinpath("ai-models-defaults.toml")
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


def model_runtime_settings(*, env: Mapping[str, str] | None = None, cwd: Path | None = None) -> tuple[str, Path]:
    environment = env if env is not None else os.environ
    base = (cwd or Path.cwd()).resolve()
    ini_values = _console_ini_environment(env=environment, cwd=base)
    source = str(environment.get(MODEL_SOURCE_ENV) or ini_values.get(MODEL_SOURCE_ENV) or "factory").strip().casefold()
    if source not in {"factory", "file", "auto"}:
        raise ValueError(f"{MODEL_SOURCE_ENV}: use factory, file ou auto")
    configured = str(environment.get(MODEL_FILE_ENV) or ini_values.get(MODEL_FILE_ENV) or DEFAULT_USER_MODEL_FILE).strip()
    selected = Path(configured).expanduser()
    if not selected.is_absolute():
        selected = base / selected
    return source, selected.resolve()


def load_model_catalog(
    *,
    path: Path | str | None = None,
    document: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> AiModelCatalog:
    if document is not None:
        return model_catalog_from_mapping(document, source="SAAS")
    if path is not None:
        selected = Path(path).expanduser().resolve()
        if not selected.is_file():
            raise ValueError(f"AI models: arquivo não encontrado: {selected}")
        return _load_toml_bytes(selected.read_bytes(), source=str(selected))
    source, selected = model_runtime_settings(env=env, cwd=cwd)
    if source == "factory":
        return load_factory_model_catalog()
    if selected.is_file():
        return _load_toml_bytes(selected.read_bytes(), source=str(selected))
    if source == "auto":
        return load_factory_model_catalog()
    raise ValueError(f"AI models: {MODEL_SOURCE_ENV}=file mas arquivo não existe: {selected}")


def restore_factory_model_catalog(destination: Path | str) -> Path:
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    resource = files("rasai").joinpath("config").joinpath("ai-models-defaults.toml")
    with resource.open("rb") as source, target.open("wb") as output:
        shutil.copyfileobj(source, output)
    return target
