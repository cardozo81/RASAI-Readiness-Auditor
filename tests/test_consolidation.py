from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from searchgeo.consolidation.index import ConsolidationIndex
from searchgeo.consolidation.service import build_data, generate, normalize_filter


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_audit(
    root: Path,
    audit_id: str,
    *,
    when: str,
    urls: tuple[str, ...] = ("https://example.com/a",),
    score: float = 80.0,
    scoring_version: str = "1",
    device: str = "MOBILE",
) -> Path:
    workspace = root / audit_id
    workspace.mkdir(parents=True)
    db = workspace / "audit.db"
    connection = sqlite3.connect(db)
    try:
        connection.executescript(
            """
            CREATE TABLE audits(
                audit_id TEXT PRIMARY KEY, project_name TEXT, status TEXT, completion_status TEXT,
                created_at TEXT, started_at TEXT, completed_at TEXT, auditor_version TEXT,
                ruleset_version TEXT
            );
            CREATE TABLE audit_targets(audit_id TEXT, normalized_origin TEXT);
            CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            CREATE TABLE page_snapshots(snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT);
            CREATE TABLE scores(
                audit_id TEXT,device TEXT,dimension TEXT,value REAL,coverage REAL,confidence TEXT,
                consolidation_status TEXT,scoring_version TEXT,calculated_at TEXT
            );
            CREATE TABLE web_performance_observations(
                audit_id TEXT,url TEXT,device TEXT,captured_at TEXT,status TEXT,strategy TEXT,
                performance_score REAL,accessibility_score REAL,best_practices_score REAL,seo_score REAL,
                fcp_lab_ms REAL,speed_index_lab_ms REAL,lcp_lab_ms REAL,tbt_lab_ms REAL,cls_lab REAL,
                field_source TEXT,field_scope TEXT,lcp_p75_ms REAL,inp_p75_ms REAL,cls_p75 REAL,cwv_assessment TEXT
            );
            CREATE TABLE synthetic_apdex_summaries(
                audit_id TEXT,url TEXT,device TEXT,calculated_at TEXT,profile_id TEXT,threshold_seconds REAL,
                valid_samples INTEGER,invalid_samples INTEGER,satisfied_count INTEGER,tolerating_count INTEGER,
                frustrated_count INTEGER,apdex_score REAL,small_group INTEGER,final_group INTEGER,
                median_ms REAL,p75_ms REAL,p90_ms REAL,p95_ms REAL,p99_ms REAL,trend_percent REAL
            );
            CREATE TABLE findings(
                audit_id TEXT,device TEXT,severity TEXT,category TEXT,page_id TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO audits VALUES (?,?,?,?,?,?,?,?,?)",
            (audit_id, "Fixture", "COMPLETED", "COMPLETE", when, when, when, "0.1.0", "rules-v1"),
        )
        connection.execute("INSERT INTO audit_targets VALUES (?,?)", (audit_id, "https://example.com"))
        for pos, url in enumerate(urls, 1):
            page_id = f"{audit_id}-P{pos}"
            connection.execute("INSERT INTO pages VALUES (?,?,?)", (page_id, audit_id, url))
            connection.execute("INSERT INTO page_snapshots VALUES (?,?,?)", (f"{audit_id}-S{pos}", page_id, device))
            connection.execute(
                "INSERT INTO web_performance_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    audit_id, url, device, when, "SUCCESS", "mobile", 0.90 + pos / 1000,
                    0.88, 0.91, 0.92, 900.0, 1400.0, 2100.0, 120.0, 0.05,
                    "PAGESPEED", "URL", 2300.0, 180.0, 0.06, "GOOD",
                ),
            )
            connection.execute(
                "INSERT INTO synthetic_apdex_summaries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    audit_id, url, device, when, "SEARCHGEO_MOBILE_TEST", 2.0,
                    100, 0, 90, 8, 2, 0.94, 0, 1,
                    900.0, 1200.0, 1500.0, 1900.0, 2400.0, 2.0,
                ),
            )
            connection.execute("INSERT INTO findings VALUES (?,?,?,?,?)", (audit_id, device, "MEDIUM", "TEST", page_id))
        connection.execute(
            "INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?)",
            (audit_id, device, "OVERALL_READINESS", score, 1.0, "HIGH", "COMPLETE", scoring_version, when),
        )
        connection.commit()
    finally:
        connection.close()
    return db


class ConsolidationTests(unittest.TestCase):
    def test_generation_is_read_only_and_deduplicates_identical_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db1 = _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00", score=70.0)
            db2 = _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00", score=80.0)
            before = {db1: _digest(db1), db2: _digest(db2)}
            filters = normalize_filter(domains=("example.com",), devices=("MOBILE",))
            first = generate(root, filters)
            second = generate(root, filters)
            self.assertFalse(first.reused)
            self.assertTrue(second.reused)
            self.assertEqual(first.report_path, second.report_path)
            self.assertTrue(first.report_path.is_file())
            self.assertTrue(first.manifest_path.is_file())
            self.assertEqual(before, {db1: _digest(db1), db2: _digest(db2)})
            manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["summary"]["audits"], 2)
            self.assertEqual(manifest["filters"]["domains"], ["example.com"])

    def test_new_matching_audit_invalidates_report_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00", score=70.0)
            filters = normalize_filter(domains=("example.com",))
            first = generate(root, filters)
            _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00", score=80.0)
            second = generate(root, filters)
            self.assertFalse(second.reused)
            self.assertNotEqual(first.request_fingerprint, second.request_fingerprint)
            self.assertNotEqual(first.report_path, second.report_path)

    def test_url_filter_never_reuses_audit_level_score_for_partial_universe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(
                root,
                "AUD-001",
                when="2026-09-01T10:00:00-03:00",
                urls=("https://example.com/a", "https://example.com/b"),
                score=77.0,
            )
            index = ConsolidationIndex(root)
            index.refresh()
            filters = normalize_filter(urls=("https://example.com/a",), devices=("MOBILE",))
            points = index.load_points(filters)
            self.assertEqual(points["scores"], ())
            self.assertEqual(len(points["performance"]), 1)
            self.assertEqual(points["performance"][0]["url"], "https://example.com/a")
            data = build_data(index, filters)
            self.assertFalse(data.scores)
            self.assertTrue(any("pontuações calculadas" in item for item in data.limitations))

    def test_mixed_scoring_versions_are_not_averaged_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00", score=50.0, scoring_version="1")
            _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00", score=90.0, scoring_version="2")
            index = ConsolidationIndex(root)
            index.refresh()
            data = build_data(index, normalize_filter(devices=("MOBILE",)))
            overall = next(item for item in data.scores if item.dimension == "OVERALL_READINESS")
            self.assertEqual(overall.scoring_versions, ("1", "2"))
            self.assertEqual(overall.statistics.count, 1)
            self.assertEqual(overall.statistics.current, 90.0)
            self.assertIsNotNone(overall.limitation)

    def test_invalid_audit_is_isolated_during_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-OK", when="2026-09-01T10:00:00-03:00")
            broken = root / "AUD-BROKEN"
            broken.mkdir()
            (broken / "audit.db").write_bytes(b"not sqlite")
            refresh = ConsolidationIndex(root).refresh()
            self.assertEqual(refresh.discovered, 2)
            self.assertEqual(refresh.indexed, 1)
            self.assertEqual(len(refresh.issues), 1)

    def test_date_filter_is_inclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_audit(root, "AUD-001", when="2026-08-01T10:00:00-03:00")
            _make_audit(root, "AUD-002", when="2026-09-01T10:00:00-03:00")
            index = ConsolidationIndex(root)
            index.refresh()
            rows = index.candidate_audits(normalize_filter(date_from=date(2026, 9, 1), date_to=date(2026, 9, 1)))
            self.assertEqual([row["audit_id"] for row in rows], ["AUD-002"])


if __name__ == "__main__":
    unittest.main()
