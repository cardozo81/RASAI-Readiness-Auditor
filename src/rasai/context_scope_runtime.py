"""Runtime integration for the canonical capture-context contract.

The project already uses additive runtime integration modules. This installer keeps the
context contract centralized while leaving the scoring engine untouched.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from rasai.context_scope import CONTEXT_SCOPE_CONTRACT_VERSION
from rasai.device_context_capture import install as install_device_context_capture


_INSTALLED = False
_CONTEXT_FILE = "context.html"

_NAV_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Visão e readiness", ("index.html", "readiness.html", "scoring.html")),
    (
        "Coleta e dispositivos",
        (
            "context.html",
            "crawling-discovery.html",
            "mobile.html",
            "desktop.html",
            "web-performance.html",
            "accessibility.html",
            "apdex.html",
            "apdex-experience.html",
        ),
    ),
    (
        "Search e IA",
        ("search-intelligence.html", "ai-visibility.html", "observability.html", "ai-usage.html"),
    ),
    (
        "Ações e referência",
        ("content-suggestions.html", "remediation.html", "quality.html", "references.html"),
    ),
)


def _register_report_surface() -> None:
    from rasai import report_contract, report_manifest, report_navigation, report_registry
    from rasai.report_contract import ReportSurface

    if not any(surface.filename == _CONTEXT_FILE for surface in report_contract.REPORT_SURFACES):
        surface = ReportSurface(
            id="context",
            filename=_CONTEXT_FILE,
            label="Contexto de coleta",
            optional=False,
            inputs=(
                "audit.db",
                "recursos origin-scoped",
                "snapshots Mobile/Desktop",
                "browser_metadata",
            ),
            outputs=(
                "topologia ORIGIN/URL/DEVICE_SNAPSHOT/PROFILE_MEASUREMENT",
                "variação do documento por dispositivo",
                "diagnósticos de runtime por snapshot",
            ),
            required_dependencies=("audit.db",),
            ai_usage="Nenhum. Esta página não dispara IA nem rede adicional.",
            score_impact="Nenhum; apresenta escopo de captura sem alterar fórmulas ou resultados persistidos.",
            source_of_truth="audit.db + metadata dos snapshots já capturados",
        )
        items = list(report_contract.REPORT_SURFACES)
        insertion = next(
            (index + 1 for index, item in enumerate(items) if item.filename == "scoring.html"),
            3,
        )
        items.insert(insertion, surface)
        report_contract.REPORT_SURFACES = tuple(items)

    report_contract.CANONICAL_NAV_ITEMS = tuple(
        (surface.label, surface.filename) for surface in report_contract.REPORT_SURFACES
    )
    report_contract.CANONICAL_FILENAMES = tuple(
        surface.filename for surface in report_contract.REPORT_SURFACES
    )

    # Modules import these tuples by value. Project the single current contract into
    # their module globals so every final normalization and manifest uses the same menu.
    report_navigation.CANONICAL_NAV_ITEMS = report_contract.CANONICAL_NAV_ITEMS
    report_navigation.NAV_ITEMS = report_contract.CANONICAL_NAV_ITEMS
    report_registry.CANONICAL_NAV_ITEMS = report_contract.CANONICAL_NAV_ITEMS
    report_registry.REPORT_SURFACES = report_contract.REPORT_SURFACES
    report_manifest.REPORT_SURFACES = report_contract.REPORT_SURFACES


def _patch_grouped_navigation() -> None:
    from rasai import report_navigation

    if getattr(report_navigation, "_rasai_context_grouped_navigation", False):
        return

    def grouped_navigation(
        report_dir: Path,
        current: str,
        *,
        generated_at: Any = None,
        software_version: str | None = None,
    ) -> str:
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
                group_links.append(
                    f"<a class='{'active' if filename == current else ''}' href='{escape(filename)}'>{escape(label)}</a>"
                )
            if group_links:
                open_attr = " open" if contains_active or group_label in {"Visão e readiness", "Coleta e dispositivos"} else ""
                sections.append(
                    f"<details class='rasai-nav-group'{open_attr}>"
                    f"<summary style='padding:10px 12px 5px;cursor:pointer;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;opacity:.78'>{escape(group_label)}</summary>"
                    + "".join(group_links)
                    + "</details>"
                )
        remaining = [
            f"<a class='{'active' if filename == current else ''}' href='{escape(filename)}'>{escape(label)}</a>"
            for label, filename in links if filename not in consumed
        ]
        if remaining:
            sections.append(
                "<details class='rasai-nav-group' open><summary style='padding:10px 12px 5px;cursor:pointer;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;opacity:.78'>Outros</summary>"
                + "".join(remaining) + "</details>"
            )
        generated_label = report_navigation.format_report_generated_at(generated_at)
        return (
            "<aside class='app-nav' aria-label='Navegação do relatório'>"
            "<div class='brand'><small>RASAi Auditor</small><strong>Relatório da auditoria</strong>"
            f"<small>Gerado em {escape(generated_label)} - Horário de Brasília</small></div>"
            f"<nav>{''.join(sections)}</nav></aside>"
        )

    report_navigation.render_report_navigation = grouped_navigation
    report_navigation._rasai_context_grouped_navigation = True


def _patch_report_completion() -> None:
    from rasai import report_completion, report_navigation
    from rasai.context_reporting import write_context_report
    from rasai.report_manifest import write_report_manifest

    if getattr(report_completion, "_rasai_context_scope_completion", False):
        return

    if _CONTEXT_FILE not in report_completion.AUDIT_ALWAYS_PAGES:
        report_completion.AUDIT_ALWAYS_PAGES = (
            *report_completion.AUDIT_ALWAYS_PAGES,
            _CONTEXT_FILE,
        )

    original = report_completion.finalize_audit_report_site

    def finalize_with_context(*, audit_id: str, workspace: Any, context_interpretations=(), routing_snapshot=None):
        base = original(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )
        errors = list(base.renderer_errors)
        try:
            write_context_report(audit_id=audit_id, workspace=workspace)
            report_dir = workspace.root / "report"
            report_navigation.normalize_report_navigation(report_dir)
            write_report_manifest(report_dir)
        except Exception as exc:
            errors.append(f"context:{type(exc).__name__}:{str(exc)[:240]}")
        inspected = report_completion.inspect_audit_report_site(audit_id=audit_id, workspace=workspace)
        return report_completion.AuditReportCompletion(
            expected_pages=inspected.expected_pages,
            generated_pages=inspected.generated_pages,
            missing_pages=inspected.missing_pages,
            renderer_errors=tuple(errors),
        )

    report_completion.finalize_audit_report_site = finalize_with_context
    report_completion._rasai_context_scope_completion = True


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai.report_registry import install as install_report_registry

    install_report_registry()
    install_device_context_capture()
    _register_report_surface()
    _patch_grouped_navigation()
    _patch_report_completion()
    _INSTALLED = True


def contract_version() -> str:
    return CONTEXT_SCOPE_CONTRACT_VERSION
