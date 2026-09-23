"""Seleção de auditorias e histórico para o relatório consolidado longitudinal.

A camada é read-only sobre AUD/CONS. Ela resolve a composição temporal solicitada
pelas superfícies Console/SaaS sem executar coleta, scoring ou renderização.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from rasai.time_contract import parse_timestamp

from .governance import build_source_governance
from .index import ConsolidationIndex
from .models import ConsolidationFilter

SELECTION_MODES = frozenset({"ALL", "SUCCESS_ONLY", "MANUAL"})
_SUCCESS_SOURCE_STATES = frozenset({"SUCCESS", "SUCCESS_WITH_LIMITATIONS"})


@dataclass(frozen=True, slots=True)
class AuditCandidate:
    audit_id: str
    event_time: str
    url: str
    domain: str
    device: str
    status: str
    completion_status: str | None


@dataclass(frozen=True, slots=True)
class ResolvedSelection:
    baseline_audit_id: str
    current_audit_id: str
    url: str
    device: str
    period_start: str
    period_end: str
    audit_ids: tuple[str, ...]
    selection_mode: str
    interval_candidate_count: int
    intermediate_count: int
    excluded_audit_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConsolidatedHistoryItem:
    cons_id: str
    generated_at: str
    url: str
    domain: str
    device: str
    period_start: str
    period_end: str
    audit_ids: tuple[str, ...]
    audit_count: int
    selection_mode: str
    generation_mode: str
    ai_status: str
    confidence: str
    report_path: Path
    report_dir: Path


def validate_selection_mode(value: str) -> str:
    mode = str(value or "ALL").strip().upper()
    if mode not in SELECTION_MODES:
        raise ValueError("selection_mode deve ser ALL, SUCCESS_ONLY ou MANUAL")
    return mode


def _devices(row: dict) -> tuple[str, ...]:
    try:
        raw = json.loads(str(row.get("devices_json") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()
    return tuple(sorted({str(item).upper() for item in raw if str(item).strip()}))


def _url_for(index: ConsolidationIndex, audit_id: str) -> str | None:
    urls = index.available_urls(ConsolidationFilter(audit_ids=(audit_id,)))
    return urls[0] if len(urls) == 1 else None


def _chronology_key(item: AuditCandidate):
    """Order AUD markers by their actual instant, never by selection order/string form."""
    try:
        instant = parse_timestamp(item.event_time)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"auditoria {item.audit_id} possui data/hora inválida para ordenação longitudinal"
        ) from exc
    return instant, item.audit_id


def _candidate(index: ConsolidationIndex, row: dict) -> AuditCandidate | None:
    if int(row.get("url_count") or 0) != 1:
        return None
    devices = _devices(row)
    if len(devices) != 1:
        return None
    audit_id = str(row.get("audit_id") or "")
    url = _url_for(index, audit_id)
    if not audit_id or not url:
        return None
    return AuditCandidate(
        audit_id=audit_id,
        event_time=str(row.get("event_time") or ""),
        url=url,
        domain=(urlparse(url).hostname or "").casefold(),
        device=devices[0],
        status=str(row.get("status") or "UNKNOWN").upper(),
        completion_status=(str(row.get("completion_status")).upper() if row.get("completion_status") else None),
    )


def candidate_audits(
    index: ConsolidationIndex,
    *,
    allowed_audit_ids: Iterable[str] = (),
    query: str | None = None,
) -> tuple[AuditCandidate, ...]:
    allowed = tuple(dict.fromkeys(str(item).strip() for item in allowed_audit_ids if str(item).strip()))
    rows = index.candidate_audits(ConsolidationFilter(audit_ids=allowed))
    candidates = [item for row in rows if (item := _candidate(index, row)) is not None]
    needle = str(query or "").strip().casefold()
    if needle:
        candidates = [
            item for item in candidates
            if needle in " ".join((
                item.audit_id,
                item.event_time,
                item.url,
                item.domain,
                item.device,
                item.status,
                item.completion_status or "",
            )).casefold()
        ]
    candidates.sort(key=_chronology_key, reverse=True)
    return tuple(candidates)


def compatible_candidates(
    index: ConsolidationIndex,
    reference_audit_id: str,
    *,
    allowed_audit_ids: Iterable[str] = (),
) -> tuple[AuditCandidate, ...]:
    candidates = candidate_audits(index, allowed_audit_ids=allowed_audit_ids)
    reference = next((item for item in candidates if item.audit_id == reference_audit_id), None)
    if reference is None:
        raise ValueError("auditoria de referência não é elegível para consolidação")
    return tuple(
        item for item in candidates
        if item.audit_id != reference.audit_id
        and item.url == reference.url
        and item.device == reference.device
    )


def resolve_selection(
    index: ConsolidationIndex,
    first_audit_id: str,
    second_audit_id: str,
    *,
    selection_mode: str = "ALL",
    manual_audit_ids: Iterable[str] = (),
    allowed_audit_ids: Iterable[str] = (),
) -> ResolvedSelection:
    mode = validate_selection_mode(selection_mode)
    if first_audit_id == second_audit_id:
        raise ValueError("selecione duas auditorias distintas")

    candidates = candidate_audits(index, allowed_audit_ids=allowed_audit_ids)
    by_id = {item.audit_id: item for item in candidates}
    first = by_id.get(first_audit_id)
    second = by_id.get(second_audit_id)
    if first is None or second is None:
        raise ValueError("uma ou mais auditorias selecionadas não são elegíveis ou não pertencem ao escopo autorizado")
    if first.url != second.url:
        raise ValueError("o consolidado exige auditorias da mesma URL")
    if first.device != second.device:
        raise ValueError("o consolidado exige auditorias do mesmo dispositivo")

    baseline, current = sorted((first, second), key=_chronology_key)
    baseline_instant = _chronology_key(baseline)[0]
    current_instant = _chronology_key(current)[0]
    interval = [
        item for item in candidates
        if item.url == baseline.url
        and item.device == baseline.device
        and baseline_instant <= _chronology_key(item)[0] <= current_instant
    ]
    interval.sort(key=_chronology_key)
    interval_ids = tuple(item.audit_id for item in interval)
    if baseline.audit_id not in interval_ids or current.audit_id not in interval_ids:
        raise ValueError("não foi possível materializar os marcos selecionados no intervalo")

    if mode == "ALL":
        selected_ids = set(interval_ids)
    elif mode == "SUCCESS_ONLY":
        rows = index.candidate_audits(
            ConsolidationFilter(
                urls=(baseline.url,),
                devices=(baseline.device,),
                audit_ids=interval_ids,
            )
        )
        governance = build_source_governance(index.audits_root, rows)
        selected_ids = {
            str(item.get("audit_id") or "")
            for item in governance.get("audits", ())
            if str(item.get("source_state") or "").upper() in _SUCCESS_SOURCE_STATES
        }
        if baseline.audit_id not in selected_ids or current.audit_id not in selected_ids:
            raise ValueError(
                "os marcos BASE e ATUAL precisam estar concluídos com sucesso para usar SUCCESS_ONLY"
            )
    else:
        manual = {str(item).strip() for item in manual_audit_ids if str(item).strip()}
        unknown = manual.difference(interval_ids)
        if unknown:
            raise ValueError(
                "seleção manual contém auditoria fora do intervalo compatível: "
                + ", ".join(sorted(unknown))
            )
        selected_ids = {baseline.audit_id, current.audit_id, *manual}

    ordered = tuple(item.audit_id for item in interval if item.audit_id in selected_ids)
    if len(ordered) < 2:
        raise ValueError("o consolidado exige pelo menos duas auditorias selecionadas")

    excluded = tuple(item.audit_id for item in interval if item.audit_id not in selected_ids)
    return ResolvedSelection(
        baseline_audit_id=ordered[0],
        current_audit_id=ordered[-1],
        url=baseline.url,
        device=baseline.device,
        period_start=baseline.event_time,
        period_end=current.event_time,
        audit_ids=ordered,
        selection_mode=mode,
        interval_candidate_count=len(interval),
        intermediate_count=max(0, len(interval) - 2),
        excluded_audit_ids=excluded,
    )


def _history_mode(payload: dict, longitudinal: dict, specialist: dict) -> tuple[str, str]:
    explicit = str(payload.get("generation_mode") or "").strip().upper()
    ai_status = str(specialist.get("status") or longitudinal.get("ai_status") or "NOT_REQUESTED").upper()
    if explicit:
        return explicit, ai_status
    if ai_status == "COMPLETE":
        return "DETERMINISTIC_AI", ai_status
    if ai_status == "NOT_REQUESTED":
        return "DETERMINISTIC", ai_status
    return "DETERMINISTIC_AI_UNAVAILABLE", ai_status


def list_consolidated_history(
    audits_root: str | Path,
    *,
    query: str | None = None,
    allowed_audit_ids: Iterable[str] = (),
) -> tuple[ConsolidatedHistoryItem, ...]:
    root = Path(audits_root) / "consolidated"
    allowed = {str(item).strip() for item in allowed_audit_ids if str(item).strip()}
    needle = str(query or "").strip().casefold()
    output: list[ConsolidatedHistoryItem] = []
    if not root.is_dir():
        return ()

    for manifest_path in root.glob("CONS-*/manifest.json"):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        source_audits = payload.get("source_audits") if isinstance(payload.get("source_audits"), list) else []
        audit_ids = tuple(
            str(item.get("audit_id") or "")
            for item in source_audits
            if isinstance(item, dict) and str(item.get("audit_id") or "")
        )
        longitudinal = payload.get("longitudinal_analysis") if isinstance(payload.get("longitudinal_analysis"), dict) else {}
        if not audit_ids:
            audit_ids = tuple(str(item) for item in longitudinal.get("audit_ids", ()) if str(item))
        if allowed and (not audit_ids or not set(audit_ids).issubset(allowed)):
            continue

        filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
        urls = filters.get("urls") if isinstance(filters.get("urls"), list) else []
        devices = filters.get("devices") if isinstance(filters.get("devices"), list) else []
        url = str(longitudinal.get("url") or (urls[0] if len(urls) == 1 else ""))
        device = str(longitudinal.get("device") or (devices[0] if len(devices) == 1 else "")).upper()
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        specialist = payload.get("specialist_ai") if isinstance(payload.get("specialist_ai"), dict) else {}
        generation_mode, ai_status = _history_mode(payload, longitudinal, specialist)
        confidence_payload = payload.get("consolidation_confidence") if isinstance(payload.get("consolidation_confidence"), dict) else {}
        cons_id = str(payload.get("cons_id") or manifest_path.parent.name)
        generated_at = str(payload.get("generated_at") or "")
        period_start = str(longitudinal.get("period_start") or summary.get("date_min") or "")
        period_end = str(longitudinal.get("period_end") or summary.get("date_max") or "")
        selection_mode = str(payload.get("selection_mode") or filters.get("selection_mode") or "ALL").upper()
        domain = (urlparse(url).hostname or "").casefold()
        report_path = manifest_path.parent / "report.html"
        if not report_path.is_file():
            continue
        item = ConsolidatedHistoryItem(
            cons_id=cons_id,
            generated_at=generated_at,
            url=url,
            domain=domain,
            device=device,
            period_start=period_start,
            period_end=period_end,
            audit_ids=audit_ids,
            audit_count=len(audit_ids),
            selection_mode=selection_mode,
            generation_mode=generation_mode,
            ai_status=ai_status,
            confidence=str(confidence_payload.get("label") or "Não determinada"),
            report_path=report_path,
            report_dir=manifest_path.parent,
        )
        if needle:
            haystack = " ".join((
                item.cons_id,
                item.generated_at,
                item.url,
                item.domain,
                item.device,
                item.period_start,
                item.period_end,
                item.selection_mode,
                item.generation_mode,
                item.confidence,
            )).casefold()
            if needle not in haystack:
                continue
        output.append(item)

    output.sort(key=lambda item: (item.generated_at, item.cons_id), reverse=True)
    return tuple(output)


__all__ = [
    "AuditCandidate",
    "ConsolidatedHistoryItem",
    "ResolvedSelection",
    "SELECTION_MODES",
    "candidate_audits",
    "compatible_candidates",
    "list_consolidated_history",
    "resolve_selection",
    "validate_selection_mode",
]
