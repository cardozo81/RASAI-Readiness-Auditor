"""Canonical capture-context contract for one RASAi audit.

The contract separates facts by the smallest scope in which they can change. It is
presentation/persistence metadata only: it does not alter SCORE-GEO-004 weights,
result factors, Coverage, Confidence or consolidation formulas.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


CONTEXT_SCOPE_CONTRACT_VERSION = "CONTEXT-SCOPE-001"


class ContextScope(StrEnum):
    ORIGIN = "ORIGIN"
    URL = "URL"
    DEVICE_SNAPSHOT = "DEVICE_SNAPSHOT"
    PROFILE_MEASUREMENT = "PROFILE_MEASUREMENT"


@dataclass(frozen=True, slots=True)
class ScopeDefinition:
    scope: ContextScope
    meaning: str
    examples: tuple[str, ...]
    reacquisition_policy: str


SCOPE_DEFINITIONS: tuple[ScopeDefinition, ...] = (
    ScopeDefinition(
        ContextScope.ORIGIN,
        "Recurso ou fato compartilhado pela origem auditada.",
        ("robots.txt", "sitemaps", "llms.txt raiz", "políticas de crawler"),
        "Adquirir uma vez por auditoria/origin e reutilizar; não repetir por página ou dispositivo.",
    ),
    ScopeDefinition(
        ContextScope.URL,
        "Fato pertencente à URL antes de qualquer contexto de browser específico.",
        ("HTTP preflight", "HTML bruto preservado", "redirects HTTP", "headers da URL"),
        "Adquirir uma vez por URL, salvo mecanismo explícito de verificação de variância.",
    ),
    ScopeDefinition(
        ContextScope.DEVICE_SNAPSHOT,
        "Fato que pode mudar com browser, User-Agent, viewport, touch ou execução JavaScript.",
        ("DOM renderizado", "runtime JavaScript", "snapshot visual", "Lighthouse Mobile/Desktop"),
        "Capturar separadamente para cada dispositivo efetivamente selecionado.",
    ),
    ScopeDefinition(
        ContextScope.PROFILE_MEASUREMENT,
        "Medição sintética dependente de um perfil operacional controlado.",
        ("Synthetic Navigation Apdex", "Synthetic User Experience Apdex"),
        "Persistir perfil, device, CPU/network throttling e parâmetros junto do resultado.",
    ),
)


def evidence_scope(*, page_id: str | None, snapshot_id: str | None, device: Any = None) -> ContextScope:
    """Derive scope from the persisted Evidence identity without changing its schema."""
    if snapshot_id is not None or device is not None:
        return ContextScope.DEVICE_SNAPSHOT
    if page_id is not None:
        return ContextScope.URL
    return ContextScope.ORIGIN


def rule_execution_scope(*, page_id: str | None, snapshot_id: str | None, device: Any = None) -> ContextScope:
    if snapshot_id is not None or device is not None:
        return ContextScope.DEVICE_SNAPSHOT
    if page_id is not None:
        return ContextScope.URL
    return ContextScope.ORIGIN


def scope_label(scope: ContextScope | str) -> str:
    value = ContextScope(str(scope))
    return {
        ContextScope.ORIGIN: "Domínio / origem",
        ContextScope.URL: "URL",
        ContextScope.DEVICE_SNAPSHOT: "Dispositivo / snapshot",
        ContextScope.PROFILE_MEASUREMENT: "Perfil sintético",
    }[value]


def scope_contract_payload() -> dict[str, Any]:
    return {
        "version": CONTEXT_SCOPE_CONTRACT_VERSION,
        "scopes": [
            {
                "scope": item.scope.value,
                "meaning": item.meaning,
                "examples": list(item.examples),
                "reacquisition_policy": item.reacquisition_policy,
            }
            for item in SCOPE_DEFINITIONS
        ],
        "scoring_formula_changed": False,
    }
