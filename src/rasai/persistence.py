"""SQLite and filesystem persistence required by M1."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Generic, TypeVar

from rasai.domain import (
    ArchitectureClassification,
    Audit,
    AuditMode,
    AuditStatus,
    AuditTarget,
    CompletionStatus,
    DeviceContext,
    DiscoverySource,
    Evidence,
    EvidenceType,
    Finding,
    FindingDevice,
    Page,
    PageSnapshot,
    RuleExecution,
    RuleResult,
    Severity,
    TargetType,
    utc_now,
)


_SCHEMA_VERSION = 1
T = TypeVar("T")


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_load(value: str) -> Any:
    return json.loads(value)


def _datetime_dump(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime_load(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _require_page_scope(connection: sqlite3.Connection, audit_id: str, page_id: str | None) -> None:
    if page_id is None:
        return
    row = connection.execute("SELECT audit_id FROM pages WHERE page_id = ?", (page_id,)).fetchone()
    if row is None or row["audit_id"] != audit_id:
        raise sqlite3.IntegrityError(f"page {page_id} does not belong to audit {audit_id}")


def _require_snapshot_scope(
    connection: sqlite3.Connection,
    audit_id: str,
    page_id: str | None,
    snapshot_id: str | None,
    device: DeviceContext | None,
) -> None:
    if snapshot_id is None:
        return
    if page_id is None:
        raise sqlite3.IntegrityError(f"snapshot {snapshot_id} requires a page reference")
    row = connection.execute(
        """
        SELECT page_snapshots.page_id, page_snapshots.device, pages.audit_id
        FROM page_snapshots
        JOIN pages ON pages.page_id = page_snapshots.page_id
        WHERE page_snapshots.snapshot_id = ?
        """,
        (snapshot_id,),
    ).fetchone()
    if row is None or row["audit_id"] != audit_id or row["page_id"] != page_id:
        raise sqlite3.IntegrityError(
            f"snapshot {snapshot_id} does not belong to page {page_id} in audit {audit_id}"
        )
    if device is not None and row["device"] != device.value:
        raise sqlite3.IntegrityError(
            f"snapshot {snapshot_id} device {row['device']} does not match {device.value}"
        )


def _require_evidence_scope(
    connection: sqlite3.Connection,
    audit_id: str,
    evidence_ids: tuple[str, ...],
    page_id: str | None = None,
    snapshot_id: str | None = None,
    device: DeviceContext | None = None,
) -> None:
    for evidence_id in evidence_ids:
        row = connection.execute(
            "SELECT audit_id, page_id, snapshot_id, device FROM evidence WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()
        if row is None or row["audit_id"] != audit_id:
            raise sqlite3.IntegrityError(
                f"evidence {evidence_id} does not belong to audit {audit_id}"
            )
        if page_id is not None and row["page_id"] != page_id:
            raise sqlite3.IntegrityError(
                f"evidence {evidence_id} does not belong to page {page_id}"
            )
        if snapshot_id is not None and row["snapshot_id"] != snapshot_id:
            raise sqlite3.IntegrityError(
                f"evidence {evidence_id} does not belong to snapshot {snapshot_id}"
            )
        if device is not None and row["device"] != device.value:
            raise sqlite3.IntegrityError(
                f"evidence {evidence_id} device {row['device']} does not match {device.value}"
            )


def _require_rule_execution_scope(connection: sqlite3.Connection, finding: Finding) -> None:
    row = connection.execute(
        """
        SELECT audit_id, rule_id, page_id, device, evidence_ids
        FROM rule_executions
        WHERE rule_execution_id = ?
        """,
        (finding.rule_execution_id,),
    ).fetchone()
    if (
        row is None
        or row["audit_id"] != finding.audit_id
        or row["rule_id"] != finding.rule_id
        or row["page_id"] != finding.page_id
    ):
        raise sqlite3.IntegrityError(
            f"rule execution {finding.rule_execution_id} is inconsistent with finding {finding.finding_id}"
        )
    if finding.device in {FindingDevice.DESKTOP, FindingDevice.MOBILE} and row["device"] != finding.device.value:
        raise sqlite3.IntegrityError(
            f"rule execution {finding.rule_execution_id} device {row['device']} does not match finding {finding.device.value}"
        )
    execution_evidence_ids = set(_json_load(row["evidence_ids"]))
    if not set(finding.evidence_ids).issubset(execution_evidence_ids):
        raise sqlite3.IntegrityError(
            f"finding {finding.finding_id} references evidence outside its rule execution"
        )


class AuditWorkspace:
    """Filesystem paths owned by one audit."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.database = root / "audit.db"
        self.artifacts = root / "artifacts"

    @classmethod
    def create(cls, audits_root: str | Path, audit_id: str) -> "AuditWorkspace":
        root = Path(audits_root) / audit_id
        workspace = cls(root)
        workspace.root.mkdir(parents=True, exist_ok=False)
        workspace.artifacts.mkdir()
        return workspace

    @classmethod
    def open(cls, audit_root: str | Path) -> "AuditWorkspace":
        workspace = cls(Path(audit_root))
        if not workspace.root.is_dir():
            raise FileNotFoundError(f"audit workspace not found: {workspace.root}")
        if not workspace.database.is_file():
            raise FileNotFoundError(f"audit database not found: {workspace.database}")
        if not workspace.artifacts.is_dir():
            raise FileNotFoundError(f"audit artifacts directory not found: {workspace.artifacts}")
        return workspace


class _Repository(Generic[T]):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def _insert(self, sql: str, values: tuple[Any, ...]) -> None:
        with self._connection:
            self._connection.execute(sql, values)

    def _fetch_one(self, sql: str, values: tuple[Any, ...], mapper: Callable[[sqlite3.Row], T]) -> T | None:
        row = self._connection.execute(sql, values).fetchone()
        return None if row is None else mapper(row)


class AuditRepository(_Repository[Audit]):
    def add(self, audit: Audit) -> None:
        self._insert(
            """
            INSERT INTO audits (
                audit_id, project_name, status, completion_status, primary_language,
                market, max_pages, audit_mode, capabilities, limitations, created_at,
                started_at, completed_at, auditor_version, ruleset_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit.audit_id,
                audit.project_name,
                audit.status.value,
                audit.completion_status.value if audit.completion_status else None,
                audit.primary_language,
                audit.market,
                audit.max_pages,
                audit.audit_mode.value if audit.audit_mode else None,
                _json_dump(list(audit.capabilities)),
                _json_dump(list(audit.limitations)),
                _datetime_dump(audit.created_at),
                _datetime_dump(audit.started_at),
                _datetime_dump(audit.completed_at),
                audit.auditor_version,
                audit.ruleset_version,
            ),
        )

    def get(self, audit_id: str) -> Audit | None:
        return self._fetch_one(
            "SELECT * FROM audits WHERE audit_id = ?",
            (audit_id,),
            self._map,
        )

    def update(self, audit: Audit) -> None:
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE audits SET
                    project_name = ?, status = ?, completion_status = ?, primary_language = ?,
                    market = ?, max_pages = ?, audit_mode = ?, capabilities = ?, limitations = ?,
                    created_at = ?, started_at = ?, completed_at = ?, auditor_version = ?,
                    ruleset_version = ?
                WHERE audit_id = ?
                """,
                (
                    audit.project_name,
                    audit.status.value,
                    audit.completion_status.value if audit.completion_status else None,
                    audit.primary_language,
                    audit.market,
                    audit.max_pages,
                    audit.audit_mode.value if audit.audit_mode else None,
                    _json_dump(list(audit.capabilities)),
                    _json_dump(list(audit.limitations)),
                    _datetime_dump(audit.created_at),
                    _datetime_dump(audit.started_at),
                    _datetime_dump(audit.completed_at),
                    audit.auditor_version,
                    audit.ruleset_version,
                    audit.audit_id,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError(f"audit not found: {audit.audit_id}")

    def complete(
        self,
        audit_id: str,
        completion_status: CompletionStatus,
        completed_at: datetime | None = None,
    ) -> Audit:
        audit = self.get(audit_id)
        if audit is None:
            raise KeyError(f"audit not found: {audit_id}")
        completed = replace(
            audit,
            status=AuditStatus.COMPLETED,
            completion_status=completion_status,
            completed_at=completed_at or utc_now(),
        )
        self.update(completed)
        return completed

    @staticmethod
    def _map(row: sqlite3.Row) -> Audit:
        return Audit(
            audit_id=row["audit_id"],
            project_name=row["project_name"],
            status=AuditStatus(row["status"]),
            completion_status=CompletionStatus(row["completion_status"]) if row["completion_status"] else None,
            primary_language=row["primary_language"],
            market=row["market"],
            max_pages=row["max_pages"],
            audit_mode=AuditMode(row["audit_mode"]) if row["audit_mode"] else None,
            capabilities=tuple(_json_load(row["capabilities"])),
            limitations=tuple(_json_load(row["limitations"])),
            created_at=_datetime_load(row["created_at"]),
            started_at=_datetime_load(row["started_at"]),
            completed_at=_datetime_load(row["completed_at"]),
            auditor_version=row["auditor_version"],
            ruleset_version=row["ruleset_version"],
        )


class AuditTargetRepository(_Repository[AuditTarget]):
    def add(self, target: AuditTarget) -> None:
        self._insert(
            "INSERT INTO audit_targets VALUES (?, ?, ?, ?, ?)",
            (target.target_id, target.audit_id, target.input_url, target.normalized_origin, target.target_type.value),
        )

    def get(self, target_id: str) -> AuditTarget | None:
        return self._fetch_one(
            "SELECT * FROM audit_targets WHERE target_id = ?",
            (target_id,),
            lambda row: AuditTarget(
                target_id=row["target_id"],
                audit_id=row["audit_id"],
                input_url=row["input_url"],
                normalized_origin=row["normalized_origin"],
                target_type=TargetType(row["target_type"]),
            ),
        )


class PageRepository(_Repository[Page]):
    def add(self, page: Page) -> None:
        self._insert(
            "INSERT INTO pages VALUES (?, ?, ?, ?, ?, ?)",
            (
                page.page_id,
                page.audit_id,
                page.normalized_url,
                page.discovered_url,
                _json_dump([source.value for source in page.discovery_sources]),
                page.depth,
            ),
        )

    def get(self, page_id: str) -> Page | None:
        return self._fetch_one(
            "SELECT * FROM pages WHERE page_id = ?",
            (page_id,),
            lambda row: Page(
                page_id=row["page_id"],
                audit_id=row["audit_id"],
                normalized_url=row["normalized_url"],
                discovered_url=row["discovered_url"],
                discovery_sources=tuple(DiscoverySource(value) for value in _json_load(row["discovery_sources"])),
                depth=row["depth"],
            ),
        )


class PageSnapshotRepository(_Repository[PageSnapshot]):
    def add(self, snapshot: PageSnapshot) -> None:
        self._insert(
            """
            INSERT INTO page_snapshots VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                snapshot.snapshot_id,
                snapshot.page_id,
                snapshot.device.value,
                snapshot.requested_url,
                snapshot.final_url,
                _datetime_dump(snapshot.captured_at),
                snapshot.http_status,
                snapshot.content_type,
                snapshot.title,
                snapshot.description,
                snapshot.canonical,
                snapshot.meta_robots,
                snapshot.rendering_mode,
                snapshot.raw_artifact_ref,
                snapshot.rendered_artifact_ref,
                snapshot.main_content_ref,
                snapshot.structured_data_ref,
                _json_dump(snapshot.browser_metadata),
                snapshot.architecture_classification.value,
            ),
        )

    def get(self, snapshot_id: str) -> PageSnapshot | None:
        return self._fetch_one(
            "SELECT * FROM page_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
            self._map,
        )

    @staticmethod
    def _map(row: sqlite3.Row) -> PageSnapshot:
        return PageSnapshot(
            snapshot_id=row["snapshot_id"],
            page_id=row["page_id"],
            device=DeviceContext(row["device"]),
            requested_url=row["requested_url"],
            final_url=row["final_url"],
            captured_at=_datetime_load(row["captured_at"]),
            http_status=row["http_status"],
            content_type=row["content_type"],
            title=row["title"],
            description=row["description"],
            canonical=row["canonical"],
            meta_robots=row["meta_robots"],
            rendering_mode=row["rendering_mode"],
            raw_artifact_ref=row["raw_artifact_ref"],
            rendered_artifact_ref=row["rendered_artifact_ref"],
            main_content_ref=row["main_content_ref"],
            structured_data_ref=row["structured_data_ref"],
            browser_metadata=_json_load(row["browser_metadata"]),
            architecture_classification=ArchitectureClassification(row["architecture_classification"]),
        )


class EvidenceRepository(_Repository[Evidence]):
    def add(self, evidence: Evidence) -> None:
        _require_page_scope(self._connection, evidence.audit_id, evidence.page_id)
        _require_snapshot_scope(
            self._connection,
            evidence.audit_id,
            evidence.page_id,
            evidence.snapshot_id,
            evidence.device,
        )
        self._insert(
            "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                evidence.evidence_id,
                evidence.audit_id,
                evidence.page_id,
                evidence.snapshot_id,
                evidence.device.value if evidence.device else None,
                evidence.evidence_type.value,
                evidence.source,
                _json_dump(evidence.observed_value),
                evidence.artifact_reference,
                _datetime_dump(evidence.captured_at),
            ),
        )

    def get(self, evidence_id: str) -> Evidence | None:
        return self._fetch_one(
            "SELECT * FROM evidence WHERE evidence_id = ?",
            (evidence_id,),
            lambda row: Evidence(
                evidence_id=row["evidence_id"],
                audit_id=row["audit_id"],
                page_id=row["page_id"],
                snapshot_id=row["snapshot_id"],
                device=DeviceContext(row["device"]) if row["device"] else None,
                evidence_type=EvidenceType(row["evidence_type"]),
                source=row["source"],
                observed_value=_json_load(row["observed_value"]),
                artifact_reference=row["artifact_reference"],
                captured_at=_datetime_load(row["captured_at"]),
            ),
        )


class RuleExecutionRepository(_Repository[RuleExecution]):
    def add(self, execution: RuleExecution) -> None:
        _require_page_scope(self._connection, execution.audit_id, execution.page_id)
        _require_snapshot_scope(
            self._connection,
            execution.audit_id,
            execution.page_id,
            execution.snapshot_id,
            execution.device,
        )
        _require_evidence_scope(
            self._connection,
            execution.audit_id,
            execution.evidence_ids,
            execution.page_id,
            execution.snapshot_id,
            execution.device,
        )
        self._insert(
            "INSERT INTO rule_executions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                execution.rule_execution_id,
                execution.audit_id,
                execution.rule_id,
                execution.rule_version,
                execution.page_id,
                execution.snapshot_id,
                execution.device.value if execution.device else None,
                execution.result.value,
                _json_dump(execution.observed_value),
                execution.expected_condition,
                _json_dump(list(execution.evidence_ids)),
                _datetime_dump(execution.executed_at),
                execution.error,
            ),
        )

    def get(self, rule_execution_id: str) -> RuleExecution | None:
        return self._fetch_one(
            "SELECT * FROM rule_executions WHERE rule_execution_id = ?",
            (rule_execution_id,),
            lambda row: RuleExecution(
                rule_execution_id=row["rule_execution_id"],
                audit_id=row["audit_id"],
                rule_id=row["rule_id"],
                rule_version=row["rule_version"],
                page_id=row["page_id"],
                snapshot_id=row["snapshot_id"],
                device=DeviceContext(row["device"]) if row["device"] else None,
                result=RuleResult(row["result"]),
                observed_value=_json_load(row["observed_value"]),
                expected_condition=row["expected_condition"],
                evidence_ids=tuple(_json_load(row["evidence_ids"])),
                executed_at=_datetime_load(row["executed_at"]),
                error=row["error"],
            ),
        )


class FindingRepository(_Repository[Finding]):
    def add(self, finding: Finding) -> None:
        _require_page_scope(self._connection, finding.audit_id, finding.page_id)
        _require_evidence_scope(self._connection, finding.audit_id, finding.evidence_ids)
        _require_rule_execution_scope(self._connection, finding)
        self._insert(
            "INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                finding.finding_id,
                finding.audit_id,
                finding.rule_id,
                finding.rule_execution_id,
                finding.page_id,
                finding.device.value,
                finding.category,
                finding.severity.value,
                finding.source,
                finding.title,
                _json_dump(finding.observed_value),
                finding.expected_condition,
                _json_dump(list(finding.evidence_ids)),
                finding.status,
            ),
        )

    def get(self, finding_id: str) -> Finding | None:
        return self._fetch_one(
            "SELECT * FROM findings WHERE finding_id = ?",
            (finding_id,),
            lambda row: Finding(
                finding_id=row["finding_id"],
                audit_id=row["audit_id"],
                rule_id=row["rule_id"],
                rule_execution_id=row["rule_execution_id"],
                page_id=row["page_id"],
                device=FindingDevice(row["device"]),
                category=row["category"],
                severity=Severity(row["severity"]),
                source=row["source"],
                title=row["title"],
                observed_value=_json_load(row["observed_value"]),
                expected_condition=row["expected_condition"],
                evidence_ids=tuple(_json_load(row["evidence_ids"])),
                status=row["status"],
            ),
        )


class AuditPersistence:
    """Own the SQLite connection and M1 repositories for one audit workspace."""

    def __init__(self, workspace: AuditWorkspace) -> None:
        self.workspace = workspace
        self._connection = sqlite3.connect(workspace.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()

        self.audits = AuditRepository(self._connection)
        self.targets = AuditTargetRepository(self._connection)
        self.pages = PageRepository(self._connection)
        self.snapshots = PageSnapshotRepository(self._connection)
        self.evidence = EvidenceRepository(self._connection)
        self.rule_executions = RuleExecutionRepository(self._connection)
        self.findings = FindingRepository(self._connection)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "AuditPersistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _initialize_schema(self) -> None:
        with self._connection:
            current_version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if current_version not in {0, _SCHEMA_VERSION}:
                raise RuntimeError(
                    f"unsupported audit.db schema version {current_version}; expected {_SCHEMA_VERSION}"
                )

            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS audits (
                    audit_id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    completion_status TEXT,
                    primary_language TEXT NOT NULL,
                    market TEXT NOT NULL,
                    max_pages INTEGER NOT NULL,
                    audit_mode TEXT,
                    capabilities TEXT NOT NULL,
                    limitations TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    auditor_version TEXT NOT NULL,
                    ruleset_version TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_targets (
                    target_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    input_url TEXT NOT NULL,
                    normalized_origin TEXT NOT NULL,
                    target_type TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pages (
                    page_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    normalized_url TEXT NOT NULL,
                    discovered_url TEXT NOT NULL,
                    discovery_sources TEXT NOT NULL,
                    depth INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS page_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    device TEXT NOT NULL,
                    requested_url TEXT NOT NULL,
                    final_url TEXT,
                    captured_at TEXT NOT NULL,
                    http_status INTEGER,
                    content_type TEXT,
                    title TEXT,
                    description TEXT,
                    canonical TEXT,
                    meta_robots TEXT,
                    rendering_mode TEXT,
                    raw_artifact_ref TEXT,
                    rendered_artifact_ref TEXT,
                    main_content_ref TEXT,
                    structured_data_ref TEXT,
                    browser_metadata TEXT NOT NULL,
                    architecture_classification TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,
                    snapshot_id TEXT REFERENCES page_snapshots(snapshot_id) ON DELETE CASCADE,
                    device TEXT,
                    evidence_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    observed_value TEXT NOT NULL,
                    artifact_reference TEXT,
                    captured_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS rule_executions (
                    rule_execution_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    rule_id TEXT NOT NULL,
                    rule_version TEXT NOT NULL,
                    page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,
                    snapshot_id TEXT REFERENCES page_snapshots(snapshot_id) ON DELETE CASCADE,
                    device TEXT,
                    result TEXT NOT NULL,
                    observed_value TEXT NOT NULL,
                    expected_condition TEXT,
                    evidence_ids TEXT NOT NULL,
                    executed_at TEXT NOT NULL,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS findings (
                    finding_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    rule_id TEXT NOT NULL,
                    rule_execution_id TEXT NOT NULL REFERENCES rule_executions(rule_execution_id) ON DELETE CASCADE,
                    page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,
                    device TEXT NOT NULL,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    observed_value TEXT NOT NULL,
                    expected_condition TEXT,
                    evidence_ids TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                """
            )
            self._connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
