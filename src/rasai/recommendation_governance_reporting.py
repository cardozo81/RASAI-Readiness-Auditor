"""CAT-09 projection for the deterministic recommendation-governance contract."""
from __future__ import annotations

from html import escape
import json
from typing import Any

from rasai.recommendation_governance import ACCEPTED, REJECTED, list_governance

_INSTALLED = False

_TARGET_LABELS = {
    "TARGET_SITE": "Site / propriedade auditada",
    "AUDITOR_INTERNAL": "Auditor RASAi",
    "EXTERNAL_PROVIDER": "Fornecedor / dependência externa",
    "ENVIRONMENTAL": "Ambiente / infraestrutura",
    "INFORMATIONAL": "Informativa / ownership não determinável",
}
_SOURCE_LABELS = {
    "DETERMINISTIC": "Remediação determinística",
    "CONTENT_AI": "Conteúdo assistido por IA",
    "JSONLD": "Dados estruturados",
    "DEEP_ANALYSIS": "CAT-08 · análise profunda",
    "REQUEST_REMEDIATION": "CAT-06/CAT-07 · requisições/runtime",
    "M24_DISCOVERY": "CAT-01 · descoberta",
}
_REASON_LABELS = {
    "AUDITOR_INTERNAL_NOT_CLIENT_ACTION": "Ação interna do auditor — excluída do plano do cliente",
    "UNKNOWN_OWNERSHIP_INFORMATIONAL_ONLY": "Ownership não determinável — mantida apenas como informação",
    "JSONLD_ABSENT_EXISTING_CONFLICT": "Conflito: a recomendação pressupõe JSON-LD existente, mas a evidência indica ausência",
    "JSONLD_ABSENT_WITHOUT_CREATION_PAYLOAD": "JSON-LD ausente sem payload de criação materializado",
    "UNCLASSIFIED_RECOMMENDATION_SOURCE": "Origem sem contrato de ownership reconhecido",
}


def _load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def governed_plan_html(database: Any, data: Any) -> str:
    from rasai import catalog_report_analysis as a

    accepted = list_governance(database, data.audit_id, decision=ACCEPTED)
    rejected = list_governance(database, data.audit_id, decision=REJECTED)
    if not accepted and not rejected:
        return (
            "<div class='notice warn'><strong>Governança de recomendações não materializada.</strong> "
            "O inventário técnico pode existir, mas não é apresentado como plano governado para o cliente.</div>"
        )

    accepted_rows = []
    accepted_modals = []
    for index, row in enumerate(accepted, 1):
        modal_id = f"governed-rec-{index}"
        evidence = _load(row.get("source_evidence_json"), [])
        accepted_rows.append((
            row.get("title") or "Recomendação",
            _TARGET_LABELS.get(str(row.get("target_class")), str(row.get("target_class") or "—")),
            _SOURCE_LABELS.get(str(row.get("source_kind")), str(row.get("source_kind") or "—")),
            row.get("source_catalog") or "—",
            a._modal_button(modal_id, "Ver governança"),
        ))
        body = a._kv((
            ("Decisão", "Aceita no plano governado"),
            ("Alvo da ação", _TARGET_LABELS.get(str(row.get("target_class")), row.get("target_class"))),
            ("Origem", _SOURCE_LABELS.get(str(row.get("source_kind")), row.get("source_kind"))),
            ("Catálogo/fonte", row.get("source_catalog") or "—"),
            ("Identificador da origem", row.get("source_id") or "—"),
            ("Racional de governança", row.get("rationale") or "—"),
            ("Evidências relacionadas", ", ".join(str(item) for item in evidence) if isinstance(evidence, list) and evidence else "—"),
            ("Contrato", row.get("contract_version") or "—"),
        ))
        accepted_modals.append(a._modal(modal_id, row.get("title") or "Recomendação", "Governança CAT-09", body))

    rejected_rows = []
    rejected_modals = []
    for index, row in enumerate(rejected, 1):
        modal_id = f"rejected-rec-{index}"
        evidence = _load(row.get("source_evidence_json"), [])
        reason = _REASON_LABELS.get(str(row.get("rejection_reason")), str(row.get("rejection_reason") or "Rejeitada pelo contrato"))
        rejected_rows.append((
            row.get("title") or "Recomendação",
            _TARGET_LABELS.get(str(row.get("target_class")), str(row.get("target_class") or "—")),
            reason,
            a._modal_button(modal_id, "Ver motivo"),
        ))
        body = a._kv((
            ("Decisão", "Rejeitada do plano do cliente"),
            ("Motivo", reason),
            ("Grupo de conflito", row.get("conflict_group") or "—"),
            ("Origem", _SOURCE_LABELS.get(str(row.get("source_kind")), row.get("source_kind"))),
            ("Racional", row.get("rationale") or "—"),
            ("Evidências relacionadas", ", ".join(str(item) for item in evidence) if isinstance(evidence, list) and evidence else "—"),
        ))
        rejected_modals.append(a._modal(modal_id, row.get("title") or "Recomendação rejeitada", "Item mantido apenas para auditoria da decisão", body))

    metrics = (
        "<div class='metric-grid'>"
        + a._metric("Ações aceitas", len(accepted))
        + a._metric("Itens rejeitados", len(rejected))
        + a._metric("Ações no ativo auditado", sum(1 for row in accepted if row.get("target_class") == "TARGET_SITE"))
        + a._metric("Dependências externas", sum(1 for row in accepted if row.get("target_class") == "EXTERNAL_PROVIDER"))
        + "</div>"
    )
    accepted_html = a._table(
        ("Ação governada", "Alvo", "Origem", "Catálogo", "Governança"),
        accepted_rows,
        empty="Nenhuma ação passou pelo contrato de governança.",
        sortable=bool(accepted_rows),
        page_size=10 if len(accepted_rows) > 10 else None,
    ) + "".join(accepted_modals)
    rejected_html = a._table(
        ("Item excluído do plano", "Classificação", "Motivo", "Detalhe"),
        rejected_rows,
        empty="Nenhum item foi rejeitado.",
        sortable=bool(rejected_rows),
        page_size=10 if len(rejected_rows) > 10 else None,
    ) + "".join(rejected_modals)
    return (
        "<div class='notice good'><strong>Plano governado:</strong> somente itens classificados e coerentes com a evidência "
        "entram nesta lista. Problemas internos do auditor e recomendações contraditórias permanecem auditáveis, mas não são "
        "tratados como ação do cliente.</div>"
        + metrics
        + "<div class='subsection'><h3>Plano de ação aceito</h3>" + accepted_html + "</div>"
        + "<details><summary>Itens rejeitados ou somente informativos</summary><div class='detail-body'>" + rejected_html + "</div></details>"
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import catalog_report_page as page

    current = page._remediation_html
    if getattr(current, "_rasai_recommendation_governance", False):
        _INSTALLED = True
        return

    def remediation_html(database: Any, data: Any) -> str:
        governed = governed_plan_html(database, data)
        raw = current(database, data)
        return (
            governed
            + "<details><summary>Inventário técnico de remediações de origem</summary><div class='detail-body'>"
            + "<div class='notice'><strong>Não é o plano governado do cliente.</strong> Esta seção preserva a projeção técnica "
              "das fontes para rastreabilidade, inclusive itens rejeitados acima.</div>"
            + raw
            + "</div></details>"
        )

    remediation_html._rasai_recommendation_governance = True
    remediation_html._rasai_original = current
    page._remediation_html = remediation_html
    _INSTALLED = True


__all__ = ["governed_plan_html", "install"]
