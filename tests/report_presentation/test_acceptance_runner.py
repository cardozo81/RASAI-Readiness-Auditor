"""Regression: #724 acceptance must retain the AUD Path through editorial triage.

A source-family dictionary must never overwrite the original audit directory Path.
The no-browser result is intentionally exit=2, but must still emit acceptance.json.
"""
import json
import os
from hashlib import sha256
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_acceptance_source_path_survives_editorial_family_iteration(tmp_path):
    audit = tmp_path / "AUD-ACCEPTANCE-722"
    audit.mkdir()
    db_path = audit / "audit.db"
    with sqlite3.connect(db_path) as db:
        db.executescript("""
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY, status TEXT);
            INSERT INTO audits VALUES('AUD-ACCEPTANCE-722', 'PARTIAL');
            CREATE TABLE scores(score_id TEXT PRIMARY KEY, value REAL, dimension TEXT);
            INSERT INTO scores VALUES('missing', NULL, 'INDEXABILITY');
            CREATE TABLE ai_provider_native_usage(id INTEGER PRIMARY KEY, native_usage_quantity REAL);
            INSERT INTO ai_provider_native_usage VALUES(1, 0);
            CREATE TABLE audit_reprocess_runs(reprocess_id TEXT PRIMARY KEY, status TEXT);
            INSERT INTO audit_reprocess_runs VALUES('R-1', 'FAILED_RETRYABLE');
            CREATE TABLE unknown_new_family(id INTEGER PRIMARY KEY, value TEXT);
            INSERT INTO unknown_new_family VALUES(1, 'technical');
        """)
    (audit / "artifacts").mkdir()
    original_sha = sha256(db_path.read_bytes()).hexdigest()
    repo = Path(__file__).resolve().parents[2]
    output = tmp_path / "acceptance"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo / "src")
    result = subprocess.run(
        [
            sys.executable, "-B", str(repo / "scripts" / "presentation_acceptance.py"),
            "--audit", str(audit), "--output", str(output),
            "--expected-db-sha256", original_sha,
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    # Browser is not requested: exit 2 indicates QA pending, not an exception.
    assert result.returncode == 2, result.stderr[-3500:]
    receipt = json.loads((output / "acceptance.json").read_text(encoding="utf-8"))
    assert receipt["browser"]["status"] == "NOT_EXECUTED"
    assert receipt["original_source_preserved"] is True
    assert receipt["copy_source_preserved"] is True
    assert receipt["sqlite_tables"] == 5
    assert receipt["checks"]["editorial_families_classified"] == 5
    assert receipt["checks"]["table_families_reconciled"] == 5
    assert receipt["checks"]["pages"] == 11
    assert receipt["checks"]["catalog_links"] == 0
    assert sha256(db_path.read_bytes()).hexdigest() == original_sha
