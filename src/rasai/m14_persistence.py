"""Additive persistence used by M14 without changing the stable M1 schema.

The M14 tables are deliberately additive.  Existing audit.db files remain
re-openable by M1 persistence, while M14-aware code can project URL-set input
and concrete DOM observations from the same database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from rasai.domain import DeviceContext, utc_now
from rasai.persistence import AuditWorkspace


_MAX_OUTER_HTML = 4096
_MAX_TEXT_EXCERPT = 512
_MAX_CLASSES = 12
_MAX_CLASS_LENGTH = 128


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load(value: str | None) -> Any:
    if value in (None, ""):
        return None
    return json.loads(value)


@dataclass(frozen=True, slots=True)
class AuditInputUrl:
    audit_id: str
    position: int
    input_url: str
    normalized_url: str


@dataclass(frozen=True, slots=True)
class AuditInputSummary:
    audit_id: str
    input_mode: str
    supplied_count: int
    normalized_unique_count: int


@dataclass(frozen=True, slots=True)
class ElementObservation:
    element_observation_id: str
    audit_id: str
    page_id: str
    snapshot_id: str
    device: DeviceContext
    url: str
    selector: str | None
    tag_name: str
    element_id: str | None
    classes: tuple[str, ...]
    outer_html: str | None
    text_excerpt: str | None
    bounding_box: dict[str, float] | None
    artifact_reference: str | None
    captured_at: datetime


class M14Persistence:
    """Persist M14 URL-set/DOM evidence tables in one audit workspace."""

    def __init__(self, workspace: AuditWorkspace) -> None:
        self.workspace = workspace
        self._connection = sqlite3.connect(workspace.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def __enter__(self) -> "M14Persistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS audit_input_urls (
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    input_url TEXT NOT NULL,
                    normalized_url TEXT NOT NULL,
                    PRIMARY KEY (audit_id, position),
                    UNIQUE (audit_id, normalized_url)
                );

                CREATE TABLE IF NOT EXISTS audit_input_summary (
                    audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                    input_mode TEXT NOT NULL,
                    supplied_count INTEGER NOT NULL CHECK (supplied_count > 0),
                    normalized_unique_count INTEGER NOT NULL CHECK (normalized_unique_count > 0)
                );

                CREATE TABLE IF NOT EXISTS element_observations (
                    element_observation_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    snapshot_id TEXT NOT NULL REFERENCES page_snapshots(snapshot_id) ON DELETE CASCADE,
                    device TEXT NOT NULL,
                    url TEXT NOT NULL,
                    selector TEXT,
                    tag_name TEXT NOT NULL,
                    element_id TEXT,
                    classes TEXT NOT NULL,
                    outer_html TEXT,
                    text_excerpt TEXT,
                    bounding_box TEXT,
                    artifact_reference TEXT,
                    captured_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_element_observations_snapshot
                    ON element_observations(snapshot_id, tag_name);
                CREATE INDEX IF NOT EXISTS idx_element_observations_page_device
                    ON element_observations(page_id, device);

                CREATE TABLE IF NOT EXISTS finding_element_observations (
                    finding_id TEXT NOT NULL REFERENCES findings(finding_id) ON DELETE CASCADE,
                    element_observation_id TEXT NOT NULL REFERENCES element_observations(element_observation_id) ON DELETE CASCADE,
                    PRIMARY KEY (finding_id, element_observation_id)
                );
                """
            )

    def replace_input_urls(self, audit_id: str, urls: tuple[tuple[str, str], ...]) -> None:
        """Replace the ordered normalized/deduplicated input universe.

        Each tuple is ``(input_url, normalized_url)``.  The raw supplied count is
        intentionally persisted separately by :meth:`set_input_summary` so the
        report can distinguish operator input count from the audited unique set.
        """

        audit = self._connection.execute(
            "SELECT 1 FROM audits WHERE audit_id = ?", (audit_id,)
        ).fetchone()
        if audit is None:
            raise sqlite3.IntegrityError(f"audit not found: {audit_id}")
        with self._connection:
            self._connection.execute("DELETE FROM audit_input_urls WHERE audit_id = ?", (audit_id,))
            for position, (input_url, normalized_url) in enumerate(urls, start=1):
                self._connection.execute(
                    "INSERT INTO audit_input_urls VALUES (?, ?, ?, ?)",
                    (audit_id, position, input_url, normalized_url),
                )

    def set_input_summary(
        self,
        audit_id: str,
        *,
        input_mode: str,
        supplied_count: int,
        normalized_unique_count: int,
    ) -> None:
        if supplied_count <= 0 or normalized_unique_count <= 0:
            raise ValueError("URL input counts must be greater than zero")
        if normalized_unique_count > supplied_count:
            raise ValueError("normalized_unique_count cannot exceed supplied_count")
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO audit_input_summary
                    (audit_id, input_mode, supplied_count, normalized_unique_count)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(audit_id) DO UPDATE SET
                    input_mode = excluded.input_mode,
                    supplied_count = excluded.supplied_count,
                    normalized_unique_count = excluded.normalized_unique_count
                """,
                (audit_id, input_mode, supplied_count, normalized_unique_count),
            )

    def get_input_summary(self, audit_id: str) -> AuditInputSummary | None:
        row = self._connection.execute(
            "SELECT * FROM audit_input_summary WHERE audit_id = ?", (audit_id,)
        ).fetchone()
        if row is None:
            return None
        return AuditInputSummary(
            audit_id=row["audit_id"],
            input_mode=row["input_mode"],
            supplied_count=row["supplied_count"],
            normalized_unique_count=row["normalized_unique_count"],
        )

    def list_input_urls(self, audit_id: str) -> tuple[AuditInputUrl, ...]:
        rows = self._connection.execute(
            "SELECT * FROM audit_input_urls WHERE audit_id = ? ORDER BY position",
            (audit_id,),
        ).fetchall()
        return tuple(
            AuditInputUrl(
                audit_id=row["audit_id"],
                position=row["position"],
                input_url=row["input_url"],
                normalized_url=row["normalized_url"],
            )
            for row in rows
        )

    def add_element_observation(self, observation: ElementObservation) -> ElementObservation:
        sanitized = sanitize_element_observation(observation)
        self._require_snapshot_scope(sanitized)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO element_observations (
                    element_observation_id, audit_id, page_id, snapshot_id, device,
                    url, selector, tag_name, element_id, classes, outer_html,
                    text_excerpt, bounding_box, artifact_reference, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sanitized.element_observation_id,
                    sanitized.audit_id,
                    sanitized.page_id,
                    sanitized.snapshot_id,
                    sanitized.device.value,
                    sanitized.url,
                    sanitized.selector,
                    sanitized.tag_name,
                    sanitized.element_id,
                    _dump(list(sanitized.classes)),
                    sanitized.outer_html,
                    sanitized.text_excerpt,
                    _dump(sanitized.bounding_box) if sanitized.bounding_box is not None else None,
                    sanitized.artifact_reference,
                    sanitized.captured_at.isoformat(),
                ),
            )
        return sanitized

    def get_element_observation(self, observation_id: str) -> ElementObservation | None:
        row = self._connection.execute(
            "SELECT * FROM element_observations WHERE element_observation_id = ?",
            (observation_id,),
        ).fetchone()
        return None if row is None else self._map_observation(row)

    def list_for_snapshot(self, snapshot_id: str) -> tuple[ElementObservation, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM element_observations
            WHERE snapshot_id = ?
            ORDER BY tag_name, selector, element_observation_id
            """,
            (snapshot_id,),
        ).fetchall()
        return tuple(self._map_observation(row) for row in rows)

    def link_finding(self, finding_id: str, observation_id: str) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO finding_element_observations
                    (finding_id, element_observation_id)
                VALUES (?, ?)
                """,
                (finding_id, observation_id),
            )

    def observations_for_finding(self, finding_id: str) -> tuple[ElementObservation, ...]:
        rows = self._connection.execute(
            """
            SELECT eo.*
            FROM element_observations eo
            JOIN finding_element_observations feo
              ON feo.element_observation_id = eo.element_observation_id
            WHERE feo.finding_id = ?
            ORDER BY eo.element_observation_id
            """,
            (finding_id,),
        ).fetchall()
        return tuple(self._map_observation(row) for row in rows)

    def _require_snapshot_scope(self, observation: ElementObservation) -> None:
        row = self._connection.execute(
            """
            SELECT p.audit_id, ps.page_id, ps.device
            FROM page_snapshots ps
            JOIN pages p ON p.page_id = ps.page_id
            WHERE ps.snapshot_id = ?
            """,
            (observation.snapshot_id,),
        ).fetchone()
        if (
            row is None
            or row["audit_id"] != observation.audit_id
            or row["page_id"] != observation.page_id
            or row["device"] != observation.device.value
        ):
            raise sqlite3.IntegrityError(
                f"element observation {observation.element_observation_id} has inconsistent audit/page/snapshot/device scope"
            )

    @staticmethod
    def _map_observation(row: sqlite3.Row) -> ElementObservation:
        box = _load(row["bounding_box"])
        return ElementObservation(
            element_observation_id=row["element_observation_id"],
            audit_id=row["audit_id"],
            page_id=row["page_id"],
            snapshot_id=row["snapshot_id"],
            device=DeviceContext(row["device"]),
            url=row["url"],
            selector=row["selector"],
            tag_name=row["tag_name"],
            element_id=row["element_id"],
            classes=tuple(_load(row["classes"]) or ()),
            outer_html=row["outer_html"],
            text_excerpt=row["text_excerpt"],
            bounding_box=box if isinstance(box, dict) else None,
            artifact_reference=row["artifact_reference"],
            captured_at=datetime.fromisoformat(row["captured_at"]),
        )


def sanitize_element_observation(observation: ElementObservation) -> ElementObservation:
    """Bound textual fields and normalize unsafe control characters.

    HTML remains source evidence, not executable report markup.  The report
    escapes it again before rendering.
    """

    selector = _clean_text(observation.selector, 2048)
    tag_name = (_clean_text(observation.tag_name, 64) or "unknown").lower()
    element_id = _clean_text(observation.element_id, 512)
    classes = tuple(
        value
        for value in (
            _clean_text(item, _MAX_CLASS_LENGTH) for item in observation.classes[:_MAX_CLASSES]
        )
        if value
    )
    outer_html = _clean_text(observation.outer_html, _MAX_OUTER_HTML)
    text_excerpt = _clean_text(observation.text_excerpt, _MAX_TEXT_EXCERPT)
    bounding_box = _sanitize_box(observation.bounding_box)
    artifact_reference = _safe_artifact_reference(observation.artifact_reference)
    return ElementObservation(
        element_observation_id=observation.element_observation_id,
        audit_id=observation.audit_id,
        page_id=observation.page_id,
        snapshot_id=observation.snapshot_id,
        device=observation.device,
        url=observation.url,
        selector=selector,
        tag_name=tag_name,
        element_id=element_id,
        classes=classes,
        outer_html=outer_html,
        text_excerpt=text_excerpt,
        bounding_box=bounding_box,
        artifact_reference=artifact_reference,
        captured_at=observation.captured_at or utc_now(),
    )


def _clean_text(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = value.replace("\x00", "").strip()
    if not cleaned:
        return None
    return cleaned[:limit]


def _sanitize_box(value: dict[str, float] | None) -> dict[str, float] | None:
    if value is None:
        return None
    try:
        box = {key: float(value[key]) for key in ("x", "y", "width", "height")}
    except (KeyError, TypeError, ValueError):
        return None
    if box["width"] <= 0 or box["height"] <= 0:
        return None
    if not all(-100000.0 <= number <= 100000.0 for number in box.values()):
        return None
    return box


def _safe_artifact_reference(value: str | None) -> str | None:
    cleaned = _clean_text(value, 2048)
    if cleaned is None:
        return None
    path = Path(cleaned)
    if path.is_absolute() or ".." in path.parts:
        return None
    return path.as_posix()
