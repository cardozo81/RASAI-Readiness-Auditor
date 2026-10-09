"""#318: no paid calls and zero source-AUD mutations."""
from __future__ import annotations

from hashlib import sha256
import json
import sqlite3

import pytest

from rasai.domain import Audit, AuditStatus, CompletionStatus
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.search_intelligence.perplexity import PerplexityHttpResponse
from rasai.geo_post_audit_complement import run_post_audit_geo_supplement as run


def source(tmp_path, monkeypatch, *, complete=True):
    aud = "AUD-POST-GEO-TEST"
    workspace = AuditWorkspace.create(tmp_path, aud)
    with AuditPersistence(workspace) as store:
        store.audits.add(Audit(
            audit_id=aud, project_name="sealed original",
            status=AuditStatus.COMPLETED if complete else AuditStatus.CREATED,
            completion_status=CompletionStatus.COMPLETE if complete else None,
        ))
    catalog = workspace.root / "report-catalog"
    catalog.mkdir()
    (catalog / "manifest.json").write_text('{"original":true}', encoding="utf-8")
    # This test is about the complement boundary, not the report package verifier.
    monkeypatch.setattr(
        "rasai.catalog_report_site.verify_catalog_report_package",
        lambda root: (True, ()),
    )
    monkeypatch.setattr(
        "rasai.catalog_report_site.catalog_report_is_fresh",
        lambda *, audit_id, workspace: True,
    )
    return workspace, aud


def fake_transport(endpoint, headers, body, timeout):
    assert "api.perplexity.ai/search" in endpoint
    assert headers["Authorization"] == "Bearer FAKE_FOR_TEST_ONLY"
    assert "FAKE_FOR_TEST_ONLY" not in body.decode("utf-8")
    payload = json.loads(body)
    assert payload["query"] == "seguro de vida"
    return PerplexityHttpResponse(
        status=200, headers={"x-request-id": "FAKE-REQ"},
        body=json.dumps({
            "id": "FAKE-PERPLEXITY-RESPONSE",
            "results": [{"url": "https://source.example/a", "title": "Fonte fake", "snippet": "Exemplo"}],
        }).encode("utf-8"),
    )


def test_one_authorized_supplement_does_not_modify_original_or_repeat_network(tmp_path, monkeypatch):
    workspace, aud = source(tmp_path, monkeypatch)
    before = sha256(workspace.database.read_bytes()).hexdigest()
    original_manifest = (workspace.root / "report-catalog" / "manifest.json").read_bytes()
    count = []

    def transport(*args):
        count.append(1)
        return fake_transport(*args)

    kwargs = dict(
        audit_id=aud, intent_id="operacao-001", query="seguro de vida",
        explicit_cost_authorization=True,
        env={"RASAI_PERPLEXITY_ENABLED": "true", "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY"},
        transport=transport,
    )
    created = run(workspace, **kwargs)
    assert created.request_executed is True
    assert created.status == "SUCCESS"
    assert created.directory is not None and created.directory.is_dir()
    assert created.directory != workspace.root
    assert workspace.root not in created.directory.parents
    assert (created.directory / "manifest.json").is_file()
    assert (created.directory / "supplement.html").is_file()
    assert len(count) == 1

    saved = run(workspace, **kwargs)
    assert saved.status == "ALREADY_RECORDED"
    assert saved.request_executed is False
    assert len(count) == 1
    assert sha256(workspace.database.read_bytes()).hexdigest() == before
    assert (workspace.root / "report-catalog" / "manifest.json").read_bytes() == original_manifest
    with sqlite3.connect(created.directory / "evidence" / "audit.db") as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchone() is None
        assert connection.execute(
            "SELECT count(*) FROM perplexity_search_runs WHERE audit_id=?", (aud,)
        ).fetchone()[0] == 1
    for path in ("manifest.json", "intent.json", "result.json", "supplement.html"):
        assert "FAKE_FOR_TEST_ONLY" not in (created.directory / path).read_text(encoding="utf-8")


def test_cost_authorization_is_not_equivalent_to_integration_flag(tmp_path, monkeypatch):
    workspace, aud = source(tmp_path, monkeypatch)
    with pytest.raises(PermissionError):
        run(workspace, audit_id=aud, intent_id="a", query="seguro de vida",
            env={"RASAI_PERPLEXITY_ENABLED": "true", "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY"},
            transport=lambda *a: pytest.fail("HTTP not authorized"))
    disabled = run(
        workspace, audit_id=aud, intent_id="a", query="seguro de vida",
        explicit_cost_authorization=True,
        env={"RASAI_PERPLEXITY_ENABLED": "false", "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY"},
        transport=lambda *a: pytest.fail("disabled must never call provider"),
    )
    assert disabled.status == "DISABLED"
    assert disabled.directory is None


def test_noncomplete_aud_or_changed_intent_never_executes(tmp_path, monkeypatch):
    workspace, aud = source(tmp_path, monkeypatch, complete=False)
    with pytest.raises(ValueError, match="COMPLETE"):
        run(workspace, audit_id=aud, intent_id="a", query="seguro de vida",
            explicit_cost_authorization=True,
            env={"RASAI_PERPLEXITY_ENABLED": "true", "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY"},
            transport=lambda *a: pytest.fail("incomplete AUD must not call"))


def test_same_intent_with_different_payload_is_rejected_before_http(tmp_path, monkeypatch):
    workspace, aud = source(tmp_path, monkeypatch)
    env = {"RASAI_PERPLEXITY_ENABLED": "true", "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY"}
    first = run(workspace, audit_id=aud, intent_id="same-intent", query="seguro de vida",
                explicit_cost_authorization=True, env=env, transport=fake_transport)
    assert first.status == "SUCCESS"
    with pytest.raises(ValueError, match="same intent_id"):
        run(workspace, audit_id=aud, intent_id="same-intent", query="previdencia",
            explicit_cost_authorization=True, env=env,
            transport=lambda *args: pytest.fail("changed scope must not call API"))


def test_timeout_has_unknown_billability_and_must_never_auto_resend(tmp_path, monkeypatch):
    from rasai.search_intelligence.perplexity import PerplexityTimeoutError
    workspace, aud = source(tmp_path, monkeypatch)
    transport_calls = []
    def ambiguous_timeout(*args):
        transport_calls.append(1)
        raise PerplexityTimeoutError("request dispatched, no response")

    kwargs = dict(
        audit_id=aud, intent_id="timeout-unresolved", query="seguro de vida",
        explicit_cost_authorization=True,
        env={"RASAI_PERPLEXITY_ENABLED": "true", "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY"},
        transport=ambiguous_timeout,
    )
    first = run(workspace, **kwargs)
    assert first.request_executed is True
    assert first.billability == "UNKNOWN"
    assert len(transport_calls) == 1
    repeated = run(workspace, **kwargs)
    assert repeated.status == "ALREADY_RECORDED"
    assert repeated.request_executed is False
    assert repeated.billability == "UNKNOWN"
    assert len(transport_calls) == 1
    assert first.directory is not None
    stored = json.loads((first.directory / "result.json").read_text(encoding="utf-8"))
    assert stored["billability"] == "UNKNOWN"
    assert stored["native_usage_quantity"] == 1.0


@pytest.mark.parametrize(
    ("status_code", "expected_status"),
    [(401, "AUTH_ERROR"), (402, "CREDIT_ERROR"), (429, "RATE_LIMIT_ERROR")],
)
def test_provider_business_errors_keep_original_sealed_and_never_retry(
    tmp_path, monkeypatch, status_code, expected_status,
):
    workspace, aud = source(tmp_path, monkeypatch)
    initial_db = sha256(workspace.database.read_bytes()).hexdigest()
    original_manifest = (workspace.root / "report-catalog" / "manifest.json").read_bytes()
    calls = []

    def negative_transport(*args):
        calls.append(status_code)
        return PerplexityHttpResponse(
            status=status_code, headers={},
            body=b'{"error":{"message":"no credits or invalid key"}}',
        )

    kwargs = dict(
        audit_id=aud, intent_id=f"http-{status_code}",
        query="seguro de vida", explicit_cost_authorization=True,
        env={"RASAI_PERPLEXITY_ENABLED": "true", "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY"},
        transport=negative_transport,
    )
    first = run(workspace, **kwargs)
    assert first.request_executed is True
    assert first.status == expected_status
    assert first.directory is not None
    with sqlite3.connect(first.directory / "evidence" / "audit.db") as con:
        assert con.execute(
            "SELECT status FROM perplexity_search_runs WHERE audit_id=?", (aud,)
        ).fetchone()[0] == expected_status
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    second = run(workspace, **kwargs)
    assert second.status == "ALREADY_RECORDED"
    assert second.request_executed is False
    assert len(calls) == 1
    assert sha256(workspace.database.read_bytes()).hexdigest() == initial_db
    assert (workspace.root / "report-catalog" / "manifest.json").read_bytes() == original_manifest


def test_existing_incomplete_intent_reservation_blocks_dispatch(tmp_path, monkeypatch):
    from hashlib import sha256 as digest

    workspace, aud = source(tmp_path, monkeypatch)
    intent = "crash-recovered"
    directory = (
        workspace.root.parent / ".rasai-geo-supplements" / aud
        / digest(intent.encode("utf-8")).hexdigest()[:32]
    )
    directory.mkdir(parents=True)
    # Simulates crash before intent.json became durable.
    kwargs = dict(
        audit_id=aud, intent_id=intent, query="seguro de vida",
        explicit_cost_authorization=True,
        env={"RASAI_PERPLEXITY_ENABLED": "true", "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY"},
        transport=lambda *args: pytest.fail("uncertain reservation must never call provider"),
    )
    result = run(workspace, **kwargs)
    assert result.status == "PENDING_UNCERTAIN"
    assert result.request_executed is False
    assert result.billability == "NOT_ATTEMPTED"
    assert not (directory / "evidence").exists()


def test_intent_payload_reuse_cannot_change_search_type_or_options(tmp_path, monkeypatch):
    workspace, aud = source(tmp_path, monkeypatch)
    common = dict(
        audit_id=aud, intent_id="unique-intent",
        query="seguro de vida", explicit_cost_authorization=True,
        env={"RASAI_PERPLEXITY_ENABLED": "true", "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY"},
    )
    first = run(workspace, **common, transport=fake_transport)
    assert first.status == "SUCCESS"
    with pytest.raises(ValueError, match="same intent_id"):
        run(
            workspace, **common, search_type="fast",
            transport=lambda *args: pytest.fail("new request cannot reuse intent"),
        )



def test_reused_supplement_fails_closed_when_source_aud_changes(tmp_path, monkeypatch):
    workspace, aud = source(tmp_path, monkeypatch)
    calls = []
    def transport(*args):
        calls.append(1)
        return fake_transport(*args)

    params = dict(
        audit_id=aud, intent_id="immutable-source",
        query="seguro de vida", explicit_cost_authorization=True,
        env={"RASAI_PERPLEXITY_ENABLED": "true", "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY"},
        transport=transport,
    )
    first = run(workspace, **params)
    assert first.status == "SUCCESS"
    with sqlite3.connect(workspace.database) as con:
        con.execute("CREATE TABLE post_audit_marker(id TEXT)")
    with pytest.raises(ValueError, match="source AUD changed since intent"):
        run(workspace, **params)
    assert len(calls) == 1


def test_corrupt_manifest_and_untrusted_manifest_path_never_resend(tmp_path, monkeypatch):
    workspace, aud = source(tmp_path, monkeypatch)
    calls = []
    def transport(*args):
        calls.append(1)
        return fake_transport(*args)

    params = dict(
        audit_id=aud, intent_id="manifest-tamper",
        query="seguro de vida", explicit_cost_authorization=True,
        env={"RASAI_PERPLEXITY_ENABLED": "true", "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY"},
        transport=transport,
    )
    result = run(workspace, **params)
    assert result.directory is not None
    manifest_path = result.directory / "manifest.json"
    original = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text("not json", encoding="utf-8")
    invalid = run(workspace, **params)
    assert invalid.status == "PENDING_UNCERTAIN"
    assert invalid.request_executed is False
    manifest = json.loads(original)
    manifest["files"][0]["path"] = "../../audit.db"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete|unsafe file path"):
        run(workspace, **params)
    assert len(calls) == 1


def test_manifest_mismatched_audit_identity_never_reuses_sidecar(tmp_path, monkeypatch):
    workspace, aud = source(tmp_path, monkeypatch)
    params = dict(
        audit_id=aud, intent_id="manifest-provenance",
        query="seguro de vida", explicit_cost_authorization=True,
        env={"RASAI_PERPLEXITY_ENABLED": "true", "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY"},
    )
    result = run(workspace, **params, transport=fake_transport)
    assert result.directory is not None
    path = result.directory / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["audit_id"] = "AUD-SPOOF"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance mismatch"):
        run(workspace, **params, transport=lambda *args: pytest.fail("must not resend"))



def test_stale_report_catalog_rejected_before_any_paid_intent(tmp_path, monkeypatch):
    workspace, aud = source(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "rasai.catalog_report_site.catalog_report_is_fresh",
        lambda *, audit_id, workspace: False,
    )
    env = {
        "RASAI_PERPLEXITY_ENABLED": "true",
        "PERPLEXITY_API_KEY": "FAKE_FOR_TEST_ONLY",
    }
    with pytest.raises(ValueError, match="stale against source AUD"):
        run(
            workspace,
            audit_id=aud, intent_id="stale-package", query="seguro de vida",
            explicit_cost_authorization=True, env=env,
            transport=lambda *args: pytest.fail("stale AUD must not dispatch"),
        )
    assert not (workspace.root.parent / ".rasai-geo-supplements").exists()
