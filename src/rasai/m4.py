"""M4 execution glue: deterministic extraction, artifacts and first-class evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path

from rasai.domain import DeviceContext, EvidenceType, PageSnapshot
from rasai.evidence import EvidenceManager
from rasai.extraction import ContentExtractor, ExtractedPage, StructuredDataBlock
from rasai.extraction_persistence import SnapshotExtractionWriter
from rasai.m3 import M3ExecutionResult
from rasai.persistence import AuditPersistence, AuditWorkspace


@dataclass(frozen=True, slots=True)
class ExtractionFailure:
    page_id: str
    snapshot_id: str
    device: DeviceContext
    error_kind: str


@dataclass(frozen=True, slots=True)
class M4ExecutionResult:
    evidence_ids: dict[str, tuple[str, ...]]
    failures: tuple[ExtractionFailure, ...]


def execute_m4(
    m3_result: M3ExecutionResult,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
    *,
    extractor: ContentExtractor | None = None,
) -> M4ExecutionResult:
    """Extract each M3 snapshot independently and persist evidence-backed outputs."""

    active_extractor = extractor or ContentExtractor()
    manager = EvidenceManager(persistence)
    writer = SnapshotExtractionWriter(workspace)
    evidence_ids: dict[str, tuple[str, ...]] = {}
    failures: list[ExtractionFailure] = []

    for page_id, per_device in m3_result.snapshot_ids.items():
        page = persistence.pages.get(page_id)
        if page is None:
            raise ValueError(f"M3 page mapping references missing page {page_id}")

        for device, snapshot_id in per_device.items():
            snapshot = persistence.snapshots.get(snapshot_id)
            if snapshot is None or snapshot.page_id != page_id or snapshot.device != device:
                raise ValueError(f"M3 snapshot mapping is inconsistent for {snapshot_id}")

            source = _load_extraction_input(snapshot, workspace)
            if source is None:
                evidence_ids[snapshot_id] = ()
                failures.append(
                    ExtractionFailure(
                        page_id=page_id,
                        snapshot_id=snapshot_id,
                        device=device,
                        error_kind="EXTRACTION_INPUT_UNAVAILABLE",
                    )
                )
                continue
            source_name, source_ref, html = source

            try:
                extracted = active_extractor.extract(html)
                main_content_ref = _write_main_content(workspace, snapshot, extracted.main_content)
                structured_data_ref = _write_structured_data(workspace, snapshot, extracted.structured_data)
                enriched = replace(
                    snapshot,
                    title=extracted.title,
                    description=extracted.description,
                    canonical=extracted.canonical,
                    meta_robots=extracted.meta_robots,
                    main_content_ref=main_content_ref,
                    structured_data_ref=structured_data_ref,
                )
                writer.update(enriched)
                ids = _record_extraction_evidence(
                    manager,
                    audit_id=page.audit_id,
                    snapshot=enriched,
                    source_name=source_name,
                    source_ref=source_ref,
                    extracted=extracted,
                )
                evidence_ids[snapshot_id] = tuple(ids)
            except Exception:
                evidence_ids[snapshot_id] = ()
                failures.append(
                    ExtractionFailure(
                        page_id=page_id,
                        snapshot_id=snapshot_id,
                        device=device,
                        error_kind="EXTRACTION_ERROR",
                    )
                )

    return M4ExecutionResult(evidence_ids=evidence_ids, failures=tuple(failures))


def _load_extraction_input(
    snapshot: PageSnapshot,
    workspace: AuditWorkspace,
) -> tuple[str, str, str] | None:
    candidates = (
        ("RENDERED_DOM", snapshot.rendered_artifact_ref),
        ("RAW_HTML_FALLBACK", snapshot.raw_artifact_ref),
    )
    for source_name, artifact_ref in candidates:
        if not artifact_ref:
            continue
        path = workspace.root / artifact_ref
        if not path.is_file():
            continue
        return source_name, artifact_ref, path.read_text(encoding="utf-8", errors="replace")
    return None


def _artifact_directory(workspace: AuditWorkspace, snapshot: PageSnapshot) -> Path:
    directory = (
        workspace.artifacts
        / "extraction"
        / snapshot.page_id
        / snapshot.device.value.lower()
        / snapshot.snapshot_id
    )
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _relative(workspace: AuditWorkspace, path: Path) -> str:
    return path.relative_to(workspace.root).as_posix()


def _write_main_content(
    workspace: AuditWorkspace,
    snapshot: PageSnapshot,
    main_content: str,
) -> str | None:
    if not main_content:
        return None
    path = _artifact_directory(workspace, snapshot) / "main_content.txt"
    path.write_text(main_content, encoding="utf-8", newline="\n")
    return _relative(workspace, path)


def _structured_payload(block: StructuredDataBlock) -> dict[str, object]:
    return {
        "index": block.index,
        "raw": block.raw,
        "parsed": block.parsed,
        "parse_error": block.parse_error,
        "types": list(block.types),
    }


def _write_structured_data(
    workspace: AuditWorkspace,
    snapshot: PageSnapshot,
    blocks: tuple[StructuredDataBlock, ...],
) -> str | None:
    if not blocks:
        return None
    path = _artifact_directory(workspace, snapshot) / "structured_data.json"
    payload = {"blocks": [_structured_payload(block) for block in blocks]}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
        newline="\n",
    )
    return _relative(workspace, path)


def _record_extraction_evidence(
    manager: EvidenceManager,
    *,
    audit_id: str,
    snapshot: PageSnapshot,
    source_name: str,
    source_ref: str,
    extracted: ExtractedPage,
) -> list[str]:
    common = {
        "audit_id": audit_id,
        "page_id": snapshot.page_id,
        "snapshot_id": snapshot.snapshot_id,
        "device": snapshot.device,
        "source": source_name,
    }
    ids: list[str] = []

    def record(evidence_type: EvidenceType, value: object, artifact: str | None = None) -> None:
        evidence = manager.record(
            **common,
            evidence_type=evidence_type,
            observed_value=value,
            artifact_reference=artifact,
        )
        ids.append(evidence.evidence_id)

    record(
        EvidenceType.DOM_ELEMENT,
        {"extraction_source": source_name, "artifact_reference": source_ref},
        source_ref,
    )
    if extracted.title is not None:
        record(EvidenceType.HTML_ELEMENT, {"element": "title", "value": extracted.title})
    if extracted.description is not None:
        record(EvidenceType.META_TAG, {"name": "description", "content": extracted.description})
    if extracted.meta_robots is not None:
        record(EvidenceType.META_TAG, {"name": "robots", "content": extracted.meta_robots})
    if extracted.canonical is not None:
        record(EvidenceType.CANONICAL, {"href": extracted.canonical})
    if extracted.headings:
        record(
            EvidenceType.HEADING,
            [{"level": item.level, "text": item.text} for item in extracted.headings],
        )
    if extracted.links:
        record(
            EvidenceType.LINK,
            [
                {"href": item.href, "text": item.text, "rel": list(item.rel)}
                for item in extracted.links
            ],
        )
    if extracted.structured_data:
        valid = sum(block.parse_error is None for block in extracted.structured_data)
        types = list(dict.fromkeys(value for block in extracted.structured_data for value in block.types))
        record(
            EvidenceType.STRUCTURED_DATA,
            {
                "blocks": len(extracted.structured_data),
                "valid_blocks": valid,
                "invalid_blocks": len(extracted.structured_data) - valid,
                "types": types,
            },
            snapshot.structured_data_ref,
        )
    if extracted.main_content:
        record(
            EvidenceType.MAIN_CONTENT,
            {
                "source": extracted.main_content_source,
                "character_count": len(extracted.main_content),
                "excerpt": extracted.main_content[:500],
            },
            snapshot.main_content_ref,
        )

    return ids
