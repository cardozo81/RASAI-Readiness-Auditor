"""Rebuildable analytical index for consolidated reporting.

The index is a disposable cache. Source ``AUD-*/audit.db`` files remain the sole
source of truth and are never modified by this module.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import hashlib
import json
import sqlite3
from typing import Any, Iterable

from .models import ConsolidationFilter, RefreshIssue, RefreshResult
from .reader import read_audit_bundle, source_file_fingerprint

INDEX_SCHEMA_VERSION = 1


class ConsolidationIndex:
    def __init__(self, audits_root: str | Path) -> None:
        self.audits_root = Path(audits_root)
        self.index_dir = self.audits_root / ".searchgeo"
        self.path = self.index_dir / "consolidated-index.db"

    def _connect(self) -> sqlite3.Connection:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        self._initialize(connection)
        return connection

    @contextmanager
    def _session(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _initialize(connection: sqlite3.Connection) -> None:
        current = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current not in {0, INDEX_SCHEMA_VERSION}:
            raise RuntimeError(
                f"unsupported consolidation index schema {current}; expected {INDEX_SCHEMA_VERSION}"
            )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_audits (
                audit_id TEXT PRIMARY KEY,
                db_path TEXT NOT NULL UNIQUE,
                source_fingerprint TEXT NOT NULL,
                project_name TEXT NOT NULL,
                status TEXT NOT NULL,
                completion_status TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                event_time TEXT NOT NULL,
                auditor_version TEXT NOT NULL,
                ruleset_version TEXT NOT NULL,
                devices_json TEXT NOT NULL,
                url_count INTEGER NOT NULL,
                indexed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_domains (
                audit_id TEXT NOT NULL REFERENCES source_audits(audit_id) ON DELETE CASCADE,
                domain TEXT NOT NULL,
                PRIMARY KEY (audit_id, domain)
            );
            CREATE TABLE IF NOT EXISTS audit_urls (
                audit_id TEXT NOT NULL REFERENCES source_audits(audit_id) ON DELETE CASCADE,
                url TEXT NOT NULL,
                PRIMARY KEY (audit_id, url)
            );
            CREATE TABLE IF NOT EXISTS score_points (
                audit_id TEXT NOT NULL REFERENCES source_audits(audit_id) ON DELETE CASCADE,
                device TEXT NOT NULL,
                dimension TEXT NOT NULL,
                value REAL,
                coverage REAL,
                confidence TEXT,
                consolidation_status TEXT,
                scoring_version TEXT,
                calculated_at TEXT,
                PRIMARY KEY (audit_id, device, dimension, scoring_version)
            );
            CREATE TABLE IF NOT EXISTS performance_points (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id TEXT NOT NULL REFERENCES source_audits(audit_id) ON DELETE CASCADE,
                url TEXT NOT NULL,
                device TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                status TEXT,
                strategy TEXT,
                performance_score REAL,
                accessibility_score REAL,
                best_practices_score REAL,
                seo_score REAL,
                fcp_lab_ms REAL,
                speed_index_lab_ms REAL,
                lcp_lab_ms REAL,
                tbt_lab_ms REAL,
                cls_lab REAL,
                field_source TEXT,
                field_scope TEXT,
                lcp_p75_ms REAL,
                inp_p75_ms REAL,
                cls_p75 REAL,
                cwv_assessment TEXT
            );
            CREATE TABLE IF NOT EXISTS apdex_points (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id TEXT NOT NULL REFERENCES source_audits(audit_id) ON DELETE CASCADE,
                url TEXT NOT NULL,
                device TEXT NOT NULL,
                calculated_at TEXT NOT NULL,
                profile_id TEXT,
                threshold_seconds REAL,
                valid_samples INTEGER,
                invalid_samples INTEGER,
                satisfied_count INTEGER,
                tolerating_count INTEGER,
                frustrated_count INTEGER,
                apdex_score REAL,
                small_group INTEGER,
                final_group INTEGER,
                median_ms REAL,
                p75_ms REAL,
                p90_ms REAL,
                p95_ms REAL,
                p99_ms REAL,
                trend_percent REAL
            );
            CREATE TABLE IF NOT EXISTS finding_points (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                audit_id TEXT NOT NULL REFERENCES source_audits(audit_id) ON DELETE CASCADE,
                device TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT NOT NULL,
                page_id TEXT,
                url TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_source_event ON source_audits(event_time);
            CREATE INDEX IF NOT EXISTS idx_domains_domain ON audit_domains(domain,audit_id);
            CREATE INDEX IF NOT EXISTS idx_urls_url ON audit_urls(url,audit_id);
            CREATE INDEX IF NOT EXISTS idx_scores_dim ON score_points(device,dimension,audit_id);
            CREATE INDEX IF NOT EXISTS idx_perf_filter ON performance_points(device,url,audit_id);
            CREATE INDEX IF NOT EXISTS idx_apdex_filter ON apdex_points(device,url,audit_id);
            CREATE INDEX IF NOT EXISTS idx_findings_filter ON finding_points(device,url,audit_id);
            """
        )
        connection.execute(f"PRAGMA user_version = {INDEX_SCHEMA_VERSION}")
        connection.commit()

    def _discover(self) -> tuple[Path, ...]:
        if not self.audits_root.is_dir():
            return ()
        return tuple(sorted(
            path / "audit.db"
            for path in self.audits_root.iterdir()
            if path.is_dir() and path.name.startswith("AUD-") and (path / "audit.db").is_file()
        ))

    def refresh(self) -> RefreshResult:
        discovered = self._discover()
        issues: list[RefreshIssue] = []
        indexed = reused = removed = 0
        with self._session() as connection:
            existing = {
                str(row["db_path"]): (str(row["audit_id"]), str(row["source_fingerprint"]))
                for row in connection.execute(
                    "SELECT audit_id,db_path,source_fingerprint FROM source_audits"
                ).fetchall()
            }
            discovered_rel = {self._relative(path): path for path in discovered}
            stale = set(existing) - set(discovered_rel)
            if stale:
                with connection:
                    for rel in stale:
                        connection.execute("DELETE FROM source_audits WHERE db_path=?", (rel,))
                        removed += 1

            by_audit_id = {
                str(row["audit_id"]): str(row["db_path"])
                for row in connection.execute("SELECT audit_id,db_path FROM source_audits").fetchall()
            }
            for rel, db_path in discovered_rel.items():
                try:
                    fingerprint = source_file_fingerprint(db_path)
                except OSError as exc:
                    issues.append(RefreshIssue(rel, f"stat failed: {exc}"))
                    continue
                prior = existing.get(rel)
                if prior and prior[1] == fingerprint:
                    reused += 1
                    continue
                try:
                    bundle = read_audit_bundle(db_path)
                    conflict = by_audit_id.get(bundle.source.audit_id)
                    if conflict is not None and conflict != rel:
                        raise ValueError(
                            f"duplicate audit_id {bundle.source.audit_id} already indexed from {conflict}"
                        )
                    self._replace_bundle(connection, rel, bundle)
                    by_audit_id[bundle.source.audit_id] = rel
                    indexed += 1
                except (OSError, sqlite3.Error, ValueError) as exc:
                    issues.append(RefreshIssue(rel, f"{type(exc).__name__}: {exc}"))
        return RefreshResult(
            discovered=len(discovered), indexed=indexed, reused=reused, removed=removed,
            issues=tuple(issues),
        )

    def _relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.audits_root.resolve()).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    @staticmethod
    def _replace_bundle(connection: sqlite3.Connection, rel: str, bundle: Any) -> None:
        src = bundle.source
        now = datetime.now().astimezone().isoformat()
        with connection:
            connection.execute("DELETE FROM source_audits WHERE audit_id=? OR db_path=?", (src.audit_id, rel))
            connection.execute(
                """INSERT INTO source_audits(
                    audit_id,db_path,source_fingerprint,project_name,status,completion_status,
                    created_at,started_at,completed_at,event_time,auditor_version,ruleset_version,
                    devices_json,url_count,indexed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    src.audit_id, rel, src.source_fingerprint, src.project_name, src.status,
                    src.completion_status, src.created_at, src.started_at, src.completed_at,
                    src.event_time, src.auditor_version, src.ruleset_version,
                    json.dumps(src.devices, ensure_ascii=False), len(src.urls), now,
                ),
            )
            connection.executemany(
                "INSERT INTO audit_domains(audit_id,domain) VALUES (?,?)",
                ((src.audit_id, item) for item in src.domains),
            )
            connection.executemany(
                "INSERT INTO audit_urls(audit_id,url) VALUES (?,?)",
                ((src.audit_id, item) for item in src.urls),
            )
            for row in bundle.scores:
                connection.execute(
                    """INSERT OR REPLACE INTO score_points(
                        audit_id,device,dimension,value,coverage,confidence,consolidation_status,
                        scoring_version,calculated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        src.audit_id, row.get("device") or "UNKNOWN", row.get("dimension") or "UNKNOWN",
                        row.get("value"), row.get("coverage"), row.get("confidence"),
                        row.get("consolidation_status"), row.get("scoring_version") or "UNKNOWN",
                        row.get("calculated_at"),
                    ),
                )
            for row in bundle.performance:
                connection.execute(
                    """INSERT INTO performance_points(
                        audit_id,url,device,captured_at,status,strategy,performance_score,
                        accessibility_score,best_practices_score,seo_score,fcp_lab_ms,
                        speed_index_lab_ms,lcp_lab_ms,tbt_lab_ms,cls_lab,field_source,field_scope,
                        lcp_p75_ms,inp_p75_ms,cls_p75,cwv_assessment
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        src.audit_id, row.get("url") or "", row.get("device") or "UNKNOWN",
                        row.get("captured_at") or src.event_time, row.get("status"), row.get("strategy"),
                        row.get("performance_score"), row.get("accessibility_score"),
                        row.get("best_practices_score"), row.get("seo_score"), row.get("fcp_lab_ms"),
                        row.get("speed_index_lab_ms"), row.get("lcp_lab_ms"), row.get("tbt_lab_ms"),
                        row.get("cls_lab"), row.get("field_source"), row.get("field_scope"),
                        row.get("lcp_p75_ms"), row.get("inp_p75_ms"), row.get("cls_p75"),
                        row.get("cwv_assessment"),
                    ),
                )
            for row in bundle.apdex:
                connection.execute(
                    """INSERT INTO apdex_points(
                        audit_id,url,device,calculated_at,profile_id,threshold_seconds,valid_samples,
                        invalid_samples,satisfied_count,tolerating_count,frustrated_count,apdex_score,
                        small_group,final_group,median_ms,p75_ms,p90_ms,p95_ms,p99_ms,trend_percent
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        src.audit_id, row.get("url") or "", row.get("device") or "UNKNOWN",
                        row.get("calculated_at") or src.event_time, row.get("profile_id"),
                        row.get("threshold_seconds"), row.get("valid_samples"), row.get("invalid_samples"),
                        row.get("satisfied_count"), row.get("tolerating_count"), row.get("frustrated_count"),
                        row.get("apdex_score"), row.get("small_group"), row.get("final_group"),
                        row.get("median_ms"), row.get("p75_ms"), row.get("p90_ms"), row.get("p95_ms"),
                        row.get("p99_ms"), row.get("trend_percent"),
                    ),
                )
            for row in bundle.findings:
                connection.execute(
                    """INSERT INTO finding_points(audit_id,device,severity,category,page_id,url)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        src.audit_id, row.get("device") or "UNKNOWN", row.get("severity") or "UNKNOWN",
                        row.get("category") or "UNKNOWN", row.get("page_id"), row.get("url"),
                    ),
                )

    @staticmethod
    def _where(filters: ConsolidationFilter, alias: str = "a") -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if filters.date_from:
            clauses.append(f"date({alias}.event_time) >= date(?)")
            params.append(filters.date_from.isoformat())
        if filters.date_to:
            clauses.append(f"date({alias}.event_time) <= date(?)")
            params.append(filters.date_to.isoformat())
        if filters.domains:
            placeholders = ",".join("?" for _ in filters.domains)
            clauses.append(
                f"EXISTS (SELECT 1 FROM audit_domains d WHERE d.audit_id={alias}.audit_id "
                f"AND lower(d.domain) IN ({placeholders}))"
            )
            params.extend(item.casefold() for item in filters.domains)
        return (" AND ".join(clauses) if clauses else "1=1"), params

    def candidate_audits(self, filters: ConsolidationFilter) -> tuple[dict[str, Any], ...]:
        where, params = self._where(filters)
        device_clause = ""
        if filters.devices:
            placeholders = ",".join("?" for _ in filters.devices)
            device_clause = (
                f" AND EXISTS (SELECT 1 FROM json_each(a.devices_json) j "
                f"WHERE upper(j.value) IN ({placeholders}))"
            )
            params.extend(item.upper() for item in filters.devices)
        url_clause = ""
        if filters.urls:
            placeholders = ",".join("?" for _ in filters.urls)
            url_clause = (
                f" AND EXISTS (SELECT 1 FROM audit_urls au WHERE au.audit_id=a.audit_id "
                f"AND au.url IN ({placeholders}))"
            )
            params.extend(filters.urls)
        with self._session() as connection:
            rows = connection.execute(
                f"SELECT * FROM source_audits a WHERE upper(a.status)='COMPLETED' AND ({where}){device_clause}{url_clause} ORDER BY event_time,audit_id",
                params,
            ).fetchall()
            return tuple(dict(row) for row in rows)

    def available_domains(self) -> tuple[str, ...]:
        with self._session() as connection:
            return tuple(str(row[0]) for row in connection.execute(
                "SELECT DISTINCT domain FROM audit_domains ORDER BY domain"
            ).fetchall())

    def available_dates(self, filters: ConsolidationFilter | None = None) -> tuple[str | None, str | None]:
        filters = filters or ConsolidationFilter()
        where, params = self._where(filters)
        with self._session() as connection:
            row = connection.execute(
                f"SELECT min(date(event_time)),max(date(event_time)) FROM source_audits a WHERE {where}",
                params,
            ).fetchone()
            return (row[0], row[1]) if row else (None, None)

    def available_devices(self, filters: ConsolidationFilter) -> tuple[str, ...]:
        audits = self.candidate_audits(filters)
        values: set[str] = set()
        for audit in audits:
            try:
                values.update(str(item).upper() for item in json.loads(audit["devices_json"]))
            except (TypeError, json.JSONDecodeError):
                pass
        return tuple(sorted(values))

    def available_urls(self, filters: ConsolidationFilter) -> tuple[str, ...]:
        audits = self.candidate_audits(filters)
        ids = [row["audit_id"] for row in audits]
        if not ids:
            return ()
        placeholders = ",".join("?" for _ in ids)
        with self._session() as connection:
            rows = connection.execute(
                f"SELECT DISTINCT url FROM audit_urls WHERE audit_id IN ({placeholders}) ORDER BY url", ids
            ).fetchall()
            return tuple(str(row[0]) for row in rows)

    def load_points(self, filters: ConsolidationFilter) -> dict[str, tuple[dict[str, Any], ...]]:
        audits = self.candidate_audits(filters)
        ids = [str(row["audit_id"]) for row in audits]
        if not ids:
            return {"audits": (), "scores": (), "performance": (), "apdex": (), "findings": ()}
        placeholders = ",".join("?" for _ in ids)
        devices = tuple(item.upper() for item in filters.devices)
        urls = tuple(filters.urls)
        with self._session() as connection:
            score_params: list[Any] = list(ids)
            score_device = ""
            if devices:
                score_device = f" AND upper(s.device) IN ({','.join('?' for _ in devices)})"
                score_params.extend(devices)
            # Audit-level scores are only valid for a URL filter when the audit's complete URL
            # universe is contained in the selected set. This prevents contamination by
            # unselected pages without re-running the scoring engine.
            score_url_guard = ""
            if urls:
                score_url_guard = (
                    " AND NOT EXISTS (SELECT 1 FROM audit_urls au WHERE au.audit_id=s.audit_id "
                    f"AND au.url NOT IN ({','.join('?' for _ in urls)}))"
                )
                score_params.extend(urls)
            score_rows = connection.execute(
                f"SELECT s.*,a.event_time FROM score_points s JOIN source_audits a USING(audit_id) "
                f"WHERE s.audit_id IN ({placeholders}){score_device}{score_url_guard} "
                "ORDER BY a.event_time,s.device,s.dimension",
                score_params,
            ).fetchall()

            point_params = list(ids)
            perf_sql = f"SELECT p.*,a.event_time FROM performance_points p JOIN source_audits a USING(audit_id) WHERE p.audit_id IN ({placeholders})"
            apdex_sql = f"SELECT p.*,a.event_time FROM apdex_points p JOIN source_audits a USING(audit_id) WHERE p.audit_id IN ({placeholders})"
            finding_sql = f"SELECT p.*,a.event_time FROM finding_points p JOIN source_audits a USING(audit_id) WHERE p.audit_id IN ({placeholders})"
            if devices:
                dph = ",".join("?" for _ in devices)
                perf_sql += f" AND upper(p.device) IN ({dph})"
                apdex_sql += f" AND upper(p.device) IN ({dph})"
                finding_sql += f" AND upper(p.device) IN ({dph})"
                point_params.extend(devices)
            if urls:
                uph = ",".join("?" for _ in urls)
                perf_sql += f" AND p.url IN ({uph})"
                apdex_sql += f" AND p.url IN ({uph})"
                finding_sql += f" AND (p.url IN ({uph}) OR p.url IS NULL)"
                point_params.extend(urls)
            perf_rows = connection.execute(perf_sql + " ORDER BY a.event_time,p.url,p.device", point_params).fetchall()
            apdex_rows = connection.execute(apdex_sql + " ORDER BY a.event_time,p.url,p.device", point_params).fetchall()
            finding_rows = connection.execute(finding_sql + " ORDER BY a.event_time,p.severity,p.category", point_params).fetchall()
            return {
                "audits": tuple(audits),
                "scores": tuple(dict(row) for row in score_rows),
                "performance": tuple(dict(row) for row in perf_rows),
                "apdex": tuple(dict(row) for row in apdex_rows),
                "findings": tuple(dict(row) for row in finding_rows),
            }

    def source_set_fingerprint(self, audits: Iterable[dict[str, Any]]) -> str:
        material = [
            (str(row["audit_id"]), str(row["source_fingerprint"]))
            for row in audits
        ]
        payload = json.dumps(sorted(material), ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
