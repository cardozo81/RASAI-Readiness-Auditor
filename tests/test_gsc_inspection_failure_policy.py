from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sqlite3
import tempfile
from urllib.error import HTTPError

import pytest

from searchgeo.observability.google_search_console import collect_url_inspection
from searchgeo.observability.store import ObservabilityStore


def _workspace(root: Path) -> Path:
    workspace = root / "AUD-GSC-FAIL"
    workspace.mkdir()
    connection = sqlite3.connect(workspace / "audit.db")
    try:
        connection.executescript(
            """
            CREATE TABLE pages (page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            INSERT INTO pages VALUES ('P1','AUD-GSC-FAIL','https://example.test/a');
            INSERT INTO pages VALUES ('P2','AUD-GSC-FAIL','https://example.test/b');
            """
        )
        connection.commit()
    finally:
        connection.close()
    return workspace


def _http_error(code: int) -> HTTPError:
    return HTTPError(
        url="https://searchconsole.googleapis.com/",
        code=code,
        msg="test",
        hdrs=None,
        fp=BytesIO(b'{"error":"test"}'),
    )


@pytest.mark.parametrize("status", [401, 403, 429, 500, 502, 503, 504])
def test_url_inspection_aborts_after_first_systemic_http_failure(status: int) -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        calls = 0

        def opener(request, timeout=0):
            nonlocal calls
            calls += 1
            raise _http_error(status)

        with pytest.raises(RuntimeError, match=f"Google API HTTP {status}"):
            collect_url_inspection(
                audit_workspace=workspace,
                site_url="sc-domain:example.test",
                access_token="bad-or-blocked-token",
                urls=("https://example.test/a", "https://example.test/b"),
                opener=opener,
            )
        assert calls == 1
        assert not (workspace / "observability.db").exists()


def test_url_inspection_keeps_url_specific_error_and_continues() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        calls = 0

        def opener(request, timeout=0):
            nonlocal calls
            calls += 1
            raise _http_error(404)

        dataset = collect_url_inspection(
            audit_workspace=workspace,
            site_url="sc-domain:example.test",
            access_token="token",
            urls=("https://example.test/a", "https://example.test/b"),
            opener=opener,
        )
        assert calls == 2
        with ObservabilityStore(workspace) as store:
            rows = store.index_rows()
            assert len(rows) == 2
            assert all(row["verdict"] == "ERROR" for row in rows)
            metadata = store.datasets()[0]["metadata"]
            assert '"errors":2' in metadata
        assert dataset.startswith("OBS-")
