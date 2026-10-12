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
    assert result["usql_extrapolation_level"] is None
    assert result["usql_reported_counts_extrapolated"] is None
    assert result["raw_rum_action_census_verified"] is False
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


@pytest.mark.parametrize("raw", [
    b'{"columnNames":["type","COUNT(*)"],"values":[["Load",7]],"values":[["Xhr",2]]}',
    b'{"columnNames":["type","COUNT(*)"],"values":[["Load",7]],"values":[["Load",7]]}',
    b'{"columnNames":["type","COUNT(*)"],"values":[["Load",7]],"extrapolationLevel":1,"extrapolationLevel":4}',
    b'{"columnNames":["type","COUNT(*)"],"values":[["Load",7]],"metadata":{"source":"a","source":"a"}}',
])
def test_usql_duplicate_response_keys_cannot_publish_ambiguous_aggregates(raw):
    fake = _FakeOpener(raw)
    with pytest.raises(ValueError, match="response JSON invalid"):
        _read(fake)
    assert len(fake.requests) == 1


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


@pytest.mark.parametrize(
    ("extrapolation", "expected"),
    [
        (1, False),
        (4, True),
        (100, True),
    ],
)
def test_usql_extrapolation_disclosed_without_raw_census_claim(
    extrapolation, expected,
):
    table = dict(TABLE, extrapolationLevel=extrapolation)
    value = _read(_FakeOpener(table))
    assert value["action_counts"]["load"] == 7
    assert value["usql_extrapolation_level"] == extrapolation
    assert value["usql_reported_counts_extrapolated"] is expected
    assert value["raw_rum_action_census_verified"] is False
    assert value["rasai_same_browser_sample_verified"] is False


@pytest.mark.parametrize("bad_level", (True, 0, -1, 1.5, "4", {}, 5000))
def test_usql_invalid_extrapolation_levels_fail_closed(bad_level):
    table = dict(TABLE, extrapolationLevel=bad_level)
    with pytest.raises(ValueError, match="extrapolation"):
        _read(_FakeOpener(table))


def test_usql_action_types_are_trimmed_before_grouping_without_extra_requests():
    fake = _FakeOpener({
        "columnNames": ["type", "COUNT(*)"],
        "values": [[" Load ", 3], [" Xhr ", 5], [" Custom ", 2],
                   [" EndVisit ", 4]],
    })
    result = _read(fake)
    assert result["action_counts"] == {
        "load": 3, "xhr": 5, "custom": 2, "other": 4,
    }
    assert result["action_count_total"] == 14
    assert result["provider_requests"] == 1
    assert result["audit_writes"] == 0
    assert len(fake.requests) == 1


@pytest.mark.parametrize("types", [
    ["Load", " load "],
    [" XHR ", "xhr"],
    [" Custom", "custom "],
    ["EndVisit ", " endvisit"],
])
def test_usql_duplicate_action_after_normalization_refuses_ambiguous_total(types):
    fake = _FakeOpener({
        "columnNames": ["type", "COUNT(*)"],
        "values": [[types[0], 3], [types[1], 7]],
    })
    with pytest.raises(ValueError, match="action count row is invalid"):
        _read(fake)
    assert len(fake.requests) == 1
