"""#330: persisted SERP HTML provenance only, never snippet or network."""
from __future__ import annotations

from hashlib import sha256
import json
import sqlite3

from rasai.geo_competitor_content_provenance_330 import (
    inspect_geo_competitor_content, main,
)


def _db(tmp_path):
    path = tmp_path / "audit.db"
    with sqlite3.connect(path) as con:
        con.executescript("""
            CREATE TABLE serp_observations(
                observation_id TEXT, audit_id TEXT, query TEXT,
                collected_at TEXT, observation_status TEXT, data_mode TEXT,
                country TEXT, language TEXT, device TEXT, engine TEXT
            );
            CREATE TABLE serp_competitive_pages(
                observation_id TEXT, role TEXT, requested_url TEXT,
                final_url TEXT, fetch_status TEXT, http_status INTEGER,
                content_type TEXT, content_sha256 TEXT, bytes_read INTEGER, word_count INTEGER,
                title TEXT, headings_json TEXT,
                query_terms_json TEXT, query_terms_body_json TEXT
            );
        """)
        con.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("SERP-1", "AUD-1", "seguro de vida", "2026-10-10T10:00:00-03:00",
             "OBSERVED", "OBSERVED_API", "BR", "pt", "MOBILE", "google"),
        )
        con.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("SERP-2", "AUD-OTHER", "seguro de carro", "2026-10-10T10:00:00Z",
             "OBSERVED", "OBSERVED_API", "US", "en", "DESKTOP", "google"),
        )
        def page(obs, role, url, words, *, status="OBSERVED", sha="a"*64):
            con.execute(
                "INSERT INTO serp_competitive_pages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (obs, role, url, url, status, 200, "text/html; charset=utf-8", sha, 500, words,
                 "Seguros" if words else "", json.dumps(["Cobertura"] if words else []),
                 json.dumps(["seguro", "vida"] if obs == "SERP-1" else ["seguro", "carro"]),
                 json.dumps(["seguro"] if words else [])),
            )
        page("SERP-1", "CUSTOMER", "https://example.org/seguro-vida", 200)
        page("SERP-1", "COMPETITOR_CANDIDATE", "https://competitor.org/seguro-vida", 300)
        page("SERP-2", "COMPETITOR_CANDIDATE", "https://intruder.org/car", 999)
    return path


def test_only_persisted_same_serp_html_pair_is_compared_and_db_is_immutable(tmp_path):
    db = _db(tmp_path)
    before = sha256(db.read_bytes()).hexdigest()
    value = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert value["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert value["context"]["country"] == "BR"
    assert value["context"]["device"] == "MOBILE"
    assert value["context"]["html_fetch_timestamp"] is None
    assert value["customer"]["content_sha256"] == "a" * 64
    assert value["customer"]["verified_html_media_type"] == "text/html"
    assert value["comparisons"][0]["observed_word_count_difference"] == 100
    assert len(value["comparisons"]) == 1
    assert "intruder.org" not in json.dumps(value)
    assert value["perplexity_content_observed"] is False
    assert value["provider_requests"] == value["audit_writes"] == 0
    assert value["score_changed"] is value["new_collection"] is False
    assert sha256(db.read_bytes()).hexdigest() == before
    assert inspect_geo_competitor_content(db, "AUD-1", "SERP-1") == value


def test_empty_or_invalid_html_cannot_be_a_competitor_page(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET content_sha256='bad' "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'"
        )
    value = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert value["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert value["comparisons"] == []
    assert value["competitors"][0]["content_sha256"] is None
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET content_sha256=?, word_count=0, title='', headings_json='[]' "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'", ("b" * 64,)
        )
    assert inspect_geo_competitor_content(db, "AUD-1", "SERP-1")["comparisons"] == []


def test_no_other_audit_or_unverified_serp_run_is_promoted(tmp_path):
    db = _db(tmp_path)
    assert inspect_geo_competitor_content(db, "AUD-1", "SERP-2")["status"] == (
        "SERP_OBSERVATION_NOT_VERIFIED"
    )
    with sqlite3.connect(db) as con:
        con.execute("UPDATE serp_observations SET data_mode='FIXTURE' WHERE observation_id='SERP-1'")
    value = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert value["status"] == "SERP_CONTEXT_NOT_PROVEN"
    assert value["comparisons"] == []


def test_unobserved_client_does_not_become_evidence(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET fetch_status='BLOCKED' "
            "WHERE role='CUSTOMER' AND observation_id='SERP-1'"
        )
    value = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert value["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert value["comparisons"] == []


def test_malformed_or_duplicate_competitor_cannot_create_false_pair(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET requested_url=' https://competitor.org/seguro-vida' "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'"
        )
    value = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert value["comparisons"] == []


def test_competitor_redirect_to_customer_is_not_independent_evidence(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET final_url=? "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'",
            ("https://example.org/seguro-vida",),
        )
    before = sha256(db.read_bytes()).hexdigest()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert result["comparisons"] == []
    assert result["competitors"][0]["final_url"] == "https://example.org/seguro-vida"
    assert sha256(db.read_bytes()).hexdigest() == before


def test_customer_redirect_to_competitor_cannot_compare_same_final_page(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET final_url=? "
            "WHERE role='CUSTOMER' AND observation_id='SERP-1'",
            ("https://competitor.org/seguro-vida",),
        )
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert result["comparisons"] == []


def test_two_competitor_serp_urls_with_one_final_html_destination_count_once(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO serp_competitive_pages "
            "SELECT observation_id, role, ?, final_url, fetch_status, http_status, "
            "content_type, content_sha256, bytes_read, word_count, title, "
            "headings_json, query_terms_json, query_terms_body_json "
            "FROM serp_competitive_pages WHERE role='COMPETITOR_CANDIDATE' "
            "AND observation_id='SERP-1'",
            ("https://alias.com/other-page",),
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert len(result["competitors"]) == 2
    assert len(result["comparisons"]) == 1
    assert result["comparisons"][0]["observed_word_count_difference"] == 100
    assert db.read_bytes() == before


def test_legacy_absent_schema_abstains_without_ddl(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db):
        pass
    original = db.read_bytes()
    value = inspect_geo_competitor_content(db, "AUD-OLD", "SERP-OLD")
    assert value["status"] == "SERP_OBSERVATION_SCHEMA_ND"
    assert db.read_bytes() == original


def test_cli_prints_offline_only_without_touching_db(tmp_path, capsys):
    db = _db(tmp_path)
    before = db.read_bytes()
    assert main([str(db), "--audit-id", "AUD-1",
                 "--serp-observation-id", "SERP-1"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert payload["provider_requests"] == 0
    assert db.read_bytes() == before


def test_shell_or_menu_without_query_terms_in_body_is_not_comparable(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET query_terms_body_json='[]' "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'"
        )
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert result["competitors"][0]["primary_content_proven"] is False
    assert result["competitors"][0]["query_body_terms"] == []
    assert result["comparisons"] == []


def test_cross_query_persisted_terms_and_tampered_json_abstain(tmp_path):
    db = _db(tmp_path)
    for changed in ('["other", "search"]', '["seguro", 5]', 'not-json'):
        with sqlite3.connect(db) as con:
            con.execute(
                "UPDATE serp_competitive_pages SET query_terms_json=? "
                "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'",
                (changed,),
            )
        result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
        assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
        assert result["comparisons"] == []


def test_query_terms_observed_do_not_establish_primary_content(tmp_path):
    db = _db(tmp_path)
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert result["customer"]["query_body_terms"] == ["seguro"]
    assert result["competitors"][0]["query_body_terms"] == ["seguro"]
    assert result["customer"]["primary_content_proven"] is False
    assert "shells SPA e menus" in result["limitations"]


def test_non_html_200_body_cannot_be_counted_as_competitor_content(tmp_path):
    db = _db(tmp_path)
    for media_type in ("application/pdf", "text/plain", "", "image/svg+xml", None):
        with sqlite3.connect(db) as con:
            con.execute(
                "UPDATE serp_competitive_pages SET content_type=? "
                "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'",
                (media_type,),
            )
        result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
        assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
        assert result["comparisons"] == []
        assert result["competitors"][0]["verified_html_media_type"] is None
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET content_type=? "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'",
            ("application/xhtml+xml",),
        )
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert result["competitors"][0]["verified_html_media_type"] == "application/xhtml+xml"


def test_historical_schema_without_mime_evidence_abstains_readonly(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE serp_observations (
                observation_id TEXT, audit_id TEXT, query TEXT,
                collected_at TEXT, observation_status TEXT, data_mode TEXT
            );
            CREATE TABLE serp_competitive_pages (
                observation_id TEXT, role TEXT, requested_url TEXT,
                final_url TEXT, fetch_status TEXT, http_status INTEGER,
                content_sha256 TEXT, bytes_read INTEGER, word_count INTEGER,
                title TEXT, headings_json TEXT,
                query_terms_json TEXT, query_terms_body_json TEXT
            );
        """)
    old = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CONTENT_EVIDENCE_SCHEMA_ND"
    assert result["comparisons"] == []
    assert db.read_bytes() == old
