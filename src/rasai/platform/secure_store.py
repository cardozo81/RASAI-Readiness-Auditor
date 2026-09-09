"""Secret-safe persistence boundary shared by SQLite and PostgreSQL control planes.

This layer deliberately sits above database adapters. Domain data that may legitimately
contain arbitrary metadata is sanitized before persistence, while durable configuration
surfaces reject inline credentials and accept only references to environment/secret
management. Immutable AUD evidence and scoring are outside this store.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from rasai.secret_safety import (
    redact_text,
    redact_value,
    validate_command_argv_secret_free,
    validate_environment_reference,
    validate_secret_free_mapping,
)

from .central_store import CentralPlatformStore
from .models import ExternalDataset, Integration, Milestone, PageIdentity, Schedule, UsageEvent


def _safe_mapping(value: dict[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    sanitized = redact_value(value)
    return dict(sanitized) if isinstance(sanitized, dict) else {}


def _safe_optional_text(value: str | None) -> str | None:
    return None if value is None else redact_text(value)


class SecurePlatformStore(CentralPlatformStore):
    """Canonical control-plane store with provider-neutral secret safety."""

    def add_milestone(self, **kwargs: Any) -> Milestone:
        kwargs["metadata"] = _safe_mapping(kwargs.get("metadata"))
        kwargs["description"] = _safe_optional_text(kwargs.get("description"))
        return super().add_milestone(**kwargs)

    def record_comparison(self, **kwargs: Any) -> str:
        kwargs["manifest"] = _safe_mapping(kwargs.get("manifest"))
        return super().record_comparison(**kwargs)

    def create_page_identity(
        self,
        property_id: str,
        canonical_name: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> PageIdentity:
        return super().create_page_identity(
            property_id,
            canonical_name,
            metadata=_safe_mapping(metadata),
        )

    def add_schedule(self, **kwargs: Any) -> Schedule:
        command_argv = tuple(str(item) for item in kwargs.get("command_argv") or ())
        validate_command_argv_secret_free(command_argv)
        kwargs["command_argv"] = command_argv
        return super().add_schedule(**kwargs)

    def add_alert_rule(self, **kwargs: Any):
        destination_env = kwargs.get("destination_env")
        if destination_env is not None:
            kwargs["destination_env"] = validate_environment_reference(str(destination_env))
        return super().add_alert_rule(**kwargs)

    def add_notification(self, **kwargs: Any) -> str:
        kwargs["payload"] = _safe_mapping(kwargs.get("payload"))
        kwargs["delivery_error"] = _safe_optional_text(kwargs.get("delivery_error"))
        destination = kwargs.get("destination")
        if isinstance(destination, str):
            kwargs["destination"] = redact_text(destination)
        return super().add_notification(**kwargs)

    def add_integration(self, **kwargs: Any) -> Integration:
        secret_env = kwargs.get("secret_env")
        if secret_env is not None:
            kwargs["secret_env"] = validate_environment_reference(str(secret_env))
        configuration = kwargs.get("configuration") or {}
        if not isinstance(configuration, dict):
            raise ValueError("integration configuration must be a mapping")
        validate_secret_free_mapping(configuration, context="integration configuration")
        kwargs["configuration"] = _safe_mapping(configuration)
        return super().add_integration(**kwargs)

    def add_external_dataset(
        self,
        dataset: ExternalDataset,
        records: Iterable[dict[str, Any]],
    ) -> None:
        safe_dataset = replace(dataset, metadata=_safe_mapping(dataset.metadata))
        safe_records: list[dict[str, Any]] = []
        for record in records:
            sanitized = redact_value(record)
            if not isinstance(sanitized, dict):
                raise ValueError("external dataset record must be a mapping")
            safe_records.append(dict(sanitized))
        super().add_external_dataset(safe_dataset, safe_records)

    def add_usage_event(self, **kwargs: Any) -> UsageEvent:
        kwargs["metadata"] = _safe_mapping(kwargs.get("metadata"))
        return super().add_usage_event(**kwargs)
