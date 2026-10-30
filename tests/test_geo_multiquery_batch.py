"""Focused, provider-free regression for GEO multi-query (#681)."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from rasai.geo_multiquery_batch import (
    estimated_search_cost_usd, latest_batch, record_item,
    request_fingerprint, reserve_batch,
)
from rasai.geo_multiquery_report import geo_multiquery_html
from rasai.geo_multiquery_runtime import execute_geo_multiquery_for_audit


def _db(root: Path) -> Path:
    db = root / "audit.db"
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("CREATE TABLE audits(audit_id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO audits VALUES ('AUD-1')")
        con.execute(
            "CREATE TABLE perplexity_search_runs("
            "run_id TEXT PRIMARY KEY, audit_id TEXT, started_at TEXT)"
        )
    return db


class GeoMultiqueryTests(unittest.TestCase):
    def test_batch_reservation_replay_and_read_only_projection(self):
        with tempfile.TemporaryDirectory() as temp:
            db = _db(Path(temp))
            terms = ("consultoria de ti", "desenvolvimento de software")
            batch = reserve_batch(db, "AUD-1", terms, "web")
            self.assertEqual(batch, latest_batch(db, "AUD-1")["batch_id"])
            self.assertEqual(latest_batch(db, "AUD-1")["items"][0]["search_state"],
                             "PENDING_UNCERTAIN")
            record_item(db, "AUD-1", batch, 0, run_id="px-1",
                        search_state="SUCCESS", geo_ai_state="AVAILABLE")
            record_item(db, "AUD-1", batch, 1, run_id="px-2",
                        search_state="TIMEOUT", geo_ai_state="NOT_EXECUTED",
                        reason="POSSIBLY_BILLABLE_TIMEOUT")
            with self.assertRaises(ValueError):
                reserve_batch(db, "AUD-1", terms, "web")
            with self.assertRaises(ValueError):
                record_item(db, "AUD-1", batch, 0, run_id="px-3",
                            search_state="SUCCESS", geo_ai_state="AVAILABLE")
            with closing(sqlite3.connect(db)) as con, con:
                con.execute(
                    "INSERT INTO perplexity_search_runs VALUES "
                    "('px-1','AUD-1','2026-10-29T22:00:01+00:00')"
                )
                con.execute(
                    "INSERT INTO perplexity_search_runs VALUES "
                    "('px-2','AUD-1','2026-10-29T22:00:02+00:00')"
                )
            before = db.read_bytes()
            html = geo_multiquery_html(db, "AUD-1")
            self.assertIn("consultoria de ti", html)
            self.assertIn("TIMEOUT", html)
            self.assertIn("1/2", html)
            self.assertEqual(before, db.read_bytes())

    def test_fingerprint_binds_terms_and_search_mode(self):
        q = ("a", "b")
        self.assertNotEqual(request_fingerprint(q, "web"),
                            request_fingerprint(q, "fast"))
        self.assertNotEqual(request_fingerprint(q, "web"),
                            request_fingerprint(tuple(reversed(q)), "web"))
        self.assertEqual(estimated_search_cost_usd(2, "web"), .01)
        self.assertEqual(estimated_search_cost_usd(2, "fast"), .002)

    def test_guard_denies_unapproved_network_cost(self):
        with tempfile.TemporaryDirectory() as temp:
            db = _db(Path(temp))
            state = SimpleNamespace(
                perplexity_queries=("a", "b"), geo_multiquery_approval="",
            )
            calls = []
            def charged_runner(*args, **kwargs):
                calls.append(kwargs)
                raise RuntimeError("should never be called")
            with patch("rasai.persistence.AuditWorkspace.open") as open_workspace:
                result = execute_geo_multiquery_for_audit(
                    state, charged_runner, Path(temp), "AUD-1",
                    {"search_type": "web", "query": ("a", "b"), "audit_id": "AUD-1"},
                )
            self.assertEqual(result, 1)
            self.assertEqual(calls, [])
            open_workspace.assert_not_called()
            self.assertEqual(latest_batch(db, "AUD-1"), None)

    def test_authorized_execution_separates_queries_and_preserves_partial_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = _db(root)
            queries = ("first", "second")
            state = SimpleNamespace(
                perplexity_queries=queries, ai_provider="auto",
                geo_multiquery_approval=request_fingerprint(queries, "web"),
            )
            workspace = SimpleNamespace(root=root, database=db)
            calls = []
            def runner(_workspace, **kwargs):
                calls.append(tuple(kwargs["query"]))
                if len(calls) == 2:
                    raise TimeoutError("ambiguous external request")
                return SimpleNamespace(
                    status="SUCCESS", run_id="px-first", sources=("one",),
                    pricing=SimpleNamespace(estimated_cost=.005),
                )
            with (
                patch("rasai.persistence.AuditWorkspace.open", return_value=workspace),
                patch("rasai.geo_observation.materialize_geo_observation"),
                patch("rasai.geo_ai.execute_geo_ai", return_value="AVAILABLE"),
            ):
                status = execute_geo_multiquery_for_audit(
                    state, runner, root, "AUD-1",
                    {"search_type": "web", "query": queries, "audit_id": "AUD-1"},
                )
                repeated = execute_geo_multiquery_for_audit(
                    state, runner, root, "AUD-1",
                    {"search_type": "web", "query": queries, "audit_id": "AUD-1"},
                )
            self.assertEqual(status, 1)
            self.assertEqual(repeated, 1)
            self.assertEqual(calls, [("first",), ("second",)])
            items = latest_batch(db, "AUD-1")["items"]
            self.assertEqual(items[0]["geo_ai_state"], "AVAILABLE")
            self.assertEqual(items[1]["search_state"], "PENDING_UNCERTAIN")


if __name__ == "__main__":
    unittest.main()
