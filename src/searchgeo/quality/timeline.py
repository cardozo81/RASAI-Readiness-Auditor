"""Historical evidence timeline built from immutable AUD workspaces."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from searchgeo.monitoring.reader import read_audit_snapshot


@dataclass(frozen=True, slots=True)
class TimelinePoint:
    audit_id: str
    event_time: str
    auditor_version: str
    ruleset_version: str
    scoring_versions: tuple[str, ...]
    domains: tuple[str, ...]
    devices: tuple[str, ...]
    url_count: int
    fail_count: int
    warning_count: int
    dimension_values: dict[str, float]
    page_states: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TimelineBundle:
    points: tuple[TimelinePoint, ...]
    domain_filter: str | None
    url_filter: str | None
    skipped: tuple[str, ...]


def build_timeline(
    audits_root: str | Path,
    *,
    domain: str | None = None,
    url: str | None = None,
) -> TimelineBundle:
    root = Path(audits_root)
    points: list[TimelinePoint] = []
    skipped: list[str] = []
    domain_filter = domain.casefold().strip() if domain else None
    for database in sorted(root.glob("AUD-*/audit.db")):
        workspace = database.parent
        try:
            snapshot = read_audit_snapshot(workspace)
        except (OSError, ValueError, RuntimeError) as exc:
            skipped.append(f"{workspace.name}:{type(exc).__name__}:{exc}")
            continue
        if domain_filter and not any(item.casefold() == domain_filter for item in snapshot.domains):
            continue
        if url and url not in snapshot.urls:
            continue
        fail_count = 0
        warning_count = 0
        dimensions: dict[str, float] = {}
        page_states: dict[str, Any] = {}
        for signal in snapshot.signals.values():
            if url and signal.url not in {None, url}:
                continue
            if signal.domain == "RULE":
                value = str(signal.value).upper()
                fail_count += value == "FAIL"
                warning_count += value == "WARNING"
            elif signal.domain == "SCORE" and signal.value is not None:
                try:
                    dimensions[f"{signal.device or 'GLOBAL'}:{signal.label}"] = float(signal.value)
                except (TypeError, ValueError):
                    pass
            elif signal.domain == "PAGE" and (not url or signal.url == url):
                key = f"{signal.device or 'GLOBAL'}:{signal.label}"
                page_states[key] = signal.value
        points.append(
            TimelinePoint(
                audit_id=snapshot.audit_id,
                event_time=snapshot.event_time,
                auditor_version=snapshot.auditor_version,
                ruleset_version=snapshot.ruleset_version,
                scoring_versions=snapshot.scoring_versions,
                domains=snapshot.domains,
                devices=snapshot.devices,
                url_count=len(snapshot.urls),
                fail_count=fail_count,
                warning_count=warning_count,
                dimension_values=dimensions,
                page_states=page_states,
            )
        )
    points.sort(key=lambda item: (item.event_time, item.audit_id))
    return TimelineBundle(tuple(points), domain_filter, url, tuple(skipped))
