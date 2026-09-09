from __future__ import annotations

from pathlib import Path
import re
import tempfile

from rasai.indicator_provenance import enrich_indicator_provenance_html
from rasai.m24_reporting import _inject_references, _page as crawling_discovery_page
from rasai.report_contract import CANONICAL_NAV_ITEMS
from rasai.report_presentation import humanize_report_html
from rasai.report_semantics import enhance_report_html

ROOT = Path(__file__).resolve().parents[1]
_MILESTONE_RE = re.compile(r"(?i)(?<![A-Za-z0-9])m\d{1,3}")


def test_m24_readiness_projection_uses_live_schema_contract() -> None:
    source = (ROOT / "src/rasai/rasai_readiness_reporting.py").read_text(encoding="utf-8")
    assert "SELECT * FROM m24_runs WHERE audit_id=? LIMIT 1" in source
    assert "m24_runs WHERE audit_id=? ORDER BY completed_at" not in source


def test_public_html_humanizes_provider_strategy_and_inline_machine_state() -> None:
    html = "<div><span>SINGLE_PROVIDER</span><p>Sitemap em estado ABSENT.</p><code>SINGLE_PROVIDER ABSENT</code></div>"
    rendered = humanize_report_html(html)
    assert "Provedor único" in rendered
    assert "Sitemap em estado Ausente" in rendered
    assert "<code>SINGLE_PROVIDER ABSENT</code>" in rendered


def test_actionable_table_rows_use_global_result_state_contract() -> None:
    html = "<table><tbody><tr><td>BR-GEO-017</td><td>Alerta</td></tr><tr><td>BR-GEO-005</td><td>Aprovado</td></tr><tr><td>x</td><td>Erro</td></tr></tbody></table>"
    rendered = enhance_report_html(html, page_name="scoring.html", report_dir=ROOT)
    assert "result-state-warn" in rendered
    assert "result-state-good" in rendered
    assert "result-state-bad" in rendered
    assert "result-tag warn" in rendered


def test_canonical_report_order_follows_reading_flow() -> None:
    filenames = [filename for _label, filename in CANONICAL_NAV_ITEMS]
    expected = [
        "index.html", "readiness.html", "scoring.html", "mobile.html", "desktop.html",
        "crawling-discovery.html", "accessibility.html", "web-performance.html",
        "search-intelligence.html", "apdex.html", "apdex-experience.html",
        "content-suggestions.html", "remediation.html", "ai-usage.html",
        "ai-visibility.html", "observability.html", "quality.html", "references.html",
    ]
    assert filenames == expected


def test_documentation_declares_development_not_prior_public_releases() -> None:
    docs_index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    assert "desenvolvimento e validação" in docs_index
    assert "não corresponde" not in docs_index.lower() or "release" not in docs_index.lower()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/README.md" in readme


def test_consolidated_report_uses_normalized_findings_series_and_cons3() -> None:
    source = (ROOT / "src/rasai/consolidation/reporting.py").read_text(encoding="utf-8")
    assert 'REPORT_FORMAT_VERSION = "CONS-3"' in source
    assert 'primary_field="per_url"' in source
    assert "latest_audit_id" in source
    assert "Confiança da readiness" in source


def test_actionable_table_rows_are_idempotent() -> None:
    html = "<table><tbody><tr><td>BR-GEO-017</td><td>Alerta</td></tr></tbody></table>"
    once = enhance_report_html(html, page_name="scoring.html", report_dir=ROOT)
    twice = enhance_report_html(once, page_name="scoring.html", report_dir=ROOT)
    assert twice.count("result-state-warn") == once.count("result-state-warn")
    assert twice.count("result-cell warn") == once.count("result-cell warn")
    assert twice.count("result-tag warn") == once.count("result-tag warn")


def test_readiness_low_confidence_has_precedence_over_consolidated_state() -> None:
    html = (
        "<table><tbody><tr><td>Evidências e confiabilidade</td><td>75.0</td>"
        "<td>67%</td><td>Baixa</td><td>Consolidado</td></tr></tbody></table>"
    )
    rendered = enhance_report_html(html, page_name="readiness.html", report_dir=ROOT)
    assert "result-state-warn" in rendered
    assert "Cobertura insuficiente" in rendered
    assert "result-state-good" not in rendered


def test_readiness_partial_state_remains_warning_after_global_decoration() -> None:
    html = (
        "<table><tbody><tr><td>Evidências e confiabilidade</td><td>75.0</td>"
        "<td>100%</td><td>Alta</td><td>Parcial</td></tr></tbody></table>"
    )
    rendered = enhance_report_html(html, page_name="readiness.html", report_dir=ROOT)
    assert "result-state-warn" in rendered
    assert "result-state-good" not in rendered


def test_public_report_pipeline_removes_known_internal_delivery_labels() -> None:
    owned_labels = " | ".join(
        (
            "M18/M20",
            "M21/M22",
            "M21 + M22 · domínio Web Performance",
            "M23 · domínio Web Performance",
            "Web Performance · M23",
            "M23 · metodologia",
            "Estado M23",
            "M24-CD-001",
            "Rastreamento e descoberta M24",
            "m20-no-eligible-note",
            "m23-apdex-summary",
        )
    )
    html = f"<html><body><header class='hero'><h1>Teste</h1></header><main><p>{owned_labels}</p></main></body></html>"
    rendered = enhance_report_html(html, page_name="index.html", report_dir=ROOT)
    assert _MILESTONE_RE.search(rendered) is None
    assert "CRAWLING-DISCOVERY-001" in rendered
    assert "content-remediation-no-eligible-note" in rendered
    assert "apdex-summary" in rendered


def test_public_report_normalization_does_not_rewrite_audited_model_names() -> None:
    html = "<html><body><header><h1>Teste</h1></header><main><p>Produto M25 industrial observado na página.</p></main></body></html>"
    rendered = enrich_indicator_provenance_html(html, page_name="other.html")
    assert "Produto M25 industrial observado na página." in rendered


def test_crawling_discovery_owned_html_is_milestone_free() -> None:
    with tempfile.TemporaryDirectory() as directory:
        report_dir = Path(directory)
        html = crawling_discovery_page(
            {"run": None, "diagnostics": [], "ai": None, "attempts": []},
            report_dir,
        )
        assert _MILESTONE_RE.search(html) is None
        assert "CRAWLING-DISCOVERY-001" in html

        references = report_dir / "references.html"
        references.write_text(
            "<html><body><main><footer class='footer'>fim</footer></main></body></html>",
            encoding="utf-8",
        )
        _inject_references(report_dir)
        rendered = references.read_text(encoding="utf-8")
        assert _MILESTONE_RE.search(rendered) is None
        assert "crawling-discovery-references" in rendered
