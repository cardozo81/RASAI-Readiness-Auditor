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


    def test_ineligible_geo_ai_request_is_readonly_with_no_derived_table(self):
        """No AI quota, materialization or schema mutation for failed search."""
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            self._db(db)
            with closing(sqlite3.connect(db)) as con, con:
                con.execute(
                    "UPDATE perplexity_search_runs SET status='AUTH_ERROR' "
                    "WHERE run_id='PXS-1'"
                )
            original = db.read_bytes()
            consumer = FakeCanonicalConsumer()
            returned = execute_geo_ai(
                db, "AUD-1", provider_selection="auto",
                provider_factory=lambda _: consumer,
            )
            self.assertEqual(returned, "NOT_ELIGIBLE")
            self.assertEqual(consumer.calls, 0)
            self.assertEqual(db.read_bytes(), original)
            with closing(sqlite3.connect(db)) as con:
                self.assertIsNone(con.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='geo_ai_interpretations'"
                ).fetchone())
                self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_missing_geo_source_tables_abstains_without_empty_ai_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "audit.db"
            with closing(sqlite3.connect(db)) as con, con:
                con.execute("CREATE TABLE audits (audit_id TEXT PRIMARY KEY)")
                con.execute("INSERT INTO audits VALUES ('AUD-1')")
            before = db.read_bytes()
            self.assertEqual(
                execute_geo_ai(db, "AUD-1", provider_selection="auto",
                               provider_factory=lambda _: self.fail("AI not eligible")),
                "NOT_ELIGIBLE",
            )
            self.assertEqual(db.read_bytes(), before)
            with closing(sqlite3.connect(db)) as con:
                self.assertIsNone(con.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='geo_ai_interpretations'"
                ).fetchone())


    def test_optional_geo_ai_never_creates_database_for_missing_file(self):
        with tempfile.TemporaryDirectory() as root:
            absent = Path(root) / "AUD-MISSING" / "audit.db"
            self.assertFalse(absent.exists())
            self.assertEqual(
                execute_geo_ai(
                    absent, "AUD-MISSING", provider_selection="auto",
                    provider_factory=lambda _: self.fail("no provider without source"),
                ),
                "NOT_ELIGIBLE",
            )
            self.assertFalse(absent.exists())


if __name__ == "__main__":
    unittest.main()


def test_geo_ai_denies_old_success_if_later_external_attempt_failed(tmp_path):
    db = tmp_path / "audit.db"
    GeoAiConsumerTests()._db(db)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE perplexity_search_runs SET started_at=? WHERE run_id='PXS-1'",
            ("2026-10-09T11:30:00+00:00",),
        )
        con.execute(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
            ("PXS-LATER-FAILED", "AUD-1", '["seguro de vida"]',
             "web", "AUTH_ERROR", "2026-10-09T09:00:00-03:00"),
        )
    before = db.read_bytes()
    result = execute_geo_ai(
        db, "AUD-1", provider_selection="auto",
        provider_factory=lambda _: (_ for _ in ()).throw(
            AssertionError("older success cannot trigger an AI call")
        ),
    )
    assert result == "NOT_ELIGIBLE"
    assert db.read_bytes() == before
    with sqlite3.connect(db) as con:
        assert con.execute(
            "SELECT name FROM sqlite_master WHERE name='geo_ai_interpretations'"
        ).fetchone() is None


def test_geo_ai_selects_actual_utc_latest_successful_source(tmp_path):
    db = tmp_path / "audit.db"
    GeoAiConsumerTests()._db(db)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE perplexity_search_runs SET started_at=? WHERE run_id='PXS-1'",
            ("2026-10-09T11:30:00+00:00",),
        )
        con.execute(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
            ("PXS-NEW", "AUD-1", '["seguro de vida"]',
             "web", "SUCCESS", "2026-10-09T09:00:00-03:00"),
        )
        con.execute(
            "INSERT INTO perplexity_search_sources VALUES (?,?,?,?,?)",
            ("PXS-NEW", 1, "https://new.example/offer", "New", "Observed"),
        )
    adapter = FakeCanonicalConsumer()
    assert execute_geo_ai(
        db, "AUD-1", provider_selection="auto",
        provider_factory=lambda _: adapter,
    ) == "AVAILABLE"
    assert adapter.calls == 1
    assert all(evidence_id.startswith("PX:PXS-NEW:") for evidence_id in adapter.last_ids)
    with sqlite3.connect(db) as con:
        assert con.execute(
            "SELECT perplexity_run_id FROM geo_ai_interpretations"
        ).fetchone()[0] == "PXS-NEW"


def test_geo_ai_abstains_on_unordered_or_tied_external_runs_without_ai_cost(
    tmp_path,
):
    db = tmp_path / "audit.db"
    GeoAiConsumerTests()._db(db)
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
            ("PXS-2", "AUD-1", '["seguro de vida"]',
             "web", "SUCCESS", "2026-10-08"),
        )
    before = db.read_bytes()
    consumer = FakeCanonicalConsumer()
    assert execute_geo_ai(
        db, "AUD-1", provider_selection="auto",
        provider_factory=lambda _: consumer,
    ) == "NOT_ELIGIBLE"
    assert consumer.calls == 0
    assert db.read_bytes() == before
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE perplexity_search_runs SET started_at=?",
            ("2026-10-09T12:00:00+00:00",),
        )
    # Distinct run IDs at the same measured instant still have no order.
    assert execute_geo_ai(
        db, "AUD-1", provider_selection="auto",
        provider_factory=lambda _: consumer,
    ) == "NOT_ELIGIBLE"
    assert consumer.calls == 0

def test_geo_ai_reserves_before_external_call_and_replay_after_crash_is_noop(
    tmp_path,
):
    """A hard process interruption must not authorize a second AI request."""
    db = tmp_path / "audit.db"
    GeoAiConsumerTests()._db(db)
    called = []

    class InterruptingConsumer:
        def analyze(self, _input):
            called.append(1)
            # The reservation is a durable, committed row while AI runs.
            with sqlite3.connect(db) as observer:
                row = observer.execute(
                    "SELECT state, error_reason FROM geo_ai_interpretations"
                ).fetchone()
            assert row == (
                "PENDING_UNCERTAIN", "GEO_AI_OUTCOME_NOT_YET_PERSISTED",
            )
            raise KeyboardInterrupt("simulated hard interruption")

    import pytest
    with pytest.raises(KeyboardInterrupt, match="simulated hard interruption"):
        execute_geo_ai(
            db, "AUD-1", provider_selection="auto",
            provider_factory=lambda _: InterruptingConsumer(),
        )
    assert called == [1]

    def prohibit_factory(_):
        raise AssertionError("reserved GEO AI intent cannot execute twice")

    assert execute_geo_ai(
        db, "AUD-1", provider_selection="auto",
        provider_factory=prohibit_factory,
    ) == "PENDING_UNCERTAIN"
    assert called == [1]
    with sqlite3.connect(db) as verify:
        assert verify.execute(
            "SELECT count(*) FROM geo_ai_interpretations"
        ).fetchone()[0] == 1
        assert verify.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert verify.execute("PRAGMA foreign_key_check").fetchone() is None


def test_geo_ai_causality_and_rationale_are_persisted_and_html_escaped(tmp_path):
    from dataclasses import replace
    import json
    from rasai.geo_report import geo_body

    class CausalCaveatConsumer(FakeCanonicalConsumer):
        def analyze(self, evidence_input):
            result = super().analyze(evidence_input)
            assessment = result.assessment
            original = assessment.opportunities[0]
            updated = replace(
                original,
                rationale="<img src=x onerror=alert(1)> observed snippet",
                causality_note="<script>not causal</script>",
            )
            return replace(
                result,
                assessment=replace(assessment, opportunities=(updated,)),
            )

    db = tmp_path / "audit.db"
    GeoAiConsumerTests()._db(db)
    assert execute_geo_ai(
        db, "AUD-1", provider_selection="auto",
        provider_factory=lambda _: CausalCaveatConsumer(),
    ) == "AVAILABLE"
    with sqlite3.connect(db) as connection:
        recorded = json.loads(connection.execute(
            "SELECT opportunities_json FROM geo_ai_interpretations"
        ).fetchone()[0])
    assert recorded[0]["causality_note"] == "<script>not causal</script>"
    assert recorded[0]["rationale"].startswith("<img")
    before = db.read_bytes()
    html = geo_body(db, "AUD-1")
    assert "Justificativa apresentada pela IA:" in html
    assert "Limite de causalidade:" in html
    assert "&lt;script&gt;not causal&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<script>not causal</script>" not in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert db.read_bytes() == before
