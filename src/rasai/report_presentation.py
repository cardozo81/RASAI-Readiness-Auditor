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
    # Scoring and evaluation.
    "PASS": "Aprovado",
    "FAIL": "Não aprovado",
    "CONSOLIDATED": "Consolidado",
    "NOT_CONSOLIDATED": "Não consolidado",
    "PARTIAL": "Parcial",
    "NOT_APPLICABLE": "Não aplicável",
    "VALID": "Válido",
    "INVALID": "Inválido",
    # Severity and confidence.
    "CRITICAL": "Crítica",
    "HIGH": "Alta",
    "MEDIUM": "Média",
    "LOW": "Baixa",
    "INFO": "Informativa",
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
}

# Exact, isolated visible values only. Nested markup is deliberately excluded.
_VISIBLE_VALUE_RE = re.compile(
    r"(<(?P<tag>td|strong|span)\b[^>]*>)(?P<value>[A-Z][A-Z0-9_/-]*)(</(?P=tag)>)"
)


def public_label(value: str) -> str:
    """Return a user-facing label for a known machine value."""
    return _PUBLIC_LABELS.get(value, value)


def humanize_report_html(html: str, *, page_name: str | None = None) -> str:
    """Humanize only isolated primary values in generated HTML.

    ``page_name`` is accepted for future domain-specific refinements, but the
    current contract intentionally uses only conservative cross-report states.
    """
    del page_name

    def replace(match: re.Match[str]) -> str:
        value = match.group("value")
        label = _PUBLIC_LABELS.get(value)
        if label is None:
            return match.group(0)
        return f"{match.group(1)}{label}{match.group(4)}"

    return _VISIBLE_VALUE_RE.sub(replace, html)
