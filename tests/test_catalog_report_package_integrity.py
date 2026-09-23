from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from rasai.catalog_report_site import (
    _sha256_file,
    _snapshot_sqlite_database,
    verify_catalog_report_package,
)


def _assurance_payload() -> dict:
    return {
        "metric_semantics": "deterministic structural-control coverage; not statistical probability",
        "thresholds": {
            "catalog_maturity_min": 95.0,
            "reliability_integrity_security_min": 99.5,
        },
        "catalogs": [],
        "global": {
            "reliability": 100.0,
            "integrity": 100.0,
            "security": 100.0,
            "maturity": 100.0,
            "configurability": 100.0,
            "governance": 100.0,
            "exposure": 100.0,
        },
        "per_catalog_target_met": True,
        "high_assurance_target_met": True,
        "closure_eligible": True,
    }


def _manifest(root: Path) -> dict:
    snapshot = root / "integrity" / "audit-snapshot.db"
    assurance_path = root / "integrity" / "catalog-assurance.json"
    assurance = _assurance_payload()
    assurance_path.write_text(json.dumps(assurance), encoding="utf-8")

    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "manifest.json"):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
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
        "assurance": {
            "metric_semantics": assurance["metric_semantics"],
            "thresholds": assurance["thresholds"],
            "global": assurance["global"],
            "per_catalog_target_met": True,
            "high_assurance_target_met": True,
            "closure_eligible": True,
            "artifact": "integrity/catalog-assurance.json",
        },
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


def test_report_package_rejects_assurance_manifest_divergence(tmp_path: Path) -> None:
    root = tmp_path / "report-catalog"
    (root / "integrity").mkdir(parents=True)
    database = root / "integrity" / "audit-snapshot.db"
    sqlite3.connect(database).close()
    (root / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    manifest = _manifest(root)
    manifest["assurance"]["closure_eligible"] = False
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    ok, errors = verify_catalog_report_package(root)
    assert ok is False
    assert any("closure_eligible divergente" in item for item in errors)
