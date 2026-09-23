"""Materialização CONS-5 do relatório consolidado longitudinal.

A renderização base é detalhe interno. Esta camada define a identidade materializada,
os contratos temporal e longitudinal e o fingerprint final.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
import hashlib
import json
import re
import shutil

from .catalog_longitudinal import CATALOG_LONGITUDINAL_CONTRACT
from .models import ConsolidationFilter, GenerationResult, RefreshResult
from .temporal_apdex import (
    TEMPORAL_APDEX_CONTRACT,
    TemporalApdexSeries,
    augment_manifest as augment_temporal_manifest,
    augment_report as augment_temporal_report,
)

REPORT_FORMAT_VERSION = "CONS-5"
LONGITUDINAL_CONTRACT = "CONSOLIDATED-LONGITUDINAL-001"
DECISION_CONTRACT = "CONSOLIDATED-DECISION-CONTEXT-002"
GOVERNANCE_CONTRACT = "CONSOLIDATED-SOURCE-GOVERNANCE-003"
MATERIALIZATION_CONTRACT = "CONSOLIDATED-MATERIALIZATION-003"


def request_fingerprint(source_fingerprint: str, filters: ConsolidationFilter) -> str:
    payload = {
        "report_format_version": REPORT_FORMAT_VERSION,
        "temporal_contract": TEMPORAL_APDEX_CONTRACT,
        "longitudinal_contract": LONGITUDINAL_CONTRACT,
        "catalog_contract": CATALOG_LONGITUDINAL_CONTRACT,
        "materialization_contract": MATERIALIZATION_CONTRACT,
        "filters": filters.canonical(),
        "source_fingerprint": source_fingerprint,
    }
    material = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _integrity_matches(
    report_dir: Path,
    integrity_files: dict[str, object],
    required_files: set[str],
) -> bool:
    for name in required_files:
        meta = integrity_files.get(name)
        if not isinstance(meta, dict):
            return False
        expected = str(meta.get("sha256") or "")
        path = report_dir / name
        if not expected or not path.is_file():
            return False
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            return False
    return True


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
        longitudinal = payload.get("longitudinal_analysis") or {}
        if payload.get("report_format_version") != REPORT_FORMAT_VERSION:
            continue
        if payload.get("request_fingerprint") != fingerprint:
            continue
        if payload.get("materialization_contract") != MATERIALIZATION_CONTRACT:
            continue
        if temporal.get("contract") != TEMPORAL_APDEX_CONTRACT:
            continue
        if longitudinal.get("contract") != LONGITUDINAL_CONTRACT:
            continue
        if longitudinal.get("catalog_contract") != CATALOG_LONGITUDINAL_CONTRACT:
            continue
        specialist = payload.get("specialist_ai") or {}
        ai_status = str(specialist.get("status") or longitudinal.get("ai_status") or "").upper()
        ai_requested = bool(specialist.get("requested"))
        if ai_requested:
            if ai_status != "COMPLETE":
                continue
        elif ai_status != "NOT_REQUESTED":
            continue
        decision = payload.get("decision_context") or {}
        governance = payload.get("source_governance") or {}
        integrity = payload.get("package_integrity") or {}
        if governance.get("contract") != GOVERNANCE_CONTRACT:
            continue
        if decision.get("contract") != DECISION_CONTRACT:
            continue
        required_files = {
            "report.html",
            "decision-context.json",
            "longitudinal-evidence.json",
            "execution.json",
        }
        if ai_status == "COMPLETE":
            required_files.update({
                "specialist-analysis.json",
                "ai-exchanges.json",
            })
        integrity_files = integrity.get("files") if isinstance(integrity, dict) else None
        if not isinstance(integrity_files, dict) or not required_files.issubset(set(integrity_files)):
            continue
        if not _integrity_matches(manifest_path.parent, integrity_files, required_files):
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
    payload["materialization_contract"] = MATERIALIZATION_CONTRACT
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
    """Materializa o artefato CONS-5 final a partir da renderização base interna."""
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
