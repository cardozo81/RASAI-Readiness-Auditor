from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import sqlite3
import tempfile

from rasai.observability.crux_history import collect_crux_history
from rasai.observability.google_search_console import collect_search_analytics, collect_url_inspection
from rasai.observability.importers import import_bing_search_performance_csv
from rasai.observability.store import ObservabilityStore


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _workspace(root: Path) -> Path:
    workspace = root / "AUD-OBS-COLLECT"
    workspace.mkdir()
    connection = sqlite3.connect(workspace / "audit.db")
    try:
        connection.executescript(
            """
            CREATE TABLE audit_targets (target_id TEXT PRIMARY KEY,audit_id TEXT,normalized_origin TEXT,target_type TEXT);
            INSERT INTO audit_targets VALUES ('T','AUD-OBS-COLLECT','https://example.test','DOMAIN');
            CREATE TABLE pages (page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            INSERT INTO pages VALUES ('P1','AUD-OBS-COLLECT','https://example.test/a');
            INSERT INTO pages VALUES ('P2','AUD-OBS-COLLECT','https://example.test/b');
            """
        )
        connection.commit()
    finally:
        connection.close()
    return workspace


def test_search_analytics_collects_and_does_not_persist_token() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        calls: list[object] = []

        def opener(request, timeout=0):
            calls.append(request)
            return _Response({
                "rows": [{
                    "keys": ["2026-08-31", "seguro viagem", "https://example.test/a", "mobile", "bra"],
                    "clicks": 10, "impressions": 100, "ctr": 0.1, "position": 2.5,
                }],
                "responseAggregationType": "byPage",
            })

        dataset = collect_search_analytics(
            audit_workspace=workspace, site_url="sc-domain:example.test", access_token="secret-oauth-token",
            start_date="2026-08-01", end_date="2026-08-31", opener=opener,
        )
        assert dataset.startswith("OBS-")
        with ObservabilityStore(workspace) as store:
            rows = store.search_rows()
            datasets = store.datasets()
            assert len(rows) == 1
            assert rows[0]["query_text"] == "seguro viagem"
            artifact = workspace / datasets[0]["artifact_path"]
            assert "secret-oauth-token" not in artifact.read_text(encoding="utf-8")
        assert calls


def test_url_inspection_normalizes_canonical_state() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))

        def opener(request, timeout=0):
            return _Response({
                "inspectionResult": {
                    "inspectionResultLink": "https://search.google.com/test",
                    "indexStatusResult": {
                        "verdict": "PASS",
                        "coverageState": "Submitted and indexed",
                        "indexingState": "INDEXING_ALLOWED",
                        "robotsTxtState": "ALLOWED",
                        "pageFetchState": "SUCCESSFUL",
                        "userCanonical": "https://example.test/a",
                        "googleCanonical": "https://example.test/b",
                        "lastCrawlTime": "2026-08-31T10:00:00Z",
                        "crawledAs": "MOBILE",
                        "referringUrls": ["https://example.test/"],
                        "sitemap": ["https://example.test/sitemap.xml"],
                    },
                }
            })

        collect_url_inspection(
            audit_workspace=workspace, site_url="sc-domain:example.test", access_token="token",
            urls=("https://example.test/a",), opener=opener,
        )
        with ObservabilityStore(workspace) as store:
            rows = store.index_rows()
            assert len(rows) == 1
            assert rows[0]["selected_canonical"] == "https://example.test/b"
            assert rows[0]["verdict"] == "PASS"


def test_crux_history_persists_weekly_series_without_api_key() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))

        def opener(request, timeout=0):
            return _Response({
                "record": {
                    "collectionPeriods": [
                        {"firstDate":{"year":2026,"month":8,"day":1},"lastDate":{"year":2026,"month":8,"day":28}},
                        {"firstDate":{"year":2026,"month":8,"day":8},"lastDate":{"year":2026,"month":9,"day":4}},
                    ],
                    "metrics": {
                        "largest_contentful_paint": {
                            "percentilesTimeseries": {"p75s": [2100, 2500]},
                            "histogramTimeseries": [
                                {"densities":[0.8,0.7]}, {"densities":[0.15,0.2]}, {"densities":[0.05,0.1]}
                            ],
                        }
                    },
                }
            })

        collect_crux_history(
            audit_workspace=workspace, api_key="do-not-persist", target="https://example.test/a",
            target_scope="url", form_factor="PHONE", metrics=("largest_contentful_paint",), opener=opener,
        )
        with ObservabilityStore(workspace) as store:
            rows = store.crux_rows()
            datasets = store.datasets()
            assert len(rows) == 2
            assert rows[-1]["p75"] == 2500
            artifact = workspace / datasets[0]["artifact_path"]
            assert "do-not-persist" not in artifact.read_text(encoding="utf-8")


def test_bing_csv_import_is_same_origin_and_normalized() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _workspace(root)
        source = root / "bing.csv"
        source.write_text(
            "Date,Query,Page,Clicks,Impressions,CTR,Position,Source\n"
            "2026-08-31,seguro viagem,https://example.test/a,10,100,10%,3.2,Chat\n",
            encoding="utf-8",
        )
        dataset = import_bing_search_performance_csv(audit_workspace=workspace, path=source)
        assert dataset.startswith("OBS-")
        with ObservabilityStore(workspace) as store:
            row = store.search_rows()[0]
            assert row["surface"] == "Chat"
            assert row["ctr"] == 0.1
            assert row["position"] == 3.2
