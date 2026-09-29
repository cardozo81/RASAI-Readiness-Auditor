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
    "WAITING_FOR_DATA": "Aguardando dados",
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
    r"^(?:AUD|RPR|CONS|CONRUN)-[A-Z0-9-]+$|^BR-GEO-\d{3}$|^SCORE-GEO-\d+$|^[a-fA-F0-9]{40,64}$"
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
    return supplemental_public_label(raw) or (
        "Etapa técnica da auditoria" if _MACHINE_VALUE_RE.fullmatch(raw) else normalize_visible_text(raw)
    )


def scope_label(value: Any) -> str:
    raw = _raw(value)
    if not raw:
        return "Auditoria"
    label = supplemental_public_label(raw)
    if label is not None:
        return label
    if is_traceability_identifier(raw):
        return raw
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
    "CONSOLE_OPERATION_LABELS",
    "CONSOLE_STATUS_LABELS",
    "SUPPLEMENTAL_PUBLIC_LABELS",
    "component_label",
    "console_operation_label",
    "console_status_label",
    "diagnostic_label",
    "is_traceability_identifier",
    "normalize_visible_text",
    "safe_visible_fallback",
    "scope_label",
    "supplemental_public_label",
    "temporal_mode_label",
]
