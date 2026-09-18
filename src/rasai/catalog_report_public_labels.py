"""Human-facing labels for internal RASAi values used by report-catalog."""
from __future__ import annotations
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
    "DETERMINISTIC-CORRELATIONAL-001": "Correlação determinística de evidências",
    "CONTENT_COMPARISON_DISABLED": "Comparação de conteúdo desabilitada",
    "CUSTOMER_URL_REQUIRED": "URL do site auditado necessária",
    "SERP_OBSERVATION_UNAVAILABLE": "Observação de SERP indisponível",
    "CLASSIFICATION_ONLY": "Somente classificação",
    "NOT_FOUND_WITHIN_DEPTH": "Não encontrado na profundidade coletada",
    "FOUND": "Encontrado na profundidade coletada",
    "NON_SCORING": "Não participa da pontuação",
    "BOUNDED_AI_RESOURCE_ASSESSMENT": "Avaliação de IA limitada e vinculada a evidências",
    "SHARED_ACQUISITION": "Aquisição compartilhada",
    "DETERMINISTIC_BASELINE": "Baseline determinístico",
    "UNKNOWN_ACTION": "Ação não classificada",
    "RATE_LIMITED": "Limite de requisições atingido",
    "REQUEST_FAILED": "Falha na requisição",
    "NETWORK_ERROR": "Erro de rede",
    "CONSOLE_ERROR": "Erro de console",
    "CORS": "Restrição CORS",
    "HTTP_ERROR": "Erro HTTP",
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
}

def public_label(value: Any) -> str | None:
    raw = str(value or "").strip()
    return PUBLIC_VALUE_LABELS.get(raw.upper()) if raw else None

__all__ = ["PUBLIC_VALUE_LABELS", "public_label"]
