"""Application service for offline consolidated reporting."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

from .aggregate import summarize_apdex, summarize_findings, summarize_performance, summarize_scores
from .comparability import annotate_score_url_universes
from .index import ConsolidationIndex
from .models import ConsolidatedData, ConsolidationFilter, GenerationResult, RefreshResult
from .reporting import write_report


def normalize_filter(
    *,
    domains: Iterable[str] = (),
    date_from: date | None = None,
    date_to: date | None = None,
    devices: Iterable[str] = (),
    urls: Iterable[str] = (),
) -> ConsolidationFilter:
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from cannot be after date_to")
    return ConsolidationFilter(
        domains=tuple(sorted({item.strip().casefold() for item in domains if item and item.strip()})),
        date_from=date_from,
        date_to=date_to,
        devices=tuple(sorted({item.strip().upper() for item in devices if item and item.strip()})),
        urls=tuple(sorted({item.strip() for item in urls if item and item.strip()})),
    )


def build_data(index: ConsolidationIndex, filters: ConsolidationFilter) -> ConsolidatedData:
    points = index.load_points(filters)
    audits = points["audits"]
    if not audits:
        raise ValueError("nenhuma auditoria COMPLETED corresponde aos filtros selecionados")
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
        score_history=score_rows,
        finding_history=points["findings"],
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
            score_history=data.score_history,
            finding_history=data.finding_history,
        )
    return write_report(audits_root=root, data=data, refresh=refresh)
