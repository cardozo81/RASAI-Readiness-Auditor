from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.catalog_status_causality import explain_catalog_status


AUD = "AUD-CAUSE"


def _data(work_items=()):
    return SimpleNamespace(audit_id=AUD, work_items=tuple(work_items))


def test_common_crawl_5xx_is_external_not_site_failure(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as con:
        con.execute(
            """CREATE TABLE standards_service_runs(
                audit_id TEXT,service_id TEXT,requested INTEGER,effective_enabled INTEGER,
                state TEXT,details_json TEXT
            )"""
        )
        con.execute(
            "INSERT INTO standards_service_runs VALUES (?,?,?,?,?,?)",
            (AUD, "common-crawl", 1, 1, "NO_DATA", "{}"),
        )

    artifact = tmp_path / "artifacts" / "observability" / "common-crawl.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({
        "error_details": [{
            "error_type": "RuntimeError",
            "message": "HTTP 503",
            "endpoint": "https://index.commoncrawl.org/secret-path",
        }]
    }), encoding="utf-8")
    obs = artifact.parent / "observability.db"
    with sqlite3.connect(obs) as con:
        con.execute(
            "CREATE TABLE datasets(dataset_id TEXT,source_type TEXT,artifact_path TEXT,metadata TEXT)"
        )
        con.execute(
            "INSERT INTO datasets VALUES (?,?,?,?)",
            ("OBS-1", "COMMON_CRAWL_CDX_HISTORY",
             "artifacts/observability/common-crawl.json", json.dumps({"errors": 1})),
        )

    causes = explain_catalog_status(
        database, _data(), "CAT-05", effective_status="PARCIAL"
    )
    cause = next(item for item in causes if item.cause_code == "COMMON_CRAWL_PROVIDER_5XX")
    assert cause.cause_class == "EXTERNAL_INTEGRATION"
    assert cause.retryable is True
    assert cause.terminal is False
    assert "externa ao site" in cause.business_explanation
    assert "secret-path" not in cause.technical_explanation


def test_serp_terminal_limited_reports_observed_requested_without_retry(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as con:
        con.execute(
            """CREATE TABLE serp_observations(
                observation_id TEXT,audit_id TEXT,requested_depth INTEGER,
                observation_status TEXT,quality_metadata TEXT
            )"""
        )
        con.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?)",
            (
                "SERP-1", AUD, 20, "OBSERVED",
                json.dumps({
                    "requested_depth_complete": False,
                    "observed_position_count": 9,
                    "observed_position_ceiling": 9,
                    "pagination_ended_before_requested_depth": True,
                    "request_budget_ended_before_requested_depth": False,
                    "normalization_incomplete_for_requested_depth": False,
                }),
            ),
        )

    causes = explain_catalog_status(
        database, _data(), "CAT-05", effective_status="PARCIAL"
    )
    cause = next(item for item in causes if item.cause_code == "SERP_TERMINAL_LIMITED")
    assert "9 de 20" in cause.technical_explanation
    assert cause.retryable is False
    assert cause.terminal is True
    assert "não podem ser tratadas como ausência" in cause.business_explanation


def test_integral_catalog_has_no_spurious_cause(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    sqlite3.connect(database).close()
    work = ({"component": "WEB_PERFORMANCE", "status": "SUCCESS"},)
    assert explain_catalog_status(
        database, _data(work), "CAT-04",
        effective_status="CONCLUÍDO", work_items=work,
    ) == ()


def test_generic_retryable_and_blocked_states_are_reusable(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    sqlite3.connect(database).close()
    retry_work = ({
        "component": "WEB_PERFORMANCE", "scope_key": "mobile",
        "status": "FAILED_RETRYABLE", "retryable": 1,
        "last_error_code": "PROVIDER_TIMEOUT",
    },)
    blocked_work = ({
        "component": "PASSIVE_SECURITY", "scope_key": "default",
        "status": "BLOCKED", "retryable": 0,
        "last_error_code": "DEPENDENCY_REQUIRED",
    },)

    retry = explain_catalog_status(
        database, _data(retry_work), "CAT-04",
        effective_status="FALHA", work_items=retry_work,
    )[0]
    blocked = explain_catalog_status(
        database, _data(blocked_work), "CAT-10",
        effective_status="PARCIAL", work_items=blocked_work,
    )[0]

    assert retry.cause_code == "WEB_PERFORMANCE_FAILED_RETRYABLE"
    assert retry.retryable is True and retry.terminal is False
    assert blocked.cause_code == "PASSIVE_SECURITY_BLOCKED"
    assert blocked.cause_class == "DEPENDENCY_BLOCK"


def test_causal_projection_does_not_echo_free_form_secret_message(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    sqlite3.connect(database).close()
    work = ({
        "component": "WEB_PERFORMANCE",
        "scope_key": "mobile",
        "status": "FAILED_RETRYABLE",
        "retryable": 1,
        "last_error_code": "TRANSPORT_ERROR",
        "last_error_message": "Authorization: Bearer super-secret-token",
    },)
    cause = explain_catalog_status(
        database, _data(work), "CAT-04",
        effective_status="FALHA", work_items=work,
    )[0]
    rendered = " ".join((
        cause.technical_explanation,
        cause.business_explanation,
        " ".join(cause.evidence_references),
    ))
    assert "super-secret-token" not in rendered
    assert "Bearer" not in rendered
