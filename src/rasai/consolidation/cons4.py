"""CONS-4 materialization for temporal consolidated reports.

The base renderer is an internal implementation detail. This layer owns the
materialized CONS-4 identity, temporal contract and final request fingerprint.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
import hashlib
import json
import re
import shutil

from .models import ConsolidationFilter, GenerationResult, RefreshResult
from .temporal_apdex import (
    TEMPORAL_APDEX_CONTRACT,
    TemporalApdexSeries,
    augment_manifest as augment_temporal_manifest,
    augment_report as augment_temporal_report,
)

REPORT_FORMAT_VERSION = "CONS-4"


def request_fingerprint(source_fingerprint: str, filters: ConsolidationFilter) -> str:
    payload = {
        "report_format_version": REPORT_FORMAT_VERSION,
        "temporal_contract": TEMPORAL_APDEX_CONTRACT,
        "filters": filters.canonical(),
        "source_fingerprint": source_fingerprint,
    }
    material = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def find_existing(
    audits_root: str | Path,
    fingerprint: str,
    refresh: RefreshResult,
) -> GenerationResult | None:
    output_root = Path(audits_root) / "consolidated"
    if not output_root.is_dir():
        return None
    for manifest_path in sorted(output_root.glob("CONS-*/manifest.json"), reverse=True):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        temporal = payload.get("temporal_apdex") or {}
        if payload.get("report_format_version") != REPORT_FORMAT_VERSION:
            continue
        if payload.get("request_fingerprint") != fingerprint:
            continue
        if temporal.get("contract") != TEMPORAL_APDEX_CONTRACT:
            continue
        report_path = manifest_path.parent / "report.html"
        if not report_path.is_file():
            continue
        return GenerationResult(
            report_dir=manifest_path.parent,
            report_path=report_path,
            manifest_path=manifest_path,
            reused=True,
            request_fingerprint=fingerprint,
            refresh=refresh,
        )
    return None


def _upgrade_footer(path: Path, fingerprint: str) -> None:
    html = path.read_text(encoding="utf-8")
    rendered = re.sub(
        r"formato CONS-\d+ · fingerprint [^<]+",
        f"formato {REPORT_FORMAT_VERSION} · fingerprint {escape(fingerprint)}",
        html,
        count=1,
    )
    if rendered != html:
        path.write_text(rendered, encoding="utf-8", newline="\n")


def _upgrade_manifest(
    path: Path,
    *,
    fingerprint: str,
    source_fingerprint: str,
    base_request_fingerprint: str | None,
    cons_id: str | None,
    generated_at: str | None,
) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["report_format_version"] = REPORT_FORMAT_VERSION
    payload["request_fingerprint"] = fingerprint
    payload["source_fingerprint"] = source_fingerprint
    if cons_id:
        payload["cons_id"] = cons_id
    if generated_at:
        payload["generated_at"] = generated_at
    temporal = payload.setdefault("temporal_apdex", {})
    temporal["report_format_version"] = REPORT_FORMAT_VERSION
    temporal["base_request_fingerprint"] = base_request_fingerprint
    temporal.pop("legacy_request_fingerprint", None)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def materialize(
    *,
    audits_root: str | Path,
    base_result: GenerationResult,
    source_fingerprint: str,
    filters: ConsolidationFilter,
    series: tuple[TemporalApdexSeries, ...],
) -> GenerationResult:
    """Materialize the final CONS-4 artifact from the internal base renderer output."""
    root = Path(audits_root)
    fingerprint = request_fingerprint(source_fingerprint, filters)
    report_dir = base_result.report_dir
    report_path = base_result.report_path
    manifest_path = base_result.manifest_path
    generated_at: str | None = None
    cons_id: str | None = None

    try:
        base_manifest = json.loads(base_result.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        base_manifest = {}
    base_request_fingerprint = str(base_manifest.get("request_fingerprint") or "") or None

    if base_result.reused:
        now = datetime.now().astimezone()
        cons_id = now.strftime("CONS-%Y%m%d-%H%M%S-%f")[:-3]
        report_dir = root / "consolidated" / cons_id
        report_dir.mkdir(parents=True, exist_ok=False)
        report_path = report_dir / "report.html"
        manifest_path = report_dir / "manifest.json"
        shutil.copyfile(base_result.report_path, report_path)
        shutil.copyfile(base_result.manifest_path, manifest_path)
        generated_at = now.isoformat()

    if series and not augment_temporal_report(report_path, series):
        raise RuntimeError("falha ao materializar seção temporal do relatório consolidado")
    if not augment_temporal_manifest(manifest_path, series):
        raise RuntimeError("falha ao materializar manifest temporal do relatório consolidado")
    _upgrade_footer(report_path, fingerprint)
    _upgrade_manifest(
        manifest_path,
        fingerprint=fingerprint,
        source_fingerprint=source_fingerprint,
        base_request_fingerprint=base_request_fingerprint,
        cons_id=cons_id,
        generated_at=generated_at,
    )
    return GenerationResult(
        report_dir=report_dir,
        report_path=report_path,
        manifest_path=manifest_path,
        reused=False,
        request_fingerprint=fingerprint,
        refresh=base_result.refresh,
    )
