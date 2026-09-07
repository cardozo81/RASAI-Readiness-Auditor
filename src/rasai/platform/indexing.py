"""Index immutable AUD workspaces into the central RASAi platform catalog."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterable
from urllib.parse import urlsplit

from rasai.monitoring.reader import read_audit_snapshot

from .central_store import CentralPlatformStore
from .models import AuditIndexRecord
from .store import file_sha256, normalize_origin, utc_now


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


def _target_origins(workspace: Path) -> tuple[str, ...]:
    """Read persisted target origins without mutating the immutable AUD."""
    database = workspace / "audit.db"
    uri = database.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        rows = connection.execute(
            "SELECT normalized_origin FROM audit_targets WHERE normalized_origin IS NOT NULL ORDER BY rowid"
        ).fetchall()
        return tuple(
            dict.fromkeys(
                normalize_origin(str(row[0])) for row in rows if str(row[0] or "").strip()
            )
        )
    finally:
        connection.close()


def _audit_origins(workspace: Path, urls: Iterable[str], domains: Iterable[str]) -> tuple[str, ...]:
    origins: list[str] = list(_target_origins(workspace))
    for url in urls:
        parts = urlsplit(url)
        if parts.scheme in {"http", "https"} and parts.hostname:
            port = f":{parts.port}" if parts.port else ""
            origins.append(f"{parts.scheme.lower()}://{parts.hostname.lower()}{port}")
    existing_hosts = {urlsplit(origin).hostname for origin in origins}
    for domain in domains:
        text = str(domain or "").strip().lower()
        if text and text not in existing_hosts:
            origins.append(normalize_origin(text))
    unique = tuple(sorted(dict.fromkeys(origins)))
    if not unique:
        raise ValueError("audit has no HTTP(S) origin that can be mapped to a Property")
    return unique


def index_audit_workspace(
    store: CentralPlatformStore,
    workspace: str | Path,
    *,
    environment_name: str = "Production",
    environment_kind: str = "PRODUCTION",
) -> tuple[AuditIndexRecord, bool]:
    root = Path(workspace)
    snapshot = read_audit_snapshot(root)
    origins = _audit_origins(root, snapshot.urls, snapshot.domains)
    scopes: list[tuple[str, str, str]] = []
    primary_prop = None
    primary_environment = None
    for index, origin in enumerate(origins):
        _, _, _, prop, environment = store.ensure_local_hierarchy(
            project_name=snapshot.project_name,
            origin=origin,
            environment_name=environment_name,
            environment_kind=environment_kind,
        )
        scopes.append((prop.property_id, environment.environment_id, origin))
        if index == 0:
            primary_prop = prop
            primary_environment = environment
    assert primary_prop is not None and primary_environment is not None

    digest = file_sha256(root / "audit.db")
    existing = store.get_audit(snapshot.audit_id)
    unchanged = bool(existing and existing.audit_db_sha256 == digest)
    record = AuditIndexRecord(
        audit_id=snapshot.audit_id,
        property_id=primary_prop.property_id,
        environment_id=primary_environment.environment_id,
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
    store.replace_audit_scopes(
        record.audit_id,
        scopes,
        primary_property_id=record.property_id,
        primary_environment_id=record.environment_id,
    )
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
    store: CentralPlatformStore,
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
        except (OSError, sqlite3.Error, ValueError, RuntimeError) as exc:
            rejected += 1
            issues.append(AuditIndexIssue(str(workspace), str(exc)))
            if strict:
                raise
    return AuditIndexSummary(scanned, indexed, unchanged, rejected, tuple(issues))
