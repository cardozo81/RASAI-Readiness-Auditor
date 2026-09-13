from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from rasai.external_observability_policy import clarity_dimensions
from rasai.external_observability_reporting import enrich_external_observability_reports
from rasai.observability.external_sources import (
    archive_rows,
    behavioral_rows,
    collect_clarity_insights,
    collect_common_crawl_history,
)
from rasai.observability.store import ObservabilityStore
from rasai.standards_service_registry import service, service_state
from rasai.system_defaults import load_system_defaults


class _Response:
    def __init__(self, value: object, *, raw: bool = False) -> None:
        self._data = value if raw else json.dumps(value).encode("utf-8")
        if isinstance(self._data, str):
            self._data = self._data.encode("utf-8")

    def read(self) -> bytes:
        return bytes(self._data)


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "AUD-EXT"
    root.mkdir()
    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audit_targets(audit_id TEXT NOT NULL, normalized_origin TEXT NOT NULL);
            CREATE TABLE pages(page_id TEXT PRIMARY KEY, audit_id TEXT NOT NULL, normalized_url TEXT NOT NULL);
            CREATE TABLE page_snapshots(snapshot_id TEXT PRIMARY KEY, page_id TEXT NOT NULL, device TEXT NOT NULL);
            """
        )
        connection.execute("INSERT INTO audit_targets VALUES (?,?)", ("AUD-EXT", "https://example.com"))
        connection.execute("INSERT INTO pages VALUES (?,?,?)", ("P1", "AUD-EXT", "https://example.com/a"))
        connection.execute("INSERT INTO page_snapshots VALUES (?,?,?)", ("S1", "P1", "mobile"))
        connection.commit()
    finally:
        connection.close()
    report = root / "report"
    report.mkdir()
    shell = "<html><body><main><section class='panel'>base</section></main><footer>end</footer></body></html>"
    for name in ("observability.html", "apdex-experience.html", "crawling-discovery.html", "web-performance.html"):
        (report / name).write_text(shell, encoding="utf-8")
    return root


def test_service_defaults_are_safe_and_scope_aware() -> None:
    common = service_state(service("common-crawl"), {})
    assert common["state"] == "READY"
    assert common["effective_enabled"] is True

    clarity = service("microsoft-clarity")
    assert service_state(clarity, {})["state"] == "DISABLED"
    assert service_state(clarity, {"RASAI_CLARITY_API_TOKEN": "secret"})["state"] == "DISABLED"
    assert service_state(clarity, {"RASAI_CLARITY_ENABLED": "true"})["state"] == "NOT_CONFIGURED"
    ready = service_state(
        clarity,
        {"RASAI_CLARITY_ENABLED": "true", "RASAI_CLARITY_API_TOKEN": "secret"},
    )
    assert ready["state"] == "READY"

    history = service_state(service("crux-history"), {"RASAI_CRUX_API_KEY": "key"})
    assert history["state"] == "READY"
    assert history["effective_enabled"] is True


def test_clarity_dimensions_require_url_scope() -> None:
    assert clarity_dimensions("URL,Device") == ("URL", "Device")
    with pytest.raises(ValueError, match="inclua URL"):
        clarity_dimensions("Device,Country/Region")


def test_packaged_defaults_enable_only_credential_free_external_collection() -> None:
    parser = load_system_defaults()
    assert parser.getboolean("environment", "RASAI_COMMON_CRAWL_ENABLED") is True
    assert parser.getint("environment", "RASAI_COMMON_CRAWL_MAX_URLS") == 3
    assert parser.getint("environment", "RASAI_COMMON_CRAWL_INDEX_COUNT") == 2
    assert parser.getboolean("environment", "RASAI_CLARITY_ENABLED") is False
    assert parser.get("environment", "RASAI_CLARITY_DIMENSIONS") == "URL,Device"
    assert not parser.has_option("environment", "RASAI_CRUX_HISTORY_ENABLED")
    source = Path(__file__).parents[1] / "src" / "rasai" / "config" / "rasai-defaults.ini"
    text = source.read_text(encoding="utf-8")
    assert "RASAI_CLARITY_API_TOKEN" not in text
    assert "RASAI_CRUX_API_KEY" not in text


def test_clarity_persists_aggregates_only_and_filters_origin(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    payload = [
        {
            "metricName": "Rage Click Count",
            "information": [
                {"URL": "https://example.com/a", "Device": "Mobile", "sessionsCount": "3"},
                {"URL": "https://other.example.net/x", "Device": "PC", "sessionsCount": "99"},
            ],
        }
    ]

    def opener(request, timeout):
        assert request.get_header("Authorization") == "Bearer clarity-secret"
        assert timeout > 0
        return _Response(payload)

    dataset_id = collect_clarity_insights(
        audit_workspace=root,
        api_token="clarity-secret",
        days=1,
        dimensions=("URL", "Device"),
        opener=opener,
    )
    rows = behavioral_rows(root)
    assert len(rows) == 1
    assert rows[0]["dataset_id"] == dataset_id
    assert rows[0]["normalized_url"] == "https://example.com/a"
    assert rows[0]["device"] == "Mobile"

    with ObservabilityStore(root) as store:
        dataset = next(row for row in store.datasets() if row["dataset_id"] == dataset_id)
        artifact = root / str(dataset["artifact_path"])
    text = artifact.read_text(encoding="utf-8")
    assert "clarity-secret" not in text
    assert "other.example.net" not in text
    assert "session replay" not in text.casefold()


def test_common_crawl_is_bounded_and_does_not_fetch_warc(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    calls: list[str] = []

    def opener(request, timeout):
        calls.append(request.full_url)
        if request.full_url.endswith("collinfo.json"):
            return _Response([
                {"id": "CC-MAIN-2026-34", "cdx-api": "https://index.commoncrawl.org/CC-MAIN-2026-34-index"},
                {"id": "CC-MAIN-2026-30", "cdx-api": "https://index.commoncrawl.org/CC-MAIN-2026-30-index"},
                {"id": "CC-MAIN-2026-26", "cdx-api": "https://index.commoncrawl.org/CC-MAIN-2026-26-index"},
            ])
        line = json.dumps({
            "url": "https://example.com/a",
            "timestamp": "20260820112233",
            "status": "200",
            "mime": "text/html",
            "digest": "sha1:TEST",
            "filename": "crawl-data/example.warc.gz",
            "offset": "10",
            "length": "20",
        })
        return _Response(line + "\n", raw=True)

    dataset_id = collect_common_crawl_history(
        audit_workspace=root,
        max_urls=1,
        collection_count=2,
        min_interval_seconds=0,
        opener=opener,
    )
    rows = archive_rows(root)
    assert len(rows) == 2
    assert {row["dataset_id"] for row in rows} == {dataset_id}
    assert len(calls) == 3  # collinfo + one exact URL in each of two indexes
    assert all("data.commoncrawl.org" not in call for call in calls)

    with ObservabilityStore(root) as store:
        dataset = next(row for row in store.datasets() if row["dataset_id"] == dataset_id)
        metadata = json.loads(dataset["metadata"])
    assert metadata["warc_content_fetched"] is False
    assert metadata["device_dimension"] is False


def test_external_data_is_projected_only_into_relevant_reports(tmp_path: Path) -> None:
    root = _workspace(tmp_path)

    collect_clarity_insights(
        audit_workspace=root,
        api_token="token",
        dimensions=("URL", "Device"),
        opener=lambda request, timeout: _Response([
            {"metricName": "Dead Click Count", "information": [{"URL": "https://example.com/a", "Device": "Mobile", "count": 2}]}
        ]),
    )
    collect_common_crawl_history(
        audit_workspace=root,
        max_urls=1,
        collection_count=1,
        min_interval_seconds=0,
        opener=lambda request, timeout: (
            _Response([{"id": "CC-MAIN-2026-34", "cdx-api": "https://index.commoncrawl.org/CC-MAIN-2026-34-index"}])
            if request.full_url.endswith("collinfo.json")
            else _Response(json.dumps({"url": "https://example.com/a", "timestamp": "20260820112233", "status": "200", "mime": "text/html"}) + "\n", raw=True)
        ),
    )

    changed = enrich_external_observability_reports(audit_workspace=root)
    assert changed
    assert "Microsoft Clarity" in (root / "report" / "apdex-experience.html").read_text(encoding="utf-8")
    assert "Common Crawl" in (root / "report" / "crawling-discovery.html").read_text(encoding="utf-8")
    observability = (root / "report" / "observability.html").read_text(encoding="utf-8")
    assert "Behavioral UX" in observability
    assert "Web history" in observability
