from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.completion_recovery_alignment import (
    _install_final_m24_resource_alignment,
    _reconcile_recovery_crux_no_data,
)


def test_final_m24_wrapper_projects_diagnostic_and_baseline_evidence(monkeypatch) -> None:
    from rasai import m24_ai

    captured: dict[str, object] = {}

    def fake_call(candidate, *args, **kwargs):
        captured.update(kwargs)
        return "RESULT", "ATTEMPT"

    monkeypatch.setattr(m24_ai, "_call", fake_call)
    _install_final_m24_resource_alignment()

    facts = [
        {
            "code": "M24-SITEMAP-HTTP_ERROR",
            "category": "SITEMAP",
            "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
            "evidence_ids": ["EV-SITEMAP-DIAGNOSTIC"],
        },
        {
            "code": "M24-RESOURCE-SITEMAP-BASELINE",
            "category": "SITEMAP",
            "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
            "evidence_ids": ["EV-SITEMAP-BASELINE"],
        },
        {
            "code": "M24-RESOURCE-ROBOTS-BASELINE",
            "category": "ROBOTS",
            "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
            "evidence_ids": ["EV-ROBOTS-BASELINE"],
        },
    ]
    result = m24_ai._call(
        SimpleNamespace(),
        facts=facts,
        allowed_codes=frozenset(item["code"] for item in facts),
        allowed_evidence=frozenset(
            {"EV-SITEMAP-DIAGNOSTIC", "EV-SITEMAP-BASELINE", "EV-ROBOTS-BASELINE"}
        ),
        resource_evidence={"SITEMAP": frozenset({"EV-SITEMAP-BASELINE"})},
        page_row={},
        attempt_index=1,
    )

    assert result == ("RESULT", "ATTEMPT")
    assert captured["resource_evidence"] == {
        "SITEMAP": frozenset({"EV-SITEMAP-DIAGNOSTIC", "EV-SITEMAP-BASELINE"}),
        "ROBOTS": frozenset({"EV-ROBOTS-BASELINE"}),
    }


def test_reprocess_crux_not_found_replaces_stale_unavailable_in_auto_mode(tmp_path: Path) -> None:
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
            "A-OLD","AUD-X","P1","S1","MOBILE","https://example.test/","CRUX_API",
            "ERROR",503,10,"UNAVAILABLE","service unavailable",None,"2026-09-14T23:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO web_performance_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "A-LATEST","AUD-X","P1","S1","MOBILE","https://example.test/","CRUX_API",
            "ERROR",404,10,"NOT_FOUND","chrome ux report data not found",None,"2026-09-15T00:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO web_performance_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "O1","AUD-X","P1","S1","MOBILE","https://example.test/","mobile","PARTIAL",
            "13.0",None,99.0,95.0,98.0,96.0,None,700.0,900.0,800.0,10.0,0.01,
            None,None,None,None,None,None,None,None,"UNAVAILABLE",200,None,
            "artifacts/psi.json",None,"CRUX:NOT_FOUND;CRUX:UNAVAILABLE","2026-09-15T00:00:01Z",
        ),
    )
    connection.execute(
        "INSERT INTO web_performance_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "AUD-X",1,"PARTIAL","auto",10,1,1,0,1,0,"[]",
            "ONE_OR_MORE_CONTEXTS_INCOMPLETE","2026-09-15T00:00:01Z",
        ),
    )
    connection.commit()
    connection.close()

    completed = _reconcile_recovery_crux_no_data(
        SimpleNamespace(database=database),
        "AUD-X",
    )
    assert completed is True

    connection = sqlite3.connect(database)
    attempt = connection.execute(
        "SELECT status,error_code FROM web_performance_attempts WHERE attempt_id='A-LATEST'"
    ).fetchone()
    observation = connection.execute(
        "SELECT status,error_summary,crux_http_status FROM web_performance_observations WHERE observation_id='O1'"
    ).fetchone()
    run = connection.execute(
        "SELECT status,successful_contexts,reason FROM web_performance_runs WHERE audit_id='AUD-X'"
    ).fetchone()
    connection.close()

    assert attempt == ("NO_DATA", "NO_DATA")
    assert observation == ("SUCCESS", None, 404)
    assert run == ("SUCCESS", 1, None)
