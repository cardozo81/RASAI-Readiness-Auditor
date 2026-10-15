"""Targeted #109 regressions: typed CAT-03 scoring groups and CAT-05 market."""
from __future__ import annotations

from rasai.catalog_report_presentation import _table
from rasai.catalog_report_search_trust import _contract_rows
from rasai.report_presentation import SCORING_CONCEPT_LABELS, humanize_report_html
from rasai.score_geo_004 import RULE_SCORING_CONTRACT
from rasai.semantic_coherence_reporting import (
    _semantic_provider_origin, _semantic_scoring_group_label,
)


def test_cat03_canonical_scoring_groups_all_have_public_labels() -> None:
    # Derive the test universe from the actual scoring contract. New groups
    # must be explicitly labeled instead of exposing a guessed name.
    groups = {contract.scoring_group for contract in RULE_SCORING_CONTRACT.values()}
    assert groups
    assert groups <= SCORING_CONCEPT_LABELS.keys()
    rows = [(_semantic_scoring_group_label(code),) for code in sorted(groups)]
    html = humanize_report_html(_table(("Grupo de pontuação",), rows), page_name="cat-03.html")
    assert "Condição técnica não catalogada" not in html
    for code in groups:
        assert _semantic_scoring_group_label(code) == SCORING_CONCEPT_LABELS[code]
        assert code not in html


def test_cat03_deterministic_assessments_are_not_labeled_as_ai() -> None:
    assert _semantic_provider_origin("DETERMINISTIC") == "Validação determinística"
    assert _semantic_provider_origin("DETERMINISTIC_BASELINE") == "Baseline determinístico"
    assert _semantic_provider_origin("NONE") == "Determinístico/sem IA"
    assert _semantic_provider_origin(None) == "Determinístico/sem IA"
    assert _semantic_provider_origin("OPENAI") == "Avaliação assistida por IA"
    html = humanize_report_html(
        _table(("Origem",), [(_semantic_provider_origin("DETERMINISTIC"),)]),
        page_name="cat-03.html",
    )
    assert "Condição técnica não catalogada" not in html
    assert "Validação determinística" in html


def test_cat05_contract_market_has_contextual_country_not_generic_br() -> None:
    rows = _contract_rows({"market": "BR", "region": "Porto Alegre"})
    country = next(value for key, value in rows if key == "País/mercado")
    assert country == "Brasil"
    rendered = humanize_report_html(
        _table(("Parâmetro", "Valor efetivo"), rows), page_name="cat-05.html"
    )
    assert "<td>País/mercado</td><td>Brasil</td>" in rendered
    assert "Condição técnica não catalogada" not in rendered
    unknown = _contract_rows({"market": "ZZ"})
    assert dict(unknown)["País/mercado"] == "País (código ISO: ZZ)"
