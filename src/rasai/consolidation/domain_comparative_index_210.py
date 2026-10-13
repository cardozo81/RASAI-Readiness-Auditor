"""#210: opt-in read-only local analytical-index entrypoint for domain preview.

This is NOT CONS-3 generation, not a native consolidation mode and not
authoritative freshness attestation of audit.db sources.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
from typing import Sequence
from urllib.parse import urlsplit

from rasai.consolidation.domain_comparative_preview_210 import preview_same_domain_candidates
from rasai.consolidation.reader import _audit_urls, _columns, _devices, source_file_fingerprint
from rasai.consolidation.selection import AuditCandidate

_AUD = re.compile(r"^AUD-[A-Za-z0-9-]{1,100}$")
_SOURCE_FINGERPRINT = re.compile(r"^[a-fA-F0-9]{64}$")
_SCHEMA_VERSION = 1


def _index_stamp(index: Path) -> tuple[int, int, int, int] | None:
    """Physical identity only; not a cryptographic byte seal."""
    try:
        if index.is_symlink() or index.parent.is_symlink() or not index.is_file():
            return None
        stat = index.stat()
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    except OSError:
        return None



def _verify_indexed_source(
    root: Path, audit_id: str, indexed_url: str,
    index_db_path: str, index_fingerprint: str, indexed_device: str,
) -> None:
    """Optional real-source metadata check; NOT cryptographic AUD attestation.

    Do not trust the indexed db_path for traversal. Only the AUD-ID-derived
    path is admissible. Source-fingerprint is path/size/mtime, not file SHA.
    """
    if index_db_path != f"{audit_id}/audit.db":
        raise ValueError("indexed AUD source path is not canonical")
    parent = root / audit_id
    source = parent / "audit.db"
    if (parent.is_symlink() or not parent.is_dir()
            or source.is_symlink() or not source.is_file()
            or parent.resolve().parent != root.resolve()):
        raise ValueError("physical AUD source missing or linked")
    if any((parent / (source.name + suffix)).exists()
           for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("physical AUD source has unverified SQLite sidecars")
    if source_file_fingerprint(source) != index_fingerprint.lower():
        raise ValueError("indexed AUD source metadata fingerprint mismatch")
    with closing(sqlite3.connect(
        source.resolve().as_uri() + "?mode=ro&immutable=1",
        uri=True, timeout=2,
    )) as con:
        con.execute("PRAGMA query_only=ON")
        required = {"audit_id", "status", "completion_status"}
        if not required.issubset(_columns(con, "audits")):
            raise ValueError("physical AUD metadata schema not verified")
        rows = con.execute(
            "SELECT audit_id, status, completion_status FROM audits LIMIT 2"
        ).fetchall()
        if (len(rows) != 1 or rows[0][0] != audit_id
                or str(rows[0][1]).strip().upper() != "COMPLETED"
                or str(rows[0][2]).strip().upper() != "COMPLETE"):
            raise ValueError("physical AUD identity/completion mismatch")
        urls = _audit_urls(con, audit_id)
        if len(urls) != 1 or urls[0] != indexed_url:
            raise ValueError("physical AUD indexed URL mismatch")
        # A cached single-device label cannot prove that the source AUD's
        # physically persisted snapshots were collected for that device.
        physical_devices = _devices(con, audit_id)
        if (len(physical_devices) != 1
                or physical_devices[0] != indexed_device.strip().upper()):
            raise ValueError("physical AUD indexed device mismatch or unverified")

    if (parent.is_symlink() or source.is_symlink() or not source.is_file()
            or any(Path(str(source) + suffix).exists()
                   for suffix in ("-wal", "-shm", "-journal"))
            or source_file_fingerprint(source) != index_fingerprint.lower()):
        raise ValueError("physical AUD source changed during metadata verification")


def domain_preview_from_index(
    audits_root: Path, audit_ids: Sequence[str], *,
    verify_source_metadata: bool = False,
) -> dict:
    """Reuse the index; optionally check original AUDs without any writes."""
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

    # immutable=1 is not a physical file lock. Do not use index rows when
    # the file identity/mtime changes before completing the full preview.
    index_before = _index_stamp(db)
    if index_before is None:
        raise ValueError("analytical index physical source not stable")
    with closing(sqlite3.connect(
        db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=3,
    )) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version != _SCHEMA_VERSION:
            raise ValueError("unsupported or uninitialized analytical index")
        for table, needed in (
            ("source_audits", {"audit_id", "event_time", "status",
                               "completion_status", "devices_json",
                               "url_count", "source_fingerprint",
                               *({"db_path"} if verify_source_metadata else set())}),
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
            "a.devices_json, a.url_count, a.source_fingerprint, u.url, "
            + ("a.db_path" if verify_source_metadata else "NULL AS db_path")
            + " FROM source_audits a LEFT JOIN audit_urls u ON u.audit_id=a.audit_id "
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
        if (not isinstance(raw_fingerprint, str)
                or not _SOURCE_FINGERPRINT.fullmatch(raw_fingerprint)):
            # Source freshness remains unverified even with a well-formed
            # cache fingerprint. An arbitrary marker must not become a
            # formally identified source in the comparison advisory.
            raise ValueError("source fingerprint absent or invalid")
        try:
            devices = json.loads(str(source["devices_json"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("devices inventory invalid") from exc
        if not isinstance(devices, list) or len(devices) != 1 or not isinstance(devices[0], str):
            raise ValueError("single-device AUD required")
        url = source["url"]
        if verify_source_metadata:
            _verify_indexed_source(
                root, item, str(url or ""), str(source["db_path"] or ""),
                raw_fingerprint, devices[0],
            )
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
        "source_audits_reopened_for_freshness": verify_source_metadata,
        "source_file_metadata_matched": verify_source_metadata,
        "source_url_identity_verified": verify_source_metadata,
        "source_fingerprints_by_audit": (
            {audit_id: by_id[audit_id][0]["source_fingerprint"].lower()
             for audit_id in ids} if verify_source_metadata else None
        ),
        # A path/size/mtime digest is not cryptographic byte attestation.
        "source_package_freshness_verified": False,
        "native_cons3_created": False,
        "limitations": (
            "Prévia do índice analítico existente. "
            + ("AUDs reabertas apenas em leitura para comparar identidade, URL, "
               "dispositivo físico e metadados do arquivo; "
               "fingerprint de cache não autentica bytes. "
               if verify_source_metadata else
               "Nenhuma AUD original foi reaberta para atestar frescor. ")
            + "O índice pode estar defasado ou não autenticado. "
            "Não é relatório CONS nem série temporal da mesma URL."
        ),
    }
    if (
        _index_stamp(db) != index_before
        or any(Path(str(db) + suffix).exists()
               for suffix in ("-wal", "-shm", "-journal"))
    ):
        raise ValueError("analytical index changed during read-only preview")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prévia consultiva por domínio de AUDs indexadas; sem gerar CONS."
    )
    parser.add_argument("--format", choices=("json", "html"), default="json",
                        help="Saída local: JSON por padrão ou HTML consultivo somente texto.")
    parser.add_argument("--audits-root", type=Path, required=True)
    parser.add_argument("--audit-id", action="append", required=True,
                        help="Identificador de AUD; informe 2 ou mais vezes")
    parser.add_argument("--verify-source-metadata", action="store_true",
                        help="Valida URL, AUD e path/size/mtime da fonte local sem escrita")
    args = parser.parse_args(argv)
    try:
        result = domain_preview_from_index(
            args.audits_root, args.audit_id,
            verify_source_metadata=args.verify_source_metadata,
        )
    except (ValueError, sqlite3.DatabaseError, OSError) as exc:
        parser.error(str(exc))
    if args.format == "html":
        from rasai.consolidation.domain_comparative_html_210 import render_same_domain_advisory_html
        print(render_same_domain_advisory_html(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
