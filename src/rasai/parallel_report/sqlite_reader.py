"""Small SQLite reader; never imports operational persistence classes."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import hashlib
import json


def quiescent(database: Path) -> None:
    if any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("SQLite sidecar present: require a sealed, quiescent audit")


@contextmanager
def connect(database: Path):
    database = database.resolve(strict=True)
    quiescent(database)
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
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

def logical_digest(database: Path) -> str:
    """Stable logical SHA-256 of a sealed, read-only SQLite source.

    This replicates the historical SQLite digest contract locally so the
    presentation need not import a sibling report renderer.
    """
    with connect(database) as connection:
        digest = hashlib.sha256()
        tables = connection.execute(
            """SELECT name,COALESCE(sql,'') FROM sqlite_master
               WHERE type='table' AND name NOT LIKE 'sqlite_%'
               ORDER BY name"""
        ).fetchall()
        for table_name, schema_sql in tables:
            name = str(table_name)
            digest.update(name.encode('utf-8'))
            digest.update(b'\0')
            digest.update(str(schema_sql or '').encode('utf-8'))
            digest.update(b'\0')
            quoted = quote(name)
            info = connection.execute(f'PRAGMA table_info({quoted})').fetchall()
            pk_columns = [(int(row[5]), str(row[1])) for row in info if int(row[5] or 0) > 0]
            pk_columns.sort()
            if pk_columns:
                order_by = ','.join(quote(column) for _pos, column in pk_columns)
            else:
                order_by = 'rowid'
            try:
                cursor = connection.execute(f'SELECT * FROM {quoted} ORDER BY {order_by}')
            except sqlite3.OperationalError:
                cursor = connection.execute(f'SELECT * FROM {quoted}')
            for row in cursor:
                values = []
                for value in row:
                    if value is None:
                        values.append(['null', None])
                    elif isinstance(value, bytes):
                        values.append(['bytes', value.hex()])
                    elif isinstance(value, float):
                        values.append(['float', repr(value)])
                    elif isinstance(value, int):
                        values.append(['int', value])
                    else:
                        values.append(['text', str(value)])
                digest.update(json.dumps(values, ensure_ascii=False,
                    separators=(',', ':'), sort_keys=False).encode('utf-8'))
                digest.update(b'\0')
            digest.update(b'\xff')
        return digest.hexdigest()
