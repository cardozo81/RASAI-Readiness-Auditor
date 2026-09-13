"""Application service for offline-first consolidated reporting."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Iterable

from rasai.report_presentation import humanize_report_html
from rasai.time_contract import normalize_timestamp_values

from .aggregate import summarize_apdex, summarize_findings, summarize_performance, summarize_scores
from .comparability import (
    annotate_audit_configurations,
    annotate_score_url_universes,
    configuration_comparability,
)
from .index import ConsolidationIndex
from .models import ConsolidatedData, ConsolidationFilter, GenerationResult, RefreshResult
from .reporting import write_report
from .cons4 import find_existing as find_cons4
from .cons4 import materialize as materialize_cons4
from .cons4 import request_fingerprint as cons4_request_fingerprint
from .specialist import enrich_result, validate_comparison_mode
from .temporal_apdex import build_temporal_apdex


def normalize_filter(
    *,
    domains: Iterable[str] = (),
    date_from: date | None = None,
    date_to: date | None = None,
    devices: Iterable[str] = (),
    urls: Iterable[str] = (),
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
    mode = validate_comparison_mode(comparison_mode)
    baseline = str(baseline_audit_id or "").strip() or None
    current = str(current_audit_id or "").strip() or None
    if mode == "MANUAL" and (not baseline or not current):
        raise ValueError("comparison_mode MANUAL exige baseline_audit_id e current_audit_id")
    if mode != "MANUAL":
        baseline = None
        current = None
    provider = str(ai_provider or "").strip().casefold() or None
    if specialist_ai and provider in {None, "none"}:
        raise ValueError("specialist_ai exige provider de IA habilitado")
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

    config_summary = configuration_comparability(audits)
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


def generate(
    audits_root: str | Path,
    filters: ConsolidationFilter,
    *,
    refresh_index: bool = True,
) -> GenerationResult:
    root = Path(audits_root)
    index = ConsolidationIndex(root)
    refresh = index.refresh() if refresh_index else RefreshResult(0, 0, 0, 0, ())
    data = build_data(index, filters)
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

    temporal_fingerprint = cons4_request_fingerprint(data.source_fingerprint, filters)
    existing_temporal = find_cons4(root, temporal_fingerprint, refresh)
    if existing_temporal is not None:
        _normalize_derivative_output(existing_temporal)
        return existing_temporal

    temporal_apdex = build_temporal_apdex(
        audits_root=root,
        audits=data.audits,
        filters=filters,
    )
    base_result = write_report(audits_root=root, data=data, refresh=refresh)
    result = materialize_cons4(
        audits_root=root,
        base_result=base_result,
        source_fingerprint=data.source_fingerprint,
        filters=filters,
        series=temporal_apdex,
    )
    # Evolution/AI enrichment is derivative and fail-open. It reads the same immutable
    # AUD workspaces through Monitoring/Quality and never feeds back into scoring.
    result = enrich_result(root, filters, result)
    _normalize_derivative_output(result)
    return result
