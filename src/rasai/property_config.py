"""Versionable, secret-free property configuration.

Property configuration describes what RASAi should analyze and which runtime capabilities
it should use. Credential values never belong in these files; only environment/secret
references may be versioned.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import tomllib
from typing import Any, Mapping
from urllib.parse import urlsplit

from .property_semantic_profile import PropertySemanticProfile, build_property_semantic_profile
from .secret_safety import (
    detect_secret_exposures,
    is_secret_reference_name,
    is_sensitive_name,
    validate_environment_reference,
)


PROPERTY_CONFIG_CONTRACT = "PROPERTY-CONFIG-001"
_PROPERTY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_ALLOWED_DATABASE_BACKENDS = {"sqlite", "postgresql"}
_SEMANTIC_PROFILE_FIELDS = (
    "business_sector",
    "business_description",
    "primary_offering",
    "target_audience_profile",
    "primary_goal",
    "positioning",
)


@dataclass(frozen=True, slots=True)
class PropertyConfig:
    property_id: str
    name: str
    origin: str
    document: Mapping[str, Any]
    source: Path

    def environment_references(self) -> tuple[str, ...]:
        values: set[str] = set()

        def visit(node: Any, key: str | None = None) -> None:
            if isinstance(node, Mapping):
                for child_key, child in node.items():
                    visit(child, str(child_key))
            elif isinstance(node, list):
                for child in node:
                    visit(child, key)
            elif key and is_secret_reference_name(key) and key.upper().endswith("_ENV"):
                values.add(validate_environment_reference(str(node)))

        visit(self.document)
        return tuple(sorted(values))

    def missing_environment_references(self, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
        environment = env if env is not None else os.environ
        return tuple(name for name in self.environment_references() if not (environment.get(name) or "").strip())

    def semantic_profile(self) -> PropertySemanticProfile:
        section = self.document.get("semantic_profile")
        values = dict(section) if isinstance(section, Mapping) else {}
        return build_property_semantic_profile(
            **{name: str(values.get(name) or "auto") for name in _SEMANTIC_PROFILE_FIELDS}
        )


def _validate_origin(value: str) -> str:
    text = value.strip()
    parsed = urlsplit(text if "://" in text else "https://" + text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("property origin must be an http(s) domain/origin")
    if parsed.username or parsed.password:
        raise ValueError("property origin must not contain credentials")
    return text


def _validate_node(node: Any, *, path: str = "") -> None:
    if isinstance(node, Mapping):
        for raw_key, value in node.items():
            key = str(raw_key)
            dotted = f"{path}.{key}" if path else key
            if is_sensitive_name(key) and not is_secret_reference_name(key):
                raise ValueError(
                    f"property configuration must not contain inline secret field {dotted!r}; "
                    "use an *_env or *_ref field"
                )
            if is_secret_reference_name(key):
                if not isinstance(value, str):
                    raise ValueError(f"secret reference {dotted!r} must be a string")
                if key.upper().endswith("_ENV"):
                    validate_environment_reference(value)
            _validate_node(value, path=dotted)
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            _validate_node(value, path=f"{path}[{index}]")
        return
    if isinstance(node, str):
        findings = detect_secret_exposures(node, path=path or "property-config")
        if findings:
            raise ValueError(
                f"property configuration contains secret-like inline value at {path or '<root>'}; "
                "store the value outside Git and reference it instead"
            )


def _validate_semantic_profile(document: Mapping[str, Any]) -> None:
    section = document.get("semantic_profile")
    if section is None:
        return
    if not isinstance(section, Mapping):
        raise ValueError("[semantic_profile] must be a TOML table")
    unknown = sorted(set(str(key) for key in section) - set(_SEMANTIC_PROFILE_FIELDS))
    if unknown:
        raise ValueError("unsupported semantic_profile field(s): " + ", ".join(unknown))
    build_property_semantic_profile(
        **{name: str(section.get(name) or "auto") for name in _SEMANTIC_PROFILE_FIELDS}
    )


def load_property_config(path: str | Path) -> PropertyConfig:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"property configuration not found: {source}")
    with source.open("rb") as stream:
        document = tomllib.load(stream)
    if not isinstance(document, dict):
        raise ValueError("property configuration root must be a TOML document")
    _validate_node(document)

    section = document.get("property")
    if not isinstance(section, dict):
        raise ValueError("property configuration requires a [property] table")
    property_id = str(section.get("id") or "").strip().casefold()
    name = str(section.get("name") or "").strip()
    origin = _validate_origin(str(section.get("origin") or ""))
    if not _PROPERTY_ID_RE.fullmatch(property_id):
        raise ValueError("property.id must use lowercase letters, numbers, dot, underscore or hyphen")
    if not name:
        raise ValueError("property.name must not be empty")

    database = document.get("database", {})
    if database is not None:
        if not isinstance(database, dict):
            raise ValueError("[database] must be a TOML table")
        backend = str(database.get("backend") or "sqlite").strip().casefold()
        if backend not in _ALLOWED_DATABASE_BACKENDS:
            raise ValueError("database.backend must be sqlite or postgresql")
        if backend == "postgresql" and "database_url_env" not in database:
            raise ValueError("postgresql property configuration requires database.database_url_env")
        if "database_url" in database:
            raise ValueError("database.database_url must not be versioned; use database_url_env")

    _validate_semantic_profile(document)

    return PropertyConfig(
        property_id=property_id,
        name=name,
        origin=origin,
        document=document,
        source=source,
    )
