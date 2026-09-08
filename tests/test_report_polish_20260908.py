from __future__ import annotations

from pathlib import Path

from rasai.report_contract import CANONICAL_NAV_ITEMS
from rasai.report_presentation import humanize_report_html
from rasai.report_semantics import enhance_report_html

ROOT = Path(__file__).resolve().parents[1]


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
        "crawling-discovery.html", "accessibility.html", "web-performance.html", "apdex.html",
        "apdex-experience.html", "content-suggestions.html", "remediation.html", "ai-usage.html",
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
