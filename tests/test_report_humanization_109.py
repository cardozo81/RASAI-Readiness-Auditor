"""Regressão isolada: campos tipados de CAT-04/05 e diagnóstico Chromium (#109)."""
from rasai.catalog_report_presentation import _table
from rasai.catalog_report_public_labels import public_text
from rasai.catalog_report_search_trust import _serp_geo_label


def test_cwv_metric_identifiers_remain_readable_and_assessment_is_localized() -> None:
    html = _table(("Métrica", "Avaliação"), [
        ("LCP", "NEEDS_IMPROVEMENT"),
        ("INP", "POOR"),
        ("CLS", "GOOD"),
    ])
    for label in ("LCP", "INP", "CLS", "Precisa melhorar", "Ruim", "Bom"):
        assert label in html
    assert "Condição técnica não catalogada" not in html


def test_serp_country_and_region_keep_geographical_meaning() -> None:
    assert _serp_geo_label("BR", None) == "Brasil"
    rendered = _serp_geo_label("BR", "Porto Alegre, Rio Grande do Sul, Brazil")
    assert rendered.startswith("Brasil")
    assert "Porto Alegre, Rio Grande do Sul, Brazil" in rendered
    assert _serp_geo_label("ZZ", "Localidade observada") == "Localidade observada"
    assert _serp_geo_label("ZZ", None) == "País (código ISO: ZZ)"
    html = _table(("País/região",), [(rendered,)])
    assert "Condição técnica não catalogada" not in html


def test_chromium_aborted_subresource_is_a_whole_localized_message() -> None:
    line = public_text("Falha: net::ERR_ABORTED")
    assert line == "Falha: Requisição interrompida pelo navegador"
    assert "net::Condição técnica" not in line
    assert "ERR_ABORTED" not in line
