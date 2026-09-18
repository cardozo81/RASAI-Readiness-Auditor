from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.catalog_report_page import _web_performance_diagnostics_html


def test_cat04_exposes_persisted_external_failure_diagnostics(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            CREATE TABLE web_performance_attempts(
                audit_id TEXT, service TEXT, status TEXT, http_status INTEGER,
                error_code TEXT, error_message TEXT
            )
            """
        )
        connection.executemany(
            "INSERT INTO web_performance_attempts VALUES (?,?,?,?,?,?)",
            [
                (
                    "AUD-WEB",
                    "PAGESPEED_INSIGHTS",
                    "ERROR",
                    500,
                    None,
                    "Lighthouse returned error: Something went wrong.",
                ),
                ("AUD-WEB", "CRUX_API", "SUCCESS", 200, None, None),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    data = SimpleNamespace(
        audit_id="AUD-WEB",
        work_items=[
            {
                "component": "WEB_PERFORMANCE",
                "status": "FAILED_RETRYABLE",
                "retryable": 1,
                "last_error_class": "EXTERNAL_SERVICE",
                "last_error_code": "PARTIAL",
                "last_error_message": "web performance state=PARTIAL",
            }
        ],
    )

    rendered = _web_performance_diagnostics_html(database, data)

    assert "PageSpeed Insights" in rendered
    assert "Erro" in rendered
    assert "HTTP 500" in rendered
    assert "Lighthouse returned error: Something went wrong." in rendered
    assert "CrUX API" in rendered
    assert "Concluído" in rendered
    assert "HTTP 200" in rendered
    assert "Falha reprocessável" in rendered
    assert "EXTERNAL_SERVICE" in rendered
    assert "PARTIAL" in rendered
    assert "Reprocessável" in rendered
