"""Presentation-only labels for generated RASAi HTML reports.

Persisted enums remain unchanged. This module only translates isolated machine
states when they are rendered as primary values in table cells, metric values or
badges. Technical identifiers inside code/pre blocks and diagnostic prose are not
rewritten.
"""
from __future__ import annotations

import re


# Keep this map intentionally conservative. Add only values whose machine form is
# materially harder to read when used as a primary user-facing value.
_PUBLIC_LABELS: dict[str, str] = {
    # Execution and availability.
    "SUCCESS": "Concluído",
    "COMPLETED": "Concluído",
    "COMPLETE": "Concluído",
    "COMPLETE_WITH_LIMITATIONS": "Concluído com limitações",
    "DEGRADED": "Execução com limitações",
    "FULL": "Execução completa",
    "NO_AI": "Execução sem IA",
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
    "SKIPPED": "Ignorado",
    "FAILED": "Falhou",
    "ERROR": "Erro",
    "WARNING": "Alerta",
    "UNKNOWN": "Não determinado",
    "UNAVAILABLE": "Indisponível",
    "NOT_AVAILABLE": "Indisponível",
    "NOT_CONFIGURED": "Não configurado",
    "DISABLED": "Desabilitado",
    "ENABLED": "Habilitado",
    "NO_ELIGIBLE_FINDINGS": "Nenhum finding elegível",
    "DATA_UNAVAILABLE": "Dados indisponíveis",
    "NOT_DETERMINABLE": "Não determinável",
    "NOT_OBSERVED": "Não observado",
    "NOT_COMPARABLE": "Não comparável",
    "URL_SET": "Conjunto de URLs",
    "SEED": "URL inicial",
    "INTERNAL_LINK": "Link interno",
    "MANUAL": "Informado manualmente",
    "OBTAINED": "Obtido",
    "HTTP_ERROR": "Erro HTTP",
    "NETWORK_ERROR": "Erro de rede",
    "NOT_FOUND": "Não localizado",
    # Scoring and evaluation.
    "PASS": "Aprovado",
    "FAIL": "Não aprovado",
    "CONSOLIDATED": "Consolidado",
    "NOT_CONSOLIDATED": "Não consolidado",
    "PARTIAL": "Parcial",
    "NOT_APPLICABLE": "Não aplicável",
    "VALID": "Válido",
    "INVALID": "Inválido",
    "SAME": "Sem diferença material",
    "DIFFERENT": "Diferente",
    "REQUIRED_FIX": "Correção necessária",
    "REVIEW_RECOMMENDED": "Revisão recomendada",
    "OPTIONAL_IMPROVEMENT": "Melhoria opcional",
    "NO_ACTION": "Nenhuma ação necessária",
    "INSUFFICIENT_EVIDENCE": "Evidência insuficiente",
    # SCORE-GEO/SARI dimensions when rendered as isolated user-facing values.
    "TECHNICAL_ACCESSIBILITY": "Acessibilidade técnica",
    "INDEXABILITY": "Capacidade de indexação",
    "CONTENT_EXTRACTABILITY": "Extração de conteúdo",
    "SEMANTIC_STRUCTURE": "Estrutura semântica",
    "ENTITY_CLARITY": "Clareza de entidades",
    "STRUCTURED_DATA": "Dados estruturados",
    "ANSWERABILITY": "Capacidade de resposta",
    "CITATION_READINESS": "Prontidão para citação",
    "EVIDENCE_TRUST": "Confiança da evidência",
    "INTENT_COVERAGE": "Cobertura de intenção",
    "OVERALL_READINESS": "Readiness geral",
    # Severity and confidence.
    "CRITICAL": "Crítica",
    "HIGH": "Alta",
    "MEDIUM": "Média",
    "LOW": "Baixa",
    "INFO": "Informativa",
    "VERY_LOW": "Muito baixa",
    "MINIMAL": "Mínimo",
    # Device/population labels.
    "MOBILE": "Mobile",
    "DESKTOP": "Desktop",
    "BOTH": "Ambos",
    "POPULATION": "População",
    # Operational priority. Keep the class visible because it is useful for traceability.
    "P0": "Crítica (P0)",
    "P1": "Alta (P1)",
    "P2": "Média (P2)",
    "P3": "Baixa (P3)",
    "P4": "Muito baixa (P4)",
    # Change/monitoring states.
    "REGRESSED": "Regrediu",
    "IMPROVED": "Melhorou",
    "RESOLVED": "Resolvido",
    "CHANGED": "Alterado",
    "NEW": "Novo",
    "UNCHANGED": "Sem alteração",
    "ALIGNED": "Alinhado",
    "UNMATCHED": "Sem correspondência",
    "INTENT_NOT_AVAILABLE": "Intenção indisponível",
    "ALIGNED_WINDOW": "Janelas alinhadas",
    "PARTIAL_OVERLAP": "Sobreposição parcial",
    "NON_OVERLAPPING": "Janelas sem sobreposição",
    "UNKNOWN_PERIOD": "Período indeterminado",
    "TEMPORAL_ASSOCIATION_ONLY": "Apenas associação temporal",
    # Fix verification states.
    "FIXED": "Corrigido",
    "PARTIALLY_FIXED": "Parcialmente corrigido",
    "NOT_FIXED": "Não corrigido",
    "NOT_VERIFIABLE": "Não verificável",
    # Quality/recommendation states.
    "ADVISORY": "Informativo",
    "COMPLETE_FOR_TOP_LEVEL_REQUIREMENTS": "Requisitos principais atendidos",
    "SUPPORTED_BY_PERSISTED_EVIDENCE": "Suportada pela evidência persistida",
    "SUPPORTED_BY_GROUP": "Suportada pelo agrupamento",
    "UNSUPPORTED": "Sem suporte suficiente",
    "OPEN": "Aberto",
    "ACTIVE": "Ativo",
    "CLOSED": "Fechado",
    "DISMISSED": "Dispensado",
    # Synthetic UX session mode. Preserve the canonical technical term in parentheses.
    "COLD": "Fria (cold)",
    "WARM": "Aquecida (warm)",
    # AI routing and provider states.
    "SINGLE_PROVIDER": "Provedor único",
    "AUTO": "Automática",
    "NONE": "Nenhuma",
    "CHAIN_EXHAUSTED": "Cadeia de provedores esgotada",
    "PROVIDER_UNAVAILABLE": "Provedor indisponível",
    "CONTRACT_ERROR": "Erro no contrato de evidências",
    "QUARANTINED_FOR_AUDIT": "Indisponível nesta auditoria",
    "PROVIDER_DEFAULT": "Padrão do provedor",
    "TECHNICAL_ERROR": "Erro técnico",
    "BUSINESS_ERROR": "Erro operacional do provedor",
    "QUARANTINED": "Isolado nesta auditoria",
    "STANDBY": "Em espera",
    "AUTH_ERROR": "Erro de autenticação",
    "QUOTA_ERROR": "Quota indisponível",
    "CREDIT_ERROR": "Crédito/saldo indisponível",
    "RATE_LIMIT_ERROR": "Limite de requisições atingido",
    "MODEL_ERROR": "Modelo indisponível ou incompatível",
    "PERMISSION_ERROR": "Permissão insuficiente",
    "TIMEOUT_ERROR": "Tempo limite excedido",
    "SERVER_ERROR": "Erro no servidor do provedor",
    "EMPTY_RESPONSE": "Resposta vazia",
    "INVALID_RESPONSE": "Resposta inválida",
    "UNKNOWN_PROVIDER_ERROR": "Erro não classificado do provedor",
    "AI_PROVIDER_UNAVAILABLE": "Provedor de IA indisponível",
    # Crawling/discovery and content-remediation machine values.
    "ABSENT": "Ausente",
    "PRESENT": "Presente",
    "AVAILABLE": "Disponível",
    "AI_ACCESS": "Acesso por sistemas de IA",
    "BOUNDED_AI_RESOURCE_ASSESSMENT": "Avaliação por IA com escopo limitado",
    "MISSING_PROPOSED": "Proposta não gerada",
    "EXISTING_REVIEW": "Revisão do JSON-LD existente",
    "NO_SAFE_SUGGESTIONS": "Nenhuma sugestão segura",
    "INTERNAL_BASELINE": "Referência interna",
    "RULES_GUIDE": "Guia de regras",
    "SCORING_GUIDE": "Guia de pontuação",
    "ADD_ATTRIBUTION": "Adicionar atribuição",
    "ADD_FACTUAL_CONTEXT": "Adicionar contexto factual",
    "ADD_OR_CORRECT": "Adicionar ou corrigir",
    "ADD_OR_RESTRUCTURE_ANSWER": "Adicionar ou reestruturar resposta",
    "ADD_QUALIFIERS": "Adicionar qualificadores",
    "CANONICAL_ABSENT": "Canonical ausente",
    "CLOSE_INTENT_GAPS": "Fechar lacunas de intenção",
    "CONTENT_REGION": "Região de conteúdo",
    "CORRECT_RESOURCE": "Corrigir recurso",
    "CORRECT_STRUCTURED_DATA": "Corrigir dados estruturados",
    "DOCUMENT_OR_CONTENT": "Documento ou conteúdo",
    "DOMAIN_RESOURCE": "Recurso do domínio",
    "REVIEW_AND_CORRECT": "Revisar e corrigir",
    "ROBOTS_ABSENT": "robots.txt ausente",
    "SITEMAP_ABSENT": "Sitemap ausente",
    "VERY_HIGH": "Muito alta",
    "HTTP_RESPONSE": "Resposta HTTP",
    "HTTP_HEADER": "Cabeçalho HTTP",
    "ROBOTS_RULE": "Regra de robots.txt",
    "SITEMAP_ENTRY": "Entrada de sitemap",
    "HTML_ELEMENT": "Elemento HTML",
    "DOM_ELEMENT": "Elemento do DOM",
    "VISUAL_SNAPSHOT": "Captura visual",
    "META_TAG": "Meta tag",
    "MAIN_CONTENT": "Conteúdo principal",
    "TEXT_EXCERPT": "Trecho de texto",
    "AI_ANALYSIS": "Análise por IA",
    "COMPARISON": "Comparação",
    "STATIC_OR_SSR": "Estática ou renderizada no servidor (SSR)",
    "HYDRATED": "Renderizada no servidor com hidratação",
    "CSR_SPA": "SPA renderizada no cliente (CSR)",
    "MIXED": "Mista",
    "GLOBAL": "Global",
    "PAGE": "Página",
    "SNAPSHOT": "Captura",
    "HEURISTIC": "Heurística",
    "ORGANIZATION": "Organização",
    "PERSON": "Pessoa",
    "PRODUCT": "Produto",
    "SERVICE": "Serviço",
    "PLACE": "Local",
    "BRAND": "Marca",
    "TOPIC": "Tópico",
    "OTHER": "Outro",
    # Rule groups/dimensions that may appear in technical tables.
    "CONTENT_EXTRACTION": "Extração de conteúdo",
    "DUPLICATE_CONTENT": "Conteúdo duplicado",
    "ENTITY_AMBIGUITY": "Ambiguidade de entidade",
    "ENTITY_CONTEXT": "Contexto de entidade",
    "ENTITY_PRIMARY": "Entidade principal",
    "EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1": "Peso igual entre dimensões aplicáveis",
    "FACTUAL_CLAIMS": "Afirmações factuais",
    "FACTUAL_CONTEXT": "Contexto factual",
    "INDEX_DIRECTIVES": "Diretivas de indexação",
    "INFERENCE_LOAD": "Carga de inferência",
    "INTENT_GAPS": "Lacunas de intenção",
    "INTENT_SET": "Conjunto de intenções",
    "INTERNAL_LINKS": "Links internos",
    "JS_CONTENT": "Conteúdo por JavaScript",
    "PAGE_ACCESS": "Acesso à página",
    "PRIMARY_ANSWERS": "Respostas principais",
    "PRIMARY_INTENT": "Intenção principal",
    "REDIRECT": "Redirecionamentos",
    "RENDER_ACCESS": "Acesso após renderização",
    "ROBOTS": "robots.txt",
    "SEMANTIC_HIERARCHY": "Hierarquia semântica",
    "SEMANTIC_TITLE": "Título semântico",
    "SEMANTIC_TOPIC": "Tópico semântico",
    "SITEMAP": "Sitemap",
    "SOFT_ERROR": "Erro aparente",
    "SPA_NAVIGATION": "Navegação SPA",
    "SPA_ROUTE": "Rota SPA",
    "STRUCTURED_DATA_SYNTAX": "Sintaxe de dados estruturados",
    # Web Performance diagnostic categories.
    "CRITICAL_PATH": "Caminho crítico",
    "JAVASCRIPT_MAIN_THREAD": "Thread principal de JavaScript",
    "LAYOUT_STABILITY": "Estabilidade de layout",
    "PAGESPEED_CRUX": "PageSpeed / CrUX",
    "PAGESPEED_INSIGHTS": "PageSpeed Insights",
    "RENDER_BLOCKING": "Bloqueio de renderização",
    "SERVER_DOCUMENT": "Documento do servidor",
    "THIRD_PARTY": "Terceiros",
    "CONNECTION": "Conexão",
    "TIMEOUT": "Tempo limite excedido",
    "PROTOCOL": "Erro de protocolo",
    "REDIRECT_LOOP": "Loop de redirecionamento",
    "TOO_MANY_REDIRECTS": "Redirecionamentos em excesso",
    "INVALID_REDIRECT": "Redirecionamento inválido",
    "BROWSER_UNAVAILABLE": "Navegador indisponível",
    "NAVIGATION_TIMEOUT": "Tempo limite de navegação excedido",
    "NAVIGATION_ERROR": "Erro de navegação",
    "RENDERER_ERROR": "Erro de renderização",
    "EXTRACTION_INPUT_UNAVAILABLE": "Conteúdo de entrada indisponível para extração",
    "EXTRACTION_ERROR": "Erro de extração",
    "NO_DEVICE_SNAPSHOTS": "Nenhuma captura de dispositivo disponível",
    "ONE_DEVICE_SNAPSHOT_MISSING": "Captura ausente em um dos dispositivos",
}

# Exact, isolated visible values only. Nested markup is deliberately excluded.
_VISIBLE_VALUE_RE = re.compile(
    r"(<(?P<tag>td|strong|span)\b[^>]*>)(?P<value>[A-Z][A-Z0-9_/-]*)(</(?P=tag)>)"
)


def public_label(value: str) -> str:
    """Return a user-facing label for a known machine value."""
    return _PUBLIC_LABELS.get(value, value)


_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)", flags=re.DOTALL)
_PUBLIC_TOKEN_RE = re.compile(
    r"(?<![A-Z0-9_])(" + "|".join(
        re.escape(value) for value in sorted(_PUBLIC_LABELS, key=len, reverse=True)
    ) + r")(?![A-Z0-9_])"
)


def humanize_report_html(html: str, *, page_name: str | None = None) -> str:
    """Humanize known machine values without mutating persisted or code content.

    Values are translated both when isolated in primary cells and when embedded
    in normal visible prose. ``code``, ``pre``, ``script`` and ``style`` remain
    untouched so technical identifiers, environment variables and examples keep
    their canonical representation.
    """
    del page_name

    def isolated(match: re.Match[str]) -> str:
        value = match.group("value")
        label = _PUBLIC_LABELS.get(value)
        if label is None:
            return match.group(0)
        return f"{match.group(1)}{label}{match.group(4)}"

    parts = _TAG_SPLIT_RE.split(html)
    blocked_depth = 0
    output: list[str] = []
    for part in parts:
        if part.startswith("<"):
            lowered = part.lower()
            if re.match(r"<(script|style|pre|code)\b", lowered):
                blocked_depth += 1
            elif re.match(r"</(script|style|pre|code)\b", lowered):
                blocked_depth = max(0, blocked_depth - 1)
            output.append(part)
            continue
        if blocked_depth:
            output.append(part)
            continue
        output.append(_PUBLIC_TOKEN_RE.sub(lambda match: _PUBLIC_LABELS[match.group(1)], part))
    return _VISIBLE_VALUE_RE.sub(isolated, "".join(output))
