"""#210: opt-in read-only local analytical-index entrypoint for domain preview.

This is NOT CONS-3 generation, not a native consolidation mode and not
authoritative freshness attestation of audit.db sources.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3
from typing import Sequence
from urllib.parse import urlsplit

from rasai.consolidation.domain_comparative_preview_210 import preview_same_domain_candidates
from rasai.consolidation.selection import AuditCandidate

_AUD = re.compile(r"^AUD-[A-Za-z0-9-]{1,100}$")
_SCHEMA_VERSION = 1


def domain_preview_from_index(audits_root: Path, audit_ids: Sequence[str]) -> dict:
    """Reuse the existing *materialized* index without creating or refreshing it."""
    root = Path(audits_root)
    ids = tuple(audit_ids)
    if not 2 <= len(ids) <= 100 or len(set(ids)) != len(ids):
        raise ValueError("select 2..100 unique AUD ids")
    if any(not isinstance(i, str) or not _AUD.fullmatch(i) for i in ids):
        raise ValueError("invalid AUD identity")
    db = root / ".rasai" / "consolidated-index.db"
    if root.is_symlink() or not root.is_dir() or db.is_symlink() or not db.is_file():
        raise ValueError("existing safe analytical index required; no refresh performed")
    if (root / ".rasai").is_symlink():
        raise ValueError("symlinked analytical index directory is forbidden")
    # Even a read-only WAL connection can create or refresh SQLite sidecars.
    # Abstain instead of opening an active or uncheckpointed cache snapshot.
    if any((db.parent / (db.name + suffix)).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("analytical index has active or unverified SQLite sidecars")

    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=3) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version != _SCHEMA_VERSION:
            raise ValueError("unsupported or uninitialized analytical index")
        for table, needed in (
            ("source_audits", {"audit_id", "event_time", "status",
                               "completion_status", "devices_json",
                               "url_count", "source_fingerprint"}),
            ("audit_urls", {"audit_id", "url"}),
        ):
            cols = {r[1] for r in con.execute("PRAGMA table_info(" + table + ")")}
            if not needed <= cols:
                raise ValueError("incomplete analytical index schema")
        # Entire index must be well formed before a claim based on it.
        if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("analytical index integrity unavailable")
        placeholders = ",".join("?" for _ in ids)
        rows = con.execute(
            "SELECT a.audit_id, a.event_time, a.status, a.completion_status, "
            "a.devices_json, a.url_count, a.source_fingerprint, u.url "
            "FROM source_audits a LEFT JOIN audit_urls u ON u.audit_id=a.audit_id "
            f"WHERE a.audit_id IN ({placeholders}) ORDER BY a.audit_id",
            ids,
        ).fetchall()
    by_id: dict[str, list[sqlite3.Row]] = {value: [] for value in ids}
    for row in rows:
        by_id[str(row["audit_id"])].append(row)
    candidates: list[AuditCandidate] = []
    for item in ids:
        parts = by_id[item]
        if len(parts) != 1 or parts[0]["url_count"] != 1:
            raise ValueError("each selected AUD needs exactly one indexed URL")
        source = parts[0]
        raw_fingerprint = source["source_fingerprint"]
        if not isinstance(raw_fingerprint, str) or not raw_fingerprint.strip():
            raise ValueError("source fingerprint absent")
        try:
            devices = json.loads(str(source["devices_json"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("devices inventory invalid") from exc
        if not isinstance(devices, list) or len(devices) != 1 or not isinstance(devices[0], str):
            raise ValueError("single-device AUD required")
        url = source["url"]
        candidates.append(AuditCandidate(
            audit_id=item,
            event_time=str(source["event_time"] or ""),
            url=str(url or ""),
            domain=str(urlsplit(str(url or "")).hostname or ""),
            device=devices[0],
            status=str(source["status"] or ""),
            completion_status=str(source["completion_status"] or ""),
        ))
    result = preview_same_domain_candidates(candidates)
    result["index_reference"] = {
        "schema_version": version,
        "selected_audit_ids": list(ids),
        "read_only": True,
        "index_writes": 0,
        "source_audits_reopened_for_freshness": False,
        "source_package_freshness_verified": False,
        "native_cons3_created": False,
        "limitations": (
            "Prévia do índice analítico existente. Nenhuma AUD original foi "
            "reaberta para atestar frescor; conteúdo do índice pode estar defasado. "
            "Não é relatório CONS nem série temporal da mesma URL."
        ),
    }
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prévia consultiva por domínio de AUDs indexadas; sem gerar CONS."
    )
    parser.add_argument("--audits-root", type=Path, required=True)
    parser.add_argument("--audit-id", action="append", required=True,
                        help="Identificador de AUD; informe 2 ou mais vezes")
    args = parser.parse_args(argv)
    try:
        result = domain_preview_from_index(args.audits_root, args.audit_id)
    except (ValueError, sqlite3.DatabaseError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
