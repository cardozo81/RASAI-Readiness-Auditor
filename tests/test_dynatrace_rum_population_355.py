"""#355: privacy bounded USQL action-population GET with no real network."""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from rasai.dynatrace_rum_population_355 import (
    read_live_dynatrace_action_population as read_counts, main,
)


BASE = "https://tenant-abc123.live.dynatrace.com"
APP = "APPLICATION-1234567890ABCDEF"
URL = "https://www.example.com/seguro-de-vida"
START = 1_780_000_000_000
END = START + 15 * 60_000
TABLE = {"columnNames": ["type", "COUNT(*)"],
         "values": [["Load", 7], ["Xhr", 25], ["Custom", 2], ["EndVisit", 3]],
         "userId": "confidential-source-must-not-appear"}


class _Response:
    def __init__(self, raw: bytes, code=200, media="application/json") -> None:
        self.body = raw
        self.code = code
        self.headers = {"Content-Type": media}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.code

    def read(self, size):
        return self.body[:size]


class _FakeOpener:
    def __init__(self, payload=TABLE, *, code=200, media="application/json"):
        self.response = _Response(
            json.dumps(payload).encode() if not isinstance(payload, bytes) else payload,
            code=code, media=media,
        )
        self.requests = []

    def open(self, req, timeout):
        self.requests.append((req, timeout))
        return self.response


def _read(opener=None, **changes):
    options = dict(
        base_url=BASE, application_id=APP, target_url=URL,
        dynatrace_device="MOBILE", start_timestamp_ms=START,
        end_timestamp_ms=END, api_token="sensitive-token",
        opener=opener or _FakeOpener(),
    )
    options.update(changes)
    return read_counts(**options)


def test_single_scoped_aggregate_query_and_no_private_session_export():
    fake = _FakeOpener()
    result = _read(fake)
    assert result["source"] == "LIVE_RUM_CLASSIC_USQL_AGGREGATE_RESPONSE"
    assert result["action_counts"] == {
        "load": 7, "xhr": 25, "custom": 2, "other": 3,
    }
    assert result["action_count_total"] == 37
    assert result["rasai_same_browser_sample_verified"] is False
    assert result["population_query_scoped_to_exact_url_device_window"] is True
    assert result["audit_writes"] == 0
    assert result["m23_m25_changed"] is False
    assert result["provider_requests"] == 1
    assert "confidential-source" not in json.dumps(result)
    assert "sensitive-token" not in json.dumps(result)
    assert len(fake.requests) == 1
    request, timeout = fake.requests[0]
    assert timeout == 10
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == "Api-Token sensitive-token"
    endpoint = urlsplit(request.full_url)
    assert endpoint.scheme == "https"
    assert endpoint.hostname == "tenant-abc123.live.dynatrace.com"
    assert endpoint.path == "/api/v1/userSessionQueryLanguage/table"
    query = parse_qs(endpoint.query)
    assert query["startTimestamp"] == [str(START)]
    assert query["endTimestamp"] == [str(END)]
    assert "FROM useraction" in query["query"][0]
    assert f'useraction.internalApplicationId = "{APP}"' in query["query"][0]
    assert f'useraction.targetUrl = "{URL}"' in query["query"][0]
    assert 'usersession.device = "MOBILE"' in query["query"][0]
    assert "sensitive-token" not in request.full_url


@pytest.mark.parametrize(
    "change",
    [
        {"base_url": "http://tenant-abc123.live.dynatrace.com"},
        {"base_url": "https://evil.example"},
        {"application_id": "APPLICATION-123\" OR 1=1"},
        {"target_url": "https://www.example.com/x\" OR 1=1"},
        {"target_url": "https://www.example.com/x#fragment"},
        {"dynatrace_device": 'MOBILE" OR 1=1'},
        {"start_timestamp_ms": END + 100},
        {"end_timestamp_ms": START + 25 * 60 * 60 * 1000},
        {"start_timestamp_ms": True},
        {"api_token": "secret\nleak"},
        {"timeout_seconds": 31},
    ],
    ids=[
        "insecure", "external-host", "application-injection",
        "url-injection", "url-fragment", "device-injection",
        "inverted-window", "too-broad-window", "boolean-clock",
        "header-injection", "unbounded-timeout",
    ],
)
def test_invalid_scope_or_header_is_rejected_before_http(change):
    fake = _FakeOpener()
    with pytest.raises(ValueError):
        _read(fake, **change)
    assert not fake.requests


@pytest.mark.parametrize(
    ("value", "expected_error"),
    [
        ({"columnNames": ["type"], "values": [["Load", 1]]}, "schema"),
        ({"columnNames": ["type", "COUNT(*)"], "values": [["Load", -1]]}, "row"),
        ({"columnNames": ["type", "COUNT(*)"], "values": [["Load", True]]}, "row"),
        ({"columnNames": ["type", "COUNT(*)"],
          "values": [["Load", 1], ["load", 2]]}, "row"),
        ({"columnNames": ["type", "COUNT(*)"], "values": [["Load", 2.5]]}, "row"),
        ({"columnNames": ["type", "COUNT(*)"], "values": [["Load", "2"]]}, "row"),
        ({"columnNames": ["name", "COUNT(*)"], "values": []}, "schema"),
        ({"columnNames": ["type", "COUNT(*)"], "values": "broken"}, "schema"),
        ({"columnNames": ["type", "COUNT(*)"], "values": [["Load", 1]] * 21}, "schema"),
    ],
    ids=[
        "missing-column", "negative", "boolean", "duplicate-action",
        "float", "string", "wrong-column", "not-table", "too-many",
    ],
)
def test_ambiguous_aggregate_response_fails_closed(value, expected_error):
    with pytest.raises(ValueError, match=expected_error):
        _read(_FakeOpener(value))


def test_invalid_http_json_and_oversize_are_not_disclosed():
    cases = [
        _FakeOpener(code=403),
        _FakeOpener(media="text/html"),
        _FakeOpener(b"not-json"),
        _FakeOpener(b"x" * (256 * 1024 + 1)),
    ]
    for fake in cases:
        with pytest.raises(ValueError) as exc:
            _read(fake)
        assert "sensitive-token" not in str(exc.value)


def test_empty_aggregate_is_not_assumed_to_prove_xhr_capture_disabled():
    result = _read(_FakeOpener({"columnNames": ["type", "COUNT(*)"], "values": []}))
    assert result["action_count_total"] == 0
    assert result["action_counts"]["xhr"] == 0
    assert "não prova que captura XHR/Fetch esteja desabilitada" in result["limitations"]


def test_live_cli_cannot_query_without_explicit_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--live-base-url", BASE, "--application-id", APP,
              "--target-url", URL, "--dynatrace-device", "MOBILE",
              "--start-timestamp-ms", str(START),
              "--end-timestamp-ms", str(END)])
    assert exc.value.code == 2
    assert "explicit --allow-live-usql-read" in capsys.readouterr().err
