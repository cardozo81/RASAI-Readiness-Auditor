from __future__ import annotations

import json

import pytest

from rasai.remote_client import RemoteApiError, RemoteClient, RemoteSettings


def test_remote_settings_require_https_except_loopback_and_never_accept_remote_trusted_header() -> None:
    with pytest.raises(ValueError, match="requires HTTPS"):
        RemoteSettings.from_environment({"RASAI_REMOTE_BASE_URL": "http://rasai.example.test"})
    with pytest.raises(ValueError, match="loopback-only"):
        RemoteSettings.from_environment(
            {
                "RASAI_REMOTE_BASE_URL": "https://rasai.example.test",
                "RASAI_REMOTE_USER_ID": "USR-EXAMPLE",
            }
        )
    local = RemoteSettings.from_environment(
        {
            "RASAI_REMOTE_BASE_URL": "http://127.0.0.1:8000/",
            "RASAI_REMOTE_USER_ID": "USR-LOCAL",
        }
    )
    assert local.base_url == "http://127.0.0.1:8000"
    assert local.loopback_user_id == "USR-LOCAL"


def test_remote_client_reads_bearer_from_environment_reference_without_persisting_it(monkeypatch) -> None:
    captured = {}

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps({"user_id": "USR-REMOTE"}).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("rasai.remote_client.urlopen", fake_urlopen)
    secret = "TEST_ONLY_REMOTE_TOKEN_NOT_REAL"
    settings = RemoteSettings.from_environment(
        {
            "RASAI_REMOTE_BASE_URL": "https://rasai.example.test",
            "RASAI_REMOTE_TOKEN_ENV": "RASAI_TEST_REMOTE_TOKEN",
        }
    )
    client = RemoteClient(settings, environment={"RASAI_TEST_REMOTE_TOKEN": secret})
    assert client.get("/api/v1/me") == {"user_id": "USR-REMOTE"}
    assert captured["authorization"] == "Bearer " + secret
    assert secret not in repr(settings)
    assert settings.token_env == "RASAI_TEST_REMOTE_TOKEN"


def test_remote_client_requires_configured_referenced_token() -> None:
    client = RemoteClient(
        RemoteSettings(base_url="https://rasai.example.test", token_env="RASAI_MISSING_TOKEN"),
        environment={},
    )
    with pytest.raises(RemoteApiError, match="not configured"):
        client.get("/api/v1/me")
