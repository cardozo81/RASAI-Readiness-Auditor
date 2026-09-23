from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from rasai.device_context import DEVICE_CONTEXT_ENV
from rasai.domain import DeviceContext
from rasai.m3 import execute_m3
from rasai.rendering import BrowserRenderResult


class _Collection:
    def __init__(self, items: dict[str, object] | None = None) -> None:
        self.items = items or {}
        self.added: list[object] = []

    def get(self, key: str):
        return self.items.get(key)

    def add(self, value: object) -> None:
        self.added.append(value)


class _Persistence:
    def __init__(self, page: object) -> None:
        self.pages = _Collection({"PGE-1": page})
        self.snapshots = _Collection()
        self.evidence = _Collection()


class _M14:
    def __init__(self, _workspace: object) -> None:
        self.observations: list[object] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def add_element_observation(self, value: object) -> None:
        self.observations.append(value)


class _Renderer:
    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult:
        return BrowserRenderResult(
            requested_url=url,
            final_url=url,
            http_status=200,
            content_type="text/html",
            rendered_html="<html><body>ok</body></html>",
            browser_metadata={
                "engine": "test",
                "profile": {"device": device.value},
                "document_source": {
                    "capture_state": "SKIPPED_NOT_FINISHED",
                    "additional_network_requests": 0,
                },
            },
        )


class _Acquisition:
    body = b""
    redirects: tuple[object, ...] = ()
    requested_url = "https://example.test/page"
    final_url = requested_url
    status = 200
    network_error = None

    @staticmethod
    def header(_name: str):
        return "text/html"

    @staticmethod
    def header_values(_name: str):
        return ()


def test_m3_logs_current_render_before_snapshot_is_persisted(tmp_path: Path, monkeypatch) -> None:
    from rasai import m3

    monkeypatch.setattr(m3, "M14Persistence", _M14)
    monkeypatch.setenv(DEVICE_CONTEXT_ENV, "mobile")

    url = "https://example.test/page"
    page = SimpleNamespace(page_id="PGE-1", audit_id="AUD-1", normalized_url=url)
    persistence = _Persistence(page)
    workspace = SimpleNamespace(root=tmp_path, artifacts=tmp_path / "artifacts")
    m2_result = SimpleNamespace(
        discovery=SimpleNamespace(
            pages=(SimpleNamespace(normalized_url=url),),
            page_acquisitions={url: _Acquisition()},
        ),
        page_ids={url: "PGE-1"},
        raw_artifact_refs={url: None},
    )

    result = execute_m3(m2_result, persistence, workspace, renderer=_Renderer())

    assert result.failures == ()
    assert len(persistence.snapshots.added) == 1
    log_path = tmp_path / "logs" / "audit.log"
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    names = [event["event"] for event in events]
    assert names == ["M3_RENDER_STARTED", "M3_RENDER_COMPLETED", "M3_SNAPSHOT_PERSISTED"]
    assert events[0]["url"] == url
    assert events[0]["device"] == "MOBILE"
    assert events[0]["context_index"] == 1
    assert events[0]["context_total"] == 1
    assert events[0]["additional_network_requests"] == 0
    assert events[1]["document_source_state"] == "SKIPPED_NOT_FINISHED"
    assert events[2]["render_succeeded"] is True
