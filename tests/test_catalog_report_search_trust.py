from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.catalog_report_search_trust import (
    _external_html,
    _overview_references,
    _serp_html,
    _source_states,
)


AUDIT_ID = "AUD-CAT05"


def _audit_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            f"""
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY, started_at TEXT, created_at TEXT);
            INSERT INTO audits VALUES('{AUDIT_ID}','2026-09-17T10:00:00+00:00','2026-09-17T09:59:00+00:00');
            """
        )
        connection.commit()
    finally:
        connection.close()


def _data(configuration: dict | None = None):
    return SimpleNamespace(
        audit_id=AUDIT_ID,
        configuration=configuration or {},
        work_items=(),
        targets=("https://example.test/",),
    )


def test_gsc_configured_but_not_requested_remains_explicitly_not_requested(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _audit_db(database)
    data = _data(
        {
            "environment": {
                "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL": "https://example.test/",
                "RASAI_GSC_ENABLED": "false",
                "RASAI_COMMON_CRAWL_ENABLED": "false",
                "RASAI_CLARITY_ENABLED": "false",
            }
        }
    )

    states = {item.source_id: item for item in _source_states(database, data)}
    gsc = states["GOOGLE_SEARCH_CONSOLE"]
    assert gsc.configured is True
    assert gsc.requested is False
    assert gsc.enabled is False
    assert gsc.executed is False
    assert gsc.data_available is False
    assert gsc.execution_status == "NOT_REQUESTED"
    assert "não solicitado" in gsc.detail


def test_common_crawl_errors_without_rows_are_visible_in_state(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _audit_db(database)
    obs = sqlite3.connect(tmp_path / "observability.db")
    try:
        obs.executescript(
            """
            CREATE TABLE datasets(
                dataset_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                capture_method TEXT NOT NULL,
                period_start TEXT,
                period_end TEXT,
                artifact_path TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                metadata TEXT NOT NULL,
                collected_at TEXT NOT NULL
            );
            CREATE TABLE web_archive_observations(
                record_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                collection TEXT NOT NULL,
                target_url TEXT NOT NULL,
                captured_at TEXT,
                status TEXT,
                mime TEXT,
                digest TEXT,
                warc_filename TEXT,
                warc_offset INTEGER,
                warc_length INTEGER,
                metadata_json TEXT NOT NULL,
                PRIMARY KEY(dataset_id,record_id)
            );
            """
        )
        obs.execute(
            "INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "OBS-CC",
                "COMMON_CRAWL_CDX_HISTORY",
                "DIRECT_PUBLIC_INDEX_API",
                None,
                None,
                "artifacts/observability/common-crawl.json",
                "abc",
                json.dumps({"requests": 2, "rows": 0, "errors": 2}),
                "2026-09-17T10:10:00+00:00",
            ),
        )
        obs.commit()
    finally:
        obs.close()
    data = _data({"environment": {"RASAI_COMMON_CRAWL_ENABLED": "true"}})

    states = {item.source_id: item for item in _source_states(database, data)}
    common = states["COMMON_CRAWL"]
    assert common.requested is True
    assert common.executed is True
    assert common.result_count == 0
    assert common.error_count == 2
    assert common.data_available is False
    assert common.data_status == "ERROR"
    assert common.execution_status == "PARTIAL"


def test_ai_overview_is_projected_from_persisted_serp_artifact(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _audit_db(database)
    artifact = tmp_path / "artifacts" / "serp" / "SERP-1" / "raw.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps(
            {
                "provider": "serpapi",
                "pages": [
                    {
                        "ai_overview": {
                            "text": "Resumo gerado para a consulta.",
                            "sources": [
                                {"link": "https://example.test/guide"},
                                {"link": "https://other.example/source"},
                            ],
                        }
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE serp_observations(
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                query TEXT NOT NULL,
                query_origin TEXT NOT NULL,
                engine TEXT NOT NULL,
                country TEXT NOT NULL,
                region TEXT,
                language TEXT NOT NULL,
                device TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_request_id TEXT,
                requested_depth INTEGER NOT NULL,
                result_count INTEGER NOT NULL,
                data_mode TEXT NOT NULL,
                observation_status TEXT NOT NULL,
                domain_of_interest TEXT,
                customer_position INTEGER,
                domain_status TEXT NOT NULL,
                raw_evidence_ref TEXT,
                raw_evidence_sha256 TEXT,
                config_metadata TEXT NOT NULL,
                quality_metadata TEXT NOT NULL,
                error_code TEXT,
                error_message TEXT
            );
            CREATE TABLE serp_results(
                observation_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                domain TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                snippet TEXT,
                result_type TEXT NOT NULL,
                serp_features TEXT NOT NULL,
                metadata TEXT NOT NULL,
                PRIMARY KEY(observation_id,position,url)
            );
            CREATE TABLE serp_evidence_provenance(
                observation_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                temporal_mode TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                source_audit_id TEXT,
                source_observation_id TEXT,
                reused_at TEXT,
                reuse_reason TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "SERP-1", AUDIT_ID, "RUN-1", "rasai", "MANUAL", "google", "BR", None,
                "pt-BR", "desktop", "2026-09-17T10:05:00+00:00", "serpapi", "REQ-1", 20,
                1, "OBSERVED_API", "OBSERVED", "example.test", 1, "FOUND",
                "artifacts/serp/SERP-1/raw.json", "abc", "{}", "{}", None, None,
            ),
        )
        connection.execute(
            "INSERT INTO serp_results VALUES (?,?,?,?,?,?,?,?,?)",
            ("SERP-1",1,"example.test","https://example.test/","Example",None,"organic","[]","{}"),
        )
        connection.execute(
            "INSERT INTO serp_evidence_provenance VALUES (?,?,?,?,?,?,?,?,?)",
            ("SERP-1",AUDIT_ID,"LIVE_RECOLLECTION","2026-09-17T10:05:00+00:00",AUDIT_ID,"SERP-1",None,None,"2026-09-17T10:05:00+00:00"),
        )
        connection.commit()
    finally:
        connection.close()

    html = _serp_html(database, _data())
    assert "AI Overview detectado" in html
    assert "Resumo gerado para a consulta" in html
    assert "https://example.test/guide" in html
    assert "Site auditado entre as referências" in html
    assert "Sim" in html


def test_ai_overview_reference_count_excludes_icons_and_thumbnails() -> None:
    references = _overview_references([
        {
            "references": [
                {
                    "index": 0,
                    "link": "https://example.test/source",
                    "source": "Example",
                    "source_icon": "https://assets.test/favicon.png",
                    "thumbnail": "https://assets.test/thumb.png",
                },
                {
                    "index": 1,
                    "link": "https://other.test/source",
                    "source": "Other",
                },
            ]
        }
    ])
    assert [row["link"] for row in references] == [
        "https://example.test/source",
        "https://other.test/source",
    ]


def test_common_crawl_error_modal_exposes_exception_and_recovery_steps(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    _audit_db(database)
    artifact = tmp_path / "artifacts" / "observability" / "common-crawl.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps({
            "errors": ["CC-MAIN-TEST:https://example.test/:RuntimeError:HTTP 503"],
            "error_details": [{
                "collection": "CC-MAIN-TEST",
                "target_url": "https://example.test/",
                "endpoint": "https://index.commoncrawl.org/CC-MAIN-TEST-index",
                "error_type": "RuntimeError",
                "message": "HTTP 503",
            }],
        }),
        encoding="utf-8",
    )
    obs = sqlite3.connect(tmp_path / "observability.db")
    try:
        obs.executescript(
            """
            CREATE TABLE datasets(
                dataset_id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                capture_method TEXT NOT NULL,
                period_start TEXT,
                period_end TEXT,
                artifact_path TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL,
                metadata TEXT NOT NULL,
                collected_at TEXT NOT NULL
            );
            CREATE TABLE web_archive_observations(
                record_id TEXT,dataset_id TEXT,collection TEXT,target_url TEXT,captured_at TEXT,
                status TEXT,mime TEXT,digest TEXT,warc_filename TEXT,warc_offset INTEGER,
                warc_length INTEGER,metadata_json TEXT
            );
            CREATE TABLE behavioral_observations(record_id TEXT,dataset_id TEXT);
            """
        )
        obs.execute(
            "INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "OBS-CC", "COMMON_CRAWL_CDX_HISTORY", "DIRECT_PUBLIC_INDEX_API",
                None, None, "artifacts/observability/common-crawl.json", "abc",
                json.dumps({"requests": 1, "rows": 0, "errors": 1}),
                "2026-09-18T10:00:00+00:00",
            ),
        )
        obs.commit()
    finally:
        obs.close()

    html = _external_html(database, _data())
    assert "Ver erro e como corrigir" in html
    assert "HTTP 503" in html
    assert "index.commoncrawl.org/CC-MAIN-TEST-index" in html
    assert "reprocessamento seletivo" in html
    assert "Falha do Common Crawl não implica erro no site" in html
