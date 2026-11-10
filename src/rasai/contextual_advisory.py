"""Offline contextual companion; uses #656 read-only paths and full AUD parity.

No documents are opened and no provider/runtime is instantiated. Canonical
renderers call load_projection once; historical AUDs use build_companion only.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

from rasai.catalog_source_dependencies import record_source_dependency
from rasai.contextual_content import CONTRACT, MAX_BYTES, observe_content
from rasai.contextual_documents import digest
from rasai.contextual_editorial import ai_availability, recommendations
from rasai.contextual_semantics import CONTRACT as SEMANTIC_CONTRACT, report_overlay
from rasai.contextual_faq_aria import CONTRACT as FAQ_ARIA_CONTRACT, report_overlay as faq_aria_report_overlay
from rasai.contextual_page_structure import CONTRACT as PAGE_STRUCTURE_CONTRACT, report_overlay as page_structure_report_overlay
from rasai.contextual_reverse_review import CONTRACT as REVERSE_REVIEW_CONTRACT, review_projection
from rasai.document_advisory import _inventory, _member, _plain, _read, _snapshots


def _worker(payload, *args):
    child = subprocess.run([sys.executable, "-m", "rasai.contextual_content_worker", *args],
        input=json.dumps(payload).encode(), stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, timeout=5, check=False)
    if child.returncode or len(child.stdout) > 5_000_000:
        raise ValueError("contextual resource limit")
    return json.loads(child.stdout)


def _observe(audit_id, snapshot, original, ref, surface):
    if original is not None:
        try:
            return _worker(dict(audit_id=audit_id, snapshot_id=snapshot.snapshot_id,
                page_id=snapshot.page_id, device=snapshot.device.value, requested_url=snapshot.requested_url,
                final_url=snapshot.final_url, captured_at=snapshot.captured_at.isoformat(),
                original=base64.b64encode(original).decode("ascii"), source_ref=ref, surface=surface))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    result = observe_content(audit_id=audit_id, snapshot=snapshot, original=None, source_ref=ref, surface=surface)
    if original is not None:
        result["source_sha256"] = digest(original)
        result["limitations"].append("PROCESSING_RESOURCE_LIMIT_ND")
    return result


def _frozen_companion_timezone(root: Path) -> dict:
    """Read the same execution configuration as the canonical catalog, read-only."""
    from contextlib import closing
    from rasai.catalog_report_model import _load_configuration
    from rasai.time_contract import presentation_timezone_for_audit
    database = _member(root, "audit.db")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=2)) as con:
        con.execute("PRAGMA query_only=ON")
        con.row_factory = sqlite3.Row
        configuration, _, _ = _load_configuration(con, root.name)
    name, provenance = presentation_timezone_for_audit(configuration)
    return dict(timezone=name, source=provenance)


def load_projection(audit_dir: Path, *, ai="none") -> dict:
    root = _plain(audit_dir)
    if _member(root, "audit.db").stat().st_size > 256 * 1024 * 1024:
        raise ValueError("contextual database byte policy")
    result = dict(contract=CONTRACT, audit_id=root.name, captures=[], recommendations=[],
                  ai=ai_availability(ai), network_requests=0, audit_writes=0,
                  limitations=["CONSULTATIVE_ONLY", "NO_ENTITY_OR_PRODUCT_AUTHENTICATION",
                               "PRIVATE_COMPANION_CONTAINS_CAPTURED_TEXT_DO_NOT_PUBLISH"])
    snapshots = _snapshots(root)
    result["presentation"] = _frozen_companion_timezone(root)
    total, emitted, deadline = 0, 0, time.monotonic() + 30
    for snapshot in snapshots:
        if any(value is not None and (not isinstance(value, str) or len(value) > 4096)
               for value in (snapshot.requested_url, snapshot.final_url, snapshot.page_id, snapshot.snapshot_id)):
            raise ValueError("contextual identity field limit")
        original, ref, surface, limitations = None, None, "NOT_CAPTURED", []
        for name, candidate in (("RENDERED_DOM", snapshot.rendered_artifact_ref),
                                ("RAW_HTML_FALLBACK", snapshot.raw_artifact_ref)):
            if not candidate:
                continue
            if not candidate.startswith("artifacts/"):
                raise ValueError("capture must be under canonical artifacts")
            path = _member(root, candidate)
            if time.monotonic() > deadline or total >= 20_000_000:
                limitations.append("AUD_PROCESSING_BUDGET_ND")
                break
            try:
                original = _read(path, min(MAX_BYTES, 20_000_000 - total))
            except (OSError, ValueError):
                # Register absence too, so newly present captures invalidate a
                # rematerialized package. Do not hash over-limit input here.
                if not path.exists():
                    record_source_dependency(path)
                limitations.append(name + "_MISSING_OR_BYTE_LIMIT_ND")
                continue
            record_source_dependency(path)
            total += len(original)
            ref, surface = candidate, name
            break
        capture = _observe(root.name, snapshot, original, ref, surface)
        capture["limitations"].extend(limitations)
        remaining = max(0, 2000 - emitted)
        if len(capture["occurrences"]) > remaining:
            capture["counts"]["omitted"] += len(capture["occurrences"]) - remaining
            capture["occurrences"] = capture["occurrences"][:remaining]
            capture["limitations"].append("AUD_OCCURRENCE_LIMIT_PARTIAL")
        emitted += len(capture["occurrences"])
        result["captures"].append(capture)
    result["recommendations"] = recommendations(result["captures"])
    try:
        search_captures = [{**{k: c[k] for k in ("audit_id", "snapshot_id", "captured_at", "device", "source_ref",
                            "source_sha256", "requested_url", "final_url_observed")},
                            "occurrences": [{k: o[k] for k in ("occurrence_id", "category")} for o in c["occurrences"]]}
                           for c in result["captures"]]
        result["search"] = _worker(search_captures, "--search", str(root))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        result["search"] = dict(status="NOT_COMPARABLE", reason="SEARCH_RESOURCE_OR_SCHEMA_LIMIT_ND",
                                 observations=[], limitations=[], provider_calls=0)
    result["semantic_v2"] = report_overlay(result["captures"], result["recommendations"])
    result["faq_aria_v3"] = faq_aria_report_overlay(result["captures"])
    result["content_structure_v3"] = page_structure_report_overlay(result["captures"])
    result["reverse_review"] = review_projection(result)
    for capture in result["captures"]:
        capture.pop("semantic_overlay_v2", None)  # publish v1 captures verbatim
        capture.pop("faq_aria_overlay_v3", None)
        capture.pop("page_structure_overlay_v3", None)
    return result


def build_companion(audit_dir: Path, output: Path, *, ai="none") -> dict:
    root, destination = _plain(audit_dir), _plain(output)
    if not root.is_dir() or not root.name.startswith("AUD-"):
        raise ValueError("canonical AUD required")
    if (destination.exists() or destination.resolve().is_relative_to(root.resolve())
            or root.resolve().is_relative_to(destination.resolve())
            or any(p.name.startswith(("AUD-", "RPR-", "CONS-")) for p in (destination, *destination.parents))):
        raise ValueError("new output external to historical packages required")
    before = _inventory(root)
    report = load_projection(root, ai=ai)
    report.update(source_inventory=before, source_unchanged=False)
    from rasai.contextual_advisory_html import companion_pages
    pages = companion_pages(report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".contextual-", dir=destination.parent) as temporary:
        stage = Path(temporary) / "companion"
        stage.mkdir(mode=0o700)
        (stage / "evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        for name, content in pages.items():
            (stage / name).parent.mkdir(parents=True, exist_ok=True)
            (stage / name).write_text(content, encoding="utf-8")
        if _inventory(root) != before:
            raise ValueError("AUD changed; publication refused")
        report["source_unchanged"] = True
        (stage / "evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = dict(contract="contextual-companion-manifest-v1", source_inventory=before,
            source_unchanged=True, output_inventory=_inventory(stage), network_requests=0,
            provider_calls=0, audit_writes=0, semantic_overlay_contract=SEMANTIC_CONTRACT, faq_aria_contract=FAQ_ARIA_CONTRACT, page_structure_contract=PAGE_STRUCTURE_CONTRACT,
            reverse_review_contract=REVERSE_REVIEW_CONTRACT)
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        _plain(destination)
        if destination.exists() or _inventory(root) != before:
            raise ValueError("output collision or AUD changed")
        stage.rename(destination)
    return report


def summary_counts(report):
    """Console-safe homologation summary: counts and N/D reason, no literals."""
    return dict(captures=len(report["captures"]), recommendations=len(report["recommendations"]),
        raw_v1_occurrences=sum(len(c["occurrences"]) for c in report["captures"]),
        semantic_v2_counts=report["semantic_v2"]["counts"],
        faq_aria_v3_counts=report["faq_aria_v3"]["counts"],
        content_structure_v3_counts=report["content_structure_v3"]["counts"],
        recommendation_v2_counts=report["semantic_v2"]["recommendation_counts"],
        reverse_review_counts=report["reverse_review"]["counts"],
        search_reason=report["search"]["reason"], source_unchanged=report["source_unchanged"],
        network_requests=0, provider_calls=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Companheiro contextual privado, offline, sem alterar AUD.")
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ai", choices=("none", "requested"), default="none")
    args = parser.parse_args(argv)
    try:
        report = build_companion(args.audit_dir, args.output, ai=args.ai)
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        print("N/D: entrada, integridade ou limites recusados. Nenhum provedor chamado.")
        return 2
    print(json.dumps(summary_counts(report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
