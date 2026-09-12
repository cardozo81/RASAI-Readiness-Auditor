"""Interactive-console reconciliation for standards service settings."""
from __future__ import annotations

from pathlib import Path

from rasai.standards_runtime import install_console_service_catalog
from rasai.standards_service_registry import (
    STANDARDS_MAX_URLS_ENV,
    STANDARDS_TIMEOUT_ENV,
    WEB_FEATURES_DATASET_ENV,
    boolean_value,
    services,
)


def install() -> None:
    install_console_service_catalog()
    from rasai import console_environment as legacy
    from rasai import console_provider_environment as facade

    if getattr(legacy, "_rasai_standards_console_validation", False):
        facade.CATEGORIES = legacy.CATEGORIES
        facade.refresh_specs()
        return

    enabled_names = {item.enabled_env for item in services()}
    original_validate = legacy._validate

    def validate(name: str, raw: str) -> str:
        value = str(raw).strip()
        if name in enabled_names:
            boolean_value(value, default=False)
            return "true" if value.casefold() in {"1", "true", "yes", "on"} else "false"
        if name == STANDARDS_MAX_URLS_ENV:
            parsed = int(value)
            if parsed < 0:
                raise ValueError(f"{name}: use inteiro >= 0")
            return str(parsed)
        if name == STANDARDS_TIMEOUT_ENV:
            parsed = float(value)
            if parsed <= 0 or parsed >= 3600:
                raise ValueError(f"{name}: use número > 0 e < 3600")
            return f"{parsed:g}"
        if name == WEB_FEATURES_DATASET_ENV:
            path = Path(value).expanduser()
            if not path.is_file():
                raise ValueError(f"{name}: dataset configurado não existe")
            return str(path)
        return original_validate(name, raw)

    legacy._validate = validate
    legacy._rasai_standards_console_validation = True
    facade.CATEGORIES = legacy.CATEGORIES
    facade.refresh_specs()
