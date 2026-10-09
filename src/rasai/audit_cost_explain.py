"""#319 financial forecast readout: deterministic explanations, never a price engine.

All values come from the existing, persisted forecast and attempt ledger.
A point-deviation severity is not an invoice, nor evidence of failed prediction
interval calibration. The external GEO supplement belongs to a separate package.
"""
from __future__ import annotations

from html import escape
from math import isfinite
from typing import Any, Mapping


def _number(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        number = float(value)
        return number if isfinite(number) else None
    except (ValueError, TypeError):
        return None


def forecast_readout(
    forecast: Mapping[str, Any] | None, *,
    observed_total: float | None,
    priced_attempts: int,
    total_attempts: int,
) -> str:
    """Return only qualified, report-ready text from already persisted numbers."""
    if not forecast:
        return (
            "<p>Sem previsão financeira prévia persistida. Não é possível "
            "classificar precisão de estimativa.</p>"
        )
    expected = _number(forecast.get("expected_cost"))
    low = _number(forecast.get("likely_low"))
    high = _number(forecast.get("likely_high"))
    p90 = _number(forecast.get("potential"))
    observed = _number(observed_total)
    count = max(int(total_attempts), 0)
    priced = max(0, min(int(priced_attempts), count))
    coverage_complete = count > 0 and priced == count
    result = (
        "<div class='notice'><strong>Interpretação da previsão:</strong> "
        "a classe de desvio compara o realizado com a estimativa pontual; "
        "não é uma análise independente de integridade da AUD e não constitui "
        "fatura do provedor. Intervalos históricos são cenários, não garantias. "
        "Chamadas opcionais pós-AUD e suplementos GEO possuem escopo econômico "
        "próprio e não devem ser atribuídos retroativamente à execução central.</div>"
    )
    if not coverage_complete:
        result += (
            "<div class='notice warn'>Cobertura monetária incompleta: "
            + str(priced) + "/" + str(count)
            + " tentativa(s) possuem valor monetário contabilizado. "
            "Não concluir precisão ou desvio do custo total.</div>"
        )
    if (
        coverage_complete and observed is not None
        and low is not None and high is not None and low <= high
    ):
        if low <= observed <= high:
            result += (
                "<p>O valor das tentativas precificadas está "
                "<strong>dentro da faixa histórica provável</strong>, "
                "independentemente da classificação de desvio pontual.</p>"
            )
        else:
            result += (
                "<p>O valor das tentativas precificadas está "
                "<strong>fora da faixa histórica provável</strong>; "
                "revisar comparabilidade do histórico e escopo.</p>"
            )
    else:
        result += (
            "<p>Posição do custo na faixa histórica: N/D "
            "(faixa, cobertura ou valor observado insuficiente).</p>"
        )
    if expected is not None and expected > 0 and coverage_complete and observed is not None:
        delta = (observed - expected) * 100 / expected
        result += (
            "<p>Desvio frente à estimativa pontual persistida: "
            + escape(f"{delta:+.2f}%")
            + ". Trata-se de uma razão aritmética; o rótulo de severidade "
            "decorre da política existente.</p>"
        )
    if p90 is not None:
        result += (
            "<p>O cenário P90 é uma referência de cauda histórica, "
            "não um teto contratual de cobrança.</p>"
        )
    return result
