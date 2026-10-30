"""Paid GEO reanalysis is never invoked without explicit operator intent."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

from rasai.geo_post_aud_ai_reanalysis import execute_authorized_geo_ai


def test_paid_geo_ai_uses_derived_db_and_deduplicates_identical_intent():
    with tempfile.TemporaryDirectory() as temporary:
        original = Path(temporary) / "AUD-ONE"
        original.mkdir()
        db = original / "audit.db"
        with sqlite3.connect(db) as con:
            con.execute("CREATE TABLE audits(audit_id TEXT PRIMARY KEY)")
            con.execute("INSERT INTO audits VALUES ('AUD-ONE')")
        bytes_before = db.read_bytes()
        snapshot = {
            "audit_id": "AUD-ONE",
            "source_sha256": sha256(bytes_before).hexdigest(),
            "catalog_manifest_sha256": "manifest",
            "saved_external_observations": [{
                "run_id": "px-run-1",
                "queries": ["uma consulta"],
                "search_status": "SUCCESS",
                "source_count": 2,
                "source_attribution": "PHYSICAL_SINGLE_QUERY",
            }],
        }
        with (
            patch("rasai.geo_post_aud_ai_reanalysis.inspect_completed_audit",
                  return_value=snapshot),
            patch("rasai.geo_ai.execute_geo_ai", return_value="AVAILABLE") as provider,
        ):
            first = execute_authorized_geo_ai(original, provider="auto")
            again = execute_authorized_geo_ai(original, provider="auto")
        assert first["state"] == "COMPLETE"
        assert again["state"] == "ALREADY_RESERVED_OR_RECORDED"
        assert provider.call_count == 1
        args, kwargs = provider.call_args
        assert args[0] != db
        assert kwargs["source_run_id"] == "px-run-1"
        assert db.read_bytes() == bytes_before
        assert (Path(first["package"]) / "manifest.json").is_file()
        # Existing paid reservations must be verified, not blindly reused.
        (Path(first["package"]) / "intent.json").write_text("{}", encoding="utf-8")
        with patch("rasai.geo_post_aud_ai_reanalysis.inspect_completed_audit",
                   return_value=snapshot):
            import pytest
            with pytest.raises(ValueError, match="reservation identity"):
                execute_authorized_geo_ai(original, provider="auto")
