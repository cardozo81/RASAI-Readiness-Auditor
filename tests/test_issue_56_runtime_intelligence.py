from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rasai.device_context_capture import _cookie_runtime_metadata, _script_runtime_metadata
from rasai.catalog_report_analysis import _runtime_security_inventory_html, _technical_target_label
from rasai.passive_security import (
    _analyze_headers,
    _cookie_attributes,
    _runtime_intelligence_rows,
    ensure_schema,
    improvement_findings,
)
from rasai.web_technology_signatures import (
    PUBLIC_IDENTIFIER,
    PUBLIC_OPERATIONAL_KEY,
    analyze_script_source,
    detect_platforms,
)


AUDIT_ID = "AUD-ISSUE56"
PAGE_ID = "PAGE-1"
SNAPSHOT_ID = "SNAP-1"


class _FakeSession:
    def send(self, method, payload):
        assert method == "Network.getResponseBody"
        assert payload["requestId"] == "REQ-1"
        return {
            "body": "eval('x'); document.cookie='secret_cookie=SHOULD_NOT_PERSIST';"
                    "analytics.load('SEGMENT_WRITE_KEY_EXAMPLE')",
            "base64Encoded": False,
        }


class _FakePage:
    url = "https://example.test/"

    def evaluate(self, _script):
        return [{
            "name": "https://cdn.segment.com/analytics.js?token=do-not-persist",
            "start_time_ms": 12.0,
            "duration_ms": 40.0,
            "transfer_size_bytes": 1200,
            "encoded_body_size_bytes": 900,
            "decoded_body_size_bytes": 2400,
            "next_hop_protocol": "h2",
        }]


class _FakeFrame:
    url = "https://example.test/"

    def evaluate(self, _script):
        return [{
            "mechanism": "DOCUMENT_COOKIE",
            "name": "session_id",
            "attributes": {"path": "/", "secure": True, "samesite": "Lax"},
            "at_ms": 25.0,
            "stack": "Error\n at setCookie (https://cdn.example.test/app.js?auth=secret:1:2)",
        }]


class _FakeCookiePage:
    frames = [_FakeFrame()]


def test_platform_identifiers_are_allowlisted_and_operational_keys_are_masked():
    source = (
        "https://www.googletagmanager.com/gtm.js?id=GTM-ABC123 "
        "analytics.load('SEGMENT_WRITE_KEY_EXAMPLE')"
    )
    platforms = detect_platforms("https://www.googletagmanager.com/gtm.js?id=GTM-ABC123", source)
    by_id = {item["platform_id"]: item for item in platforms}

    gtm = by_id["GOOGLE_TAG_MANAGER"]
    gtm_id = next(item for item in gtm["identifiers"] if item["identifier_type"] == "GTM_CONTAINER_ID")
    assert gtm_id["identifier_class"] == PUBLIC_IDENTIFIER
    assert gtm_id["identifier_display"] == "GTM-ABC123"

    segment = by_id["SEGMENT"]
    write_key = next(item for item in segment["identifiers"] if item["identifier_type"] == "SEGMENT_WRITE_KEY")
    assert write_key["identifier_class"] == PUBLIC_OPERATIONAL_KEY
    assert write_key["identifier_display"] != "SEGMENT_WRITE_KEY_EXAMPLE"
    assert "SEGMENT_WRITE_KEY_EXAMPLE" not in json.dumps(platforms)


def test_static_script_analysis_reports_signals_not_malware_verdicts():
    signals = analyze_script_source("eval('x'); new Function('return 1'); navigator.geolocation")
    ids = {item["signal_id"] for item in signals}
    assert {"DYNAMIC_EVAL", "DYNAMIC_FUNCTION", "GEOLOCATION"} <= ids
    assert "malware" not in json.dumps(signals).casefold()


def test_cookie_identity_is_stable_and_never_contains_value():
    first = _cookie_attributes(
        "SessionId=VERY_SECRET_VALUE; Secure; HttpOnly; SameSite=Lax; Path=/app",
        "https://example.test/app/login",
    )
    second = _cookie_attributes(
        "SessionId=DIFFERENT_VALUE; Secure; HttpOnly; SameSite=Lax; Path=/app",
        "https://example.test/app/login",
    )
    other_path = _cookie_attributes(
        "SessionId=VERY_SECRET_VALUE; Secure; HttpOnly; SameSite=Lax; Path=/other",
        "https://example.test/app/login",
    )

    assert first["cookie_ref"] == second["cookie_ref"]
    assert first["cookie_ref"] != other_path["cookie_ref"]
    assert first["name_display"] == "SessionId"
    serialized = json.dumps(first)
    assert "VERY_SECRET_VALUE" not in serialized
    assert "DIFFERENT_VALUE" not in serialized


def test_http_cookie_finding_exposes_safe_name_id_and_technical_owner():
    findings = _analyze_headers(
        AUDIT_ID,
        {
            "page_id": PAGE_ID,
            "page_url": "https://example.test/app/login",
            "headers": {
                "set-cookie": [
                    "SessionId=VERY_SECRET_VALUE; Secure; SameSite=Lax; Path=/app",
                ],
            },
            "header_evidence": ["EV-HEADERS"],
            "http": {},
        },
    )

    finding = next(item for item in findings if item["title"] == "Cookie sem HttpOnly observado")
    target = finding["details"]["target"]
    assert target["label"] == "SessionId"
    assert str(target["ref"]).startswith("CK-")
    assert target["party"] == "FIRST_PARTY"
    assert target["owner_class"] == "TARGET_SITE"
    assert target["owner_label"] == "Site auditado · example.test"
    serialized = json.dumps(findings)
    assert "VERY_SECRET_VALUE" not in serialized


def test_cat10_cookie_inventory_exposes_name_id_and_technical_owner(tmp_path):
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
            CREATE TABLE pages(page_id TEXT PRIMARY KEY, audit_id TEXT);
            INSERT INTO audits VALUES ('AUD-ISSUE56');
            INSERT INTO pages VALUES ('PAGE-1','AUD-ISSUE56');
            """
        )
        ensure_schema(connection)
        attrs = _cookie_attributes(
            "SessionId=VERY_SECRET_VALUE; Secure; SameSite=Lax; Path=/app",
            "https://example.test/app/login",
        )
        connection.execute(
            """INSERT INTO passive_security_cookie_attribution(
                 cookie_attribution_id,audit_id,page_id,snapshot_id,cookie_ref,cookie_name_display,
                 name_hash,creation_mechanism,effective_domain,effective_path,host_only,
                 setter_script_url,setter_script_ref,platform_ref,party,purpose,purpose_confidence,
                 attribution_confidence,details_json,evidence_ids_json
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "PCA-1", AUDIT_ID, PAGE_ID, None, attrs["cookie_ref"], attrs["name_display"],
                attrs["name_hash"], "HTTP_SET_COOKIE", attrs["effective_domain"], attrs["effective_path"], 1,
                None, None, None, "FIRST_PARTY", attrs["purpose"], attrs["purpose_confidence"],
                "HIGH", json.dumps({"set_cookie_index": 1}), json.dumps(["EV-HEADERS"]),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    html = _runtime_security_inventory_html(database, AUDIT_ID)
    assert "SessionId" in html
    assert attrs["cookie_ref"] in html
    assert "ID RASAi" in html
    assert "Proprietário / responsável técnico" in html
    assert "Site auditado · example.test" in html
    assert "VERY_SECRET_VALUE" not in html


def test_cookie_target_label_is_preserved_for_cat08_cat09_projection():
    finding = {
        "details_json": json.dumps({
            "target": {
                "kind": "COOKIE",
                "ref": "CK-ABC123",
                "label": "SessionId",
                "owner_label": "Site auditado · example.test",
                "scope": "example.test /app",
                "occurrence": "Set-Cookie #1",
            }
        })
    }
    label = _technical_target_label(finding)
    assert "SessionId" in label
    assert "ID CK-ABC123" in label
    assert "Responsável: Site auditado · example.test" in label
    assert "example.test /app" in label
    assert "Set-Cookie #1" in label


def test_script_runtime_uses_buffered_body_without_persisting_source():
    capture = {
        "available": True,
        "script_responses": {
            "REQ-1": {
                "raw_url": "https://cdn.segment.com/analytics.js?token=do-not-persist",
                "url": "https://cdn.segment.com/analytics.js",
                "url_hash": "unused-by-test",
                "status": 200,
                "mime_type": "application/javascript",
                "protocol": "h2",
                "from_disk_cache": False,
                "from_service_worker": False,
                "initiator_type": "parser",
                "initiator_url": "https://example.test/",
            }
        },
        "finished": {"REQ-1": 1200.0},
    }
    # Match the same URL hash ResourceTiming uses.
    import hashlib

    raw = capture["script_responses"]["REQ-1"]["raw_url"]
    capture["script_responses"]["REQ-1"]["url_hash"] = hashlib.sha256(raw.encode()).hexdigest()[:16]
    result = _script_runtime_metadata(_FakeSession(), capture, _FakePage())

    assert result["additional_network_requests"] == 0
    assert result["cpu_attribution_state"] == "NOT_COLLECTED_TO_AVOID_PROFILER_OVERHEAD"
    assert result["items"][0]["body_analysis_state"] == "ANALYZED"
    assert result["items"][0]["content_sha256"]
    assert "DYNAMIC_EVAL" in {item["signal_id"] for item in result["items"][0]["risk_signals"]}
    serialized = json.dumps(result)
    assert "SHOULD_NOT_PERSIST" not in serialized
    assert "SEGMENT_WRITE_KEY_EXAMPLE" not in serialized
    assert "do-not-persist" not in serialized


def test_cookie_runtime_persists_only_name_attributes_and_sanitized_setter():
    result = _cookie_runtime_metadata(_FakeCookiePage())
    assert result["additional_network_requests"] == 0
    assert result["state"] == "CAPTURED"
    item = result["items"][0]
    assert item["cookie_name"] == "session_id"
    assert item["setter_script_url"] == "https://cdn.example.test/app.js"
    assert item["consent_state_at_creation"] == "NOT_OBSERVED"
    serialized = json.dumps(result)
    assert "auth=secret" not in serialized
    assert "SHOULD_NOT_PERSIST" not in serialized


def test_runtime_normalization_links_script_platform_and_cookie_without_value():
    script_url = "https://www.googletagmanager.com/gtm.js?id=GTM-ABC123"
    page_context = {
        PAGE_ID: {
            "page_url": "https://example.test/",
            "headers": {
                "set-cookie": ["server_session=SERVER_SECRET; Secure; HttpOnly; Path=/"],
            },
            "header_evidence": ["EV-HEADERS"],
            "script_runtime": [{
                "snapshot_id": SNAPSHOT_ID,
                "url": script_url,
                "url_hash": "hash",
                "party": "THIRD_PARTY",
                "body_analysis_state": "ANALYZED",
                "content_sha256": "abc",
                "risk_signals": [],
                "platforms": detect_platforms(script_url, "GTM-ABC123"),
            }],
            "cookie_runtime": [{
                "snapshot_id": SNAPSHOT_ID,
                "mechanism": "DOCUMENT_COOKIE",
                "cookie_name": "_ga",
                "name_hash": "hash-ga",
                "frame_url": "https://example.test/",
                "path_attribute": "/",
                "setter_script_url": script_url,
                "attribution_confidence": "MEDIUM",
            }],
            "verifications": [],
        }
    }
    scripts, cookies, platforms, relationships = _runtime_intelligence_rows(
        AUDIT_ID,
        [],
        page_context,
    )

    assert len(scripts) == 1
    assert {item["creation_mechanism"] for item in cookies} == {"HTTP_SET_COOKIE", "DOCUMENT_COOKIE"}
    runtime_cookie = next(item for item in cookies if item["creation_mechanism"] == "DOCUMENT_COOKIE")
    assert runtime_cookie["purpose"] == "ANALYTICS"
    assert runtime_cookie["setter_script_ref"] == scripts[0]["script_ref"]
    assert any(item["platform_id"] == "GOOGLE_TAG_MANAGER" for item in platforms)
    assert "SCRIPT_SETS_COOKIE" in {item["relation_type"] for item in relationships}
    serialized = json.dumps([scripts, cookies, platforms, relationships])
    assert "SERVER_SECRET" not in serialized


def test_improvement_projection_preserves_deterministic_target_details():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE audits(audit_id TEXT PRIMARY KEY);
        CREATE TABLE pages(page_id TEXT PRIMARY KEY, audit_id TEXT);
        INSERT INTO audits VALUES ('AUD-ISSUE56');
        INSERT INTO pages VALUES ('PAGE-1','AUD-ISSUE56');
        """
    )
    ensure_schema(connection)
    details = {
        "target": {
            "kind": "COOKIE",
            "ref": "CK-123",
            "label": "_ga",
            "scope": "example.test /",
        },
        "cookie": {"purpose": "ANALYTICS"},
    }
    connection.execute(
        """INSERT INTO passive_security_findings(
             finding_id,audit_id,page_id,url_scope,category,finding_type,title,description,
             severity,confidence,source,evidence_ids_json,party_context,origin_kind,impact,
             containment,remediation,validation,cwe,cve_json,details_json,created_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "SEC-1", AUDIT_ID, PAGE_ID, "https://example.test/", "Cookies", "OBSERVATION",
            "Cookie sem SameSite", "SameSite não observado", "LOW", "HIGH", "TEST",
            '["EV-1"]', "FIRST_PARTY", "DETERMINISTIC", "impact", "contain", "fix", "validate",
            None, "[]", json.dumps(details), "2026-09-28T00:00:00Z",
        ),
    )
    connection.commit()

    projected = improvement_findings(connection, AUDIT_ID, PAGE_ID)
    assert projected is not None
    findings, summary = projected
    assert findings[0]["details"]["target"]["ref"] == "CK-123"
    assert findings[0]["details"]["cookie"]["purpose"] == "ANALYTICS"
    assert summary["shared_security_core"] is True
