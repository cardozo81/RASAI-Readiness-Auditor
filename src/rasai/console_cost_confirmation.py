"""Pre-execution monetary cost confirmation for the local interactive console."""
from __future__ import annotations

from types import ModuleType
from typing import Any

from rasai.cost_forecast import CostForecast, forecast_local_cost
from rasai.console_ui import CYAN, DIM, GREEN, YELLOW, paint

_DECLINED: set[int] = set()


def _money(value: float | None, currency: str | None) -> str:
    if value is None or not currency:
        return "-"
    return f"{currency} {value:.6f}"


def _render_forecast(forecast: CostForecast) -> None:
    print("\nESTIMATIVA FINANCEIRA ANTES DA EXECUÇÃO")
    print("-" * 100)
    print(
        "Base histórica      : "
        f"{forecast.sample_runs} execução(ões), {forecast.sample_calls} chamada(s) com custo conhecido"
    )
    print(f"Volume estimado     : {forecast.target_pages} página(s)")
    print(
        "Custo só sucessos   : "
        + paint(_money(forecast.success_baseline, forecast.currency), CYAN, bold=True)
    )
    print(
        "Custo esperado      : "
        + paint(_money(forecast.expected, forecast.currency), YELLOW, bold=True)
    )
    print(
        "Faixa provável      : "
        f"{_money(forecast.likely_low, forecast.currency)} - "
        f"{_money(forecast.likely_high, forecast.currency)}"
    )
    print(
        "Cenário potencial   : "
        + paint(_money(forecast.potential, forecast.currency), YELLOW, bold=True)
    )
    print(f"Confiança            : {paint(forecast.confidence, GREEN if forecast.confidence in {'BOA', 'ALTA'} else YELLOW, bold=True)}")
    print(f"Reprecificação atual : {forecast.repriced_share * 100:.0f}% das chamadas conhecidas")
    for note in forecast.notes:
        print(paint(f"Observação           : {note}", DIM))
    print(
        paint(
            "A execução ainda não iniciou e nenhuma chamada tarifável foi disparada nesta etapa.",
            GREEN,
            bold=True,
        )
    )


def install(console_module: ModuleType) -> None:
    """Wrap the final local run contract without changing the audit engine."""
    if getattr(console_module, "_rasai_cost_confirmation", False):
        return

    original_run = console_module.run_audit_from_console
    original_post_run = console_module._post_run_actions

    def run(state: Any) -> int:
        forecast = forecast_local_cost(state)
        if not forecast.show_confirmation:
            return int(original_run(state) or 0)

        state.operation = "LOCAL:COST_FORECAST"
        state.error = ""
        console_module.render_header(state)
        _render_forecast(forecast)
        print("\nC. Confirmar e executar")
        print("V. Voltar sem executar")
        while True:
            choice = input("Escolha: ").strip().upper()
            if choice == "C":
                state.operation = "LOCAL:COST_CONFIRMED"
                return int(original_run(state) or 0)
            if choice in {"V", "Q"}:
                _DECLINED.add(id(state))
                state.status = "READY"
                state.operation = "LOCAL:COST_DECLINED"
                state.error = ""
                return 0
            print("Opção inválida. Use C para confirmar ou V para voltar.")

    def post_run(state: Any) -> bool:
        if id(state) in _DECLINED:
            _DECLINED.discard(id(state))
            return False
        return bool(original_post_run(state))

    console_module.run_audit_from_console = run
    console_module._post_run_actions = post_run
    console_module._rasai_cost_confirmation = True
