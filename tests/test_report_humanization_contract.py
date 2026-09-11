from __future__ import annotations

from pathlib import Path
import tempfile

from rasai.score_geo_004 import FEATURE_ORDER, SCORING_VERSION
from rasai.score_geo_004_reporting import _dimension_list


def _page(body: str) -> str:
    return (
        "<html><body><aside class='app-nav'><nav></nav></aside>"
        f"<main>{body}</main></body></html>"
    )


def test_scoring_dimension_list_never_exposes_raw_dimension_enums() -> None:
    html = _dimension_list(SCORING_VERSION)
    for dimension in FEATURE_ORDER:
        assert f">{dimension}<" not in html
        assert f"<code>{dimension}</code>" not in html
    assert "Discovery &amp; Crawler Access" in html
    assert "Indexability" in html
    assert "Rendering &amp; Extractability" in html
    assert "Structured Data" in html
    assert "Citation Readiness" in html
    assert "Content Value" in html


def test_final_report_normalization_humanizes_every_html_surface() -> None:
    from rasai import report_navigation
    from rasai.report_registry import install as install_report_registry

    install_report_registry()
    with tempfile.TemporaryDirectory() as tmp:
        report_dir = Path(tmp)
        (report_dir / "css").mkdir()
        (report_dir / "css" / "site.css").write_text("body{}\n", encoding="utf-8")
        (report_dir / "index.html").write_text(
            _page("<table><tr><td>CONTENT_VALUE</td><td>BLOCKED</td></tr></table>"),
            encoding="utf-8",
        )
        (report_dir / "readiness.html").write_text(
            _page("<table><tr><td>Capacidade de Indexação</td><td>NOT_CONSOLIDATED</td></tr></table>"),
            encoding="utf-8",
        )
        (report_dir / "mobile.html").write_text(
            _page("<table><tr><td>Extração de Conteúdo</td><td>Dados Estruturados</td></tr></table>"),
            encoding="utf-8",
        )

        report_navigation.normalize_report_navigation(report_dir)

        index_html = (report_dir / "index.html").read_text(encoding="utf-8")
        readiness_html = (report_dir / "readiness.html").read_text(encoding="utf-8")
        mobile_html = (report_dir / "mobile.html").read_text(encoding="utf-8")
        assert "<td>Content Value</td>" in index_html
        assert ">Bloqueado<" in index_html
        assert "BLOCKED" not in index_html
        assert "<td>Indexability</td>" in readiness_html
        assert ">Não consolidado<" in readiness_html
        assert "NOT_CONSOLIDATED" not in readiness_html
        assert ">Rendering &amp; Extractability<" in mobile_html
        assert ">Structured Data<" in mobile_html
        assert "CONTENT_VALUE" not in index_html
        assert "Capacidade de Indexação" not in readiness_html
        assert "Extração de Conteúdo" not in mobile_html


def test_sari_methodology_uses_human_title_and_keeps_contract_id_technical() -> None:
    from rasai.report_registry import _sari_method_panel

    with tempfile.TemporaryDirectory() as tmp:
        html = _sari_method_panel(Path(tmp), "scoring.html")
    assert "<h2>Hierarchical Weighted Readiness</h2>" in html
    assert "<code>HIERARCHICAL_WEIGHTED_READINESS_V1</code>" in html
    assert "<h2>HIERARCHICAL_WEIGHTED_READINESS_V1</h2>" not in html
