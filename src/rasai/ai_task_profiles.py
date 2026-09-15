"""Configurable, versioned task specialization profiles for RASAi AI calls.

The profile catalog controls persona, competencies, objective and optional task guidance.
Normative evidence, schema, scoring, safety and human-review rules remain owned by the
calling feature and are intentionally not configurable here.
"""
from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import os
from pathlib import Path
import re
import shutil
import tomllib
from typing import Any, Iterable, Mapping

PROFILE_FILE_ENV = "RASAI_AI_TASK_PROFILES_FILE"
PROFILE_SOURCE_ENV = "RASAI_AI_TASK_PROFILES_SOURCE"
CONSOLE_INI_ENV = "RASAI_CONSOLE_INI"
FACTORY_PROFILE_RESOURCE = "config/ai-profiles-defaults.toml"
DEFAULT_USER_PROFILE_FILE = "config/ai-task-profiles.toml"
DEFAULT_CONSOLE_INI = "rasai-console.ini"
SUPPORTED_SCHEMA_VERSION = 1

REQUIRED_PROFILE_IDS = (
    "SEMANTIC_READINESS",
    "CONTENT_REMEDIATION",
    "TECHNICAL_HTML",
    "CRAWL_DISCOVERY",
    "SOURCE_QUALITY",
    "SEARCH_INTELLIGENCE",
    "PERFORMANCE",
    "ACCESSIBILITY",
    "SECURITY_PASSIVE",
    "AI_READINESS",
    "EVOLUTION",
)

IMPROVEMENT_DOMAIN_PROFILES: dict[str, str] = {
    "TECHNICAL_HTML": "TECHNICAL_HTML",
    "SEMANTICS_STRUCTURE": "SEMANTIC_READINESS",
    "CONTENT": "CONTENT_REMEDIATION",
    "SEARCH_RANKING": "SEARCH_INTELLIGENCE",
    "FILES_DISCOVERY": "CRAWL_DISCOVERY",
    "PERFORMANCE": "PERFORMANCE",
    "ACCESSIBILITY": "ACCESSIBILITY",
    "BEST_PRACTICES": "TECHNICAL_HTML",
    "SECURITY": "SECURITY_PASSIVE",
    "AI_ACCESS": "AI_READINESS",
}

_PROFILE_ID = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_ALLOWED_PROFILE_FIELDS = frozenset({"version", "role", "objective", "competencies", "guidance"})


@dataclass(frozen=True, slots=True)
class TaskProfileMetadata:
    schema_version: int
    catalog_version: str
    reference_date: str
    description: str


@dataclass(frozen=True, slots=True)
class AiTaskProfile:
    profile_id: str
    version: str
    role: str
    objective: str
    competencies: tuple[str, ...]
    guidance: str


@dataclass(frozen=True, slots=True)
class AiTaskProfileCatalog:
    metadata: TaskProfileMetadata
    profiles: Mapping[str, AiTaskProfile]
    source: str

    def profile(self, profile_id: str) -> AiTaskProfile:
        key = str(profile_id or "").strip().upper()
        item = self.profiles.get(key)
        if item is None:
            raise ValueError(f"AI task profiles: perfil desconhecido: {profile_id}")
        return item


def _text(value: Any, field: str, *, maximum: int) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"AI task profiles: campo obrigatório ausente/vazio: {field}")
    if len(result) > maximum:
        raise ValueError(f"AI task profiles: {field} excede {maximum} caracteres")
    return result


def _parse_profile(profile_id: str, raw: Mapping[str, Any]) -> AiTaskProfile:
    key = str(profile_id or "").strip().upper()
    if not _PROFILE_ID.fullmatch(key):
        raise ValueError(f"AI task profiles: id inválido: {profile_id!r}")
    unknown = set(raw) - _ALLOWED_PROFILE_FIELDS
    if unknown:
        raise ValueError(
            f"AI task profiles: campos não suportados em {key}: {', '.join(sorted(unknown))}"
        )
    competencies_raw = raw.get("competencies")
    if not isinstance(competencies_raw, list) or not competencies_raw:
        raise ValueError(f"AI task profiles: {key}.competencies deve ser lista não vazia")
    if len(competencies_raw) > 12:
        raise ValueError(f"AI task profiles: {key}.competencies aceita no máximo 12 itens")
    competencies = tuple(
        dict.fromkeys(_text(value, f"{key}.competencies", maximum=200) for value in competencies_raw)
    )
    return AiTaskProfile(
        profile_id=key,
        version=_text(raw.get("version"), f"{key}.version", maximum=64),
        role=_text(raw.get("role"), f"{key}.role", maximum=500),
        objective=_text(raw.get("objective"), f"{key}.objective", maximum=1200),
        competencies=competencies,
        guidance=_text(raw.get("guidance"), f"{key}.guidance", maximum=1800),
    )


def _parse_document(
    document: Mapping[str, Any],
    *,
    source: str,
    require_all: bool,
) -> AiTaskProfileCatalog:
    metadata_raw = document.get("metadata")
    if not isinstance(metadata_raw, Mapping):
        raise ValueError("AI task profiles: seção [metadata] ausente")
    schema_version = int(metadata_raw.get("schema_version", 0))
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"AI task profiles: schema_version={schema_version} incompatível; esperado {SUPPORTED_SCHEMA_VERSION}"
        )
    metadata = TaskProfileMetadata(
        schema_version=schema_version,
        catalog_version=_text(metadata_raw.get("catalog_version"), "metadata.catalog_version", maximum=128),
        reference_date=_text(metadata_raw.get("reference_date"), "metadata.reference_date", maximum=32),
        description=_text(metadata_raw.get("description"), "metadata.description", maximum=1000),
    )
    profiles_raw = document.get("profiles")
    if not isinstance(profiles_raw, Mapping):
        raise ValueError("AI task profiles: seção [profiles.*] ausente")
    parsed: dict[str, AiTaskProfile] = {}
    for profile_id, raw in profiles_raw.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"AI task profiles: profiles.{profile_id} deve ser objeto TOML")
        item = _parse_profile(str(profile_id), raw)
        if item.profile_id in parsed:
            raise ValueError(f"AI task profiles: perfil duplicado: {item.profile_id}")
        parsed[item.profile_id] = item
    if require_all:
        missing = [profile_id for profile_id in REQUIRED_PROFILE_IDS if profile_id not in parsed]
        if missing:
            raise ValueError("AI task profiles: perfis obrigatórios ausentes: " + ", ".join(missing))
    return AiTaskProfileCatalog(metadata=metadata, profiles=parsed, source=source)


def _load_toml_bytes(payload: bytes, *, source: str, require_all: bool) -> AiTaskProfileCatalog:
    try:
        document = tomllib.loads(payload.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"AI task profiles: TOML inválido em {source}: {exc}") from exc
    return _parse_document(document, source=source, require_all=require_all)


def load_factory_task_profile_catalog() -> AiTaskProfileCatalog:
    resource = files("rasai").joinpath("config").joinpath("ai-profiles-defaults.toml")
    return _load_toml_bytes(resource.read_bytes(), source="FACTORY", require_all=True)


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


def task_profile_runtime_settings(
    *, env: Mapping[str, str] | None = None, cwd: Path | None = None
) -> tuple[str, Path]:
    environment = env if env is not None else os.environ
    base = (cwd or Path.cwd()).resolve()
    ini_values = _console_ini_environment(env=environment, cwd=base)
    source = str(
        environment.get(PROFILE_SOURCE_ENV)
        or ini_values.get(PROFILE_SOURCE_ENV)
        or "auto"
    ).strip().casefold()
    if source not in {"factory", "file", "auto"}:
        raise ValueError(f"{PROFILE_SOURCE_ENV}: use factory, file ou auto")
    configured = str(
        environment.get(PROFILE_FILE_ENV)
        or ini_values.get(PROFILE_FILE_ENV)
        or DEFAULT_USER_PROFILE_FILE
    ).strip()
    selected = Path(configured).expanduser()
    if not selected.is_absolute():
        selected = base / selected
    return source, selected.resolve()


def _merge_catalogs(
    factory: AiTaskProfileCatalog,
    override: AiTaskProfileCatalog,
) -> AiTaskProfileCatalog:
    profiles = dict(factory.profiles)
    profiles.update(override.profiles)
    missing = [profile_id for profile_id in REQUIRED_PROFILE_IDS if profile_id not in profiles]
    if missing:
        raise ValueError("AI task profiles: perfis obrigatórios ausentes após merge: " + ", ".join(missing))
    return AiTaskProfileCatalog(
        metadata=override.metadata,
        profiles=profiles,
        source=override.source,
    )


def load_task_profile_catalog(
    *,
    path: Path | str | None = None,
    document: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> AiTaskProfileCatalog:
    factory = load_factory_task_profile_catalog()
    if document is not None:
        override = _parse_document(document, source="SAAS", require_all=False)
        return _merge_catalogs(factory, override)
    if path is not None:
        selected = Path(path).expanduser().resolve()
        if not selected.is_file():
            raise ValueError(f"AI task profiles: arquivo não encontrado: {selected}")
        override = _load_toml_bytes(selected.read_bytes(), source=str(selected), require_all=False)
        return _merge_catalogs(factory, override)
    source, selected = task_profile_runtime_settings(env=env, cwd=cwd)
    if source == "factory":
        return factory
    if selected.is_file():
        override = _load_toml_bytes(selected.read_bytes(), source=str(selected), require_all=False)
        return _merge_catalogs(factory, override)
    if source == "auto":
        return factory
    raise ValueError(f"AI task profiles: {PROFILE_SOURCE_ENV}=file mas arquivo não existe: {selected}")


@lru_cache(maxsize=1)
def active_task_profile_catalog() -> AiTaskProfileCatalog:
    return load_task_profile_catalog()


def clear_task_profile_cache() -> None:
    active_task_profile_catalog.cache_clear()


def normalize_profile_ids(profile_ids: str | Iterable[str]) -> tuple[str, ...]:
    raw = (profile_ids,) if isinstance(profile_ids, str) else tuple(profile_ids)
    normalized = tuple(
        dict.fromkeys(str(value or "").strip().upper() for value in raw if str(value or "").strip())
    )
    if not normalized:
        raise ValueError("AI task profiles: ao menos um profile_id é obrigatório")
    return normalized


def profiles_for_improvement_domains(domains: Iterable[str]) -> tuple[str, ...]:
    selected: list[str] = []
    for raw in domains:
        domain = str(raw or "").strip().upper()
        profile_id = IMPROVEMENT_DOMAIN_PROFILES.get(domain)
        if profile_id and profile_id not in selected:
            selected.append(profile_id)
    return tuple(selected) or ("TECHNICAL_HTML",)


def render_task_profiles(
    profile_ids: str | Iterable[str],
    *,
    catalog: AiTaskProfileCatalog | None = None,
) -> str:
    selected = normalize_profile_ids(profile_ids)
    effective = catalog or active_task_profile_catalog()
    blocks: list[str] = []
    for profile_id in selected:
        item = effective.profile(profile_id)
        competencies = "; ".join(item.competencies)
        blocks.append(
            f"Task specialization profile: {item.profile_id} (version {item.version}). "
            f"Act as {item.role}. Objective: {item.objective} "
            f"Core competencies: {competencies}. Profile guidance: {item.guidance}"
        )
    return "\n".join(blocks)


def profile_identity(
    profile_ids: str | Iterable[str],
    *,
    catalog: AiTaskProfileCatalog | None = None,
) -> tuple[str, str]:
    selected = normalize_profile_ids(profile_ids)
    effective = catalog or active_task_profile_catalog()
    ids: list[str] = []
    versions: list[str] = []
    for profile_id in selected:
        item = effective.profile(profile_id)
        ids.append(item.profile_id)
        versions.append(item.version)
    return ",".join(ids), ",".join(versions)


def profile_summary_tag(
    profile_ids: str | Iterable[str],
    *,
    catalog: AiTaskProfileCatalog | None = None,
) -> str:
    ids, versions = profile_identity(profile_ids, catalog=catalog)
    pairs = [f"{profile_id}@{version}" for profile_id, version in zip(ids.split(","), versions.split(","))]
    return "profile=" + ",".join(pairs)


def restore_factory_task_profile_catalog(destination: Path | str) -> Path:
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    resource = files("rasai").joinpath("config").joinpath("ai-profiles-defaults.toml")
    with resource.open("rb") as source, target.open("wb") as output:
        shutil.copyfileobj(source, output)
    return target
