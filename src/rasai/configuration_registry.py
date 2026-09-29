"""Canonical inventory of console configuration ownership, persistence and defaults.

The registry is derived from the installed EnvironmentSpec surface plus the audit catalog
capability mapping. It deliberately avoids per-catalog lists so new configuration keys are
classified by the same primitives used by the interactive console.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_BOOTSTRAP_ENV_NAMES = frozenset({"RASAI_CONSOLE_INI", "RASAI_CONFIG"})


@dataclass(frozen=True, slots=True)
class ConfigurationRegistration:
    name: str
    category: str
    catalog_ids: tuple[str, ...]
    sensitive: bool
    persist_session: bool
    persist_ini: bool
    persist_windows_user: bool
    default: str | None
    default_policy: str
    source: str

    @property
    def shared(self) -> bool:
        return len(self.catalog_ids) > 1


def _is_sensitive(spec: Any) -> bool:
    from rasai.console_config import is_secret

    return bool(getattr(spec, "sensitive", False)) or is_secret(str(spec.name))


def _catalog_owners() -> dict[str, set[str]]:
    from rasai.audit_catalog import CATALOGS
    from rasai.console_ui_catalog import capability_specs

    owners: dict[str, set[str]] = {}
    for catalog in CATALOGS:
        for capability_id in catalog.capability_ids:
            for spec in capability_specs(capability_id):
                owners.setdefault(str(spec.name), set()).add(catalog.id)
    return owners


def build_configuration_registry() -> tuple[ConfigurationRegistration, ...]:
    """Return the complete installed console configuration inventory."""
    from rasai import console_provider_environment as facade

    specs = facade.refresh_specs()
    owners = _catalog_owners()
    result: list[ConfigurationRegistration] = []
    for spec in specs:
        name = str(spec.name)
        sensitive = _is_sensitive(spec)
        default = None if getattr(spec, "default", None) is None else str(spec.default)
        result.append(
            ConfigurationRegistration(
                name=name,
                category=str(getattr(spec, "category", "") or ""),
                catalog_ids=tuple(sorted(owners.get(name, ()))),
                sensitive=sensitive,
                persist_session=True,
                persist_ini=(not sensitive and name not in _BOOTSTRAP_ENV_NAMES),
                persist_windows_user=sensitive,
                default=default,
                default_policy="canonical" if default is not None else "conditional-or-unset",
                source=str(getattr(spec, "source", "") or ""),
            )
        )
    return tuple(result)


def catalog_configuration_partition(
    catalog_id: str,
) -> tuple[tuple[ConfigurationRegistration, ...], tuple[ConfigurationRegistration, ...]]:
    """Return exclusive and shared configuration registrations for one CAT-*."""
    target = str(catalog_id).strip().upper()
    owned = tuple(item for item in build_configuration_registry() if target in item.catalog_ids)
    exclusive = tuple(item for item in owned if item.catalog_ids == (target,))
    shared = tuple(item for item in owned if item.catalog_ids != (target,))
    return exclusive, shared
