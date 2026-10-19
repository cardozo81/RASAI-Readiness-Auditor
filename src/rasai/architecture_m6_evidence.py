"""Read persisted M6 architecture evidence without external acquisition or writes.

An audit reprocess/complement may inspect this read-only inventory. No replay,
scoring, file mutation, new requests, or inference across URL/device/snapshot.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from dataclasses import dataclass
import hashlib
import sqlite3

from rasai.architecture_context import ArchitectureObservation, CLASSES
from rasai.audit_configuration_reuse import normalize_audit_id

MAX_OBSERVATIONS = 2000
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024


def _safe_artifact_reference(value: object) -> bool:
    """Validate syntax only; this does not attest integrity or manifest membership."""
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if "\\" in value or ":" in value or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return False
    parts = value.split("/")
    path = PurePosixPath(value)
    return (not path.is_absolute() and len(parts) > 1
            and all(segment not in {"", ".", ".."} for segment in parts))


@dataclass(frozen=True)
class ArchitectureArtifactInspection:
    """Physical inspection only: computed digests are NOT trusted manifest digests."""
    status: str
    raw_sha256: str | None = None
    rendered_sha256: str | None = None
    manifest_attested: bool = False


def capture_artifact_binding(
    workspace: str | Path, raw_ref: str | None, rendered_ref: str | None,
) -> dict[str, object]:
    """Bind newly written canonical artifacts to a snapshot, without network.

    Missing and unsafe files stay unverified; never create an attestation from
    references alone. M3 stores this record in its existing SQLite metadata.
    """
    root = Path(workspace).resolve()
    values: dict[str, str | None] = {}
    for kind, ref in (("raw", raw_ref), ("rendered", rendered_ref)):
        digest: str | None = None
        if isinstance(ref, str) and ref.startswith("artifacts/") and _safe_artifact_reference(ref):
            candidate = root / ref
            try:
                current = root
                for component in candidate.relative_to(root).parts:
                    current = current / component
                    if current.is_symlink():
                        raise ValueError("symlink")
                if candidate.is_file() and candidate.stat().st_size <= MAX_ARTIFACT_BYTES:
                    checksum = hashlib.sha256()
                    size = 0
                    with candidate.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            size += len(chunk)
                            if size > MAX_ARTIFACT_BYTES:
                                raise ValueError("oversized")
                            checksum.update(chunk)
                    digest = checksum.hexdigest()
            except (OSError, ValueError):
                digest = None
        values[kind] = digest
    return {"version": "m3-artifact-binding-v1", "raw_sha256": values["raw"],
            "rendered_sha256": values["rendered"], "manifest_attested": False}


def verify_artifact_binding(
    audits_root: str | Path, audit_id: str, raw_ref: str | None,
    rendered_ref: str | None, binding: object,
) -> str:
    """Verify a stored M3 snapshot binding against current canonical bytes."""
    if not isinstance(binding, dict) or binding.get("version") != "m3-artifact-binding-v1":
        return "UNVERIFIED_LEGACY"
    if binding.get("manifest_attested") is not False:
        return "UNTRUSTED_ATTESTATION"
    if not any(binding.get(k) is not None for k in ("raw_sha256", "rendered_sha256")):
        return "NO_CAPTURE_DIGEST"
    computed = capture_artifact_binding(Path(audits_root) / normalize_audit_id(audit_id),
                                        raw_ref, rendered_ref)
    for name in ("raw_sha256", "rendered_sha256"):
        expected = binding.get(name)
        if expected is not None:
            if not isinstance(expected, str) or len(expected) != 64:
                return "DIGEST_MISMATCH"
            if computed[name] != expected:
                return "DIGEST_MISMATCH"
    return "VERIFIED_EMBEDDED_DIGEST"


def inspect_architecture_artifact_pair(
    audits_root: str | Path, audit_id: str, raw_ref: str, rendered_ref: str,
) -> ArchitectureArtifactInspection:
    """Inspect a persisted pair without following symlinks or writing any files.

    A freshly calculated digest cannot prove historic authenticity without an
    independently anchored canonical hash. Never report attestation here.
    """
    normalized = normalize_audit_id(audit_id)
    root = Path(audits_root).resolve()
    workspace = root / normalized
    if workspace.is_symlink() or not workspace.is_dir():
        return ArchitectureArtifactInspection("WORKSPACE_UNAVAILABLE")
    if not all(_safe_artifact_reference(x) and x.startswith("artifacts/")
               for x in (raw_ref, rendered_ref)):
        return ArchitectureArtifactInspection("INVALID_REFERENCE")
    digests = []
    for reference in (raw_ref, rendered_ref):
        candidate = workspace / reference
        try:
            relative = candidate.relative_to(workspace)
            current = workspace
            for segment in relative.parts:
                current = current / segment
                if current.is_symlink():
                    return ArchitectureArtifactInspection("UNSAFE_SYMLINK")
            if not candidate.is_file() or not candidate.resolve().is_relative_to(workspace.resolve()):
                return ArchitectureArtifactInspection("ARTIFACT_UNAVAILABLE")
            if candidate.stat().st_size > MAX_ARTIFACT_BYTES:
                return ArchitectureArtifactInspection("ARTIFACT_LIMIT_EXCEEDED")
            digest = hashlib.sha256()
            total = 0
            with candidate.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    total += len(chunk)
                    if total > MAX_ARTIFACT_BYTES:
                        return ArchitectureArtifactInspection("ARTIFACT_LIMIT_EXCEEDED")
                    digest.update(chunk)
            digests.append(digest.hexdigest())
        except (OSError, ValueError):
            return ArchitectureArtifactInspection("ARTIFACT_UNAVAILABLE")
    return ArchitectureArtifactInspection(
        "PRESENT_UNATTESTED", digests[0], digests[1], False,
    )


def inspect_historical_snapshot_artifacts(
    audits_root: str | Path, audit_id: str, *, page_id: str,
    snapshot_id: str, requested_url: str, final_url: str, device: str,
) -> ArchitectureArtifactInspection:
    """Read-only physical diagnostic scoped to an unambiguous AUD snapshot."""
    normalized = normalize_audit_id(audit_id)
    root = Path(audits_root).resolve()
    workspace = root / normalized
    database = workspace / "audit.db"
    identity = (page_id, snapshot_id, requested_url, final_url, device)
    if not all(isinstance(v, str) and v.strip() for v in identity):
        return ArchitectureArtifactInspection("INVALID_IDENTITY")
    if (workspace.is_symlink() or database.is_symlink()
            or not database.is_file()
            or not database.resolve().is_relative_to(root)):
        return ArchitectureArtifactInspection("WORKSPACE_UNAVAILABLE")
    try:
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro",
                             uri=True, timeout=1.0) as con:
            con.execute("PRAGMA query_only=ON")
            rows = con.execute(
                """SELECT ps.raw_artifact_ref, ps.rendered_artifact_ref
                   FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
                   WHERE p.audit_id=? AND ps.page_id=? AND ps.snapshot_id=?
                     AND ps.requested_url=? AND ps.final_url=? AND ps.device=?
                   LIMIT 2""",
                (normalized, page_id, snapshot_id, requested_url, final_url, device),
            ).fetchall()
            count = con.execute(
                """SELECT COUNT(*) FROM page_snapshots ps
                   JOIN pages p ON p.page_id=ps.page_id
                   WHERE p.audit_id=? AND ps.snapshot_id=?""",
                (normalized, snapshot_id),
            ).fetchone()[0]
    except (OSError, sqlite3.Error, ValueError):
        return ArchitectureArtifactInspection("DATABASE_UNAVAILABLE")
    if len(rows) != 1 or count != 1:
        return ArchitectureArtifactInspection("MISSING_OR_AMBIGUOUS_IDENTITY")
    return inspect_architecture_artifact_pair(
        root, normalized, rows[0][0], rows[0][1],
    )


def read_audit_architecture_observations(
    audits_root: str | Path, audit_id: str,
) -> tuple[ArchitectureObservation, ...]:
    normalized = normalize_audit_id(audit_id)
    root = Path(audits_root).resolve()
    workspace = root / normalized
    database = workspace / "audit.db"
    if (workspace.is_symlink() or database.is_symlink()
            or not database.resolve().is_relative_to(root)
            or not database.is_file()):
        return ()
    try:
        connection = sqlite3.connect(
            database.resolve().as_uri() + "?mode=ro", uri=True, timeout=1.0,
        )
        try:
            connection.execute("PRAGMA query_only=ON")
            rows = connection.execute(
                """SELECT ps.snapshot_id, ps.page_id, ps.device,
                          ps.requested_url, ps.final_url, ps.architecture_classification,
                          ps.raw_artifact_ref, ps.rendered_artifact_ref
                   FROM page_snapshots ps JOIN pages p ON ps.page_id=p.page_id
                   WHERE p.audit_id=?
                   ORDER BY ps.snapshot_id LIMIT ?""",
                (normalized, MAX_OBSERVATIONS + 1),
            ).fetchall()
        finally:
            connection.close()
    except (OSError, sqlite3.Error, ValueError):
        return ()
    if len(rows) > MAX_OBSERVATIONS:
        return ()
    observations = []
    seen = set()
    ambiguous = set()
    snapshot_identities = {}
    ambiguous_snapshots = set()
    for snapshot_id, page_id, device, requested, final, architecture, raw, rendered in rows:
        identity = (snapshot_id, page_id, device, requested, final)
        # A snapshot ID is a physical identity within one AUD, not a
        # reusable label for different pages, devices or target URLs.
        if snapshot_id in snapshot_identities and snapshot_identities[snapshot_id] != identity:
            ambiguous_snapshots.add(snapshot_id)
        snapshot_identities[snapshot_id] = identity
        if identity in seen:
            ambiguous.add(identity)
        seen.add(identity)
        if (not all(isinstance(item, str) and item.strip() for item in identity)
                or identity in ambiguous or architecture not in CLASSES
                or not _safe_artifact_reference(raw)
                or not _safe_artifact_reference(rendered)):
            # Never elevate an incomplete or duplicated RAW/rendered pair.
            continue
        observations.append(ArchitectureObservation(
            architecture=architecture, requested_url=requested,
            final_url=final, device=device, snapshot_id=snapshot_id,
            evidence_ref=raw, audit_id=normalized, page_id=page_id,
        ))
    return tuple(o for o in observations if (
        o.snapshot_id, o.page_id, o.device,
        o.requested_url, o.final_url,
    ) not in ambiguous and o.snapshot_id not in ambiguous_snapshots)
