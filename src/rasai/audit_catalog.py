"""Canonical audit catalog taxonomy shared by the console and report projections.

The catalog is a product/readiness taxonomy only. It does not redefine collectors,
scoring, provider routing, retries, quarantine, fulfillment or report-generation rules.
Stable ``CAT-*`` identifiers are intended to survive wording/layout changes so one AUD
can later project the same choices into HTML evidence and result surfaces.
"""
from __future__ import annotations

from dataclasses import dataclass

CATALOG_VERSION = "2"
AI_NONE = "NONE"
AI_OPTIONAL = "OPTIONAL"
AI_REQUIRED = "REQUIRED"


@dataclass(frozen=True, slots=True)
class AiUse:
    operation: str
    label: str
    mode: str
    purpose: str


@dataclass(frozen=True, slots=True)
class AuditCatalog:
    id: str
    label: str
    purpose: str
    expected_result: str
    capability_ids: tuple[str, ...]
    ai_uses: tuple[AiUse, ...] = ()
    producer: bool = True

    @property
    def ai_mode(self) -> str:
        modes = {item.mode for item in self.ai_uses}
        if AI_REQUIRED in modes:
            return AI_REQUIRED
        if AI_OPTIONAL in modes:
            return AI_OPTIONAL
        return AI_NONE


CATALOGS: tuple[AuditCatalog, ...] = (
    AuditCatalog(
        "CAT-01",
        "Fundamentos técnicos e descoberta",
        "Validar a base técnica que permite descobrir, acessar e interpretar o alvo.",
        "Descoberta, indexabilidade, controles técnicos e evidências estruturais do alvo.",
        ("domain-discovery", "standards"),
    ),
    AuditCatalog(
        "CAT-02",
        "Acessibilidade",
        "Avaliar barreiras de acessibilidade e manter a evidência técnica separada da interpretação advisory.",
        "Violações, elementos afetados, severidade e evidências de acessibilidade.",
        ("accessibility",),
    ),
    AuditCatalog(
        "CAT-03",
        "Conteúdo, semântica e dados estruturados",
        "Avaliar estrutura de conteúdo, JSON-LD e contexto semântico/editorial aplicável.",
        "Conteúdo, estrutura semântica, JSON-LD e contexto editorial aplicável.",
        ("content-suggestions",),
        (
            AiUse(
                "semantic_context",
                "Semântica/YMYL/E-E-A-T contextual",
                AI_OPTIONAL,
                "Enriquece leitura contextual; validações estruturais permanecem determinísticas.",
            ),
        ),
    ),
    AuditCatalog(
        "CAT-04",
        "Web Performance",
        "Medir laboratório/campo e evidenciar gargalos de performance conforme fontes configuradas.",
        "Métricas de performance, categorias Lighthouse solicitadas e dados de campo disponíveis.",
        ("web-performance",),
    ),
    AuditCatalog(
        "CAT-05",
        "Search & AI Intelligence",
        "Combinar Search/SERP, GSC compatível, visibilidade em IA e observabilidade aplicável sem acoplar fontes independentes.",
        "Inteligência de Search/AI baseada nas fontes explicitamente configuradas e aplicáveis ao alvo.",
        ("search-intelligence", "google-search-console", "ai-visibility", "observability"),
    ),
    AuditCatalog(
        "CAT-06",
        "Apdex de navegação",
        "Mensurar navegação sintética segundo thresholds, amostras e carga definidos.",
        "Amostras de navegação e Apdex calculado conforme thresholds e carga configurados.",
        ("apdex-navigation",),
    ),
    AuditCatalog(
        "CAT-07",
        "Apdex de experiência",
        "Mensurar experiência sintética e distribuição populacional sobre a base de navegação.",
        "Apdex de experiência e distribuição da população sintética conforme configuração vigente.",
        ("apdex-experience",),
    ),
    AuditCatalog(
        "CAT-08",
        "Análise profunda e melhorias",
        "Consumir as evidências produzidas pelos catálogos selecionados e gerar análise evidence-bound adicional.",
        "Prioridades, explicações, correlações e ações adicionais vinculadas às evidências produzidas.",
        ("deep-analysis",),
        (
            AiUse(
                "deep_analysis",
                "Análise profunda evidence-bound",
                AI_REQUIRED,
                "O resultado deste catálogo é produzido pelo orquestrador principal de IA sobre evidências existentes.",
            ),
        ),
        producer=False,
    ),
    AuditCatalog(
        "CAT-09",
        "Remediações",
        "Transformar achados/evidências em ações técnicas ou editoriais rastreáveis.",
        "Ações técnicas/editoriais derivadas das evidências sem alterar scoring por opinião de IA.",
        ("remediation",),
        (
            AiUse(
                "remediation_enrichment",
                "Contextualização/exemplos adicionais",
                AI_OPTIONAL,
                "Enriquece ações quando solicitado; remediações determinísticas continuam disponíveis.",
            ),
        ),
        producer=False,
    ),
    AuditCatalog(
        "CAT-10",
        "Segurança passiva",
        "Avaliar a prontidão de segurança web de forma passiva, reutilizando HTTP, navegador e dados de tempo de execução, além de correlacionar vulnerabilidades conhecidas sem exploração.",
        "Postura de transporte, cabeçalhos, cookies, recursos próprios e externos, dados de tempo de execução, vulnerabilidades conhecidas e remediações rastreáveis.",
        ("passive-security",),
        (
            AiUse(
                "passive_security_advisory",
                "Interpretação e remediação de segurança",
                AI_OPTIONAL,
                "Enriquece achados determinísticos após a consolidação da evidência; não decide presença de controles, versão ou CVE.",
            ),
        ),
    ),
)
CATALOG_BY_ID = {item.id: item for item in CATALOGS}
PRODUCER_CATALOG_IDS = frozenset(item.id for item in CATALOGS if item.producer)
SYSTEM_DERIVED_CAPABILITY_IDS = ("quality",)
