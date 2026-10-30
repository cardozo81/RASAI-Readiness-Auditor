"""Focused no-network test of sealed-AUD AI/Search replay (#682)."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import json
import tempfile
import unittest
from unittest.mock import patch

from rasai.geo_post_aud_ai_reanalysis import (
    inspect_completed_audit, publish_local_reanalysis,
)


class CompletedAuditIntegrationReplayTests(unittest.TestCase):
    def test_preview_and_persisted_replay_preserve_source_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            aud = Path(temp) / "AUD-1"
            aud.mkdir()
            database = aud / "audit.db"
            with closing(sqlite3.connect(database)) as con, con:
                con.execute("CREATE TABLE audits(audit_id TEXT)")
                con.execute("INSERT INTO audits VALUES ('AUD-1')")
                con.execute(
                    "CREATE TABLE perplexity_search_runs("
                    "run_id TEXT, audit_id TEXT, query_json TEXT, "
                    "status TEXT, started_at TEXT)"
                )
                con.execute(
                    "CREATE TABLE perplexity_search_sources("
                    "run_id TEXT, url TEXT)"
                )
                con.execute(
                    "INSERT INTO perplexity_search_runs VALUES "
                    "('px1','AUD-1','[\"consultoria de ti\"]','SUCCESS',"
                    "'2026-10-29T22:40:00+00:00')"
                )
                con.execute(
                    "INSERT INTO perplexity_search_sources VALUES "
                    "('px1','https://example.org')"
                )
                con.execute(
                    "CREATE TABLE geo_ai_interpretations("
                    "audit_id TEXT,perplexity_run_id TEXT,created_at TEXT,"
                    "state TEXT,summary TEXT,provider TEXT,model TEXT,"
                    "prompt_id TEXT,prompt_version TEXT,opportunities_json TEXT)"
                )
                stored = json.dumps([{
                    "recommendation": "Ajustar arquitetura informacional",
                    "confidence": 0.91,
                    "evidence_ids": ["PX:px1:0:abc"],
                }])
                con.execute(
                    "INSERT INTO geo_ai_interpretations VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ("AUD-1", "px1", "2026-10-29T22:45:00+00:00",
                     "AVAILABLE", "Síntese pré-existente", "openai", "modelo",
                     "prompt", "v1", stored),
                )
            before = database.read_bytes()
            # Canonical package seal is tested separately. The fixture tests
            # only this module's read-only behavior and sidecar isolation.
            with patch(
                "rasai.geo_post_audit_complement._sealed_audit",
                return_value=("dbhash", "manifesthash", "statehash"),
            ):
                preview = inspect_completed_audit(aud)
                self.assertEqual(preview["provider_calls"], 0)
                self.assertEqual(len(preview["saved_local_interpretations"]), 1)
                self.assertEqual(
                    preview["saved_local_interpretations"][0]["opportunities"][0]["confidence_percent"], 91.0,
                )
                self.assertTrue(any(
                    op["operation"] == "GEO_SAVED_INTERPRETATION_REPLAY"
                    and op["state"] == "ELIGIBLE" for op in preview["operations"]
                ))
                self.assertEqual(preview["operations"][1]["state"], "ELIGIBLE")
                self.assertTrue(any(x["operation"] == "NEW_CANONICAL_AI_INFERENCE"
                                    and x["execution"] == "NOT_EXECUTED"
                                    for x in preview["operations"]))
                first = publish_local_reanalysis(aud)
                second = publish_local_reanalysis(aud)
            self.assertEqual(first["state"], "PUBLISHED")
            self.assertEqual(second["state"], "ALREADY_RECORDED")
            self.assertEqual(before, database.read_bytes())
            self.assertTrue((Path(first["package"]) / "manifest.json").is_file())
            self.assertIn("Síntese pré-existente", (
                Path(first["package"]) / "reanalysis.html"
            ).read_text(encoding="utf-8"))

    def test_latest_failed_search_does_not_promote_old_success(self):
        with tempfile.TemporaryDirectory() as temp:
            aud = Path(temp) / "AUD-RECENT"
            aud.mkdir()
            with closing(sqlite3.connect(aud / "audit.db")) as con, con:
                con.execute("CREATE TABLE audits(audit_id TEXT)")
                con.execute("INSERT INTO audits VALUES ('AUD-RECENT')")
                con.execute("CREATE TABLE perplexity_search_runs("
                            "run_id TEXT,audit_id TEXT,query_json TEXT,"
                            "status TEXT,started_at TEXT)")
                con.execute("CREATE TABLE perplexity_search_sources(run_id TEXT,url TEXT)")
                con.executemany(
                    "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?)",
                    [
                        ("old", "AUD-RECENT", '["term"]', "SUCCESS",
                         "2026-10-29T22:00:00+00:00"),
                        ("new", "AUD-RECENT", '["term"]', "TIMEOUT",
                         "2026-10-29T23:00:00+00:00"),
                    ],
                )
                con.execute("INSERT INTO perplexity_search_sources VALUES "
                            "('old','https://source.example')")
            with patch(
                "rasai.geo_post_audit_complement._sealed_audit",
                return_value=("dbhash", "manifesthash", "statehash"),
            ):
                report = inspect_completed_audit(aud)
            self.assertEqual(report["current_verified_run_ids"], ["new"])
            self.assertEqual(report["operations"][1]["state"], "NOT_ELIGIBLE")
            self.assertFalse(report["saved_local_interpretations"])

    def test_limited_completed_audit_is_eligible_only_for_consultative_mode(self):
        from types import SimpleNamespace
        from rasai.geo_post_audit_complement import _sealed_audit
        with tempfile.TemporaryDirectory() as temp:
            aud = Path(temp) / "AUD-LIMITED"
            aud.mkdir()
            db = aud / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.execute("CREATE TABLE audits("
                            "audit_id TEXT,status TEXT,completion_status TEXT)")
                con.execute("INSERT INTO audits VALUES "
                            "('AUD-LIMITED','COMPLETED','COMPLETE_WITH_LIMITATIONS')")
            catalog = aud / "report-catalog"
            catalog.mkdir()
            (catalog / "manifest.json").write_text("{}", encoding="utf-8")
            original = db.read_bytes()
            workspace = SimpleNamespace(root=aud, database=db)
            with (
                patch("rasai.catalog_report_site.verify_catalog_report_package",
                      return_value=(True, [])),
                patch("rasai.catalog_report_site.catalog_report_is_fresh",
                      return_value=True),
                patch("rasai.catalog_report_site._source_fingerprint",
                      return_value="sealed-state"),
            ):
                with self.assertRaisesRegex(ValueError, "must be COMPLETE"):
                    _sealed_audit(workspace, "AUD-LIMITED")
                preview = inspect_completed_audit(aud)
            self.assertEqual(preview["audit_id"], "AUD-LIMITED")
            self.assertEqual(preview["provider_calls"], 0)
            self.assertEqual(preview["saved_local_interpretations"], [])
            self.assertEqual(original, db.read_bytes())

    def test_missing_sources_do_not_become_eligible(self):
        with tempfile.TemporaryDirectory() as temp:
            aud = Path(temp) / "AUD-2"
            aud.mkdir()
            with closing(sqlite3.connect(aud / "audit.db")) as con, con:
                con.execute("CREATE TABLE audits(audit_id TEXT)")
            with patch(
                "rasai.geo_post_audit_complement._sealed_audit",
                return_value=("dbhash", "manifesthash", "statehash"),
            ):
                result = inspect_completed_audit(aud)
            self.assertEqual(result["operations"][1]["state"], "NOT_ELIGIBLE")
            self.assertEqual(result["provider_calls"], 0)


if __name__ == "__main__":
    unittest.main()
