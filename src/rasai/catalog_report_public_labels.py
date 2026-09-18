"""Human-facing labels for internal RASAi values used by report-catalog."""
from __future__ import annotations
import re
from typing import Any

PUBLIC_VALUE_LABELS: dict[str, str] = {
    "DIRECT_PUBLIC_INDEX_API": "API pública de índice",
    "DIRECT_OFFICIAL_API": "API oficial da fonte",
    "NORMALIZED_EXPORT": "Exportação normalizada",
    "MANUAL_TRANSCRIPTION": "Transcrição manual",
    "CONTROLLED_PROTOCOL": "Protocolo controlado",
    "EXTERNAL_AUTOMATION": "Automação externa",
    "LIVE_RECOLLECTION": "Coleta ao vivo desta auditoria",
    "REUSED_EVIDENCE": "Evidência reutilizada",
    "REPLAY_SAFE": "Reutilizável sem nova coleta",
    "NON_LIVE_SOURCE": "Fonte sem coleta ao vivo",
    "OBSERVED_EXTERNAL_DATA": "Dados externos observados",
    "HISTORICAL_WEB_ARCHIVE": "Arquivo histórico da web",
    "MIXED": "Origem temporal mista",
    "LEGACY": "Origem legada",
    "DETERMINISTIC_CORRELATIONAL_001": "Correlação determinística de evidências",
    "CONTENT_COMPARISON_DISABLED": "Comparação de conteúdo desabilitada",
    "CUSTOMER_URL_REQUIRED": "URL do site auditado necessária",
    "CUSTOMER_CONTENT_UNAVAILABLE": "Conteúdo do site auditado indisponível",
    "NO_ELIGIBLE_COMPETITOR_CANDIDATES": "Nenhum candidato concorrente elegível",
    "COMPETITOR_CONTENT_UNAVAILABLE": "Conteúdo dos concorrentes indisponível",
    "PUBLIC_WEB_DESTINATION_BLOCKED": "Destino público bloqueado pela política de aquisição",
    "SERP_OBSERVATION_UNAVAILABLE": "Observação de SERP indisponível",
    "CLASSIFICATION_ONLY": "Somente classificação",
    "NOT_FOUND_WITHIN_DEPTH": "Não encontrado na profundidade coletada",
    "FOUND": "Encontrado na profundidade coletada",
    "ORGANIC_CANDIDATE": "Candidato orgânico",
    "PUBLIC_AUTHORITY": "Autoridade pública",
    "NON_SCORING": "Não participa da pontuação",
    "BOUNDED_AI_RESOURCE_ASSESSMENT": "Avaliação de IA limitada e vinculada a evidências",
    "SHARED_ACQUISITION": "Aquisição compartilhada",
    "DETERMINISTIC_BASELINE": "Baseline determinístico",
    "UNKNOWN_ACTION": "Ação não classificada",
    "RATE_LIMITED": "Limite de requisições atingido",
    "REQUEST_FAILED": "Falha na requisição",
    "NETWORK_ERROR": "Erro de rede",
    "DNS": "Erro de DNS",
    "CONNECTION": "Erro de conexão",
    "TIMEOUT": "Tempo limite excedido",
    "TLS": "Erro TLS",
    "PROTOCOL": "Erro de protocolo",
    "REDIRECT_LOOP": "Loop de redirecionamento",
    "TOO_MANY_REDIRECTS": "Redirecionamentos em excesso",
    "INVALID_REDIRECT": "Redirecionamento inválido",
    "CONSOLE_ERROR": "Erro de console",
    "CORS": "Restrição CORS",
    "HTTP_ERROR": "Erro HTTP",
    "AUTH_ERROR": "Erro de autenticação",
    "QUOTA_ERROR": "Cota excedida",
    "CREDIT_ERROR": "Crédito indisponível",
    "RATE_LIMIT_ERROR": "Limite de requisições atingido",
    "MODEL_ERROR": "Erro do modelo",
    "PERMISSION_ERROR": "Erro de permissão",
    "TIMEOUT_ERROR": "Tempo limite excedido",
    "SERVER_ERROR": "Erro do servidor",
    "BUSINESS_ERROR": "Erro de regra de negócio",
    "EMPTY_RESPONSE": "Resposta vazia",
    "INVALID_RESPONSE": "Resposta inválida",
    "UNKNOWN_PROVIDER_ERROR": "Erro não identificado do provedor",
    "QUARANTINED": "Em quarentena",
    "QUARANTINED_FOR_AUDIT": "Indisponível nesta auditoria",
    "ADD_CONTEXT": "Adicionar contexto",
    "EDIT_CONTENT": "Editar conteúdo",
    "ADD_OR_CORRECT": "Adicionar ou corrigir",
    "ADD_OR_RESTRUCTURE_ANSWER": "Adicionar ou reestruturar resposta",
    "CLARIFY_ENTITY_RELATIONSHIPS": "Esclarecer relações entre entidades",
    "CLOSE_INTENT_GAPS": "Fechar lacunas de intenção",
    "DISAMBIGUATE_ENTITY": "Desambiguar entidade",
    "DISCOVERY_ACCESS": "Acesso e descoberta",
    "TECHNICAL_ACCESSIBILITY": "Acessibilidade técnica",
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
    "OVERALL_READINESS": "SARI - Search & AI Readiness",
    "NOT_REQUESTED": "Não solicitado",
    "OBTAINED": "Obtido",
    "OBSERVED": "Observado",
    "INVALID": "Inválido",
    "BLOCKED": "Bloqueado",
    "UNKNOWN": "Não determinado",
    "PARTIAL_RETRYABLE": "Parcial - reprocessamento disponível",
    "PARTIAL_BLOCKED": "Parcial - há bloqueios",
    "EXPIRED_FOR_COMPLETION": "Expirado para conclusão",
    "CUSTOMER": "Site auditado",
    "COMPETITOR_CANDIDATE": "Candidato concorrente",
    "CONTENT_REMEDIATION": "Remediação de conteúdo",
    "IMPROVEMENT_INTELLIGENCE": "Análise profunda e melhorias",
    "COMPETITIVE_INTELLIGENCE": "Inteligência competitiva",
    "SEMANTIC_M7": "Análise semântica",
    "REQUEST_REMEDIATION": "Remediação de requisições",
    "M24_TECHNICAL_REMEDIATION": "Remediação técnica de rastreamento e descoberta",
    "INTERPRETED": "Interpretado",
    "NOT_DETERMINABLE": "Não determinável",
    "FINANCIAL_SECURITY": "Segurança financeira",
    "GENERAL": "Público geral",
    "NOT_EXPECTED": "Experiência prévia não esperada",
    "PRODUCT_SERVICE": "Produto ou serviço",
    "FIRST_PARTY": "Conteúdo próprio",
    "LOW": "Baixa",
    "MEDIUM": "Média",
    "HIGH": "Alta",
    "AI_INFERENCE": "Inferência de IA",
    "AUTO": "Automático",
    "NOT_CONSOLIDATED": "Não consolidado",
    "CONSOLIDATED": "Consolidado",
}

PUBLIC_PHRASE_LABELS: dict[str, str] = {
    "external organic result; business equivalence is not inferred": "Resultado orgânico externo; equivalência comercial não é inferida",
    "public-authority domain heuristic": "Heurística de domínio de autoridade pública",
}

def _key(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return re.sub(r"[^A-Z0-9]+", "_", raw).strip("_")

def public_label(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    phrase = PUBLIC_PHRASE_LABELS.get(raw.casefold())
    return phrase or PUBLIC_VALUE_LABELS.get(_key(raw))

_PUBLIC_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")

def public_text(value: Any) -> str:
    """Translate known internal tokens embedded in human-facing diagnostic text."""
    raw = str(value or "")
    if not raw:
        return raw
    return _PUBLIC_TOKEN_RE.sub(
        lambda match: public_label(match.group(0)) or match.group(0),
        raw,
    )

def public_contract_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "-"
    parts = raw.split(":")
    head = _key(parts[0])

    if head == "DIMENSION_NOT_APPLICABLE" and len(parts) >= 2:
        return f"Dimensão {public_label(parts[1]) or parts[1].replace('_',' ').title()} não aplicável"
    if head == "DIMENSION_MEASUREMENT_LIMITED" and len(parts) >= 2:
        return f"Medição limitada na dimensão {public_label(parts[1]) or parts[1].replace('_',' ').title()}"
    if head == "DIMENSION_NOT_CONSOLIDATED" and len(parts) >= 2:
        return f"Dimensão {public_label(parts[1]) or parts[1].replace('_',' ').title()} ainda não consolidada"
    if head == "CRITICAL_GATE" and len(parts) >= 3:
        subject = {
            "DISCOVERY": "descoberta",
            "INDEXABILITY": "indexabilidade",
            "EXTRACTION": "extração",
        }.get(_key(parts[1]), parts[1].replace("_"," ").casefold())
        state = {
            "WARNING": "atenção",
            "PASS": "aprovado",
            "FAIL": "não aprovado",
            "BLOCKED": "bloqueado",
            "UNKNOWN": "não determinado",
            "NOT_DETERMINABLE": "não determinável",
            "NOT_APPLICABLE": "não aplicável",
        }.get(_key(parts[2]), public_label(parts[2]) or parts[2].replace("_"," ").casefold())
        return f"Gate crítico de {subject}: {state}"
    if head == "READINESS_STATUS" and len(parts) >= 2:
        state = {
            "ATTENTION": "atenção",
            "READY": "pronto",
            "BLOCKED": "bloqueado",
            "UNKNOWN": "não determinado",
            "NOT_DETERMINABLE": "não determinável",
        }.get(_key(parts[1]), public_label(parts[1]) or parts[1].replace("_"," ").casefold())
        return f"Estado de prontidão: {state}"
    if head == "OVERALL_MEASUREMENT_BELOW_MINIMUM_GATE":
        return "Medição geral abaixo do mínimo exigido"
    if head == "OVERALL_MEASUREMENT_BELOW_CONSOLIDATION_GATE":
        return "Medição geral abaixo do mínimo para consolidação"
    if head == "OVERALL_AGGREGATION":
        return "Agregação geral: prontidão hierárquica ponderada - versão 1"
    if head == "DIMENSION_WEIGHTS":
        return "Pesos das dimensões: política SARI - versão 1"
    if head == "GROUP_WEIGHTS":
        return "Pesos dos grupos: política SARI - versão 1"
    if head == "CRITICAL_GATES":
        return "Gates críticos: política SARI - versão 1"
    if head == "MEASUREMENT_CONFIDENCE":
        return "Confiança da medição: cálculo ponderado - versão 1"
    if head == "EXTERNAL_CRAWL_CORROBORATION":
        rule = parts[1] if len(parts) > 1 else "BR-GEO-060"
        return f"Corroboração externa de crawl: somente impacto positivo, limite geral 0,45 - regra {rule}"
    if head == "EMPIRICAL_VALIDATION":
        return "Validação empírica: não participa da pontuação"

    return public_label(raw) or raw.replace("_", " ")

__all__ = ["PUBLIC_VALUE_LABELS", "PUBLIC_PHRASE_LABELS", "public_label", "public_text", "public_contract_label"]
