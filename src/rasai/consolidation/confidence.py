"""Confiabilidade determinística do relatório consolidado.

O indicador não usa IA e não altera SARI/SCORE-GEO. Ele expressa robustez do
conjunto longitudinal selecionado a partir de governança e comparabilidade já
calculadas pelo CONS.
"""
from __future__ import annotations

from typing import Any

from .models import ConsolidatedData


def evaluate_consolidation_confidence(data: ConsolidatedData, bundle: Any) -> dict[str, Any]:
    score = 100
    factors: list[dict[str, Any]] = []

    governance = bundle.governance if isinstance(getattr(bundle, "governance", None), dict) else {}
    conclusion = str(governance.get("conclusion_state") or "NON_CONCLUSIVE").upper()
    if conclusion == "CONCLUSIVE":
        factors.append({"factor": "auditorias_fonte", "state": "CONCLUSIVE", "impact": 0})
    elif conclusion == "CONCLUSIVE_WITH_LIMITATIONS":
        score -= 10
        factors.append({"factor": "auditorias_fonte", "state": conclusion, "impact": -10})
    else:
        score -= 35
        factors.append({"factor": "auditorias_fonte", "state": conclusion, "impact": -35})

    overlaps = [
        item for item in governance.get("temporal_revision_overlaps", ())
        if isinstance(item, dict)
    ]
    overlap_states = {str(item.get("state") or "").upper() for item in overlaps}
    if "LIVE_RECOLLECTION_AFTER_NEXT_OBSERVATION" in overlap_states:
        score -= 20
        factors.append({
            "factor": "revisao_temporal_pos_observacao",
            "state": "LIVE_RECOLLECTION_AFTER_NEXT_OBSERVATION",
            "impact": -20,
        })
    elif "UNKNOWN_REVISION_AFTER_NEXT_OBSERVATION" in overlap_states:
        score -= 10
        factors.append({
            "factor": "revisao_temporal_pos_observacao",
            "state": "UNKNOWN_REVISION_AFTER_NEXT_OBSERVATION",
            "impact": -10,
        })
    elif "REPLAY_SAFE_AFTER_NEXT_OBSERVATION" in overlap_states:
        factors.append({
            "factor": "revisao_temporal_pos_observacao",
            "state": "REPLAY_SAFE_AFTER_NEXT_OBSERVATION",
            "impact": 0,
        })
    else:
        factors.append({
            "factor": "revisao_temporal_pos_observacao",
            "state": "NONE",
            "impact": 0,
        })

    pair_status = str(data.configuration_comparability.get("pair_status") or "INSUFFICIENT_DATA").upper()
    pair_penalty = {
        "EXACT": 0,
        "EQUIVALENT_WITHOUT_LINEAGE": 8,
        "PARTIAL": 18,
        "UNRELATED": 30,
        "INSUFFICIENT_DATA": 25,
    }.get(pair_status, 20)
    score -= pair_penalty
    factors.append({
        "factor": "comparabilidade_configuracao",
        "state": pair_status,
        "impact": -pair_penalty,
    })

    scoring_versions = {
        str(item.get("scoring_version") or "UNKNOWN")
        for item in data.score_history
        if str(item.get("dimension") or "").upper() == "OVERALL_READINESS"
    }
    if len(scoring_versions) > 1:
        score -= 20
        factors.append({
            "factor": "metodologia_scoring",
            "state": "MULTIPLE_VERSIONS",
            "impact": -20,
        })
    elif not scoring_versions:
        score -= 10
        factors.append({
            "factor": "metodologia_scoring",
            "state": "NO_COMPARABLE_SARI",
            "impact": -10,
        })
    else:
        factors.append({
            "factor": "metodologia_scoring",
            "state": next(iter(scoring_versions)),
            "impact": 0,
        })

    limitation_count = len(tuple(data.limitations or ()))
    limitation_penalty = min(15, limitation_count * 3)
    score -= limitation_penalty
    factors.append({
        "factor": "limitacoes_registradas",
        "state": limitation_count,
        "impact": -limitation_penalty,
    })

    audit_count = len(tuple(getattr(bundle, "audit_ids", ()) or ()))
    factors.append({
        "factor": "pontos_temporais",
        "state": audit_count,
        "impact": 0,
    })

    score = max(0, min(100, int(round(score))))
    if score >= 90:
        label, tone = "Muito alta", "good"
    elif score >= 75:
        label, tone = "Alta", "good"
    elif score >= 55:
        label, tone = "Moderada", "warn"
    else:
        label, tone = "Limitada", "bad"

    return {
        "label": label,
        "tone": tone,
        "score": score,
        "method": "CONSOLIDATED-CONFIDENCE-001",
        "ai_independent": True,
        "audit_count": audit_count,
        "source_conclusion": conclusion,
        "configuration_pair_status": pair_status,
        "factors": factors,
        "interpretation": (
            "Grau determinístico de robustez do conjunto longitudinal. "
            "Não mede qualidade do site, não altera SARI/SCORE-GEO e não aumenta "
            "automaticamente quando a análise por IA é utilizada."
        ),
    }


__all__ = ["evaluate_consolidation_confidence"]
