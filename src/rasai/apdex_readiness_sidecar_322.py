"""#322: immutable advisory sidecar for same-sample content readiness.

Written OUTSIDE an original sealed AUD and its report-catalog; no M23/M25
table, scoring, browser hook or provider use. This validates the observation
contract but cannot independently establish physical Playwright provenance.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import sqlite3

from rasai.apdex_content_readiness_observation import (
    PrimaryContentReadiness,
    STRICT_PROVENANCE_VERSION,
)

SIDECAR_VERSION = "RASAI-PRIMARY-CONTENT-READINESS-SIDECAR-001"
_AUD_ID = re.compile(r"^AUD-[A-Za-z0-9-]{1,100}$")
_STATES = frozenset({
    "OBSERVED", "NOT_OBSERVED", "TIMEOUT", "NOT_APPLICABLE", "ERROR",
})


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _original(aud_dir: Path) -> tuple[str, str, str]:
    """Return proven sealed AUD identity using only read-only local operations."""
    aud_dir = Path(aud_dir)
    if not _AUD_ID.fullmatch(aud_dir.name) or aud_dir.is_symlink():
        raise ValueError("unsafe AUD directory identity")
    db = aud_dir / "audit.db"
    manifest = aud_dir / "report-catalog" / "manifest.json"
    if (
        db.is_symlink() or manifest.is_symlink()
        or not db.is_file() or not manifest.is_file()
    ):
        raise ValueError("sealed source audit.db and manifest required")
    uri = db.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=1) as con:
        con.execute("PRAGMA query_only=ON")
        try:
            rows = con.execute(
                "SELECT status, completion_status FROM audits WHERE audit_id=?",
                (aud_dir.name,),
            ).fetchall()
            if (
                len(rows) != 1 or str(rows[0][0]).upper() != "COMPLETED"
                or str(rows[0][1]).upper() != "COMPLETE"
                or con.execute("PRAGMA quick_check").fetchone()[0] != "ok"
                or con.execute("PRAGMA foreign_key_check").fetchone() is not None
            ):
                raise ValueError("source AUD is not complete and valid")
        except sqlite3.Error as exc:
            raise ValueError("source AUD schema not verifiable") from exc
    return aud_dir.name, _sha(db), _sha(manifest)


def _valid(observation: PrimaryContentReadiness) -> dict:
    if not isinstance(observation, PrimaryContentReadiness):
        raise ValueError("invalid readiness observation contract")
    row = asdict(observation)
    if (
        row["method_version"] != STRICT_PROVENANCE_VERSION
        or row["status"] not in _STATES
        or not all(
            isinstance(row[key], str) and bool(row[key].strip())
            and len(row[key]) <= 160
            for key in ("sample_id", "context_id", "page_id", "device", "reason")
        )
        or row["architecture"] not in {"CSR_SPA", "HYDRATED", "MIXED",
                                       "STATIC_OR_SSR", "UNKNOWN"}
        or type(row["observation_window_ms"]) is not int
        or not 100 <= row["observation_window_ms"] <= 3000
    ):
        raise ValueError("incomplete or non-strict readiness provenance")
    for key in ("load_ms", "primary_content_ms", "post_load_delta_ms"):
        val = row[key]
        if val is not None and (
            type(val) not in (int, float) or not math.isfinite(val) or val < 0
        ):
            raise ValueError("invalid physical readiness timestamp")
    if row["status"] == "OBSERVED":
        start, ready, delta = (
            row["load_ms"], row["primary_content_ms"], row["post_load_delta_ms"],
        )
        if (
            start is None or ready is None or delta is None
            or ready > start + row["observation_window_ms"]
            or abs(delta - max(0.0, ready - start)) > 0.001
        ):
            raise ValueError("observed readiness delta not same-sample verifiable")
    elif row["primary_content_ms"] is not None or row["post_load_delta_ms"] is not None:
        raise ValueError("censored or unavailable observation cannot claim readiness")
    return row


def _serialized(audit_id: str, db_sha: str, manifest_sha: str, row: dict) -> bytes:
    return (
        json.dumps(
            {
                "contract_version": SIDECAR_VERSION,
                "audit_id": audit_id,
                "source_audit_db_sha256": db_sha,
                "source_report_manifest_sha256": manifest_sha,
                "advisory_only": True,
                "measurement_provenance": "PRODUCER_DECLARED_SAME_SAMPLE",
                "observation": row,
            },
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
    ).encode("utf-8")


def _root(aud_dir: Path, audit_id: str) -> Path:
    return aud_dir.parent / ".rasai-readiness-sidecars" / audit_id


def write_readiness_sidecar(
    aud_dir: Path, observation: PrimaryContentReadiness,
) -> Path:
    """Persist one versioned, deduplicated digest-named immutable JSON record.

    The AUD must already be sealed; do not call from the active M23/M25 gateway.
    An existing different or corrupt file causes failure, never overwrite.
    """
    audit_id, db_sha, manifest_sha = _original(Path(aud_dir))
    row = _valid(observation)
    payload = _serialized(audit_id, db_sha, manifest_sha, row)
    digest = sha256(payload).hexdigest()
    folder = _root(Path(aud_dir), audit_id)
    if folder.parent.is_symlink() or folder.is_symlink():
        raise ValueError("sidecar directory cannot be symlink")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (digest + ".json")
    if path.is_symlink():
        raise ValueError("sidecar cannot be symlink")
    try:
        # Exclusive create. A replay never rewrites an already recorded output.
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError("sidecar checksum mismatch; not overwriting")
    return path


def read_readiness_sidecar(aud_dir: Path, sidecar_path: Path) -> dict:
    """Verify exact source binding, digest and strictly defined data contract."""
    audit_id, db_sha, manifest_sha = _original(Path(aud_dir))
    expected = _root(Path(aud_dir), audit_id)
    sidecar_path = Path(sidecar_path)
    if (
        sidecar_path.parent != expected
        or sidecar_path.is_symlink() or expected.is_symlink()
        or not re.fullmatch(r"[0-9a-f]{64}\.json", sidecar_path.name)
    ):
        raise ValueError("sidecar path outside sealed AUD scope")
    raw = sidecar_path.read_bytes()
    if sha256(raw).hexdigest() + ".json" != sidecar_path.name:
        raise ValueError("sidecar SHA-256 mismatch")
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict) or any(
            obj.get(name) != required
            for name, required in {
                "contract_version": SIDECAR_VERSION,
                "audit_id": audit_id,
                "source_audit_db_sha256": db_sha,
                "source_report_manifest_sha256": manifest_sha,
                "advisory_only": True,
                "measurement_provenance": "PRODUCER_DECLARED_SAME_SAMPLE",
            }.items()
        ):
            raise ValueError("sidecar source or contract mismatch")
        obs = obj.get("observation")
        if not isinstance(obs, dict):
            raise ValueError("invalid sidecar observation")
        _valid(PrimaryContentReadiness(**obs))
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("invalid sidecar encoding") from exc
    return obj
