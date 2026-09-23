"""Application service for offline-first consolidated reporting."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import shutil
from typing import Any, Callable, Iterable, Mapping

from rasai.report_presentation import humanize_report_html
from rasai.secret_safety import redact_value
from rasai.time_contract import normalize_timestamp_values

from .aggregate import summarize_apdex, summarize_findings, summarize_performance, summarize_scores
from .confidence import evaluate_consolidation_confidence
from .comparability import (
    annotate_audit_configurations,
    annotate_score_url_universes,
    configuration_comparability,
)
from .decision_context import DECISION_CONTRACT, build_decision_context
from .execution_log import ConsolidationExecutionError, ConsolidationExecutionLog, EXECUTION_CONTRACT
from .index import ConsolidationIndex
from .models import ConsolidatedData, ConsolidationFilter, GenerationResult, RefreshResult
from .reporting import write_report
from .cons5 import find_existing as find_cons5
from .cons5 import materialize as materialize_cons5
from .cons5 import request_fingerprint as cons5_request_fingerprint
from .diagnostic_reporting import materialize_diagnostic_notice
from .presentation import enforce_source_report_navigation, refine_result
from .specialist import (
    LongitudinalPreparation,
    SpecialistPreview,
    _longitudinal_deterministic_html,
    _longitudinal_rows,
    _validate_preparation,
    apply_longitudinal_analysis,
    prepare_longitudinal_specialist,
    preview_longitudinal_specialist,
    run_longitudinal_ai,
    validate_comparison_mode,
)
from .temporal_apdex import build_temporal_apdex
from .selection import validate_selection_mode


def normalize_filter(
    *,
    domains: Iterable[str] = (),
    date_from: date | None = None,
    date_to: date | None = None,
    devices: Iterable[str] = (),
    urls: Iterable[str] = (),
    audit_ids: Iterable[str] = (),
    selection_mode: str = "ALL",
    comparison_mode: str = "FIRST_LAST",
    baseline_audit_id: str | None = None,
    current_audit_id: str | None = None,
    specialist_ai: bool = False,
    ai_provider: str | None = None,
    ai_model: str | None = None,
    ai_reasoning: str | None = None,
    ai_timeout_seconds: float | None = None,
) -> ConsolidationFilter:
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from cannot be after date_to")
    selection = validate_selection_mode(selection_mode)
    mode = validate_comparison_mode(comparison_mode)
    baseline = str(baseline_audit_id or "").strip() or None
    current = str(current_audit_id or "").strip() or None
    if mode == "MANUAL" and (not baseline or not current):
        raise ValueError("comparison_mode MANUAL exige baseline_audit_id e current_audit_id")
    if mode != "MANUAL":
        baseline = None
        current = None
    provider = str(ai_provider or "").strip().casefold() or None
    # IA solicitada e IA disponível são conceitos distintos. Provider ausente/none
    # produz uma camada de IA pendente, mas não bloqueia o consolidado determinístico.
    timeout = None
    if specialist_ai:
        timeout = float(ai_timeout_seconds or 180.0)
        if not timeout > 0:
            raise ValueError("ai_timeout_seconds deve ser > 0")
    return ConsolidationFilter(
        domains=tuple(sorted({item.strip().casefold() for item in domains if item and item.strip()})),
        date_from=date_from,
        date_to=date_to,
        devices=tuple(sorted({item.strip().upper() for item in devices if item and item.strip()})),
        urls=tuple(sorted({item.strip() for item in urls if item and item.strip()})),
        audit_ids=tuple(sorted({item.strip() for item in audit_ids if item and item.strip()})),
        selection_mode=selection,
        comparison_mode=mode,
        baseline_audit_id=baseline,
        current_audit_id=current,
        specialist_ai=bool(specialist_ai),
        ai_provider=provider if specialist_ai else None,
        ai_model=(str(ai_model).strip() or None) if specialist_ai and ai_model is not None else None,
        ai_reasoning=(str(ai_reasoning).strip().upper() or None) if specialist_ai and ai_reasoning is not None else None,
        ai_timeout_seconds=timeout,
    )


def _configuration_limitations(summary: dict[str, object]) -> tuple[str, ...]:
    output: list[str] = []
    missing = int(summary.get("without_snapshot") or 0)
    if missing:
        output.append(
            f"{missing} AUD(s) do período não possuem snapshot canônico de configuração; "
            "a equivalência metodológica completa dessas observações não pode ser comprovada."
        )
    pair = str(summary.get("pair_status") or "INSUFFICIENT_DATA")
    baseline = str(summary.get("baseline_audit_id") or "")
    current = str(summary.get("current_audit_id") or "")
    if pair == "PARTIAL":
        fields = tuple(str(item) for item in summary.get("altered_fields") or ())
        detail = f" Campos alterados na série: {', '.join(fields)}." if fields else ""
        output.append(
            f"Comparabilidade de configuração entre {baseline} e {current}: PARCIAL. "
            "As auditorias pertencem à mesma série longitudinal, mas a configuração efetiva mudou."
            + detail
        )
    elif pair == "EQUIVALENT_WITHOUT_LINEAGE":
        output.append(
            f"{baseline} e {current} possuem configuração efetiva equivalente, porém não compartilham "
            "linhagem explícita de uma mesma série de execução."
        )
    elif pair == "UNRELATED":
        output.append(
            f"{baseline} e {current} não pertencem à mesma série de configuração e possuem configurações "
            "efetivas distintas; tendências entre elas devem ser interpretadas como comparação contextual, "
            "não como repetição controlada do mesmo teste."
        )
    return tuple(output)


def build_data(index: ConsolidationIndex, filters: ConsolidationFilter) -> ConsolidatedData:
    points = index.load_points(filters)
    raw_audits = points["audits"]
    if not raw_audits:
        raise ValueError("nenhuma auditoria COMPLETED corresponde aos filtros selecionados")
    audits = annotate_audit_configurations(index.audits_root, raw_audits)
    source_fp = index.source_set_fingerprint(audits)
    available_urls = set(index.available_urls(filters))
    if filters.urls:
        available_urls.intersection_update(filters.urls)

    limitations: list[str] = []
    rulesets = tuple(sorted({str(row.get("ruleset_version") or "UNKNOWN") for row in audits}))
    if len(rulesets) > 1:
        limitations.append(
            "Múltiplas versões do conjunto de regras estão presentes no período: " + ", ".join(rulesets)
            + ". O relatório não presume equivalência metodológica entre versões."
        )
    auditors = tuple(sorted({str(row.get("auditor_version") or "UNKNOWN") for row in audits}))
    if len(auditors) > 1:
        limitations.append(
            "O período contém múltiplas versões do auditor: " + ", ".join(auditors) + "."
        )
    if filters.urls:
        score_audits = {str(row.get("audit_id")) for row in points["scores"]}
        candidate_with_scores = {
            str(row.get("audit_id")) for row in audits
            if int(row.get("url_count") or 0) > 0
        }
        if candidate_with_scores - score_audits:
            limitations.append(
                "Filtro explícito de URL ativo: pontuações calculadas para um universo maior de páginas "
                "foram excluídas quando o universo completo da auditoria não estava contido nas URLs selecionadas. "
                "Desempenho Web, Apdex e ocorrências continuam filtrados diretamente por URL."
            )

    config_summary = configuration_comparability(
        audits,
        comparison_mode=filters.comparison_mode,
        baseline_audit_id=filters.baseline_audit_id,
        current_audit_id=filters.current_audit_id,
    )
    limitations.extend(_configuration_limitations(config_summary))
    score_rows = annotate_score_url_universes(index.path, points["scores"])
    dates = [str(row.get("event_time") or "")[:10] for row in audits if row.get("event_time")]
    return ConsolidatedData(
        filters=filters,
        audits=audits,
        source_fingerprint=source_fp,
        scores=summarize_scores(score_rows),
        performance=summarize_performance(points["performance"]),
        apdex=summarize_apdex(points["apdex"]),
        findings=summarize_findings(points["findings"]),
        unique_urls=len(available_urls),
        date_min=min(dates) if dates else None,
        date_max=max(dates) if dates else None,
        limitations=tuple(limitations),
        configuration_comparability=config_summary,
        score_history=score_rows,
        finding_history=points["findings"],
    )


def _normalize_derivative_output(result: GenerationResult) -> None:
    """Apply the timezone contract to rebuildable consolidated artifacts only."""
    try:
        html = result.report_path.read_text(encoding="utf-8")
    except OSError:
        html = ""
    if html:
        rendered = humanize_report_html(html, page_name="consolidated.html")
        if rendered != html:
            result.report_path.write_text(rendered, encoding="utf-8", newline="\n")

    try:
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    normalized = normalize_timestamp_values(manifest)
    if normalized != manifest:
        result.manifest_path.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def _link_execution(result: GenerationResult, execution: ConsolidationExecutionLog) -> None:
    try:
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    manifest["consolidation_execution"] = {
        "contract": EXECUTION_CONTRACT,
        "run_id": execution.run_id,
        "execution_path": execution.execution_path.relative_to(result.report_dir.parent).as_posix(),
        "exchanges_path": execution.exchanges_path.relative_to(result.report_dir.parent).as_posix(),
    }
    result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    artifact_path = result.report_dir / "specialist-analysis.json"
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        artifact = None
    if isinstance(artifact, dict):
        artifact["consolidation_execution"] = {
            "contract": EXECUTION_CONTRACT,
            "run_id": execution.run_id,
        }
        artifact_path.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _apply_decision_context(
    result: GenerationResult,
    data: ConsolidatedData,
    longitudinal: Any,
    ai_run: Any,
) -> dict[str, Any]:
    context = build_decision_context(data, longitudinal, ai_run)
    _write_json(result.report_dir / "decision-context.json", context)

    artifact_path = result.report_dir / "specialist-analysis.json"
    if artifact_path.is_file():
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            artifact = {}
        if isinstance(artifact, dict):
            artifact["decision_context"] = context
            artifact["source_governance"] = longitudinal.governance
            _write_json(artifact_path, artifact)

    try:
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    manifest["decision_context"] = {
        "contract": DECISION_CONTRACT,
        "file": "decision-context.json",
        "structural_state": context.get("structural_matrix", {}).get("overall"),
        "source_conclusion": longitudinal.governance.get("conclusion_state"),
    }
    manifest["source_governance"] = longitudinal.governance
    source_audits = [
        item for item in longitudinal.governance.get("audits", ())
        if isinstance(item, Mapping)
    ]
    existing_sources = {
        str(item.get("audit_id") or ""): dict(item)
        for item in manifest.get("source_audits", ())
        if isinstance(item, Mapping)
    }
    manifest["source_audits"] = [
        {
            **existing_sources.get(str(item.get("audit_id") or ""), {}),
            "audit_id": str(item.get("audit_id") or ""),
            "event_time": str(item.get("event_time") or ""),
            "observation_at": str(item.get("observation_at") or item.get("event_time") or ""),
            "revision_at": str(item.get("revision_at") or item.get("event_time") or ""),
            "revision_mode": str(item.get("revision_mode") or "NONE"),
            "source_revision_id": str(item.get("source_revision_id") or ""),
            "source_revision_logical_sha256": str(item.get("source_revision_logical_sha256") or ""),
            "post_observation_revision": bool(item.get("post_observation_revision")),
            "temporal_revision_overlap": bool(item.get("temporal_revision_overlap")),
            "temporal_revision_overlap_with": item.get("temporal_revision_overlap_with"),
            "temporal_revision_overlap_state": str(item.get("temporal_revision_overlap_state") or "NONE"),
        }
        for item in source_audits
    ]
    linkable_report_audits = [
        str(item.get("audit_id") or "")
        for item in source_audits
        if item.get("report_catalog_fresh") is True
    ]
    stale_report_audits = [
        str(item.get("audit_id") or "")
        for item in source_audits
        if item.get("report_catalog_present") is True and item.get("report_catalog_fresh") is False
    ]
    unavailable_report_audits = [
        str(item.get("audit_id") or "")
        for item in source_audits
        if item.get("report_catalog_present") is False
    ]
    manifest["source_navigation"] = {
        "mode": "RELATIVE_SIBLING_AUD_TREE",
        "source_report_pattern": "../../{audit_id}/report-catalog/index.html",
        "canonical_audit_ids": list(longitudinal.audit_ids),
        "linkable_report_audit_ids": linkable_report_audits,
        "stale_report_audit_ids": stale_report_audits,
        "unavailable_report_audit_ids": unavailable_report_audits,
        "standalone_portable_links": False,
        "note": (
            "Os links de navegação para AUDs fonte dependem da árvore canônica audits/ "
            "com o CONS em audits/consolidated/CONS-*. O HTML cria navegação somente quando "
            "o report-catalog da fonte comprova freshness contra o audit.db atual; relatórios "
            "desatualizados ou ausentes permanecem identificados, mas não recebem link automático. "
            "Se o pacote CONS for copiado isoladamente, os IDs e hashes permanecem válidos, "
            "mas os links relativos não são autocontidos."
        ),
    }
    _write_json(result.manifest_path, manifest)
    return context


def _enforce_source_navigation_policy(result: GenerationResult, governance: Mapping[str, Any]) -> None:
    try:
        html = result.report_path.read_text(encoding="utf-8")
    except OSError:
        return
    rendered = enforce_source_report_navigation(html, governance)
    if rendered != html:
        result.report_path.write_text(rendered, encoding="utf-8", newline="\n")


def _embed_execution(result: GenerationResult, execution: ConsolidationExecutionLog) -> None:
    try:
        payload = json.loads(execution.execution_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if isinstance(payload, dict):
        material = dict(payload)
        result_info = material.get("result")
        if isinstance(result_info, dict):
            material["result"] = {
                **result_info,
                "report_dir": ".",
                "report_path": "report.html",
                "manifest_path": "manifest.json",
            }
        _write_json(result.report_dir / "execution.json", material)

    try:
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    specialist = manifest.get("specialist_ai") if isinstance(manifest.get("specialist_ai"), dict) else {}
    ai_requested = bool(specialist.get("requested"))
    if (
        ai_requested
        and not (result.report_dir / "ai-exchanges.json").is_file()
        and execution.exchanges_path.is_file()
    ):
        shutil.copyfile(execution.exchanges_path, result.report_dir / "ai-exchanges.json")

    manifest["consolidation_execution"] = {
        "contract": EXECUTION_CONTRACT,
        "run_id": execution.run_id,
        "execution_path": "execution.json",
        "exchanges_path": "ai-exchanges.json" if ai_requested else None,
    }
    _write_json(result.manifest_path, manifest)


def _package_integrity(result: GenerationResult) -> None:
    names = (
        "report.html",
        "rules-reference.html",
        "specialist-analysis.json",
        "decision-context.json",
        "longitudinal-evidence.json",
        "ai-exchanges.json",
        "execution.json",
    )
    files: dict[str, dict[str, Any]] = {}
    for name in names:
        path = result.report_dir / name
        if not path.is_file():
            continue
        raw = path.read_bytes()
        files[name] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }
    try:
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    manifest["package_integrity"] = {
        "algorithm": "SHA-256",
        "manifest_excluded_to_avoid_circular_hash": True,
        "files": files,
    }
    _write_json(result.manifest_path, manifest)


def _request_identity(
    index: ConsolidationIndex,
    filters: ConsolidationFilter,
) -> tuple[str, str]:
    audits = _longitudinal_rows(index.audits_root, filters, index=index)
    source_fingerprint = index.source_set_fingerprint(audits)
    return source_fingerprint, cons5_request_fingerprint(source_fingerprint, filters)


def find_reusable(
    audits_root: str | Path,
    filters: ConsolidationFilter,
    *,
    index: ConsolidationIndex | None = None,
    refresh: RefreshResult | None = None,
) -> GenerationResult | None:
    root = Path(audits_root)
    effective_index = index or ConsolidationIndex(root)
    _source_fingerprint, request_fingerprint = _request_identity(effective_index, filters)
    effective_refresh = refresh or RefreshResult(0, 0, 0, 0, ())
    return find_cons5(root, request_fingerprint, effective_refresh)


ProgressCallback = Callable[[str, str, str], None]


def _notify_progress(
    callback: ProgressCallback | None,
    stage: str,
    status: str,
    message: str,
) -> None:
    if callback is not None:
        callback(stage, status, message)


def _append_deterministic_longitudinal_html(
    result: GenerationResult,
    longitudinal: Any,
) -> None:
    html = result.report_path.read_text(encoding="utf-8")
    block = _longitudinal_deterministic_html(longitudinal)
    if "id='longitudinal-evolution'" in html or 'id="longitudinal-evolution"' in html:
        return
    if "<footer" in html:
        html = html.replace("<footer", block + "<footer", 1)
    else:
        html = html.replace("</body>", block + "</body>", 1)
    result.report_path.write_text(html, encoding="utf-8", newline="\n")


def _materialize_deterministic_longitudinal(
    result: GenerationResult,
    filters: ConsolidationFilter,
    prepared: LongitudinalPreparation,
    *,
    ai_requested: bool,
    ai_status: str,
    ai_reason: str | None,
    ai_run: Any | None = None,
    preview: SpecialistPreview | None = None,
) -> None:
    bundle = prepared.bundle
    evidence_artifact = {
        "contract": str(prepared.full_packet.get("contract") or "CONSOLIDATED-LONGITUDINAL-001"),
        "catalog_contract": str(prepared.full_packet.get("catalog_contract") or "CONSOLIDATED-CATALOG-LONGITUDINAL-001"),
        "evidence_count": len(prepared.full_evidence_ids),
        "scope": {
            "url": bundle.url,
            "device": bundle.device,
            "audit_ids": list(bundle.audit_ids),
            "event_times": list(bundle.event_times),
        },
        "evidence": prepared.full_packet,
    }
    evidence_safe = redact_value(evidence_artifact)
    evidence_raw = json.dumps(
        evidence_safe,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ) + "\n"
    evidence_path = result.report_dir / "longitudinal-evidence.json"
    evidence_path.write_text(evidence_raw, encoding="utf-8", newline="\n")
    evidence_sha256 = hashlib.sha256(evidence_raw.encode("utf-8")).hexdigest()

    try:
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    manifest["longitudinal_analysis"] = {
        "contract": evidence_artifact["contract"],
        "catalog_contract": evidence_artifact["catalog_contract"],
        "url": bundle.url,
        "device": bundle.device,
        "audit_ids": list(bundle.audit_ids),
        "audit_count": len(bundle.audit_ids),
        "period_start": bundle.event_times[0],
        "period_end": bundle.event_times[-1],
        "intervals": [
            {
                "interval_id": catalog.interval_id,
                "baseline_audit_id": catalog.baseline_audit_id,
                "current_audit_id": catalog.current_audit_id,
                "baseline_event_time": catalog.baseline_event_time,
                "current_event_time": catalog.current_event_time,
                "stable_within_expected": catalog.stable_expected,
                "stable_requiring_attention": catalog.stable_attention,
            }
            for catalog in bundle.catalog_intervals
        ],
        "ai_required": False,
        "ai_status": ai_status,
        "evidence_file": "longitudinal-evidence.json",
        "evidence_sha256": evidence_sha256,
        "evidence_count": len(prepared.full_evidence_ids),
        "limitations": list(bundle.limitations),
    }
    attempts = [
        asdict(item) if is_dataclass(item) else dict(item) if isinstance(item, Mapping) else {"value": str(item)}
        for item in (getattr(ai_run, "attempts", ()) or ())
    ]
    candidates = list(getattr(ai_run, "candidates", ()) or ())
    excluded = list(getattr(ai_run, "excluded_candidates", ()) or ())
    forecast = getattr(ai_run, "forecast", None)
    rounds = int(getattr(ai_run, "rounds", 0) or 0)
    context_projection = getattr(ai_run, "context_projection", None)
    if ai_run is None and preview is not None:
        candidates = [
            {
                "provider": item.provider,
                "model": item.model,
                "reasoning_profile": item.reasoning_profile,
                "estimated_input_tokens": item.estimated_input_tokens,
                "estimated_output_tokens": item.estimated_output_tokens,
                "estimated_cost": item.estimated_cost,
                "currency": item.currency,
                "pricing_version": item.pricing_version,
            }
            for item in preview.candidates
        ]
        excluded = list(preview.excluded_candidates)
        forecast = preview.forecast
        context_projection = preview.context_projection
    manifest["specialist_ai"] = {
        "contract": "CONSOLIDATED-SPECIALIST-001",
        "requested": bool(ai_requested),
        "required": False,
        "status": ai_status,
        "provider_selection": filters.ai_provider if ai_requested else None,
        "model_selection": filters.ai_model if ai_requested else None,
        "reasoning_selection": filters.ai_reasoning if ai_requested else None,
        "reason": ai_reason,
        "rounds": rounds,
        "candidates": candidates,
        "excluded_candidates": excluded,
        "forecast": forecast,
        "context_projection": context_projection,
        "attempts": attempts,
    }
    manifest["source_governance"] = bundle.governance
    _write_json(result.manifest_path, manifest)


def _apply_consolidation_metadata(
    result: GenerationResult,
    data: ConsolidatedData,
    longitudinal: Any,
    *,
    ai_status: str,
) -> dict[str, Any]:
    confidence = evaluate_consolidation_confidence(data, longitudinal)
    if ai_status == "COMPLETE":
        generation_mode = "DETERMINISTIC_AI"
    elif ai_status == "NOT_REQUESTED":
        generation_mode = "DETERMINISTIC"
    else:
        generation_mode = "DETERMINISTIC_AI_UNAVAILABLE"
    try:
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    manifest["selection_mode"] = data.filters.selection_mode
    manifest["generation_mode"] = generation_mode
    manifest["consolidation_confidence"] = confidence
    manifest["selection"] = {
        "baseline_audit_id": longitudinal.audit_ids[0],
        "current_audit_id": longitudinal.audit_ids[-1],
        "audit_ids": list(longitudinal.audit_ids),
        "audit_count": len(longitudinal.audit_ids),
        "period_start": longitudinal.event_times[0],
        "period_end": longitudinal.event_times[-1],
        "url": longitudinal.url,
        "device": longitudinal.device,
        "selection_mode": data.filters.selection_mode,
    }
    manifest["source_governance"] = longitudinal.governance
    _write_json(result.manifest_path, manifest)
    return confidence


def generate(
    audits_root: str | Path,
    filters: ConsolidationFilter,
    *,
    refresh_index: bool = True,
    prepared: LongitudinalPreparation | None = None,
    preview: SpecialistPreview | None = None,
    progress: ProgressCallback | None = None,
) -> GenerationResult:
    root = Path(audits_root)
    execution = ConsolidationExecutionLog.start(root, filters)
    result: GenerationResult | None = None
    try:
        execution.event(
            stage="INDEX",
            status="RUNNING",
            message="Atualizando o índice analítico reconstruível.",
        )
        _notify_progress(progress, "INDEX", "RUNNING", "Atualizando o índice analítico reconstruível.")
        index = ConsolidationIndex(root)
        refresh = index.refresh() if refresh_index else RefreshResult(0, 0, 0, 0, ())

        source_fingerprint, temporal_fingerprint = _request_identity(index, filters)
        existing_temporal = find_cons5(root, temporal_fingerprint, refresh)
        if existing_temporal is not None:
            execution.reused(existing_temporal)
            _notify_progress(progress, "COMPLETE", "REUSED", "Consolidado íntegro reutilizado.")
            return existing_temporal

        execution.event(
            stage="PREPARING",
            status="RUNNING",
            message="Validando identidade longitudinal e carregando evidências persistidas.",
        )
        _notify_progress(progress, "PREPARING", "RUNNING", "Validando fontes e preparando a série longitudinal.")
        if prepared is None:
            prepared = prepare_longitudinal_specialist(root, filters)
        else:
            _validate_preparation(prepared, root, filters)
        if prepared.source_fingerprint != source_fingerprint:
            raise RuntimeError(
                "as auditorias fonte mudaram após a preparação longitudinal; a geração deve ser reiniciada"
            )
        longitudinal = prepared.bundle
        data = build_data(index, filters)
        longitudinal.governance["configuration_comparability"] = dict(data.configuration_comparability)
        if data.source_fingerprint != source_fingerprint:
            raise RuntimeError(
                "o fingerprint das fontes divergiu durante a preparação do consolidado"
            )
        execution.event(
            stage="PREPARED",
            status="READY",
            message="Universo longitudinal preparado.",
            details={
                "url": longitudinal.url,
                "device": longitudinal.device,
                "audit_ids": longitudinal.audit_ids,
                "audit_count": len(longitudinal.audit_ids),
                "interval_count": len(longitudinal.intervals),
                "period_start": longitudinal.event_times[0],
                "period_end": longitudinal.event_times[-1],
            },
        )
        _notify_progress(progress, "PREPARED", "READY", "Universo longitudinal preparado.")

        if refresh.issues:
            data = ConsolidatedData(
                filters=data.filters,
                audits=data.audits,
                source_fingerprint=data.source_fingerprint,
                scores=data.scores,
                performance=data.performance,
                apdex=data.apdex,
                findings=data.findings,
                unique_urls=data.unique_urls,
                date_min=data.date_min,
                date_max=data.date_max,
                limitations=data.limitations + (
                    f"{len(refresh.issues)} AUD(s) não puderam ser indexados nesta atualização; detalhes constam no manifest.json.",
                ),
                configuration_comparability=data.configuration_comparability,
                score_history=data.score_history,
                finding_history=data.finding_history,
            )

        ai_run = None
        ai_status = "NOT_REQUESTED"
        ai_reason: str | None = None

        if filters.specialist_ai:
            selected_provider = str(filters.ai_provider or "none").strip().casefold()
            if selected_provider in {"", "none"}:
                # Explicit requested-but-not-configured state: no preview/provider
                # transport is attempted, no token/cost can be consumed.
                ai_status = "NOT_CONFIGURED"
                ai_reason = "AI_PROVIDER_NOT_CONFIGURED"
                execution.event(
                    stage="AI_FORECAST",
                    status="NOT_CONFIGURED",
                    message="IA longitudinal solicitada, mas nenhum provider foi configurado.",
                    details={"provider_called": False},
                )
                _notify_progress(
                    progress,
                    "AI_FORECAST",
                    "NOT_CONFIGURED",
                    "IA solicitada sem provider; seguindo com consolidação determinística.",
                )
            else:
                if preview is None:
                    preview = preview_longitudinal_specialist(root, filters, prepared=prepared)
                else:
                    if preview.baseline_audit_id != longitudinal.audit_ids[0]:
                        raise ValueError("a prévia autorizada não corresponde ao marco inicial preparado")
                    if preview.current_audit_id != longitudinal.audit_ids[-1]:
                        raise ValueError("a prévia autorizada não corresponde ao marco final preparado")
                    if preview.context_projection != prepared.context_projection:
                        raise ValueError("a prévia autorizada não corresponde à projeção de contexto preparada")
                execution.record_preview(preview)
                execution.event(
                    stage="AI_FORECAST",
                    status="READY" if preview.available else "UNAVAILABLE",
                    message="Previsão pré-execução da IA calculada.",
                    details={
                        "candidate_count": len(preview.candidates),
                        "fallback_available": len(preview.candidates) > 1,
                        "excluded_candidates": preview.excluded_candidates,
                        "forecast": preview.forecast,
                    },
                )
                _notify_progress(
                    progress,
                    "AI_FORECAST",
                    "READY" if preview.available else "UNAVAILABLE",
                    "Previsão da análise por IA calculada.",
                )
                if preview.available:
                    execution.event(
                        stage="AI_RUNNING",
                        status="RUNNING",
                        message="Executando análise longitudinal por IA.",
                    )
                    _notify_progress(progress, "AI_RUNNING", "RUNNING", "Executando análise longitudinal por IA.")
                    try:
                        ai_run = run_longitudinal_ai(
                            longitudinal,
                            filters,
                            prepared=prepared,
                            expected_preview=preview,
                        )
                        execution.record_ai(ai_run)
                        ai_status = str(ai_run.status or "UNAVAILABLE").upper()
                        ai_reason = ai_run.reason
                    except Exception as ai_exc:
                        ai_status = "UNAVAILABLE"
                        ai_reason = f"{type(ai_exc).__name__}: {ai_exc}"
                        execution.event(
                            stage="AI_RUNNING",
                            status="UNAVAILABLE",
                            message="A análise por IA não foi concluída; a consolidação determinística será preservada.",
                            details={"reason": ai_reason},
                        )
                else:
                    ai_status = "UNAVAILABLE"
                    ai_reason = str(preview.reason or "nenhum provedor de IA elegível")
        else:
            execution.event(
                stage="AI",
                status="NOT_REQUESTED",
                message="Análise por IA não solicitada; seguindo em modo determinístico.",
            )
            _notify_progress(progress, "AI", "NOT_REQUESTED", "Análise por IA não solicitada.")

        execution.event(
            stage="MATERIALIZING",
            status="RUNNING",
            message="Materializando CONS-5 a partir dos dados persistidos.",
        )
        _notify_progress(progress, "MATERIALIZING", "RUNNING", "Materializando o relatório consolidado.")
        temporal_apdex = build_temporal_apdex(
            audits_root=root,
            audits=data.audits,
            filters=filters,
        )
        base_result = write_report(audits_root=root, data=data, refresh=refresh)
        result = materialize_cons5(
            audits_root=root,
            base_result=base_result,
            source_fingerprint=data.source_fingerprint,
            filters=filters,
            series=temporal_apdex,
        )

        if ai_run is not None and ai_status == "COMPLETE":
            result = apply_longitudinal_analysis(
                result,
                filters,
                longitudinal,
                ai_run,
                prepared=prepared,
            )
            decision_run = ai_run
        else:
            _append_deterministic_longitudinal_html(result, longitudinal)
            _materialize_deterministic_longitudinal(
                result,
                filters,
                prepared,
                ai_requested=bool(filters.specialist_ai),
                ai_status=ai_status,
                ai_reason=ai_reason,
                ai_run=ai_run,
                preview=preview,
            )
            decision_run = ai_run or SimpleNamespace(
                requested=bool(filters.specialist_ai),
                status=ai_status,
                summary="",
                topic_analyses=(),
            )

        _apply_decision_context(result, data, longitudinal, decision_run)
        _enforce_source_navigation_policy(result, longitudinal.governance)
        _apply_consolidation_metadata(result, data, longitudinal, ai_status=ai_status)
        result = materialize_diagnostic_notice(
            result,
            longitudinal.governance,
            ai_requested=bool(filters.specialist_ai),
            ai_status=ai_status,
            ai_reason=ai_reason,
        )
        _link_execution(result, execution)
        _normalize_derivative_output(result)
        # Corporate presentation, source governance and deterministic rule references
        # are mode-independent. Only interpretive AI blocks depend on ai_status.
        result = refine_result(result)
        execution.complete(result)
        _embed_execution(result, execution)
        _package_integrity(result)
        _notify_progress(progress, "COMPLETE", "COMPLETE", "Relatório consolidado concluído.")
        return result
    except Exception as exc:
        if result is not None and result.report_dir.is_dir():
            shutil.rmtree(result.report_dir, ignore_errors=True)
        execution.fail(exc, stage="FAILED")
        _notify_progress(progress, "FAILED", "FAILED", str(exc))
        if isinstance(exc, ConsolidationExecutionError):
            raise
        raise ConsolidationExecutionError(
            str(exc),
            execution=execution,
        ) from exc
