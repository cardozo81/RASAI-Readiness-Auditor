from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai import console_execution_profiles as profiles
from rasai.execution_completion_reliability import (
    _harden_m24_schema,
    _install_console_gsc_profile_lifetime,
    _reconcile_crux_no_data,
)
from rasai.execution_context_isolation import (
    build_execution_environment,
    install as install_execution_context_isolation,
)
from rasai.gsc_scope import GSC_ENABLED_ENV
from rasai.m21_web_performance import M21ExecutionResult


def test_crux_not_found_is_no_data_and_does_not_make_valid_lighthouse_partial(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE web_performance_attempts(
          attempt_id TEXT,audit_id TEXT,page_id TEXT,snapshot_id TEXT,device TEXT,url TEXT,
          service TEXT,status TEXT,http_status INTEGER,duration_ms INTEGER,error_code TEXT,
          error_message TEXT,artifact_reference TEXT,created_at TEXT
        );
        CREATE TABLE web_performance_observations(
          observation_id TEXT,audit_id TEXT,page_id TEXT,snapshot_id TEXT,device TEXT,url TEXT,
          strategy TEXT,status TEXT,lighthouse_version TEXT,lighthouse_fetch_time TEXT,
          performance_score REAL,accessibility_score REAL,best_practices_score REAL,seo_score REAL,
          agentic_browsing_score REAL,fcp_lab_ms REAL,speed_index_lab_ms REAL,lcp_lab_ms REAL,
          tbt_lab_ms REAL,cls_lab REAL,field_source TEXT,field_scope TEXT,lcp_p75_ms REAL,
          inp_p75_ms REAL,cls_p75 REAL,lcp_assessment TEXT,inp_assessment TEXT,cls_assessment TEXT,
          cwv_assessment TEXT,pagespeed_http_status INTEGER,crux_http_status INTEGER,
          pagespeed_artifact_reference TEXT,crux_artifact_reference TEXT,error_summary TEXT,captured_at TEXT
        );
        CREATE TABLE web_performance_runs(
          audit_id TEXT,enabled INTEGER,status TEXT,field_source TEXT,page_limit INTEGER,
          pages_considered INTEGER,context_attempts INTEGER,successful_contexts INTEGER,
          pagespeed_successes INTEGER,crux_successes INTEGER,categories TEXT,reason TEXT,updated_at TEXT
        );
        """
    )
    connection.execute(
        "INSERT INTO web_performance_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "A-CRUX","AUD-X","P1","S1","MOBILE","https://example.test/","CRUX_API",
            "ERROR",404,12,"NOT_FOUND","chrome ux report data not found",None,"2026-09-14T00:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO web_performance_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "O1","AUD-X","P1","S1","MOBILE","https://example.test/","mobile","PARTIAL",
            "13.0",None,91.0,95.0,93.0,96.0,None,900.0,1100.0,1400.0,20.0,0.01,
            None,None,None,None,None,None,None,None,"UNAVAILABLE",200,None,
            "artifacts/psi.json",None,"CRUX:NOT_FOUND","2026-09-14T00:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO web_performance_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "AUD-X",1,"PARTIAL","auto",10,1,1,1,1,0,"[]",
            "ONE_OR_MORE_EXTERNAL_COMPONENTS_UNAVAILABLE","2026-09-14T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    result = M21ExecutionResult(
        status="PARTIAL", enabled=True, pages_considered=1, context_attempts=1,
        successful_contexts=1, pagespeed_attempts=1, pagespeed_successes=1,
        crux_attempts=1, crux_successes=0, partial_contexts=1, observation_ids=("O1",),
    )
    corrected = _reconcile_crux_no_data(SimpleNamespace(database=database), "AUD-X", result)
    assert corrected.status == "SUCCESS"
    assert corrected.partial_contexts == 0

    connection = sqlite3.connect(database)
    attempt = connection.execute(
        "SELECT status,error_code FROM web_performance_attempts WHERE attempt_id='A-CRUX'"
    ).fetchone()
    observation = connection.execute(
        """SELECT status,error_summary,crux_http_status
           FROM web_performance_observations WHERE observation_id='O1'"""
    ).fetchone()
    run = connection.execute(
        "SELECT status,reason FROM web_performance_runs WHERE audit_id='AUD-X'"
    ).fetchone()
    connection.close()
    assert attempt == ("NO_DATA", "NO_DATA")
    assert observation == ("SUCCESS", None, 404)
    assert run == ("SUCCESS", None)


def test_m24_schema_binds_each_resource_to_its_own_evidence_ids() -> None:
    base = {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "diagnostic_code": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "resource_assessments": {"type": "array", "items": {"type": "object"}},
        },
    }
    facts = [
        {
            "code": "M24-ROBOTS",
            "category": "ROBOTS",
            "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
            "evidence_ids": ["EV-ROBOTS-1"],
        },
        {
            "code": "M24-SITEMAP",
            "category": "SITEMAP",
            "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
            "evidence_ids": ["EV-SITEMAP-1"],
        },
    ]
    hardened = _harden_m24_schema(base, facts)
    items = hardened["properties"]["resource_assessments"]["items"]
    branches = items["anyOf"]
    by_resource = {
        branch["properties"]["resource"]["enum"][0]: branch
        for branch in branches
    }
    assert by_resource["ROBOTS"]["properties"]["evidence_ids"]["items"]["enum"] == ["EV-ROBOTS-1"]
    assert by_resource["SITEMAP"]["properties"]["evidence_ids"]["items"]["enum"] == ["EV-SITEMAP-1"]


def test_active_profile_keeps_canonical_gsc_and_projects_disabled_only_to_execution(monkeypatch) -> None:
    from rasai import console_execution_profile_readiness as readiness

    monkeypatch.setenv(GSC_ENABLED_ENV, "true")
    _install_console_gsc_profile_lifetime()
    install_execution_context_isolation()
    readiness.install()
    state = SimpleNamespace(
        input_mode="url",
        target="https://example.test/",
        ai_provider="none",
        ai_model=None,
        ai_reasoning=None,
        runtime_blocks={},
        web_performance=False,
        lighthouse_categories="",
        content_remediation=False,
        technical_remediation=False,
        synthetic_apdex=False,
        apdex_experience=False,
        search_queries=(),
        search_depth=20,
        search_device="mobile",
        improvement_enabled=False,
        improvement_provider="",
        improvement_model="",
        improvement_reasoning="",
        error="",
        operation="",
    )
    session = profiles.set_profile(state, profile_id="seo")
    readiness.set_gsc_profile_policy(session, readiness.GSC_PROFILE_DISABLED)

    with profiles.effective_profile(state, session):
        # Canonical user/session configuration is never the profile overlay.
        assert __import__("os").environ[GSC_ENABLED_ENV] == "true"
        execution_env = build_execution_environment(state)
        assert execution_env[GSC_ENABLED_ENV] == "false"

    assert __import__("os").environ[GSC_ENABLED_ENV] == "true"
    profiles.clear_profile(state)
    assert __import__("os").environ[GSC_ENABLED_ENV] == "true"