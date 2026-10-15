"""#328: CAT section readability is presentation only, including print/mobile."""
from pathlib import Path

from rasai import catalog_report_page as page
from rasai.catalog_report_style import _CSS


def _sources(monkeypatch):
    monkeypatch.setattr(page, "_catalog_metrics", lambda *_args: {})
    monkeypatch.setattr(page, "_catalog_metric_rows", lambda *_args: ())
    monkeypatch.setattr(page, "_apdex_samples_html",
                        lambda *_args, **_kwargs: "<p>Dados persistidos de amostras</p>")
    monkeypatch.setattr(page, "_ux_profile_execution_html",
                        lambda *_args: "<p>Dados persistidos de perfis</p>")


def test_cat06_readability_scopes_only_sample_section(monkeypatch):
    _sources(monkeypatch)
    html = page._catalog_results_html(Path("unused.db"), object(), "CAT-06")
    assert "class='subsection cat-apdex-readable'><h3>Amostras</h3>" in html
    assert html.count("cat-apdex-readable") == 1
    assert "Dados persistidos de amostras" in html


def test_cat07_separates_profiles_and_samples_without_reordering(monkeypatch):
    _sources(monkeypatch)
    html = page._catalog_results_html(Path("unused.db"), object(), "CAT-07")
    assert html.count("cat-apdex-readable") == 2
    assert html.index("Tentativas e retornos por perfil") < html.index("<h3>Amostras</h3>")
    assert "Dados persistidos de amostras" in html
    assert "Dados persistidos de perfis" in html
    assert "fuso horário de apresentação" in html


def test_css_scoped_to_apdex_sections_and_print_remains_visible():
    assert ".cat-apdex-readable{" in _CSS
    assert "[data-contract='CAT07-ARCHITECTURE-358']" in _CSS
    assert "@media(max-width:700px)" in _CSS
    assert "@media print{" in _CSS
    block = _CSS.split("/* #328:")[1]
    assert "break-inside:auto" in block
    assert "display:none" not in block
    assert "max-width:100%" in block
