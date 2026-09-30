"""Secret-safe, machine-stable diagnosis for initial and RPR Chromium captures."""
from __future__ import annotations

import re
from typing import Any

# Stages are intentionally closed: exception messages, URLs and arbitrary page
# contents must never be copied into operational failure metadata.
_STAGES = frozenset({
    "BROWSER_STARTUP", "CONTEXT_PROFILE", "CONTEXT_CREATE", "NEW_PAGE",
    "INIT_SCRIPT", "CDP_SETUP", "EVENT_HANDLERS", "NAVIGATION", "SETTLE",
    "DOM_CAPTURE", "DOCUMENT_SOURCE", "RENDERED_DOM", "SCRIPT_RUNTIME",
    "COOKIE_RUNTIME", "SCREENSHOT", "DOM_OBSERVATIONS", "LAZY_PROBE",
    "METADATA", "UNCLASSIFIED",
})
_CLASS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

STAGE_LABELS = {
    "BROWSER_STARTUP": "Inicialização do navegador",
    "CONTEXT_PROFILE": "Configuração do perfil do navegador",
    "CONTEXT_CREATE": "Criação do contexto do navegador",
    "NEW_PAGE": "Abertura da página",
    "INIT_SCRIPT": "Instrumentação inicial",
    "CDP_SETUP": "Preparação da captura do documento",
    "EVENT_HANDLERS": "Instrumentação dos eventos",
    "NAVIGATION": "Navegação do documento principal",
    "SETTLE": "Estabilização da navegação",
    "DOM_CAPTURE": "Captura do HTML renderizado",
    "DOCUMENT_SOURCE": "Aquisição da origem do documento",
    "RENDERED_DOM": "Diagnóstico da árvore renderizada",
    "SCRIPT_RUNTIME": "Diagnóstico dos scripts",
    "COOKIE_RUNTIME": "Diagnóstico dos cookies",
    "SCREENSHOT": "Captura visual",
    "DOM_OBSERVATIONS": "Observações do documento",
    "LAZY_PROBE": "Verificação do conteúdo tardio",
    "METADATA": "Montagem dos metadados do navegador",
    "UNCLASSIFIED": "Etapa não identificada",
}


def render_failure_context(stage: Any, error: BaseException) -> dict[str, str]:
    raw_stage = str(stage or "").upper()
    safe_stage = raw_stage if raw_stage in _STAGES else "UNCLASSIFIED"
    raw_class = type(error).__name__
    safe_class = raw_class if _CLASS.fullmatch(raw_class) else "Exception"
    return {"stage": safe_stage, "exception_class": safe_class}


def render_failure_public_detail(context: Any) -> str:
    if not isinstance(context, dict):
        return "Falha na captura renderizada sem etapa diagnóstica disponível"
    stage = str(context.get("stage") or "UNCLASSIFIED").upper()
    label = STAGE_LABELS.get(stage, STAGE_LABELS["UNCLASSIFIED"])
    raw_class = str(context.get("exception_class") or "").strip()
    safe_class = raw_class if _CLASS.fullmatch(raw_class) else "Exception"
    return f"Falha na captura renderizada: {label} (classe técnica: {safe_class})"
