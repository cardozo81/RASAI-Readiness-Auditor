from __future__ import annotations

from types import SimpleNamespace

from rasai.catalog_report_public_labels import public_contract_label, public_label, public_text
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
        "NETWORK_ERROR": "Erro de rede",
        "CREATED": "Criado",
        "INITIALIZING": "Inicializando",
        "DISCOVERING": "Descobrindo URLs",
        "ACQUIRING": "Coletando páginas",
        "ANALYZING": "Analisando",
        "COMPARING": "Comparando",
        "SCORING": "Calculando pontuação",
        "RECOMMENDING": "Gerando recomendações",
        "REPORTING": "Gerando relatórios",
        "CANCELLED": "Cancelado",
        "DOMAIN": "Domínio",
        "URL_SET": "Conjunto de URLs",
        "INTERNAL_LINK": "Link interno",
        "REDIRECT": "Redirecionamento",
        "HTTP_RESPONSE": "Resposta HTTP",
        "STRUCTURED_DATA": "Dados estruturados",
        "OBSERVED_API": "API observada",
        "SEARCH_CONSOLE": "Google Search Console",
        "PAGE_CONTENT": "Conteúdo da página",
        "AI_INFERRED": "Inferido por IA",
        "OBSERVED": "Observado",
        "PARTIAL_RETRYABLE": "Parcial - reprocessamento disponível",
        "PARTIAL_BLOCKED": "Parcial - há bloqueios",
        "CUSTOMER": "Site auditado",
        "COMPETITOR_CANDIDATE": "Candidato concorrente",
        "CONTENT_REMEDIATION": "Remediação de conteúdo",
        "ORGANIC_CANDIDATE": "Candidato orgânico",
        "PUBLIC_AUTHORITY": "Autoridade pública",
        "KNOWLEDGE_REFERENCE": "Referência de conhecimento",
        "SOCIAL_PLATFORM": "Plataforma social",
        "VIDEO_PLATFORM": "Plataforma de vídeo",
        "MARKETPLACE": "Marketplace",
        "NON_ORGANIC": "Resultado não orgânico",
        "NOT_ELIGIBLE": "Não elegível",
        "QUERY_INTENT": "Intenção da consulta",
        "TOPIC_COVERAGE": "Cobertura temática",
        "ENTITY_COVERAGE": "Cobertura de entidades",
        "INFORMATION_ARCHITECTURE": "Arquitetura da informação",
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
        "CRITICAL_GATE:DISCOVERY:BLOCKED": "Gate crítico de descoberta: bloqueado",
        "CRITICAL_GATE:INDEXABILITY:UNKNOWN": "Gate crítico de indexabilidade: não determinado",
        "CRITICAL_GATE:EXTRACTION:PASS": "Gate crítico de extração: aprovado",
        "READINESS_STATUS:ATTENTION": "Estado de prontidão: atenção",
        "READINESS_STATUS:BLOCKED": "Estado de prontidão: bloqueado",
        "OVERALL_MEASUREMENT_BELOW_MINIMUM_GATE": "Medição geral abaixo do mínimo exigido",
        "OVERALL_MEASUREMENT_BELOW_CONSOLIDATION_GATE": "Medição geral abaixo do mínimo para consolidação",
        "OVERALL_AGGREGATION:HIERARCHICAL_WEIGHTED_READINESS_V1": "Agregação Hierárquica Ponderada de Prontidão - versão pública 001",
        "EMPIRICAL_VALIDATION:NOT_SCORE_INPUT": "Validação empírica: não participa da pontuação",
    }
    for raw, label in expected.items():
        assert public_contract_label(raw) == label


def test_embedded_diagnostic_tokens_are_localized_without_touching_free_text() -> None:
    assert public_text("Sitemap/feed em estado NETWORK_ERROR") == "Sitemap/feed em estado Erro de rede"
    assert public_text("Coleta OBSERVED para COMPETITOR_CANDIDATE") == "Coleta Observado para Candidato concorrente"
    assert public_text("Código BR-GEO-060 preservado") == "Código BR-GEO-060 preservado"


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
    assert _status_label("PARTIAL_RETRYABLE") == "Parcial - reprocessamento disponível"
    assert _status_label("OBSERVED") == "Observado"
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


def test_common_report_labels_cover_audit_lifecycle_and_public_domains() -> None:
    from rasai.report_presentation import public_label as common_public_label

    expected = {
        "ANALYZING": "Analisando",
        "REPORTING": "Gerando relatórios",
        "DOMAIN": "Domínio",
        "URL_SET": "Conjunto de URLs",
        "INTERNAL_LINK": "Link interno",
        "REDIRECT": "Redirecionamento",
        "OBSERVED_API": "API observada",
        "SEARCH_CONSOLE": "Google Search Console",
        "PAGE_CONTENT": "Conteúdo da página",
        "AI_INFERRED": "Inferido por IA",
        "APDEX_NAVIGATION": "Apdex de navegação",
        "GEO_SEARCH_AI": "GEO / Busca e IA",
        "BEST_PRACTICES": "Boas práticas",
        "TECHNICAL_QUALITY": "Qualidade técnica",
        "SEARCH_ANALYTICS": "Desempenho de pesquisa",
        "SEARCH_APPEARANCE": "Aparência na pesquisa",
        "URL_INSPECTION": "Inspeção de URL",
        "PROPERTIES": "Propriedades",
    }
    for raw, label in expected.items():
        assert common_public_label(raw) == label


def test_rich_text_humanizes_embedded_public_status_and_domain_tokens() -> None:
    rendered = str(_rich_text("Auditoria ANALYZING · origem SEARCH_CONSOLE · escopo URL_SET"))
    assert "Auditoria Analisando" in rendered
    assert "Google Search Console" in rendered
    assert "Conjunto de URLs" in rendered
    assert "ANALYZING" not in rendered
    assert "SEARCH_CONSOLE" not in rendered
    assert "URL_SET" not in rendered


def test_search_and_ai_operational_enums_have_public_labels() -> None:
    from rasai.m18_ai import AttemptStatus
    from rasai.search_intelligence.models import (
        DomainMatchStatus,
        QueryOrigin,
        SerpDataMode,
        SerpObservationStatus,
    )

    values = (
        *(item.value for item in AttemptStatus),
        *(item.value for item in DomainMatchStatus),
        *(item.value for item in QueryOrigin),
        *(item.value for item in SerpDataMode),
        *(item.value for item in SerpObservationStatus),
    )
    for raw in values:
        label = public_label(raw)
        assert label is not None
        assert label != raw.replace("_", " ").title()


def test_core_audit_status_enums_have_pt_br_public_labels() -> None:
    from rasai.domain import AuditMode, AuditStatus, CompletionStatus, RuleResult

    values = (
        *(item.value for item in AuditStatus),
        *(item.value for item in CompletionStatus),
        *(item.value for item in AuditMode),
        *(item.value for item in RuleResult),
    )
    for raw in values:
        label = public_label(raw)
        assert label is not None
        assert label != raw.replace("_", " ").title()


def test_core_public_domains_have_human_labels() -> None:
    from rasai.domain import (
        ArchitectureClassification,
        DeviceContext,
        DiscoverySource,
        EvidenceType,
        FindingDevice,
        Severity,
        TargetType,
    )

    values = (
        *(item.value for item in TargetType),
        *(item.value for item in DiscoverySource),
        *(item.value for item in EvidenceType),
        *(item.value for item in DeviceContext),
        *(item.value for item in FindingDevice),
        *(item.value for item in ArchitectureClassification),
        *(item.value for item in Severity),
    )
    for raw in values:
        label = public_label(raw)
        assert label is not None

    assert public_label("DOMAIN") == "Domínio"
    assert public_label("URL_SET") == "Conjunto de URLs"
    assert public_label("INTERNAL_LINK") == "Link interno"
    assert public_label("HTTP_RESPONSE") == "Resposta HTTP"
    assert public_label("VISUAL_SNAPSHOT") == "Captura visual"
    assert public_label("STRUCTURED_DATA") == "Dados estruturados"
    assert public_label("MOBILE") == "Dispositivo móvel"
    assert public_label("STATIC_OR_SSR") == "Estática ou renderizada no servidor (SSR)"


def test_catalog_public_labels_cover_all_domain_strenum_values() -> None:
    import ast
    import re
    from pathlib import Path
    from rasai.catalog_report_public_labels import PUBLIC_VALUE_LABELS

    root = Path(__file__).resolve().parents[1] / "src" / "rasai"
    files = (
        "domain.py",
        "actionability.py",
        "context_scope.py",
        "content_context.py",
        "prioritization.py",
        "comparison.py",
        "rules.py",
        "discovery.py",
        "semantic.py",
        "scoring.py",
        "acquisition.py",
        "semantic_coherence.py",
        "rendering.py",
        "m18_ai.py",
        "search_intelligence/models.py",
        "search_intelligence/competitive.py",
        "search_intelligence/competitive_ai.py",
        "search_intelligence/content.py",
    )
    missing: list[str] = []
    for relative in files:
        source = (root / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {
                base.id
                for base in node.bases
                if isinstance(base, ast.Name)
            }
            if not ({"StrEnum", "Enum"} & bases):
                continue
            for item in node.body:
                if not isinstance(item, ast.Assign) or not isinstance(item.value, ast.Constant):
                    continue
                if not isinstance(item.value.value, str):
                    continue
                raw = item.value.value
                key = re.sub(r"[^A-Z0-9]+", "_", raw.upper()).strip("_")
                if key not in PUBLIC_VALUE_LABELS:
                    missing.append(f"{relative}:{node.name}: {raw}")
    assert not missing, "\n".join(missing)


def test_public_label_catalog_covers_canonical_enum_domains() -> None:
    from rasai.actionability import Actionability
    from rasai.acquisition import NetworkErrorKind
    from rasai.comparison import DeviceComparisonOutcome
    from rasai.context_scope import ContextScope
    from rasai.discovery import RobotsState, SitemapState
    from rasai.domain import (
        ArchitectureClassification,
        AuditMode,
        AuditStatus,
        CompletionStatus,
        DeviceContext,
        DiscoverySource,
        EvidenceType,
        FindingDevice,
        RuleResult,
        Severity,
        TargetType,
    )
    from rasai.m18_ai import AttemptStatus, ProviderErrorClass, RuntimeProviderState
    from rasai.prioritization import Effort, Impact, PriorityClass, PriorityConfidence
    from rasai.rendering import RenderErrorKind
    from rasai.scoring import ConsolidationStatus, ScoreConfidence
    from rasai.search_intelligence.competitive import SearchResultClass
    from rasai.search_intelligence.competitive_ai import (
        CompetitiveAiCategory,
        CompetitiveAiPriority,
        CompetitiveAiState,
    )
    from rasai.search_intelligence.content import ContentFetchStatus
    from rasai.search_intelligence.models import (
        DomainMatchStatus,
        QueryOrigin,
        SerpDataMode,
        SerpObservationStatus,
    )
    from rasai.semantic import EntityType, ProviderState
    from rasai.semantic_coherence import CoherenceResult

    enum_types = (
        Actionability,
        NetworkErrorKind,
        DeviceComparisonOutcome,
        ContextScope,
        RobotsState,
        SitemapState,
        ArchitectureClassification,
        AuditMode,
        AuditStatus,
        CompletionStatus,
        DeviceContext,
        DiscoverySource,
        EvidenceType,
        FindingDevice,
        RuleResult,
        Severity,
        TargetType,
        AttemptStatus,
        ProviderErrorClass,
        RuntimeProviderState,
        Effort,
        Impact,
        PriorityClass,
        PriorityConfidence,
        RenderErrorKind,
        ConsolidationStatus,
        ScoreConfidence,
        SearchResultClass,
        CompetitiveAiCategory,
        CompetitiveAiPriority,
        CompetitiveAiState,
        ContentFetchStatus,
        DomainMatchStatus,
        QueryOrigin,
        SerpDataMode,
        SerpObservationStatus,
        EntityType,
        ProviderState,
        CoherenceResult,
    )
    missing = [
        f"{enum_type.__name__}.{item.name}={item.value}"
        for enum_type in enum_types
        for item in enum_type
        if public_label(item.value) is None
    ]
    assert missing == []


def test_security_and_observability_public_labels_are_pt_br() -> None:
    expected = {
        "CONFIGURATION_WEAKNESS": "Fragilidade de configuração",
        "POTENTIAL_VULNERABILITY": "Vulnerabilidade potencial",
        "HTTP_SECURITY": "Segurança HTTP",
        "VULNERABILITY_INTELLIGENCE": "Inteligência de vulnerabilidades / CVE",
        "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS": "Google Search Console - Análise de pesquisa",
        "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION": "Google Search Console - Inspeção de URL",
        "CHROME_UX_REPORT_HISTORY": "Histórico do Chrome UX Report",
        "MICROSOFT_CLARITY_LIVE_INSIGHTS": "Microsoft Clarity",
    }
    for raw, label in expected.items():
        assert public_label(raw) == label
