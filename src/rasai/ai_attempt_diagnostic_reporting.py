"""Presentation refinements for persisted AI attempt diagnostics.

The persistence model remains canonical. This module only makes operation family and
sanitized local contract detail visible in the existing AI usage/report projections.
"""
from __future__ import annotations

from html import escape
from typing import Any

_INSTALLED = False


def _value(row: Any, key: str, default: Any = None) -> Any:
    try:
        keys = row.keys()
    except AttributeError:
        keys = row
    try:
        return row[key] if key in keys else default
    except (KeyError, TypeError):
        return default


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import m18_reporting

    original_operation = m18_reporting._operation
    if not bool(getattr(original_operation, "_rasai_attempt_family_label", False)):
        def operation(row: Any) -> str:
            contract = str(_value(row, "semantic_contract_version", "") or "")
            if contract.startswith("M24-"):
                return "Remediação técnica"
            try:
                from rasai.improvement_intelligence import CONTRACT_VERSION
                if contract == CONTRACT_VERSION:
                    return "Análise profunda e melhorias"
            except ImportError:
                pass
            return original_operation(row)

        operation._rasai_attempt_family_label = True
        operation._rasai_original = original_operation
        m18_reporting._operation = operation

    original_failure_detail = m18_reporting._failure_detail
    if not bool(getattr(original_failure_detail, "_rasai_contract_error_detail", False)):
        def failure_detail(attempts: list[Any]) -> str:
            base = original_failure_detail(attempts)
            rows: list[str] = []
            for row in attempts:
                if str(_value(row, "status", "") or "").upper() == "SUCCESS":
                    continue
                detail = str(_value(row, "error_detail", "") or "").strip()
                if not detail:
                    continue
                provider = str(_value(row, "provider", "-") or "-")
                model = str(_value(row, "model", "-") or "-")
                error_type = str(_value(row, "error_type", "-") or "-")
                error_code = str(_value(row, "error_code", "-") or "-")
                rows.append(
                    "<li><strong>"
                    + escape(f"{provider}/{model}")
                    + "</strong> · "
                    + escape(f"{error_type} · {error_code} · {detail[:1000]}")
                    + "</li>"
                )
                if len(rows) >= 12:
                    break
            if not rows:
                return base
            return (
                base
                + "<div class='m18-note ai-contract-detail'><strong>Detalhe sanitizado da validação local:</strong>"
                + "<ul>"
                + "".join(rows)
                + "</ul><p>O provider respondeu; este detalhe descreve por que a resposta foi rejeitada localmente. "
                "Tokens e custo da tentativa permanecem contabilizados.</p></div>"
            )

        failure_detail._rasai_contract_error_detail = True
        failure_detail._rasai_original = original_failure_detail
        m18_reporting._failure_detail = failure_detail

    _INSTALLED = True
