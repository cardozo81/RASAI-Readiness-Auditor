from __future__ import annotations

from types import SimpleNamespace

from rasai.catalog_report_public_labels import public_contract_label, public_label
from rasai.catalog_report_presentation import (
    _kv,
    _rich_text,
    _score_table,
    _status_label,
    _table,
    _temporal_mode_label,
    _translated_text,
)
from rasai.score_geo_004_reporting import _score_row
from rasai.semantic import semantic_output_language_directive


def test_internal_contract_values_have_human_labels_without_internal_tooltips() -> None:
    expected = {
        "DIRECT_PUBLIC_INDEX_API": "API pública de índice",
        "DIRECT_OFFICIAL_API": "API oficial da fonte",
        "DETERMINISTIC-CORRELATIONAL-001": "Correlação determinística de evidências",
        "LIVE_RECOLLECTION": "Coleta ao vivo desta auditoria",
        "REUSED_EVIDENCE": "Evidência reutilizada",
        "REPLAY_SAFE": "Reutilizável sem nova coleta",
        "CONTENT_COMPARISON_DISABLED": "Comparação de conteúdo desabilitada",
        "CLASSIFICATION_ONLY": "Somente classificação",
        "UNKNOWN_ACTION": "Ação não classificada",
        "RATE_LIMITED": "Limite de requisições atingido",
        "ORGANIC_CANDIDATE": "Candidato orgânico",
        "PUBLIC_AUTHORITY": "Autoridade pública",
        "ADD_CONTEXT": "Adicionar contexto",
        "EDIT_CONTENT": "Editar conteúdo",
        "FINANCIAL_SECURITY": "Segurança financeira",
        "AI_INFERENCE": "Inferência de IA",
        "NOT_CONSOLIDATED": "Não consolidado",
    }
    for raw, label in expected.items():
        assert public_label(raw) == label

    html = _table(
        ("Método", "Estado", "Ação"),
        [("DIRECT_OFFICIAL_API", "RATE_LIMITED", "ADD_CONTEXT")],
    )
    assert "API oficial da fonte" in html
    assert "Limite de requisições atingido" in html
    assert "Adicionar contexto" in html
    assert "translation-mark" not in html
    assert "DIRECT_OFFICIAL_API" not in html


def test_compound_sari_contracts_are_humanized() -> None:
    expected = {
        "DIMENSION_NOT_APPLICABLE:STRUCTURED_DATA": "Dimensão Dados estruturados não aplicável",
        "DIMENSION_MEASUREMENT_LIMITED:CONTENT_VALUE": "Medição limitada na dimensão Valor do conteúdo",
        "CRITICAL_GATE:DISCOVERY:WARNING": "Gate crítico de descoberta: atenção",
        "CRITICAL_GATE:INDEXABILITY:WARNING": "Gate crítico de indexabilidade: atenção",
        "CRITICAL_GATE:EXTRACTION:PASS": "Gate crítico de extração: aprovado",
        "READINESS_STATUS:ATTENTION": "Estado de prontidão: atenção",
        "OVERALL_AGGREGATION:HIERARCHICAL_WEIGHTED_READINESS_V1": "Agregação geral: prontidão hierárquica ponderada - versão 1",
        "EMPIRICAL_VALIDATION:NOT_SCORE_INPUT": "Validação empírica: não participa da pontuação",
    }
    for raw, label in expected.items():
        assert public_contract_label(raw) == label


def test_external_translation_keeps_original_only_for_external_source_text() -> None:
    rendered = str(
        _translated_text(
            "Contraste insuficiente entre texto e plano de fundo",
            "Low-contrast text is difficult or impossible for many users to read.",
        )
    )
    assert "Contraste insuficiente" in rendered
    assert "translation-mark" in rendered
    assert "Low-contrast text" in rendered


def test_competitive_reason_and_classification_are_humanized() -> None:
    table = _table(
        ("Classificação", "Motivo"),
        [("ORGANIC_CANDIDATE", "external organic result; business equivalence is not inferred")],
    )
    assert "Candidato orgânico" in table
    assert "Resultado orgânico externo; equivalência comercial não é inferida" in table
    assert "ORGANIC_CANDIDATE" not in table


def test_status_and_temporal_labels_are_human_first() -> None:
    assert _status_label("CONTENT_COMPARISON_DISABLED") == "Comparação de conteúdo desabilitada"
    assert _status_label("SERP_OBSERVATION_UNAVAILABLE") == "Observação de SERP indisponível"
    assert _status_label("NOT_CONSOLIDATED") == "Não consolidado"
    rendered = str(_temporal_mode_label("LIVE_RECOLLECTION"))
    assert rendered == "Coleta ao vivo desta auditoria"
    assert "LIVE_RECOLLECTION" not in rendered


def test_rich_text_renders_safe_external_links_in_new_tab() -> None:
    rendered = str(
        _rich_text(
            "Veja [documentação oficial](https://developers.google.com/search/docs) e `sameAs`."
        )
    )
    assert "target='_blank'" in rendered
    assert "rel='noopener noreferrer'" in rendered
    assert "documentação oficial ↗" in rendered
    assert "<code>sameAs</code>" in rendered
    assert "[documentação oficial]" not in rendered


def test_rich_text_escapes_arbitrary_html() -> None:
    rendered = str(_rich_text("<script>alert(1)</script> https://example.test/a"))
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "href='https://example.test/a'" in rendered


def test_report_placeholder_uses_hyphen_not_em_dash() -> None:
    rendered = _table(("Valor",), [("—",)])
    assert "<td>-</td>" in rendered
    assert "—" not in rendered


def test_catalog_score_table_humanizes_consolidation() -> None:
    data = SimpleNamespace(scores=[{
        "dimension": "CONTENT_VALUE",
        "device": "MOBILE",
        "value": 50.0,
        "coverage": 0.4,
        "confidence": "LOW",
        "consolidation_status": "NOT_CONSOLIDATED",
        "scoring_version": "SCORE-GEO-004",
    }])
    html = _score_table(data)
    assert "Valor do conteúdo" in html
    assert "Dispositivo móvel" in html
    assert "Baixa" in html
    assert "Não consolidado" in html
    assert "Not Consolidated" not in html


def test_canonical_scoring_row_is_humanized() -> None:
    html = _score_row({
        "device": "MOBILE",
        "value": 63.0,
        "coverage": 0.91,
        "confidence": "LOW",
        "consolidation_status": "NOT_CONSOLIDATED",
        "scoring_version": "SCORE-GEO-004",
        "limitations": "[]",
    })
    assert "Dispositivo móvel" in html
    assert "Baixa" in html
    assert "Não consolidado" in html


def test_semantic_free_text_contract_uses_audit_language_and_hyphen() -> None:
    directive = semantic_output_language_directive(
        SimpleNamespace(primary_language="pt-BR")
    )
    assert "pt-BR" in directive
    assert "reasoning_summary" in directive
    assert "observed_value.summary" in directive
    assert "ASCII hyphen '-'" in directive
    assert "em dash" in directive
