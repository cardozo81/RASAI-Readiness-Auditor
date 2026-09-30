"""Isolated regression for semantic summary provenance (#109)."""
from rasai.catalog_report_evidence import _semantic_provenance_notice
from rasai.report_presentation import humanize_report_html


def test_deterministic_only_never_announces_ai_execution() -> None:
    html = _semantic_provenance_notice([
        {"provider": "DETERMINISTIC", "model": None},
        {"provider": "DETERMINISTIC_BASELINE", "model": None},
    ])
    assert "Avaliações semânticas persistidas" in html
    assert "2 determinística(s)" in html
    assert "0 com provedor informado" in html
    assert "Não há execução de IA inferível" in html
    assert "Análise semântica assistida por IA" not in html
    assert "ai-integrations.html" not in html
    assert humanize_report_html(html, page_name="cat-03.html") == html


def test_provider_identified_is_attributed_but_not_claimed_as_verified_call() -> None:
    html = _semantic_provenance_notice([
        {"provider": "DETERMINISTIC", "model": None},
        {"provider": "vendor-example", "model": "model-test"},
        {"provider": "NONE", "model": None},
    ])
    assert "1 determinística(s), 1 com provedor informado e 1 sem provedor" in html
    assert "vendor-example / model-test" in html
    assert "execução efetiva" in html
    assert "ai-integrations.html" in html
    assert "assistida por IA" not in html


def test_provider_name_is_escaped_for_html() -> None:
    html = _semantic_provenance_notice([
        {"provider": "Vendor & Partner", "model": "model-test"}
    ])
    assert "Vendor &amp; Partner" in html
