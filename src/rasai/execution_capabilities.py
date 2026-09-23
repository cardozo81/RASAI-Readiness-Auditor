"""Canonical audit-capability catalog shared by preparation UX and execution profiles."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuditCapability:
    id: str
    label: str
    purpose: str
    expected_result: str
    profile_selectable: bool = False
    automatic: bool = False
    derived: bool = False
    workload: str = "local"
    cost_note: str = "Sem workload externo adicional específico."


CAPABILITIES: tuple[AuditCapability, ...] = (
    AuditCapability(
        "domain-discovery",
        "Domínio e descoberta",
        "Verificar descoberta técnica, crawler controls, robots, sitemaps/feeds e sinais de exposição do domínio.",
        "Evidências determinísticas de descoberta/indexabilidade e controles de crawler.",
        automatic=True,
    ),
    AuditCapability(
        "accessibility",
        "Acessibilidade",
        "Avaliar evidências de acessibilidade disponíveis no core e, quando solicitado, enriquecer com Lighthouse.",
        "Diagnóstico de acessibilidade com evidências determinísticas e enriquecimento disponível.",
        automatic=True,
    ),
    AuditCapability(
        "web-performance",
        "Web Performance",
        "Medir performance de laboratório/campo usando PageSpeed, Lighthouse e CrUX conforme configuração.",
        "Métricas de performance, categorias Lighthouse solicitadas e dados de campo disponíveis.",
        profile_selectable=True,
        workload="api",
        cost_note="Pode consumir quota de PageSpeed/CrUX e tempo de processamento Lighthouse.",
    ),
    AuditCapability(
        "standards",
        "Métricas e padrões",
        "Aplicar serviços e referências complementares baseados em padrões Web quando disponíveis.",
        "Evidências complementares de padrões, compatibilidade e qualidade técnica.",
        automatic=True,
        workload="external-if-configured",
        cost_note="Usa somente serviços já habilitados/configurados sob seus próprios contratos.",
    ),
    AuditCapability(
        "search-intelligence",
        "Search Intelligence / SERP",
        "Observar resultados de busca para termos explicitamente definidos pelo operador.",
        "Posicionamento/concorrência SERP para os termos e profundidade configurados.",
        profile_selectable=True,
        workload="api",
        cost_note="Pode consumir quota/créditos do provider SERP conforme termos, depth e paginação.",
    ),
    AuditCapability(
        "apdex-navigation",
        "Apdex de navegação",
        "Executar navegações sintéticas repetidas para medir desempenho percebido sob perfil controlado.",
        "Amostras de navegação e Apdex calculado conforme thresholds e carga configurados.",
        profile_selectable=True,
        workload="browser",
        cost_note="Gera navegações reais, uso local de CPU/tempo e carga HTTP contra o alvo.",
    ),
    AuditCapability(
        "apdex-experience",
        "Apdex de experiência",
        "Modelar experiência sintética por distribuição de dispositivos e parâmetros definidos pelo operador.",
        "Apdex de experiência e distribuição da população sintética conforme configuração vigente.",
        profile_selectable=True,
        workload="browser",
        cost_note="Depende da medição sintética e pode ampliar volume de navegações/carga.",
    ),
    AuditCapability(
        "ai-visibility",
        "Visibilidade em IA",
        "Consolidar evidências de visibilidade/consumo por IA quando houver fontes aplicáveis.",
        "Leitura de visibilidade em IA baseada somente em evidências efetivamente disponíveis.",
        automatic=True,
        derived=True,
    ),
    AuditCapability(
        "observability",
        "Search & AI observados",
        "Agregar fontes observacionais externas previamente configuradas.",
        "Evidências observacionais complementares sem tornar integrações opt-in obrigatórias.",
        automatic=True,
        workload="external-if-configured",
        cost_note="Não ativa integrações opt-in; usa somente as que já estiverem habilitadas.",
    ),
    AuditCapability(
        "deep-analysis",
        "Análise profunda e melhorias",
        "Executar análise evidence-bound adicional para uma URL usando a IA principal/orquestrador canônico.",
        "Prioridades, explicações e ações corretivas adicionais vinculadas às evidências da URL.",
        profile_selectable=True,
        workload="ai",
        cost_note="Gera chamadas adicionais de IA pelo orquestrador principal.",
    ),
    AuditCapability(
        "content-suggestions",
        "Conteúdo e JSON-LD",
        "Avaliar estrutura/conteúdo e produzir orientação JSON-LD; IA permanece enriquecimento opcional.",
        "Diagnóstico estrutural de conteúdo/JSON-LD e remediação advisory quando IA estiver habilitada.",
        automatic=True,
    ),
    AuditCapability(
        "remediation",
        "Remediações",
        "Produzir correções determinísticas e, quando solicitado, enriquecimento advisory por IA.",
        "Ações técnicas/editoriais derivadas das evidências sem alterar scoring por opinião de IA.",
        profile_selectable=True,
        workload="ai-if-enabled",
        cost_note="IA só gera custo quando remediação por IA já estiver solicitada e houver provider apto.",
    ),
    AuditCapability(
        "quality",
        "Quality & decisão",
        "Derivar visão de qualidade/decisão a partir das evidências e regras aplicáveis.",
        "Resultado sistêmico derivado do conjunto efetivamente executado.",
        automatic=True,
        derived=True,
    ),
)

CAPABILITY_BY_ID = {item.id: item for item in CAPABILITIES}
PROFILE_SELECTABLE = tuple(item for item in CAPABILITIES if item.profile_selectable)

# Capabilities whose presence in a profile describes expected coverage but does not create
# a blocking prerequisite by itself. They are automatic/derived or consume only services
# already explicitly enabled elsewhere.
NON_BLOCKING_PROFILE_CAPABILITIES = frozenset(
    item.id for item in CAPABILITIES if item.automatic or item.derived
)
