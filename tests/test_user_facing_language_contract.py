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
    names = ["m18_reporting.py", "m20_reporting.py", "m21_reporting.py", "m22_quality_domains.py", "m23_reporting.py", "m24_reporting.py", "m25_reporting.py", "m26_reporting.py", "report_navigation.py", "report_semantics.py", "rasai_readiness_reporting.py", "indicator_provenance.py", "console_help.py", "source_quality_report_summary.py"]
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
