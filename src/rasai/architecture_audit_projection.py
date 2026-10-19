"""#646 F3: read-only, per-snapshot architectural context of ONE sealed AUD.

A frozen operator choice and the M6 observation are different facts. The
existing architecture_context resolver remains the sole selector for approved
descriptive consumers. No retroactive change to collectors/M23/M25/scoring.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Any

from rasai.architecture_context import resolve_architecture, CONTRACT_VERSION
from rasai.architecture_choice_audit_adapter import read_architecture_choice_for_reprocess
from rasai.architecture_m6_evidence import read_audit_architecture_observations
from rasai.audit_configuration_reuse import normalize_audit_id

MAX_SNAPSHOTS = 100
VERSION = "architecture-audit-advisory-v1"


def _empty(audit_id: str | None, reason: str) -> dict[str, Any]:
    return {
        "contract": VERSION, "resolver": CONTRACT_VERSION, "audit_id": audit_id,
        "status": "NOT_VERIFIABLE", "reason": reason, "snapshots": [],
        "choice_origin": "UNVERIFIED", "selection": "UNFORCED",
        "provided_architecture": None, "audit_writes": 0,
        "provider_requests": 0, "applied_to_scoring": False,
    }


def _stamp(db: Path):
    st = db.stat()
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def _unsealed(db: Path) -> bool:
    return (
        db.is_symlink() or db.parent.is_symlink() or not db.is_file()
        or any(Path(str(db) + suffix).exists()
               for suffix in ("-wal", "-shm", "-journal"))
    )


def inspect_audit_architecture_context(
    audits_root: str | Path, audit_id: str,
) -> dict[str, Any]:
    """One physical audit, at most 100 M6 snapshots, no accidental DB create.

    Untrusted or conflicting physical identifiers do not leak a classification
    from another audit. A signed or embedded digest is verified by the existing
    M6 source reader where present; legacy references remain advisory only.
    """
    try:
        identity = normalize_audit_id(audit_id)
        root = Path(audits_root)
        workspace = root / identity
        db = workspace / "audit.db"
        if (root.is_symlink() or workspace.is_symlink() or not workspace.is_dir()
                or _unsealed(db)):
            return _empty(identity, "AUD_SOURCE_UNAVAILABLE_OR_UNSEALED")
        before = _stamp(db)
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro&immutable=1",
            uri=True, timeout=2,
        )) as con:
            con.execute("PRAGMA query_only=ON")
            tables = {str(row[0]) for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if not {"pages", "page_snapshots"}.issubset(tables):
                return _empty(identity, "M6_SOURCE_SCHEMA_UNAVAILABLE")
            required = {
                "snapshot_id", "page_id", "device", "requested_url", "final_url",
            }
            cols = {str(row[1]) for row in con.execute(
                "PRAGMA table_info(page_snapshots)"
            )}
            if not required.issubset(cols):
                return _empty(identity, "M6_IDENTITY_FIELDS_UNAVAILABLE")
            page_cols = {str(row[1]) for row in con.execute("PRAGMA table_info(pages)")}
            if not {"audit_id", "page_id"}.issubset(page_cols):
                return _empty(identity, "M6_PAGE_IDENTITY_FIELDS_UNAVAILABLE")
            physical = con.execute(
                "SELECT ps.snapshot_id, ps.page_id, ps.device, "
                "ps.requested_url, ps.final_url "
                "FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id "
                "WHERE p.audit_id=? ORDER BY ps.snapshot_id LIMIT ?",
                (identity, MAX_SNAPSHOTS + 1),
            ).fetchall()
            if len(physical) > MAX_SNAPSHOTS:
                return _empty(identity, "SNAPSHOT_COHORT_LIMIT")
            identities = []
            for snapshot_id, page_id, device, requested, final in physical:
                # Page and snapshot IDs must be globally unique in the
                # physical ledger; otherwise a JOIN could cross two AUDs.
                page_uses = con.execute(
                    "SELECT COUNT(*) FROM pages WHERE page_id=?", (page_id,),
                ).fetchone()[0]
                snapshot_uses = con.execute(
                    "SELECT COUNT(*) FROM page_snapshots WHERE snapshot_id=?",
                    (snapshot_id,),
                ).fetchone()[0]
                if (page_uses != 1 or snapshot_uses != 1
                        or not all(isinstance(x, str) and x.strip()
                                   for x in (snapshot_id, page_id, device, requested, final))):
                    return _empty(identity, "PHYSICAL_SNAPSHOT_IDENTITY_AMBIGUOUS")
                identities.append((snapshot_id, page_id, device, requested, final))
        choice = read_architecture_choice_for_reprocess(root, identity)
        observations = read_audit_architecture_observations(root, identity)
        if _unsealed(db) or _stamp(db) != before:
            return _empty(identity, "AUD_SOURCE_CHANGED_DURING_READ")
        mode = choice.choice.mode if choice is not None else "UNFORCED"
        declared = choice.choice.declared_architecture if choice is not None else None
        source = choice.source if choice is not None else "UNVERIFIED_OR_LEGACY"
        rows = []
        for snapshot_id, page_id, device, requested, final in identities:
            resolved = resolve_architecture(
                mode=mode, declared_architecture=declared, observations=observations,
                audit_id=identity, page_id=page_id,
                snapshot_id=snapshot_id, requested_url=requested,
                final_url=final, device=device,
                consumer_id="descriptive_report",
                advisory_consumers=frozenset({"descriptive_report"}),
                phase="POST_COLLECTION",
            )
            rows.append({
                "snapshot_id": snapshot_id, "page_id": page_id,
                "device": device, "requested_url": requested, "final_url": final,
                "observed_architecture": resolved.observed_architecture,
                "selected_mode": resolved.selected_mode,
                "declared_architecture": resolved.declared_architecture,
                "effective_architecture": resolved.effective_architecture,
                "source": resolved.source,
                "discrepancy": resolved.discrepancy,
                "abstention_reason": resolved.abstention_reason,
                "evidence_ref": resolved.evidence_ref,
                "applicability": resolved.applicability,
            })
        if not rows:
            return _empty(identity, "NO_M6_SNAPSHOTS_IN_AUD")
        return {
            "contract": VERSION, "resolver": CONTRACT_VERSION,
            "audit_id": identity, "status": "ADVISORY_OBSERVED",
            "reason": None, "snapshots": rows,
            "choice_origin": source, "selection": mode,
            "provided_architecture": declared,
            "audit_writes": 0, "provider_requests": 0,
            "applied_to_scoring": False,
            "limitations": (
                "Arquitetura observada no snapshot nao configura motores ja executados. "
                "Escolha declarada nao substitui observacao M6. Legado UNFORCED "
                "preserva discovery como informacao e impede aplicacao implicita. "
                "Nenhum perfil de Apdex, SARI, SCORE-GEO, IA ou coletor foi alterado."
            ),
        }
    except (sqlite3.Error, OSError, ValueError, TypeError, OverflowError):
        return _empty(str(audit_id) if isinstance(audit_id, str) else None,
                      "AUD_CONTEXT_READ_UNVERIFIABLE")


__all__ = ["inspect_audit_architecture_context", "VERSION", "MAX_SNAPSHOTS"]
