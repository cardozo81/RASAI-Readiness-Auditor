"""Statistical policies for persisted SearchGEO indicators.

The consolidator summarizes persisted observations; it never re-runs the GEO
scoring engine or fabricates missing values. Version/profile incompatibilities
and materially different URL universes are isolated before statistics are
calculated.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean, median
from typing import Any, Iterable

from .models import (
    ApdexSummary,
    FindingSummary,
    MetricSummary,
    NumericSummary,
    PerformanceSummary,
    ScoreSummary,
)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _empty_stats() -> NumericSummary:
    return NumericSummary(0, None, None, None, None, None, None, None, None)


def _stats(rows: Iterable[dict[str, Any]], field: str, *, time_field: str = "event_time") -> NumericSummary:
    usable = [(str(row.get(time_field) or ""), value) for row in rows if (value := _number(row.get(field))) is not None]
    usable.sort(key=lambda item: item[0])
    values = [item[1] for item in usable]
    if not values:
        return _empty_stats()
    initial = values[0]
    current = values[-1]
    delta = current - initial
    percent = (delta / abs(initial) * 100.0) if initial != 0 else None
    return NumericSummary(
        count=len(values), current=current, initial=initial, mean=mean(values), median=median(values),
        minimum=min(values), maximum=max(values), change_absolute=delta, change_percent=percent,
    )


def _state_stats_by_url(
    rows: Iterable[dict[str, Any]],
    field: str,
    *,
    time_field: str,
) -> NumericSummary:
    """Use earliest/latest observation per URL for state change.

    Mean/median/min/max still describe all persisted observations in the selected
    period. Initial/current are cross-sectional means of each URL's earliest and
    latest valid observation, preventing one repeatedly audited URL from becoming
    the whole domain's current value merely because it is the final row.
    """
    usable = [
        row for row in rows
        if row.get("url") and _number(row.get(field)) is not None
    ]
    if not usable:
        return _stats(rows, field, time_field=time_field)
    by_url: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in usable:
        by_url[str(row["url"])].append(row)
    initial_values: list[float] = []
    current_values: list[float] = []
    all_values: list[float] = []
    for url_rows in by_url.values():
        url_rows.sort(key=lambda row: str(row.get(time_field) or ""))
        values = [value for row in url_rows if (value := _number(row.get(field))) is not None]
        if not values:
            continue
        initial_values.append(values[0])
        current_values.append(values[-1])
        all_values.extend(values)
    if not all_values or not initial_values or not current_values:
        return _empty_stats()
    initial = mean(initial_values)
    current = mean(current_values)
    delta = current - initial
    percent = (delta / abs(initial) * 100.0) if initial != 0 else None
    return NumericSummary(
        count=len(all_values), current=current, initial=initial, mean=mean(all_values),
        median=median(all_values), minimum=min(all_values), maximum=max(all_values),
        change_absolute=delta, change_percent=percent,
    )


def summarize_scores(rows: tuple[dict[str, Any], ...]) -> tuple[ScoreSummary, ...]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("device") or "UNKNOWN"), str(row.get("dimension") or "UNKNOWN"))].append(row)
    output: list[ScoreSummary] = []
    for (device, dimension), items in sorted(grouped.items()):
        items.sort(key=lambda row: str(row.get("event_time") or row.get("calculated_at") or ""))
        versions = tuple(dict.fromkeys(str(row.get("scoring_version") or "UNKNOWN") for row in items))
        universes = tuple(dict.fromkeys(str(row.get("url_universe") or "UNKNOWN") for row in items))
        latest_version = str(items[-1].get("scoring_version") or "UNKNOWN")
        latest_universe = str(items[-1].get("url_universe") or "UNKNOWN")
        compatible = [
            row for row in items
            if str(row.get("scoring_version") or "UNKNOWN") == latest_version
            and str(row.get("url_universe") or "UNKNOWN") == latest_universe
        ]
        coverages = [value for row in compatible if (value := _number(row.get("coverage"))) is not None]
        limitations: list[str] = []
        if len(versions) > 1:
            limitations.append(
                f"Mudança de versão do método de pontuação detectada ({', '.join(versions)}); versão comparável mais recente: {latest_version}."
            )
        if len(universes) > 1:
            limitations.append(
                f"Foram detectados {len(universes)} universos distintos de URLs; a estatística da pontuação usa somente o universo da auditoria mais recente."
            )
        output.append(ScoreSummary(
            device=device,
            dimension=dimension,
            scoring_versions=versions,
            url_universes=len(universes),
            observations=len(items),
            valid_observations=sum(_number(row.get("value")) is not None for row in compatible),
            average_coverage=mean(coverages) if coverages else None,
            confidence_counts=dict(Counter(str(row.get("confidence") or "UNKNOWN") for row in compatible)),
            consolidation_counts=dict(Counter(str(row.get("consolidation_status") or "UNKNOWN") for row in compatible)),
            statistics=_stats(compatible, "value"),
            limitation=" ".join(limitations) if limitations else None,
        ))
    return tuple(output)


_PERF_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("performance_score", "Performance Lighthouse", "score"),
    ("accessibility_score", "Accessibility Lighthouse", "score"),
    ("best_practices_score", "Best Practices Lighthouse", "score"),
    ("seo_score", "SEO Lighthouse", "score"),
    ("fcp_lab_ms", "FCP lab", "ms"),
    ("speed_index_lab_ms", "Speed Index lab", "ms"),
    ("lcp_lab_ms", "LCP lab", "ms"),
    ("tbt_lab_ms", "TBT lab", "ms"),
    ("cls_lab", "CLS lab", "score"),
    ("lcp_p75_ms", "LCP p75 de campo", "ms"),
    ("inp_p75_ms", "INP p75 de campo", "ms"),
    ("cls_p75", "CLS p75 de campo", "score"),
)


def summarize_performance(rows: tuple[dict[str, Any], ...]) -> tuple[PerformanceSummary, ...]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("device") or "UNKNOWN")].append(row)
    output: list[PerformanceSummary] = []
    for device, items in sorted(grouped.items()):
        metrics = tuple(
            MetricSummary(
                name=label,
                unit=unit,
                statistics=_state_stats_by_url(items, field, time_field="captured_at"),
            )
            for field, label, unit in _PERF_FIELDS
            if any(_number(row.get(field)) is not None for row in items)
        )
        cwv = Counter(str(row.get("cwv_assessment") or "UNKNOWN") for row in items)
        scopes = Counter(
            f"{row.get('field_source') or 'NONE'} / {row.get('field_scope') or 'NONE'}"
            for row in items
        )
        output.append(PerformanceSummary(
            device=device,
            observations=len(items),
            urls=len({str(row.get("url") or "") for row in items if row.get("url")}),
            metrics=metrics,
            cwv_counts=dict(cwv),
            source_scopes=dict(scopes),
        ))
    return tuple(output)


def summarize_apdex(rows: tuple[dict[str, Any], ...]) -> tuple[ApdexSummary, ...]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("device") or "UNKNOWN")].append(row)
    output: list[ApdexSummary] = []
    for device, items in sorted(grouped.items()):
        items.sort(key=lambda row: str(row.get("calculated_at") or row.get("event_time") or ""))
        profiles = tuple(dict.fromkeys(str(row.get("profile_id") or "UNKNOWN") for row in items))
        thresholds = tuple(sorted({value for row in items if (value := _number(row.get("threshold_seconds"))) is not None}))
        latest_profile = str(items[-1].get("profile_id") or "UNKNOWN")
        latest_threshold = _number(items[-1].get("threshold_seconds"))
        compatible = [
            row for row in items
            if str(row.get("profile_id") or "UNKNOWN") == latest_profile
            and _number(row.get("threshold_seconds")) == latest_threshold
        ]
        valid = sum(int(row.get("valid_samples") or 0) for row in compatible)
        invalid = sum(int(row.get("invalid_samples") or 0) for row in compatible)
        weighted_numerator = 0.0
        weighted_denominator = 0
        for row in compatible:
            score = _number(row.get("apdex_score"))
            samples = int(row.get("valid_samples") or 0)
            if score is not None and samples > 0:
                weighted_numerator += score * samples
                weighted_denominator += samples
        duration_fields = (
            ("median_ms", "Mediana de navegação", "ms"),
            ("p75_ms", "p75 de navegação", "ms"),
            ("p90_ms", "p90 de navegação", "ms"),
            ("p95_ms", "p95 de navegação", "ms"),
            ("p99_ms", "p99 de navegação", "ms"),
            ("trend_percent", "Tendência entre metades", "%"),
        )
        limitation = None
        if len(profiles) > 1 or len(thresholds) > 1:
            limitation = (
                "Perfis ou limiares T incompatíveis de Apdex foram detectados; as estatísticas agregadas usam apenas "
                f"o conjunto mais recente ({latest_profile}, T={latest_threshold})."
            )
        output.append(ApdexSummary(
            device=device,
            profile_ids=profiles,
            thresholds=thresholds,
            observations=len(items),
            urls=len({str(row.get("url") or "") for row in compatible if row.get("url")}),
            valid_samples=valid,
            invalid_samples=invalid,
            weighted_apdex=(weighted_numerator / weighted_denominator) if weighted_denominator else None,
            small_groups=sum(bool(row.get("small_group")) for row in compatible),
            final_groups=sum(bool(row.get("final_group")) for row in compatible),
            duration_metrics=tuple(
                MetricSummary(
                    label,
                    unit,
                    _state_stats_by_url(compatible, field, time_field="calculated_at"),
                )
                for field, label, unit in duration_fields
                if any(_number(row.get(field)) is not None for row in compatible)
            ),
            limitation=limitation,
        ))
    return tuple(output)


def summarize_findings(rows: tuple[dict[str, Any], ...]) -> FindingSummary:
    return FindingSummary(
        severity_counts=dict(Counter(str(row.get("severity") or "UNKNOWN") for row in rows)),
        category_counts=dict(Counter(str(row.get("category") or "UNKNOWN") for row in rows)),
        affected_pages=len({str(row.get("page_id")) for row in rows if row.get("page_id")}),
        observations=len(rows),
    )
