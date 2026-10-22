"""#322: immutable advisory sidecar for same-sample content readiness.

Written OUTSIDE an original sealed AUD and its report-catalog; no M23/M25
table, scoring, browser hook or provider use. This validates the observation
contract but cannot independently establish physical Playwright provenance.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import asdict
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import re
import sqlite3

from rasai.apdex_content_readiness_observation import (
    PrimaryContentReadiness,
    STRICT_PROVENANCE_VERSION,
)
from rasai.readiness_probe_cost_pilot import PrimaryContentProbeCost, VERSION as PROBE_COST_VERSION

SIDECAR_VERSION = "RASAI-PRIMARY-CONTENT-READINESS-SIDECAR-001"
_MAX_AUD_SOURCE_BYTES = 256 * 1024 * 1024
_AUD_ID = re.compile(r"^AUD-[A-Za-z0-9-]{1,100}$")
_STATES = frozenset({
    "OBSERVED", "NOT_OBSERVED", "TIMEOUT", "NOT_APPLICABLE", "ERROR",
})


def _unique_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate sidecar JSON key")
        result[key] = value
    return result


def _reject_non_json_constant(token: str) -> None:
    raise ValueError("nonstandard sidecar JSON numeric constant")


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _original(aud_dir: Path, *, allow_limited_completion: bool = False) -> tuple[str, str, str]:
    """Return proven sealed AUD identity; optional limitations apply only to FAQ.

    Default strict COMPLETE semantics remain unchanged for M25 and other readers.
    Explicit FAQ acceptance of COMPLETE_WITH_LIMITATIONS does not waive manifest,
    source integrity, finalized status, or the receipt-to-snapshot binding.
    """
    aud_dir = Path(aud_dir)
    if not _AUD_ID.fullmatch(aud_dir.name) or aud_dir.is_symlink():
        raise ValueError("unsafe AUD directory identity")
    db = aud_dir / "audit.db"
    manifest = aud_dir / "report-catalog" / "manifest.json"
    if (
        db.is_symlink() or manifest.is_symlink()
        or (aud_dir / "report-catalog").is_symlink()
        or not db.is_file() or not manifest.is_file()
    ):
        raise ValueError("sealed source audit.db and manifest required")
    if (db.stat().st_size > _MAX_AUD_SOURCE_BYTES
            or manifest.stat().st_size > 32 * 1024 * 1024):
        raise ValueError("sealed AUD source exceeds bounded integrity budget")
    if any(Path(str(db) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("sealed AUD SQLite has live transaction sidecars")
    # An AUD flagged COMPLETE is not sufficient: its packaged HTML/evidence
    # must also be fresh and cryptographically consistent with the source.
    from rasai.catalog_report_site import catalog_report_is_fresh
    if not catalog_report_is_fresh(
        audit_id=aud_dir.name,
        workspace=SimpleNamespace(root=aud_dir, database=db),
    ):
        raise ValueError("source AUD report manifest is stale or invalid")
    uri = db.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=1)) as con:
        con.execute("PRAGMA query_only=ON")
        try:
            rows = con.execute(
                "SELECT status, completion_status FROM audits WHERE audit_id=?",
                (aud_dir.name,),
            ).fetchall()
            if (
                len(rows) != 1 or str(rows[0][0]).upper() != "COMPLETED"
                or str(rows[0][1]).upper() not in (
                    {"COMPLETE", "COMPLETE_WITH_LIMITATIONS"}
                    if allow_limited_completion else {"COMPLETE"}
                )
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
    # Measurement states are only authorized for opt-in architectures.
    # Otherwise a manually created JSON could falsely claim same-sample
    # readiness on UNKNOWN/STATIC_OR_SSR without any physical probe.
    if (
        row["status"] in {"OBSERVED", "NOT_OBSERVED", "TIMEOUT"}
        and row["architecture"] not in {"CSR_SPA", "HYDRATED", "MIXED"}
    ):
        raise ValueError("readiness measurement on non-eligible architecture")
    if row["status"] == "OBSERVED" and row["reason"] != "stable_primary_dom_text":
        raise ValueError("observed readiness must cite stability rule")
    for key in ("load_ms", "primary_content_ms", "post_load_delta_ms"):
        val = row[key]
        if val is not None and (
            type(val) not in (int, float) or not math.isfinite(val)
            or not 0 <= val <= 48 * 60 * 60 * 1000
        ):
            raise ValueError("invalid physical readiness timestamp")
    if row["status"] in {"OBSERVED", "NOT_OBSERVED", "TIMEOUT"} and row["load_ms"] is None:
        raise ValueError("same-sample load boundary required for readiness probe")
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



_PROBE_COST_FIELDS = (
    "contract_version", "sample_id", "page_id", "device",
    "number_of_dom_evaluations", "total_dom_evaluation_ms",
    "maximum_dom_evaluation_ms", "elapsed_probe_wall_ms",
    "measured_sleep_ms", "active_probe_wall_ms",
    "evaluation_budget_ms", "local_evaluation_budget_met",
    "integration_gate", "identity_proof", "source_page_reused",
)


def _cost_metadata(value: PrimaryContentProbeCost | dict, row: dict) -> dict:
    """Validate bounded same-sample telemetry, never claim an A/B budget pass."""
    if isinstance(value, PrimaryContentProbeCost):
        if asdict(value.observation) != row:
            raise ValueError("probe cost observation identity mismatch")
        if value.provider_requests != 0 or value.audit_writes != 0 or value.apdex_changed is not False:
            raise ValueError("probe cost cannot alter canonical audit")
        value = {
            "contract_version": value.contract_version,
            "sample_id": value.observation.sample_id,
            "page_id": value.observation.page_id,
            "device": value.observation.device,
            **{k: getattr(value, k) for k in _PROBE_COST_FIELDS[4:]},
        }
    if not isinstance(value, dict) or set(value) != set(_PROBE_COST_FIELDS):
        raise ValueError("invalid probe cost schema")
    if (
        value["contract_version"] != PROBE_COST_VERSION
        or any(value[k] != row[k] for k in ("sample_id", "page_id", "device"))
        or value["identity_proof"] != "CALLER_DECLARED_NOT_ATTESTED_BY_M25"
        or value["source_page_reused"] is not True
        or value["integration_gate"] not in {
            "NOT_APPLICABLE_OR_NO_DOM_EVALUATION",
            "BLOCKED_BY_LOCAL_DOM_OVERHEAD",
            "PILOT_ONLY_REQUIRES_MATCHED_BASELINE_AND_GATEWAY_IDENTITY",
        }
        or type(value["number_of_dom_evaluations"]) is not int
        or not 0 <= value["number_of_dom_evaluations"] <= 50
        or any(
            type(value[k]) not in (int, float)
            or not math.isfinite(value[k]) or not 0 <= value[k] <= 600000
            for k in (
                "total_dom_evaluation_ms", "maximum_dom_evaluation_ms",
                "elapsed_probe_wall_ms", "measured_sleep_ms",
                "active_probe_wall_ms", "evaluation_budget_ms",
            )
        )
        or not 0 < value["evaluation_budget_ms"] <= 1000
        or value["maximum_dom_evaluation_ms"] > value["total_dom_evaluation_ms"] + .01
        or value["total_dom_evaluation_ms"] > value["elapsed_probe_wall_ms"] + .05
        or value["active_probe_wall_ms"] > value["elapsed_probe_wall_ms"] + .05
        or type(value["local_evaluation_budget_met"]) not in (bool, type(None))
        or (value["local_evaluation_budget_met"] is None) != (
            value["number_of_dom_evaluations"] == 0
        )
    ):
        raise ValueError("unverifiable or unbounded probe cost")
    return dict(value)


def _serialized(audit_id: str, db_sha: str, manifest_sha: str, row: dict, cost: dict | None = None) -> bytes:
    data = {
        "contract_version": SIDECAR_VERSION,
        "audit_id": audit_id,
        "source_audit_db_sha256": db_sha,
        "source_report_manifest_sha256": manifest_sha,
        "advisory_only": True,
        "measurement_provenance": "PRODUCER_DECLARED_SAME_SAMPLE",
        "observation": row,
    }
    if cost is not None:
        data["probe_cost"] = cost
    return (
        json.dumps(
            data,
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ) + "\n"
    ).encode("utf-8")


def _root(aud_dir: Path, audit_id: str) -> Path:
    return aud_dir.parent / ".rasai-readiness-sidecars" / audit_id


def write_readiness_sidecar(
    aud_dir: Path, observation: PrimaryContentReadiness,
    *, probe_cost: PrimaryContentProbeCost | None = None,
) -> Path:
    """Persist one versioned, deduplicated digest-named immutable JSON record.

    The AUD must already be sealed; do not call from the active M23/M25 gateway.
    An existing different or corrupt file causes failure, never overwrite.
    """
    audit_id, db_sha, manifest_sha = _original(Path(aud_dir))
    row = _valid(observation)
    cost = _cost_metadata(probe_cost, row) if probe_cost is not None else None
    payload = _serialized(audit_id, db_sha, manifest_sha, row, cost)
    digest = sha256(payload).hexdigest()
    folder = _root(Path(aud_dir), audit_id)
    if folder.parent.is_symlink() or folder.is_symlink():
        raise ValueError("sidecar directory cannot be symlink")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (digest + ".json")
    if path.is_symlink():
        raise ValueError("sidecar cannot be symlink")
    # Stage completely before publication. Writing directly to the final
    # immutable name would expose truncated JSON if interrupted mid-write.
    # Hard-link publication is exclusive: never overwrite a concurrent writer,
    # even on replay. A crash may leave an ignored .pending- file, not a
    # falsely sealed record.
    fd, staged = tempfile.mkstemp(dir=folder, prefix=".pending-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(staged, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != payload:
                raise ValueError("sidecar checksum mismatch; not overwriting")
    finally:
        Path(staged).unlink(missing_ok=True)
    return path


def read_readiness_sidecar(aud_dir: Path, sidecar_path: Path) -> dict:
    """Verify exact source binding, digest and strictly defined data contract."""
    audit_id, db_sha, manifest_sha = _original(Path(aud_dir))
    expected = _root(Path(aud_dir), audit_id)
    sidecar_path = Path(sidecar_path)
    if (
        sidecar_path.parent != expected
        or sidecar_path.is_symlink() or expected.is_symlink()
        or expected.parent.is_symlink()
        or not re.fullmatch(r"[0-9a-f]{64}\.json", sidecar_path.name)
    ):
        raise ValueError("sidecar path outside sealed AUD scope")
    if not sidecar_path.is_file() or sidecar_path.stat().st_size > 64 * 1024:
        raise ValueError("sidecar source missing or exceeds bounded size")
    raw = sidecar_path.read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError("sidecar changed beyond bounded size")
    if sha256(raw).hexdigest() + ".json" != sidecar_path.name:
        raise ValueError("sidecar SHA-256 mismatch")
    try:
        obj = json.loads(
            raw, object_pairs_hook=_unique_json_keys,
            parse_constant=_reject_non_json_constant,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid sidecar encoding") from exc
    if not isinstance(obj, dict):
        raise ValueError("invalid sidecar encoding")
    # Distinguish a well-formed, immutable sidecar bound to a different
    # physical source from an invalid JSON/observation encoding. Do not
    # translate this intentional source-binding rejection in the parser catch.
    if any(
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
    try:
        obs = obj.get("observation")
        if not isinstance(obs, dict):
            raise ValueError("invalid sidecar observation")
        checked = _valid(PrimaryContentReadiness(**obs))
        if "probe_cost" in obj:
            _cost_metadata(obj["probe_cost"], checked)
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError("invalid sidecar encoding") from exc
    return obj
