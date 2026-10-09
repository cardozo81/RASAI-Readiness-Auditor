"""Read-only, bounded UTC chronology for GEO consumers and reports.

One comparison contract for optional AI inputs and HTML projections. Neither
this module nor its callers may use opaque ID sorting as temporal proof.
Missing/unprovable clocks return _UNVERIFIABLE, never a prior success.
No provider, collector, SQLite writes, or network operations.
"""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3


def _columns(con: sqlite3.Connection, name: str) -> set[str]:
    if con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is None:
        return set()
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({name})")}


_UNVERIFIABLE = object()
_MAX_READONLY_CROSSREF_ROWS = 256


def _last_temporally_verified(
    con: sqlite3.Connection, *,
    table: str, audit_id: str,
    columns: tuple[str, ...], time_column: str,
    condition: str = "",
    condition_params: tuple = (),
) -> tuple | None | object:
    """Pick the latest same-AUD row only with provable clock chronology.

    IDs are opaque and SQLite lexical ordering of ISO instants with different
    UTC offsets is not temporal ordering. A single row needs no ordering proof;
    multiple rows require unique, offset-aware, parsable instants. Bounded and
    read-only; ambiguous ordering never promotes an old success as current.
    All SQL identifiers/conditions are fixed by internal callers.
    """
    available = _columns(con, table)
    if not {"audit_id", *columns}.issubset(available):
        return _UNVERIFIABLE
    stamp = time_column if time_column in available else "NULL"
    query = (
        "SELECT " + ", ".join(columns) + ", " + stamp + " AS _observed_at "
        + "FROM " + table + " WHERE audit_id=?" + condition
        + " LIMIT " + str(_MAX_READONLY_CROSSREF_ROWS + 1)
    )
    rows = con.execute(query, (audit_id, *condition_params)).fetchall()
    if not rows:
        return None
    if len(rows) == 1:
        return tuple(rows[0][:-1])
    if len(rows) > _MAX_READONLY_CROSSREF_ROWS or time_column not in available:
        return _UNVERIFIABLE
    ordered: list[tuple[datetime, tuple]] = []
    for record in rows:
        try:
            instant = datetime.fromisoformat(
                str(record[-1]).replace("Z", "+00:00")
            )
            if instant.tzinfo is None:
                return _UNVERIFIABLE
            instant = instant.astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            return _UNVERIFIABLE
        ordered.append((instant, tuple(record[:-1])))
    ordered.sort(key=lambda item: item[0], reverse=True)
    if ordered[0][0] == ordered[1][0]:
        # Equal timestamps cannot prove which physical attempt was last.
        return _UNVERIFIABLE
    return ordered[0][1]


