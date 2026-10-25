"""Observed-only, source-segregated CAT-01 inventory."""
import sqlite3
from rasai.architecture_audit_facts import _network_facts, _public_host


def test_public_host_excludes_private_identifiers_and_url_secrets():
    assert _public_host("https://user:pass@cdn.example.org/a?token=secret") == "cdn.example.org"
    assert _public_host("cdn.example.org") == "cdn.example.org"
    for bad in ("127.0.0.1", "192.168.10.2", "host.local", "localhost", "<svg/onload=1>"):
        assert _public_host(bad) is None


def test_snapshot_resource_declaration_not_misclassified_as_network(tmp_path):
    db=tmp_path/"audit.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE passive_security_resources(audit_id TEXT,snapshot_id TEXT,resource_kind TEXT,domain TEXT)")
        con.executemany("INSERT INTO passive_security_resources VALUES (?,?,?,?)",[
            ("A","S1","STYLESHEET","cdn.example.org"),
            ("A","S1","SCRIPT","site.example.org"),
            ("A","S2","IMG","site.example.org"),
            ("B","S1","SCRIPT","other.example.org"),
        ])
    meta={
        "script_runtime":{"state":"CAPTURED","count":1,"items":[
            {"status":200,"protocol":"h2","url":"https://site.example.org/main.js?token=private"}]},
        "network_resource_observations":{"state":"CAPTURED","count":1,"items":[
            {"resource_type":"Stylesheet","host":"cdn.example.org","status":200}]},
        "navigation_trace":[{"status":302},{"status":200}],
        "cookie_runtime":{"count":9},
        "main_response_network":{
            "state":"OBSERVED_MAIN_DOCUMENT_RESPONSE",
            "http_protocol":"h2","tls_protocol":"TLS 1.3",
            "tls_issuer":"Public CA", "remote_public_peer_ip":"8.8.8.8",
            "tls_valid_from":1790000000,
        },
    }
    result=_network_facts(db,"A","S1",meta)
    assert result["dom_count"] == 2
    assert result["dom_types"] == {"STYLESHEET":1,"SCRIPT":1}
    assert result["script_count"] == 1
    assert result["response_count"] == 1
    assert result["response_types"] == {"Stylesheet":1}
    assert result["cookie_events"] == 9
    assert result["navigation_count"] == 2
    assert result["topology"] == "NETWORK_TOPOLOGY_NOT_DETERMINABLE"
    assert result["main_response_security"]["tls_protocol"] == "TLS 1.3"
    assert result["main_response_security"]["remote_public_peer_ip"] == "8.8.8.8"
    assert "private" not in repr(result)


def test_no_table_and_legacy_audit_keep_unknown_distinct_from_zero(tmp_path):
    db=tmp_path/"audit.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE other (x TEXT)")
    result=_network_facts(db,"A","S",{})
    assert result["dom_count"] is None
    assert result["response_state"] == "NOT_COLLECTED"
    assert result["response_count"] is None
    assert result["main_response_state"] == "NOT_COLLECTED"
