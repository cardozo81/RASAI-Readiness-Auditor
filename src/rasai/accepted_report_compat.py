"""Small compatibility glue for accepted catalog/report refinements."""
from __future__ import annotations

import json
from typing import Any, Mapping


def _discovery_title(action: Mapping[str, Any]) -> tuple[str, str]:
    code = str(action.get("diagnostic_code") or "").upper()
    if "ROBOTS-ABSENT" in code:
        return "Considerar publicar robots.txt explícito", "Oportunidade"
    if "SITEMAP-ABSENT" in code:
        return "Avaliar publicação e localização do sitemap", "Oportunidade"
    if "LLMS" in code and "ABSENT" in code:
        return "Avaliar llms.txt apenas como recurso opcional", "Oportunidade"
    return str(action.get("objective_pt") or "Orientação técnica de descoberta"), "Informativa"


def _jsonld_title(row: Mapping[str, Any]) -> str:
    existing = row.get("existing_types")
    try:
        parsed = json.loads(existing) if isinstance(existing, str) else existing
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = []
    return (
        "Aprimorar dados estruturados existentes"
        if isinstance(parsed, list) and parsed
        else "Considerar implementar dados estruturados aplicáveis"
    )


def install() -> None:
    from rasai import catalog_report_analysis as analysis
    from rasai.accepted_apdex_error_evidence import install as install_apdex_error_evidence
    from rasai.accepted_apdex_error_evidence_compat import install as install_apdex_error_evidence_compat

    install_apdex_error_evidence()
    install_apdex_error_evidence_compat()
    analysis._discovery_title = _discovery_title
    analysis._jsonld_title = _jsonld_title


__all__ = ["install"]
