from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile

from searchgeo.platform.automation import compute_next_run
from searchgeo.platform.central_store import CentralPlatformStore
from searchgeo.platform.cli import build_parser
from searchgeo.platform.deployment import compare_deployment_pair, resolve_deployment_pair
from searchgeo.platform.indexing import index_audit_workspace
from searchgeo.platform.integrations import classify_ai_crawler, import_combined_access_log, import_ga4_csv
from searchgeo.platform.models import Schedule
from searchgeo.platform.page_compare import compare_pages, write_page_compare_report
from searchgeo.platform.reporting import write_deployment_report, write_platform_site


def _audit(
    root: Path,
    audit_id: str,
    *,
    completed_at: str,
    rule_result: str = "PASS",
    canonical_a: str = "https://example.test/a",
    title_a: str = "Produto A",
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
            INSERT INTO audits VALUES ('{audit_id}','Projeto Produto','{completed_at}','{completed_at}','{completed_at}','COMPLETED','COMPLETE','1.0','RULESET-1');
            CREATE TABLE audit_targets (target_id TEXT PRIMARY KEY,audit_id TEXT,normalized_origin TEXT,target_type TEXT);
            INSERT INTO audit_targets VALUES ('T1','{audit_id}','https://example.test','DOMAIN');
            CREATE TABLE pages (page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            INSERT INTO pages VALUES ('P1','{audit_id}','https://example.test/a');
            INSERT INTO pages VALUES ('P2','{audit_id}','https://example.test/b');
            CREATE TABLE page_snapshots (
                snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT,captured_at TEXT,http_status INTEGER,
                final_url TEXT,canonical TEXT,meta_robots TEXT,title TEXT,structured_data_ref TEXT,
                rendered_artifact_ref TEXT,raw_artifact_ref TEXT,main_content_ref TEXT
            );
            INSERT INTO page_snapshots VALUES ('S1','P1','MOBILE','{completed_at}',200,'https://example.test/a','{canonical_a}','index,follow','{title_a}',NULL,NULL,NULL,NULL);
            INSERT INTO page_snapshots VALUES ('S2','P2','MOBILE','{completed_at}',200,'https://example.test/b','https://example.test/b','index,follow','Produto B',NULL,NULL,NULL,NULL);
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
            INSERT INTO scores VALUES ('SC1','{audit_id}','INDEXABILITY','MOBILE',90,1.0,'HIGH','CONSOLIDATED','SCORE-GEO-003','{completed_at}');
            """
        )
        connection.commit()
    finally:
        connection.close()
    (workspace / "artifacts").mkdir()
    return workspace


def _add_secondary_domain(workspace: Path, audit_id: str, completed_at: str) -> None:
    connection = sqlite3.connect(workspace / "audit.db")
    try:
        connection.execute(
            "INSERT INTO audit_targets VALUES (?,?,?,?)",
            ("T2", audit_id, "https://shop.example.test", "DOMAIN"),
        )
        connection.execute(
            "INSERT INTO pages VALUES (?,?,?)",
            ("P3", audit_id, "https://shop.example.test/item"),
        )
        connection.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "S3", "P3", "MOBILE", completed_at, 200,
                "https://shop.example.test/item", "https://shop.example.test/item",
                "index,follow", "Item", None, None, None, None,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_platform_store_is_central_sidecar_and_hierarchy_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "Audits With Space"
        database = root / ".searchgeo" / "platform.db"
        with CentralPlatformStore(database) as store:
            org1, ws1, project1, prop1, env1 = store.ensure_local_hierarchy(
                project_name="Loja Brasil", origin="https://www.example.test"
            )
            org2, ws2, project2, prop2, env2 = store.ensure_local_hierarchy(
                project_name="Loja Brasil", origin="https://www.example.test"
            )
            assert org1.organization_id == org2.organization_id
            assert ws1.workspace_id == ws2.workspace_id
            assert project1.project_id == project2.project_id
            assert prop1.property_id == prop2.property_id
            assert env1.environment_id == env2.environment_id
            assert store.counts()["properties"] == 1
            assert store.data_governance_status()["canonical_schema"] == 2
        assert database.is_file()


def test_audit_index_preserves_immutable_audit_and_detects_tamper() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _audit(root, "AUD-BASE", completed_at="2026-09-07T10:00:00-03:00")
        with CentralPlatformStore(root / ".searchgeo" / "platform.db") as store:
            record, unchanged = index_audit_workspace(store, workspace)
            assert unchanged is False
            _, unchanged_again = index_audit_workspace(store, workspace)
            assert unchanged_again is True
            valid, expected, actual = store.validate_audit_immutability(record.audit_id)
            assert valid is True
            assert expected == actual
            connection = sqlite3.connect(workspace / "audit.db")
            try:
                connection.execute("UPDATE audits SET project_name='TAMPERED'")
                connection.commit()
            finally:
                connection.close()
            valid, expected, actual = store.validate_audit_immutability(record.audit_id)
            assert valid is False
            assert expected != actual
            try:
                index_audit_workspace(store, workspace)
            except RuntimeError as exc:
                assert "immutable audit" in str(exc)
            else:
                raise AssertionError("tampered AUD must not be silently re-indexed")


def test_multidomain_audit_is_linked_to_every_property_scope() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        completed = "2026-09-07T10:00:00-03:00"
        workspace = _audit(root, "AUD-MULTI", completed_at=completed)
        _add_secondary_domain(workspace, "AUD-MULTI", completed)
        with CentralPlatformStore(root / ".searchgeo" / "platform.db") as store:
            record, _ = index_audit_workspace(store, workspace)
            scopes = store.audit_scopes(record.audit_id)
            assert len(scopes) == 2
            assert {scope["hostname"] for scope in scopes} == {"example.test", "shop.example.test"}
            secondary = next(scope for scope in scopes if scope["hostname"] == "shop.example.test")
            secondary_audits = store.list_audits(
                property_id=str(secondary["property_id"]),
                environment_id=str(secondary["environment_id"]),
            )
            assert [item.audit_id for item in secondary_audits] == ["AUD-MULTI"]
            store.set_golden_baseline(
                str(secondary["property_id"]),
                str(secondary["environment_id"]),
                record.audit_id,
            )
            assert store.get_golden_baseline(
                str(secondary["property_id"]), str(secondary["environment_id"])
            ) == record.audit_id
            site = write_platform_site(store, root / "platform-report")
            html = site.read_text(encoding="utf-8")
            assert "shop.example.test" in html
            assert "AUD-MULTI" in html


def test_multiuser_membership_and_scope_integrity_are_tenant_safe() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with CentralPlatformStore(Path(directory) / ".searchgeo" / "platform.db") as store:
            org_a = store.get_or_create_organization("Org A", slug="org-a")
            org_b = store.get_or_create_organization("Org B", slug="org-b")
            ws_a = store.get_or_create_workspace(org_a.organization_id, "Client A")
            ws_b = store.get_or_create_workspace(org_b.organization_id, "Client B")
            prj_a = store.get_or_create_project(ws_a.workspace_id, "Site A")
            prj_b = store.get_or_create_project(ws_b.workspace_id, "Site B")
            prop_a = store.get_or_create_property(prj_a.project_id, "A", "https://a.example.test")
            env_a = store.get_or_create_environment(prop_a.property_id, "Production", "PRODUCTION", prop_a.canonical_origin)
            user = store.get_or_create_user("Analyst", email="analyst@example.test")
            membership = store.add_membership(
                org_a.organization_id,
                user.user_id,
                "ANALYST",
                workspace_id=ws_a.workspace_id,
                project_id=prj_a.project_id,
            )
            assert membership.startswith("MBR-")
            assert len(store.list_memberships(organization_id=org_a.organization_id)) == 1
            try:
                store.add_membership(
                    org_a.organization_id,
                    user.user_id,
                    "VIEWER",
                    workspace_id=ws_b.workspace_id,
                    project_id=prj_b.project_id,
                )
            except ValueError as exc:
                assert "organization" in str(exc)
            else:
                raise AssertionError("cross-tenant membership must be rejected")
            try:
                store.add_milestone(
                    project_id=prj_b.project_id,
                    property_id=prop_a.property_id,
                    environment_id=env_a.environment_id,
                    kind="DEPLOYMENT",
                    occurred_at="2026-09-07T12:00:00-03:00",
                    title="Invalid cross-project deploy",
                )
            except ValueError as exc:
                assert "project" in str(exc)
            else:
                raise AssertionError("cross-project milestone must be rejected")


def test_deployment_pair_before_after_gate_and_reports() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        before = _audit(root, "AUD-BEFORE", completed_at="2026-09-07T13:00:00-03:00", rule_result="PASS")
        after = _audit(
            root,
            "AUD-AFTER",
            completed_at="2026-09-07T15:00:00-03:00",
            rule_result="FAIL",
            canonical_a="https://example.test/b",
            title_a="Produto A novo",
        )
        with CentralPlatformStore(root / ".searchgeo" / "platform.db") as store:
            before_record, _ = index_audit_workspace(store, before)
            after_record, _ = index_audit_workspace(store, after)
            hierarchy = store.hierarchy_for_property(before_record.property_id)
            milestone = store.add_milestone(
                project_id=str(hierarchy["project_id"]),
                property_id=before_record.property_id,
                environment_id=before_record.environment_id,
                kind="DEPLOYMENT",
                occurred_at="2026-09-07T14:00:00-03:00",
                title="Release 3.12",
                release="3.12.0",
                commit_sha="abc123",
            )
            pair = resolve_deployment_pair(store, milestone)
            assert pair.baseline_audit_id == before_record.audit_id
            assert pair.current_audit_id == after_record.audit_id
            assert pair.comparable is True
            result, gate = compare_deployment_pair(store, pair)
            assert any(event.rule_id == "BR-GEO-011" and event.status == "REGRESSED" for event in result.events)
            assert gate.passed is False
            report, manifest = write_deployment_report(store, pair, result, gate, root / "deploy-report")
            assert report.is_file()
            assert manifest.is_file()
            html = report.read_text(encoding="utf-8")
            assert "Deployment Impact" in html
            assert "Release gate" in html
            assert "href='deployments.html'" not in html
            platform = write_platform_site(store, root / "platform-report")
            assert platform.is_file()
            platform_html = platform.read_text(encoding="utf-8")
            assert "Portfólio Search & AI Readiness" in platform_html
            assert "AUDs recentes" in platform_html


def test_alert_status_defaults_do_not_leak_when_user_overrides() -> None:
    parser = build_parser()
    base = [
        "alert", "add",
        "--project", "PRJ-1",
        "--property", "PTY-1",
        "--environment", "ENV-1",
        "--name", "Alert",
    ]
    default_args = parser.parse_args(base)
    assert default_args.status is None
    explicit_args = parser.parse_args(base + ["--status", "CHANGED", "--status", "IMPROVED"])
    assert explicit_args.status == ["CHANGED", "IMPROVED"]


def test_golden_baseline_override_and_page_compare() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        golden = _audit(root, "AUD-GOLD", completed_at="2026-09-05T10:00:00-03:00")
        before = _audit(root, "AUD-BEFORE", completed_at="2026-09-07T10:00:00-03:00")
        after = _audit(root, "AUD-AFTER", completed_at="2026-09-07T16:00:00-03:00", title_a="Título alterado")
        with CentralPlatformStore(root / ".searchgeo" / "platform.db") as store:
            gold_record, _ = index_audit_workspace(store, golden)
            before_record, _ = index_audit_workspace(store, before)
            after_record, _ = index_audit_workspace(store, after)
            hierarchy = store.hierarchy_for_property(before_record.property_id)
            store.set_golden_baseline(before_record.property_id, before_record.environment_id, gold_record.audit_id)
            milestone = store.add_milestone(
                project_id=str(hierarchy["project_id"]),
                property_id=before_record.property_id,
                environment_id=before_record.environment_id,
                kind="DEPLOYMENT",
                occurred_at="2026-09-07T12:00:00-03:00",
                title="Release",
            )
            pair = resolve_deployment_pair(store, milestone, baseline_mode="GOLDEN")
            assert pair.baseline_audit_id == gold_record.audit_id
            assert pair.current_audit_id == after_record.audit_id
        comparison = compare_pages(
            before,
            after,
            baseline_url="https://example.test/a",
        )
        assert any(change.label == "Title" and change.status == "CHANGED" for change in comparison.changes)
        page_report = write_page_compare_report(comparison, root / "page.html")
        assert "Título alterado" in page_report.read_text(encoding="utf-8")


def test_external_imports_keep_outcomes_outside_audit_db() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = _audit(root, "AUD-EXT", completed_at="2026-09-07T10:00:00-03:00")
        ga4 = root / "ga4.csv"
        ga4.write_text(
            "date,pagePathPlusQueryString,sessions,totalRevenue\n20260907,/a,10,125.50\n",
            encoding="utf-8",
        )
        access = root / "access.log"
        access.write_text(
            '203.0.113.1 - - [07/Sep/2026:10:10:00 -0300] "GET /a HTTP/1.1" 200 1234 "-" "GPTBot/1.0"\n',
            encoding="utf-8",
        )
        with CentralPlatformStore(root / ".searchgeo" / "platform.db") as store:
            record, _ = index_audit_workspace(store, workspace)
            ga4_dataset = import_ga4_csv(
                store,
                property_id=record.property_id,
                environment_id=record.environment_id,
                path=ga4,
            )
            log_dataset = import_combined_access_log(
                store,
                property_id=record.property_id,
                environment_id=record.environment_id,
                path=access,
            )
            assert ga4_dataset.row_count == 1
            assert log_dataset.row_count == 1
            log_record = store.external_records(log_dataset.dataset_id)[0]
            assert log_record["dimensions"]["ai_crawler"] == "OpenAI training crawler"
        connection = sqlite3.connect(workspace / "audit.db")
        try:
            table_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()
        assert "external_datasets" not in table_names
        assert classify_ai_crawler("Mozilla OAI-SearchBot") == "OpenAI Search crawler"


def test_scheduler_next_run_is_cross_platform_and_does_not_require_docker() -> None:
    schedule = Schedule(
        schedule_id="SCH-1",
        project_id="PRJ-1",
        property_id="PTY-1",
        environment_id="ENV-1",
        name="Daily",
        kind="DAILY",
        command_argv=("audit", "https://example.test"),
        enabled=True,
        created_at="2026-09-07T00:00:00-03:00",
        daily_time="08:30",
    )
    next_run = compute_next_run(schedule, after=datetime.fromisoformat("2026-09-07T09:00:00-03:00"))
    assert next_run.startswith("2026-09-08T08:30:00")
