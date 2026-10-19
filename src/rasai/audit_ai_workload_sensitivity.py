"""#319: one-URL independent-AI-need sensitivity; not a price forecast.

The historical sample demonstrated eight actual AI requests in one AUD.
This module only makes that work-volume variability visible *before*
execution: scenario counts are explicitly hypothetical. It does not know
future findings, output length, tokens, provider failures or optional work.
"""
from __future__ import annotations

from typing import Any, Iterable

TASK_SCENARIOS = (1, 8, 16)


def _cycles(state: Any) -> int | None:
    raw = getattr(state, "ai_max_cycles", None)
    return raw if type(raw) is int and 1 <= raw <= 10 else None


def independent_ai_need_sensitivity(
    state: Any, *, min_pages: int, max_pages: int,
) -> dict[str, object]:
    """No request, no monetary arithmetic and no false global request cap."""
    output: dict[str, object] = {
        "contract": "RASAI-AI-NEED-SENSITIVITY-319-001",
        "status": "NOT_APPLICABLE",
        "independent_need_scenarios": (),
        "future_token_total": None,
        "future_cost_usd": None,
        "future_findings_and_actions": None,
        "paid_request_authorized": False,
        "provider_requests": 0,
        "audit_writes": 0,
        "is_aud_total_request_cap": False,
    }
    if type(min_pages) is not int or type(max_pages) is not int:
        return {**output, "status": "WORKLOAD_SCOPE_UNVERIFIABLE"}
    if min_pages != 1 or max_pages != 1:
        return {**output, "status": "NOT_SINGLE_PAGE_SCOPE"}
    provider = str(getattr(state, "ai_provider", "none") or "none").casefold()
    if provider == "none":
        return output
    cycles = _cycles(state)
    if cycles is None:
        return {**output, "status": "AI_CYCLE_POLICY_UNVERIFIABLE"}
    single_provider = provider != "auto"
    scenarios = tuple({
        "independent_needs": needs,
        "illustrative_max_cycle_attempts": needs * cycles if single_provider else None,
        "provider_pool_factor_verified": single_provider,
        "model_input_tokens": None,
        "model_output_tokens": None,
        "estimated_cost_usd": None,
        "historical_frequency_verified": False,
    } for needs in TASK_SCENARIOS)
    return {
        **output, "status": "ILLUSTRATIVE_NOT_FORECAST",
        "ai_max_cycles": cycles,
        "independent_need_scenarios": scenarios,
    }


def format_independent_ai_need_sensitivity(result: dict[str, object]) -> tuple[str, ...]:
    """Display hypothetical demand without implying pricing or consent."""
    if result.get("status") != "ILLUSTRATIVE_NOT_FORECAST":
        if result.get("status") == "NOT_APPLICABLE":
            return ()
        return (
            "Sensibilidade de tarefas IA: N/D (exige 1 página conhecida e "
            "política de ciclos íntegra).",
        )
    lines = [
        "SENSIBILIDADE IA — SIMULAÇÕES DE DEMANDA, NÃO FORECAST FINANCEIRO",
        "Uma URL pode originar múltiplas necessidades independentes de IA. "
        "Os cenários 1/8/16 são exemplos de carga, não probabilidade, "
        "baseline estatística, orçamento aprovado ou teto da AUD.",
    ]
    for scenario in result["independent_need_scenarios"]:
        if scenario["illustrative_max_cycle_attempts"] is None:
            upper = "N/D (pool AUTO variável)"
        else:
            upper = (
                f"até {scenario['illustrative_max_cycle_attempts']} ciclos de chamada "
                "de provider explícito, se todas as necessidades consumirem o teto"
            )
        lines.append(
            f"{scenario['independent_needs']} necessidade(s) IA: {upper}; "
            "tokens, findings/ações e USD futuros = N/D."
        )
    lines.append(
        "Improvement, Competitive, remediações e Análise Direcionada "
        "dependem de evidências/consentimento próprios; nenhuma chamada, "
        "reprecificação ou redução de qualidade foi realizada."
    )
    return tuple(lines)


__all__ = (
    "TASK_SCENARIOS",
    "independent_ai_need_sensitivity",
    "format_independent_ai_need_sensitivity",
)
