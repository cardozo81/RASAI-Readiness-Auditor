from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from rasai.standards_css_validation import (
    PUBLIC_MIN_INTERVAL_SECONDS,
    collect_css_validation,
    parse_css_validation_soap,
)
from rasai.standards_metrics import _init
from rasai.standards_service_registry import service, service_state


_VALID = b"""<?xml version='1.0' encoding='utf-8'?>
<env:Envelope xmlns:env='http://www.w3.org/2003/05/soap-envelope'>
 <env:Body>
  <m:cssvalidationresponse xmlns:m='http://www.w3.org/2005/07/css-validator'>
   <m:uri>https://example.test/</m:uri>
   <m:checkedby>https://jigsaw.w3.org/css-validator/</m:checkedby>
   <m:csslevel>css3</m:csslevel>
   <m:date>2026-09-11T12:00:00Z</m:date>
   <m:validity>true</m:validity>
   <m:result>
    <m:errors><m:errorcount>0</m:errorcount></m:errors>
    <m:warnings><m:warningcount>2</m:warningcount></m:warnings>
   </m:result>
  </m:cssvalidationresponse>
 </env:Body>
</env:Envelope>"""

_INVALID = _VALID.replace(b"<m:validity>true</m:validity>", b"<m:validity>false</m:validity>").replace(
    b"<m:errorcount>0</m:errorcount>", b"<m:errorcount>3</m:errorcount>"
)


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload


def _workspace(tmp_path):
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE audits (audit_id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE pages (page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT)")
        connection.execute("INSERT INTO audits VALUES ('AUD-CSS')")
        connection.executemany(
            "INSERT INTO pages VALUES (?,?,?)",
            (
                ("P1", "AUD-CSS", "https://example.test/a"),
                ("P2", "AUD-CSS", "https://example.test/b"),
            ),
        )
        _init(connection)
        connection.commit()
    finally:
        connection.close()
    return SimpleNamespace(database=database)


def test_css_validator_is_free_default_on_and_independently_toggleable() -> None:
    ready = service_state(service("w3c-css-validator"), {})
    disabled = service_state(service("w3c-css-validator"), {"RASAI_W3C_CSS_VALIDATOR": "false"})
    assert ready["state"] == "READY"
    assert ready["effective_enabled"] is True
    assert disabled["state"] == "DISABLED"


def test_parse_css_validation_soap_preserves_source_outcome() -> None:
    valid = parse_css_validation_soap(_VALID)
    invalid = parse_css_validation_soap(_INVALID)
    assert valid["valid"] is True
    assert valid["errors"] == 0
    assert valid["warnings"] == 2
    assert valid["css_level"] == "css3"
    assert invalid["valid"] is False
    assert invalid["errors"] == 3


def test_css_collection_throttles_public_service_and_persists_pass_fail(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    payloads = iter((_VALID, _INVALID))
    requests = []
    sleeps = []

    def opener(request, *, timeout):
        requests.append((request.full_url, timeout))
        return _Response(next(payloads))

    result = collect_css_validation(
        audit_id="AUD-CSS",
        workspace=workspace,
        env={
            "RASAI_W3C_CSS_VALIDATOR": "true",
            "RASAI_STANDARDS_MAX_URLS": "2",
            "RASAI_STANDARDS_TIMEOUT_SECONDS": "5",
        },
        opener=opener,
        sleeper=sleeps.append,
    )

    assert result["collection_state"] == "SUCCESS"
    assert result["attempted"] == 2
    assert result["succeeded"] == 2
    assert sleeps == [PUBLIC_MIN_INTERVAL_SECONDS]
    assert all("output=soap12" in url and "profile=css3" in url for url, _ in requests)

    connection = sqlite3.connect(workspace.database)
    try:
        rows = connection.execute(
            "SELECT target,state,value FROM standards_metric_observations WHERE metric_id='w3c_css_conformance' ORDER BY target"
        ).fetchall()
        run = connection.execute(
            "SELECT state,targets_attempted,targets_succeeded FROM standards_service_runs WHERE service_id='w3c-css-validator'"
        ).fetchone()
    finally:
        connection.close()
    assert rows == [
        ("https://example.test/a", "PASS", 0.0),
        ("https://example.test/b", "FAIL", 3.0),
    ]
    assert run == ("SUCCESS", 2, 2)
