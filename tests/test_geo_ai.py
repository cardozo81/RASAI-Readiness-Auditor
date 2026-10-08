"""GEO AI must be explicit, canonical-provider-owned and idempotent."""
from __future__ import annotations

from contextlib import closing

import sqlite3
import tempfile
import unittest
from pathlib import Path

from rasai.geo_ai import execute_geo_ai
from rasai.search_intelligence.competitive_ai import (
    CompetitiveAiAssessment, CompetitiveAiCategory, CompetitiveAiOpportunity,
    CompetitiveAiPriority, CompetitiveAiResult, CompetitiveAiState,
)


class FakeCanonicalConsumer:
    calls = 0

    def analyze(self, evidence_input):
        self.calls += 1
        first = next(iter(evidence_input.allowed_evidence_ids))
        self.last_ids = evidence_input.allowed_evidence_ids
        assessment = CompetitiveAiAssessment(
            query_intent="Evaluation",
            ymyl_assessment="Review",
            summary="Evidence-bounded opportunity",
            opportunities=(
                CompetitiveAiOpportunity(
                    category=CompetitiveAiCategory.SEO_AEO_GEO,
                    priority=CompetitiveAiPriority.MEDIUM,
                    title="Clarify coverage",
                    recommendation="Review factual offer distinctions",
                    rationale="Observed external snippet",
                    evidence_ids=(first,),
                    confidence=0.6,
                    causality_note="No ranking causality",
                ),
            ),
            provider="FAKE_CANONICAL",
            model="fixture",
        )
        return CompetitiveAiResult(CompetitiveAiState.AVAILABLE, assessment=assessment)


class GeoAiConsumerTests(unittest.TestCase):
    def _db(self, path):
        with closing(sqlite3.connect(path)) as con, con:
            con.executescript("""
                CREATE TABLE audits (audit_id TEXT PRIMARY KEY);
                CREATE TABLE perplexity_search_runs (
                    run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                    search_type TEXT, status TEXT, started_at TEXT
                );
                CREATE TABLE perplexity_search_sources (
                    run_id TEXT, position INTEGER, url TEXT, title TEXT, snippet TEXT
                );
            """)
            con.execute("INSERT INTO audits VALUES ('AUD-1')")
            con.execute(
                "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
                ("PXS-1", "AUD-1", '["seguro de vida"]', "web", "SUCCESS", "2026-10-07")
            )
            con.execute(
                "INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?)",
                ("PXS-1", 1, "https://external.example/policy", "Offer", "Published terms")
            )

    def test_explicit_canonical_consumer_only_and_replay_no_new_calls(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            self._db(db)
            adapter = FakeCanonicalConsumer()
            factory = lambda selection: adapter
            first = execute_geo_ai(db, "AUD-1", provider_selection="auto", provider_factory=factory)
            self.assertEqual(first, "AVAILABLE")
            self.assertEqual(len(adapter.last_ids), 1)
            second = execute_geo_ai(db, "AUD-1", provider_selection="auto", provider_factory=factory)
            self.assertEqual(second, "AVAILABLE")
            self.assertEqual(adapter.calls, 1)
            with closing(sqlite3.connect(db)) as con, con:
                self.assertEqual(
                    con.execute("SELECT count(*) FROM geo_ai_interpretations").fetchone()[0], 1
                )
                self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_no_credential_selection_creates_no_calls_or_tables(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            self._db(db)
            self.assertEqual(execute_geo_ai(db, "AUD-1", provider_selection="none"), "NOT_CONFIGURED")
            with closing(sqlite3.connect(db)) as con, con:
                self.assertFalse(con.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='geo_ai_interpretations'"
                ).fetchone())


if __name__ == "__main__":
    unittest.main()
