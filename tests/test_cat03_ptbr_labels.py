from rasai.semantic_coherence_reporting import (
    _PAGE_COHERENCE_LABELS,
    _PROPERTY_COHERENCE_LABELS,
    _dimension_label,
)


def test_cat03_dimension_labels_are_presented_in_pt_br_with_original_tooltip() -> None:
    semantic = str(_dimension_label("SEMANTIC_STRUCTURE"))
    entity = str(_dimension_label("ENTITY_CLARITY"))
    structured = str(_dimension_label("STRUCTURED_DATA"))
    evidence = str(_dimension_label("EVIDENCE_TRUST"))
    intent = str(_dimension_label("INTENT_COVERAGE"))

    assert "Estrutura semântica" in semantic
    assert "title='Semantic Structure'" in semantic
    assert "Clareza de entidades" in entity
    assert "title='Entity Clarity'" in entity
    assert "Dados estruturados" in structured
    assert "Evidências e confiabilidade" in evidence
    assert "Cobertura de intenções" in intent
    assert "🌐" in semantic


def test_cat03_coherence_descriptions_are_presented_in_pt_br() -> None:
    assert _PROPERTY_COHERENCE_LABELS["SC-X02"].startswith("Oferta principal")
    assert _PAGE_COHERENCE_LABELS["SC-P01"].startswith("Título e conteúdo")
    assert "autoria" in _PAGE_COHERENCE_LABELS["SC-P12"].casefold()
    assert "atualização" in _PAGE_COHERENCE_LABELS["SC-P13"].casefold()
