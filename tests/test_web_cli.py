from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

from rasai.web.cli import _is_loopback_host, main


def test_loopback_detection_accepts_localhost_ipv4_and_ipv6() -> None:
    assert _is_loopback_host("localhost")
    assert _is_loopback_host("127.0.0.1")
    assert _is_loopback_host("::1")
    assert not _is_loopback_host("0.0.0.0")
    assert not _is_loopback_host("10.0.0.20")


def test_non_loopback_bind_requires_explicit_acknowledgement(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_run(*_args, **_kwargs):
        nonlocal called
        called = True

    import uvicorn
    monkeypatch.setattr(uvicorn, "run", fake_run)

    with pytest.raises(SystemExit, match="--allow-public-bind"):
        main(["--host", "0.0.0.0", "--port", "8000"])
    assert not called

    assert main([
        "--host", "0.0.0.0", "--port", "8000", "--allow-public-bind", "--auth-mode", "deny"
    ]) == 0
    assert called
