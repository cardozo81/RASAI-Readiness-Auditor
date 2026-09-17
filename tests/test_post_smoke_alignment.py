from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.post_smoke_alignment import _cat08_required, _primary_ai_context
from rasai.post_smoke_hotfix import (
    _install_materialized_sidecar_counts,
    _latest_common_crawl_dataset,
)


def test_cat08_required_uses_frozen_plan_and_auto_session(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audit_execution_configurations(
                audit_id TEXT PRIMARY KEY,
                configuration_json TEXT NOT NULL
            );
            CREATE TABLE ai_audit_sessions(
                audit_id TEXT PRIMARY KEY,
                strategy TEXT,
                initial_provider TEXT,
                initial_model TEXT,
                initial_reasoning_profile TEXT,
                effective_provider TEXT,
                effective_model TEXT,
                effective_reasoning_profile TEXT
            );
            """
        )
        payload = {
            "audit_catalog": {
                "selected": ["CAT-08"],
                "ai_enabled": True,
                "items": [
                    {
                        "id": "CAT-08",
                        "selected": True,
                        "ai_mode": "REQUIRED",
                        "ai_execution_enabled": True,
                    }
                ],
            }
        }
        connection.execute(
            "INSERT INTO audit_execution_configurations VALUES(?,?)",
            ("AUD-1", json.dumps(payload)),
        )
        connection.execute(
            "INSERT INTO ai_audit_sessions VALUES(?,?,?,?,?,?,?,?)",
            (
                "AUD-1",
                "AUTO",
                "DEEPSEEK",
                "deepseek-v4-pro",
                "LOW",
                "OPENAI",
                "gpt-5.6-luna",
                "NONE",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    workspace = SimpleNamespace(database=database)
    assert _cat08_required(workspace, "AUD-1") is True
    assert _primary_ai_context(workspace, "AUD-1") == ("auto", "", "")


def test_common_crawl_scoring_reuses_preseal_dataset(tmp_path: Path) -> None:
    database = tmp_path / "observability.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE datasets(dataset_id TEXT,source_type TEXT,collected_at TEXT)"
        )
        connection.execute(
            "INSERT INTO datasets VALUES(?,?,?)",
            ("OBS-OLD", "COMMON_CRAWL_CDX_HISTORY", "2026-09-17T10:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO datasets VALUES(?,?,?)",
            ("OBS-NEW", "COMMON_CRAWL_CDX_HISTORY", "2026-09-17T11:00:00+00:00"),
        )
        connection.commit()
    finally:
        connection.close()

    assert _latest_common_crawl_dataset(tmp_path) == "OBS-NEW"


def test_empty_common_crawl_dataset_is_not_counted_as_source_with_data(tmp_path: Path) -> None:
    audit_database = tmp_path / "audit.db"
    sqlite3.connect(audit_database).close()
    sidecar = tmp_path / "observability.db"
    connection = sqlite3.connect(sidecar)
    try:
        connection.executescript(
            """
            CREATE TABLE datasets(dataset_id TEXT,source_type TEXT,collected_at TEXT);
            CREATE TABLE web_archive_observations(dataset_id TEXT,record_id TEXT);
            CREATE TABLE crux_history(dataset_id TEXT,record_id TEXT);
            """
        )
        connection.execute(
            "INSERT INTO datasets VALUES(?,?,?)",
            ("OBS-CC", "COMMON_CRAWL_CDX_HISTORY", "2026-09-17T11:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO datasets VALUES(?,?,?)",
            ("OBS-CRUX", "CHROME_UX_REPORT_HISTORY", "2026-09-17T11:00:00+00:00"),
        )
        connection.execute("INSERT INTO crux_history VALUES(?,?)", ("OBS-CRUX", "CRUX-1"))
        connection.commit()
    finally:
        connection.close()

    _install_materialized_sidecar_counts()
    from rasai import post_smoke_alignment as alignment

    counts = alignment._sidecar_source_counts(audit_database)
    assert counts.get("CHROME_UX_REPORT_HISTORY") == 1
    assert "COMMON_CRAWL_CDX_HISTORY" not in counts
