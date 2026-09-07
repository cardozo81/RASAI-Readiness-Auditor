from __future__ import annotations

import sqlite3

from searchgeo.monitoring.impact import _search_signals


def test_google_genai_export_metrics_are_non_directional_and_missing_metrics_stay_absent() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE search_performance (
            dataset_id TEXT,
            source TEXT,
            surface TEXT,
            clicks REAL,
            impressions REAL,
            position REAL
        )"""
    )
    source = "GOOGLE_SEARCH_CONSOLE_GENERATIVE_AI_PERFORMANCE_EXPORT_SEARCH"
    connection.execute(
        "INSERT INTO search_performance VALUES (?,?,?,?,?,?)",
        ("OBS-1", source, "GENAI_SEARCH", None, 0.0, None),
    )
    selected = {
        source: {
            "dataset_id": "OBS-1",
            "source": source,
            "period_start": "2026-08-01",
            "period_end": "2026-08-31",
            "collected_at": "2026-09-01T00:00:00+00:00",
        }
    }
    output: dict[str, dict] = {}
    _search_signals(connection, output, selected)

    impressions = output[f"SEARCH|{source}|GENAI_SEARCH|impressions"]
    assert impressions["value"] == 0.0
    assert impressions["direction"] == "STATE"
    assert f"SEARCH|{source}|GENAI_SEARCH|clicks" not in output
    assert f"SEARCH|{source}|GENAI_SEARCH|ctr" not in output
    assert f"SEARCH|{source}|GENAI_SEARCH|position" not in output
