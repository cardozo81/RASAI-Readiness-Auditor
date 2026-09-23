from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.catalog_report_analysis import _integration_indicator
from rasai.catalog_report_catalog_state import _catalog_sources
from rasai.catalog_report_evidence import (
    _crux_provenance_html,
    _lighthouse_accessibility_html,
)


AUDIT_ID = "AUD-SMOKE-PROVENANCE"


def _database(tmp_path: Path, schema: str) -> Path:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(schema)
        connection.commit()
    finally:
        connection.close()
    return database


def test_cat02_no_lighthouse_result_does_not_imply_accessibility_score_exists(tmp_path: Path) -> None:
    database = _database(
        tmp_path,
        """
        CREATE TABLE web_performance_observations(
            audit_id TEXT,
            accessibility_score REAL,
            pagespeed_artifact_reference TEXT
        );
        INSERT INTO web_performance_observations VALUES(
            'AUD-SMOKE-PROVENANCE', NULL, NULL
        );
        """,
    )

    html = _lighthouse_accessibility_html(
        database,
        SimpleNamespace(audit_id=AUDIT_ID),
    )

    assert "Sem resultado automatizado de acessibilidade" in html
    assert "não materializou pontuação nem artefato detalhado" in html
    assert "CrUX de performance" in html
    assert "pode estar persistida" not in html


def test_cat04_crux_provenance_exposes_exact_scope_device_and_period(tmp_path: Path) -> None:
    database = _database(
        tmp_path,
        """
        CREATE TABLE web_performance_observations(
            audit_id TEXT,
            url TEXT,
            field_scope TEXT,
            crux_artifact_reference TEXT
        );
        INSERT INTO web_performance_observations VALUES(
            'AUD-SMOKE-PROVENANCE',
            'https://example.test/',
            'URL',
            'artifacts/web-performance/current.crux.json'
        );
        """,
    )
    artifact = tmp_path / "artifacts" / "web-performance" / "current.crux.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps(
            {
                "record": {
                    "key": {
                        "formFactor": "PHONE",
                        "url": "https://example.test/",
                    },
                    "collectionPeriod": {
                        "firstDate": {"year": 2026, "month": 8, "day": 21},
                        "lastDate": {"year": 2026, "month": 9, "day": 17},
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    html = _crux_provenance_html(
        database,
        SimpleNamespace(audit_id=AUDIT_ID),
    )

    assert "Proveniência dos dados CrUX" in html
    assert "CrUX API · medição atual" in html
    assert "URL exata" in html
    assert "Telefone" in html
    assert "21/08/2026 a 17/09/2026" in html
    assert "https://example.test/" in html


def test_cat02_counts_only_pagespeed_as_accessibility_integration(tmp_path: Path) -> None:
    database = _database(
        tmp_path,
        """
        CREATE TABLE web_performance_attempts(
            audit_id TEXT,
            service TEXT,
            status TEXT
        );
        CREATE TABLE web_performance_observations(
            audit_id TEXT,
            accessibility_score REAL
        );
        INSERT INTO web_performance_attempts VALUES(
            'AUD-SMOKE-PROVENANCE', 'PAGESPEED_INSIGHTS', 'ERROR'
        );
        INSERT INTO web_performance_attempts VALUES(
            'AUD-SMOKE-PROVENANCE', 'CRUX_API', 'SUCCESS'
        );
        INSERT INTO web_performance_observations VALUES(
            'AUD-SMOKE-PROVENANCE', NULL
        );
        """,
    )
    data = SimpleNamespace(audit_id=AUDIT_ID)

    sources = _catalog_sources(database, data, "CAT-02")
    rendered = _integration_indicator(database, data, "CAT-02")

    assert sources == [
        ("web_performance_attempts", "Tentativas PageSpeed/Lighthouse", 1)
    ]
    assert "PageSpeed Insights" in rendered
    assert "Crux Api" not in rendered
