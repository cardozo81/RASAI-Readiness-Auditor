"""Telemetry labels/cost attribution for grouped request remediation AI."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sqlite3
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


def _request_costs(database: Path) -> dict[str, Decimal]:
    if not database.is_file():
        return {}
    connection = sqlite3.connect(database)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_provider_attempts'"
        ).fetchone()
        if not exists:
            return {}
        rows = connection.execute(
            "SELECT cost_currency,SUM(estimated_cost) FROM ai_provider_attempts "
            "WHERE semantic_contract_version=? AND estimated_cost IS NOT NULL AND cost_currency IS NOT NULL "
            "GROUP BY cost_currency",
            (REQUEST_REMEDIATION_CONTRACT,),
        ).fetchall()
        return {str(currency): Decimal(str(amount)) for currency, amount in rows if currency is not None and amount is not None}
    finally:
        connection.close()


def _patch_cost_attribution() -> None:
    try:
        from rasai import documented_contract_reconciliation as reconciliation
    except Exception:
        return
    current = reconciliation._db_ai_costs
    if getattr(current, "_rasai_request_remediation_cost", False):
        return

    def db_ai_costs(database: Path) -> dict[str, dict[str, Decimal]]:
        totals = current(database)
        for currency, amount in _request_costs(database).items():
            bucket = totals.setdefault(currency, {})
            # The canonical Improvement cost wrapper classifies unknown semantic contracts
            # in the generic semantic bucket. Reclassify, do not double-count.
            generic = bucket.get("Análise semântica por IA", Decimal("0"))
            if generic:
                remaining = generic - amount
                if remaining > 0:
                    bucket["Análise semântica por IA"] = remaining
                else:
                    bucket.pop("Análise semântica por IA", None)
            bucket["Remediação agrupada de carregamento/execução por IA"] = (
                bucket.get("Remediação agrupada de carregamento/execução por IA", Decimal("0")) + amount
            )
        return totals

    db_ai_costs._rasai_request_remediation_cost = True
    db_ai_costs._rasai_original = current
    reconciliation._db_ai_costs = db_ai_costs


def _wrap_improvement_cost_installer() -> None:
    try:
        from rasai import improvement_intelligence_runtime as runtime
    except Exception:
        _patch_cost_attribution()
        return
    current = runtime._install_ai_cost_attribution
    if getattr(current, "_rasai_request_remediation_cost", False):
        return

    def install_ai_cost_attribution() -> None:
        current()
        _patch_cost_attribution()

    install_ai_cost_attribution._rasai_request_remediation_cost = True
    install_ai_cost_attribution._rasai_original = current
    runtime._install_ai_cost_attribution = install_ai_cost_attribution
    _patch_cost_attribution()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_report_labels()
    _wrap_improvement_cost_installer()
    _INSTALLED = True


__all__ = ["install"]
