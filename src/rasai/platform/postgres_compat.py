"""Small PostgreSQL compatibility layer for the RASAi control plane.

The product store was intentionally written against a narrow DB-API surface.  This
module adapts Psycopg 3 to that surface so domain methods can be reused without
sprinkling database-engine checks throughout product logic.

The adapter is not used by immutable ``AUD-*/audit.db`` evidence databases.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit


class PostgreSQLDependencyError(RuntimeError):
    """Raised when the optional PostgreSQL runtime dependency is unavailable."""


class PostgreSQLConfigurationError(ValueError):
    """Raised when PostgreSQL was selected without a valid connection URL."""


@dataclass(frozen=True, slots=True)
class CompatRow(Mapping[str, Any]):
    """Mapping row that also preserves sqlite-style numeric indexing."""

    _keys: tuple[str, ...]
    _values: tuple[Any, ...]

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        try:
            return self._values[self._keys.index(key)]
        except ValueError as exc:
            raise KeyError(key) from exc

    def __iter__(self) -> Iterator[str]:
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def keys(self) -> tuple[str, ...]:
        return self._keys


class PostgresCursorAdapter:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    @property
    def description(self) -> Any:
        return self._cursor.description

    def _row(self, row: Any) -> CompatRow | None:
        if row is None:
            return None
        description = self._cursor.description or ()
        keys = tuple(str(column.name) for column in description)
        if isinstance(row, Mapping):
            values = tuple(row[key] for key in keys)
        else:
            values = tuple(row)
        return CompatRow(keys, values)

    def fetchone(self) -> CompatRow | None:
        return self._row(self._cursor.fetchone())

    def fetchall(self) -> list[CompatRow]:
        return [self._row(row) for row in self._cursor.fetchall()]  # type: ignore[list-item]

    def __iter__(self) -> Iterator[CompatRow]:
        for row in self._cursor:
            mapped = self._row(row)
            if mapped is not None:
                yield mapped


def _qmark_to_pyformat(sql: str) -> str:
    """Translate sqlite qmark parameters to Psycopg ``%s`` outside SQL quotes."""

    output: list[str] = []
    single = False
    double = False
    index = 0
    while index < len(sql):
        char = sql[index]
        if char == "'" and not double:
            output.append(char)
            if single and index + 1 < len(sql) and sql[index + 1] == "'":
                output.append("'")
                index += 2
                continue
            single = not single
        elif char == '"' and not single:
            output.append(char)
            double = not double
        elif char == "?" and not single and not double:
            output.append("%s")
        else:
            output.append(char)
        index += 1
    return "".join(output)


class PostgresConnectionAdapter:
    """Psycopg connection exposing the subset consumed by product stores.

    The underlying Psycopg connection runs in autocommit mode.  ``with
    connection:`` explicitly starts one transaction, matching the write blocks used
    by the SQLite store without leaving read-only SELECT statements in idle
    transactions.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._transaction_depth = 0

    @property
    def raw_connection(self) -> Any:
        return self._connection

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> PostgresCursorAdapter:
        translated = _qmark_to_pyformat(sql)
        cursor = self._connection.cursor()
        if params is None:
            cursor.execute(translated)
        else:
            cursor.execute(translated, tuple(params))
        return PostgresCursorAdapter(cursor)

    def commit(self) -> None:
        if not self._connection.autocommit:
            self._connection.commit()

    def rollback(self) -> None:
        if not self._connection.autocommit:
            self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "PostgresConnectionAdapter":
        if self._transaction_depth == 0:
            self.execute("BEGIN")
        else:
            self.execute(f"SAVEPOINT rasai_nested_{self._transaction_depth}")
        self._transaction_depth += 1
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._transaction_depth -= 1
        if self._transaction_depth < 0:
            self._transaction_depth = 0
            raise RuntimeError("PostgreSQL transaction depth underflow")
        if self._transaction_depth == 0:
            self.execute("ROLLBACK" if exc_type is not None else "COMMIT")
            return
        savepoint = f"rasai_nested_{self._transaction_depth}"
        if exc_type is not None:
            self.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        self.execute(f"RELEASE SAVEPOINT {savepoint}")


def require_postgres_url(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        raise PostgreSQLConfigurationError(
            "PostgreSQL backend requires RASAI_PLATFORM_DATABASE_URL; no SQLite fallback is permitted"
        )
    parsed = urlsplit(text)
    if parsed.scheme not in {"postgresql", "postgres"} or not parsed.hostname or not parsed.path.strip("/"):
        raise PostgreSQLConfigurationError(
            "RASAI_PLATFORM_DATABASE_URL must be a postgresql:// URL with host and database name"
        )
    return text


def redact_postgres_url(value: str) -> str:
    """Return a safe display URL that never contains the database password."""

    parsed = urlsplit(require_postgres_url(value))
    username = quote(parsed.username or "", safe="")
    auth = f"{username}@" if username else ""
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    return urlunsplit(("postgresql", f"{auth}{host}{port}", parsed.path, "", ""))


def connect_postgres(database_url: str) -> PostgresConnectionAdapter:
    url = require_postgres_url(database_url)
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised in optional-dependency tests
        raise PostgreSQLDependencyError(
            'PostgreSQL support requires the optional dependency: pip install -e ".[postgresql]"'
        ) from exc
    connection = psycopg.connect(url, autocommit=True)
    adapter = PostgresConnectionAdapter(connection)
    adapter.execute("SET TIME ZONE 'UTC'")
    return adapter
