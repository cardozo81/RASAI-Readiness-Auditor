"""Focused Portuguese report contract without external acquisition."""
from rasai.report_ptbr_copy import public_geo_action
from rasai.experience_architecture_guidance import resolve_experience_architecture_guidance
from rasai.architecture_audit_facts import _architecture_runtime_state_label


def test_only_known_legacy_geo_copy_is_rewritten():
    source = "Revisar cobertura da intencao, clareza da oferta e evidencias no CAT-03 antes de propor remediacao."
    value = public_geo_action(source)
    assert value == "Revisar a cobertura da intenção, a clareza da oferta e as evidências no CAT-03 antes de propor remediação."
    assert public_geo_action("https://example.org/intencao") == "https://example.org/intencao"
    # Texto histórico v8: somente frases exatas do produto são reescritas.
    assert public_geo_action("Alvo unico ou atribuicao por consulta indisponivel.") == "Alvo único ou atribuição por consulta indisponível."
    assert public_geo_action("Observacao incompleta.") == "Observação incompleta."
    assert public_geo_action("Observacao pontual; nao prova inclusao em resposta gerativa nem causa de ausencia.") == "Observação pontual; não comprova inclusão em resposta generativa nem a causa da ausência."
    assert public_geo_action("Coincidencia textual da consulta nao comprova equivalencia de mercado, intencao, idioma, dispositivo ou motor; janela temporal de 24h e so elegibilidade observacional.").startswith("A coincidência textual da consulta não comprova equivalência")
    assert "citação generativa" in public_geo_action("A busca externa nao equivale a resposta/citacao generativa; nao ha atribuicao de fontes a consultas individuais em multi-query. Sobreposicao nao demonstra causalidade ou representatividade.")
    # Dados externos, URLs e trechos não conhecidos permanecem literais.
    assert public_geo_action("Texto externo sem acentos e URL /acao") == "Texto externo sem acentos e URL /acao"
    assert public_geo_action(value) == value


def test_cat07_guided_advisory_is_ptbr_without_mutating_executable_settings():
    config = {"kpm":"USER_ACTION_DURATION","satisfied_threshold_seconds":4.0,"frustrated_threshold_seconds":12.0}
    saved = dict(config)
    advice = resolve_experience_architecture_guidance(
        config, profile_mode="DYNATRACE_GUIDED",
        observed_architecture="CSR_SPA",
        provenance={"page_id":"P1","snapshot_id":"S1","device":"MOBILE"},
    )
    notes = " ".join(item["text"] for item in advice["next_actions"])
    assert "parâmetros guiados" in notes and "configuração atual" in notes
    assert "não alterar amostras" in notes
    assert config == saved


def test_capture_state_label_humanizes_enum_without_inference():
    assert _architecture_runtime_state_label("CAPTURED") == "Capturado nesta auditoria"
    assert _architecture_runtime_state_label("OBSERVED_MAIN_DOCUMENT_RESPONSE") == "Resposta principal observada pelo navegador"
    assert _architecture_runtime_state_label("NOT_COLLECTED").startswith("Não coletado")
    assert _architecture_runtime_state_label("FUTURE_NEW_ENUM").startswith("N/D")
