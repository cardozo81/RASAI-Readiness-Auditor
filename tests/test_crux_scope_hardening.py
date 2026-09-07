from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile

import pytest

from searchgeo.observability.crux_history import collect_crux_history
from searchgeo.observability.store import ObservabilityStore


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _workspace(root: Path) -> Path:
    workspace = root / "AUD-CRUX-SCOPE"
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
            INSERT INTO audit_targets VALUES ('T1','AUD-CRUX-SCOPE','https://example.test','DOMAIN');
            """
        )
        connection.commit()
    finally:
        connection.close()
    return workspace


def _opener(request, timeout=0):
    return _Response(
        {
            "record": {
                "collectionPeriods": [
                    {
                        "firstDate": {"year": 2026, "month": 8, "day": 1},
                        "lastDate": {"year": 2026, "month": 8, "day": 28},
                    }
                ],
                "metrics": {
                    "largest_contentful_paint": {
                        "percentilesTimeseries": {"p75s": [2400]},
                        "histogramTimeseries": [
                            {"densities": [0.8]},
                            {"densities": [0.15]},
                            {"densities": [0.05]},
                        ],
                    }
                },
            }
        }
    )


def test_direct_crux_rejects_outside_origin_before_network_call() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        called = False

        def opener(request, timeout=0):
            nonlocal called
            called = True
            return _opener(request, timeout)

        with pytest.raises(ValueError, match="outside audited origin"):
            collect_crux_history(
                audit_workspace=workspace,
                api_key="secret",
                target="https://outside.test/",
                target_scope="origin",
                metrics=("largest_contentful_paint",),
                opener=opener,
            )
        assert called is False
        assert not (workspace / "observability.db").exists()


def test_direct_crux_origin_scope_rejects_path() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        with pytest.raises(ValueError, match="must not contain path"):
            collect_crux_history(
                audit_workspace=workspace,
                api_key="secret",
                target="https://example.test/path",
                target_scope="origin",
                metrics=("largest_contentful_paint",),
                opener=_opener,
            )


def test_direct_crux_in_scope_origin_is_normalized_and_key_not_persisted() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        dataset = collect_crux_history(
            audit_workspace=workspace,
            api_key="never-persist-this-key",
            target="https://example.test/",
            target_scope="origin",
            metrics=("largest_contentful_paint",),
            opener=_opener,
        )
        assert dataset.startswith("OBS-")
        with ObservabilityStore(workspace) as store:
            rows = store.crux_rows()
            assert len(rows) == 1
            assert rows[0]["target"] == "https://example.test"
            assert rows[0]["target_scope"] == "ORIGIN"
            info = store.datasets()[0]
            artifact = workspace / info["artifact_path"]
            assert "never-persist-this-key" not in artifact.read_text(encoding="utf-8")
