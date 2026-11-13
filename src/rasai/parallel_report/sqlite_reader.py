"""Small SQLite reader; never imports operational persistence classes."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


def quiescent(database: Path) -> None:
    if any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("SQLite sidecar present: require a sealed, quiescent audit")


@contextmanager
def connect(database: Path):
    database = database.resolve(strict=True)
    quiescent(database)
    connection = sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.row_factory = sqlite3.Row
        yield connection
    finally:
        connection.close()
        quiescent(database)


def quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def read_database(database):
    tables, schema = {}, {}
    with connect(database) as connection:
        names = [r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        for name in names:
            columns = [dict(r) for r in connection.execute(f"PRAGMA table_info({quote(name)})")]
            schema[name] = {
                "columns": [c["name"] for c in columns],
                "primary_key": [c["name"] for c in sorted(columns, key=lambda c: c["pk"]) if c["pk"]],
                "foreign_keys": [dict(r) for r in connection.execute(f"PRAGMA foreign_key_list({quote(name)})")],
            }
            tables[name] = [dict(r) for r in connection.execute(f"SELECT * FROM {quote(name)}")]
    return tables, schema
