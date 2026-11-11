"""Private, offline, copy-only physical acceptance of 21 report pages (#692).

Not a semantic or human approval. Do not point the output at an AUD tree.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import socket
from types import SimpleNamespace
from unittest.mock import patch

from rasai.catalog_report_contract import CATALOG_REPORT_PAGES
from rasai.document_advisory import _inventory, _plain, _snapshots
from rasai.report_temporal_inventory import _LOCAL, inventory
from rasai.time_contract import _AWARE_ISO_TIMESTAMP_RE, presentation_timezone_for_audit


class _NonTemporalTokens(HTMLParser):
    """Compare renderer output without equating actual timestamps to other text."""

    def __init__(self, html: str):
        super().__init__(convert_charrefs=False)
        self.tokens: list[tuple | str] = []
        self.stack: list[str] = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tokens.append(("start", self.get_starttag_text()))
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.tokens.append(("empty", self.get_starttag_text()))

    def handle_endtag(self, tag):
        self.tokens.append(("end", tag))
        if tag in self.stack:
            del self.stack[len(self.stack) - 1 - self.stack[::-1].index(tag):]

    def handle_data(self, data):
        if not any(tag in {"code", "pre", "script", "style"} for tag in self.stack):
            data = _LOCAL.sub("INSTANT", _AWARE_ISO_TIMESTAMP_RE.sub("INSTANT", data))
        self.tokens.append(("text", data))

    def handle_entityref(self, name):
        self.tokens.append(("entity", name))

    def handle_charref(self, name):
        self.tokens.append(("charref", name))

    def handle_comment(self, data):
        self.tokens.append(("comment", data))

    def handle_decl(self, decl):
        self.tokens.append(("decl", decl))


def _preflight(source: Path, target: Path) -> tuple[Path, Path]:
    source, target = _plain(source), _plain(target)
    if not source.is_dir() or not (source / "audit.db").is_file():
        raise ValueError("source AUD unavailable")
    if not source.name.startswith("AUD-"):
        raise ValueError("source must be an AUD directory")
    if target.exists() or target.is_symlink():
        raise ValueError("destination must be new")
    if not target.parent.is_dir():
        raise ValueError("dedicated private parent must already exist")
    if target.resolve().is_relative_to(source.resolve()) or source.resolve().is_relative_to(target.resolve()):
        raise ValueError("output must be outside source tree")
    if any(p.name.startswith(("AUD-", "RPR-", "CONS-")) for p in (target, *target.parents)):
        raise ValueError("output must not be placed in a historical tree")
    return source, target


def verify_copy(source: Path, target: Path) -> dict:
    """Copy the complete sealed source, rematerialize on copy, verify physical gates.

    The source tree is only read. Every generated file stays in target.
    Raised errors are not converted into successful acceptance states.
    """
    source, target = _preflight(Path(source), Path(target))
    _snapshots(source)  # AUD identity/status and SQLite-sidecar policy
    before = _inventory(source)
    target.mkdir(mode=0o700)
    result = {
        "contract": "RASAI-692-PHYSICAL-TEMPORAL-ACCEPTANCE-001",
        "status": "FAIL",
        "audit_id": source.name,
        "source_files": len(before),
        "source_unchanged": False,
        "page_count": 0,
        "temporal_21_pages": "N/D",
        "non_temporal_21_pages": "N/D",
        "human_review": "N/D",
        "network_attempts_blocked": 0,
        "provider_calls": "N/D",
        "limitations": [
            "DERIVED_COPY_ONLY_NOT_HISTORICAL_REPORT_REWRITE",
            "NODE_SCANNER_IS_NOT_EXHAUSTIVE_TYPED_FIELD_PROOF",
            "HUMAN_AND_VISUAL_ACCEPTANCE_NOT_AUTOMATED",
            "SOCKET_GUARD_DOES_NOT_PROVE_ABSENCE_OF_CHILD_PROCESS_NETWORK",
        ],
    }
    error = None
    try:
        copy = target / source.name
        shutil.copytree(source, copy, symlinks=False)
        if _inventory(copy) != before:
            raise RuntimeError("copied source differs from original inventory")

        from rasai import catalog_report_presentation as presentation
        from rasai.catalog_report_site import (
            _load_data, materialize_catalog_report_site, verify_catalog_report_package,
        )

        zone, source_field = presentation_timezone_for_audit(
            _load_data(source.name, copy / "audit.db").configuration
        )
        original = presentation.localize_html_timestamps
        compared = []
        attempted = []

        def guarded_connect(*args, **kwargs):
            attempted.append("NETWORK_DENIED")
            raise RuntimeError("network forbidden in private offline acceptance")

        def checked(html, **kwargs):
            rendered = original(html, **kwargs)
            if _NonTemporalTokens(html).tokens != _NonTemporalTokens(rendered).tokens:
                raise RuntimeError("non-temporal HTML structure/content changed by timezone localization")
            compared.append(True)
            return rendered

        with ExitStack() as stack:
            stack.enter_context(patch.object(socket.socket, "connect", guarded_connect))
            stack.enter_context(patch.object(socket, "create_connection", guarded_connect))
            stack.enter_context(patch.object(presentation, "localize_html_timestamps", checked))
            workspace = SimpleNamespace(root=copy, database=copy / "audit.db")
            report = materialize_catalog_report_site(audit_id=source.name, workspace=workspace).parent

        result["network_attempts_blocked"] = len(attempted)
        if attempted:
            raise RuntimeError("network attempted during materialization")
        if len(compared) != len(CATALOG_REPORT_PAGES):
            raise RuntimeError("not every page passed non-temporal parity")
        ok, errors = verify_catalog_report_package(report)
        if not ok:
            raise RuntimeError("derived report package integrity rejected: " + str(len(errors)))

        evidence = inventory(report, zone=zone)
        if len(evidence["pages"]) != len(CATALOG_REPORT_PAGES):
            raise RuntimeError("catalog page coverage incomplete")
        (target / "temporal-inventory.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        result.update(
            status="PASS_TECHNICAL",
            page_count=len(evidence["pages"]),
            source_timezone=zone,
            timezone_source=source_field,
            derived_report_integrity="PASS",
            non_temporal_21_pages="PASS_FOCAL_LOCALIZER_PARITY",
            temporal_21_pages="REVIEW_REQUIRED",
            historical_report_pages=sum((source / "report-catalog" / p.filename).is_file()
                                        for p in CATALOG_REPORT_PAGES),
            temporal_summary=evidence["summary"],
            network_attempts_blocked=len(attempted),
            provider_calls="NOT_INSTRUMENTED_USE_OFFLINE_GUARD",
        )
    except Exception as exc:
        error = exc
        result["error_type"] = type(exc).__name__
    finally:
        try:
            result["source_unchanged"] = before == _inventory(source)
            if not result["source_unchanged"]:
                result["status"] = "FAIL"
        except Exception:
            result["status"] = "FAIL"
            result["source_unchanged"] = False
            result["source_inventory_after"] = "UNAVAILABLE"
        (target / "temporal-acceptance.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if error is not None:
        raise RuntimeError("physical temporal acceptance failed; inspect private evidence") from error
    if result["status"] != "PASS_TECHNICAL" or not result["source_unchanged"]:
        raise RuntimeError("temporal acceptance did not pass physical integrity gate")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Rematerialização temporal 21 páginas em cópia privada.")
    parser.add_argument("--audit-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    proof = verify_copy(args.audit_dir, args.output_dir)
    print(json.dumps({k: proof[k] for k in (
        "status", "source_unchanged", "page_count", "source_timezone",
        "temporal_21_pages", "non_temporal_21_pages", "human_review"
    )}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
