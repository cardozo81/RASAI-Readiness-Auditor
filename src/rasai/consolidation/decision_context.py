"""Contexto decisório derivado para apresentação do CONS-5.

Não recalcula SARI nem qualquer métrica. Organiza apenas valores persistidos e
resultados já produzidos pela consolidação/IA para orientar a leitura humana.
"""
from __future__ import annotations

from typing import Any, Mapping

from .models import ConsolidatedData


DECISION_CONTRACT = "CONSOLIDATED-DECISION-CONTEXT-002"

_TOPIC_LABELS = {
    "SEO": "SEO e descoberta",
    "GEO_AI_READINESS": "Busca e IA / Índice de Prontidão",
    "PERFORMANCE": "Desempenho e Core Web Vitals",
    "UX_APDEX": "Experiência / Apdex",
    "ACCESSIBILITY": "Acessibilidade",
    "INFRASTRUCTURE": "Engenharia e infraestrutura",
    "SECURITY": "Segurança passiva",
    "CONTENT_SEMANTICS": "Conteúdo e semântica",
}
_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_SUCCESS_CATALOG = {"SUCCESS", "COMPLETE", "COMPLETED", "CONCLUIDO", "CONCLUÍDO", "READY", "MEASURED"}
_NEUTRAL_CATALOG = {
    "NOT_REQUESTED", "NOT REQUESTED",
    "NAO_SOLICITADO", "NAO SOLICITADO",
    "NÃO_SOLICITADO", "NÃO SOLICITADO",
    "NOT_APPLICABLE", "NOT APPLICABLE",
    "NAO_APLICAVEL", "NAO APLICAVEL",
    "NÃO_APLICÁVEL", "NÃO APLICÁVEL",
}


def _number(value: Any) -> float | None:
    try:
        return None if value is None or isinstance(value, bool) else float(value)
    except (TypeError, ValueError):
        return None


def _sari_series(data: ConsolidatedData) -> list[dict[str, Any]]:
    rows = [
        row for row in data.score_history
        if str(row.get("dimension") or "").upper() == "OVERALL_READINESS"
    ]
    rows.sort(key=lambda row: (str(row.get("event_time") or ""), str(row.get("audit_id") or "")))
    return [
        {
            "audit_id": str(row.get("audit_id") or ""),
            "event_time": str(row.get("event_time") or ""),
            "value": _number(row.get("value")),
            "coverage": _number(row.get("coverage")),
            "confidence": str(row.get("confidence") or "UNKNOWN").upper(),
            "consolidation_status": str(row.get("consolidation_status") or "UNKNOWN").upper(),
            "scoring_version": str(row.get("scoring_version") or "UNKNOWN"),
        }
        for row in rows
    ]


def _sari_summary(series: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [item for item in series if item["value"] is not None]
    if not measured:
        return {
            "available": False,
            "method": "SARI-001 / SCORE-GEO-004",
            "series": series,
        }
    initial = measured[0]
    current = measured[-1]
    peak = max(measured, key=lambda item: float(item["value"]))
    delta = float(current["value"]) - float(initial["value"])
    return {
        "available": True,
        "method": "SARI-001 / SCORE-GEO-004",
        "initial": initial,
        "current": current,
        "peak": peak,
        "delta": delta,
        "delta_percent": (delta / abs(float(initial["value"])) * 100.0) if float(initial["value"]) else None,
        "series": series,
    }


def _catalog_matrix(bundle: Any) -> dict[str, Any]:
    initial = {
        str(item.get("catalog_id") or ""): item
        for item in bundle.catalog_snapshots[0].catalogs
        if isinstance(item, Mapping) and item.get("catalog_id")
    }
    final = {
        str(item.get("catalog_id") or ""): item
        for item in bundle.catalog_snapshots[-1].catalogs
        if isinstance(item, Mapping) and item.get("catalog_id")
    }
    ids = tuple(dict.fromkeys((*initial.keys(), *final.keys())))
    rows = []
    warnings = 0
    for catalog_id in ids:
        before = initial.get(catalog_id) or {}
        after = final.get(catalog_id) or {}
        before_status = str(before.get("status") or "SEM_DADO").upper()
        after_status = str(after.get("status") or "SEM_DADO").upper()
        comparable = (
            bool(before)
            and bool(after)
            and before_status not in _NEUTRAL_CATALOG
            and after_status not in _NEUTRAL_CATALOG
        )
        if not comparable or after_status not in _SUCCESS_CATALOG:
            warnings += 1
        rows.append({
            "catalog_id": catalog_id,
            "label": str(after.get("label") or before.get("label") or catalog_id),
            "initial_status": before_status,
            "final_status": after_status,
            "comparable": comparable,
        })
    return {
        "catalog_count": len(ids),
        "warnings": warnings,
        "rows": rows,
    }


def _axis(axis: str, label: str, state: str, tone: str, detail: str) -> dict[str, str]:
    return {
        "axis": axis,
        "label": label,
        "state": state,
        "tone": tone,
        "detail": detail,
    }


def _structural_matrix(data: ConsolidatedData, bundle: Any, run: Any, sari: Mapping[str, Any]) -> dict[str, Any]:
    governance = bundle.governance
    config = data.configuration_comparability
    catalog = _catalog_matrix(bundle)
    scoring_versions = sorted({
        str(item.get("scoring_version") or "UNKNOWN")
        for item in data.score_history
        if str(item.get("dimension") or "").upper() == "OVERALL_READINESS"
    })

    axes: list[dict[str, str]] = []
    source_conclusion = str(governance.get("conclusion_state") or "NON_CONCLUSIVE")
    if source_conclusion == "CONCLUSIVE":
        axes.append(_axis("SOURCE_HEALTH", "Saúde das auditorias fonte", "CONCLUÍDO", "good", "Todas as AUDs selecionadas possuem encerramento final comprovado, sem ressalva estrutural de conclusão."))
    elif source_conclusion == "CONCLUSIVE_WITH_LIMITATIONS":
        limited_count = int(governance.get("limited_audits") or 0)
        axes.append(_axis(
            "SOURCE_HEALTH",
            "Saúde das auditorias fonte",
            "CONCLUÍDO COM LIMITAÇÕES",
            "warn",
            f"{limited_count} AUD(s) possuem encerramento final e são elegíveis para consolidação, mas registram limitações não bloqueantes. Não há indicação automática de reprocessamento.",
        ))
    else:
        ids = ", ".join(governance.get("reprocess_recommended_audit_ids") or ()) or "consultar auditorias fonte"
        axes.append(_axis("SOURCE_HEALTH", "Saúde das auditorias fonte", "NÃO CONCLUSIVO", "bad", f"Há AUDs sem encerramento final comprovado. Reprocessar/verificar quando houver trabalho pendente: {ids}."))

    axes.append(_axis("IDENTITY", "Identidade longitudinal", "CONCLUÍDO", "good", "Mesma URL e mesmo dispositivo em toda a série selecionada."))

    if len(scoring_versions) == 1 and scoring_versions[0] == "SCORE-GEO-004":
        axes.append(_axis("METHODOLOGY", "Método de Pontuação de Prontidão", "CONCLUÍDO", "good", "Toda a série do Índice de Prontidão Search & IA usa o mesmo contrato técnico SCORE-GEO-004."))
    elif len(scoring_versions) == 1:
        axes.append(_axis("METHODOLOGY", "Método de Pontuação de Prontidão", "ATENÇÃO", "warn", f"A série usa o contrato técnico {scoring_versions[0]}; interpretar conforme o contrato persistido."))
    else:
        axes.append(_axis("METHODOLOGY", "Método de Pontuação de Prontidão", "NÃO COMPARÁVEL", "bad", "Há mais de um contrato técnico de pontuação na série."))

    pair_status = str(config.get("pair_status") or "INSUFFICIENT_DATA")
    if pair_status == "EXACT":
        axes.append(_axis("CONFIGURATION", "Configuração de execução", "CONCLUÍDO", "good", "Marco inicial e final pertencem à mesma série e usam configuração equivalente."))
    elif pair_status == "EQUIVALENT_WITHOUT_LINEAGE":
        axes.append(_axis("CONFIGURATION", "Configuração de execução", "COM RESSALVA", "info", "Configuração equivalente, mas sem linhagem explícita compartilhada."))
    elif pair_status == "PARTIAL":
        fields = ", ".join(config.get("altered_fields") or ())
        detail = (
            f"A configuração da mesma série mudou nos campos: {fields}. "
            "Diferenças temporais não devem ser tratadas automaticamente como efeito da URL."
            if fields
            else "A configuração da mesma série possui hashes diferentes; os campos alterados não foram materializados. "
                 "Diferenças temporais não devem ser tratadas automaticamente como efeito da URL."
        )
        axes.append(_axis("CONFIGURATION", "Configuração de execução", "CONTEXTUAL", "warn", detail))
    elif pair_status == "UNRELATED":
        axes.append(_axis(
            "CONFIGURATION",
            "Configuração de execução",
            "CONTEXTUAL",
            "warn",
            "Os marcos possuem configurações efetivas diferentes e não pertencem à mesma série de execução. "
            "Não há base suficiente para atribuir essas diferenças à URL nem para listar campos alterados entre as séries.",
        ))
    else:
        axes.append(_axis("CONFIGURATION", "Configuração de execução", "NÃO COMPROVADA", "warn", "Não há informação suficiente para comprovar equivalência de configuração."))

    if catalog["warnings"] == 0:
        axes.append(_axis("CATALOGS", "Cobertura dos catálogos", "CONCLUÍDO", "good", "Todos os catálogos encontrados possuem cobertura comparável e estado final adequado."))
    else:
        axes.append(_axis("CATALOGS", "Cobertura dos catálogos", "COM RESSALVAS", "warn", f"{catalog['warnings']} catálogo(s) possuem diferença de cobertura, estado parcial ou ausência em algum marco."))

    axes.append(_axis("EVIDENCE", "Evidência longitudinal", "CONCLUÍDO", "good", "Evidência integral é preservada localmente com SHA-256 no pacote CONS."))
    axes.append(_axis("INTEGRITY", "Integridade das fontes", "CONCLUÍDO", "good", "Cada audit.db selecionado possui SHA-256 calculado em modo somente leitura."))

    ai_status = str(getattr(run, "status", "NOT_REQUESTED") or "NOT_REQUESTED").upper()
    if ai_status == "COMPLETE":
        axes.append(_axis("AI", "Análise assistida por IA", "CONCLUÍDO", "good", "IA concluída com input/output sanitizados, custos e tentativas rastreáveis."))
    elif ai_status == "NOT_REQUESTED":
        axes.append(_axis("AI", "Análise assistida por IA", "NÃO SOLICITADA", "info", "Modo determinístico selecionado; IA não compõe requisito de encerramento."))
    else:
        axes.append(_axis("AI", "Análise assistida por IA", "INDISPONÍVEL", "warn", "A IA foi solicitada, mas não concluiu. Os dados determinísticos permanecem válidos e auditáveis."))

    axes.append(_axis("SECURITY", "Segurança da consolidação", "CONCLUÍDO", "good", "Leitura das fontes é read-only e a análise de segurança permanece passiva."))
    axes.append(_axis("PACKAGE", "Pacote auditável", "CONCLUÍDO", "good", "Artifacts de evidência, IA, execução e manifesto pertencem ao pacote CONS."))

    if any(item["tone"] == "bad" for item in axes):
        overall = "NÃO ENCERRADO"
        tone = "bad"
    elif any(item["tone"] == "warn" for item in axes):
        overall = "ENCERRADO COM RESSALVAS"
        tone = "warn"
    else:
        overall = "ENCERRADO"
        tone = "good"
    return {
        "overall": overall,
        "tone": tone,
        "axes": axes,
        "catalogs": catalog,
        "scoring_versions": scoring_versions,
        "sari_available": bool(sari.get("available")),
    }


def _confidence_label(value: float | None) -> str:
    if value is None:
        return "Não determinada"
    if value >= 0.95:
        return "Muito alta"
    if value >= 0.75:
        return "Alta"
    return "Limitada"


def _ai_reliability(data: ConsolidatedData, bundle: Any, run: Any, priorities: list[dict[str, Any]]) -> dict[str, Any]:
    ai_status = str(getattr(run, "status", "NOT_REQUESTED") or "NOT_REQUESTED").upper()
    if ai_status == "NOT_REQUESTED":
        return {
            "label": "Não aplicável",
            "tone": "info",
            "status": "NOT_REQUESTED",
            "declared_confidence": None,
            "declared_confidence_label": "Não aplicável",
            "topics_with_confidence": 0,
            "topic_count": 0,
            "topics_with_evidence": 0,
            "evidence_coverage": None,
            "source_conclusion": str(bundle.governance.get("conclusion_state") or "NON_CONCLUSIVE"),
            "configuration_pair_status": str(data.configuration_comparability.get("pair_status") or "INSUFFICIENT_DATA"),
            "reasons": ["Análise por IA não solicitada para este consolidado."],
            "interpretation": "A confiabilidade do consolidado é calculada separadamente e independe do uso de IA.",
        }
    if ai_status != "COMPLETE":
        return {
            "label": "Indisponível",
            "tone": "warn",
            "status": ai_status,
            "declared_confidence": None,
            "declared_confidence_label": "Indisponível",
            "topics_with_confidence": 0,
            "topic_count": len(priorities),
            "topics_with_evidence": 0,
            "evidence_coverage": None,
            "source_conclusion": str(bundle.governance.get("conclusion_state") or "NON_CONCLUSIVE"),
            "configuration_pair_status": str(data.configuration_comparability.get("pair_status") or "INSUFFICIENT_DATA"),
            "reasons": ["A IA foi solicitada, mas não concluiu; a consolidação determinística permanece independente."],
            "interpretation": "Este estado descreve somente a camada interpretativa por IA.",
        }
    confidences = [
        float(item["confidence"])
        for item in priorities
        if item.get("confidence") is not None
    ]
    average = (sum(confidences) / len(confidences)) if confidences else None
    evidence_covered = sum(1 for item in priorities if item.get("evidence_ids"))
    evidence_ratio = (evidence_covered / len(priorities)) if priorities else 0.0

    source_state = str(bundle.governance.get("conclusion_state") or "NON_CONCLUSIVE")
    pair_status = str(data.configuration_comparability.get("pair_status") or "INSUFFICIENT_DATA")

    declared_label = _confidence_label(average)
    reliability_rank = {"Muito alta": 3, "Alta": 2, "Limitada": 1, "Não determinada": 0}.get(declared_label, 0)
    reasons: list[str] = []

    if average is not None:
        reasons.append(
            f"Confiança média declarada pela IA nos tópicos: {average * 100:.0f}%."
        )
    else:
        reasons.append("A IA não forneceu confiança numérica para os tópicos.")

    if evidence_ratio >= 0.999 and priorities:
        reasons.append("Todos os tópicos priorizados citam evidências do consolidado.")
    else:
        reliability_rank = min(reliability_rank, 2)
        reasons.append(
            f"Cobertura de evidências nos tópicos: {evidence_covered}/{len(priorities)}."
        )

    if source_state == "NON_CONCLUSIVE":
        reliability_rank = min(reliability_rank, 1)
        reasons.append("Há AUD fonte não conclusiva; a interpretação deve permanecer contextual.")
    elif source_state == "CONCLUSIVE_WITH_LIMITATIONS":
        reliability_rank = min(reliability_rank, 2)
        reasons.append("As AUDs são finais, mas possuem limitações não bloqueantes.")
    else:
        reasons.append("As AUDs fonte possuem encerramento final comprovado.")

    if pair_status in {"PARTIAL", "UNRELATED"}:
        reliability_rank = min(reliability_rank, 1)
        reasons.append(
            "A comparabilidade de configuração não é uma repetição controlada equivalente; a confiabilidade da interpretação longitudinal é limitada e associações temporais não provam causalidade."
        )
    elif pair_status == "INSUFFICIENT_DATA":
        reliability_rank = 0
        reasons.append(
            "Não há dados suficientes para comprovar comparabilidade de configuração entre os marcos."
        )
    elif pair_status == "EQUIVALENT_WITHOUT_LINEAGE":
        reliability_rank = min(reliability_rank, 2)
        reasons.append("A configuração é equivalente, mas sem linhagem explícita compartilhada.")
    else:
        reasons.append("A configuração do marco inicial e final é comparável.")

    labels = {3: "Muito alta", 2: "Alta", 1: "Limitada", 0: "Não determinada"}
    label = labels[reliability_rank]
    return {
        "label": label,
        "tone": {"Muito alta": "good", "Alta": "good", "Limitada": "warn", "Não determinada": "bad"}[label],
        "declared_confidence": average,
        "declared_confidence_label": declared_label,
        "topics_with_confidence": len(confidences),
        "topic_count": len(priorities),
        "topics_with_evidence": evidence_covered,
        "evidence_coverage": evidence_ratio,
        "source_conclusion": source_state,
        "configuration_pair_status": pair_status,
        "reasons": reasons,
        "interpretation": (
            "Este grau representa a robustez da interpretação assistida por IA diante das evidências e da comparabilidade disponíveis. "
            "Não é garantia de causalidade, correção futura ou ganho de desempenho."
        ),
    }


def _priorities(run: Any) -> list[dict[str, Any]]:
    values = []
    for item in getattr(run, "topic_analyses", ()) or ():
        if not isinstance(item, Mapping):
            continue
        priority = str(item.get("priority") or "P3").upper()
        values.append({
            "priority": priority,
            "topic": str(item.get("topic") or ""),
            "topic_label": _TOPIC_LABELS.get(str(item.get("topic") or ""), str(item.get("topic") or "Tópico")),
            "assessment": str(item.get("assessment") or ""),
            "cause_analysis": str(item.get("cause_analysis") or item.get("assessment") or ""),
            "recommended_actions": [str(value) for value in item.get("recommended_actions", ()) if str(value).strip()],
            "confidence": _number(item.get("confidence")),
            "evidence_ids": [str(value) for value in item.get("evidence_ids", ()) if str(value).strip()],
        })
    values.sort(key=lambda item: (_PRIORITY_RANK.get(item["priority"], 9), item["topic_label"]))
    return values


def build_decision_context(data: ConsolidatedData, bundle: Any, run: Any) -> dict[str, Any]:
    sari = _sari_summary(_sari_series(data))
    governance = bundle.governance
    priorities = _priorities(run)
    ai_reliability = _ai_reliability(data, bundle, run, priorities)
    comparability = {
        "methodological": "COMPARABLE" if len({
            item["scoring_version"] for item in sari.get("series", [])
        }) <= 1 else "NOT_COMPARABLE",
        "configuration": data.configuration_comparability,
        "source_conclusion": governance.get("conclusion_state"),
    }
    return {
        "contract": DECISION_CONTRACT,
        "url": bundle.url,
        "device": bundle.device,
        "period_start": bundle.event_times[0],
        "period_end": bundle.event_times[-1],
        "audit_count": len(bundle.audit_ids),
        "interval_count": len(bundle.intervals),
        "managerial_summary": str(getattr(run, "summary", "") or ""),
        "managerial_summary_origin": "IA" if str(getattr(run, "status", "")).upper() == "COMPLETE" else "DADOS_DETERMINISTICOS",
        "sari": sari,
        "source_governance": governance,
        "comparability": comparability,
        "priorities": priorities,
        "ai_reliability": ai_reliability,
        "structural_matrix": _structural_matrix(data, bundle, run, sari),
    }


__all__ = ["DECISION_CONTRACT", "build_decision_context"]
