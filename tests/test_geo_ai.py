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

    def test_invalid_evidence_ids_are_quarantined_without_publishing_summary(self):
        from dataclasses import replace

        class InvalidEvidenceConsumer(FakeCanonicalConsumer):
            def analyze(self, evidence_input):
                result = super().analyze(evidence_input)
                assert result.assessment is not None
                original = result.assessment.opportunities[0]
                bad = replace(original, evidence_ids=("UNOBSERVED-ID",))
                return replace(
                    result,
                    assessment=replace(result.assessment, opportunities=(bad,)),
                )

        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            self._db(db)
            consumer = InvalidEvidenceConsumer()
            factory = lambda _: consumer
            state = execute_geo_ai(
                db, "AUD-1", provider_selection="auto",
                provider_factory=factory,
            )
            self.assertEqual(state, "UNAVAILABLE")
            with closing(sqlite3.connect(db)) as con, con:
                row = con.execute(
                    "SELECT state, summary, opportunities_json, error_reason "
                    "FROM geo_ai_interpretations"
                ).fetchone()
                self.assertEqual(row[0], "UNAVAILABLE")
                self.assertIsNone(row[1])
                self.assertEqual(row[2], "[]")
                self.assertEqual(row[3], "GEO_AI_INVALID_EVIDENCE_REFERENCES")
            self.assertEqual(
                execute_geo_ai(db, "AUD-1", provider_selection="auto", provider_factory=factory),
                "UNAVAILABLE",
            )
            self.assertEqual(consumer.calls, 1)

    def test_failed_search_abstains_without_ai_call(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            self._db(db)
            with closing(sqlite3.connect(db)) as con, con:
                con.execute(
                    "UPDATE perplexity_search_runs SET status='TIMEOUT_ERROR' "
                    "WHERE run_id='PXS-1'"
                )
            consumer = FakeCanonicalConsumer()
            self.assertEqual(
                execute_geo_ai(db, "AUD-1", provider_selection="auto",
                               provider_factory=lambda _: consumer),
                "NOT_ELIGIBLE",
            )
            self.assertEqual(consumer.calls, 0)

    def test_unexpected_canonical_exception_is_terminal_and_never_retried(self):
        class BrokenConsumer:
            calls = 0

            def analyze(self, _evidence):
                self.calls += 1
                raise TimeoutError("possible billed AI timeout: SECRET_DO_NOT_LOG")

        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            self._db(db)
            consumer = BrokenConsumer()
            factory = lambda _: consumer
            self.assertEqual(
                execute_geo_ai(db, "AUD-1", provider_selection="auto",
                               provider_factory=factory),
                "UNAVAILABLE",
            )
            self.assertEqual(
                execute_geo_ai(db, "AUD-1", provider_selection="auto",
                               provider_factory=factory),
                "UNAVAILABLE",
            )
            self.assertEqual(consumer.calls, 1)
            with closing(sqlite3.connect(db)) as con:
                state, summary, reason = con.execute(
                    "SELECT state, summary, error_reason FROM geo_ai_interpretations"
                ).fetchone()
                self.assertEqual(state, "UNAVAILABLE")
                self.assertIsNone(summary)
                self.assertEqual(reason, "GEO_AI_CANONICAL_EXECUTION_ERROR")
                self.assertNotIn("SECRET_DO_NOT_LOG", reason)
                self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_canonical_factory_failure_never_falls_back_to_private_provider(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            self._db(db)

            def invalid_factory(_selection):
                raise RuntimeError("missing credential")

            self.assertEqual(
                execute_geo_ai(db, "AUD-1", provider_selection="auto",
                               provider_factory=invalid_factory),
                "CANONICAL_AI_UNAVAILABLE",
            )
            with closing(sqlite3.connect(db)) as con:
                self.assertEqual(
                    con.execute("SELECT count(*) FROM geo_ai_interpretations").fetchone()[0], 0
                )

    def test_multiquery_never_infers_evidence_assignment(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            self._db(db)
            with closing(sqlite3.connect(db)) as con, con:
                con.execute(
                    "UPDATE perplexity_search_runs SET query_json='[\"one\",\"two\"]' "
                    "WHERE run_id='PXS-1'"
                )
            consumer = FakeCanonicalConsumer()
            self.assertEqual(
                execute_geo_ai(db, "AUD-1", provider_selection="auto",
                               provider_factory=lambda _: consumer),
                "NOT_ELIGIBLE",
            )
            self.assertEqual(consumer.calls, 0)

    def test_empty_available_assessment_does_not_fake_success(self):
        class EmptyConsumer:
            def analyze(self, _evidence):
                return CompetitiveAiResult(CompetitiveAiState.AVAILABLE, assessment=None)

        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            self._db(db)
            state = execute_geo_ai(
                db, "AUD-1", provider_selection="auto",
                provider_factory=lambda _: EmptyConsumer(),
            )
            self.assertEqual(state, "UNAVAILABLE")
            with closing(sqlite3.connect(db)) as con:
                row = con.execute(
                    "SELECT summary, opportunities_json, error_reason "
                    "FROM geo_ai_interpretations"
                ).fetchone()
                self.assertIsNone(row[0])
                self.assertEqual(row[1], "[]")
                self.assertEqual(row[2], "GEO_AI_EMPTY_CANONICAL_ASSESSMENT")

    def test_unavailable_provider_never_publishes_incidental_assessment(self):
        class InvalidStateConsumer(FakeCanonicalConsumer):
            def analyze(self, evidence_input):
                result = super().analyze(evidence_input)
                return CompetitiveAiResult(
                    CompetitiveAiState.UNAVAILABLE,
                    assessment=result.assessment,
                    reason="FAKE_UNAVAILABLE",
                )

        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            self._db(db)
            state = execute_geo_ai(
                db, "AUD-1", provider_selection="auto",
                provider_factory=lambda _: InvalidStateConsumer(),
            )
            self.assertEqual(state, "UNAVAILABLE")
            with closing(sqlite3.connect(db)) as con:
                row = con.execute(
                    "SELECT summary, opportunities_json, error_reason FROM geo_ai_interpretations"
                ).fetchone()
                self.assertIsNone(row[0])
                self.assertEqual(row[1], "[]")
                self.assertEqual(row[2], "FAKE_UNAVAILABLE")

    def test_default_factory_must_create_canonical_provider_not_fake(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            self._db(db)
            fake = FakeCanonicalConsumer()
            # This mock occupies the real builder's module. Production must
            # still validate the returned provider type before invoking AI.
            with patch(
                "rasai.search_intelligence.competitive_ai.build_competitive_ai_provider",
                return_value=fake,
            ):
                status = execute_geo_ai(db, "AUD-1", provider_selection="auto")
            self.assertEqual(status, "CANONICAL_AI_NOT_INSTALLED")
            self.assertEqual(fake.calls, 0)
            with closing(sqlite3.connect(db)) as con:
                self.assertEqual(
                    con.execute("SELECT count(*) FROM geo_ai_interpretations").fetchone()[0],
                    0,
                )

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
