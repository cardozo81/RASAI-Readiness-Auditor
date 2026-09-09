from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import tempfile

import pytest

from rasai.platform.deployment import compare_deployment_pair, resolve_deployment_pair
from rasai.platform.indexing import index_audit_workspace
from rasai.platform.postgres_admin import migrate_postgres
from rasai.platform.postgres_store import PostgreSQLPlatformStore
from rasai.platform.reporting import write_deployment_report, write_platform_site


POSTGRES_URL = os.getenv("RASAI_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="RASAI_TEST_POSTGRES_URL is not configured")


def _reset(store: PostgreSQLPlatformStore) -> None:
    store._connection.execute(
        """TRUNCATE TABLE
           search_monitor_runs,search_monitor_queries,notifications,external_records,
           external_datasets,usage_events,integrations,alert_rules,comparison_runs,
           golden_baselines,audit_scope_links,page_identity_urls,page_identities,
           schedules,milestones,audit_index,memberships,environments,properties,
           projects,workspaces,users,organizations RESTART IDENTITY CASCADE"""
    )


def _audit(
    root: Path,
    audit_id: str,
    *,
    completed_at: str,
    rule_result: str,
    title: str,
) -> Path:
    workspace = root / audit_id
    workspace.mkdir(parents=True)
    database = workspace / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            f"""
            CREATE TABLE audits (
                audit_id TEXT PRIMARY KEY, project_name TEXT, created_at TEXT, started_at TEXT,
                completed_at TEXT, status TEXT, completion_status TEXT, auditor_version TEXT, ruleset_version TEXT
            );
            INSERT INTO audits VALUES ('{audit_id}','PostgreSQL Audit Catalog','{completed_at}','{completed_at}','{completed_at}','COMPLETED','COMPLETE','1.0','RULESET-1');
            CREATE TABLE audit_targets (target_id TEXT PRIMARY KEY,audit_id TEXT,normalized_origin TEXT,target_type TEXT);
            INSERT INTO audit_targets VALUES ('T1','{audit_id}','https://example.test','DOMAIN');
            CREATE TABLE pages (page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            INSERT INTO pages VALUES ('P1','{audit_id}','https://example.test/a');
            CREATE TABLE page_snapshots (
                snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT,captured_at TEXT,http_status INTEGER,
                final_url TEXT,canonical TEXT,meta_robots TEXT,title TEXT,structured_data_ref TEXT,
                rendered_artifact_ref TEXT,raw_artifact_ref TEXT,main_content_ref TEXT
            );
            INSERT INTO page_snapshots VALUES ('S1','P1','MOBILE','{completed_at}',200,'https://example.test/a','https://example.test/a','index,follow','{title}',NULL,NULL,NULL,NULL);
            CREATE TABLE rule_executions (
                audit_id TEXT,rule_id TEXT,page_id TEXT,device TEXT,result TEXT,observed_value TEXT,error TEXT,executed_at TEXT
            );
            INSERT INTO rule_executions VALUES ('{audit_id}','BR-GEO-011','P1','MOBILE','{rule_result}','{{}}',NULL,'{completed_at}');
            CREATE TABLE findings (
                audit_id TEXT,severity TEXT,rule_id TEXT,page_id TEXT,device TEXT,status TEXT,title TEXT,observed_value TEXT
            );
            INSERT INTO findings VALUES ('{audit_id}','HIGH','BR-GEO-011','P1','MOBILE','OPEN','Indexabilidade','{{}}');
            CREATE TABLE scores (
                score_id TEXT PRIMARY KEY,audit_id TEXT,dimension TEXT,device TEXT,value REAL,coverage REAL,
                confidence TEXT,consolidation_status TEXT,scoring_version TEXT,calculated_at TEXT
            );
            INSERT INTO scores VALUES ('SC-{audit_id}','{audit_id}','INDEXABILITY','MOBILE',90,1.0,'HIGH','CONSOLIDATED','SCORE-GEO-004','{completed_at}');
            """
        )
        connection.commit()
    finally:
        connection.close()
    (workspace / "artifacts").mkdir()
    return workspace


def test_postgresql_catalog_indexes_immutable_sqlite_auds_and_compares_deployment() -> None:
    assert POSTGRES_URL is not None
    migrate_postgres(POSTGRES_URL)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        before = _audit(
            root,
            "AUD-PG-BEFORE",
            completed_at="2026-09-09T09:00:00+00:00",
            rule_result="PASS",
            title="Before",
        )
        after = _audit(
            root,
            "AUD-PG-AFTER",
            completed_at="2026-09-09T11:00:00+00:00",
            rule_result="FAIL",
            title="After",
        )
        before_bytes = (before / "audit.db").read_bytes()
        after_bytes = (after / "audit.db").read_bytes()

        with PostgreSQLPlatformStore(POSTGRES_URL) as store:
            _reset(store)
            before_record, unchanged = index_audit_workspace(store, before)
            assert unchanged is False
            after_record, unchanged = index_audit_workspace(store, after)
            assert unchanged is False
            _same_record, unchanged = index_audit_workspace(store, before)
            assert unchanged is True

            valid, expected, actual = store.validate_audit_immutability(before_record.audit_id)
            assert valid is True
            assert expected == actual

            hierarchy = store.hierarchy_for_property(before_record.property_id)
            milestone = store.add_milestone(
                project_id=str(hierarchy["project_id"]),
                property_id=before_record.property_id,
                environment_id=before_record.environment_id,
                kind="DEPLOYMENT",
                occurred_at="2026-09-09T10:00:00+00:00",
                title="PostgreSQL parity release",
            )
            pair = resolve_deployment_pair(store, milestone)
            assert pair.baseline_audit_id == before_record.audit_id
            assert pair.current_audit_id == after_record.audit_id
            assert pair.comparable is True

            result, gate = compare_deployment_pair(store, pair)
            assert any(event.rule_id == "BR-GEO-011" and event.status == "REGRESSED" for event in result.events)
            report, manifest = write_deployment_report(store, pair, result, gate, root / "deploy-report")
            assert report.is_file()
            assert manifest.is_file()
            site = write_platform_site(store, root / "platform-report")
            assert site.is_file()
            assert "AUD-PG-BEFORE" in site.read_text(encoding="utf-8")

        assert (before / "audit.db").read_bytes() == before_bytes
        assert (after / "audit.db").read_bytes() == after_bytes


def test_postgresql_catalog_detects_audit_tampering_without_rewriting_evidence() -> None:
    assert POSTGRES_URL is not None
    migrate_postgres(POSTGRES_URL)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _audit(
            root,
            "AUD-PG-TAMPER",
            completed_at="2026-09-09T09:00:00+00:00",
            rule_result="PASS",
            title="Original",
        )
        with PostgreSQLPlatformStore(POSTGRES_URL) as store:
            _reset(store)
            record, _ = index_audit_workspace(store, workspace)
            connection = sqlite3.connect(workspace / "audit.db")
            try:
                connection.execute("UPDATE audits SET project_name='TAMPERED'")
                connection.commit()
            finally:
                connection.close()
            valid, expected, actual = store.validate_audit_immutability(record.audit_id)
            assert valid is False
            assert expected != actual
            with pytest.raises(RuntimeError, match="immutable audit"):
                index_audit_workspace(store, workspace)
