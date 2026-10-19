"""#600/#604: strictly local HTML-vs-SQLite decision matrix parity gate.

Reads the existing, integrity-verified catalog report package and compares
actual <tbody> cells, not arbitrary page text or JavaScript, against the
read-only decision projection from that same AUD. Does not render, write, score,
open a browser or claim regulatory/market/sample certification.
"""
from __future__ import annotations

from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
from typing import Any, Mapping

from rasai.catalog_report_contract import CATALOG_REPORT_DIR

_CONTRACT = "RASAI-REPORT-HTML-PARITY-600-001"
_MARKER = "DECISION-EVIDENCE-604-001"
_MAX_HTML_BYTES = 4 * 1024 * 1024
_MAX_MANIFEST_BYTES = 1024 * 1024
_COLUMNS = ("indicator", "observed", "scope", "source", "limitation")
_SARI = frozenset({"SARI", "Dimensões SARI com cobertura não integral"})
_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})


class _DecisionTable(HTMLParser):
    """Only parse a real decision-matrix tbody inside the right report section."""

    def __init__(self, section_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.section_id = section_id
        self.stack: list[tuple[str, dict[str, str | None]]] = []
        self.section_count = 0
        self.marker_count = 0
        self.closed = 0
        self.tbody_count = 0
        self.table_count = 0
        self.rows: list[tuple[str, ...]] = []
        self.marker_depth: int | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.invalid = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "section" and attributes.get("id") == self.section_id:
            self.section_count += 1
        if tag == "div" and attributes.get("data-contract") == _MARKER:
            self.marker_count += 1
            section_parent = any(
                kind == "section" and values.get("id") == self.section_id
                for kind, values in self.stack
            )
            if not section_parent or self.marker_depth is not None:
                self.invalid = True
            else:
                self.marker_depth = len(self.stack)
        elif self.marker_depth is not None:
            if tag == "table":
                self.table_count += 1
            elif tag == "tbody":
                self.tbody_count += 1
            elif tag == "tr" and self.tbody_count == 1:
                if self.row is not None:
                    self.invalid = True
                self.row = []
            elif tag == "td" and self.row is not None:
                if self.cell is not None:
                    self.invalid = True
                self.cell = []
        if tag not in _VOID:
            self.stack.append((tag, attributes))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.marker_depth is not None and self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.marker_depth is not None:
            if tag == "td" and self.cell is not None and self.row is not None:
                self.row.append("".join(self.cell).strip())
                self.cell = None
            elif tag == "tr" and self.row is not None:
                if self.cell is not None:
                    self.invalid = True
                self.rows.append(tuple(self.row))
                self.row = None
        if tag in _VOID:
            return
        while self.stack:
            popped, _attributes = self.stack.pop()
            if popped == tag:
                break
        else:
            self.invalid = True
        # marker_depth is the length of the parent stack BEFORE marker start.
        if self.marker_depth is not None and len(self.stack) <= self.marker_depth:
            if tag != "div" or self.cell is not None or self.row is not None:
                self.invalid = True
            self.marker_depth = None
            self.closed += 1

    def valid(self) -> bool:
        return (not self.invalid and self.section_count == 1
                and self.marker_count == 1 and self.closed == 1
                and self.table_count == 1 and self.tbody_count == 1
                and self.marker_depth is None
                and all(len(row) == len(_COLUMNS) for row in self.rows))


def _bounded_verified_file(path: Path, expected_sha256: str, limit: int) -> bytes | None:
    if (not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or any(letter not in "0123456789abcdef" for letter in expected_sha256)):
        return None
    if path.is_symlink() or not path.is_file():
        return None
    before = path.stat()
    if not 0 < before.st_size <= limit:
        return None
    with path.open("rb") as opened:
        descriptor = os.fstat(opened.fileno())
        data = opened.read(limit + 1)
    after = path.stat()
    identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if (path.is_symlink() or len(data) != before.st_size
            or any(getattr(before, field) != getattr(item, field)
                   for item in (descriptor, after) for field in identity)
            or sha256(data).hexdigest() != expected_sha256):
        return None
    return data


def _expected(rows: list[dict[str, Any]], sari_only: bool) -> tuple[tuple[str, ...], ...]:
    subset = (
        (row for row in rows if str(row.get("indicator") or "").startswith("SARI /")
         or row.get("indicator") in _SARI)
        if sari_only else iter(rows)
    )
    return tuple(
        tuple(str(row.get(column) or "N/D") for column in _COLUMNS)
        for row in subset
    )


def inspect_decision_html_parity(
    audit_directory: Path, projection: Mapping[str, Any],
) -> dict[str, Any]:
    """Reject stale or partial rendering, without leaking evidence values.

    The manifest/package hash authenticates local package *integrity only*;
    this diagnostic does not authenticate a browser view, physical sampling,
    published external content, live-provider access or score methodology.
    """
    base: dict[str, Any] = {
        "contract": _CONTRACT, "status": "NOT_VERIFIABLE",
        "index_matrix_rows": None, "sari_matrix_rows": None,
        "source": "SEALED_AUD_AND_REPORT_PACKAGE_REQUIRED",
        "values_exposed": False, "browser_inspection_verified": False,
        "external_requests": 0, "audit_writes": 0,
        "scoring_modified": False, "normative_acceptance": False,
        "aud_source_snapshot_matches_report": False,
    }
    if (not isinstance(projection, Mapping)
            or projection.get("status") != "DESCRIPTIVE_ONLY"
            or projection.get("contract") != "RASAI-DECISION-EVIDENCE-604-001"
            or not isinstance(projection.get("rows"), list)):
        return base
    try:
        root = Path(audit_directory)
        if (root.is_symlink() or not root.is_dir()
                or not root.name.startswith("AUD-")
                or projection.get("audit_id") != root.name):
            return {**base, "status": "AUD_SCOPE_MISMATCH"}
        report = root / CATALOG_REPORT_DIR
        manifest_file = report / "manifest.json"
        if report.is_symlink() or not report.is_dir():
            return {**base, "status": "REPORT_PACKAGE_UNAVAILABLE"}
        # The canonical verifier checks all packaged members, integrity
        # snapshot and consistency before any semantic comparison.
        from rasai.catalog_report_site import verify_catalog_report_package
        ok, _detail = verify_catalog_report_package(report)
        if not ok:
            return {**base, "status": "REPORT_PACKAGE_INTEGRITY_UNVERIFIED"}
        if manifest_file.is_symlink() or not manifest_file.is_file():
            return {**base, "status": "REPORT_PACKAGE_INTEGRITY_UNVERIFIED"}
        size = manifest_file.stat().st_size
        if not 0 < size <= _MAX_MANIFEST_BYTES:
            return {**base, "status": "REPORT_PACKAGE_INTEGRITY_UNVERIFIED"}
        manifest = json.loads(manifest_file.read_bytes().decode("utf-8"))
        if (not isinstance(manifest, dict)
                or manifest.get("audit_id") != root.name
                or manifest.get("freshness") != "FINAL"):
            return {**base, "status": "REPORT_PACKAGE_AUD_MISMATCH"}
        # A self-consistent package can still be STALE compared to its
        # originating AUD. Verify the actual AUD's *logical* SQLite contents
        # against the source digest recorded at report materialization.
        # A digest of the report snapshot alone would not catch this.
        origin_db = root / "audit.db"
        if (origin_db.is_symlink() or not origin_db.is_file()
                or not 0 < origin_db.stat().st_size <= 512 * 1024 * 1024):
            return {**base, "status": "AUD_SOURCE_UNAVAILABLE"}
        if any(Path(str(origin_db) + suffix).exists()
               for suffix in ("-wal", "-shm", "-journal")):
            return {**base, "status": "AUD_SOURCE_NOT_SEALED"}
        source_record = manifest.get("audit_snapshot")
        digest = (
            source_record.get("source_logical_sha256")
            if isinstance(source_record, dict) else None
        )
        if (not isinstance(digest, str) or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)):
            return {**base, "status": "AUD_REPORT_SOURCE_BINDING_ABSENT"}
        from rasai.catalog_report_site import _sqlite_logical_digest
        start = origin_db.stat()
        if _sqlite_logical_digest(origin_db) != digest:
            return {**base, "status": "AUD_REPORT_SOURCE_STALE"}
        stop = origin_db.stat()
        if (origin_db.is_symlink()
                or any(getattr(start, name) != getattr(stop, name)
                       for name in ("st_dev", "st_ino", "st_size", "st_mtime_ns"))
                or any(Path(str(origin_db) + suffix).exists()
                       for suffix in ("-wal", "-shm", "-journal"))):
            return {**base, "status": "AUD_SOURCE_CHANGED_DURING_READ"}
        files = manifest.get("packaged_files")
        if not isinstance(files, list) or len(files) > 1000:
            return {**base, "status": "REPORT_PACKAGE_INTEGRITY_UNVERIFIED"}
        records: dict[str, str] = {}
        for row in files:
            if not isinstance(row, dict):
                return {**base, "status": "REPORT_PACKAGE_INTEGRITY_UNVERIFIED"}
            name = row.get("path")
            digest = row.get("sha256")
            if name in {"index.html", "sari.html"}:
                if name in records:
                    return {**base, "status": "REPORT_PACKAGE_INTEGRITY_UNVERIFIED"}
                records[name] = digest
        if set(records) != {"index.html", "sari.html"}:
            return {**base, "status": "REPORT_PACKAGE_INTEGRITY_UNVERIFIED"}
        expected_rows = projection["rows"]
        if len(expected_rows) > 32 or any(
            not isinstance(row, Mapping) for row in expected_rows
        ):
            return base
        # A byte-for-byte matching report with no persisted SARI evidence
        # is NOT sufficient proof of SARI coverage/readiness. It is a valid
        # incomplete report but not an evidence-parity acceptance.
        sari_expected = _expected(expected_rows, True)
        if not sari_expected or not any(
            row[0].startswith("SARI /") for row in sari_expected
        ):
            return {**base, "status": "SARI_PHYSICAL_EVIDENCE_ABSENT"}
        totals = {}
        for name, section, sari_only in (
            ("index.html", "decision-matrix", False),
            ("sari.html", "scope", True),
        ):
            content = _bounded_verified_file(
                report / name, records[name], _MAX_HTML_BYTES,
            )
            if content is None:
                return {**base, "status": "REPORT_HTML_SOURCE_UNVERIFIABLE"}
            parser = _DecisionTable(section)
            parser.feed(content.decode("utf-8"))
            parser.close()
            expected = _expected(expected_rows, sari_only)
            if not parser.valid() or parser.rows != list(expected):
                return {**base, "status": (
                    "SARI_HTML_MATRIX_MISMATCH" if sari_only
                    else "INDEX_HTML_MATRIX_MISMATCH"
                )}
            totals["sari_matrix_rows" if sari_only else "index_matrix_rows"] = len(expected)
        return {
            **base, "status": "HTML_MATRIX_PARITY_VERIFIED", **totals,
            "source": "SEALED_LOCAL_REPORT_PACKAGE_MATCHES_AUD_DECISION_PROJECTION",
            "aud_source_snapshot_matches_report": True,
        }
    except (OSError, TypeError, ValueError, UnicodeError, OverflowError, __import__("sqlite3").Error):
        return base


__all__ = ["inspect_decision_html_parity"]
