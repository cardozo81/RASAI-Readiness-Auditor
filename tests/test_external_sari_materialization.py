from __future__ import annotations

import json
from pathlib import Path

from rasai.domain import Audit, Page, RuleResult
from rasai.external_sari import RULE_ID, materialize_common_crawl_corroboration
from rasai.persistence import AuditPersistence, AuditWorkspace


def _workspace(tmp_path: Path) -> tuple[AuditWorkspace, AuditPersistence]:
    workspace = AuditWorkspace.create(tmp_path, "AUD-EXT-SARI-MAT")
    persistence = AuditPersistence(workspace)
    persistence.audits.add(Audit(audit_id="AUD-EXT-SARI-MAT", project_name="external-sari-test"))
    persistence.pages.add(
        Page(
            page_id="P1",
            audit_id="AUD-EXT-SARI-MAT",
            normalized_url="https://openai.com/research",
            discovered_url="https://openai.com/research",
        )
    )
    return workspace, persistence


def _env() -> dict[str, str]:
    return {
        "RASAI_COMMON_CRAWL_ENABLED": "true",
        "RASAI_COMMON_CRAWL_MAX_URLS": "1",
        "RASAI_COMMON_CRAWL_INDEX_COUNT": "1",
    }


def test_positive_common_crawl_materializes_reproducible_rule(monkeypatch, tmp_path: Path) -> None:
    workspace, persistence = _workspace(tmp_path)
    try:
        monkeypatch.setattr(
            "rasai.external_sari.collect_common_crawl_history",
            lambda **kwargs: "OBS-COMMON-CRAWL-TEST",
        )
        monkeypatch.setattr(
            "rasai.external_sari.archive_rows",
            lambda root: [
                {
                    "dataset_id": "OBS-COMMON-CRAWL-TEST",
                    "target_url": "https://openai.com/research",
                    "collection": "CC-MAIN-2026-34",
                    "captured_at": "2026-08-20T11:22:33Z",
                }
            ],
        )
        monkeypatch.setattr(
            "rasai.external_sari._dataset_row",
            lambda workspace, dataset_id: {"artifact_path": "artifacts/observability/common-crawl-test.json"},
        )

        result = materialize_common_crawl_corroboration(
            audit_id="AUD-EXT-SARI-MAT",
            rule_execution_ids=(),
            persistence=persistence,
            workspace=workspace,
            env=_env(),
        )

        assert result.state == "SUCCESS"
        assert result.dataset_id == "OBS-COMMON-CRAWL-TEST"
        assert result.observed_ratio == 1.0
        assert len(result.rule_execution_ids) == 1

        execution = persistence.rule_executions.get(result.rule_execution_ids[0])
        assert execution is not None
        assert execution.rule_id == RULE_ID
        assert execution.result is RuleResult.PASS
        assert execution.device is None
        assert len(execution.evidence_ids) == 1

        evidence = persistence.evidence.get(execution.evidence_ids[0])
        assert evidence is not None
        assert evidence.source == "external:common-crawl:BR-GEO-060"
        assert evidence.artifact_reference == "artifacts/observability/common-crawl-test.json"
        assert evidence.observed_value["historical_only"] is True
        assert evidence.observed_value["proves_google_or_bing_indexation"] is False
        # The binary float originates from multiplying the contracted 15% and 3%
        # weights; its public/methodological value is two-decimal 0.45 point.
        assert round(float(evidence.observed_value["maximum_overall_impact_points"]), 2) == 0.45

        state = json.loads(
            (workspace.root / "artifacts" / "observability" / "common-crawl-pre-scoring-state.json").read_text(
                encoding="utf-8"
            )
        )
        assert state["sari_rule"] == RULE_ID
        assert state["sari_contribution_materialized"] is True
    finally:
        persistence.close()


def test_no_capture_does_not_materialize_fail_or_unknown_rule(monkeypatch, tmp_path: Path) -> None:
    workspace, persistence = _workspace(tmp_path)
    try:
        monkeypatch.setattr(
            "rasai.external_sari.collect_common_crawl_history",
            lambda **kwargs: "OBS-COMMON-CRAWL-EMPTY",
        )
        monkeypatch.setattr("rasai.external_sari.archive_rows", lambda root: [])

        result = materialize_common_crawl_corroboration(
            audit_id="AUD-EXT-SARI-MAT",
            rule_execution_ids=(),
            persistence=persistence,
            workspace=workspace,
            env=_env(),
        )

        assert result.state == "NO_DATA"
        assert result.rule_execution_ids == ()
        assert result.reason == "NO_COMMON_CRAWL_CAPTURE_OBSERVED"
    finally:
        persistence.close()


def test_provider_error_does_not_materialize_rule(monkeypatch, tmp_path: Path) -> None:
    workspace, persistence = _workspace(tmp_path)
    try:
        def fail(**kwargs):
            raise RuntimeError("provider temporarily unavailable")

        monkeypatch.setattr("rasai.external_sari.collect_common_crawl_history", fail)

        result = materialize_common_crawl_corroboration(
            audit_id="AUD-EXT-SARI-MAT",
            rule_execution_ids=(),
            persistence=persistence,
            workspace=workspace,
            env=_env(),
        )

        assert result.state == "ERROR"
        assert result.rule_execution_ids == ()
        assert "RuntimeError" in str(result.reason)
    finally:
        persistence.close()
