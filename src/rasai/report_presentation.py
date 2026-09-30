"""Presentation-only labels for generated RASAi HTML reports.

Persisted enums remain unchanged. This module translates machine states when they
are rendered as user-facing values. Public concepts, operational states and messages
are presented in pt-BR. Legitimate traceability identifiers and technical payloads
inside code/pre blocks remain canonical.
"""
from __future__ import annotations

import re

from rasai.public_language import (
    SUPPLEMENTAL_PUBLIC_LABELS,
    is_traceability_identifier,
    safe_visible_fallback,
    supplemental_public_label,
)
from rasai.time_contract import localize_visible_timestamps


# Vocabulário conceitual público do contrato SARI/SCORE-GEO. Cada dimensão/grupo
# deve possuir rótulo pt-BR explícito; os testes impõem cobertura.
SCORING_CONCEPT_LABELS: dict[str, str] = {
    # Dimensões. TECHNICAL_ACCESSIBILITY é compatibilidade de leitura e converge
    # para o mesmo conceito público de DISCOVERY_ACCESS.
    "TECHNICAL_ACCESSIBILITY": "Acesso e descoberta",
    "DISCOVERY_ACCESS": "Acesso e descoberta",
    "INDEXABILITY": "Indexabilidade e canonicalização",
    "CONTENT_EXTRACTABILITY": "Renderização e extração",
    "SEMANTIC_STRUCTURE": "Estrutura semântica",
    "ENTITY_CLARITY": "Clareza de entidades",
    "STRUCTURED_DATA": "Dados estruturados",
    "ANSWERABILITY": "Capacidade de resposta",
    "CITATION_READINESS": "Preparação para citação",
    "EVIDENCE_TRUST": "Evidências e confiabilidade",
    "INTENT_COVERAGE": "Cobertura de intenções",
    "CONTENT_VALUE": "Valor do conteúdo",
    "OVERALL_READINESS": "Prontidão geral",
    # Macrocomponentes.
    "DISCOVERY_AND_CRAWLER_ACCESS": "Descoberta e acesso de crawlers",
    "INDEXABILITY_AND_CANONICALIZATION": "Indexabilidade e canonicalização",
    "RENDERING_AND_EXTRACTABILITY": "Renderização e extração",
    "SEMANTIC_UNDERSTANDABILITY": "Compreensão semântica",
    "CONTENT_UTILITY_AND_INTENT": "Utilidade do conteúdo e intenção",
    "EVIDENCE_TRUST_AND_CITATION": "Evidências, confiança e citação",
    # Grupos de scoring.
    "PAGE_ACCESS": "Acesso à página",
    "ROBOTS": "robots.txt",
    "SITEMAP": "Sitemap",
    "REDIRECT": "Redirecionamentos",
    "SPA_ROUTE": "Rota SPA",
    "SPA_NAVIGATION": "Navegação SPA",
    "INTERNAL_LINKS": "Links internos",
    "INDEX_DIRECTIVES": "Diretivas de indexação",
    "CANONICAL": "Canonical",
    "SOFT_ERROR": "Erro suave (soft error)",
    "RENDER_ACCESS": "Acesso à renderização",
    "JS_CONTENT": "Conteúdo via JavaScript",
    "CONTENT_EXTRACTION": "Extração de conteúdo",
    "DUPLICATE_CONTENT": "Conteúdo duplicado",
    "SEMANTIC_TITLE": "Título semântico",
    "SEMANTIC_HIERARCHY": "Hierarquia semântica",
    "SEMANTIC_TOPIC": "Tópico semântico",
    "ENTITY_PRIMARY": "Entidade principal",
    "ENTITY_CONTEXT": "Contexto da entidade",
    "ENTITY_AMBIGUITY": "Ambiguidade de entidade",
    "STRUCTURED_DATA_SYNTAX": "Sintaxe dos dados estruturados",
    "STRUCTURED_DATA_CONSISTENCY": "Consistência dos dados estruturados",
    "PRIMARY_INTENT": "Intenção principal",
    "PRIMARY_ANSWERS": "Respostas principais",
    "FACTUAL_CLAIMS": "Afirmações factuais",
    "FACTUAL_CONTEXT": "Contexto factual",
    "INFERENCE_LOAD": "Carga de inferência",
    "ATTRIBUTION": "Atribuição",
    "RESPONSIBILITY": "Responsabilidade",
    "FRESHNESS": "Atualidade",
    "INTENT_SET": "Conjunto de intenções",
    "INTENT_GAPS": "Lacunas de intenção",
    "CONTENT_USEFULNESS": "Utilidade do conteúdo",
    "CONTENT_DIFFERENTIATION": "Diferenciação do conteúdo",
    "CONTENT_DEPTH": "Profundidade do conteúdo",
    # Conceitos dos gates críticos de prontidão.
    "DISCOVERY": "Descoberta",
    "EXTRACTION": "Extração",
}

# Some renderers may already have converted machine identifiers into Portuguese
# labels before the common presentation pass. Normalize only standalone text nodes;
# prose is intentionally not rewritten. This keeps conceptual names consistent
# without producing mixed-language sentence substitutions. Keys are casefolded so
# capitalization differences across renderers do not leak to HTML.
_STANDALONE_CONCEPT_LABELS: dict[str, str] = {
    key.casefold(): value
    for key, value in {
        # Normalize legacy English presentation vocabulary to the current pt-BR contract.
        "Discovery & Crawler Access": "Acesso e descoberta",
        "Discovery Access": "Acesso e descoberta",
        "Indexability": "Indexabilidade e canonicalização",
        "Rendering & Extractability": "Renderização e extração",
        "Content Extractability": "Renderização e extração",
        "Semantic Structure": "Estrutura semântica",
        "Entity Clarity": "Clareza de entidades",
        "Structured Data": "Dados estruturados",
        "Answerability": "Capacidade de resposta",
        "Citation Readiness": "Preparação para citação",
        "Evidence & Trust": "Evidências e confiabilidade",
        "Evidence Trust": "Evidências e confiabilidade",
        "Intent Coverage": "Cobertura de intenções",
        "Content Value": "Valor do conteúdo",
        # Normalize older Portuguese wording to the current public terminology.
        "Capacidade de indexação": "Indexabilidade e canonicalização",
        "Extração de conteúdo": "Renderização e extração",
    }.items()
}


# Keep this map conservative outside of the scoring vocabulary. Add values whose
# machine form is materially harder to read when used as a primary user-facing value.
_PUBLIC_LABELS: dict[str, str] = {
    **SCORING_CONCEPT_LABELS,
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
    "PROCESSING": "Em processamento",
    "RUNNING": "Em execução",
    "PENDING": "Pendente",
    "WAITING_FOR_DATA": "Aguardando dados",
    "PARTIAL_RETRYABLE": "Parcial - reprocessamento disponível",
    "PARTIAL_BLOCKED": "Parcial - há bloqueios",
    "EXPIRED_FOR_COMPLETION": "Expirado para conclusão",
    "FAILED_RETRYABLE": "Falha reprocessável",
    "FAILED_TERMINAL": "Falha terminal",
    "FAILED_PERMANENT": "Falha permanente",
    "FAILED_FATAL": "Falha fatal",
    "REQUESTED_NOT_EXECUTED": "Solicitado, não executado",
    # Stable Core Web Vitals identifiers must survive the final HTML humanizer.
    # Do not whitelist ambiguous ISO country codes globally.
    "LCP": "LCP",
    "INP": "INP",
    "CLS": "CLS",
    "NO_DATA": "Sem dados",
    "INCOMPLETE": "Incompleto",
    "PRELIMINARY": "Preliminar",
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
    "READY": "Pronto",
    "AVAILABLE": "Disponível",
    "MEASURED": "Medido",
    "GENERATED": "Gerado",
    "FINAL": "Final",
    "NOT_REQUESTED": "Não solicitado",
    "EXPIRED": "Expirado",
    "APPLICATION_ERROR": "Erro da aplicação",
    "INVALID_SAMPLE": "Amostra inválida",
    "ATTENTION": "Atenção",
    "BLOCKED": "Bloqueado",
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
    # Domínios canônicos usados por auditoria, evidência e Search Intelligence.
    "DOMAIN": "Domínio",
    "URL": "URL",
    "URL_SET": "Conjunto de URLs",
    "SEED": "URL inicial",
    "SITEMAP": "Sitemap",
    "INTERNAL_LINK": "Link interno",
    "REDIRECT": "Redirecionamento",
    "MANUAL": "Informado manualmente",
    "HEADING": "Título hierárquico (heading)",
    "LINK": "Link",
    "OBSERVED": "Observado",
    "OBSERVED_API": "API observada",
    "OBSERVED_SYNTHETIC": "Observação sintética",
    "IMPORTED": "Importado",
    "FIXTURE": "Dados de teste (fixture)",
    "MODELED": "Modelado",
    "AI_INFERRED": "Inferido por IA",
    "SEARCH_CONSOLE": "Google Search Console",
    "PROPERTIES": "Propriedades",
    "SITEMAPS": "Sitemaps",
    "SEARCH_ANALYTICS": "Desempenho de pesquisa",
    "SEARCH_APPEARANCE": "Aparência na pesquisa",
    "URL_INSPECTION": "Inspeção de URL",
    "GENERATIVE_AI_PERFORMANCE_EXPORT": "Exportação de desempenho em IA generativa",
    "GENERATIVE_AI_CONTROL": "Controle de IA generativa",
    "BING_WEBMASTER": "Bing Webmaster Tools",
    "PAGE_CONTENT": "Conteúdo da página",
    "AI_HYPOTHESIS": "Hipótese por IA",
    "SERP_RELATED": "Relacionada à SERP",
    "COMPETITOR_DISCOVERY": "Descoberta de concorrentes",
    "EXTERNAL": "Externo",
    "APDEX_NAVIGATION": "Apdex de navegação",
    "APDEX_EXPERIENCE": "Apdex de experiência",
    "EXPERIENCE": "Experiência",
    "SEO": "SEO",
    "GEO_SEARCH_AI": "GEO / Busca e IA",
    "BEST_PRACTICES": "Boas práticas",
    "SEMANTICS": "Semântica",
    "YMYL": "YMYL",
    "SECURITY": "Segurança",
    "VULNERABILITIES": "Vulnerabilidades",
    "HTML_CSS": "HTML / CSS",
    "CRAWLABILITY": "Rastreabilidade por crawlers",
    "COMPETITIVE_INTELLIGENCE": "Inteligência competitiva",
    "TECHNICAL_QUALITY": "Qualidade técnica",
    "ORIGIN": "Domínio / origem",
    "DEVICE_SNAPSHOT": "Dispositivo / captura",
    "PROFILE_MEASUREMENT": "Medição por perfil",
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
    "SEO_AEO_GEO": "SEO / AEO / GEO",
    "INFORMATIONAL": "Informacional",
    "TRANSACTIONAL": "Transacional",
    "REVIEW_COMPARISON": "Avaliação / comparação",
    "NEWS_EDITORIAL": "Notícias / editorial",
    "SUPPORT_DOCUMENTATION": "Suporte / documentação",
    "FORUM_UGC": "Fórum / conteúdo gerado por usuários",
    "PROFESSIONAL": "Profissional",
    "BENEFICIAL": "Benéfica",
    "USER_GENERATED": "Conteúdo gerado por usuários",
    "PRESENT": "Presente",
    "COHERENT": "Coerente",
    "INCOHERENT": "Incoerente",
    "CONSISTENT": "Consistente",
    "INCONSISTENT": "Inconsistente",
    "ALIGNED": "Alinhado",
    "MISALIGNED": "Desalinhado",
    "SATISFIED": "Satisfatória",
    "TOLERATING": "Tolerável",
    "FRUSTRATED": "Frustrada",
    "GOOD": "Bom",
    "POOR": "Ruim",
    "NEEDS_IMPROVEMENT": "Precisa melhorar",
    "NOT_FOUND_WITHIN_DEPTH": "Não encontrado na profundidade coletada",
    # Scoring and evaluation states. Concept names themselves live above.
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
    "HIERARCHICAL_WEIGHTED_READINESS_V1": "Hierarchical Weighted Readiness",
    "EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1": "Hierarchical Weighted Readiness",
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
    "P1": "Muito alta (P1)",
    "P2": "Alta (P2)",
    "P3": "Média (P3)",
    "P4": "Baixa (P4)",
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
    "AUTO": "Automático",
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
    "AI_NOT_AUTHORIZED_FOR_EXECUTION": "IA não autorizada para execução nesta auditoria",
    "AI_PREREQUISITES_INCOMPLETE": "Pré-requisitos da IA ainda não concluídos",
    "AI_PROVIDER_NOT_CONFIGURED": "Provedor de IA não configurado",
    "AI_NOT_CONFIGURED": "IA não configurada",
    "EXECUTION_POLICY": "Política de execução",
    "PREREQUISITE": "Pré-requisito",
    "ORCHESTRATION": "Orquestração",
    "EXTERNAL_SERVICE": "Serviço externo",
    "CONFIGURATION": "Configuração",
    "CONFIGURATION_REQUIRED": "Configuração necessária",
    "SERVICE_INCOMPLETE": "Serviço incompleto",
    "TECHNICAL_AI": "IA técnica",
    "TECHNICAL_AI_CONTRACT_VALIDATION_ERROR": "Erro de validação do contrato da IA técnica",
    "TECHNICAL_AI_UNAVAILABLE": "IA técnica indisponível",
    "AI_CONTRACT": "Contrato de IA",
    "AI_PROVIDER": "Provedor de IA",
    "IMPROVEMENT_CONFIGURATION_INVALID": "Configuração da análise profunda inválida",
    "IMPROVEMENT_INCOMPLETE": "Análise profunda incompleta",
    "REPROCESS_ELIGIBLE": "Elegível para reprocessamento",
    "SITE_URL_REQUIRED": "URL do site necessária",
    "SYNTHETIC_APDEX": "Apdex sintético",
    "EXPERIENCE_APDEX": "Apdex de experiência",
    "AUDIT": "Auditoria",
    "TARGET_SITE": "Site / propriedade auditada",
    "AUDITOR_INTERNAL": "Auditor RASAi",
    "EXTERNAL_PROVIDER": "Fornecedor / dependência externa",
    "ENVIRONMENTAL": "Ambiente / infraestrutura",
    "AI_REQUIREMENTS": "Requisitos da IA",
    "AI_RESULT_STALE": "Resultado de IA desatualizado",
    "AUDIT_INCOMPLETE_RECOVERABLE": "Auditoria incompleta, passível de retomada",
    "AUDIT_RESUME_PLAN_UNAVAILABLE": "Plano seguro de retomada indisponível",
    "CATALOG_ADDED_AFTER_INITIAL_COMPLETION": "Catálogo adicionado após a conclusão inicial",
    "CATALOG_EXTENSION": "Extensão de catálogo",
    "COMPETITIVE_AI_OUTPUT_INVALID": "Saída inválida da IA competitiva",
    "CONSOLIDATED_LONGITUDINAL_OUTPUT_INVALID": "Saída longitudinal consolidada inválida",
    "CONTENT_HTTP_STATUS": "Status HTTP do conteúdo",
    "CONTENT_REMEDIATION_EXECUTION_FAILURE": "Falha na execução da remediação de conteúdo",
    "CONTENT_UNSUPPORTED_MEDIA_TYPE": "Tipo de mídia do conteúdo não suportado",
    "CORE_RECOVERY": "Retomada do núcleo da auditoria",
    "CORE_RECOVERY_EXCEPTION": "Erro na retomada do núcleo da auditoria",
    "DIRECTED_ANALYSIS_OUTPUT_INVALID": "Saída inválida da Análise Direcionada",
    "EVIDENCE_COVERAGE": "Cobertura de evidências",
    "EVIDENCE_DEPENDENCY": "Dependência de evidências",
    "EVIDENCE_VERSION": "Versão da evidência",
    "EXECUTION_INTERRUPTED": "Execução interrompida",
    "IMPROVEMENT_CALL_WRAPPER_ERROR": "Erro na chamada da análise profunda",
    "IMPROVEMENT_OUTPUT_INVALID": "Saída inválida da análise profunda",
    "IMPROVEMENT_WALL_CLOCK_TIMEOUT": "Tempo total da análise profunda excedido",
    "INTERNAL": "Interno",
    "INVALID_JSON": "JSON inválido",
    "INVALID_JSON_OBJECT": "Objeto JSON inválido",
    "M20_UNEXPECTED_CONTRACT_ERROR": "Erro inesperado no contrato da análise",
    "M2_DISCOVERY_ACQUISITION_FAILED": "Falha na aquisição durante a descoberta",
    "NETWORK": "Rede",
    "PASSIVE_SECURITY": "Segurança passiva",
    "PASSIVE_SECURITY_EXTERNAL_COVERAGE_INCOMPLETE": "Cobertura externa de segurança passiva incompleta",
    "PASSIVE_SECURITY_INPUT_CHANGED": "Entradas da segurança passiva alteradas",
    "PERSISTED_RENDER_ARTIFACT_MISSING": "Artefato de renderização persistido ausente",
    "PERSISTED_EXTRACTION_SOURCE_MISSING": "Fonte de extração persistida ausente",
    "PERSISTED_EVIDENCE_MISSING": "Evidência persistida ausente",
    "PLANNED_WORK_NOT_EXECUTED": "Etapa planejada não executada",
    "RATE_LIMIT": "Limite de requisições",
    "RECOVERY": "Retomada",
    "RECOVERY_CONTRACT": "Contrato de retomada",
    "REFUSAL": "Recusa do provedor",
    "REPROCESS_PREREQUISITES_INCOMPLETE": "Pré-requisitos do reprocessamento ainda não concluídos",
    "REQUEST_REMEDIATION_OUTPUT_INVALID": "Saída inválida da remediação de requisições",
    "SEARCH_INTELLIGENCE_INCOMPLETE": "Inteligência de busca incompleta",
    "SEARCH_INTELLIGENCE_RUNTIME_ERROR": "Erro na execução da Inteligência de busca",
    "SEARCH_PROVIDER": "Provedor de busca",
    "SEARCH_SKIPPED_SOURCE_BLOCKER": "Fonte de busca ignorada por bloqueio técnico",
    "SEMANTIC_CONTEXT_NOT_EXECUTED": "Contexto semântico não executado",
    "SEMANTIC_CONTEXT_NOT_RECOVERABLE": "Contexto semântico não recuperável",
    "SERP_CONSOLE_RUNTIME_ERROR": "Erro na execução da coleta SERP",
    "SERP_DISABLED": "SERP desabilitada",
    "SERP_REQUESTED_DEPTH_INCOMPLETE": "Profundidade solicitada da SERP não concluída",
    "SERVICE_DISABLED": "Serviço desabilitado",
    "SERVICE_UNAVAILABLE": "Serviço indisponível",
    "SOURCE_BLOCKED": "Fonte bloqueada",
    "TECHNICAL_AI_PARTIAL_REQUIREMENTS": "Requisitos parciais da IA técnica",
    "TIMEOUTERROR": "Tempo limite excedido",
    "WALL_CLOCK_TIMEOUT": "Tempo total de execução excedido",
    "WEB_PERFORMANCE_RUN_UNAVAILABLE": "Execução de desempenho web indisponível",
    "WEB_PERFORMANCE_STATE_UNAVAILABLE": "Estado de desempenho web indisponível",
    "WORKER_RESULT_MISSING": "Resultado do executor ausente",
    "SEMANTIC_EFFECTIVE_RESULT_CHANGED": "Resultado semântico efetivo alterado",
    "ATTEMPT_ABANDONED": "Tentativa interrompida",
    "INTEGRITY": "Integridade",
    "RESULT_STALE": "Resultado desatualizado",
    "SEMANTIC_AI_NO_SUCCESSFUL_CAUSAL_ATTEMPT": "Nenhuma tentativa válida de IA semântica foi concluída para este contexto",
    "EXPLICIT": "Explícito",
    "FALLBACK": "Alternativa automática (fallback)",
    "HTTP_429": "HTTP 429 - limite de requisições",
    "HTTP_503": "HTTP 503 - serviço indisponível",
    "ACCESSIBILITY_CATEGORY_NOT_REQUESTED": "Categoria de acessibilidade não solicitada",
    "ACCESSIBILITY_SCORE_UNAVAILABLE": "Pontuação de acessibilidade indisponível",
    "BUSINESS_AUTHENTICATION_OR_PERMISSION": "Autenticação ou permissão do serviço",
    "BUSINESS_CREDIT_OR_BILLING": "Crédito ou faturamento do serviço",
    "BUSINESS_QUOTA_OR_PLAN": "Cota ou limite do plano do serviço",
    "SERP_PROVIDER_ERROR": "Erro do provedor de SERP",
    "TECHNICAL_PROVIDER_OR_RUNTIME": "Falha técnica do provedor ou da execução",
    "TECHNICAL_RATE_LIMIT": "Limite técnico de requisições atingido",
    "TECHNICAL_TIMEOUT": "Tempo limite técnico excedido",
    "TECHNICAL_TRANSIENT_PROVIDER": "Falha transitória do provedor",
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
    "PLAYWRIGHT_CHROMIUM": "Chromium via Playwright",
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
    return _PUBLIC_LABELS.get(value) or supplemental_public_label(value) or value


_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)", flags=re.DOTALL)
_PUBLIC_TOKEN_VALUES = tuple(
    sorted(set(_PUBLIC_LABELS) | set(SUPPLEMENTAL_PUBLIC_LABELS), key=len, reverse=True)
)
_PUBLIC_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])("
    + "|".join(re.escape(value) for value in _PUBLIC_TOKEN_VALUES)
    + r"|TECHNICAL_PREREQUISITE_BR_GEO_\d{3}_[A-Z0-9_]+"
    + r"|[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?![A-Za-z0-9_])"
)


def _public_token_replacement(match: re.Match[str]) -> str:
    value = match.group(1)
    # Do not translate a known word when it appears inside a canonical hyphenated
    # identifier such as CRAWLING-DISCOVERY-001 or SCORE-GEO-004.
    text = match.string
    left = match.start()
    right = match.end()
    while left > 0 and text[left - 1] in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-":
        left -= 1
    while right < len(text) and text[right] in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-":
        right += 1
    containing_token = text[left:right]
    if containing_token != value and is_traceability_identifier(containing_token):
        return value
    # Unknown limitation codes are intentionally retained only inside an explicit
    # technical/auditable wrapper. The surrounding prose tells the reader that
    # this is a canonical code, not user-facing business vocabulary.
    prefix = match.string[max(0, match.start() - 40):match.start()]
    if prefix.endswith("Limitação técnica registrada ("):
        return value
    # Priority labels intentionally retain the canonical Pn token in parentheses.
    # Keep repeated report-normalization passes idempotent instead of recursively
    # expanding e.g. P2 -> Alta (P2) -> Alta (Alta (P2)).
    if value in {"P0", "P1", "P2", "P3", "P4"} and match.start() > 0 and match.string[match.start() - 1] == "(":
        return value
    if value in _PUBLIC_LABELS:
        return _PUBLIC_LABELS[value]
    label = supplemental_public_label(value)
    return label if label is not None else safe_visible_fallback(value)


def _standalone_concept_label(text: str, *, page_name: str | None) -> str:
    stripped = text.strip()
    replacement = _STANDALONE_CONCEPT_LABELS.get(stripped.casefold())
    if replacement is None:
        return text
    # "Acessibilidade técnica" is ambiguous outside scoring/readiness surfaces;
    # do not rewrite accessibility-domain prose or headings globally.
    if stripped.casefold() == "acessibilidade técnica" and page_name == "accessibility.html":
        return text
    prefix = text[: len(text) - len(text.lstrip())]
    suffix = text[len(text.rstrip()):]
    return f"{prefix}{replacement}{suffix}"


def humanize_report_html(html: str, *, page_name: str | None = None) -> str:
    """Humanize visible report values without mutating persisted or code content.

    Known machine values are translated and timezone-aware ISO timestamps are
    converted to the default report presentation timezone (America/Sao_Paulo).
    ``code``, ``pre``, ``script`` and ``style`` remain untouched so technical
    identifiers, environment variables and canonical timestamps used as examples
    keep their original representation.
    """

    def isolated(match: re.Match[str]) -> str:
        value = match.group("value")
        if is_traceability_identifier(value):
            return match.group(0)
        if value in _PUBLIC_LABELS:
            label = _PUBLIC_LABELS[value]
        else:
            label = supplemental_public_label(value) or safe_visible_fallback(value)
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
        visible = localize_visible_timestamps(part)
        visible = visible.replace("\u2014", "-").replace("\u2013", "-")
        visible = _standalone_concept_label(visible, page_name=page_name)
        output.append(_PUBLIC_TOKEN_RE.sub(_public_token_replacement, visible))
    return _VISIBLE_VALUE_RE.sub(isolated, "".join(output))