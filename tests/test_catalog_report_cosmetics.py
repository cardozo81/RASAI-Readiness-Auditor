from rasai.catalog_report_presentation import _navigation, _state_text
from rasai.catalog_report_style import _CSS


def test_catalog_menu_hides_technical_catalog_prefix() -> None:
    html = _navigation("cat-03.html")

    assert "CAT-03 · Conteúdo, semântica e dados estruturados" not in html
    assert ">Conteúdo, semântica e dados estruturados</a>" in html
    assert ">Índice de Prontidão Search &amp; IA</a>" in html


def test_state_text_changes_only_semantic_color_contract() -> None:
    approved = str(_state_text("PASS"))
    attention = str(_state_text("WARNING"))
    rejected = str(_state_text("FAIL"))

    assert "state-text good" in approved
    assert "state-text warn" in attention
    assert "state-text bad" in rejected
    assert "badge" not in approved + attention + rejected


def test_audit_identification_typography_is_secondary() -> None:
    assert ".brand strong{display:block;color:#fff;margin-top:4px;font-size:.76rem;font-weight:600" in _CSS
    assert ".hero .eyebrow{font-size:.66rem" in _CSS
    assert "font-weight:600" in _CSS


def test_dark_gray_is_reserved_for_explicit_neutral_states() -> None:
    from rasai.catalog_report_presentation import _display_value

    assert "--secondary-ink:#475467" in _CSS
    assert "td{color:var(--ink)}" in _CSS
    assert ".modal-body{padding:18px 20px;overflow:auto;max-height:calc(88vh - 120px);color:var(--ink)}" in _CSS
    assert ".kv dd{overflow-wrap:anywhere;color:var(--ink)}" in _CSS
    assert ".state-text.neutral{color:var(--secondary-ink)}" in _CSS
    assert ".metric strong>.state-text.neutral{font-weight:400}" in _CSS

    for value in (
        "Automático",
        "Não aplicável",
        "Não aplicável - nenhum dado estruturado foi observado",
        "Não determinado",
        "Não determinável",
        "AUTO não determinável",
        "Não solicitado",
        "Não elegível",
        "Não elegível sem IA competitiva",
        "Comparação de conteúdo desabilitada",
        "Não habilitado",
        "Não definida",
        "Sem dados",
        "Sem amostra",
        "Não observado",
        "Não comparável",
        "Versão não determinada",
        "Indeterminado - snapshot ausente/inválido",
    ):
        rendered = str(_display_value(value))
        assert "state-text neutral" in rendered
        assert "badge" not in rendered


def test_operational_states_use_consistent_font_semantics() -> None:
    from rasai.catalog_report_presentation import _display_value

    for value in ("Concluído", "Etapa concluída", "Execução completa", "Aprovado", "Interpretado", "Executado com dados", "Pronto", "Íntegro - SHA-256 confere"):
        assert "state-text good" in str(_display_value(value))
    for value in ("Não configurado", "Capacidade não configurada", "Não consolidado", "Sem evidência", "Sem resultado", "Etapa parcial", "Etapa pendente", "Parcial - reprocessamento disponível", "Executado parcialmente", "Executado sem dados"):
        assert "state-text warn" in str(_display_value(value))
    for value in ("Falha", "Bloqueado", "Observação de SERP indisponível", "Indisponível", "Dados indisponíveis", "Sem dados disponíveis", "Executado com erro e sem dados", "INCONSISTENTE - SHA-256 divergente"):
        assert "state-text bad" in str(_display_value(value))


def test_primary_result_value_is_bold_without_badge() -> None:
    from rasai.catalog_report_presentation import _result_value

    rendered = str(_result_value("92 / 100", "good"))
    assert "result-value good" in rendered
    assert rendered.startswith("<strong")
    assert "badge" not in rendered


def test_catalog_result_ranges_use_existing_canonical_bands() -> None:
    from rasai.catalog_report_page import _catalog_metric_tone

    assert _catalog_metric_tone("CAT-01", "Acesso e descoberta", "75") == "good"
    assert _catalog_metric_tone("CAT-01", "Acesso e descoberta", "60") == "warn"
    assert _catalog_metric_tone("CAT-01", "Acesso e descoberta", "40") == "low"
    assert _catalog_metric_tone("CAT-01", "Acesso e descoberta", "39") == "bad"
    assert _catalog_metric_tone("CAT-03", "Estrutura semântica", "75") == "good"

    assert _catalog_metric_tone("CAT-02", "Lighthouse · Acessibilidade", "90 / 100") == "good"
    assert _catalog_metric_tone("CAT-02", "Lighthouse · Acessibilidade", "89 / 100") == "warn"
    assert _catalog_metric_tone("CAT-04", "LCP de campo (p75)", "2 500 ms") == "good"
    assert _catalog_metric_tone("CAT-04", "LCP de campo (p75)", "4 001 ms") == "bad"
    assert _catalog_metric_tone("CAT-04", "Core Web Vitals", "Pass") == "good"
    assert _catalog_metric_tone("CAT-04", "Core Web Vitals", "Aprovado") == "good"
    assert _catalog_metric_tone("CAT-04", "Core Web Vitals", "Needs Improvement") == "warn"
    assert _catalog_metric_tone("CAT-04", "Core Web Vitals", "Precisa melhorar") == "warn"
    assert _catalog_metric_tone("CAT-04", "Core Web Vitals", "Ruim") == "bad"

    assert _catalog_metric_tone("CAT-05", "Faixa de posições observada", "1 a 10") == "neutral"

    assert _catalog_metric_tone("CAT-06", "Apdex", "0.94") == "good"
    assert _catalog_metric_tone("CAT-06", "Apdex", "0.70") == "warn"
    assert _catalog_metric_tone("CAT-06", "Apdex", "0.50") == "bad"

    assert _catalog_metric_tone("CAT-10", "Achados críticos", "1") == "bad"
    assert _catalog_metric_tone("CAT-10", "Achados críticos", "0") == "neutral"
    assert _catalog_metric_tone("CAT-10", "Achados médios", "1") == "warn"


def test_only_final_catalog_results_receive_bold_emphasis() -> None:
    from rasai.catalog_report_page import _catalog_metric_is_primary

    assert _catalog_metric_is_primary("CAT-01", "Acesso e descoberta") is True
    assert _catalog_metric_is_primary("CAT-02", "Lighthouse · Acessibilidade") is True
    assert _catalog_metric_is_primary("CAT-03", "Estrutura semântica") is True
    assert _catalog_metric_is_primary("CAT-04", "Lighthouse Performance") is True
    assert _catalog_metric_is_primary("CAT-04", "Lighthouse SEO") is False
    assert _catalog_metric_is_primary("CAT-04", "LCP de campo (p75)") is True
    assert _catalog_metric_is_primary("CAT-05", "Faixa de posições observada") is True
    assert _catalog_metric_is_primary("CAT-05", "Resultados coletados") is False
    assert _catalog_metric_is_primary("CAT-06", "Apdex") is True
    assert _catalog_metric_is_primary("CAT-06", "Amostras válidas") is False
    assert _catalog_metric_is_primary("CAT-07", "Apdex") is True
    assert _catalog_metric_is_primary("CAT-10", "Achados críticos") is True
    assert _catalog_metric_is_primary("CAT-10", "Páginas analisadas") is False


def test_auto_configuration_is_always_rendered_as_automatic_only() -> None:
    from rasai.configuration_value_labels import (
        configuration_value_choice,
        configuration_value_info,
        configuration_value_report,
    )

    for renderer in (configuration_value_choice, configuration_value_info, configuration_value_report):
        assert renderer("RASAI_YMYL_CATEGORY", "auto") == "Automático"
        assert renderer("RASAI_WEB_PERFORMANCE_FIELD_SOURCE", "auto") == "Automático"
        assert "(auto)" not in renderer("RASAI_YMYL_CATEGORY", "auto")


def test_cat05_auto_ymyl_projection_is_human_only() -> None:
    from rasai.catalog_report_search_trust import _competitive_validation_rows

    rows = _competitive_validation_rows(
        {"ymyl_mode": "auto", "competitive": False, "compare_content": False, "ai_competitive": False},
        {},
        (),
        (),
        None,
        None,
        (),
        None,
        {},
    )
    ymyl = next(row for row in rows if row[0] == "YMYL")
    assert ymyl[1] == "Automático"
    assert "(auto)" not in str(ymyl[1])


def test_priority_and_severity_use_font_only_semantics() -> None:
    from rasai.catalog_report_presentation import _priority_text, _severity_text

    assert "result-value bad" in str(_severity_text("HIGH"))
    assert "result-value warn" in str(_severity_text("MEDIUM"))
    assert "result-value neutral" in str(_severity_text("LOW"))
    assert "result-value bad" in str(_priority_text("P1"))
    assert "result-value warn" in str(_priority_text("P2"))
    assert "result-value bad" in str(_priority_text("Alta"))
    assert "result-value bad" in str(_severity_text("Alta"))

def test_score_low_band_is_font_only_orange() -> None:
    from rasai.catalog_report_presentation import _result_value, _score_result_tone

    assert _score_result_tone("59") == "low"
    rendered = str(_result_value("59.0", "low"))
    assert "result-value low" in rendered
    assert rendered.startswith("<strong")
    assert "badge" not in rendered
    assert "--orange:#9a5b13" in _CSS


def test_cat05_automatic_model_does_not_expose_technical_auto_token() -> None:
    from rasai.catalog_report_search_trust import _contract_rows

    rows = dict(_contract_rows({"ai_provider": "auto", "ai_model": None}))
    assert rows["IA principal solicitada"] == "Automático"
    assert rows["Modelo solicitado"] == "Automático"


def test_cat10_modal_details_keep_neutral_states_gray() -> None:
    from rasai.catalog_report_analysis import _security_detail_html

    rendered = _security_detail_html("NOT_APPLICABLE")
    assert "state-text neutral" in rendered
    assert "Não aplicável" in rendered


def test_zero_ai_cost_and_tokens_use_light_gray_font_only() -> None:
    from decimal import Decimal
    from rasai.catalog_report_integrations import (
        _money_display,
        _money_range_display,
        _signed_money_display,
        _token_pair_display,
        _token_value_display,
    )

    for rendered in (
        str(_money_display(Decimal("0"), "USD")),
        str(_signed_money_display(Decimal("0"), "USD")),
        str(_money_range_display(0, 0, "USD")),
        str(_token_pair_display(120, 42, cost=0)),
        str(_token_value_display(120, cost=0)),
    ):
        assert "no-cost-value" in rendered
    assert "USD 0.00000000" in str(_money_display(0, "USD"))
    mixed_range = str(_money_range_display(0, 0.5, "USD"))
    assert "no-cost-value" in mixed_range
    assert "USD 0.00000000" in mixed_range
    assert "USD 0.50000000" in mixed_range
    assert "120 / 42" in str(_token_pair_display(120, 42, cost=0))
    assert "--light-muted:#6c7789" in _CSS
    assert ".no-cost-value{color:var(--light-muted);font-weight:400}" in _CSS

    assert "no-cost-value" not in str(_money_display(Decimal("0.01"), "USD"))
    assert "no-cost-value" not in str(_token_pair_display(120, 42, cost=Decimal("0.01")))
    unpriced = str(_money_display(None, "USD"))
    assert "no-cost-value" not in unpriced
    assert "state-text neutral" in unpriced
    assert "Não precificado" in unpriced
    assert "USD 0.00000000" not in unpriced
    assert "no-cost-value" not in str(_token_pair_display(120, 42, cost=None))
    assert "no-cost-value" not in str(_token_value_display(120, cost=None))


def test_execution_origin_distinguishes_processing_and_reprocessing() -> None:
    from rasai.catalog_report_integrations import _execution_origin

    runs = (
        {
            "reprocess_id": "RPR-001",
            "started_at": "2026-09-21T12:00:00+00:00",
            "completed_at": "2026-09-21T12:10:00+00:00",
        },
    )
    assert _execution_origin("2026-09-21T11:59:59+00:00", runs) == ("Processamento", None)
    assert _execution_origin("2026-09-21T12:05:00+00:00", runs) == ("Reprocessamento", "RPR-001")
    assert _execution_origin(None, runs) == ("Não determinado", None)


def test_audit_lifecycle_statuses_are_pt_br() -> None:
    from rasai.catalog_report_presentation import _status_label

    expected = {
        "CREATED": "Criado",
        "INITIALIZING": "Inicializando",
        "DISCOVERING": "Descobrindo URLs",
        "ACQUIRING": "Coletando páginas",
        "ANALYZING": "Analisando",
        "COMPARING": "Comparando",
        "SCORING": "Calculando pontuação",
        "RECOMMENDING": "Gerando recomendações",
        "REPORTING": "Gerando relatórios",
        "COMPLETED": "Concluído",
        "FAILED": "Falhou",
        "CANCELLED": "Cancelado",
        "DEGRADED": "Execução com limitações",
        "NO_AI": "Execução sem IA",
        "PARTIAL_RETRYABLE": "Parcial - reprocessamento disponível",
        "PARTIAL_BLOCKED": "Parcial - há bloqueios",
        "EXPIRED_FOR_COMPLETION": "Expirado para conclusão",
        "NOT_CONSOLIDATED": "Não consolidado",
        "NO_SAFE_SUGGESTIONS": "Nenhuma sugestão segura",
        "NO_ELIGIBLE_FINDINGS": "Nenhum finding elegível",
    }
    for raw, label in expected.items():
        assert _status_label(raw) == label


def test_audit_base_never_exposes_raw_analyzing_status() -> None:
    from types import SimpleNamespace
    from rasai.catalog_report_adherence import _audit_hero
    from rasai.catalog_report_presentation import _status_label

    data = SimpleNamespace(
        audit_id="AUD-TEST",
        targets=("https://example.test/",),
        audit={"project_name": "Projeto", "status": "ANALYZING", "completion_status": None},
        fulfillment={},
        selected={"CAT-01"},
    )
    rendered = _audit_hero(data, "Visão geral por catálogos", "Resumo")
    assert "Auditoria-base" in rendered
    assert "Analisando" in rendered
    assert "ANALYZING" not in rendered
    assert _status_label("analyzing") == "Analisando"


def test_public_domain_enums_have_pt_br_labels() -> None:
    from rasai.catalog_report_public_labels import public_label

    expected = {
        "DOMAIN": "Domínio",
        "URL_SET": "Conjunto de URLs",
        "INTERNAL_LINK": "Link interno",
        "REDIRECT": "Redirecionamento",
        "HTTP_RESPONSE": "Resposta HTTP",
        "VISUAL_SNAPSHOT": "Captura visual",
        "STRUCTURED_DATA": "Dados estruturados",
        "MOBILE": "Dispositivo móvel",
        "BOTH": "Ambos",
        "STATIC_OR_SSR": "Estática ou renderizada no servidor (SSR)",
        "OBSERVED_API": "API observada",
        "OBSERVED_SYNTHETIC": "Observação sintética",
        "AI_INFERRED": "Inferido por IA",
        "SEARCH_CONSOLE": "Google Search Console",
        "BING_WEBMASTER": "Bing Webmaster Tools",
        "PAGE_CONTENT": "Conteúdo da página",
        "AI_HYPOTHESIS": "Hipótese por IA",
        "SERP_RELATED": "Relacionada à SERP",
        "COMPETITOR_DISCOVERY": "Descoberta de concorrentes",
        "GOOGLE_SEARCH_CONSOLE": "Google Search Console",
        "MICROSOFT_CLARITY": "Microsoft Clarity",
        "COMMON_CRAWL": "Common Crawl",
    }
    for raw, label in expected.items():
        assert public_label(raw) == label


def test_cross_domain_operational_statuses_have_pt_br_labels() -> None:
    from rasai.catalog_report_presentation import _status_label

    expected = {
        "NOT_CONSOLIDATED": "Não consolidado",
        "TECHNICAL_ERROR": "Erro técnico",
        "BUSINESS_ERROR": "Erro de regra de negócio",
        "CONTRACT_ERROR": "Erro de resposta contratual",
        "QUARANTINED_FOR_AUDIT": "Indisponível nesta auditoria",
        "ACTIVE": "Ativo",
        "STANDBY": "Em espera",
        "OBSERVED": "Observado",
        "UNAVAILABLE": "Sem dados disponíveis",
        "REQUESTED_NOT_EXECUTED": "Solicitado, não executado",
        "WAITING_FOR_DATA": "Aguardando dados",
    }
    for raw, label in expected.items():
        assert _status_label(raw) == label


def test_improvement_domains_have_pt_br_public_labels() -> None:
    from rasai.catalog_report_presentation import _domain_label
    from rasai.improvement_intelligence import DEFAULT_DOMAINS

    rendered = {domain: _domain_label(domain) for domain in DEFAULT_DOMAINS}
    assert rendered == {
        "TECHNICAL_HTML": "HTML e estrutura técnica",
        "SEMANTICS_STRUCTURE": "Estrutura semântica",
        "CONTENT": "Conteúdo",
        "SEARCH_RANKING": "Busca e posicionamento",
        "FILES_DISCOVERY": "Arquivos de descoberta",
        "PERFORMANCE": "Desempenho",
        "ACCESSIBILITY": "Acessibilidade",
        "BEST_PRACTICES": "Boas práticas",
        "SECURITY": "Segurança passiva",
        "AI_ACCESS": "Acesso por agentes de IA",
    }
    for domain, label in rendered.items():
        assert label != domain.replace("_", " ").title()


def test_architecture_labels_are_domain_specific() -> None:
    from rasai.catalog_report_presentation import _architecture_label, _temporal_mode_label

    assert _architecture_label("STATIC_OR_SSR") == "Estática ou renderizada no servidor (SSR)"
    assert _architecture_label("HYDRATED") == "Renderizada no servidor com hidratação"
    assert _architecture_label("CSR_SPA") == "SPA renderizada no cliente (CSR)"
    assert _architecture_label("MIXED") == "Mista"
    assert str(_temporal_mode_label("MIXED")) == "Origem temporal mista"


def test_component_domains_are_humanized() -> None:
    from rasai.catalog_report_catalog_state import _friendly_component

    assert _friendly_component("SEARCH_INTELLIGENCE") == "Inteligência de busca / SERP"
    assert _friendly_component("GOOGLE_SEARCH_CONSOLE") == "Google Search Console"
    assert _friendly_component("AI_VISIBILITY") == "Visibilidade em respostas de IA"
    assert _friendly_component("PASSIVE_SECURITY") == "Segurança passiva"


def test_raw_audit_lifecycle_states_keep_pt_br_and_visual_semantics() -> None:
    from rasai.catalog_report_presentation import _display_value

    assert "state-text warn" in str(_display_value("ANALYZING"))
    assert "Analisando" in str(_display_value("ANALYZING"))
    assert "state-text warn" in str(_display_value("REPORTING"))
    assert "Gerando relatórios" in str(_display_value("REPORTING"))
    assert "state-text good" in str(_display_value("FULL"))
    assert "Execução completa" in str(_display_value("FULL"))
    assert "state-text neutral" in str(_display_value("NO_AI"))
    assert "Execução sem IA" in str(_display_value("NO_AI"))
    assert "state-text bad" in str(_display_value("FAILED"))
    assert "Falhou" in str(_display_value("FAILED"))


def test_public_component_labels_prefer_pt_br() -> None:
    from rasai.catalog_report_catalog_state import _friendly_component

    assert _friendly_component("WEB_PERFORMANCE") == "Desempenho web"
    assert _friendly_component("SEARCH_INTELLIGENCE") == "Inteligência de busca / SERP"
    assert _friendly_component("PASSIVE_SECURITY") == "Segurança passiva"
