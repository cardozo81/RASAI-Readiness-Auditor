from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from rasai.catalog_report_site import (
    _sha256_file,
    _snapshot_sqlite_database,
    verify_catalog_report_package,
)


def _manifest(root: Path) -> dict:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "manifest.json"):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    snapshot = root / "integrity" / "audit-snapshot.db"
    return {
        "audit_id": "AUD-INTEGRITY",
        "freshness": "FINAL",
        "audit_snapshot": {
            "path": "integrity/audit-snapshot.db",
            "sha256": _sha256_file(snapshot),
            "algorithm": "sha256",
            "standalone_sqlite": True,
        },
        "packaged_files": files,
    }


def test_sqlite_snapshot_contains_wal_commits_without_sidecar_dependency(tmp_path: Path) -> None:
    source = tmp_path / "audit.db"
    connection = sqlite3.connect(source)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE sample(value TEXT)")
    connection.execute("INSERT INTO sample VALUES ('persisted-through-wal')")
    connection.commit()

    destination = tmp_path / "report-catalog" / "integrity" / "audit-snapshot.db"
    _snapshot_sqlite_database(source, destination)

    snapshot = sqlite3.connect(destination)
    try:
        assert snapshot.execute("SELECT value FROM sample").fetchone()[0] == "persisted-through-wal"
    finally:
        snapshot.close()
        connection.close()
    assert destination.is_file()
    assert not destination.with_name(destination.name + "-wal").exists()


def test_report_package_verifies_using_only_delivered_files_and_detects_tampering(tmp_path: Path) -> None:
    root = tmp_path / "report-catalog"
    (root / "integrity").mkdir(parents=True)
    database = root / "integrity" / "audit-snapshot.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE audits(audit_id TEXT PRIMARY KEY)")
    connection.execute("INSERT INTO audits VALUES ('AUD-INTEGRITY')")
    connection.commit()
    connection.close()
    (root / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    manifest = _manifest(root)
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    ok, errors = verify_catalog_report_package(root)
    assert ok is True
    assert errors == ()

    (root / "index.html").write_text("<html>tampered</html>", encoding="utf-8")
    ok, errors = verify_catalog_report_package(root)
    assert ok is False
    assert any("hash divergente: index.html" in item for item in errors)
