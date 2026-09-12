"""Pre-execution monetary confirmation and post-run cost adherence for the local console."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from types import ModuleType
from typing import Any

from rasai.console_artifacts import artifact_status
from rasai.console_cost import actual_usage
from rasai.cost_forecast import CostForecast, forecast_local_cost
from rasai.console_ui import CYAN, DIM, GREEN, RED, YELLOW, paint

_DECLINED: set[int] = set()
_FORECASTS: dict[int, CostForecast] = {}
_OUTCOMES: dict[int, "_CostOutcome"] = {}
_ALERT_THRESHOLD_PERCENT = 5.0


@dataclass(frozen=True, slots=True)
class _CostOutcome:
    comparable: bool
    currency: str | None
    expected: float | None
    actual: float | None
    deviation: float | None
    deviation_percent: float | None
    status: str
    relation: str
    forecast_pages: int
    actual_pages: int | None
    unpriced_ai_attempts: int
    notes: tuple[str, ...] = ()


def _money(value: float | None, currency: str | None) -> str:
    if value is None or not currency:
        return "-"
    return f"{currency} {value:.6f}"


def _signed_money(value: float | None, currency: str | None) -> str:
    if value is None or not currency:
        return "-"
    return f"{currency} {value:+.6f}"


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


def _actual_page_count(workspace: Any) -> int | None:
    if workspace is None:
        return None
    database = workspace / "audit.db"
    if not database.is_file():
        return None
    try:
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True, timeout=0.5)
        try:
            row = connection.execute("SELECT COUNT(*) FROM pages").fetchone()
            return int(row[0] or 0) if row else 0
        finally:
            connection.close()
    except sqlite3.Error:
        return None


def _historical_relation(forecast: CostForecast, actual: float) -> str:
    low = forecast.likely_low
    high = forecast.likely_high
    potential = forecast.potential
    if low is not None and actual < low:
        return "abaixo da faixa provável histórica"
    if high is not None and actual <= high:
        return "dentro da faixa provável histórica"
    if potential is not None and actual <= potential:
        return "acima da faixa provável, mas ainda dentro do cenário potencial P90"
    if potential is not None:
        return "acima do cenário potencial P90"
    return "sem faixa histórica suficiente para posicionamento"


def _evaluate_cost_outcome(
    forecast: CostForecast,
    *,
    costs: tuple[tuple[str, float], ...],
    unpriced_ai_attempts: int,
    actual_pages: int | None,
) -> _CostOutcome:
    expected = forecast.expected
    currency = forecast.currency
    notes: list[str] = []
    observed: float | None = None

    if not forecast.show_confirmation or expected is None or expected <= 0 or not currency:
        notes.append("estimativa prévia não possui custo esperado monetário comparável")
    elif unpriced_ai_attempts > 0:
        matching = [float(amount) for item_currency, amount in costs if item_currency == currency]
        observed = sum(matching) if matching else 0.0
        notes.append(
            f"{unpriced_ai_attempts} tentativa(s) de IA não possuem preço monetário conhecido; "
            "o custo observado é parcial e não recebe classificação de aderência"
        )
    elif len(costs) > 1:
        notes.append("a execução materializou custos em múltiplas moedas; não há conversão cambial implícita")
    elif costs and costs[0][0] != currency:
        notes.append(
            f"moeda observada ({costs[0][0]}) difere da moeda prevista ({currency}); comparação recusada"
        )
    else:
        observed = float(costs[0][1]) if costs else 0.0

    if observed is None or notes:
        return _CostOutcome(
            comparable=False,
            currency=currency,
            expected=expected,
            actual=observed,
            deviation=None,
            deviation_percent=None,
            status="NÃO COMPARÁVEL",
            relation="cobertura monetária incompleta ou incompatível",
            forecast_pages=forecast.target_pages,
            actual_pages=actual_pages,
            unpriced_ai_attempts=max(int(unpriced_ai_attempts), 0),
            notes=tuple(notes),
        )

    deviation = observed - expected
    deviation_percent = (deviation / expected) * 100.0
    if deviation_percent <= 0:
        status = "DENTRO DO ESPERADO"
    elif round(deviation_percent, 10) <= _ALERT_THRESHOLD_PERCENT:
        status = "ALERTA"
    else:
        status = "CRÍTICO"
    return _CostOutcome(
        comparable=True,
        currency=currency,
        expected=expected,
        actual=observed,
        deviation=deviation,
        deviation_percent=deviation_percent,
        status=status,
        relation=_historical_relation(forecast, observed),
        forecast_pages=forecast.target_pages,
        actual_pages=actual_pages,
        unpriced_ai_attempts=0,
        notes=(
            "classificação compara o custo monetário técnico observado com o custo esperado da prévia; "
            "não representa invoice/fatura do provider",
        ),
    )


def _build_outcome(state: Any, forecast: CostForecast) -> _CostOutcome | None:
    if not str(getattr(state, "audit_id", "") or "").strip():
        return None
    workspace, _ = artifact_status(state)
    usage = actual_usage(workspace)
    if workspace is None or usage is None:
        return None
    return _evaluate_cost_outcome(
        forecast,
        costs=usage.costs,
        unpriced_ai_attempts=usage.unpriced_ai_attempts,
        actual_pages=_actual_page_count(workspace),
    )


def _persist_outcome(state: Any, forecast: CostForecast, outcome: _CostOutcome) -> bool:
    if not str(getattr(state, "audit_id", "") or "").strip():
        return False
    workspace, _ = artifact_status(state)
    if workspace is None:
        return False
    database = workspace / "audit.db"
    if not database.is_file():
        return False
    try:
        connection = sqlite3.connect(database, timeout=1.0)
        try:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS console_cost_forecast_outcomes (
                        audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                        evaluated_at TEXT NOT NULL,
                        currency TEXT,
                        expected_cost REAL,
                        actual_cost REAL,
                        deviation_amount REAL,
                        deviation_percent REAL,
                        status TEXT NOT NULL,
                        relation TEXT NOT NULL,
                        forecast_pages INTEGER NOT NULL,
                        actual_pages INTEGER,
                        likely_low REAL,
                        likely_high REAL,
                        potential REAL,
                        sample_runs INTEGER NOT NULL,
                        sample_calls INTEGER NOT NULL,
                        confidence TEXT NOT NULL,
                        unpriced_ai_attempts INTEGER NOT NULL,
                        source TEXT NOT NULL,
                        notes TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT OR REPLACE INTO console_cost_forecast_outcomes VALUES (
                        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                    )
                    """,
                    (
                        state.audit_id,
                        datetime.now(timezone.utc).isoformat(),
                        outcome.currency,
                        outcome.expected,
                        outcome.actual,
                        outcome.deviation,
                        outcome.deviation_percent,
                        outcome.status,
                        outcome.relation,
                        outcome.forecast_pages,
                        outcome.actual_pages,
                        forecast.likely_low,
                        forecast.likely_high,
                        forecast.potential,
                        forecast.sample_runs,
                        forecast.sample_calls,
                        forecast.confidence,
                        outcome.unpriced_ai_attempts,
                        forecast.source,
                        json.dumps(outcome.notes, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
        finally:
            connection.close()
    except sqlite3.Error:
        return False
    return True


def _status_color(status: str) -> str:
    if status == "CRÍTICO":
        return RED
    if status in {"ALERTA", "NÃO COMPARÁVEL"}:
        return YELLOW
    return GREEN


def _render_outcome(forecast: CostForecast, outcome: _CostOutcome) -> None:
    color = _status_color(outcome.status)
    print("\nADERÊNCIA DO CUSTO À ESTIMATIVA PRÉ-EXECUÇÃO")
    print("-" * 100)
    print("Custo esperado      : " + paint(_money(outcome.expected, outcome.currency), CYAN, bold=True))
    print("Custo observado     : " + paint(_money(outcome.actual, outcome.currency), color, bold=True))
    if outcome.deviation is not None and outcome.deviation_percent is not None:
        print(
            "Desvio vs esperado   : "
            + paint(
                f"{_signed_money(outcome.deviation, outcome.currency)} ({outcome.deviation_percent:+.2f}%)",
                color,
                bold=True,
            )
        )
    else:
        print("Desvio vs esperado   : -")
    print(
        "Faixa provável      : "
        f"{_money(forecast.likely_low, forecast.currency)} - {_money(forecast.likely_high, forecast.currency)}"
    )
    print("Cenário potencial   : " + _money(forecast.potential, forecast.currency) + " (P90)")
    actual_pages = str(outcome.actual_pages) if outcome.actual_pages is not None else "-"
    print(f"Volume previsto/real: {outcome.forecast_pages} / {actual_pages} página(s)")
    print(f"Posição histórica   : {outcome.relation}")
    if outcome.status == "ALERTA":
        explanation = f"custo ficou até {_ALERT_THRESHOLD_PERCENT:.0f}% acima do esperado"
    elif outcome.status == "CRÍTICO":
        explanation = f"custo ultrapassou {_ALERT_THRESHOLD_PERCENT:.0f}% acima do esperado"
    elif outcome.status == "DENTRO DO ESPERADO":
        explanation = "custo igual ou abaixo do esperado"
    else:
        explanation = "telemetria monetária insuficiente para um veredito confiável"
    print("Resultado            : " + paint(f"{outcome.status} — {explanation}", color, bold=True))
    for note in outcome.notes:
        print(paint(f"Observação           : {note}", DIM))
    print(
        paint(
            "Escopo financeiro: apenas serviços cuja telemetria monetária é conhecida pelo RASAi; "
            "serviços sem preço canônico permanecem fora desta comparação.",
            DIM,
        )
    )


def install(console_module: ModuleType) -> None:
    """Wrap the final local run contract without changing the audit engine."""
    if getattr(console_module, "_rasai_cost_confirmation", False):
        return

    original_run = console_module.run_audit_from_console
    original_post_run = console_module._post_run_actions
    original_usage = getattr(console_module, "_render_actual_usage", None)

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
                _FORECASTS[id(state)] = forecast
                state.operation = "LOCAL:COST_CONFIRMED"
                code = int(original_run(state) or 0)
                outcome = _build_outcome(state, forecast)
                if outcome is not None:
                    _OUTCOMES[id(state)] = outcome
                    _persist_outcome(state, forecast, outcome)
                return code
            if choice in {"V", "Q"}:
                _DECLINED.add(id(state))
                _FORECASTS.pop(id(state), None)
                _OUTCOMES.pop(id(state), None)
                state.status = "READY"
                state.operation = "LOCAL:COST_DECLINED"
                state.error = ""
                return 0
            print("Opção inválida. Use C para confirmar ou V para voltar.")

    def usage(state: Any) -> None:
        if callable(original_usage):
            original_usage(state)
        forecast = _FORECASTS.get(id(state))
        outcome = _OUTCOMES.get(id(state))
        if forecast is not None and outcome is not None:
            _render_outcome(forecast, outcome)

    def post_run(state: Any) -> bool:
        if id(state) in _DECLINED:
            _DECLINED.discard(id(state))
            return False
        try:
            return bool(original_post_run(state))
        finally:
            _FORECASTS.pop(id(state), None)
            _OUTCOMES.pop(id(state), None)

    console_module.run_audit_from_console = run
    if callable(original_usage):
        console_module._render_actual_usage = usage
    console_module._post_run_actions = post_run
    console_module._rasai_cost_confirmation = True
