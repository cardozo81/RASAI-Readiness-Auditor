from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.platform.central_store import CentralPlatformStore
from rasai.platform.store import default_platform_database
from rasai.search_intelligence.monitoring import (
    SQLiteSearchMonitoringRepository,
    SearchMonitorChange,
    SearchMonitorRun,
    SearchMonitorSnapshot,
    detect_changes,
    execute_registered_query,
    new_query,
)
from rasai.search_intelligence.monitoring_reporting import write_search_monitoring_report


class SearchMonitoringTests(unittest.TestCase):
    def _scope(self, root: Path):
        database = default_platform_database(root)
        with CentralPlatformStore(database) as store:
            _org, _workspace, project, prop, environment = store.ensure_local_hierarchy(
                project_name="Search Monitoring",
                origin="https://client.example",
            )
        return database, project, prop, environment

    def _query(self, project, prop, environment, **overrides):
        values = dict(
            project_id=project.project_id,
            property_id=prop.property_id,
            environment_id=environment.environment_id,
            query="seguro auto",
            domain_of_interest="client.example",
            engine="google",
            country="BR",
            language="pt-BR",
            device="desktop",
            requested_depth=10,
            mode="fixture",
            provider="serpapi",
            competitive=True,
            compare_content=False,
            ai_competitive=False,
        )
        values.update(overrides)
        return new_query(**values)

    def test_registry_is_scoped_and_rejects_duplicate_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database, project, prop, environment = self._scope(root)
            with SQLiteSearchMonitoringRepository(database) as repository:
                item = repository.register_query(self._query(project, prop, environment))
                self.assertEqual(item.query_id, repository.get_query(item.query_id).query_id)
                self.assertEqual(1, len(repository.list_queries()))
                with self.assertRaises(ValueError):
                    repository.register_query(self._query(project, prop, environment))

    def test_change_detection_preserves_depth_semantics_and_competitor_changes(self):
        previous_snapshot = SearchMonitorSnapshot(
            observation_id="OBS-1", collected_at="2026-09-01T00:00:00+00:00",
            provider="fixture", data_mode="FIXTURE", observation_status="OBSERVED",
            domain_status="FOUND", customer_position=8, result_count=10,
            competitor_domains_ahead=("a.example", "b.example"),
            raw_evidence_ref=None, raw_evidence_sha256=None, comparison_status="CONSOLIDATED",
            gap_codes=("GAP-A",), query_body_coverage=.5, query_title_coverage=.5,
            query_heading_coverage=.5, word_count=500, jsonld_types=("Article",),
            ai_state=None, ai_provider=None, ai_model=None, ai_opportunity_count=0,
        )
        previous = SearchMonitorRun(
            monitor_run_id="RUN-1", query_id="Q-1", started_at="x", completed_at="x",
            status="SUCCESS", snapshot=previous_snapshot, changes=(), comparable_to_previous=None,
            comparison_note=None, serp_http_requests=0, content_http_requests=0,
            ai_provider_calls=0, manifest_ref=None, manifest_sha256=None,
        )
        current = SearchMonitorSnapshot(
            observation_id="OBS-2", collected_at="2026-09-02T00:00:00+00:00",
            provider="fixture", data_mode="FIXTURE", observation_status="OBSERVED",
            domain_status="FOUND", customer_position=4, result_count=10,
            competitor_domains_ahead=("a.example", "c.example"),
            raw_evidence_ref=None, raw_evidence_sha256=None, comparison_status="CONSOLIDATED",
            gap_codes=(), query_body_coverage=.8, query_title_coverage=.5,
            query_heading_coverage=.5, word_count=650, jsonld_types=("Article", "FAQPage"),
            ai_state=None, ai_provider=None, ai_model=None, ai_opportunity_count=0,
        )
        changes, comparable, note = detect_changes(previous, current)
        statuses = {item.status for item in changes}
        self.assertTrue(comparable)
        self.assertIsNone(note)
        self.assertIn("POSITION_IMPROVED", statuses)
        self.assertIn("COMPETITOR_AHEAD_ADDED", statuses)
        self.assertIn("COMPETITOR_AHEAD_REMOVED", statuses)
        self.assertIn("DETERMINISTIC_GAP_RESOLVED", statuses)
        self.assertIn("CONTENT_SIGNAL_CHANGED", statuses)
        self.assertIn("CONTENT_VOLUME_CHANGED", statuses)
        self.assertIn("STRUCTURED_DATA_CHANGED", statuses)

    def test_fixture_execution_persists_control_plane_run_and_evidence_not_audit_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database, project, prop, environment = self._scope(root)
            fixture1 = root / "serp1.json"
            fixture1.write_text(json.dumps({
                "fixture_version": "SERP-FIXTURE-001",
                "query": "seguro auto",
                "results": [
                    {"position": 1, "url": "https://leader.example/a", "title": "Leader"},
                    {"position": 5, "url": "https://client.example/auto", "title": "Client"},
                ],
            }), encoding="utf-8")
            fixture2 = root / "serp2.json"
            fixture2.write_text(json.dumps({
                "fixture_version": "SERP-FIXTURE-001",
                "query": "seguro auto",
                "results": [
                    {"position": 1, "url": "https://leader.example/a", "title": "Leader"},
                    {"position": 3, "url": "https://client.example/auto", "title": "Client"},
                ],
            }), encoding="utf-8")

            with SQLiteSearchMonitoringRepository(database) as repository:
                query = repository.register_query(self._query(project, prop, environment))
                first = execute_registered_query(repository, query, audits_root=root, fixture_path=fixture1)
                second = execute_registered_query(repository, query, audits_root=root, fixture_path=fixture2)
                self.assertEqual("SUCCESS", first.status)
                self.assertEqual(5, first.snapshot.customer_position)
                self.assertEqual(3, second.snapshot.customer_position)
                self.assertIn("POSITION_IMPROVED", {item.status for item in second.changes})
                self.assertEqual(2, len(repository.list_runs(query.query_id)))
                self.assertTrue((root / ".rasai" / "search-monitoring" / first.manifest_ref).is_file())
                self.assertTrue(first.snapshot.raw_evidence_ref)
                report = write_search_monitoring_report(repository, root / "platform-report")
                html = report.read_text(encoding="utf-8")
                self.assertIn("Search Intelligence - monitoramento recorrente", html)
                self.assertIn("seguro auto", html)
                self.assertIn("POSITION_IMPROVED", html)

            self.assertFalse(any(root.glob("AUD-*/audit.db")))
            with sqlite3.connect(database) as connection:
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM search_monitor_queries").fetchone()[0])
                self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM search_monitor_runs").fetchone()[0])

    def test_provider_change_is_not_comparable(self):
        before = SearchMonitorSnapshot(
            observation_id="1", collected_at="x", provider="fixture", data_mode="FIXTURE",
            observation_status="OBSERVED", domain_status="FOUND", customer_position=2,
            result_count=2, competitor_domains_ahead=(), raw_evidence_ref=None,
            raw_evidence_sha256=None, comparison_status=None, gap_codes=(),
            query_body_coverage=None, query_title_coverage=None, query_heading_coverage=None,
            word_count=None, jsonld_types=(), ai_state=None, ai_provider=None, ai_model=None,
            ai_opportunity_count=0,
        )
        prior = SearchMonitorRun(
            monitor_run_id="r", query_id="q", started_at="x", completed_at="x", status="SUCCESS",
            snapshot=before, changes=(SearchMonitorChange("BASELINE_ESTABLISHED", "x", None, None),),
            comparable_to_previous=None, comparison_note=None, serp_http_requests=0,
            content_http_requests=0, ai_provider_calls=0, manifest_ref=None, manifest_sha256=None,
        )
        current = SearchMonitorSnapshot(
            observation_id="2", collected_at="y", provider="serpapi", data_mode="OBSERVED_API",
            observation_status="OBSERVED", domain_status="FOUND", customer_position=1,
            result_count=2, competitor_domains_ahead=(), raw_evidence_ref=None,
            raw_evidence_sha256=None, comparison_status=None, gap_codes=(),
            query_body_coverage=None, query_title_coverage=None, query_heading_coverage=None,
            word_count=None, jsonld_types=(), ai_state=None, ai_provider=None, ai_model=None,
            ai_opportunity_count=0,
        )
        changes, comparable, note = detect_changes(prior, current)
        self.assertFalse(comparable)
        self.assertEqual("NOT_COMPARABLE", changes[0].status)
        self.assertIn("Provider", note)


if __name__ == "__main__":
    unittest.main()
