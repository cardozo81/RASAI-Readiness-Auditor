from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile

import pytest

from searchgeo.observability.google_search_console import collect_search_analytics
from searchgeo.observability.store import ObservabilityStore


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _workspace(root: Path) -> Path:
    workspace = root / "AUD-GSC-SCOPE"
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
            INSERT INTO audit_targets VALUES ('T1','AUD-GSC-SCOPE','https://example.test','DOMAIN');
            """
        )
        connection.commit()
    finally:
        connection.close()
    return workspace


def test_search_analytics_filters_out_of_scope_pages_from_rows_and_artifact() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))

        def opener(request, timeout=0):
            return _Response(
                {
                    "rows": [
                        {
                            "keys": ["2026-08-31", "q1", "https://example.test/a", "mobile", "bra"],
                            "clicks": 1,
                            "impressions": 10,
                            "ctr": 0.1,
                            "position": 2,
                        },
                        {
                            "keys": ["2026-08-31", "q2", "https://blog.example.test/b", "mobile", "bra"],
                            "clicks": 2,
                            "impressions": 20,
                            "ctr": 0.1,
                            "position": 3,
                        },
                    ],
                    "responseAggregationType": "byPage",
                }
            )

        collect_search_analytics(
            audit_workspace=workspace,
            site_url="sc-domain:example.test",
            access_token="secret",
            start_date="2026-08-01",
            end_date="2026-08-31",
            max_rows=10,
            opener=opener,
        )
        with ObservabilityStore(workspace) as store:
            rows = store.search_rows()
            assert len(rows) == 1
            assert rows[0]["url"] == "https://example.test/a"
            dataset = store.datasets()[0]
            metadata = json.loads(dataset["metadata"])
            assert metadata["api_rows_seen"] == 2
            assert metadata["excluded_out_of_scope_rows"] == 1
            artifact = workspace / dataset["artifact_path"]
            text = artifact.read_text(encoding="utf-8")
            assert "https://example.test/a" in text
            assert "https://blog.example.test/b" not in text


def test_search_analytics_rejects_property_with_only_out_of_scope_rows_without_sidecar() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))

        def opener(request, timeout=0):
            return _Response(
                {
                    "rows": [
                        {
                            "keys": ["2026-08-31", "q", "https://blog.example.test/b", "mobile", "bra"],
                            "clicks": 1,
                            "impressions": 10,
                            "ctr": 0.1,
                            "position": 2,
                        }
                    ]
                }
            )

        with pytest.raises(ValueError, match="none belong to the audited origin"):
            collect_search_analytics(
                audit_workspace=workspace,
                site_url="sc-domain:example.test",
                access_token="secret",
                start_date="2026-08-01",
                end_date="2026-08-31",
                max_rows=1,
                opener=opener,
            )
        assert not (workspace / "observability.db").exists()


def test_search_analytics_requires_page_dimension_for_aud_scoping() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        called = False

        def opener(request, timeout=0):
            nonlocal called
            called = True
            return _Response({"rows": []})

        with pytest.raises(ValueError, match="requires the page dimension"):
            collect_search_analytics(
                audit_workspace=workspace,
                site_url="sc-domain:example.test",
                access_token="secret",
                start_date="2026-08-01",
                end_date="2026-08-31",
                dimensions=("date", "query"),
                opener=opener,
            )
        assert called is False
