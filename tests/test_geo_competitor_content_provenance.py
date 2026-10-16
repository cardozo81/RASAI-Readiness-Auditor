"""#330: persisted SERP HTML provenance only, never snippet or network."""
from __future__ import annotations

from hashlib import sha256
import json
import sqlite3

import pytest

from rasai.geo_competitor_content_provenance import (
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
            CREATE TABLE serp_results(
                observation_id TEXT, position INTEGER, url TEXT
            );
            CREATE TABLE audit_targets(
                audit_id TEXT, input_url TEXT
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
        con.execute(
            "INSERT INTO audit_targets VALUES (?,?)",
            ("AUD-1", "https://example.org/seguro-vida"),
        )
        con.execute(
            "INSERT INTO serp_results VALUES (?,?,?)",
            ("SERP-1", 1, "https://competitor.org/seguro-vida"),
        )
        con.execute(
            "INSERT INTO serp_results VALUES (?,?,?)",
            ("SERP-2", 1, "https://intruder.org/car"),
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


def test_observed_html_without_final_url_cannot_claim_page_identity(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET final_url=NULL "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'"
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert result["comparisons"] == []
    assert result["competitors"][0]["final_url"] is None
    assert result["competitors"][0]["content_sha256"] is None
    assert db.read_bytes() == before


def test_customer_html_without_final_url_cannot_enter_comparison(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET final_url=NULL "
            "WHERE role='CUSTOMER' AND observation_id='SERP-1'"
        )
    before = sha256(db.read_bytes()).hexdigest()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert result["comparisons"] == []
    assert result["customer"]["content_evidence_status"] == "NOT_COMPARABLE"
    assert sha256(db.read_bytes()).hexdigest() == before


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


@pytest.mark.parametrize("role", ["CUSTOMER", "COMPETITOR_CANDIDATE"])
@pytest.mark.parametrize("repetition", [
    ["seguro", "seguro"],
    ["seguro", "vida", "seguro"],
])
def test_duplicate_persisted_body_terms_never_inflate_competitor_lexical_counts(
    tmp_path, role, repetition,
):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET query_terms_body_json=? "
            "WHERE observation_id='SERP-1' AND role=?",
            (json.dumps(repetition), role),
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert result["comparisons"] == []
    affected = (result["customer"] if role == "CUSTOMER"
                else result["competitors"][0])
    assert affected["content_evidence_status"] == "NOT_COMPARABLE"
    assert affected["query_body_terms"] == []
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert db.read_bytes() == before


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


def test_current_html_features_reuse_persisted_lexical_evidence_without_scoring(tmp_path):
    db = _db(tmp_path)
    fields = (
        "meta_description", "query_terms_title_json",
        "query_terms_description_json", "query_terms_headings_json",
        "jsonld_types_json",
    )
    with sqlite3.connect(db) as con:
        for name in fields:
            con.execute(f"ALTER TABLE serp_competitive_pages ADD COLUMN {name} TEXT")
        for role, data in (
            ("CUSTOMER", (
                "Plano de seguro", '["seguro"]', '[]', '["seguro"]', '[]',
            )),
            ("COMPETITOR_CANDIDATE", (
                "Proteção de seguro", '["seguro","vida"]',
                '["seguro"]', '[]', '["Product","FAQPage"]',
            )),
        ):
            con.execute(
                "UPDATE serp_competitive_pages SET " +
                ", ".join(f"{name}=?" for name in fields) +
                " WHERE observation_id='SERP-1' AND role=?",
                (*data, role),
            )
    original = sha256(db.read_bytes()).hexdigest()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert result["comparisons"][0]["observed_lexical_differences"] == {
        "query_terms_in_title": 1,
        "query_terms_in_description": 1,
        "query_terms_in_headings": -1,
        "query_terms_in_body": 0,
    }
    assert result["competitors"][0]["jsonld_types"] == ["Product", "FAQPage"]
    assert result["competitors"][0]["primary_content_proven"] is False
    assert result["score_changed"] is False
    assert sha256(db.read_bytes()).hexdigest() == original


def test_legacy_optional_features_are_nd_and_observed_empty_is_zero(tmp_path):
    db = _db(tmp_path)
    old = db.read_bytes()
    preview = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    diffs = preview["comparisons"][0]["observed_lexical_differences"]
    assert diffs == {
        "query_terms_in_title": None,
        "query_terms_in_description": None,
        "query_terms_in_headings": None,
        "query_terms_in_body": 0,
    }
    assert preview["competitors"][0]["jsonld_types"] is None
    assert db.read_bytes() == old


@pytest.mark.parametrize(
    ("column", "expected_field", "required"),
    [
        ("query_terms_json", None, True),
        ("query_terms_body_json", None, True),
        ("query_terms_title_json", "query_title_terms", False),
        ("query_terms_description_json", "query_description_terms", False),
        ("query_terms_headings_json", "query_heading_terms", False),
        ("jsonld_types_json", "jsonld_types", False),
    ],
)
def test_oversized_persisted_lexical_json_cannot_supply_html_evidence(
    tmp_path, column, expected_field, required,
):
    db = _db(tmp_path)
    oversized_valid_json = " " * (32 * 1024 + 1) + '["seguro"]'
    with sqlite3.connect(db) as con:
        if not required:
            con.execute(f"ALTER TABLE serp_competitive_pages ADD COLUMN {column} TEXT")
        con.execute(
            f"UPDATE serp_competitive_pages SET {column}=? "
            "WHERE observation_id='SERP-1' AND role='COMPETITOR_CANDIDATE'",
            (oversized_valid_json,),
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    competitor = result["competitors"][0]
    if required:
        assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
        assert result["comparisons"] == []
        assert competitor["content_evidence_status"] == "NOT_COMPARABLE"
    else:
        assert result["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
        assert len(result["comparisons"]) == 1
        assert competitor[expected_field] is None
        if column != "jsonld_types_json":
            field = {
                "query_terms_title_json": "query_terms_in_title",
                "query_terms_description_json": "query_terms_in_description",
                "query_terms_headings_json": "query_terms_in_headings",
            }[column]
            assert result["comparisons"][0]["observed_lexical_differences"][field] is None
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert result["score_changed"] is False
    assert db.read_bytes() == before


def test_malformed_optional_lexical_json_abstains_without_falsifying_zero(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "ALTER TABLE serp_competitive_pages ADD COLUMN query_terms_title_json TEXT"
        )
        con.execute(
            "ALTER TABLE serp_competitive_pages ADD COLUMN jsonld_types_json TEXT"
        )
        con.execute(
            "UPDATE serp_competitive_pages SET query_terms_title_json='[]', "
            "jsonld_types_json='[]' WHERE role='CUSTOMER' AND observation_id='SERP-1'"
        )
        con.execute(
            "UPDATE serp_competitive_pages SET query_terms_title_json=?, "
            "jsonld_types_json=? WHERE role='COMPETITOR_CANDIDATE' "
            "AND observation_id='SERP-1'",
            ('["unrelated"]', '{"tampered": true}'),
        )
    original = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert result["comparisons"][0]["observed_lexical_differences"][
        "query_terms_in_title"
    ] is None
    assert result["competitors"][0]["jsonld_types"] is None
    assert result["customer"]["query_title_terms"] == []
    assert db.read_bytes() == original


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


def test_duplicate_serp_observation_id_from_foreign_aud_cannot_inject_html(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO serp_observations "
            "SELECT observation_id, 'AUD-FOREIGN', query, collected_at, "
            "observation_status, data_mode, country, language, device, engine "
            "FROM serp_observations WHERE observation_id='SERP-1'"
        )
    initial = sha256(db.read_bytes()).hexdigest()
    outcome = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert outcome["status"] == "SERP_OBSERVATION_ID_AMBIGUOUS_OR_FOREIGN"
    assert outcome["customer"] is None
    assert outcome["competitors"] == []
    assert outcome["comparisons"] == []
    assert sha256(db.read_bytes()).hexdigest() == initial


def test_optional_content_aud_scoping_blocks_foreign_rows(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("ALTER TABLE serp_competitive_pages ADD COLUMN audit_id TEXT")
        con.execute(
            "UPDATE serp_competitive_pages SET audit_id='AUD-1' "
            "WHERE observation_id='SERP-1'"
        )
        con.execute(
            "UPDATE serp_competitive_pages SET audit_id='AUD-FOREIGN' "
            "WHERE observation_id='SERP-1' AND role='COMPETITOR_CANDIDATE'"
        )
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CROSS_AUD_CONTENT_PROVENANCE_UNVERIFIABLE"
    assert not result["comparisons"]


def test_mutating_physical_aud_while_evaluating_cannot_return_content_metrics(
    tmp_path, monkeypatch,
):
    from rasai import geo_competitor_content_provenance as module
    db = _db(tmp_path)
    original = module._page
    triggered = []
    def edit_after_snapshot(row, expected_terms):
        if not triggered:
            triggered.append(True)
            with sqlite3.connect(db) as con:
                con.execute(
                    "UPDATE serp_competitive_pages SET title='changed mid-read' "
                    "WHERE observation_id='SERP-1' AND role='CUSTOMER'"
                )
        return original(row, expected_terms)
    monkeypatch.setattr(module, "_page", edit_after_snapshot)
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert triggered
    assert result["status"] == "AUD_SOURCE_CHANGED_DURING_READ"
    assert result["customer"] is None
    assert result["comparisons"] == []


def test_sqlite_sidecar_abstains_before_content_read(tmp_path):
    import pytest
    db = _db(tmp_path)
    sidecar = db.parent / "audit.db-wal"
    sidecar.write_bytes(b"unverified concurrent transaction")
    with pytest.raises(ValueError, match="SQLite sidecars"):
        inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert sidecar.read_bytes() == b"unverified concurrent transaction"


def test_cross_hostname_competitor_redirect_is_not_misattributed_to_serp_host(
    tmp_path,
):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET final_url=? "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'",
            ("https://third-party-host.net/landing",),
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert result["comparisons"] == []
    assert result["competitors"][0]["requested_url"] == (
        "https://competitor.org/seguro-vida"
    )
    assert result["competitors"][0]["final_url"] == (
        "https://third-party-host.net/landing"
    )
    assert result["competitors"][0]["primary_content_proven"] is False
    assert result["audit_writes"] == result["provider_requests"] == 0
    assert db.read_bytes() == before


def test_cross_hostname_customer_redirect_cannot_claim_target_text_gap(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET final_url=? "
            "WHERE role='CUSTOMER' AND observation_id='SERP-1'",
            ("https://unrelated-customer-landing.net/other",),
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert result["customer"]["final_url"] == (
        "https://unrelated-customer-landing.net/other"
    )
    assert result["comparisons"] == []
    assert result["customer"]["primary_content_proven"] is False
    assert db.read_bytes() == before


def test_same_hostname_redirect_retains_final_url_and_observational_limit(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET final_url=? "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'",
            ("https://competitor.org/canonical-landing",),
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert result["competitors"][0]["final_url"] == (
        "https://competitor.org/canonical-landing"
    )
    assert result["comparisons"][0]["meaning"] == (
        "DESCRIPTIVE_CONTENT_ONLY_NO_CAUSAL_CLAIM"
    )
    assert result["competitors"][0]["primary_content_proven"] is False
    assert db.read_bytes() == before


def test_deep_competitor_html_requires_serp_result_membership_for_pair(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        # HTML is persisted but its URL was never returned in the observed
        # SERP. The link by observation_id alone does not prove membership.
        con.execute(
            "UPDATE serp_competitive_pages SET requested_url=?,final_url=? "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'",
            ("https://unrelated.org/not-observed",
             "https://unrelated.org/not-observed"),
        )
    before = db.read_bytes()
    value = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert value["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert value["comparisons"] == []
    assert value["competitors"][0]["serp_result_membership_proven"] is False
    assert value["competitors"][0]["primary_content_proven"] is False
    assert value["provider_requests"] == value["audit_writes"] == 0
    assert db.read_bytes() == before


def test_deep_content_without_physical_serp_results_is_nd_not_fake_pair(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("DROP TABLE serp_results")
    before = db.read_bytes()
    output = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert output["status"] == "SERP_RESULT_URL_PROVENANCE_ND"
    assert output["comparisons"] == []
    assert output["competitors"] == [] and output["customer"] is None
    assert db.read_bytes() == before


def test_deep_content_serp_member_from_foreign_observation_not_sufficient(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("DELETE FROM serp_results WHERE observation_id='SERP-1'")
    original = db.read_bytes()
    value = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert value["status"] == "SERP_RESULT_URL_PROVENANCE_ND"
    assert value["comparisons"] == []
    assert db.read_bytes() == original


def test_deep_content_serp_identity_is_preserved_with_valid_physical_member(tmp_path):
    db = _db(tmp_path)
    before = db.read_bytes()
    value = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert value["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert value["comparisons"][0]["competitor_url"] == (
        "https://competitor.org/seguro-vida"
    )
    assert value["competitors"][0]["serp_result_membership_proven"] is True
    assert db.read_bytes() == before


def test_customer_content_must_match_unique_physical_aud_target(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages "
            "SET requested_url='https://other-aud-customer.net/landing',"
            "final_url='https://other-aud-customer.net/landing' "
            "WHERE role='CUSTOMER' AND observation_id='SERP-1'"
        )
    before = db.read_bytes()
    out = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert out["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert out["customer"]["aud_target_exact_url_proven"] is False
    assert out["comparisons"] == []
    assert out["competitors"][0]["serp_result_membership_proven"] is True
    assert out["provider_requests"] == out["audit_writes"] == 0
    assert db.read_bytes() == before


def test_target_from_other_audit_never_grants_customer_content_identity(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("DELETE FROM audit_targets")
        con.execute(
            "INSERT INTO audit_targets VALUES (?,?)",
            ("AUD-OTHER", "https://example.org/seguro-vida"),
        )
    before = db.read_bytes()
    out = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert out["status"] == "AUD_TARGET_URL_PROVENANCE_ND"
    assert out["customer"] is None
    assert out["competitors"] == out["comparisons"] == []
    assert db.read_bytes() == before


def test_missing_or_ambiguous_physical_target_abstains_before_html_pair(tmp_path):
    for defect in ("missing_table", "missing_row", "two_targets", "bad_url"):
        from pathlib import Path
        folder = tmp_path / defect
        folder.mkdir()
        db = _db(folder)
        with sqlite3.connect(db) as con:
            if defect == "missing_table":
                con.execute("DROP TABLE audit_targets")
            elif defect == "missing_row":
                con.execute("DELETE FROM audit_targets")
            elif defect == "two_targets":
                con.execute(
                    "INSERT INTO audit_targets VALUES (?,?)",
                    ("AUD-1", "https://example.org/other"),
                )
            else:
                con.execute(
                    "UPDATE audit_targets SET input_url=? WHERE audit_id='AUD-1'",
                    ("javascript:alert(1)",),
                )
        before = db.read_bytes()
        out = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
        assert out["status"] == "AUD_TARGET_URL_PROVENANCE_ND"
        assert out["customer"] is None and out["comparisons"] == []
        assert out["provider_requests"] == out["audit_writes"] == 0
        assert db.read_bytes() == before


def test_exact_customer_target_can_compare_serp_member_without_primary_claim(tmp_path):
    db = _db(tmp_path)
    before = db.read_bytes()
    out = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert out["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert out["customer"]["aud_target_exact_url_proven"] is True
    assert out["competitors"][0]["serp_result_membership_proven"] is True
    assert len(out["comparisons"]) == 1
    assert out["customer"]["primary_content_proven"] is False
    assert out["provider_requests"] == out["audit_writes"] == 0
    assert db.read_bytes() == before


@pytest.mark.parametrize(
    "final_url",
    (
        "http://competitor.org/landing",
        "https://competitor.org:8443/landing",
        "http://competitor.org:8080/landing",
    ),
)
def test_same_hostname_different_http_origin_competitor_cannot_compare(
    tmp_path, final_url,
):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET final_url=? "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'",
            (final_url,),
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert result["comparisons"] == []
    assert result["competitors"][0]["final_url"] == final_url
    assert result["competitors"][0]["primary_content_proven"] is False
    assert db.read_bytes() == before


@pytest.mark.parametrize(
    "final_url",
    (
        "http://example.org/seguro-vida",
        "https://example.org:8443/seguro-vida",
        "http://example.org:8080/seguro-vida",
    ),
)
def test_same_hostname_different_http_origin_customer_cannot_compare(
    tmp_path, final_url,
):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET final_url=? "
            "WHERE role='CUSTOMER' AND observation_id='SERP-1'",
            (final_url,),
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert result["comparisons"] == []
    assert result["customer"]["aud_target_exact_url_proven"] is True
    assert result["customer"]["final_url"] == final_url
    assert db.read_bytes() == before


def test_default_tls_port_redirect_within_same_origin_remains_observational(
    tmp_path,
):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET final_url=? "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'",
            ("https://competitor.org:443/canonical-landing",),
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert len(result["comparisons"]) == 1
    assert result["customer"]["aud_target_exact_url_proven"] is True
    assert result["competitors"][0]["serp_result_membership_proven"] is True
    assert result["competitors"][0]["primary_content_proven"] is False
    assert db.read_bytes() == before


@pytest.mark.parametrize(
    "defect",
    ("missing", "malformed", "non_list", "non_string",
     "blank_heading", "oversized_bytes", "over_100_headings"),
)
def test_invalid_or_unbounded_persisted_headings_never_infer_zero(
    tmp_path, defect,
):
    # Keep pytest IDs short on Windows: large raw parameter values
    # can overflow its 32767-character environment-variable limit.
    bad_headings = {
        "missing": None,
        "malformed": "{invalid-json",
        "non_list": '{"not": "a-list"}',
        "non_string": '["real heading", 7]',
        "blank_heading": '["real heading", "  "]',
        "oversized_bytes": json.dumps(["x" * (128 * 1024 + 1)]),
        "over_100_headings": json.dumps([str(i) for i in range(101)]),
    }[defect]
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET headings_json=? "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'",
            (bad_headings,),
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "CONTENT_EVIDENCE_NOT_COMPARABLE"
    assert result["comparisons"] == []
    assert result["competitors"][0]["content_evidence_status"] == "NOT_COMPARABLE"
    assert result["competitors"][0]["headings_count"] is None
    assert result["competitors"][0]["primary_content_proven"] is False
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert db.read_bytes() == before


def test_explicit_empty_headings_is_observed_zero_when_title_is_present(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET headings_json='[]' "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'"
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert result["competitors"][0]["headings_count"] == 0
    assert len(result["comparisons"]) == 1
    assert db.read_bytes() == before


def test_bounded_persisted_headings_are_counted_without_silent_truncation(tmp_path):
    db = _db(tmp_path)
    headings = [f"Tópico {i}" for i in range(40)]
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE serp_competitive_pages SET headings_json=? "
            "WHERE role='COMPETITOR_CANDIDATE' AND observation_id='SERP-1'",
            (json.dumps(headings),),
        )
    before = db.read_bytes()
    result = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert result["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert result["competitors"][0]["headings_count"] == 40
    assert result["competitors"][0]["title_present"] is True
    assert result["competitors"][0]["primary_content_proven"] is False
    assert db.read_bytes() == before


def test_duplicate_same_serp_competitor_url_with_conflicting_html_abstains(
    tmp_path,
):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO serp_competitive_pages "
            "SELECT observation_id, role, requested_url, final_url, "
            "fetch_status, http_status, content_type, ?, bytes_read, ?, "
            "title, headings_json, query_terms_json, query_terms_body_json "
            "FROM serp_competitive_pages "
            "WHERE observation_id='SERP-1' AND role='COMPETITOR_CANDIDATE'",
            ("b" * 64, 9999),
        )
    original = db.read_bytes()
    out = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert out["status"] == "COMPETITOR_HTML_REQUESTED_URL_AMBIGUOUS"
    assert out["comparisons"] == []
    assert out["competitors"] == []
    assert out["customer"] is None
    assert out["provider_requests"] == out["audit_writes"] == 0
    assert db.read_bytes() == original


def test_same_serp_competitor_url_duplicate_even_if_html_equal_abstains(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO serp_competitive_pages "
            "SELECT * FROM serp_competitive_pages "
            "WHERE observation_id='SERP-1' AND role='COMPETITOR_CANDIDATE'"
        )
    before = db.read_bytes()
    out = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert out["status"] == "COMPETITOR_HTML_REQUESTED_URL_AMBIGUOUS"
    assert out["comparisons"] == []
    assert db.read_bytes() == before


def test_different_serp_urls_same_final_destination_remain_deduplicated(
    tmp_path,
):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO serp_results VALUES (?,?,?)",
            ("SERP-1", 2, "https://competitor.org/redirect-alias"),
        )
        con.execute(
            "INSERT INTO serp_competitive_pages "
            "SELECT observation_id,role,?,final_url,fetch_status,http_status,"
            "content_type,content_sha256,bytes_read,word_count,title,"
            "headings_json,query_terms_json,query_terms_body_json "
            "FROM serp_competitive_pages "
            "WHERE observation_id='SERP-1' AND role='COMPETITOR_CANDIDATE'",
            ("https://competitor.org/redirect-alias",),
        )
    original = db.read_bytes()
    out = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert out["status"] == "DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
    assert len(out["competitors"]) == 2
    assert len(out["comparisons"]) == 1
    assert out["provider_requests"] == out["audit_writes"] == 0
    assert db.read_bytes() == original


def test_jsonld_type_must_not_be_truncated_into_false_persisted_fact(tmp_path):
    from rasai.geo_competitor_content_provenance import _optional_jsonld_types
    oversized = "Schema" + "X" * 120
    assert _optional_jsonld_types(json.dumps([oversized])) is None
    assert _optional_jsonld_types(json.dumps(["FAQPage", "Product"])) == [
        "FAQPage", "Product",
    ]
    assert _optional_jsonld_types(json.dumps(["X" * 120])) == ["X" * 120]


def test_jsonld_repeated_type_cannot_inflate_observed_schema_inventory():
    from rasai.geo_competitor_content_provenance import _optional_jsonld_types
    assert _optional_jsonld_types('["Product","Product"]') is None
    assert _optional_jsonld_types('["Product","FAQPage"]') == ["Product", "FAQPage"]


@pytest.mark.parametrize("invalid", ["javascript:alert(1)", " https://malformed.test/", "https://user:secret@competitor.test/"])
def test_malformed_serp_member_cannot_be_silently_removed_from_comparison(tmp_path, invalid):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("INSERT INTO serp_results VALUES (?,?,?)", ("SERP-1", 2, invalid))
    original = db.read_bytes()
    value = inspect_geo_competitor_content(db, "AUD-1", "SERP-1")
    assert value["status"] == "SERP_RESULT_URL_IDENTITY_UNVERIFIABLE"
    assert value["comparisons"] == []
    assert db.read_bytes() == original
