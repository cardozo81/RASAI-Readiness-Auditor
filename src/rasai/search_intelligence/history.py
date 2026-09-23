"""Historical comparison for persisted Search Intelligence observations.

The comparison is read-only and reuses immutable audit workspaces. It never
changes readiness scoring and never treats temporal association as causality.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from rasai.platform.models import DeploymentPair
    from rasai.platform.store import PlatformStore


HISTORY_METHOD = "SEARCH-HISTORY-001"


@dataclass(frozen=True, slots=True)
class SearchHistoryContext:
    query: str
    engine: str
    country: str
    region: str | None
    language: str
    device: str
    requested_depth: int
    domain_of_interest: str

    @property
    def key(self) -> str:
        return "|".join(
            (
                self.query,
                self.engine,
                self.country,
                self.region or "",
                self.language,
                self.device,
                str(self.requested_depth),
                self.domain_of_interest,
            )
        )


@dataclass(frozen=True, slots=True)
class SearchContentSnapshot:
    comparison_status: str | None
    query_body_coverage: float | None
    query_title_coverage: float | None
    query_heading_coverage: float | None
    word_count: int | None
    jsonld_types: tuple[str, ...]
    gap_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchHistoricalObservation:
    audit_id: str
    observation_id: str
    context: SearchHistoryContext
    collected_at: str
    provider: str
    data_mode: str
    observation_status: str
    domain_status: str
    customer_position: int | None
    content: SearchContentSnapshot


@dataclass(frozen=True, slots=True)
class SearchHistoryEvent:
    context_key: str
    query: str
    status: str
    label: str
    before: Any
    after: Any
    delta: float | None = None
    unit: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class SearchHistoryComparison:
    baseline_audit_id: str
    current_audit_id: str
    method: str
    comparable_contexts: int
    non_comparable_contexts: int
    events: tuple[SearchHistoryEvent, ...]
    compatibility_notes: tuple[str, ...]
    interpretation_policy: str = (
        "Search movements are point-in-time observational changes within identical "
        "query contexts. Temporal proximity to a deployment or content change does "
        "not prove causality."
    )


def _connect(workspace: str | Path) -> sqlite3.Connection:
    database = Path(workspace) / "audit.db"
    if not database.is_file():
        raise FileNotFoundError(f"audit database not found: {database}")
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def _json_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    try:
        raw = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw if isinstance(item, (str, int, float)))


def _ratio(matches: tuple[str, ...], terms: tuple[str, ...]) -> float | None:
    denominator = len(set(terms))
    if denominator == 0:
        return None
    return len(set(matches)) / denominator


def _empty_content() -> SearchContentSnapshot:
    return SearchContentSnapshot(None, None, None, None, None, (), ())


def _content_snapshot(
    connection: sqlite3.Connection,
    tables: set[str],
    observation_id: str,
) -> SearchContentSnapshot:
    if "serp_competitive_analyses" not in tables:
        return _empty_content()
    analysis = connection.execute(
        """SELECT comparison_status,gaps_json
           FROM serp_competitive_analyses WHERE observation_id=?""",
        (observation_id,),
    ).fetchone()
    if analysis is None:
        return _empty_content()

    gap_codes: tuple[str, ...] = ()
    try:
        raw_gaps = json.loads(str(analysis["gaps_json"]))
    except (TypeError, ValueError, json.JSONDecodeError):
        raw_gaps = []
    if isinstance(raw_gaps, list):
        gap_codes = tuple(
            sorted(
                {
                    str(item["code"])
                    for item in raw_gaps
                    if isinstance(item, dict) and item.get("code")
                }
            )
        )

    if "serp_competitive_pages" not in tables:
        return SearchContentSnapshot(
            str(analysis["comparison_status"]), None, None, None, None, (), gap_codes
        )
    page = connection.execute(
        """SELECT * FROM serp_competitive_pages
           WHERE observation_id=? AND role='CUSTOMER'
           ORDER BY requested_url LIMIT 1""",
        (observation_id,),
    ).fetchone()
    if page is None or str(page["fetch_status"]).upper() != "OBSERVED":
        return SearchContentSnapshot(
            str(analysis["comparison_status"]), None, None, None, None, (), gap_codes
        )

    terms = _json_list(page["query_terms_json"])
    return SearchContentSnapshot(
        comparison_status=str(analysis["comparison_status"]),
        query_body_coverage=_ratio(_json_list(page["query_terms_body_json"]), terms),
        query_title_coverage=_ratio(_json_list(page["query_terms_title_json"]), terms),
        query_heading_coverage=_ratio(_json_list(page["query_terms_headings_json"]), terms),
        word_count=int(page["word_count"]),
        jsonld_types=tuple(sorted(set(_json_list(page["jsonld_types_json"])))),
        gap_codes=gap_codes,
    )


def read_search_history_snapshot(
    workspace: str | Path,
) -> dict[str, SearchHistoricalObservation]:
    """Return the latest Search observation for every exact comparison context."""
    connection = _connect(workspace)
    try:
        tables = _tables(connection)
        if "serp_observations" not in tables:
            return {}
        audit = connection.execute("SELECT audit_id FROM audits ORDER BY rowid LIMIT 1").fetchone()
        if audit is None:
            raise ValueError("audit workspace contains no audit metadata")
        audit_id = str(audit["audit_id"])
        rows = connection.execute(
            """SELECT rowid,* FROM serp_observations
               WHERE audit_id=? ORDER BY collected_at,rowid""",
            (audit_id,),
        ).fetchall()
        latest: dict[str, SearchHistoricalObservation] = {}
        for row in rows:
            domain = str(row["domain_of_interest"] or "").strip().casefold()
            if not domain:
                continue
            context = SearchHistoryContext(
                query=str(row["query"]),
                engine=str(row["engine"]).casefold(),
                country=str(row["country"]).upper(),
                region=str(row["region"]) if row["region"] is not None else None,
                language=str(row["language"]),
                device=str(row["device"]).casefold(),
                requested_depth=int(row["requested_depth"]),
                domain_of_interest=domain,
            )
            observation_id = str(row["observation_id"])
            latest[context.key] = SearchHistoricalObservation(
                audit_id=audit_id,
                observation_id=observation_id,
                context=context,
                collected_at=str(row["collected_at"]),
                provider=str(row["provider"]),
                data_mode=str(row["data_mode"]),
                observation_status=str(row["observation_status"]),
                domain_status=str(row["domain_status"]),
                customer_position=(
                    int(row["customer_position"])
                    if row["customer_position"] is not None
                    else None
                ),
                content=_content_snapshot(connection, tables, observation_id),
            )
        return latest
    finally:
        connection.close()


def _event(
    observation: SearchHistoricalObservation,
    status: str,
    label: str,
    before: Any,
    after: Any,
    *,
    delta: float | None = None,
    unit: str | None = None,
    note: str | None = None,
) -> SearchHistoryEvent:
    return SearchHistoryEvent(
        context_key=observation.context.key,
        query=observation.context.query,
        status=status,
        label=label,
        before=before,
        after=after,
        delta=delta,
        unit=unit,
        note=note,
    )


def _content_events(
    before: SearchHistoricalObservation,
    after: SearchHistoricalObservation,
) -> list[SearchHistoryEvent]:
    b = before.content
    a = after.content
    if b.comparison_status != "CONSOLIDATED" or a.comparison_status != "CONSOLIDATED":
        return []
    events: list[SearchHistoryEvent] = []
    for field, label in (
        ("query_body_coverage", "Query coverage in body"),
        ("query_title_coverage", "Query coverage in title"),
        ("query_heading_coverage", "Query coverage in headings"),
    ):
        before_value = getattr(b, field)
        after_value = getattr(a, field)
        if before_value is None or after_value is None or before_value == after_value:
            continue
        events.append(
            _event(
                after,
                "CONTENT_SIGNAL_CHANGED",
                label,
                before_value,
                after_value,
                delta=float(after_value) - float(before_value),
                unit="ratio",
                note="Deterministic content signal; not a ranking-causality claim.",
            )
        )
    if b.word_count is not None and a.word_count is not None and b.word_count != a.word_count:
        events.append(
            _event(
                after,
                "CONTENT_VOLUME_CHANGED",
                "Observed customer page word count",
                b.word_count,
                a.word_count,
                delta=float(a.word_count - b.word_count),
                unit="words",
                note="Content volume has no automatic quality interpretation.",
            )
        )
    if b.jsonld_types != a.jsonld_types:
        events.append(
            _event(
                after,
                "STRUCTURED_DATA_CHANGED",
                "Observed JSON-LD types",
                b.jsonld_types,
                a.jsonld_types,
                note="Markup difference is informational, not an automatic recommendation.",
            )
        )
    before_gaps = set(b.gap_codes)
    after_gaps = set(a.gap_codes)
    for code in sorted(after_gaps - before_gaps):
        events.append(
            _event(
                after,
                "DETERMINISTIC_GAP_ADDED",
                code,
                False,
                True,
                note="New correlational difference against the observed leader reference set.",
            )
        )
    for code in sorted(before_gaps - after_gaps):
        events.append(
            _event(
                after,
                "DETERMINISTIC_GAP_RESOLVED",
                code,
                True,
                False,
                note="Previously observed correlational difference is no longer present.",
            )
        )
    return events


def compare_search_workspaces(
    baseline_workspace: str | Path,
    current_workspace: str | Path,
) -> SearchHistoryComparison:
    baseline = read_search_history_snapshot(baseline_workspace)
    current = read_search_history_snapshot(current_workspace)
    baseline_audit_id = next(iter(baseline.values())).audit_id if baseline else Path(baseline_workspace).name
    current_audit_id = next(iter(current.values())).audit_id if current else Path(current_workspace).name
    events: list[SearchHistoryEvent] = []
    notes: list[str] = []
    comparable = 0
    non_comparable = 0

    for key in sorted(set(baseline) | set(current)):
        before = baseline.get(key)
        after = current.get(key)
        if before is None and after is not None:
            non_comparable += 1
            events.append(
                _event(after, "NEW_CONTEXT", "Search observation context", None, after.domain_status,
                       note="No matching baseline context exists; no rank delta is computed.")
            )
            continue
        if before is not None and after is None:
            non_comparable += 1
            events.append(
                _event(before, "MISSING_CURRENT_CONTEXT", "Search observation context", before.domain_status, None,
                       note="Current audit has no identical Search context; no rank delta is computed.")
            )
            continue
        assert before is not None and after is not None

        incompatibilities: list[str] = []
        if before.observation_status != "OBSERVED" or after.observation_status != "OBSERVED":
            incompatibilities.append("both observations must have status OBSERVED")
        if before.data_mode != after.data_mode:
            incompatibilities.append(f"data mode changed: {before.data_mode} -> {after.data_mode}")
        if before.provider != after.provider:
            incompatibilities.append(f"provider changed: {before.provider} -> {after.provider}")
        if incompatibilities:
            non_comparable += 1
            notes.extend(f"{after.context.key}: {item}" for item in incompatibilities)
            events.append(
                _event(
                    after,
                    "NOT_COMPARABLE",
                    "Search observation provenance",
                    {"provider": before.provider, "data_mode": before.data_mode, "status": before.observation_status},
                    {"provider": after.provider, "data_mode": after.data_mode, "status": after.observation_status},
                    note="Context matches, but provenance changed or an observation is not usable.",
                )
            )
            continue

        comparable += 1
        before_found = before.domain_status == "FOUND" and before.customer_position is not None
        after_found = after.domain_status == "FOUND" and after.customer_position is not None
        if before_found and after_found:
            delta = int(after.customer_position) - int(before.customer_position)
            status = "POSITION_IMPROVED" if delta < 0 else "POSITION_REGRESSED" if delta > 0 else "POSITION_UNCHANGED"
            events.append(
                _event(
                    after,
                    status,
                    "Observed customer position",
                    before.customer_position,
                    after.customer_position,
                    delta=float(delta),
                    unit="positions",
                    note="Lower position number is better within this exact observed context.",
                )
            )
        elif not before_found and after_found:
            events.append(
                _event(
                    after,
                    "ENTERED_OBSERVED_DEPTH",
                    "Customer presence within requested depth",
                    before.domain_status,
                    after.customer_position,
                    note="The customer is now within the requested depth; its previous absolute rank remains unknown.",
                )
            )
        elif before_found and not after_found:
            events.append(
                _event(
                    after,
                    "LEFT_OBSERVED_DEPTH",
                    "Customer presence within requested depth",
                    before.customer_position,
                    after.domain_status,
                    note="Not observed within depth does not mean the domain does not rank beyond that depth.",
                )
            )
        elif before.domain_status != after.domain_status:
            events.append(_event(after, "DOMAIN_STATUS_CHANGED", "Search domain status", before.domain_status, after.domain_status))
        else:
            events.append(_event(after, "OBSERVED_DEPTH_STATE_UNCHANGED", "Search domain status", before.domain_status, after.domain_status))
        events.extend(_content_events(before, after))

    return SearchHistoryComparison(
        baseline_audit_id=baseline_audit_id,
        current_audit_id=current_audit_id,
        method=HISTORY_METHOD,
        comparable_contexts=comparable,
        non_comparable_contexts=non_comparable,
        events=tuple(events),
        compatibility_notes=tuple(sorted(set(notes))),
    )


def compare_search_deployment_pair(
    store: "PlatformStore",
    pair: "DeploymentPair",
) -> SearchHistoryComparison:
    """Compare Search evidence for a deployment pair selected by the platform model."""
    if pair.baseline_audit_id is None or pair.current_audit_id is None:
        raise ValueError("deployment pair is incomplete; baseline and current audits are required")
    baseline = store.get_audit(pair.baseline_audit_id)
    current = store.get_audit(pair.current_audit_id)
    if baseline is None or current is None:
        raise KeyError("deployment pair references audit(s) missing from platform index")
    return compare_search_workspaces(Path(baseline.workspace_path), Path(current.workspace_path))
