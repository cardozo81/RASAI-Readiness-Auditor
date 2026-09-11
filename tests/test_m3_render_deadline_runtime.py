from __future__ import annotations

import pytest

from rasai.domain import DeviceContext
from rasai.m3_render_deadline_runtime import (
    IsolatedBrowserIdentityRenderer,
    configured_wallclock_seconds,
)
from rasai.rendering import RenderErrorKind


class _Process:
    def __init__(self) -> None:
        self.alive = True
        self.terminated = False

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False

    def join(self, timeout: float | None = None) -> None:
        return None

    def kill(self) -> None:
        self.terminated = True
        self.alive = False


class _Connection:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.closed = False

    def send(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)

    def poll(self, timeout: float) -> bool:
        return False

    def close(self) -> None:
        self.closed = True


def test_wallclock_configuration_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RASAI_M3_RENDER_WALLCLOCK_SECONDS", raising=False)
    assert configured_wallclock_seconds() == 60.0
    monkeypatch.setenv("RASAI_M3_RENDER_WALLCLOCK_SECONDS", "45")
    assert configured_wallclock_seconds() == 45.0
    monkeypatch.setenv("RASAI_M3_RENDER_WALLCLOCK_SECONDS", "1")
    with pytest.raises(ValueError):
        configured_wallclock_seconds()


def test_timeout_kills_browser_worker_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RASAI_M3_RENDER_WALLCLOCK_SECONDS", "5")
    renderer = IsolatedBrowserIdentityRenderer()
    process = _Process()
    connection = _Connection()
    renderer._process = process  # type: ignore[assignment]
    renderer._connection = connection  # type: ignore[assignment]

    result = renderer.render("https://example.test/a", DeviceContext.MOBILE)

    assert result.error_kind is RenderErrorKind.RENDERER_ERROR
    assert result.browser_metadata["render_failure_reason"] == "RENDER_WALLCLOCK_TIMEOUT"
    assert result.browser_metadata["automatic_retry"] is False
    assert len(connection.sent) == 1
    assert connection.sent[0]["command"] == "render"
    assert process.terminated is True
    assert connection.closed is True
