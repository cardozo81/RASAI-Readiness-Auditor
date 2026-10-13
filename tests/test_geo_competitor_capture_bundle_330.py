"""#330: physically linked SERP -> immutable opt-in competitor sidecar."""
from __future__ import annotations

from hashlib import sha256
import json
import sqlite3

import pytest

from rasai import geo_competitor_capture_bundle_330 as capture


_URL = "https://competitor.example.org/seguro"
_OBS = "SERP-OBS-330"


def _audit(tmp_path):
    folder = tmp_path / "AUD-REAL"
    folder.mkdir()
    with sqlite3.connect(folder / "audit.db") as con:
        con.executescript("""
            CREATE TABLE audits(
                audit_id TEXT,status TEXT,completion_status TEXT
            );
            CREATE TABLE serp_observations(
                observation_id TEXT,audit_id TEXT,query TEXT,collected_at TEXT,
                observation_status TEXT,data_mode TEXT,
                engine TEXT,country TEXT,region TEXT,language TEXT,device TEXT
            );
            CREATE TABLE serp_results(
                observation_id TEXT,position INTEGER,url TEXT
            );
            INSERT INTO audits VALUES ('AUD-REAL','COMPLETED','COMPLETE');
        """)
        con.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (_OBS, "AUD-REAL", "seguro de vida", "2026-10-10T10:00:00Z",
             "OBSERVED", "OBSERVED_API", "google", "BR", "São Paulo",
             "pt-BR", "mobile"),
        )
        con.execute("INSERT INTO serp_results VALUES (?,?,?)", (_OBS, 1, _URL))
    return folder


def _response(**changes):
    out = {
        "status": "STATIC_HTML_FEATURES_OBSERVED",
        "contract_version": "RASAI-COMPETITOR-ROBOTS-LOCAL-001",
        "role": "COMPETITOR_CANDIDATE",
        "robots_fetch_status": "ALLOWED",
        "requested_url": _URL, "final_url": _URL,
        "http_status": 200,
        "content_sha256": "f"*64,
        "html_fetch_timestamp": "2026-10-10T10:15:00Z",
        "html_rendering": "STATIC_HTTP_ONLY_NO_JS",
        "title": "Seguro de vida", "headings": ["Proteção"],
        "query_body_terms": ["seguro", "vida"],
        "word_count": 50,
        "primary_content_proven": False,
        "provider_requests": 2,
        "audit_writes": 0,
        "score_changed": False,
    }
    out.update(changes)
    return out


def _fake(monkeypatch, data=None):
    seen = []
    def inspect(url, **kwargs):
        seen.append((url, kwargs))
        return data if data is not None else _response()
    monkeypatch.setattr(capture, "inspect_consented_public_html", inspect)
    return seen


def _run(root, tmp_path, **kwargs):
    return capture.capture_competitor_sidecar(
        root, _OBS, _URL, output_root=tmp_path / "output",
        consented_hostnames=("competitor.example.org",),
        **kwargs,
    )


def test_source_provenance_and_versioned_output_not_written_into_aud(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path)
    calls = _fake(monkeypatch)
    original = (folder/"audit.db").read_bytes()
    first = _run(folder, tmp_path)
    assert first["status"] == "MATERIALIZED"
    assert first["companion_files_written"] == 1
    assert first["provider_requests"] == 2
    assert len(calls) == 1
    assert calls[0][0] == _URL
    assert calls[0][1]["query"] == "seguro de vida"
    assert calls[0][1]["role"] == "COMPETITOR_CANDIDATE"
    manifest = json.loads(
        open(first["manifest_path"], encoding="utf-8").read()
    )
    assert manifest["contract_version"] == "RASAI-COMPETITOR-CAPTURE-SIDECAR-330-001"
    assert manifest["source_audit_id"] == folder.name
    assert manifest["source_audit_db_sha256"] == sha256(original).hexdigest()
    assert manifest["source_serp_observation_id"] == _OBS
    assert manifest["source_serp_scope"]["country"] == "BR"
    assert manifest["content_sha256"] == "f"*64
    assert manifest["content_comparison_eligible"] is False
    assert manifest["locale_equivalence_proven"] is False
    assert manifest["device_equivalence_proven"] is False
    assert manifest["temporal_equivalence_proven"] is False
    assert manifest["raw_html_persisted"] is False
    assert manifest["audit_writes"] == 0
    assert (folder/"audit.db").read_bytes() == original
    assert not list(folder.glob("COBS-*"))
    again = _run(folder, tmp_path)
    assert again["status"] == "IDEMPOTENT_EXISTING"
    assert again["package_id"] == first["package_id"]
    assert again["companion_files_written"] == 0
    assert (folder/"audit.db").read_bytes() == original


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("UPDATE audits SET completion_status='PARTIAL_RETRYABLE'", "AUD identity"),
        ("UPDATE audits SET audit_id='AUD-OTHER'", "AUD identity"),
        ("UPDATE serp_observations SET audit_id='AUD-OTHER'", "foreign SERP"),
        ("UPDATE serp_observations SET data_mode='NOT_OBSERVED'", "foreign SERP"),
        ("UPDATE serp_observations SET language=NULL", "context not proven"),
        ("DELETE FROM serp_results", "not in persisted SERP"),
    ],
    ids=("partial", "foreign-aud", "foreign-serp", "unobserved-serp",
         "missing-locale", "absent-candidate"),
)
def test_bad_serp_or_aud_identity_blocks_http_and_does_not_create_package(
    tmp_path, monkeypatch, statement, expected,
):
    folder = _audit(tmp_path)
    calls = _fake(monkeypatch)
    with sqlite3.connect(folder/"audit.db") as con:
        con.execute(statement)
    before = (folder/"audit.db").read_bytes()
    with pytest.raises(ValueError, match=expected):
        _run(folder, tmp_path)
    assert calls == []
    assert (folder/"audit.db").read_bytes() == before
    assert not (tmp_path/"output").exists()


def test_unverified_robots_or_html_does_not_publish_evidence(tmp_path, monkeypatch):
    folder = _audit(tmp_path)
    _fake(monkeypatch, _response(status="ROBOTS_DISALLOWED"))
    result = _run(folder, tmp_path)
    assert result["status"] == "NOT_CAPTURED"
    assert result["reason"] == "ROBOTS_DISALLOWED"
    assert result["companion_files_written"] == 0
    assert result["content_comparison_eligible"] is False
    assert not (tmp_path/"output").exists()


def test_no_write_into_source_aud_and_no_followed_redirect(tmp_path, monkeypatch):
    folder = _audit(tmp_path)
    calls = _fake(monkeypatch)
    with pytest.raises(ValueError, match="outside the AUD"):
        capture.capture_competitor_sidecar(
            folder, _OBS, _URL,
            output_root=folder / "artifacts", consented_hostnames=(),
        )
    assert not calls
    _fake(monkeypatch, _response(final_url="https://wrong.example.org/path"))
    with pytest.raises(ValueError, match="final fetched URL"):
        _run(folder, tmp_path)
    assert not (tmp_path/"output").exists()


def test_source_change_during_fetch_fails_before_persistence(tmp_path, monkeypatch):
    folder = _audit(tmp_path)
    def mutate_then_return(url, **kwargs):
        with sqlite3.connect(folder/"audit.db") as con:
            con.execute("UPDATE audits SET completion_status='PARTIAL_RETRYABLE'")
        return _response()
    monkeypatch.setattr(capture, "inspect_consented_public_html", mutate_then_return)
    with pytest.raises(ValueError, match="changed during capture"):
        _run(folder, tmp_path)
    assert not (tmp_path/"output").exists()


def test_existing_corrupted_evidence_cannot_be_overwritten(tmp_path, monkeypatch):
    folder = _audit(tmp_path)
    _fake(monkeypatch)
    result = _run(folder, tmp_path)
    manifest = result["manifest_path"]
    with open(manifest, "wb") as f:
        f.write(b"tampered")
    with pytest.raises(ValueError, match="refusing overwrite"):
        _run(folder, tmp_path)
    with open(manifest, "rb") as f:
        assert f.read() == b"tampered"


def test_cli_requires_explicit_network_flag_without_reaching_network(tmp_path, capsys):
    folder = _audit(tmp_path)
    with pytest.raises(SystemExit) as exc:
        capture.main([
            "--audit-dir", str(folder), "--serp-observation-id", _OBS,
            "--candidate-url", _URL,
            "--output-root", str(tmp_path/"output"),
            "--consent-host", "competitor.example.org",
        ])
    assert exc.value.code == 2
    assert "explicit --allow-public-html-requests" in capsys.readouterr().err
    assert not (tmp_path/"output").exists()


@pytest.mark.parametrize(
    "package_relative",
    (
        "AUD-OTHER/artifacts/competitor-evidence",
        "consolidated/CONS-FOREIGN/artifacts",
        "RPR-ANOTHER/artifacts/cobs",
    ),
)
def test_capture_never_writes_inside_foreign_aud_cons_rpr_packages(
    tmp_path, monkeypatch, package_relative,
):
    folder = _audit(tmp_path)
    calls = _fake(monkeypatch)
    # Output roots must be isolated even when they belong to a DIFFERENT
    # physical package; an unrelated AUD is not writable capture storage.
    target = tmp_path / package_relative
    assert not target.exists()
    original = (folder / "audit.db").read_bytes()
    with pytest.raises(ValueError, match="outside every AUD/CONS/RPR"):
        capture.capture_competitor_sidecar(
            folder, _OBS, _URL,
            output_root=target,
            consented_hostnames=("competitor.example.org",),
        )
    assert calls == []
    assert not target.exists()
    assert (folder / "audit.db").read_bytes() == original


def test_capture_relative_parent_traversal_to_other_aud_rejected_before_network(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path)
    calls = _fake(monkeypatch)
    other = tmp_path / "AUD-OTHER"
    other.mkdir()
    misleading_root = folder / ".." / "AUD-OTHER" / "artifacts"
    with pytest.raises(ValueError, match="outside every AUD/CONS/RPR"):
        capture.capture_competitor_sidecar(
            folder, _OBS, _URL, output_root=misleading_root,
            consented_hostnames=("competitor.example.org",),
        )
    assert calls == []
    assert not (other / "artifacts").exists()


@pytest.mark.parametrize(
    "unverified_clock",
    [
        "2026-10-10",
        "2026-10-10T10:00:00",
        "2026-15-99T00:00:00Z",
        "not-a-date",
        "",
    ],
    ids=["date-only", "timezone-absent", "impossible", "malformed", "empty"],
)
def test_unverified_serp_observation_clock_refuses_before_any_network(
    tmp_path, monkeypatch, unverified_clock,
):
    folder = _audit(tmp_path)
    calls = _fake(monkeypatch)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "UPDATE serp_observations SET collected_at=? WHERE observation_id=?",
            (unverified_clock, _OBS),
        )
    before = (folder / "audit.db").read_bytes()
    with pytest.raises(ValueError, match="(UTC clock not proven|context not proven)"):
        _run(folder, tmp_path)
    assert calls == []
    assert not (tmp_path / "output").exists()
    assert (folder / "audit.db").read_bytes() == before


def test_serp_clock_is_normalized_to_utc_without_claiming_same_page_context(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path)
    _fake(monkeypatch)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "UPDATE serp_observations SET collected_at=? WHERE observation_id=?",
            ("2026-10-10T07:00:00-03:00", _OBS),
        )
    first = _run(folder, tmp_path)
    manifest = json.loads(
        open(first["manifest_path"], encoding="utf-8").read()
    )
    assert manifest["source_serp_collected_at"] == "2026-10-10T10:00:00+00:00"
    assert manifest["temporal_equivalence_proven"] is False
    assert manifest["locale_equivalence_proven"] is False
    assert manifest["content_comparison_eligible"] is False


def test_failed_http_outcome_does_not_hide_aud_mutation(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path)
    def changed_before_rejected_response(url, **kwargs):
        with sqlite3.connect(folder / "audit.db") as conn:
            conn.execute(
                "UPDATE audits SET completion_status='PARTIAL_RETRYABLE'"
            )
        return _response(status="ROBOTS_DISALLOWED")
    monkeypatch.setattr(
        capture, "inspect_consented_public_html",
        changed_before_rejected_response,
    )
    with pytest.raises(ValueError, match="physical AUD changed during capture"):
        _run(folder, tmp_path)
    assert not (tmp_path / "output").exists()


def test_new_sqlite_sidecar_during_blocked_http_rejects_source(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path)
    before = (folder / "audit.db").read_bytes()
    def sidecar_before_rejected_response(url, **kwargs):
        (folder / "audit.db-wal").write_bytes(b"concurrent write")
        return _response(status="ROBOTS_DISALLOWED")
    monkeypatch.setattr(
        capture, "inspect_consented_public_html",
        sidecar_before_rejected_response,
    )
    with pytest.raises(ValueError, match="no longer sealed"):
        _run(folder, tmp_path)
    assert not (tmp_path / "output").exists()
    assert (folder / "audit.db").read_bytes() == before


def test_aud_modified_while_manifest_is_prepared_never_gets_published(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path)
    _fake(monkeypatch)
    original_payload = capture._payload
    def manifest_built_after_source_changes(data):
        raw = original_payload(data)
        with sqlite3.connect(folder / "audit.db") as con:
            con.execute("UPDATE audits SET status='REOPENED'")
        return raw
    monkeypatch.setattr(capture, "_payload", manifest_built_after_source_changes)
    with pytest.raises(ValueError, match="physical AUD changed during capture"):
        _run(folder, tmp_path)
    destination_root = tmp_path / "output"
    assert not list(destination_root.glob("COBS-*"))
    assert not list(destination_root.glob(".cobs-staging-*"))


def test_new_sidecar_created_during_manifest_preparation_prevents_publish(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path)
    _fake(monkeypatch)
    original_payload = capture._payload
    def manifest_built_with_unsealed_source(data):
        raw = original_payload(data)
        (folder / "audit.db-journal").write_bytes(b"unsealed")
        return raw
    monkeypatch.setattr(
        capture, "_payload", manifest_built_with_unsealed_source,
    )
    with pytest.raises(ValueError, match="no longer sealed"):
        _run(folder, tmp_path)
    dest = tmp_path / "output"
    assert not list(dest.glob("COBS-*"))
    assert not list(dest.glob(".cobs-staging-*"))


def test_public_competitor_sha256_fails_closed_if_bytes_grow_while_reading(
    tmp_path, monkeypatch,
):
    # Stat at entry fits the budget; an expanding stream must not be hashed
    # without an ongoing read limit. No HTTP or physical AUD is needed.
    from io import BytesIO
    source = tmp_path / "audit.db"
    source.write_bytes(b"1234")
    monkeypatch.setattr(capture, "_MAX_SOURCE_DB_BYTES", 8)
    original_open = type(source).open

    def expanding_open(path, *args, **kwargs):
        if path == source:
            return BytesIO(b"123456789")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(type(source), "open", expanding_open)
    with pytest.raises(ValueError, match="grew beyond bounded"):
        capture._physical_digest(source)


def test_public_competitor_sha256_fails_closed_on_truncated_during_read(
    tmp_path, monkeypatch,
):
    from io import BytesIO
    source = tmp_path / "audit.db"
    source.write_bytes(b"12345678")
    monkeypatch.setattr(capture, "_MAX_SOURCE_DB_BYTES", 12)
    original_open = type(source).open

    def truncated_open(path, *args, **kwargs):
        if path == source:
            return BytesIO(b"1234")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(type(source), "open", truncated_open)
    with pytest.raises(ValueError, match="changed size"):
        capture._physical_digest(source)


_TARGET_URL = "https://customer.example.org/seguro-vida"


def _add_aud_targets(folder, rows):
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute("CREATE TABLE audit_targets(audit_id TEXT,input_url TEXT)")
        con.executemany("INSERT INTO audit_targets VALUES (?,?)", rows)


@pytest.mark.parametrize("same_aud_target", [True, False])
def test_serp_member_cannot_be_labeled_competitor_when_it_is_exact_aud_target(
    tmp_path, monkeypatch, same_aud_target,
):
    """#330: role provenance is stronger than mere SERP result membership."""
    folder = _audit(tmp_path)
    _add_aud_targets(folder, [
        (folder.name, _URL if same_aud_target else _TARGET_URL),
    ])
    seen = _fake(monkeypatch)
    original = (folder / "audit.db").read_bytes()
    if same_aud_target:
        with pytest.raises(ValueError, match="AUD target cannot be labeled"):
            _run(folder, tmp_path)
        assert seen == []
        assert not (tmp_path / "output").exists()
    else:
        outcome = _run(folder, tmp_path)
        assert outcome["status"] == "MATERIALIZED"
        assert len(seen) == 1
        assert outcome["content_comparison_eligible"] is False
    assert (folder / "audit.db").read_bytes() == original


def test_explicit_customer_capture_uses_unique_aud_target_without_serp_listing(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path)
    _add_aud_targets(folder, [(folder.name, _TARGET_URL)])
    before = sha256((folder / "audit.db").read_bytes()).hexdigest()
    seen = []
    def fake(url, **kwargs):
        seen.append((url, kwargs))
        return _response(
            role=kwargs["role"], requested_url=url, final_url=url,
            content_sha256="e"*64,
        )
    monkeypatch.setattr(capture, "inspect_consented_public_html", fake)
    result = capture.capture_competitor_sidecar(
        folder, _OBS, _TARGET_URL,
        role="CUSTOMER",
        output_root=tmp_path / "customer-evidence",
        consented_hostnames=("customer.example.org",),
    )
    assert result["status"] == "MATERIALIZED"
    assert seen[0][0] == _TARGET_URL
    assert seen[0][1]["query"] == "seguro de vida"
    assert seen[0][1]["role"] == "CUSTOMER"
    manifest = json.loads(open(result["manifest_path"], encoding="utf-8").read())
    assert manifest["contract_version"] == "RASAI-COMPETITOR-CAPTURE-SIDECAR-330-002"
    assert manifest["source_role"] == "CUSTOMER"
    assert manifest["source_target_exact_url"] == _TARGET_URL
    assert manifest["source_serp_result_membership_proven"] is False
    assert manifest["source_audit_db_sha256"] == before
    assert manifest["source_serp_observation_id"] == _OBS
    assert manifest["content_comparison_eligible"] is False
    assert manifest["primary_content_proven"] is False
    assert manifest["raw_html_persisted"] is False
    assert sha256((folder / "audit.db").read_bytes()).hexdigest() == before
    again = capture.capture_competitor_sidecar(
        folder, _OBS, _TARGET_URL,
        role="CUSTOMER",
        output_root=tmp_path / "customer-evidence",
        consented_hostnames=("customer.example.org",),
    )
    assert again["status"] == "IDEMPOTENT_EXISTING"


@pytest.mark.parametrize(
    ("targets", "expected"),
    [
        ([], "unique AUD target"),
        ([("AUD-OTHER", _TARGET_URL)], "unique AUD target"),
        ([("AUD-REAL", "https://another.example.org/vida")], "unique AUD target"),
        ([
            ("AUD-REAL", _TARGET_URL),
            ("AUD-REAL", _TARGET_URL),
        ], "unique AUD target"),
    ],
    ids=["empty", "foreign", "different-customer", "ambiguous-duplicate"],
)
def test_customer_capture_rejects_unverified_target_before_dns(
    tmp_path, monkeypatch, targets, expected,
):
    folder = _audit(tmp_path)
    _add_aud_targets(folder, targets)
    seen = _fake(monkeypatch)
    original = (folder / "audit.db").read_bytes()
    with pytest.raises(ValueError, match=expected):
        capture.capture_competitor_sidecar(
            folder, _OBS, _TARGET_URL,
            role="CUSTOMER",
            output_root=tmp_path / "out",
            consented_hostnames=("customer.example.org",),
        )
    assert seen == []
    assert not (tmp_path / "out").exists()
    assert (folder / "audit.db").read_bytes() == original


def test_customer_capture_does_not_make_nonserp_competitor_eligible(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path)
    _add_aud_targets(folder, [(folder.name, _TARGET_URL)])
    seen = _fake(monkeypatch)
    with pytest.raises(ValueError, match="not in persisted SERP"):
        capture.capture_competitor_sidecar(
            folder, _OBS, _TARGET_URL,
            role="COMPETITOR_CANDIDATE",
            output_root=tmp_path / "out",
            consented_hostnames=("customer.example.org",),
        )
    assert seen == []


def test_customer_capture_rejects_mismatched_transport_role_and_requested_url(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path)
    _add_aud_targets(folder, [(folder.name, _TARGET_URL)])
    for data in (
        _response(role="COMPETITOR_CANDIDATE",
                  requested_url=_TARGET_URL, final_url=_TARGET_URL),
        _response(role="CUSTOMER", requested_url=_URL,
                  final_url=_TARGET_URL),
        _response(role="CUSTOMER", requested_url=_TARGET_URL,
                  final_url=_TARGET_URL, robots_fetch_status="NOT_VERIFIED"),
    ):
        _fake(monkeypatch, data)
        with pytest.raises(ValueError, match="captured HTML provenance"):
            capture.capture_competitor_sidecar(
                folder, _OBS, _TARGET_URL,
                role="CUSTOMER",
                output_root=tmp_path / "out",
                consented_hostnames=("customer.example.org",),
            )
        assert not (tmp_path / "out").exists()


def _pair_capture(tmp_path, monkeypatch, *, gap_hours=1):
    from rasai.geo_competitor_pair_330 import compare_cobs_static_pair
    folder = _audit(tmp_path)
    _add_aud_targets(folder, [(folder.name, _TARGET_URL)])
    original = (folder / "audit.db").read_bytes()
    calls = []
    def fake(url, **kwargs):
        calls.append((url, kwargs["role"]))
        target = kwargs["role"] == "CUSTOMER"
        return _response(
            role=kwargs["role"], requested_url=url, final_url=url,
            title="Meu seguro" if target else "Seguro concorrente",
            headings=["Cobertura", "Assistência"] if target else ["Proteção"],
            jsonld_types=["Product"] if target else ["FAQPage", "Product"],
            query_body_terms=["vida", "seguro"] if target else ["vida"],
            content_sha256=("e" if target else "f") * 64,
            html_fetch_timestamp=(
                "2026-10-10T10:15:00Z" if target
                else ("2026-10-12T10:15:00Z" if gap_hours > 24
                      else "2026-10-10T11:15:00Z")
            ),
        )
    monkeypatch.setattr(capture, "inspect_consented_public_html", fake)
    target = capture.capture_competitor_sidecar(
        folder, _OBS, _TARGET_URL, role="CUSTOMER",
        output_root=tmp_path / "pair-evidence",
        consented_hostnames=("customer.example.org",),
    )
    competitor = _run(folder, tmp_path)
    return folder, target, competitor, original, calls


def test_customer_competitor_pair_compares_only_sealed_static_metadata(
    tmp_path, monkeypatch,
):
    from rasai.geo_competitor_pair_330 import compare_cobs_static_pair
    folder, target, competitor, original, calls = _pair_capture(tmp_path, monkeypatch)
    assert [role for _, role in calls] == ["CUSTOMER", "COMPETITOR_CANDIDATE"]
    result = compare_cobs_static_pair(
        folder, target["manifest_path"], competitor["manifest_path"],
    )
    assert result["status"] == "DESCRIPTIVE_STATIC_HTML_ONLY"
    assert result["source_audit_id"] == folder.name
    assert result["source_audit_db_sha256"] == sha256(original).hexdigest()
    assert result["source_serp_observation_id"] == _OBS
    assert result["html_capture_gap_seconds"] == 3600
    assert result["customer"]["url"] == _TARGET_URL
    assert result["competitor"]["url"] == _URL
    assert result["customer"]["title"] == "Meu seguro"
    assert result["competitor"]["title"] == "Seguro concorrente"
    assert result["title_exact_text_equal"] is False
    assert result["observed_jsonld_types_both"] == ["Product"]
    assert result["observed_jsonld_types_competitor_only"] == ["FAQPage"]
    assert result["observed_heading_text_both"] == []
    assert result["observed_heading_text_customer_only"] == ["Assistência", "Cobertura"]
    assert result["observed_heading_text_competitor_only"] == ["Proteção"]
    assert result["observed_query_body_terms_both"] == ["vida"]
    assert result["observed_query_body_terms_customer_only"] == ["seguro"]
    assert result["observed_query_body_terms_competitor_only"] == []
    assert result["static_text_intersection_method"] == "EXACT_OBSERVED_STRINGS_NO_SEMANTIC_MATCH"
    assert result["static_text_differences_are_editorial_gaps"] is False
    assert result["rendered_or_primary_content_verified"] is False
    assert result["primary_content_comparison_eligible"] is False
    assert result["editorial_gap_claim_eligible"] is False
    assert result["word_count_delta_eligible"] is False
    assert result["localisation_equivalence_proven"] is False
    assert result["generative_citation_proven"] is False
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert (folder / "audit.db").read_bytes() == original


@pytest.mark.parametrize("mutation", [
    "competitor_not_in_serp", "fabricated_query",
    "fabricated_serp_scope", "fabricated_customer_target",
])
def test_cobs_pair_refuses_rehashed_manifest_without_physical_serp_binding(
    tmp_path, monkeypatch, mutation,
):
    from pathlib import Path
    from rasai.geo_competitor_pair_330 import compare_cobs_static_pair
    folder, target, competitor, original, calls = _pair_capture(tmp_path, monkeypatch)
    customer = json.loads(Path(target["manifest_path"]).read_text(encoding="utf-8"))
    candidate = json.loads(Path(competitor["manifest_path"]).read_text(encoding="utf-8"))
    if mutation == "competitor_not_in_serp":
        forged_url = "https://not-in-serp.example.org/competitor"
        candidate["requested_url"] = forged_url
        candidate["capture"]["requested_url"] = forged_url
        candidate["capture"]["final_url"] = forged_url
    elif mutation == "fabricated_query":
        customer["source_serp_query"] = "outra consulta"
        candidate["source_serp_query"] = "outra consulta"
    elif mutation == "fabricated_serp_scope":
        customer["source_serp_scope"]["language"] = "en-US"
        candidate["source_serp_scope"]["language"] = "en-US"
    else:
        forged_url = "https://not-the-aud-target.example.org/seguro"
        customer["requested_url"] = forged_url
        customer["source_target_exact_url"] = forged_url
        customer["capture"]["requested_url"] = forged_url
        customer["capture"]["final_url"] = forged_url

    def reseal(payload):
        raw = capture._payload(payload)
        name = "COBS-" + sha256(raw).hexdigest()[:32].upper()
        path = tmp_path / "forged-evidence" / name / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    n_before = len(calls)
    with pytest.raises(ValueError, match="COBS (physical SERP|manifest SERP|customer URL|competitor URL)"):
        compare_cobs_static_pair(folder, reseal(customer), reseal(candidate))
    assert len(calls) == n_before
    assert (folder / "audit.db").read_bytes() == original


@pytest.mark.parametrize("duplicate", [
    "identical_root_key", "conflicting_root_before_valid",
    "nested_capture_role_before_valid",
])
def test_cobs_pair_refuses_rehashed_manifest_with_duplicate_json_keys(
    tmp_path, monkeypatch, duplicate,
):
    from pathlib import Path
    from rasai.geo_competitor_pair_330 import compare_cobs_static_pair
    folder, target, competitor, original, calls = _pair_capture(tmp_path, monkeypatch)
    candidate = json.loads(Path(competitor["manifest_path"]).read_text(encoding="utf-8"))
    raw = capture._payload(candidate)
    if duplicate == "identical_root_key":
        text = raw.decode("utf-8").rstrip()
        raw = (text[:-1] + ',"requested_url":' +
               json.dumps(candidate["requested_url"]) + '}').encode("utf-8")
    elif duplicate == "conflicting_root_before_valid":
        raw = (b'{"requested_url":"https://forged.example.org/page",' +
               raw.lstrip()[1:])
    else:
        raw = raw.replace(
            b'"capture": {',
            b'"capture": {"role": "CUSTOMER",',
            1,
        )
    # The previous default decoder chose the last duplicate, apparently
    # accepting a valid customer/competitor comparison after recomputing SHA.
    default = json.loads(raw)
    assert default["requested_url"] == candidate["requested_url"]
    assert default["capture"]["role"] == "COMPETITOR_CANDIDATE"
    name = "COBS-" + sha256(raw).hexdigest()[:32].upper()
    suspect = tmp_path / "rehashed-duplicate" / name / "manifest.json"
    suspect.parent.mkdir(parents=True)
    suspect.write_bytes(raw)
    before_calls = len(calls)
    with pytest.raises(ValueError, match="COBS manifest JSON invalid"):
        compare_cobs_static_pair(folder, target["manifest_path"], suspect)
    assert len(calls) == before_calls
    assert (folder / "audit.db").read_bytes() == original


@pytest.mark.parametrize(
    ("token", "site"),
    [
        ("NaN", "root"),
        ("Infinity", "root"),
        ("-Infinity", "root"),
        ("NaN", "capture"),
    ],
)
def test_cobs_pair_rejects_rehashed_manifest_with_non_json_constants(
    tmp_path, monkeypatch, token, site,
):
    """#330: SHA rehashing cannot turn invalid JSON into valid COBS evidence."""
    from pathlib import Path
    from rasai.geo_competitor_pair_330 import compare_cobs_static_pair

    folder, customer, competitor, aud_bytes, calls = _pair_capture(
        tmp_path, monkeypatch,
    )
    raw = Path(competitor["manifest_path"]).read_bytes()
    number = token.encode("ascii")
    if site == "root":
        raw = raw.rstrip()[:-1] + b', "unverified": ' + number + b"}"
    else:
        raw = raw.replace(
            b'"capture": {',
            b'"capture": {"unverified": ' + number + b",",
            1,
        )
    # Python's permissive JSON decoder accepts the nonstandard tokens,
    # whereas physical COBS JSON must be strictly conformant.
    assert isinstance(json.loads(raw), dict)
    package_id = "COBS-" + sha256(raw).hexdigest()[:32].upper()
    suspect = tmp_path / "invalid-json-sidecars" / package_id / "manifest.json"
    suspect.parent.mkdir(parents=True)
    suspect.write_bytes(raw)
    prior_requests = len(calls)
    with pytest.raises(ValueError, match="COBS manifest JSON invalid"):
        compare_cobs_static_pair(
            folder, customer["manifest_path"], suspect,
        )
    assert len(calls) == prior_requests
    assert (folder / "audit.db").read_bytes() == aud_bytes


def test_cobs_pair_fails_on_changed_physical_aud(tmp_path, monkeypatch):
    from rasai.geo_competitor_pair_330 import compare_cobs_static_pair
    folder, target, competitor, _, _ = _pair_capture(tmp_path, monkeypatch)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute("UPDATE audits SET completion_status='PARTIAL_RETRYABLE'")
    with pytest.raises(ValueError, match="different physical AUD"):
        compare_cobs_static_pair(
            folder, target["manifest_path"], competitor["manifest_path"],
        )


def test_cobs_pair_rejects_stale_capture_and_reversed_roles(tmp_path, monkeypatch):
    from rasai.geo_competitor_pair_330 import compare_cobs_static_pair
    folder, target, competitor, _, _ = _pair_capture(
        tmp_path, monkeypatch, gap_hours=48,
    )
    with pytest.raises(ValueError, match="outside permitted 24h"):
        compare_cobs_static_pair(
            folder, target["manifest_path"], competitor["manifest_path"],
        )
    with pytest.raises(ValueError, match="version does not match role"):
        compare_cobs_static_pair(
            folder, competitor["manifest_path"], target["manifest_path"],
        )


def test_cobs_pair_rejects_manifest_byte_tampering_before_reading_facts(
    tmp_path, monkeypatch,
):
    from pathlib import Path
    from rasai.geo_competitor_pair_330 import compare_cobs_static_pair
    folder, target, competitor, original, _ = _pair_capture(tmp_path, monkeypatch)
    suspect = Path(competitor["manifest_path"])
    suspect.write_bytes(suspect.read_bytes() + b" ")
    with pytest.raises(ValueError, match="package ID does not match"):
        compare_cobs_static_pair(
            folder, target["manifest_path"], suspect,
        )
    assert (folder / "audit.db").read_bytes() == original


@pytest.mark.parametrize("altered_role", ("CUSTOMER", "COMPETITOR_CANDIDATE"))
def test_cobs_pair_refuses_source_manifest_change_during_sqlite_verification(
    tmp_path, monkeypatch, altered_role,
):
    """#330: a second seal prevents stale comparisons after sidecar mutation."""
    from pathlib import Path
    from rasai import geo_competitor_pair_330 as pair

    folder, target, competitor, original, calls = _pair_capture(
        tmp_path, monkeypatch,
    )
    target_path = Path(target["manifest_path"])
    competitor_path = Path(competitor["manifest_path"])
    suspect = target_path if altered_role == "CUSTOMER" else competitor_path
    untouched = competitor_path if altered_role == "CUSTOMER" else target_path
    untouched_bytes = untouched.read_bytes()
    requests_before = len(calls)

    verify_original = pair._verify_physical_serp_pair
    invocations = []
    def modify_after_first_manifest_checks(*args, **kwargs):
        verify_original(*args, **kwargs)
        invocations.append(True)
        # Simulate a sidecar physically changed after its valid initial
        # read but before the final post-SQLite source integrity gate.
        suspect.write_bytes(suspect.read_bytes() + b" ")

    monkeypatch.setattr(
        pair, "_verify_physical_serp_pair",
        modify_after_first_manifest_checks,
    )
    with pytest.raises(ValueError, match="COBS package ID does not match"):
        pair.compare_cobs_static_pair(folder, target_path, competitor_path)
    assert invocations == [True]
    assert len(calls) == requests_before
    assert (folder / "audit.db").read_bytes() == original
    assert untouched.read_bytes() == untouched_bytes


def test_pair_cli_read_only_without_network(tmp_path, monkeypatch, capsys):
    from rasai.geo_competitor_pair_330 import main as pair_main
    folder, target, competitor, original, calls = _pair_capture(tmp_path, monkeypatch)
    requests_before = len(calls)
    assert pair_main([
        "--audit-dir", str(folder),
        "--customer-manifest", target["manifest_path"],
        "--competitor-manifest", competitor["manifest_path"],
    ]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "DESCRIPTIVE_STATIC_HTML_ONLY"
    assert len(calls) == requests_before
    assert (folder / "audit.db").read_bytes() == original


def test_real_cobs_fetch_gate_refuses_missing_operation_consent_before_dns_or_http(
    tmp_path,
):
    from rasai.search_intelligence.content import PublicWebFetcher

    folder = _audit(tmp_path)
    before = (folder / "audit.db").read_bytes()
    dns = []

    def resolver(host, port):
        dns.append((host, port))
        pytest.fail("authorization must be resolved before DNS")

    def transport(*args, **kwargs):
        pytest.fail("authorization must be resolved before HTTP")

    client = PublicWebFetcher(
        max_redirects=0, resolver=resolver, opener=transport,
    )
    result = capture.capture_competitor_sidecar(
        folder, _OBS, _URL,
        output_root=tmp_path / "output",
        consented_hostnames=("competitor.example.org",),
        consent_purpose="GEO_COMPETITOR_STATIC_CONTENT_REVIEW",
        consented_operations=("GET_ROBOTS_TXT",),
        fetcher=client,
    )
    assert result["status"] == "NOT_CAPTURED"
    assert result["reason"] == "EXPLICIT_PURPOSE_OPERATION_CONSENT_MISSING"
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert dns == []
    assert client.requests_used == 0
    assert (folder / "audit.db").read_bytes() == before
    assert not (tmp_path / "output").exists()


def test_cobs_static_text_is_exact_case_sensitive_lexical_only(tmp_path, monkeypatch):
    """A static heading case change is not inferred to be a semantic match."""
    from pathlib import Path
    from rasai.geo_competitor_pair_330 import compare_cobs_static_pair

    folder, customer, competitor, before, calls = _pair_capture(tmp_path, monkeypatch)
    manifest = json.loads(Path(competitor["manifest_path"]).read_text(encoding="utf-8"))
    manifest["capture"]["headings"] = ["cobertura", "Proteção", "Proteção"]
    manifest["capture"]["query_body_terms"] = ["VIDA", "VIDA", "seguro"]
    data = capture._payload(manifest)
    package = "COBS-" + sha256(data).hexdigest()[:32].upper()
    path = tmp_path / "renamed-cobs" / package / "manifest.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    result = compare_cobs_static_pair(folder, customer["manifest_path"], path)
    assert result["observed_heading_text_both"] == []
    assert result["observed_heading_text_customer_only"] == ["Assistência", "Cobertura"]
    assert result["observed_heading_text_competitor_only"] == ["Proteção", "cobertura"]
    assert result["observed_query_body_terms_both"] == ["seguro"]
    assert result["observed_query_body_terms_customer_only"] == ["vida"]
    assert result["observed_query_body_terms_competitor_only"] == ["VIDA"]
    assert result["editorial_gap_claim_eligible"] is False
    assert result["word_count_delta_eligible"] is False
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert (folder / "audit.db").read_bytes() == before
    assert [role for _, role in calls] == ["CUSTOMER", "COMPETITOR_CANDIDATE"]


def test_cobs_pair_standalone_html_is_escaped_and_no_new_http_or_aud_writes(
    tmp_path, monkeypatch, capsys,
):
    from pathlib import Path
    from rasai.geo_competitor_pair_330 import main as compare_cli
    folder, target, competitor, db_bytes, calls = _pair_capture(
        tmp_path, monkeypatch,
    )
    first = Path(target["manifest_path"])
    second = Path(competitor["manifest_path"])
    first_bytes, second_bytes = first.read_bytes(), second.read_bytes()
    count = len(calls)
    assert compare_cli([
        "--audit-dir", str(folder),
        "--customer-manifest", str(first),
        "--competitor-manifest", str(second),
        "--format", "html",
    ]) == 0
    page = capsys.readouterr().out
    assert "<!doctype html>" in page
    assert "lang='pt-BR'" in page
    assert "Comparacao lexical observacional - COBS" in page
    assert "URL auditada - extrato estatico" in page
    assert "URL concorrente - extrato estatico" in page
    assert "Intersecoes lexicais exatas" in page
    assert "Tipos JSON-LD" in page
    assert "Mesmo conjunto" not in page  # No inferred content equivalence.
    assert "Assistência" in page
    assert "FAQPage" in page
    assert "3600 segundos" in page
    assert "grid-template-columns:1fr 1fr" in page
    assert "@media(max-width:720px)" in page
    assert "@media print" in page
    assert "<script" not in page
    assert "Sem JS, DNS, HTTP, IA" in page
    assert len(calls) == count
    assert (folder / "audit.db").read_bytes() == db_bytes
    assert first.read_bytes() == first_bytes and second.read_bytes() == second_bytes
    assert not (folder / "report-catalog").exists()


def test_cobs_html_renderer_escapes_external_text_without_links_or_markup(
    tmp_path, monkeypatch,
):
    from copy import deepcopy
    from rasai.geo_competitor_pair_330 import compare_cobs_static_pair
    from rasai.geo_competitor_pair_html_330 import render_cobs_static_pair_html
    folder, customer, competitor, _, calls = _pair_capture(tmp_path, monkeypatch)
    verified = compare_cobs_static_pair(
        folder, customer["manifest_path"], competitor["manifest_path"],
    )
    injected = deepcopy(verified)
    tag = '<img src=x onerror="alert(330)">'
    injected["customer"]["title"] = tag
    injected["competitor"]["headings"] = ["<script>alert(330)</script>"]
    injected["observed_heading_text_competitor_only"] = [
        "<svg onload=alert(330)>",
    ]
    injected["observed_jsonld_types_both"] = ['<a href="javascript:alert(330)">X</a>']
    html = render_cobs_static_pair_html(injected)
    assert tag not in html
    assert "<script>alert" not in html
    assert "<svg onload" not in html
    assert 'href="javascript:' not in html
    assert "&lt;img src=x onerror=&quot;alert(330)&quot;&gt;" in html
    assert "&lt;svg onload=alert(330)&gt;" in html
    assert "&lt;a href=&quot;javascript:alert(330)&quot;&gt;" in html
    assert "Content-Security-Policy" in html
    assert "lacunas editoriais" in html.lower()
    assert len(calls) == 2


@pytest.mark.parametrize("tamper", [
    "fake_score", "fake_primary", "fake_write", "infinite_gap",
    "wrong_version", "wrong_status", "missing_customer",
])
def test_cobs_html_never_promotes_forged_score_or_unverified_content(
    tmp_path, monkeypatch, tamper,
):
    from copy import deepcopy
    from rasai.geo_competitor_pair_330 import compare_cobs_static_pair
    from rasai.geo_competitor_pair_html_330 import render_cobs_static_pair_html
    folder, customer, competitor, _, _ = _pair_capture(tmp_path, monkeypatch)
    value = deepcopy(compare_cobs_static_pair(
        folder, customer["manifest_path"], competitor["manifest_path"],
    ))
    if tamper == "fake_score":
        value["editorial_gap_claim_eligible"] = True
    elif tamper == "fake_primary":
        value["rendered_or_primary_content_verified"] = True
    elif tamper == "fake_write":
        value["audit_writes"] = 1
    elif tamper == "infinite_gap":
        value["html_capture_gap_seconds"] = float("inf")
    elif tamper == "wrong_version":
        value["contract_version"] = "COBS-INVENTED"
    elif tamper == "wrong_status":
        value["status"] = "EDITORIAL_GAP_PROVEN"
    else:
        value.pop("customer")
    with pytest.raises(ValueError):
        render_cobs_static_pair_html(value)
