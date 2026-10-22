"""Read-only documentary presentation of ONE already sealed content-readiness sidecar.

This is an externally producer-declared experiment, NOT a M23/M25 observation,
score extension, reliable browser attestation or alternative to the original
Apdex. A sidecar references the sealed AUD hash but does not prove the sample
was collected by the browser task named in its fields.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

from rasai.apdex_readiness_sidecar import read_readiness_sidecar

CONTRACT = "RASAI-CONTENT-READINESS-REVIEW-322-001"
_MAX_STR = 180


def inspect_content_readiness_review(
    aud_dir: Path, sidecar_file: Path,
) -> dict[str, Any]:
    """Fail closed if the local sidecar/source no longer verify, with no writes."""
    baseline: dict[str, Any] = {
        "contract": CONTRACT, "status": "NOT_VERIFIABLE",
        "audit_id": None, "reason": "SOURCE_NOT_VERIFIABLE",
        "provider_requests": 0, "audit_writes": 0,
        "apdex_writes": 0, "apdex_recalculated": False,
        "producer_declared_only": True, "physical_sample_attested": False,
        "persisted_sample_link_verified": False,
        "observation": None,
    }
    try:
        source = read_readiness_sidecar(Path(aud_dir), Path(sidecar_file))
        aud_id = source.get("audit_id")
        observation = source.get("observation")
        if not isinstance(aud_id, str) or not isinstance(observation, dict):
            return baseline
        keys = (
            "sample_id", "context_id", "page_id", "device", "architecture",
            "method_version", "status", "reason", "observation_window_ms",
            "load_ms", "primary_content_ms", "post_load_delta_ms",
        )
        projection = {k: observation.get(k) for k in keys}
        if any(
            not isinstance(projection[k], str)
            or not 0 < len(projection[k]) <= _MAX_STR
            for k in ("sample_id", "context_id", "page_id", "device", "architecture",
                      "method_version", "status", "reason")
        ):
            return baseline
        if projection["status"] not in {
            "OBSERVED", "NOT_OBSERVED", "TIMEOUT", "NOT_APPLICABLE", "ERROR",
        }:
            return baseline
        # A digest-matching sidecar is not enough: the measured sample
        # must exist exactly once in the sealed, read-only source SQLite.
        db_path = Path(aud_dir) / "audit.db"
        with sqlite3.connect(
            db_path.resolve().as_uri() + "?mode=ro&immutable=1",
            uri=True, timeout=1,
        ) as connection:
            connection.execute("PRAGMA query_only=ON")
            matching = connection.execute(
                "SELECT COUNT(*) FROM synthetic_ux_apdex_samples "
                "WHERE audit_id=? AND sample_id=? AND page_id=? AND device=?",
                (aud_id, projection["sample_id"], projection["page_id"],
                 projection["device"]),
            ).fetchone()
        if matching is None or matching[0] != 1:
            return baseline
        return {
            **baseline,
            "status": "DOCUMENTARY_SIDECAR_OBSERVED",
            "persisted_sample_link_verified": True,
            "audit_id": aud_id,
            "reason": None,
            "observation": projection,
            "source_binding": (
                "SHA256_AUD_DB_AND_REPORT_MANIFEST_CHECKED"
            ),
            "method_note": (
                "Tempos monotônicos declarados pelo produtor no mesmo "
                "contexto não equivalem a prova externa de coleta física. "
                "A identidade declarada coincide com um registro M25 "
                "persistido na AUD selada. Sem auditoria independente do "
                "browser, não inferir delta "
                "de load de M23/M25 e não computar outro Apdex."
            ),
        }
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        return baseline


__all__ = ["inspect_content_readiness_review", "CONTRACT"]
