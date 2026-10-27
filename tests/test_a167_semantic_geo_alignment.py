"""No-network acceptance for AUD-A167 semantic fallback and GEO query alignment."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from rasai.domain import RuleResult
from rasai.m7 import _PriorState, _dependency_state
from rasai.geo_search_alignment import geo_query_alignment
from rasai.semantic_recovery_runtime import _dependency_reason
from rasai.semantic_rendered_source import verified_rendered_semantic_source


def _case(tmp_path: Path, *, raw_status: int = 403, quality: str = "READY"):
    page_id, sid, aid = "P-1", "S-1", "AUD-A167"
    doc = (
        "<html><body><nav>Latest</nav><main><h1>Verified readable story</h1><p>"
        + "Substantive news story with reported evidence and document context. " * 15
        + "</p></main></body></html>"
    )
    main = "Substantive news story with reported evidence and document context. " * 15
    rendered_ref = "artifacts/rendered/source.html"
    main_ref = "artifacts/extraction/main.txt"
    (tmp_path / "artifacts/rendered").mkdir(parents=True)
    (tmp_path / "artifacts/extraction").mkdir(parents=True)
    (tmp_path / rendered_ref).write_text(doc, encoding="utf-8")
    (tmp_path / main_ref).write_text(main, encoding="utf-8")
    snapshot = SimpleNamespace(
        snapshot_id=sid, page_id=page_id, http_status=200,
        rendered_artifact_ref=rendered_ref, main_content_ref=main_ref,
        browser_metadata={
            "raw_http": {"status": raw_status},
            "capture_quality": {
                "state": quality,
                "final": {"main_text_length": len(main)},
            },
            "architecture_artifact_binding": {
                "version": "m3-artifact-binding-v1",
                "rendered_sha256": sha256(doc.encode()).hexdigest(),
            },
        },
    )
    rows = [
        SimpleNamespace(
            rule_execution_id="M5-009", rule_id="BR-GEO-009", page_id=page_id,
            snapshot_id=None, result=RuleResult.NOT_APPLICABLE,
        ),
        SimpleNamespace(
            rule_execution_id="M6-020", rule_id="BR-GEO-020", page_id=page_id,
            snapshot_id=sid, result=RuleResult.NOT_APPLICABLE,
        ),
    ]
    index = {r.rule_execution_id: r for r in rows}
    persistence = SimpleNamespace(
        pages=SimpleNamespace(get=lambda key: SimpleNamespace(audit_id=aid) if key == page_id else None),
        snapshots=SimpleNamespace(get=lambda key: snapshot if key == sid else None),
        rule_executions=SimpleNamespace(get=lambda key: index.get(key)),
    )
    workspace = SimpleNamespace(root=tmp_path)
    m5 = SimpleNamespace(rule_execution_ids=("M5-009",))
    m6 = SimpleNamespace(rule_execution_ids=("M6-020",))
    return persistence, workspace, aid, page_id, sid, m5, m6, snapshot


def test_a167_physical_rendered_403_is_semantic_source_without_rewriting_br_rules(tmp_path):
    persistence, ws, aid, page_id, sid, m5, m6, _ = _case(tmp_path)
    args = dict(persistence=persistence, workspace=ws, audit_id=aid,
                page_id=page_id, snapshot_id=sid)
    assert verified_rendered_semantic_source(**args)
    assert _dependency_reason(
        persistence=persistence, m5_result=m5, m6_result=m6,
        page_id=page_id, snapshot_id=sid, workspace=ws, audit_id=aid,
    ) is None
    prior = _PriorState(persistence, m5, m6, workspace=ws, audit_id=aid)
    assert _dependency_state("BR-GEO-038", prior, page_id, sid) is None
    assert prior.get("BR-GEO-009", page_id, sid) is RuleResult.NOT_APPLICABLE
    assert prior.get("BR-GEO-020", page_id, sid) is RuleResult.NOT_APPLICABLE


def test_a167_semantic_source_abstains_if_sha_or_scope_or_quality_is_bad(tmp_path):
    persistence, ws, aid, page_id, sid, m5, m6, snap = _case(tmp_path)
    snap.browser_metadata["architecture_artifact_binding"]["rendered_sha256"] = "0" * 64
    assert not verified_rendered_semantic_source(
        persistence=persistence, workspace=ws, audit_id=aid,
        page_id=page_id, snapshot_id=sid,
    )
    reason = _dependency_reason(
        persistence=persistence, m5_result=m5, m6_result=m6,
        page_id=page_id, snapshot_id=sid, workspace=ws, audit_id=aid,
    )
    assert reason == "TECHNICAL_PREREQUISITE_BR_GEO_009_NOT_APPLICABLE"
    snap.browser_metadata["architecture_artifact_binding"]["rendered_sha256"] = sha256(
        (ws.root / snap.rendered_artifact_ref).read_bytes()
    ).hexdigest()
    snap.browser_metadata["capture_quality"]["state"] = "INCOMPLETE"
    assert not verified_rendered_semantic_source(
        persistence=persistence, workspace=ws, audit_id=aid,
        page_id=page_id, snapshot_id=sid,
    )
    snap.browser_metadata["capture_quality"]["state"] = "READY"
    assert not verified_rendered_semantic_source(
        persistence=persistence, workspace=ws, audit_id="AUD-FOREIGN",
        page_id=page_id, snapshot_id=sid,
    )


def test_a167_semantic_source_refuses_unrelated_http_codes(tmp_path):
    persistence, ws, aid, page_id, sid, _, _, _ = _case(tmp_path, raw_status=404)
    assert not verified_rendered_semantic_source(
        persistence=persistence, workspace=ws, audit_id=aid,
        page_id=page_id, snapshot_id=sid,
    )


def test_a167_geo_alignment_reports_mismatch_without_provider_or_mutation():
    matched = geo_query_alignment(("seguro de vida",), (" Seguro de Vida ",))
    assert matched["status"] == "QUERY_MATCH"
    mismatch = geo_query_alignment(("seguro de vida",), ("seguro para família",))
    assert mismatch["status"] == "DIVERGENT"
    assert "N/D" in mismatch["label"]
    assert geo_query_alignment(("seguro de vida",), ())["status"] == "NOT_REQUESTED"
    assert geo_query_alignment(("a", "b"), ("b", "a"))["status"] == "QUERY_SET_MATCH"
