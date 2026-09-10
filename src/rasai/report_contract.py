"""Stable public report-surface contract for RASAi.

Public report URLs are version-neutral. Method and product versions belong to
persisted metadata and report content, never to the canonical filename. This module
is the single source of truth for navigation, completeness checks, report manifests
and SaaS/API projection.
"""
from __future__ import annotations

from dataclasses import dataclass

SARI_VERSION = "SARI-001"
REPORT_CONTRACT_VERSION = "REPORT-CONTRACT-002"
OBSERVABILITY_CONTRACT_VERSION = "OBSERVABILITY-CONTRACT-001"


@dataclass(frozen=True, slots=True)
class ReportSurface:
    id: str
    filename: str
    label: str
    optional: bool
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    required_dependencies: tuple[str, ...] = ()
    optional_dependencies: tuple[str, ...] = ()
    ai_usage: str = "Nenhum"
    score_impact: str = "Nenhum"
    source_of_truth: str = "audit.db"


REPORT_SURFACES: tuple[ReportSurface, ...] = (
    ReportSurface(
        id="index",
        filename="index.html",
        label="Visão geral",
        optional=False,
        inputs=("evidências persistidas", "resultados derivados da auditoria"),
        outputs=("síntese executiva", "mapa de dependências"),
        optional_dependencies=("domínios externos habilitados", "resultados de IA habilitados"),
        ai_usage="Somente projeta resultados de IA já persistidos; não chama IA.",
        score_impact="Nenhum; apenas apresenta o SARI/SCORE persistido.",
    ),
    ReportSurface(
        id="readiness",
        filename="readiness.html",
        label="Readiness SARI",
        optional=False,
        inputs=("scores", "Coverage", "Confidence", "Consolidation", "evidências de regras"),
        outputs=("SARI-001", "dimensões de readiness", "Overall persistido"),
        required_dependencies=("audit.db",),
        ai_usage="IA pode fornecer evidência semântica para regras específicas; o score é calculado deterministicamente a partir das evidências persistidas.",
        score_impact="É a projeção pública do SARI-001 e do scoring_version persistido.",
    ),
    ReportSurface(
        id="scoring",
        filename="scoring.html",
        label="Metodologia de scoring",
        optional=False,
        inputs=("scoring_version persistido", "scores", "Coverage", "Confidence", "Consolidation"),
        outputs=("fórmula", "dimensões", "pesos", "gates", "limitações", "reprodutibilidade"),
        required_dependencies=("audit.db",),
        ai_usage="A fórmula e os pesos não dependem de IA. Quando habilitada, a IA técnica pode materializar somente avaliações evidence-bound bounded em BR-GEO-055/056, compartilhando os grupos determinísticos SITEMAP/ROBOTS sem escolher pesos nem criar bônus duplicado.",
        score_impact="Define e explica o contrato de scoring aplicado à auditoria; não recalcula o score ao renderizar HTML.",
    ),
    ReportSurface(
        id="mobile",
        filename="mobile.html",
        label="Relatório Mobile",
        optional=True,
        inputs=("snapshots Mobile", "RuleExecutions", "Findings", "Evidences"),
        outputs=("scorecard de contexto read-only", "findings e evidências Mobile"),
        ai_usage="Pode exibir resultados semânticos de IA já persistidos e identificados como tal.",
        score_impact="Somente as regras que fazem parte do contrato SARI/SCORE contribuem; a página HTML não altera score.",
    ),
    ReportSurface(
        id="desktop",
        filename="desktop.html",
        label="Relatório Desktop",
        optional=True,
        inputs=("snapshots Desktop", "RuleExecutions", "Findings", "Evidences"),
        outputs=("scorecard de contexto read-only", "findings e evidências Desktop"),
        ai_usage="Pode exibir resultados semânticos de IA já persistidos e identificados como tal.",
        score_impact="Somente as regras que fazem parte do contrato SARI/SCORE contribuem; a página HTML não altera score.",
    ),
    ReportSurface(
        id="crawling-discovery",
        filename="crawling-discovery.html",
        label="Rastreamento e descoberta",
        optional=False,
        inputs=("robots.txt", "sitemaps", "links", "controles de crawlers", "diagnósticos determinísticos"),
        outputs=("diagnóstico de crawling/discovery",),
        optional_dependencies=("análise por IA explicitamente habilitada",),
        ai_usage="A IA, quando habilitada, interpreta somente diagnósticos/evidências fornecidos e o resultado deve ser marcado como gerado por IA.",
        score_impact="BR-GEO-003/017/018 e, quando houver avaliação técnica evidence-bound válida, BR-GEO-055/056 podem contribuir pelos grupos SITEMAP/ROBOTS; demais diagnósticos desta superfície permanecem advisory/non-scoring.",
    ),
    ReportSurface(
        id="accessibility",
        filename="accessibility.html",
        label="Acessibilidade",
        optional=False,
        inputs=("estado/artefato Lighthouse accessibility quando coletado",),
        outputs=("diagnóstico automatizado de acessibilidade ou estado explícito de indisponibilidade/desabilitação",),
        optional_dependencies=("coleta Web Performance/Lighthouse",),
        ai_usage="Nenhum.",
        score_impact="Nenhum impacto no SCORE-GEO-004.",
    ),
    ReportSurface(
        id="web-performance",
        filename="web-performance.html",
        label="Web Performance",
        optional=False,
        inputs=("estado da coleta", "PageSpeed/Lighthouse quando habilitado", "CrUX quando disponível"),
        outputs=("estado da integração", "métricas de laboratório quando coletadas", "Core Web Vitals de campo quando disponíveis", "telemetria de coleta"),
        optional_dependencies=("PageSpeed API", "CrUX API"),
        ai_usage="Nenhum.",
        score_impact="Nenhum impacto no SCORE-GEO-004.",
    ),
    ReportSurface(
        id="search-intelligence",
        filename="search-intelligence.html",
        label="Search Intelligence",
        optional=True,
        inputs=(
            "SERP observations persistidas",
            "resultados normalizados do provider de Search",
            "classificação competitiva RASAi quando executada",
            "features de conteúdo público quando explicitamente coletadas",
            "análise semântica por IA quando explicitamente habilitada e persistida",
        ),
        outputs=(
            "posição observada e contexto da query",
            "SERP normalizada",
            "candidatos competitivos observados",
            "comparação determinística de conteúdo",
            "hipóteses/recomendações semânticas evidence-bound quando disponíveis",
        ),
        required_dependencies=("SERP Observation persistida",),
        optional_dependencies=("provider de Search", "coleta HTTP pública limitada", "provider de IA"),
        ai_usage="A página não chama IA. Quando existe análise semântica persistida, identifica-a como derivada por IA e preserva provider/modelo/evidências disponíveis.",
        score_impact="Nenhum impacto automático em SARI-001 ou SCORE-GEO-004; Search Intelligence permanece observacional/advisory e não causal.",
        source_of_truth="Search Intelligence persistence + artifacts associados",
    ),
    ReportSurface(
        id="apdex",
        filename="apdex.html",
        label="Apdex de navegação",
        optional=True,
        inputs=("navegações sintéticas", "threshold T", "perfil de execução"),
        outputs=("Synthetic Navigation Apdex", "amostras e exclusões"),
        ai_usage="Nenhum.",
        score_impact="Nenhum impacto no SCORE-GEO-004.",
    ),
    ReportSurface(
        id="apdex-experience",
        filename="apdex-experience.html",
        label="Apdex de experiência",
        optional=True,
        inputs=("população sintética", "mix percentual Mobile/Desktop/Tablet", "thresholds configurados"),
        outputs=("Synthetic User Experience Apdex",),
        ai_usage="Nenhum.",
        score_impact="Nenhum impacto no SCORE-GEO-004.",
    ),
    ReportSurface(
        id="content-suggestions",
        filename="content-suggestions.html",
        label="Conteúdo e JSON-LD",
        optional=False,
        inputs=("findings elegíveis", "evidência textual", "contexto editorial/YMYL quando configurado"),
        outputs=("estado da remediação de conteúdo", "sugestões textuais advisory quando habilitadas", "orientação JSON-LD"),
        optional_dependencies=("provider de IA configurado",),
        ai_usage="Quando IA é usada, o output deve identificar provider/modelo e os inputs persistidos que fundamentaram a sugestão. Quando desabilitada, a página explicita esse estado.",
        score_impact="Nenhum efeito automático no SCORE-GEO-004.",
    ),
    ReportSurface(
        id="remediation",
        filename="remediation.html",
        label="Remediações",
        optional=False,
        inputs=("Findings", "RuleExecutions", "Evidences"),
        outputs=("receitas de remediação determinísticas",),
        ai_usage="Nenhum, salvo conteúdo explicitamente identificado como remediação textual por IA.",
        score_impact="Nenhum efeito automático; aplicar uma recomendação exige nova auditoria para nova medição.",
    ),
    ReportSurface(
        id="ai-usage",
        filename="ai-usage.html",
        label="Uso de IA",
        optional=False,
        inputs=("estado da sessão de IA", "telemetria de requests quando existentes", "provider/modelo", "tokens", "custos estimáveis"),
        outputs=("estado explícito de uso de IA", "rastreabilidade de chamadas quando executadas", "custo estimado quando calculável"),
        ai_usage="É a superfície de telemetria; não cria chamadas adicionais. Quando IA não é usada, a página explicita esse estado.",
        score_impact="Nenhum impacto no SCORE-GEO-004.",
    ),
    ReportSurface(
        id="ai-visibility",
        filename="ai-visibility.html",
        label="Visibilidade em IA",
        optional=True,
        inputs=("dataset/import observacional de visibilidade generativa",),
        outputs=("visibilidade generativa observada",),
        optional_dependencies=("dataset/import externo",),
        ai_usage="Não confundir a origem observacional com a IA usada pelo RASAi; a página não chama LLM para fabricar observações.",
        score_impact="Nenhum impacto no SCORE-GEO-004.",
    ),
    ReportSurface(
        id="observability",
        filename="observability.html",
        label="Search & AI observados",
        optional=True,
        inputs=("observability.db", "artifacts/observability", "fontes externas configuradas"),
        outputs=("observações pós-auditoria",),
        optional_dependencies=("Search Console", "URL Inspection", "CrUX History", "imports suportados"),
        ai_usage="Nenhum, salvo análise explicitamente identificada como derivada por IA.",
        score_impact="Nenhum impacto automático no SCORE-GEO-004.",
        source_of_truth="observability.db + artifacts/observability",
    ),
    ReportSurface(
        id="quality",
        filename="quality.html",
        label="Quality & decisão",
        optional=True,
        inputs=("audit.db read-only", "evidências", "comparações suportadas"),
        outputs=("verificação de qualidade", "fix verification", "evidence timeline"),
        ai_usage="Nenhum por padrão.",
        score_impact="Nenhum novo score; preserva a versão de origem e a comparabilidade metodológica.",
    ),
    ReportSurface(
        id="references",
        filename="references.html",
        label="Referências e metodologia",
        optional=False,
        inputs=("fontes metodológicas e referências públicas",),
        outputs=("proveniência metodológica", "glossário"),
        ai_usage="Nenhum.",
        score_impact="Nenhum; documenta fundamentos e fronteiras.",
    ),
)


CANONICAL_NAV_ITEMS: tuple[tuple[str, str], ...] = tuple(
    (surface.label, surface.filename) for surface in REPORT_SURFACES
)
CANONICAL_FILENAMES: tuple[str, ...] = tuple(surface.filename for surface in REPORT_SURFACES)
# Pre-publication contract: canonical filenames only; this remains empty by design.
REPORT_ALIASES: dict[str, str] = {}


def surface_by_id(surface_id: str) -> ReportSurface:
    for surface in REPORT_SURFACES:
        if surface.id == surface_id:
            return surface
    raise KeyError(surface_id)


def surface_by_filename(filename: str) -> ReportSurface:
    for surface in REPORT_SURFACES:
        if surface.filename == filename:
            return surface
    raise KeyError(filename)
