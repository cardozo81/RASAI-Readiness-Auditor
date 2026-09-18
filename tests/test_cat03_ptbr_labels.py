from rasai.semantic_coherence_reporting import (
    _PAGE_COHERENCE_LABELS,
    _PROPERTY_COHERENCE_LABELS,
    _dimension_label,
)


def test_cat03_dimension_labels_are_presented_in_pt_br() -> None:
    assert _dimension_label("SEMANTIC_STRUCTURE") == "Estrutura semântica"
    assert _dimension_label("ENTITY_CLARITY") == "Clareza de entidades"
    assert _dimension_label("STRUCTURED_DATA") == "Dados estruturados"
    assert _dimension_label("EVIDENCE_TRUST") == "Evidências e confiabilidade"
    assert _dimension_label("INTENT_COVERAGE") == "Cobertura de intenções"


def test_cat03_coherence_descriptions_are_presented_in_pt_br() -> None:
    assert _PROPERTY_COHERENCE_LABELS["SC-X02"].startswith("Oferta principal")
    assert _PAGE_COHERENCE_LABELS["SC-P01"].startswith("Título e conteúdo")
    assert "autoria" in _PAGE_COHERENCE_LABELS["SC-P12"].casefold()
    assert "atualização" in _PAGE_COHERENCE_LABELS["SC-P13"].casefold()
