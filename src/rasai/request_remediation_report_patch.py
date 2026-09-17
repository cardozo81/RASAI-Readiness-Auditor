"""Report-only composition for deterministic request error groups.

CAT-07 keeps observation/sample evidence. CAT-09 is solution-oriented and shows one
consolidated remediation per deterministic group, with individual events only on demand.
"""
from __future__ import annotations

from typing import Any, Sequence

_INSTALLED = False


def _cat07_group_summary(database: Any, audit_id: str) -> str:
    from rasai import catalog_report_analysis as analysis
    from rasai.request_remediation_intelligence import (
        collect_request_error_evidence,
        group_request_error_evidence,
    )

    events, sample_universe = collect_request_error_evidence(database, audit_id, sources={"CAT-07"})
    groups = group_request_error_evidence(events, sample_universe, audit_id=audit_id)
    if not groups:
        return ""
    rows: list[Sequence[Any]] = []
    for group in groups:
        ratio = float(group.get("recurrence_ratio") or 0.0)
        resources = list(group.get("resource_urls") or [])
        sample = resources[0] if resources else "—"
        if len(resources) > 1:
            sample += f" · +{len(resources) - 1} recurso(s)"
        observed = " · ".join(str(value) for value in group.get("observed_impacts", [])) or "Diagnóstico técnico"
        rows.append((
            group.get("title") or "Grupo técnico",
            group.get("problem_count") or 0,
            group.get("occurrence_count") or 0,
            f"{group.get('affected_sample_count') or 0}/{group.get('total_sample_count') or 0}",
            f"{ratio * 100:.1f}% · {group.get('recurrence_class') or '—'}",
            str(group.get("party_scope") or "—").replace("FIRST_PARTY", "Primeira parte").replace("THIRD_PARTY", "Terceiro").replace("UNKNOWN", "Indeterminado"),
            observed,
            sample,
        ))
    return (
        "<details open><summary>Padrões de erro entre as amostras (" + str(len(groups)) + ")</summary>"
        "<div class='detail-body'><p class='section-lead'>A recorrência abaixo é calculada deterministicamente sobre as amostras coletadas. "
        "Os rótulos recorrente/intermitente/ocasional descrevem frequência e não atribuem causalidade estrutural por si sós. "
        "Os eventos individuais permanecem disponíveis logo abaixo.</p>"
        + analysis._table(
            ("Grupo / solução possível", "Problemas", "Ocorrências", "Amostras", "Recorrência", "Origem", "Impacto observado", "Exemplo de recurso"),
            rows,
            sortable=True,
            page_size=10 if len(rows) > 10 else None,
        )
        + "</div></details>"
    )


def _patch_cat07() -> None:
    from rasai import accepted_apdex_error_evidence as evidence

    current = evidence._error_details_html
    if getattr(current, "_rasai_grouped_request_errors", False):
        return

    def error_details_html(database: Any, audit_id: str) -> str:
        base = current(database, audit_id)
        if not base:
            return base
        try:
            grouped = _cat07_group_summary(database, audit_id)
        except Exception:
            grouped = ""
        return grouped + base

    error_details_html._rasai_grouped_request_errors = True
    error_details_html._rasai_original = current
    evidence._error_details_html = error_details_html


def _patch_cat09() -> None:
    from rasai import accepted_audit_refinements as refinements

    current = refinements._remediation_html
    if getattr(current, "_rasai_request_remediation_section", False):
        return

    def remediation_html(database: Any, data: Any) -> str:
        from rasai import catalog_report_analysis as analysis
        from rasai.request_remediation_intelligence import request_remediation_report_html

        base = current(database, data)
        try:
            section = request_remediation_report_html(database, data.audit_id, analysis)
        except Exception:
            section = ""
        return section + base

    remediation_html._rasai_request_remediation_section = True
    remediation_html._rasai_original = current
    refinements._remediation_html = remediation_html


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai.request_remediation_telemetry_patch import install as install_telemetry

    _patch_cat07()
    _patch_cat09()
    install_telemetry()
    _INSTALLED = True


__all__ = ["install"]
