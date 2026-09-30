"""Shared public-language contract for human-facing RASAi surfaces.

Internal enums and persisted values remain canonical. This module only controls
how operational values are projected to reports and interactive/human CLI output.
"""
from __future__ import annotations

import re
from typing import Any


SUPPLEMENTAL_PUBLIC_LABELS: dict[str, str] = {
    # Fulfillment/components/scopes.
    "CORE_AUDIT": "Auditoria principal",
    "HTTP_ACQUISITION": "Aquisição HTTP",
    "RENDER_CAPTURE": "Captura renderizada",
    "CONTENT_EXTRACTION": "Extração de conteúdo",
    "SEMANTIC_AI": "Análise semântica por IA",
    "TECHNICAL_AI": "Análise técnica por IA",
    "CONTENT_REMEDIATION_AI": "Remediação de conteúdo por IA",
    "ACCESSIBILITY_DATA": "Dados de acessibilidade",
    "STANDARDS_EXTERNAL": "Validação externa de padrões",
    "DIRECTED_ANALYSIS": "Análise direcionada",
    "SERP_OBSERVATION": "Observação de SERP",
    "SNAPSHOT_EVIDENCE": "Evidência da captura",
    "TECHNICAL_RESOURCE_EVIDENCE": "Evidência técnica de recurso",
    "AUDIT": "Auditoria",
    # Runtime/error/reason values identified by the public-surface audit.
    "HTTP_ACQUISITION_INCOMPLETE": "Aquisição HTTP incompleta",
    "TECHNICAL_EVIDENCE_INSUFFICIENT": "Evidência técnica insuficiente",
    "EXTRACTION_SOURCE_UNAVAILABLE": "Fonte de extração indisponível",
    "IMPROVEMENT_INTELLIGENCE_DISABLED": "Análise profunda por IA desabilitada",
    "IMPROVEMENT_INTELLIGENCE_UNAVAILABLE": "Análise profunda por IA indisponível",
    "EXTERNAL_WEB_PERFORMANCE_DISABLED": "Web Performance externo desabilitado",
    "NO_SUCCESSFUL_WEB_PERFORMANCE_CONTEXTS": "Nenhuma medição de Web Performance concluída com sucesso",
    "M24_AI_UNAVAILABLE": "IA técnica indisponível",
    "M24_AI_NO_SNAPSHOT_CONTEXT": "Contexto de captura indisponível para a IA técnica",
    "SOURCE_QUALITY_AI_UNAVAILABLE": "IA de qualidade da origem indisponível",
    "SOURCE_QUALITY_AI_NO_SNAPSHOT": "Captura indisponível para a IA de qualidade da origem",
    "AI_NOT_CONFIGURED_OR_UNSUPPORTED_FOR_SOURCE_QUALITY": "IA não configurada ou não compatível com a análise de qualidade da origem",
    "AI_NOT_REQUESTED": "IA não solicitada nesta execução",
    "SERP_PROVIDER_UNAVAILABLE": "Provedor de SERP indisponível",
    "COMPETITIVE_AI_DISABLED": "Análise competitiva por IA desabilitada",
    "COMPETITIVE_AI_REQUIRES_SERP_OBSERVATION": "Análise competitiva por IA aguarda uma observação de SERP",
    "SYNTHETIC_APDEX_DISABLED": "Apdex de navegação desabilitado",
    "SERVICE_NOT_ENABLED": "Serviço não habilitado",
    "NO_RESULT": "Execução sem resultado utilizável",
    "DEPENDENCY_CHANGED": "Dependência alterada",
    "MAIN_DOCUMENT_LOADING_FAILED": "Falha ao carregar o documento principal",
    "MAIN_DOCUMENT_NOT_CONFIRMED_FINISHED": "Carregamento do documento principal não concluído",
    "CAPTURE_FAILED": "Falha na captura",
    "SKIPPED_NOT_FINISHED": "Ignorado porque o carregamento não foi concluído",
    "COMMON_CRAWL_MAX_URLS_ZERO": "Coleta do Common Crawl desabilitada por limite de URLs igual a zero",
    "COMMON_CRAWL_PRESEAL_DATASET_MISSING": "Conjunto de dados do Common Crawl esperado não foi materializado",
    "PRE_SCORING_COLLECTION_STATE_NOT_FOUND": "Estado da coleta anterior à pontuação não encontrado",
    "NO_ACTIONABLE_PERSISTED_RECOMMENDATIONS": "Nenhuma recomendação persistida exige ação",
    "NO_ACTIONS": "Nenhuma ação aplicável",
    "NO_BASELINE_FACTUAL_CLAIM_SIGNAL": "Nenhum sinal factual explícito identificado na linha de base",
    "NO_EXPLICIT_QA_APPLICABILITY_SIGNAL": "Nenhum sinal explícito de aplicabilidade de perguntas e respostas",
    "NO_EXTERNAL_OBSERVABILITY_BEFORE_CORE_EVIDENCE": "Observabilidade externa aguarda evidência principal",
    "EXTERNAL_OBSERVABILITY_EVIDENCE_GATE_BLOCKED": "Observabilidade externa bloqueada até a evidência principal estar disponível",
    "EXCESSIVE_REDIRECT_CHAIN": "Cadeia de redirecionamentos excessiva",
    "EXPLICIT_NOINDEX": "Diretiva noindex explícita",
    "NON_CRAWLABLE_NAVIGATION_CONTROLS": "Controles de navegação sem destino rastreável",
    "LAZY_PROBE_UNAVAILABLE_NO_REFETCH": "Verificação de carregamento tardio indisponível sem nova coleta",
    "INVALID_JSON_RESPONSE": "Resposta JSON inválida",
    "RENDERED_UNAVAILABLE": "Conteúdo renderizado indisponível",
    "REUSED_EFFECTIVE_SUCCESS": "Resultado bem-sucedido anterior reutilizado",
    "RUNTIME_ERROR": "Erro de execução",
    "REPORT_REFRESH": "Atualização do relatório",
    "DEFAULT_OFF": "Desabilitado por padrão",
    "SMALL_GROUP_BELOW_NORMAL_MINIMUM": "Grupo amostral abaixo do mínimo normal",
    "QUERY_BODY_COVERAGE_LOWER": "Cobertura da consulta no conteúdo abaixo da referência observada",
    "QUERY_BODY_COVERAGE_LOWER_THAN_OBSERVED_LEADERS": "Cobertura da consulta no conteúdo abaixo das páginas observadas à frente",
    "TITLE_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS": "Alinhamento da consulta no título abaixo das páginas observadas à frente",
    "HEADING_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS": "Alinhamento da consulta nos títulos hierárquicos abaixo das páginas observadas à frente",
    "CONTENT_WORD_COUNT_LOWER_THAN_OBSERVED_LEADERS": "Volume textual abaixo das páginas observadas à frente",
    "STRUCTURED_DATA_TYPES_DIFFER_FROM_OBSERVED_LEADERS": "Tipos de dados estruturados diferem das páginas observadas à frente",
    "M2_DISCOVERY_ACQUISITION": "Aquisição para descoberta",
    "M23_COMPLETED": "Medição Apdex concluída",
    # Crawling/discovery and external-metric presentation values.
    "LIGHTHOUSE": "Lighthouse",
    "LIGHTHOUSE_ARTIFACT": "Artefato Lighthouse",
    "ARTIFACT_UNAVAILABLE": "Artefato indisponível",
    "CATEGORY_INCOMPLETE": "Categorias incompletas",
    "LIGHTHOUSE_RESULT_MISSING": "Resultado Lighthouse ausente",
    "EXTERNAL_METRICS_INTEGRITY_RECONCILED": "Integridade das métricas externas reconciliada",
    "EXTERNAL_METRICS_INTEGRITY_REFRESHED": "Integridade das métricas externas atualizada",
    "EXTERNAL_WEB_PERFORMANCE_UNAVAILABLE": "Web Performance externo indisponível",
    "NO_ERROR": "Sem erro",
    "ONE_OR_MORE_EXTERNAL_COMPONENTS_UNAVAILABLE": "Um ou mais componentes externos indisponíveis",
    "PAGESPEED_TRANSPORT_IS_NOT_LIGHTHOUSE_VALIDITY": "Resposta do PageSpeed não comprova validade do Lighthouse",
    "PERSISTED_EFFECTIVE_STATE": "Estado efetivo persistido",
    "RESULT_MISSING": "Resultado ausente",
    "ATOM_1": "Feed Atom 1.0",
    "RSS_2": "Feed RSS 2.0",
    "XML_INDEX": "Índice XML de sitemaps",
    "XML_URLSET": "Sitemap XML de URLs",
    "ATTENTION_REQUIRED": "Requer atenção",
    "COMMUNITY_PROPOSAL_NOT_WEB_STANDARD": "Proposta comunitária - não é padrão Web",
    "DECLARATION_PRESERVED_NOT_FETCHED": "Declaração preservada; recurso externo não coletado",
    "NO_ACQUIRED_SITEMAP": "Nenhum sitemap/feed adquirido",
    "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE": "Elegível para avaliação técnica limitada ao recurso",
    "BOUNDED_STATIC_FACTORS": "Fatores estáticos limitados ao recurso",
    "NENHUM": "Nenhum",
    "CAPTURADO": "Capturado",
    # Shared diagnostic classes/codes used by report and console surfaces.
    "NETWORK": "Erro de rede",
    "NETWORK_ERROR": "Erro de rede",
    "CONNECT_ERROR": "Erro de conexão",
    "TLS_ERROR": "Erro TLS",
    "SERVER_ERROR": "Erro do servidor",
    "EXTERNAL_SERVICE": "Serviço externo",
    "SERVICE_UNAVAILABLE": "Serviço indisponível",
    "TIMEOUT_ERROR": "Tempo limite excedido",
    "AUTH_ERROR": "Erro de autenticação",
    "INTERNAL": "Erro interno",
    "PARTIAL": "Parcial",
    "MAIN_CONTENT_UNAVAILABLE": "Conteúdo principal indisponível",
    "AI_WAITING_FOR_DATA": "IA aguardando pré-requisitos",
    "SEMANTIC_AI_RETRY_INCOMPLETE": "Nova tentativa da análise semântica por IA ficou incompleta",
    "AI_CONTRACT": "Contrato de IA",
    "AI_PROVIDER": "Provedor de IA",
    "SEARCH_PROVIDER": "Provedor de busca",
    "ORCHESTRATION": "Orquestração",
    "PREREQUISITE": "Pré-requisito",
    # Additional semantic values discovered by the repository-wide contract gate.
    "IMPROVEMENT_OUTPUT_PARTIAL": "Saída da análise profunda parcialmente válida",
    "IMPROVEMENT_REPAIR_INVALID": "Reparo da análise profunda inválido",
    "IMPROVEMENT_REPAIR_PARTIAL": "Reparo da análise profunda parcial",
    "SYNTHETIC_MEASUREMENT": "Medição sintética",
    "M21_RUNTIME_FAILURE": "Falha de execução do Web Performance",
    "M23_RUNTIME_FAILURE": "Falha de execução do Apdex de navegação",
    "NO_RENDERED_CONTEXTS": "Nenhum contexto renderizado disponível",
    "LOGICALLY_DELETED": "Excluída logicamente",
    "PHYSICAL_CLEANUP_PENDING": "Limpeza física pendente",
    "PREPARATION_FAILED": "Falha na preparação",
    "AUDIT_DELETION_CANCELLED": "Exclusão da auditoria cancelada",
    "CONTENT_REMEDIATION_RETRY_INCOMPLETE": "Nova tentativa da remediação de conteúdo ficou incompleta",
    "TECHNICAL_AI_RETRY_INCOMPLETE": "Nova tentativa da IA técnica ficou incompleta",
    "CTRL_C_INTERACTIVE_CONSOLE": "Interrupção pelo operador no console interativo",
    "SYNTHETIC_LIMITATION": "Limitação da medição sintética",
    "CONTENT_EXTRACTION_PREREQUISITE_BLOCKED": "Pré-requisito da extração de conteúdo bloqueado",
    "CORE_DERIVED": "Derivações principais",
    "M5_FOUNDATION": "Fundamentos técnicos",
    "CDP_RESPONSE_BODY_UNAVAILABLE": "Corpo da resposta indisponível via protocolo do navegador",
    "DECODED_DOCUMENT_EXCEEDS_CAPTURE_LIMIT": "Documento decodificado excede o limite de captura",
    "MAIN_DOCUMENT_EXCEEDS_CAPTURE_LIMIT": "Documento principal excede o limite de captura",
    "SAME_SESSION_LAZY_PROBE_FAILED": "Verificação de carregamento tardio falhou na mesma sessão",
    "SAME_SESSION_LAZY_PROBE_TIMEOUT": "Verificação de carregamento tardio excedeu o tempo limite na mesma sessão",
    "AI_NOT_REQUESTED_FOR_AUDIT": "IA não solicitada para esta auditoria",
    "AI_PROVIDER_NOT_RESOLVED": "Provedor de IA não resolvido",
    "COMMON_CRAWL_PARTIAL_PROVIDER_ERRORS": "Common Crawl com falhas parciais do provedor",
    "COMMON_CRAWL_PROVIDER_ERRORS": "Falha do provedor do Common Crawl",
    "CURRENT_DISCOVERY_GATE_BLOCKED": "Gate atual de descoberta bloqueado",
    "NO_COMMON_CRAWL_CAPTURE_OBSERVED": "Nenhuma captura do Common Crawl observada",
    "OBSERVED_URL_RATIO_BELOW_CORROBORATION_THRESHOLD": "Proporção de URLs observadas abaixo do limiar de corroboração",
    "NO_AUDIT_CLI_CONTEXT": "Contexto da auditoria não disponível na CLI",
    "AI_WAITING_FOR_PREREQUISITES": "IA aguardando pré-requisitos",
    "CONFIGURATION_INVALID": "Configuração inválida",
    "AI_PROVIDER_ATTEMPT_BUDGET_EXHAUSTED": "Limite de tentativas dos provedores de IA esgotado",
    "REUSED_GOVERNED_TASK": "Tarefa governada anterior reutilizada",
    "BROWSER_WORKER_RENDER_EXCEPTION": "Exceção no processo de renderização do navegador",
    "CANONICAL_TARGET_OUTSIDE_AUDITED_UNIVERSE": "Destino canonical fora do universo auditado",
    "CRAWLER_ACCESS_UNRESOLVED": "Acesso do crawler não resolvido",
    "RAW_OR_RENDERED_UNAVAILABLE": "Conteúdo original e renderizado indisponíveis",
    "RENDER_FAILED_BUT_RAW_FALLBACK_REMAINED_ANALYZABLE": "Renderização falhou, mas o conteúdo original permaneceu analisável",
    "RENDER_FAILURE_PREVENTED_CONTENT_RECOVERY": "Falha de renderização impediu a recuperação do conteúdo",
    "SEARCH_CRAWLER_BLOCKED": "Crawler de busca bloqueado",
    "SITEMAP_HTTP_ERROR": "Erro HTTP no sitemap",
    "SITEMAP_INVALID": "Sitemap inválido",
    "SITEMAP_NETWORK_ERROR": "Erro de rede ao acessar o sitemap",
    "CONTENT_LOST_AFTER_RENDER": "Conteúdo perdido após a renderização",
    "CONTENT_RECOVERED_BY_BOUNDED_SCROLL": "Conteúdo recuperado por rolagem limitada",
    "ESSENTIAL_CONTENT_NOT_IDENTIFIED": "Conteúdo essencial não identificado",
    "ESSENTIAL_CONTENT_NOT_RECOVERED_BY_BOUNDED_SCROLL": "Conteúdo essencial não recuperado por rolagem limitada",
    "BR_GEO_034_BLOCKS_TYPE_IDENTIFICATION": "BR-GEO-034 bloqueia a identificação do tipo",
    "SEMANTIC_PREREQUISITE_BLOCKED": "Pré-requisito semântico bloqueado",
    "STRUCTURED_DATA_ABSENT": "Dados estruturados ausentes",
    "STRUCTURED_DATA_NOT_INTERPRETABLE": "Dados estruturados não interpretáveis",
    "STRUCTURED_DATA_TYPE_NOT_IDENTIFIABLE": "Tipo dos dados estruturados não identificável",
    "TITLE_MISSING": "Título da página ausente",
    "MATERIAL_DEVICE_DIFFERENCE": "Diferença material entre dispositivos",
    "ALIGNED_WINDOW": "Janela temporal alinhada",
    "DATA_UNAVAILABLE": "Dados indisponíveis",
    "NON_OVERLAPPING": "Períodos sem sobreposição",
    "PARTIAL_OVERLAP": "Sobreposição parcial",
    "TEMPORAL_ASSOCIATION_ONLY": "Apenas associação temporal",
    "UNKNOWN_PERIOD": "Período não determinado",
    "POTENTIAL_CANNIBALIZATION": "Potencial canibalização observada",
    "LIVE_PAGE_CAPTURE_HOOK_NOT_REACHED": "Ponto de captura da página ao vivo não foi alcançado",
    "METRICS_CAPTURE_FAILED": "Falha na captura de métricas",
    "PLAYWRIGHT_METRICS_UNAVAILABLE": "Métricas do navegador indisponíveis",
    "UNEXPECTED_BROWSER_RESULT": "Resultado inesperado do navegador",
    "NO_CVE_FROM_OSV": "Nenhuma CVE retornada pelo OSV",
    "NO_VERSIONED_COMPONENT_IDENTIFIED": "Nenhum componente versionado identificado",
    "OPTIONAL_DEEP_TLS_NOT_ENABLED_IN_INITIAL_SCOPE": "Análise TLS aprofundada opcional não habilitada no escopo inicial",
    "PASSIVE_SECURITY_NOT_SELECTED": "Segurança passiva não selecionada",
    "URL_REPUTATION_REQUIRES_EXPLICIT_PRIVACY_AND_PROVIDER_POLICY": "Reputação de URL exige política explícita de privacidade e provedor",
    "RPR_GOVERNED_RESULT_REUSED": "Resultado governado de reprocessamento reutilizado",
    "FINDING_NOT_REOPENABLE": "Achado não pode ser reaberto",
    "RULE_EXECUTION_NOT_REOPENABLE": "Execução de regra não pode ser reaberta",
    "SUPPORTED_BY_PERSISTED_EVIDENCE": "Suportada pela evidência persistida",
    "NOT_FIXED": "Não corrigido",
    "NOT_VERIFIABLE": "Não verificável",
    "PARTIALLY_FIXED": "Parcialmente corrigido",
    "DERIVED_RECOMPUTE": "Recálculo de derivações",
    "STRUCTURED_DATA_ABSENT_NOT_UNIVERSAL_SARI_REQUIREMENT": "Dados estruturados ausentes; não são requisito universal do índice",
    "COMPETITIVE_CONTENT": "Conteúdo competitivo",
    "EXTERNAL_API": "API externa",
    "COMPETITIVE_CONTENT_PARTIAL": "Comparação de conteúdo competitivo parcial",
    "SEARCH_TARGET_UNAVAILABLE": "Alvo de busca indisponível",
    "AI_DISABLED_FOR_THIS_RPR": "IA desabilitada para este reprocessamento",
    "CONTENT_COMPARISON_REQUIRED": "Comparação de conteúdo necessária",
    "NO_CONSOLIDATED_COMPETITIVE_EVIDENCE": "Nenhuma evidência competitiva consolidada disponível",
    "SEALED_EVIDENCE_REQUIRED": "Evidência consolidada e selada necessária",
    "GSC_RETRY_NOT_MATERIALIZED": "Nova tentativa do Google Search Console não materializada",
    "IMPROVEMENT_RETRY_NOT_MATERIALIZED": "Nova tentativa da análise profunda não materializada",
    "SEARCH_CONFIGURATION_INVALID": "Configuração de busca inválida",
    "SEARCH_QUERIES_REQUIRED": "Termos de busca necessários",
    "NO_BASELINE_ATTRIBUTION_APPLICABILITY_SIGNAL": "Nenhum sinal de aplicabilidade de atribuição na linha de base",
    "NO_FRESHNESS_SIGNAL": "Nenhum sinal de atualização identificado",
    "NO_MATERIAL_BASELINE_INTENT_GAP_SET": "Nenhuma lacuna material de intenção na linha de base",
    "SEMANTIC_PREREQUISITE": "Pré-requisito semântico",
    "NO_DOMAIN_SERP_OBSERVATIONS": "Nenhuma observação SERP do domínio",
    "SERP_OBSERVATIONS_NOT_AVAILABLE": "Observações SERP indisponíveis",
    "EXPERIENCE_SESSION_WARM_REQUIRES_ISOLATED_ACQUISITION": "Sessão aquecida de experiência exige aquisição isolada",
    "INJECTED_GATEWAY_REQUIRES_ISOLATED_ACQUISITION": "Gateway injetado exige aquisição isolada",
    "ISOLATED_BY_CONFIGURATION": "Isolado pela configuração",
    # Console status values.
    "STARTING": "Iniciando",
    "FINALIZING": "Finalizando auditoria",
    "REPROCESSING": "Reprocessando auditoria",
    "REPROCESS_FAILED": "Falha no reprocessamento",
    "PRECHECK_FAILED": "Pré-verificação falhou",
    "START_FAILED": "Falha ao iniciar",
    "CONFIG_SOURCE_REJECTED": "Configuração de origem rejeitada",
    "AUDIT_DELETION_REJECTED": "Exclusão da auditoria rejeitada",
    "CONSOLIDATING": "Consolidando relatórios",
    "SYNTHETIC_UX_APDEX": "Medindo Apdex de experiência",
    "WEB_PERFORMANCE": "Coletando Web Performance",
    "SOURCE_BLOCKED": "Origem bloqueada",
    "PENDING": "Pendente",
    "WAITING_FOR_DATA": "Aguardando pré-requisitos",
    "NOT_CONFIGURED": "Não configurado",
    "REQUESTED_NOT_EXECUTED": "Solicitado, não executado",
    "FAILED_RETRYABLE": "Falha reprocessável",
    "FAILED_PERMANENT": "Falha permanente",
    "FAILED_FATAL": "Falha fatal",
    "BLOCKED": "Bloqueado",
    "DISABLED": "Desabilitado",
    "NOT_APPLICABLE": "Não aplicável",
    "SUCCESS": "Concluído",
    "FINAL": "Final",
    "PRELIMINARY": "Preliminar",
    "INCOMPLETE": "Incompleto",
    "UNAVAILABLE": "Indisponível",
    "UNKNOWN": "Não determinado",
    "OK": "Disponível",
    "NOT_TESTED": "Não testado",
}

# Finite vocabularies observed in typed CAT-04/CAT-10 evidence. Never whitelist
# unknown uppercase strings or arbitrary cookie identifiers globally.
SUPPLEMENTAL_PUBLIC_LABELS.update({
    "HTTP_SET_COOKIE": "Cabeçalho HTTP Set-Cookie",
    "DOCUMENT_COOKIE": "JavaScript (document.cookie)",
    "COOKIE_STORE": "API Cookie Store",
    "ANALYTICS": "Análise estatística",
    "NECESSARY": "Necessário para funcionamento",
    "ANALYZED": "Analisado",
    "SKIPPED_SIZE_LIMIT": "Corpo não analisado: limite de tamanho",
    "SKIPPED_TOTAL_BUDGET": "Corpo não analisado: orçamento de coleta atingido",
    "BODY_UNAVAILABLE": "Corpo do recurso indisponível",
    "NOT_FINISHED": "Carregamento ainda não concluído",
    "DYNAMIC_EVAL": "Execução dinâmica por eval()",
    "DYNAMIC_FUNCTION": "Criação dinâmica de função JavaScript",
    "DOCUMENT_WRITE": "Escrita de HTML via document.write()",
    "DYNAMIC_SCRIPT_INJECTION": "Inserção dinâmica de script",
    "COOKIE_API": "Acesso às APIs de cookies",
    "WEB_STORAGE": "Acesso ao armazenamento do navegador",
    "WEBSOCKET": "Uso de conexão WebSocket",
    "SERVICE_WORKER": "Registro de Service Worker",
    "WORKER": "Criação de Web Worker",
    "GEOLOCATION": "Acesso à API de geolocalização",
    "CLIPBOARD": "Acesso à área de transferência",
    "DYNAMIC_IMPORT": "Importação dinâmica JavaScript",
    "FINGERPRINTING_SURFACE": "Acesso a recursos potencialmente usados em identificação do navegador",
    "PUBLIC_IDENTIFIER": "Identificador público documentado",
    "PUBLIC_OPERATIONAL_KEY": "Chave operacional de exposição restrita",
    "SECRET_OR_CREDENTIAL": "Potencial segredo ou credencial (protegido)",
    "UNKNOWN_IDENTIFIER": "Identificador sem classificação pública",
    "GTM_CONTAINER_ID": "Identificador público de contêiner GTM",
    "GA_MEASUREMENT_ID": "Identificador público de medição Google Analytics",
    "OSV": "Base OSV de vulnerabilidades",
})

CONSOLE_OPERATION_LABELS: dict[str, str] = {
    "LOCAL:MENU": "Navegação no console",
    "LOCAL:DONE": "Auditoria concluída",
    "LOCAL:PRECHECK": "Validando pré-requisitos",
    "LOCAL:PRECHECK_OK": "Pré-requisitos validados",
    "LOCAL:ERROR": "Tratando falha da execução",
    "LOCAL:SUBPROCESS": "Iniciando processo de auditoria",
    "LOCAL:SOURCE_DIAGNOSTIC": "Diagnosticando acesso à origem",
    "LOCAL:FAIL_FAST": "Interrompendo etapa bloqueada",
    "LOCAL:REPORT_ENRICHMENT": "Finalizando relatórios",
    "LOCAL:SEMANTIC_RULES": "Executando regras semânticas",
    "LOCAL:SNAPSHOT_PERSIST": "Persistindo captura",
    "LOCAL:DOM_EXTRACTION": "Extraindo conteúdo do documento",
    "LOCAL:COLLECTION_TERMINAL": "Finalizando coleta",
    "LOCAL:EVIDENCE_SEALED": "Consolidando evidências",
    "LOCAL:BROWSER": "Preparando navegador",
    "LOCAL:AUD_REPROCESS": "Reprocessando auditoria",
    "LOCAL:AUD_REPROCESS_CANCELLED": "Reprocessamento cancelado",
    "LOCAL:AUD_REPROCESS_SKIPPED": "Reprocessamento não necessário",
    "LOCAL:AUD_CATALOG_EXTENSION": "Complementando catálogos da auditoria",
    "LOCAL:AUD_CONFIG_REUSE": "Reutilizando configuração da auditoria",
    "LOCAL:AUD_CONFIG_REUSE_CANCELLED": "Reutilização de configuração cancelada",
    "LOCAL:AUDIT_DELETE": "Excluindo auditoria",
    "LOCAL:AI_CONFIGURATION": "Configurando Inteligência Artificial",
    "LOCAL:CONFIG_RESTORED": "Configuração restaurada",
    "LOCAL:CONFIG_UPDATED": "Configuração atualizada",
    "LOCAL:RESTORE_SYSTEM_DEFAULTS": "Restaurando padrões do sistema",
    "LOCAL:EXECUTION_PROFILE_NONE": "Revisando perfil de execução",
    "LOCAL:PERSIST_USER_SECRET": "Salvando credencial do usuário",
    "LOCAL:SECRET_EDIT_CANCELLED": "Edição de credencial cancelada",
    "LOCAL:IMPROVEMENT_EDIT_CANCELLED": "Edição da análise profunda cancelada",
    "LOCAL:APDEX_EDIT_CANCELLED": "Edição do Apdex cancelada",
    "LOCAL:INTEGRATION_DIAGNOSTIC": "Diagnosticando integração",
    "LOCAL:INTEGRATION_WARNING_CANCELLED": "Operação de integração cancelada",
    "LOCAL:CONSOLIDATED_REPORT": "Gerando relatório consolidado",
    "LOCAL:CONSOLIDATION_ERROR": "Tratando falha de consolidação",
    "LOCAL:COST_EXPOSURE_PREVIEW": "Exibindo estimativa de consumo",
    "LOCAL:COST_FORECAST": "Calculando estimativa de consumo",
    "LOCAL:COST_DECLINED": "Execução cancelada após estimativa de consumo",
    "API:SERP": "Consultando provedor de SERP",
    "API:GOOGLE_SEARCH_CONSOLE": "Consultando Google Search Console",
    "API:PAGESPEED/CRUX": "Consultando PageSpeed / CrUX",
    "API:WEB_PERFORMANCE": "Consultando serviços de Web Performance",
    "BROWSER:CHROMIUM_RENDER": "Renderizando página no Chromium",
    "BROWSER:SYNTHETIC_UX_APDEX": "Medindo Apdex de experiência no navegador",
    "INTEGRATION:HTTP": "Coletando recurso HTTP",
    "INTEGRATION:COLLECTION": "Executando coleta externa",
    "INTEGRATION:EXTERNAL_OBSERVABILITY": "Coletando observabilidade externa",
    "INTEGRATION:SEARCH_INTELLIGENCE_LIMITATION": "Registrando limitação da inteligência de busca",
}


# Operações públicas descobertas por varredura estática do console. O valor interno
# permanece inalterado; somente a projeção humana usa estes rótulos.
CONSOLE_OPERATION_LABELS.update({
    "API:AI": "Consultando provedor de IA",
    "API:AUXILIARY": "Consultando serviço auxiliar",
    "API:COMMON_CRAWL": "Consultando Common Crawl",
    "API:SOURCE_QUALITY_AI": "Analisando qualidade da fonte por IA",
    "BROWSER:SYNTHETIC_APDEX": "Medindo Apdex de navegação no navegador",
    "LOCAL:APDEX_FAIL_OPEN": "Registrando limitação do Apdex de navegação",
    "LOCAL:APDEX_REPORT": "Gerando relatório do Apdex de navegação",
    "LOCAL:APDEX_SKIPPED": "Apdex de navegação não executado",
    "LOCAL:AUDIT_DELETE_CLEANUP": "Limpando arquivos da auditoria excluída",
    "LOCAL:CANCELLED": "Operação cancelada",
    "LOCAL:CONFIG_EDIT_CANCELLED": "Edição de configuração cancelada",
    "LOCAL:CONFIG_OVERRIDE_CLEARED": "Sobrescrita de configuração removida",
    "LOCAL:CONFIG_OVERRIDE_REMOVED": "Sobrescrita de configuração removida",
    "LOCAL:CONFIG_RESET_CANCELLED": "Restauração de configuração cancelada",
    "LOCAL:CONFIG_RESET_NOOP": "Configuração já está nos padrões",
    "LOCAL:CONFIG_RESET_SESSION": "Restaurando padrões na sessão",
    "LOCAL:CONFIG_RESET_SESSION_INI": "Restaurando padrões na sessão e no arquivo de configuração",
    "LOCAL:CONFIG_RESET_SESSION_USER": "Restaurando padrões na sessão e no perfil do usuário",
    "LOCAL:CONTENT_EXTRACTABILITY": "Avaliando renderização e extração",
    "LOCAL:CONTEXT_COMPARISON": "Comparando contextos de captura",
    "LOCAL:COST_CONFIRMED": "Execução confirmada após estimativa de consumo",
    "LOCAL:COST_CONFIRMED_NO_AI": "Execução sem IA confirmada após estimativa de consumo",
    "LOCAL:COST_EXPOSURE_CONFIRMED": "Estimativa de consumo confirmada",
    "LOCAL:COST_EXPOSURE_CONFIRMED_NO_AI": "Estimativa confirmada para execução sem IA",
    "LOCAL:COST_EXPOSURE_DECLINED": "Execução cancelada após estimativa de consumo",
    "LOCAL:DETERMINISTIC_RULES": "Aplicando regras determinísticas",
    "LOCAL:EVIDENCE_INTEGRITY": "Validando integridade das evidências",
    "LOCAL:EXECUTION_PROFILE_SELECTED": "Aplicando perfil de execução",
    "LOCAL:EXTERNAL_OBSERVABILITY_REPORTS": "Gerando relatórios de observabilidade externa",
    "LOCAL:EXTERNAL_OBSERVABILITY_SKIPPED": "Observabilidade externa não executada",
    "LOCAL:EXTRACTION": "Extraindo conteúdo",
    "LOCAL:FINAL_DERIVATION": "Calculando derivações finais",
    "LOCAL:FINDING_LINKAGE": "Relacionando achados e evidências",
    "LOCAL:IMPROVEMENT_FAIL_OPEN": "Registrando limitação da análise profunda",
    "LOCAL:JAVASCRIPT_SPA": "Analisando JavaScript e SPA",
    "LOCAL:OPEN_AUDIT_FOLDER": "Abrindo pasta da auditoria",
    "LOCAL:OPEN_ENV_DOCUMENTATION": "Abrindo documentação de configuração",
    "LOCAL:OPEN_REPORT": "Abrindo relatório",
    "LOCAL:OPEN_SELECTED_AUDIT_REPORT": "Abrindo relatório da auditoria selecionada",
    "LOCAL:PIPELINE": "Executando pipeline local",
    "LOCAL:RECOMMENDATIONS": "Gerando recomendações",
    "LOCAL:REMOVE_USER_SECRET": "Removendo credencial do usuário",
    "LOCAL:REPORT": "Gerando relatório",
    "LOCAL:REPORTING": "Gerando relatórios",
    "LOCAL:RULES/SCORE": "Aplicando regras e calculando pontuação",
    "LOCAL:SARI_SCORE": "Calculando Índice de Prontidão Search & IA",
    "LOCAL:SAVE_CONFIG": "Salvando configuração",
    "LOCAL:SYNTHETIC": "Executando medições sintéticas",
    "LOCAL:SYNTHETIC_UX_FAIL_OPEN": "Registrando limitação do Apdex de experiência",
    "LOCAL:TIMEZONE_EDIT_CANCELLED": "Edição do fuso horário cancelada",
})

COMPONENT_LABELS: dict[str, str] = {
    "CORE_AUDIT": "Auditoria principal",
    "HTTP_ACQUISITION": "Aquisição HTTP",
    "RENDER_CAPTURE": "Captura renderizada",
    "CONTENT_EXTRACTION": "Extração de conteúdo",
    "SEMANTIC_AI": "Análise semântica por IA",
    "TECHNICAL_AI": "Análise técnica por IA",
    "CONTENT_REMEDIATION_AI": "Remediação de conteúdo por IA",
    "ACCESSIBILITY_DATA": "Dados de acessibilidade",
    "STANDARDS_EXTERNAL": "Validação externa de padrões",
    "DIRECTED_ANALYSIS": "Análise direcionada",
    "SEARCH_INTELLIGENCE": "Inteligência de busca / SERP",
    "WEB_PERFORMANCE": "Web Performance",
    "SYNTHETIC_APDEX": "Apdex de navegação",
    "EXPERIENCE_APDEX": "Apdex de experiência",
    "IMPROVEMENT_INTELLIGENCE": "Análise profunda por IA",
}

CONSOLE_STATUS_LABELS: dict[str, str] = {
    **{key: value for key, value in SUPPLEMENTAL_PUBLIC_LABELS.items() if key in {
        "STARTING", "FINALIZING", "REPROCESSING", "REPROCESS_FAILED", "PRECHECK_FAILED",
        "START_FAILED", "CONFIG_SOURCE_REJECTED", "AUDIT_DELETION_REJECTED", "CONSOLIDATING",
        "SYNTHETIC_UX_APDEX", "WEB_PERFORMANCE", "SOURCE_BLOCKED",
    }},
    "CREATED": "Criado",
    "INITIALIZING": "Inicializando",
    "DISCOVERING": "Descobrindo URLs",
    "ACQUIRING": "Coletando páginas",
    "ANALYZING": "Analisando",
    "COMPARING": "Comparando",
    "SCORING": "Calculando pontuação",
    "RECOMMENDING": "Gerando recomendações",
    "REPORTING": "Gerando relatórios",
    "PROCESSING": "Em processamento",
    "RUNNING": "Em execução",
    "READY": "Disponível",
    "COMPLETE": "Concluído",
    "COMPLETED": "Concluído",
    "COMPLETE_WITH_LIMITATIONS": "Concluído com limitações",
    "PARTIAL_RETRYABLE": "Parcial - reprocessamento disponível",
    "PARTIAL_BLOCKED": "Parcial - há bloqueios",
    "FAILED": "Falhou",
    "ERROR": "Erro",
    "WAITING_FOR_DATA": "Aguardando pré-requisitos",
    "NOT_CONFIGURED": "Não configurado",
    "REQUESTED_NOT_EXECUTED": "Solicitado, não executado",
    "FAILED_RETRYABLE": "Falha reprocessável",
    "FAILED_PERMANENT": "Falha permanente",
    "FAILED_FATAL": "Falha fatal",
    "BLOCKED": "Bloqueado",
    "DISABLED": "Desabilitado",
    "NOT_APPLICABLE": "Não aplicável",
    "SUCCESS": "Concluído",
    "FINAL": "Final",
    "PRELIMINARY": "Preliminar",
    "INCOMPLETE": "Incompleto",
    "UNAVAILABLE": "Indisponível",
    "UNKNOWN": "Não determinado",
}

_STATE_LABELS_LOWER: dict[str, str] = {
    "PASS": "aprovado",
    "FAIL": "não aprovado",
    "WARNING": "atenção",
    "UNKNOWN": "não determinado",
    "NOT_DETERMINABLE": "não determinável",
    "NOT_APPLICABLE": "não aplicável",
    "MISSING": "ausente",
    "ABSENT": "ausente",
    "UNAVAILABLE": "indisponível",
    "BLOCKED": "bloqueado",
    "SUCCESS": "concluído",
}

_TECHNICAL_PREREQUISITE_RE = re.compile(
    r"^TECHNICAL_PREREQUISITE_BR_GEO_(\d{3})_([A-Z0-9_]+)$",
    re.IGNORECASE,
)
_MACHINE_VALUE_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:(?:[_:][A-Z0-9][A-Z0-9_./:-]*))?$")
_TRACEABILITY_RE = re.compile(
    r"^(?:AUD|RPR|CONS|CONRUN)-[A-Z0-9-]+$"
    r"|^BR-GEO-\d{3}$|^SCORE-GEO-\d+$"
    r"|^[A-Z]{2,12}(?:-[A-Z0-9]+)+$"
    r"|^[a-fA-F0-9]{40,64}$"
)


def _raw(value: Any) -> str:
    return str(value or "").strip()


def normalize_visible_text(value: Any) -> str:
    return _raw(value).replace("\u2014", "-").replace("\u2013", "-")


def is_traceability_identifier(value: Any) -> bool:
    raw = _raw(value)
    if not raw:
        return False
    if _TRACEABILITY_RE.fullmatch(raw):
        return True
    if raw.startswith("RASAI_"):
        return True
    if re.fullmatch(r"[A-Z][A-Z0-9_]+_V\d+", raw):
        return True
    return False


def safe_visible_fallback(value: Any) -> str:
    """Prevent an unmapped machine enum from becoming primary public copy."""
    raw = _raw(value)
    if not raw:
        return "-"
    if is_traceability_identifier(raw):
        return raw
    if _MACHINE_VALUE_RE.fullmatch(raw):
        return "Condição técnica não catalogada"
    return normalize_visible_text(raw)


def supplemental_public_label(value: Any) -> str | None:
    raw = _raw(value)
    if not raw:
        return None
    key = re.sub(r"[^A-Z0-9]+", "_", raw.upper()).strip("_")
    direct = SUPPLEMENTAL_PUBLIC_LABELS.get(key)
    if direct is not None:
        return direct
    match = _TECHNICAL_PREREQUISITE_RE.fullmatch(raw)
    if match:
        state = _STATE_LABELS_LOWER.get(match.group(2).upper())
        if state is None:
            state = "estado técnico não determinado"
        return f"Pré-requisito técnico BR-GEO-{match.group(1)}: {state}"
    return None


def console_status_label(value: Any) -> str:
    raw = _raw(value)
    if not raw:
        return "Não determinado"
    key = re.sub(r"[^A-Z0-9]+", "_", raw.upper()).strip("_")
    return CONSOLE_STATUS_LABELS.get(key) or supplemental_public_label(raw) or (
        "Estado operacional" if _MACHINE_VALUE_RE.fullmatch(raw) else normalize_visible_text(raw)
    )


def console_operation_label(value: Any) -> str:
    raw = _raw(value)
    if not raw:
        return "Operação local"
    if raw in CONSOLE_OPERATION_LABELS:
        return CONSOLE_OPERATION_LABELS[raw]
    upper = raw.upper()
    if upper.startswith("LOCAL:"):
        return "Operação local"
    if upper.startswith("API:"):
        return "Consulta a serviço externo"
    if upper.startswith("BROWSER:"):
        return "Automação de navegador"
    if upper.startswith("INTEGRATION:"):
        return "Integração externa"
    return normalize_visible_text(raw)


def component_label(value: Any) -> str:
    raw = _raw(value)
    if not raw:
        return "Etapa da auditoria"
    key = re.sub(r"[^A-Z0-9]+", "_", raw.upper()).strip("_")
    return COMPONENT_LABELS.get(key) or supplemental_public_label(raw) or (
        "Etapa técnica da auditoria" if _MACHINE_VALUE_RE.fullmatch(raw) else normalize_visible_text(raw)
    )


def scope_label(value: Any) -> str:
    raw = _raw(value)
    if not raw:
        return "Auditoria"
    if raw.upper() == "AUDIT":
        return "Auditoria"
    if raw.upper().startswith("PLANNED:"):
        parts = raw.split(":")
        details: list[str] = ["Planejado"]
        for part in parts[1:]:
            upper = part.upper()
            if upper == "MOBILE":
                details.append("Mobile")
            elif upper == "DESKTOP":
                details.append("Desktop")
            elif upper == "TABLET":
                details.append("Tablet")
            else:
                details.append(part)
        return " - ".join(details)
    if is_traceability_identifier(raw):
        return raw
    label = supplemental_public_label(raw)
    if label is not None:
        return label
    if _MACHINE_VALUE_RE.fullmatch(raw):
        return "Escopo técnico"
    return normalize_visible_text(raw)


def diagnostic_label(value: Any) -> str:
    raw = _raw(value)
    if not raw:
        return "-"
    label = supplemental_public_label(raw)
    if label is not None:
        return label
    if is_traceability_identifier(raw):
        return raw
    if _MACHINE_VALUE_RE.fullmatch(raw):
        return "Diagnóstico técnico registrado"
    return normalize_visible_text(raw)


def diagnostic_text(value: Any) -> str:
    """Humanize known machine tokens embedded in a persisted diagnostic message."""
    raw = normalize_visible_text(value)
    if not raw:
        return ""
    if re.fullmatch(r"[A-Z][A-Z0-9_]+(?::[A-Z][A-Z0-9_]+)+", raw):
        labels: list[str] = []
        for token in raw.split(":"):
            label = supplemental_public_label(token)
            if label is None:
                key = re.sub(r"[^A-Z0-9]+", "_", token.upper()).strip("_")
                label = CONSOLE_STATUS_LABELS.get(key)
            labels.append(label or safe_visible_fallback(token))
        return " - ".join(labels)

    token_re = re.compile(r"(?<![A-Za-z0-9_])([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)(?![A-Za-z0-9_])")
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        label = supplemental_public_label(token)
        if label is None:
            key = re.sub(r"[^A-Z0-9]+", "_", token.upper()).strip("_")
            label = CONSOLE_STATUS_LABELS.get(key)
        return label or token

    return token_re.sub(replace, raw)


def temporal_mode_label(value: Any) -> str:
    raw = _raw(value)
    labels = {
        "REPLAY_SAFE": "Reutiliza evidências válidas",
        "LIVE_RECOLLECTION": "Nova coleta necessária",
        "LIVE_ONLY": "Execução ao vivo",
        "PERSISTED_REUSE": "Reutiliza resultado persistido",
    }
    key = re.sub(r"[^A-Z0-9]+", "_", raw.upper()).strip("_")
    return labels.get(key) or ("Modo de recuperação" if _MACHINE_VALUE_RE.fullmatch(raw) else normalize_visible_text(raw))


__all__ = [
    "COMPONENT_LABELS",
    "CONSOLE_OPERATION_LABELS",
    "CONSOLE_STATUS_LABELS",
    "SUPPLEMENTAL_PUBLIC_LABELS",
    "component_label",
    "console_operation_label",
    "console_status_label",
    "diagnostic_label",
    "diagnostic_text",
    "is_traceability_identifier",
    "normalize_visible_text",
    "safe_visible_fallback",
    "scope_label",
    "supplemental_public_label",
    "temporal_mode_label",
]
