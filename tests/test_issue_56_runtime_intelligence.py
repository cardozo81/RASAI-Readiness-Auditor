from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rasai.device_context_capture import _cookie_runtime_metadata, _script_runtime_metadata
from rasai.catalog_report_analysis import _runtime_security_inventory_html, _technical_target_label
from rasai.passive_security import (
    _analyze_headers,
    _cookie_attributes,
    _deduplicate_runtime_scripts,
    _persist_runtime_intelligence,
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


class _FakeCookieContext:
    def cookies(self):
        return [{
            "name": "session_id",
            "value": "SHOULD_NOT_PERSIST_COOKIE_VALUE",
            "domain": "example.test",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "sameSite": "Lax",
        }]


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


def test_cat10_unconfirmed_cookie_write_is_not_presented_as_effective_cookie(tmp_path):
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
        connection.execute(
            """INSERT INTO passive_security_cookie_attribution(
                 cookie_attribution_id,audit_id,page_id,snapshot_id,cookie_ref,cookie_name_display,
                 name_hash,creation_mechanism,effective_domain,effective_path,host_only,
                 setter_script_url,setter_script_ref,platform_ref,party,purpose,purpose_confidence,
                 attribution_confidence,details_json,evidence_ids_json
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "PCA-ATTEMPT", AUDIT_ID, PAGE_ID, SNAPSHOT_ID, "CKA-TEST", "domain_probe",
                "probehash", "DOCUMENT_COOKIE", None, None, 0,
                "https://cdn.example.test/probe.js", None, None, "UNKNOWN", "UNKNOWN", "LOW",
                "MEDIUM", json.dumps({
                    "observation_state": "WRITE_ATTEMPT_NOT_CONFIRMED",
                    "declared_domain": "com.br",
                    "declared_path": "/",
                    "attribution_basis": "BROWSER_RUNTIME_INSTRUMENTATION",
                }), json.dumps([SNAPSHOT_ID]),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    html = _runtime_security_inventory_html(database, AUDIT_ID)

    assert "domain_probe" in html
    assert "CKA-TEST" in html
    assert "Tentativa de escrita não confirmada" in html
    assert "Domínio efetivo / confirmado" in html
    assert "Não confirmado" in html
    assert "Domínio declarado na tentativa" in html
    assert "com.br" in html
    assert "Site auditado · com.br" not in html


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
    result = _cookie_runtime_metadata(_FakeCookiePage(), _FakeCookieContext())
    assert result["additional_network_requests"] == 0
    assert result["state"] == "CAPTURED"
    assert result["browser_store_state"] == "CAPTURED"
    item = result["items"][0]
    assert item["cookie_name"] == "session_id"
    assert item["setter_script_url"] == "https://cdn.example.test/app.js"
    assert item["consent_state_at_creation"] == "NOT_OBSERVED"
    assert item["store_state"] == "CONFIRMED_IN_BROWSER_STORE"
    assert item["confirmed_domain"] == "example.test"
    assert item["confirmed_path"] == "/"
    serialized = json.dumps(result)
    assert "auth=secret" not in serialized
    assert "SHOULD_NOT_PERSIST" not in serialized
    assert "SHOULD_NOT_PERSIST_COOKIE_VALUE" not in serialized


def test_cookie_runtime_keeps_invalid_domain_write_as_unconfirmed_attempt():
    class InvalidDomainFrame:
        url = "https://example.com.br/"

        def evaluate(self, _script):
            return [{
                "mechanism": "DOCUMENT_COOKIE",
                "name": "probe_cookie",
                "attributes": {"domain": "com.br", "path": "/"},
                "at_ms": 10.0,
                "stack": "Error\n at probe (https://cdn.example.test/probe.js:1:1)",
            }]

    class Page:
        frames = [InvalidDomainFrame()]

    class Context:
        def cookies(self):
            return [{
                "name": "other_cookie",
                "value": "SECRET",
                "domain": "example.com.br",
                "path": "/",
            }]

    result = _cookie_runtime_metadata(Page(), Context())
    item = result["items"][0]

    assert item["store_state"] == "WRITE_ATTEMPT_NOT_CONFIRMED"
    assert item["domain_attribute"] == "com.br"
    assert item["confirmed_domain"] is None
    assert "SECRET" not in json.dumps(result)


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
                "store_state": "CONFIRMED_IN_BROWSER_STORE",
                "confirmed_domain": "example.test",
                "confirmed_path": "/",
                "confirmed_host_only": True,
                "confirmed_secure": False,
                "confirmed_httponly": False,
                "confirmed_samesite": "Lax",
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
    assert runtime_cookie["effective_domain"] == "example.test"
    assert runtime_cookie["party"] == "FIRST_PARTY"
    assert runtime_cookie["details"]["observation_state"] == "CONFIRMED_IN_BROWSER_STORE"
    assert any(item["platform_id"] == "GOOGLE_TAG_MANAGER" for item in platforms)
    assert "SCRIPT_SETS_COOKIE" in {item["relation_type"] for item in relationships}
    serialized = json.dumps([scripts, cookies, platforms, relationships])
    assert "SERVER_SECRET" not in serialized




def test_duplicate_runtime_script_is_collapsed_before_primary_key_persistence(tmp_path):
    script_url = "https://cdn.example.test/repeated.js"
    runtime_item = {
        "snapshot_id": SNAPSHOT_ID,
        "url": script_url,
        "url_hash": "same-runtime-hash",
        "party": "THIRD_PARTY",
        "body_analysis_state": "ANALYZED",
        "content_sha256": "abc",
        "risk_signals": [{"signal_id": "DYNAMIC_EVAL"}],
        "platforms": [],
    }
    page_context = {
        PAGE_ID: {
            "page_url": "https://example.test/",
            "headers": {"set-cookie": []},
            "header_evidence": [],
            "script_runtime": [dict(runtime_item), dict(runtime_item)],
            "cookie_runtime": [],
            "verifications": [],
        }
    }

    scripts, cookies, platforms, relationships = _runtime_intelligence_rows(
        AUDIT_ID,
        [],
        page_context,
    )

    assert len(scripts) == 1
    assert scripts[0]["resource_url"] == script_url
    assert {item["signal_id"] for item in scripts[0]["risk_signals"]} == {"DYNAMIC_EVAL"}

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
        _persist_runtime_intelligence(
            connection,
            AUDIT_ID,
            scripts,
            cookies,
            platforms,
            relationships,
        )
        connection.commit()
        count = connection.execute(
            "SELECT COUNT(*) FROM passive_security_script_observations WHERE audit_id=?",
            (AUDIT_ID,),
        ).fetchone()[0]
        assert count == 1
    finally:
        connection.close()


def test_duplicate_runtime_script_merges_complementary_evidence_deterministically():
    shared = {
        "script_ref": "PSS-SAME",
        "audit_id": AUDIT_ID,
        "page_id": PAGE_ID,
        "snapshot_id": SNAPSHOT_ID,
        "resource_url": "https://cdn.example.test/repeated.js",
        "party": "THIRD_PARTY",
        "domain": "cdn.example.test",
        "analysis_state": "ANALYZED",
    }
    first = {
        **shared,
        "timing": {"duration_ms": 20},
        "integrity": {"content_sha256": "abc"},
        "risk_signals": [{"signal_id": "DYNAMIC_EVAL"}],
        "platforms": [{"platform_id": "TAG_A"}],
        "evidence_ids": ["EV-2"],
    }
    second = {
        **shared,
        "timing": {"transfer_size_bytes": 1200},
        "integrity": {"content_bytes": 900},
        "risk_signals": [{"signal_id": "DOCUMENT_WRITE"}],
        "platforms": [{"platform_id": "TAG_B"}],
        "evidence_ids": ["EV-1", "EV-2"],
    }

    merged = _deduplicate_runtime_scripts([second, first])

    assert len(merged) == 1
    item = merged[0]
    assert item["timing"] == {"duration_ms": 20, "transfer_size_bytes": 1200}
    assert item["integrity"] == {"content_bytes": 900, "content_sha256": "abc"}
    assert {value["signal_id"] for value in item["risk_signals"]} == {
        "DOCUMENT_WRITE",
        "DYNAMIC_EVAL",
    }
    assert {value["platform_id"] for value in item["platforms"]} == {"TAG_A", "TAG_B"}
    assert item["evidence_ids"] == ["EV-1", "EV-2"]


def test_runtime_normalization_does_not_promote_unconfirmed_write_to_effective_cookie():
    page_context = {
        PAGE_ID: {
            "page_url": "https://example.com.br/",
            "headers": {"set-cookie": []},
            "header_evidence": [],
            "script_runtime": [{
                "snapshot_id": SNAPSHOT_ID,
                "url": "https://cdn.example.test/probe.js",
                "url_hash": "probe-script",
                "party": "THIRD_PARTY",
                "body_analysis_state": "ANALYZED",
                "content_sha256": "abc",
                "risk_signals": [],
                "platforms": [],
            }],
            "cookie_runtime": [{
                "snapshot_id": SNAPSHOT_ID,
                "mechanism": "DOCUMENT_COOKIE",
                "cookie_name": "domain_probe",
                "name_hash": "hash-probe",
                "frame_url": "https://example.com.br/",
                "domain_attribute": "com.br",
                "path_attribute": "/",
                "setter_script_url": "https://cdn.example.test/probe.js",
                "attribution_confidence": "MEDIUM",
                "store_state": "WRITE_ATTEMPT_NOT_CONFIRMED",
                "confirmed_domain": None,
                "confirmed_path": None,
            }],
            "verifications": [],
        }
    }

    _scripts, cookies, _platforms, relationships = _runtime_intelligence_rows(
        AUDIT_ID,
        [],
        page_context,
    )

    attempt = cookies[0]
    assert attempt["effective_domain"] is None
    assert attempt["effective_path"] is None
    assert attempt["party"] == "UNKNOWN"
    assert attempt["details"]["declared_domain"] == "com.br"
    assert attempt["details"]["observation_state"] == "WRITE_ATTEMPT_NOT_CONFIRMED"
    relation_types = {item["relation_type"] for item in relationships}
    assert "SCRIPT_SETS_COOKIE" not in relation_types
    assert "SCRIPT_ATTEMPTS_COOKIE_WRITE" in relation_types


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
