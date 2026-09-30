"""Regressão isolada: campos tipados de CAT-04/05 e diagnóstico Chromium (#109)."""
from rasai.catalog_report_presentation import _table
from rasai.catalog_report_public_labels import public_text
from rasai.catalog_report_search_trust import _serp_geo_label
from rasai.report_presentation import humanize_report_html


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



def test_final_html_presentation_keeps_cwv_table_identifiers() -> None:
    # The CAT-04 table generator is not the final rendering stage. The earlier
    # regression passed before humanize_report_html destroyed these labels.
    initial = _table(("Métrica", "Avaliação"), [
        ("LCP", "NEEDS_IMPROVEMENT"),
        ("INP", "POOR"),
        ("CLS", "GOOD"),
    ])
    final = humanize_report_html(initial, page_name="cat-04.html")
    for metric in ("LCP", "INP", "CLS"):
        assert f"<td>{metric}</td>" in final
    for assessment in ("Precisa melhorar", "Ruim", "Bom"):
        assert assessment in final
    assert "Condição técnica não catalogada" not in final
    # Unknown enums must still be humanized; do not globally expose raw codes.
    assert "Condição técnica não catalogada" in humanize_report_html("<td>NEW_UNKNOWN_METRIC</td>")
    assert humanize_report_html(final, page_name="cat-04.html") == final
