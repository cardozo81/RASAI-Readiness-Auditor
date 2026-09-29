from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MILESTONE = re.compile(r"(?<![\w-])M\d{1,2}(?![\w-])")


def test_documentation_has_no_standalone_delivery_milestone_labels() -> None:
    failures = []
    for path in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
        matches = sorted(set(MILESTONE.findall(path.read_text(encoding="utf-8"))))
        if matches:
            failures.append(f"{path.relative_to(ROOT)}: {matches}")
    assert not failures, "\n".join(failures)


def test_user_facing_templates_have_no_standalone_delivery_milestone_labels() -> None:
    names = ["m20_reporting.py", "m21_reporting.py", "m22_quality_domains.py", "m23_reporting.py", "m24_reporting.py", "report_navigation.py", "report_semantics.py", "indicator_provenance.py", "console_help.py"]
    failures = []
    for name in names:
        path = ROOT / "src/rasai" / name
        matches = sorted(set(MILESTONE.findall(path.read_text(encoding="utf-8"))))
        if matches:
            failures.append(f"{name}: {matches}")
    assert not failures, "\n".join(failures)


def test_accessibility_zero_is_not_presented_as_proof_of_no_failures() -> None:
    from rasai.report_semantics import enhance_report_html
    html = "<div class='metric'><small>Falhas automatizadas</small><strong>0</strong></div>"
    rendered = enhance_report_html(html, page_name="accessibility.html", report_dir=ROOT)
    assert "Nenhuma ocorrência registrada" in rendered
    assert "Sem falhas detectadas" not in rendered


def test_unavailable_cwv_is_neutral() -> None:
    from rasai.report_semantics import enhance_report_html
    html = "<div class='metric'><small>CWV</small><strong>UNAVAILABLE</strong></div>"
    rendered = enhance_report_html(html, page_name="web-performance.html", report_dir=ROOT)
    assert "Dados de campo indisponíveis" in rendered
    assert "result-state-neutral" in rendered


def test_legacy_milestone_chrome_is_sanitized_without_touching_audited_copy() -> None:
    from rasai.report_consistency_v2 import _sanitize_presentation
    html = "<p>Produto M20 com motor M23 permanece conteúdo auditado.</p><div>M22 · diagnóstico técnico</div>"
    rendered = _sanitize_presentation(html)
    assert "Produto M20 com motor M23 permanece conteúdo auditado." in rendered
    assert "Diagnóstico técnico" in rendered


def test_single_provider_strategy_is_not_exposed_as_raw_enum() -> None:
    from rasai.report_presentation import humanize_report_html
    rendered = humanize_report_html("<div><span>SINGLE_PROVIDER</span></div>")
    assert "Provedor único" in rendered
    assert ">SINGLE_PROVIDER<" not in rendered


def test_common_report_machine_values_are_humanized() -> None:
    from rasai.report_presentation import humanize_report_html

    html = (
        "<table><tr><td>INTERNAL_LINKS</td><td>PAGE_ACCESS</td><td>SPA_NAVIGATION</td>"
        "<td>SPA_ROUTE</td><td>DEGRADED</td><td>EXISTING_REVIEW</td>"
        "<td>AUTH_ERROR</td><td>NAVIGATION_TIMEOUT</td></tr></table>"
    )
    rendered = humanize_report_html(html)
    assert "Internal Links" in rendered
    assert "Page Access" in rendered
    assert "SPA Navigation" in rendered
    assert "SPA Route" in rendered
    assert "Execução com limitações" in rendered
    assert "Revisão do JSON-LD existente" in rendered
    assert "Erro de autenticação" in rendered
    assert "Tempo limite de navegação excedido" in rendered
    for raw in ("INTERNAL_LINKS", "PAGE_ACCESS", "SPA_NAVIGATION", "SPA_ROUTE", "DEGRADED", "EXISTING_REVIEW"):
        assert f">{raw}<" not in rendered


def test_technical_identifiers_remain_canonical_when_they_are_traceability_data() -> None:
    from rasai.report_presentation import humanize_report_html

    html = (
        "<div><code>RASAI_AI_CONTENT_REMEDIATION</code>"
        "<span>BR-GEO-017</span><strong>RASAI_TABLET_CONTROLLED4G_V1</strong>"
        "<pre>DEGRADED SINGLE_PROVIDER</pre></div>"
    )
    rendered = humanize_report_html(html)
    assert "RASAI_AI_CONTENT_REMEDIATION" in rendered
    assert "BR-GEO-017" in rendered
    assert "RASAI_TABLET_CONTROLLED4G_V1" in rendered
    assert "<pre>DEGRADED SINGLE_PROVIDER</pre>" in rendered

def test_reader_transparency_does_not_expose_fulfillment_enums() -> None:
    from rasai.report_reader_experience import _render_work_items

    rendered = _render_work_items(
        (
            {
                "component": "TECHNICAL_AI",
                "scope_key": "AUDIT",
                "status": "WAITING_FOR_DATA",
                "attempt_count": 1,
                "last_error_code": "AI_NOT_AUTHORIZED_FOR_EXECUTION",
            },
        )
    )
    assert "Análise técnica por IA" in rendered
    assert "Contexto da execução: escopo Auditoria" in rendered
    assert "IA não autorizada para execução nesta auditoria" in rendered
    assert "TECHNICAL_AI" not in rendered
    assert "AI_NOT_AUTHORIZED_FOR_EXECUTION" not in rendered
    assert ">AUDIT<" not in rendered


def test_serp_runtime_notice_uses_human_diagnostic_labels() -> None:
    from rasai.runtime_adherence_extensions import _issue_notice

    rendered = _issue_notice(
        (
            {
                "query": "seguro auto",
                "provider": "SerpApi",
                "error_code": "SERP_PROVIDER_ERROR",
                "error_message": "HTTP 503 unavailable",
            },
        ),
        title="Limitação de busca",
    )
    assert "Falha transitória do provedor" in rendered
    assert "Erro do provedor de SERP" in rendered
    assert "TECHNICAL_TRANSIENT_PROVIDER" not in rendered
    assert "SERP_PROVIDER_ERROR" not in rendered


def test_legacy_report_error_summaries_use_human_labels() -> None:
    from rasai.m20_reporting import _attempt_error_summary
    from rasai.report_consistency_v2 import _attempt_reason

    summary = _attempt_error_summary(
        [
            {
                "error_class": "SERVER_ERROR",
                "error_type": "TimeoutError",
                "error_code": "SERVICE_UNAVAILABLE",
            }
        ]
    )
    assert "Erro do servidor" in summary
    assert "Tempo limite excedido" in summary
    assert "Serviço indisponível" in summary
    assert "SERVER_ERROR" not in summary
    assert "TimeoutError" not in summary
    assert "SERVICE_UNAVAILABLE" not in summary

    reason = _attempt_reason(
        {
            "http_status": 503,
            "error_code": "SERVICE_UNAVAILABLE",
            "error_message": "indisponível — tente novamente",
            "status": "FAILED",
        }
    )
    assert reason == "HTTP 503 - Serviço indisponível - indisponível - tente novamente"
    assert "SERVICE_UNAVAILABLE" not in reason
    assert "—" not in reason

