"""Late human-label normalization for persisted product-language values."""
from __future__ import annotations

import sys
from typing import Any


_PT_LEVELS = {
    "CRÍTICO": "Crítico",
    "CRITICO": "Crítico",
    "CRÍTICA": "Crítica",
    "CRITICA": "Crítica",
    "MODERADA": "Moderada",
    "MODERADO": "Moderado",
    "ALTA": "Alta",
    "ALTO": "Alto",
    "BAIXA": "Baixa",
    "BAIXO": "Baixo",
    "INFORMATIVA": "Informativa",
    "INFORMATIVO": "Informativo",
}


def install_catalog_human_labels() -> None:
    """Keep technical enums out of primary report copy without changing stored data."""
    from rasai import catalog_report_presentation as presentation

    original = getattr(presentation._level_label, "_rasai_original", presentation._level_label)

    def human_level(value: Any) -> str:
        raw = str(value or "").strip()
        direct = _PT_LEVELS.get(raw.upper())
        if direct:
            return direct
        return original(value)

    human_level._rasai_original = original  # type: ignore[attr-defined]
    presentation._level_label = human_level

    # The report modules import presentation helpers with ``import *``.  Replace their
    # already-bound helper as well so every primary surface uses the same label policy.
    for name in (
        "rasai.catalog_report_metrics",
        "rasai.catalog_report_evidence",
        "rasai.catalog_report_analysis",
        "rasai.catalog_report_page",
        "rasai.catalog_report_governance",
        "rasai.catalog_report_integrations",
        "rasai.catalog_report_site",
    ):
        module = sys.modules.get(name)
        if module is not None:
            setattr(module, "_level_label", human_level)


__all__ = ["install_catalog_human_labels"]
