"""Runtime integration for the canonical capture-context contract.

The public report catalog lives in ``report_contract``. This installer only wires that
single contract into generators, capture/runtime enrichment and final report completion;
it does not create a second report-surface registry and does not touch scoring.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from rasai.context_scope import CONTEXT_SCOPE_CONTRACT_VERSION
from rasai.device_context_capture import install as install_device_context_capture
from rasai.synthetic_profile_console_runtime import install as install_synthetic_profile_console_runtime
from rasai.synthetic_profile_runtime import install as install_synthetic_profile_runtime
from rasai.synthetic_profile_saas_runtime import install as install_synthetic_profile_saas_runtime

_INSTALLED = False
_CONTEXT_FILE = "context.html"

_NAV_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Visão e readiness", ("index.html", "readiness.html", "scoring.html")),
    ("Coleta e dispositivos", ("context.html", "crawling-discovery.html", "mobile.html", "desktop.html", "web-performance.html", "accessibility.html", "apdex.html", "apdex-experience.html")),
    ("Search e IA", ("search-intelligence.html", "ai-visibility.html", "observability.html", "ai-usage.html")),
    ("Ações e referência", ("content-suggestions.html", "remediation.html", "quality.html", "references.html")),
)


def _project_report_contract() -> None:
    from rasai import report_contract, report_manifest, report_navigation, report_registry
    report_navigation.CANONICAL_NAV_ITEMS = report_contract.CANONICAL_NAV_ITEMS
    report_navigation.NAV_ITEMS = report_contract.CANONICAL_NAV_ITEMS
    report_registry.CANONICAL_NAV_ITEMS = report_contract.CANONICAL_NAV_ITEMS
    report_registry.REPORT_SURFACES = report_contract.REPORT_SURFACES
    report_manifest.REPORT_SURFACES = report_contract.REPORT_SURFACES


def _patch_grouped_navigation() -> None:
    from rasai import report_navigation
    if getattr(report_navigation, "_rasai_context_grouped_navigation", False):
        return

    def grouped_navigation(report_dir: Path, current: str, *, generated_at: Any = None, software_version: str | None = None) -> str:
        del software_version
        links = report_navigation.available_navigation(report_dir, current)
        by_file = {filename: label for label, filename in links}
        consumed: set[str] = set()
        sections: list[str] = []
        for group_label, filenames in _NAV_GROUPS:
            group_links: list[str] = []
            contains_active = False
            for filename in filenames:
                label = by_file.get(filename)
                if label is None:
                    continue
                consumed.add(filename)
                contains_active = contains_active or filename == current
                group_links.append(f"<a class='{'active' if filename == current else ''}' href='{escape(filename)}'>{escape(label)}</a>")
            if group_links:
                open_attr = " open" if contains_active or group_label in {"Visão e readiness", "Coleta e dispositivos"} else ""
                sections.append(f"<details class='rasai-nav-group'{open_attr}><summary style='padding:10px 12px 5px;cursor:pointer;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;opacity:.78'>{escape(group_label)}</summary>" + "".join(group_links) + "</details>")
        remaining = [f"<a class='{'active' if filename == current else ''}' href='{escape(filename)}'>{escape(label)}</a>" for label, filename in links if filename not in consumed]
        if remaining:
            sections.append("<details class='rasai-nav-group' open><summary style='padding:10px 12px 5px;cursor:pointer;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;opacity:.78'>Outros</summary>" + "".join(remaining) + "</details>")
        generated_label = report_navigation.format_report_generated_at(generated_at)
        return "<aside class='app-nav' aria-label='Navegação do relatório'><div class='brand'><small>RASAi Auditor</small><strong>Relatório da auditoria</strong>" + f"<small>Gerado em {escape(generated_label)} - Horário de Brasília</small></div><nav>{''.join(sections)}</nav></aside>"

    report_navigation.render_report_navigation = grouped_navigation
    report_navigation._rasai_context_grouped_navigation = True


def _patch_report_completion() -> None:
    from rasai import report_completion, report_navigation
    from rasai.context_reporting import write_context_report
    from rasai.report_manifest import write_report_manifest
    from rasai.report_scale_ux import enhance_report_directory
    from rasai.synthetic_profile_reporting import enrich_synthetic_profile_reports

    if getattr(report_completion, "_rasai_context_scope_completion", False):
        return
    if _CONTEXT_FILE not in report_completion.AUDIT_ALWAYS_PAGES:
        report_completion.AUDIT_ALWAYS_PAGES = (*report_completion.AUDIT_ALWAYS_PAGES, _CONTEXT_FILE)
    original = report_completion.finalize_audit_report_site

    def finalize_with_context(*, audit_id: str, workspace: Any, context_interpretations=(), routing_snapshot=None):
        base = original(audit_id=audit_id, workspace=workspace, context_interpretations=context_interpretations, routing_snapshot=routing_snapshot)
        errors = list(base.renderer_errors)
        try:
            write_context_report(audit_id=audit_id, workspace=workspace)
            enrich_synthetic_profile_reports(audit_id=audit_id, workspace=workspace)
            report_dir = workspace.root / "report"
            report_navigation.normalize_report_navigation(report_dir)
            enhance_report_directory(report_dir)
            write_report_manifest(report_dir)
        except Exception as exc:
            errors.append(f"context:{type(exc).__name__}:{str(exc)[:240]}")
        inspected = report_completion.inspect_audit_report_site(audit_id=audit_id, workspace=workspace)
        return report_completion.AuditReportCompletion(expected_pages=inspected.expected_pages, generated_pages=inspected.generated_pages, missing_pages=inspected.missing_pages, renderer_errors=tuple(errors))

    report_completion.finalize_audit_report_site = finalize_with_context
    report_completion._rasai_context_scope_completion = True


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai.report_registry import install as install_report_registry
    install_report_registry()
    install_device_context_capture()
    install_synthetic_profile_runtime()
    install_synthetic_profile_console_runtime()
    install_synthetic_profile_saas_runtime()
    _project_report_contract()
    _patch_grouped_navigation()
    _patch_report_completion()
    _INSTALLED = True


def contract_version() -> str:
    return CONTEXT_SCOPE_CONTRACT_VERSION
