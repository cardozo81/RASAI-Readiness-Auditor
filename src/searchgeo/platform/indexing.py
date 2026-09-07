"""Index immutable AUD workspaces into the central RASAI platform catalog."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlsplit

from searchgeo.monitoring.reader import read_audit_snapshot

from .models import AuditIndexRecord
from .store import PlatformStore, file_sha256, normalize_origin, utc_now


@dataclass(frozen=True, slots=True)
class AuditIndexIssue:
    workspace: str
    error: str


@dataclass(frozen=True, slots=True)
class AuditIndexSummary:
    scanned: int
    indexed: int
    unchanged: int
    rejected: int
    issues: tuple[AuditIndexIssue, ...]


def _primary_origin(urls: Iterable[str], domains: Iterable[str]) -> str:
    origins: list[str] = []
    for url in urls:
        parts = urlsplit(url)
        if parts.scheme in {"http", "https"} and parts.hostname:
            port = f":{parts.port}" if parts.port else ""
            origins.append(f"{parts.scheme.lower()}://{parts.hostname.lower()}{port}")
    if origins:
        return sorted(set(origins))[0]
    domain_list = sorted({item.strip().lower() for item in domains if item and item.strip()})
    if domain_list:
        return normalize_origin(domain_list[0])
    raise ValueError("audit has no HTTP(S) URL/origin that can be mapped to a Property")


def index_audit_workspace(
    store: PlatformStore,
    workspace: str | Path,
    *,
    environment_name: str = "Production",
    environment_kind: str = "PRODUCTION",
) -> tuple[AuditIndexRecord, bool]:
    root = Path(workspace)
    snapshot = read_audit_snapshot(root)
    origin = _primary_origin(snapshot.urls, snapshot.domains)
    _, _, _, prop, environment = store.ensure_local_hierarchy(
        project_name=snapshot.project_name,
        origin=origin,
        environment_name=environment_name,
        environment_kind=environment_kind,
    )
    digest = file_sha256(root / "audit.db")
    existing = store.get_audit(snapshot.audit_id)
    unchanged = bool(existing and existing.audit_db_sha256 == digest)
    record = AuditIndexRecord(
        audit_id=snapshot.audit_id,
        property_id=prop.property_id,
        environment_id=environment.environment_id,
        workspace_path=str(root.resolve()),
        audit_db_sha256=digest,
        event_time=snapshot.event_time,
        status=snapshot.status,
        completion_status=snapshot.completion_status,
        project_name=snapshot.project_name,
        auditor_version=snapshot.auditor_version,
        ruleset_version=snapshot.ruleset_version,
        scoring_versions=snapshot.scoring_versions,
        domains=snapshot.domains,
        devices=snapshot.devices,
        url_count=len(snapshot.urls),
        indexed_at=utc_now(),
    )
    store.upsert_audit(record)
    return record, unchanged


def iter_audit_workspaces(audits_root: str | Path) -> Iterable[Path]:
    root = Path(audits_root)
    if not root.exists():
        return ()
    return tuple(
        candidate
        for candidate in sorted(root.iterdir())
        if candidate.is_dir() and candidate.name.startswith("AUD-") and (candidate / "audit.db").is_file()
    )


def index_audits(
    store: PlatformStore,
    audits_root: str | Path,
    *,
    strict: bool = False,
    environment_name: str = "Production",
    environment_kind: str = "PRODUCTION",
) -> AuditIndexSummary:
    scanned = indexed = unchanged = rejected = 0
    issues: list[AuditIndexIssue] = []
    for workspace in iter_audit_workspaces(audits_root):
        scanned += 1
        try:
            _, was_unchanged = index_audit_workspace(
                store,
                workspace,
                environment_name=environment_name,
                environment_kind=environment_kind,
            )
            if was_unchanged:
                unchanged += 1
            else:
                indexed += 1
        except (OSError, ValueError, RuntimeError) as exc:
            rejected += 1
            issues.append(AuditIndexIssue(str(workspace), str(exc)))
            if strict:
                raise
    return AuditIndexSummary(scanned, indexed, unchanged, rejected, tuple(issues))
