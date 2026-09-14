"""Fallback pre-run cost preview when no comparable monetary history exists.

The historical forecaster remains authoritative whenever it can produce a monetary
estimate. This adapter only prevents the first AI-enabled run from starting with no
financial preview at all: it shows the known request-volume exposure and current
per-token tariffs, without inventing an unknown token total.
"""
from __future__ import annotations

from types import ModuleType
from typing import Any

from rasai.console_cost import ExposureEstimate, estimate_exposure
from rasai.console_ui import CYAN, DIM, GREEN, YELLOW, paint
from rasai.cost_forecast import CostForecast, forecast_local_cost

_DECLINED: set[int] = set()


def _render_fallback(forecast: CostForecast, exposure: ExposureEstimate) -> None:
    print("\nPRÉVIA FINANCEIRA ANTES DA EXECUÇÃO - SEM HISTÓRICO COMPARÁVEL")
    print("-" * 100)
    print(
        "Histórico monetário : "
        + paint("ainda insuficiente para estimar um total confiável", YELLOW, bold=True)
    )
    print(f"Exposição estimada   : {paint(exposure.level, YELLOW, bold=True)}")
    print(
        f"Tentativas de IA     : {exposure.min_ai_attempts}-{exposure.max_ai_attempts} "
        "potenciais, conforme páginas/contextos e retries elegíveis"
    )
    if exposure.pricing_lines:
        print("\nTarifas vigentes conhecidas para os providers/modelos elegíveis:")
        for line in exposure.pricing_lines:
            print("  - " + line)
    else:
        print("Tarifas vigentes     : nenhuma tarifa monetária canônica disponível para a seleção atual")
    print(
        "\nCusto monetário total: "
        + paint("não calculável com segurança antes desta primeira base comparável", CYAN, bold=True)
    )
    print(
        paint(
            "O RASAi não inventa quantidade de tokens antes de conhecer o conteúdo real. "
            "Após a execução, o console exibirá tentativas, tokens e custo técnico estimado persistido.",
            DIM,
        )
    )
    for note in forecast.notes:
        print(paint(f"Motivo histórico     : {note}", DIM))
    print(
        paint(
            "Nenhuma chamada tarifável foi disparada nesta etapa de prévia.",
            GREEN,
            bold=True,
        )
    )


def install(console_module: ModuleType) -> None:
    """Require an explicit acknowledgement for AI-enabled first-run exposure."""
    if getattr(console_module, "_rasai_first_run_cost_preview", False):
        return
    original_run = console_module.run_audit_from_console
    original_post_run = console_module._post_run_actions

    def run(state: Any) -> int:
        forecast = forecast_local_cost(state)
        # The canonical historical confirmation already handles this case.
        if forecast.show_confirmation:
            return int(original_run(state) or 0)

        exposure = estimate_exposure(state)
        if exposure.max_ai_attempts <= 0:
            return int(original_run(state) or 0)

        state.operation = "LOCAL:COST_EXPOSURE_PREVIEW"
        state.error = ""
        console_module.render_header(state)
        _render_fallback(forecast, exposure)
        print("\nC. Confirmar exposição e executar")
        print("V. Voltar sem executar")
        while True:
            choice = input("Escolha: ").strip().upper()
            if choice == "C":
                state.operation = "LOCAL:COST_EXPOSURE_CONFIRMED"
                return int(original_run(state) or 0)
            if choice in {"V", "Q"}:
                _DECLINED.add(id(state))
                state.status = "READY"
                state.operation = "LOCAL:COST_EXPOSURE_DECLINED"
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
    console_module._rasai_first_run_cost_preview = True
