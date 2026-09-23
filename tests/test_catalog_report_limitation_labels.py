from __future__ import annotations

from rasai.catalog_report_adherence import _human_limitation
from rasai.catalog_report_public_labels import public_label


def test_persisted_audit_scope_limitations_are_humanized() -> None:
    assert _human_limitation(
        "MAX_PAGES_REACHED:discovered=19;audited=1"
    ) == "Limite máximo de páginas atingido: 19 URLs descobertas; 1 URL auditada"
    assert _human_limitation(
        "RENDERED_LINKS_OUTSIDE_AUDIT_UNIVERSE_MAX_PAGES:17"
    ) == (
        "Links renderizados fora do universo auditado devido ao limite máximo de páginas: "
        "17 URLs renderizadas fora do universo auditado"
    )
    assert _human_limitation(
        "RENDERED_DISCOVERY_GAP:1"
    ) == "Lacuna na descoberta renderizada: 1 URL renderizada fora do universo auditado"


def test_ai_limitations_translate_known_codes_but_preserve_technical_rule_ids() -> None:
    assert _human_limitation(
        "AI_PROVIDER_UNAVAILABLE:NETWORK_ERROR"
    ) == "Provedor de IA indisponível: Erro de rede"
    assert _human_limitation(
        "AI_WAITING_FOR_DATA:TECHNICAL_PREREQUISITE_BR_GEO_020_UNKNOWN"
    ) == (
        "IA aguardando dados necessários: "
        "pré-requisito técnico BR-GEO-020: não determinado"
    )
    assert _human_limitation(
        "AI_NOT_CONFIGURED"
    ) == "IA selecionada sem configuração elegível"


def test_future_unknown_limitation_remains_auditable_instead_of_being_invented() -> None:
    raw = "CUSTOM_FUTURE_LIMITATION"
    assert _human_limitation(raw) == f"Limitação técnica registrada ({raw})"


def test_related_public_diagnostic_labels_are_available_for_future_projection() -> None:
    expected = {
        "AI_PROVIDER_CHAIN_EXHAUSTED": "Nenhum provedor de IA elegível permaneceu disponível",
        "CONTENT_EVIDENCE_INSUFFICIENT": "Evidência de conteúdo insuficiente",
        "MAIN_CONTENT_UNAVAILABLE": "Conteúdo principal indisponível",
        "SEMANTIC_EVIDENCE_UNAVAILABLE": "Evidência semântica indisponível",
        "SOURCE_QUALITY_BLOCKED": "Aquisição técnica bloqueada pela qualidade da origem",
    }
    for raw, label in expected.items():
        assert public_label(raw) == label
