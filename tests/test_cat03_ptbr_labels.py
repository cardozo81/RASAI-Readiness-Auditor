from rasai.semantic_coherence_reporting import (
    _PAGE_COHERENCE_LABELS,
    _PROPERTY_COHERENCE_LABELS,
    _dimension_label,
)


def test_cat03_dimension_labels_are_pt_br_without_internal_translation_tooltip() -> None:
    semantic = str(_dimension_label("SEMANTIC_STRUCTURE"))
    entity = str(_dimension_label("ENTITY_CLARITY"))
    structured = str(_dimension_label("STRUCTURED_DATA"))
    evidence = str(_dimension_label("EVIDENCE_TRUST"))
    intent = str(_dimension_label("INTENT_COVERAGE"))

    assert semantic == "Estrutura semântica"
    assert entity == "Clareza de entidades"
    assert structured == "Dados estruturados"
    assert evidence == "Evidências e confiabilidade"
    assert intent == "Cobertura de intenções"
    assert "🌐" not in semantic
    assert "Semantic Structure" not in semantic


def test_cat03_coherence_descriptions_are_presented_in_pt_br() -> None:
    assert _PROPERTY_COHERENCE_LABELS["SC-X02"].startswith("Oferta principal")
    assert _PAGE_COHERENCE_LABELS["SC-P01"].startswith("Título e conteúdo")
    assert "autoria" in _PAGE_COHERENCE_LABELS["SC-P12"].casefold()
    assert "atualização" in _PAGE_COHERENCE_LABELS["SC-P13"].casefold()
