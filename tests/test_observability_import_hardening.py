from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile

import pytest

from searchgeo.observability.importers import (
    import_bing_search_performance_csv,
    import_observability_json,
)
from searchgeo.observability.store import ObservabilityStore


def _workspace(root: Path) -> Path:
    workspace = root / "AUD-IMPORT-HARDENING"
    workspace.mkdir()
    connection = sqlite3.connect(workspace / "audit.db")
    try:
        connection.executescript(
            """
            CREATE TABLE audit_targets (
                target_id TEXT PRIMARY KEY,
                audit_id TEXT,
                normalized_origin TEXT,
                target_type TEXT
            );
            INSERT INTO audit_targets VALUES ('T1','AUD-IMPORT-HARDENING','https://example.test','DOMAIN');
            """
        )
        connection.commit()
    finally:
        connection.close()
    return workspace


def test_bing_surface_override_participates_in_dataset_identity() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root)
        source = root / "bing.csv"
        source.write_text(
            "Date,Query,Page,Clicks,Impressions,CTR,Position\n"
            "2026-08-31,seguro,https://example.test/a,1,10,10%,2\n",
            encoding="utf-8",
        )
        web = import_bing_search_performance_csv(
            audit_workspace=workspace,
            path=source,
            surface="Web",
        )
        chat = import_bing_search_performance_csv(
            audit_workspace=workspace,
            path=source,
            surface="Chat",
        )
        assert web != chat
        with ObservabilityStore(workspace) as store:
            datasets = store.datasets()
            rows = store.search_rows()
            assert len(datasets) == 2
            assert len(rows) == 2
            assert {row["surface"] for row in rows} == {"Web", "Chat"}
            assert {row["source"] for row in rows} == {
                "BING_WEBMASTER_TOOLS_SEARCH_PERFORMANCE_EXPORT_WEB",
                "BING_WEBMASTER_TOOLS_SEARCH_PERFORMANCE_EXPORT_CHAT",
            }
            assert len({row["artifact_sha256"] for row in datasets}) == 1


def test_generic_crux_import_rejects_target_outside_audited_origin() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root)
        source = root / "obs.json"
        source.write_text(
            json.dumps(
                {
                    "format_version": "RASAI-OBS-IMPORT-001",
                    "source": {"type": "TEST_CRUX", "capture_method": "TEST"},
                    "crux_history": [
                        {
                            "target": "https://outside.test/",
                            "target_scope": "ORIGIN",
                            "metric": "largest_contentful_paint",
                            "period_start": "2026-08-01",
                            "period_end": "2026-08-31",
                            "p75": 2500,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="outside audited origin"):
            import_observability_json(audit_workspace=workspace, path=source)


def test_generic_crux_origin_scope_rejects_path_and_reversed_period() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root)
        source = root / "obs.json"
        payload = {
            "format_version": "RASAI-OBS-IMPORT-001",
            "source": {"type": "TEST_CRUX", "capture_method": "TEST"},
            "crux_history": [
                {
                    "target": "https://example.test/path",
                    "target_scope": "ORIGIN",
                    "metric": "largest_contentful_paint",
                    "period_start": "2026-08-01",
                    "period_end": "2026-08-31",
                    "p75": 2500,
                }
            ],
        }
        source.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="must be an origin"):
            import_observability_json(audit_workspace=workspace, path=source)

        payload["crux_history"][0]["target"] = "https://example.test/"
        payload["crux_history"][0]["period_start"] = "2026-09-01"
        payload["crux_history"][0]["period_end"] = "2026-08-31"
        source.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="start cannot be after end"):
            import_observability_json(audit_workspace=workspace, path=source)
