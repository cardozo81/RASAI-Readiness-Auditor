"""Catalog telemetry labels for grouped request remediation AI."""
from __future__ import annotations

from typing import Any

from rasai.request_remediation_intelligence import REQUEST_REMEDIATION_CONTRACT

_INSTALLED = False


def _patch_report_labels() -> None:
    from rasai import catalog_report_integrations as integrations
    from rasai import catalog_report_model as model

    model._AI_PURPOSE_LABELS[REQUEST_REMEDIATION_CONTRACT] = (
        "Remediação agrupada de carregamento e execução",
        "CAT-09",
    )
    model._AI_EXCHANGE_PURPOSES["REQUEST_REMEDIATION"] = "Remediação agrupada de carregamento e execução"
    integrations._AI_PURPOSE_LABELS[REQUEST_REMEDIATION_CONTRACT] = model._AI_PURPOSE_LABELS[REQUEST_REMEDIATION_CONTRACT]
    integrations._AI_EXCHANGE_PURPOSES["REQUEST_REMEDIATION"] = model._AI_EXCHANGE_PURPOSES["REQUEST_REMEDIATION"]
    integrations._AI_USAGE_DETAILS[REQUEST_REMEDIATION_CONTRACT] = (
        "CAT-06/CAT-07 → CAT-09 · erros de carregamento e execução",
        "Grupos determinísticos de request/HTTP/console/JavaScript, com recorrência, origem, recursos, amostras e impactos observados já calculados pelo RASAi.",
        "Produzir uma solução técnica ponderada por grupo, com confiança, exemplo quando justificável e passos de revalidação; a IA não altera os fatos, agrupamentos nem o Apdex.",
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_report_labels()
    _INSTALLED = True


__all__ = ["install"]
