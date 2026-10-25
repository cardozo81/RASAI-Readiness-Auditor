from __future__ import annotations

from rasai.catalog_report_adherence import _human_limitation
from rasai.catalog_report_public_labels import public_label


def test_persisted_audit_scope_limitations_are_humanized() -> None:
    assert _human_limitation(
        "MAX_PAGES_REACHED:discovered=19;audited=1"
    ) == (
        "Limite de páginas selecionadas para análise atingido: "
        "1 URL auditada entre 19 URLs descobertas no recorte coletado. "
        "A contagem descoberta pode estar limitada por orçamento de amostragem."
    )
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
    assert _human_limitation(raw) == "Limitação técnica registrada (Condição técnica não catalogada)"


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


def test_three_independent_discovery_budgets_are_not_confused_with_site_size() -> None:
    sitemap = _human_limitation(
        "SITEMAP_RESOURCE_BUDGET_EXHAUSTED:acquired=12;queued=3328;policy=12"
    )
    assert "12 recurso(s) adquirido(s) de 3328 endereço(s) na fila" in sitemap
    assert "não foram adquiridos" in sitemap
    assert "não comprova ausência" in sitemap

    candidates = _human_limitation(
        "DISCOVERY_CANDIDATE_BUDGET_EXHAUSTED:retained=2000;policy=2000"
    )
    assert "2000 URL(s) candidata(s) retida(s)" in candidates
    assert "não exaustivo" in candidates
    assert "total real" in candidates

    scope = _human_limitation(
        "MAX_PAGES_REACHED:discovered=2000;audited=1"
    )
    assert "1 URL auditada entre 2000 URLs descobertas" in scope
    assert "pode estar limitada" in scope
    assert "não foram adquiridos" not in scope


def test_unrecognized_budget_text_keeps_raw_provenance_instead_of_claiming_completeness() -> None:
    value = "SITEMAP_RESOURCE_BUDGET_EXHAUSTED:policy=12"
    assert "SITEMAP_RESOURCE_BUDGET_EXHAUSTED" in _human_limitation(value)
