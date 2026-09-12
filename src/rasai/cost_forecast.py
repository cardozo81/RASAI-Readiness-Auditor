"""Historical pre-execution financial cost forecasting.

Forecasts are advisory. RASAi learns only from persisted billable telemetry, reprices
token usage with the current catalog when possible, never invents unknown charges,
and never performs implicit currency conversion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from statistics import median
from typing import Any, Iterable, Mapping

from rasai.audit_execution_contract import normalize_audit_job_payload
from rasai.m18_ai import ProviderUsage, estimate_cost
from rasai.provider_registry import get_provider_registration

_SUCCESS = {"SUCCESS", "SUCCEEDED", "COMPLETED", "PASS"}
_AI_OPS = {"SEMANTIC_ANALYSIS", "CONTENT_REMEDIATION"}


@dataclass(frozen=True, slots=True)
class HistoricalRunCost:
    audit_id: str
    page_count: int
    success_cost: float
    billable_cost: float
    currency: str
    known_calls: int
    repriced_calls: int


@dataclass(frozen=True, slots=True)
class CostForecast:
    available: bool
    show_confirmation: bool
    currency: str | None = None
    success_baseline: float | None = None
    expected: float | None = None
    likely_low: float | None = None
    likely_high: float | None = None
    potential: float | None = None
    sample_runs: int = 0
    sample_calls: int = 0
    target_pages: int = 0
    confidence: str = "NENHUMA"
    source: str = ""
    repriced_share: float = 0.0
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["notes"] = list(self.notes)
        return value


def unavailable_forecast(*notes: str, source: str = "") -> CostForecast:
    return CostForecast(False, False, source=source, notes=tuple(filter(None, notes)))


def _percentile(values: Iterable[float], p: float) -> float:
    ordered = sorted(float(x) for x in values)
    if not ordered:
        raise ValueError("percentile requires values")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _confidence(runs: int, repriced_share: float) -> str:
    value = "ALTA" if runs >= 50 else "BOA" if runs >= 20 else "MODERADA" if runs >= 5 else "BAIXA" if runs else "NENHUMA"
    if value != "NENHUMA" and repriced_share < 0.80:
        order = ("BAIXA", "MODERADA", "BOA", "ALTA")
        value = order[max(0, order.index(value) - 1)]
    return value


def _forecast_from_runs(
    runs: Iterable[HistoricalRunCost], *, target_pages: int, source: str, notes: Iterable[str] = ()
) -> CostForecast:
    items = [run for run in runs if run.page_count > 0 and run.known_calls > 0]
    if not items:
        return unavailable_forecast(*tuple(notes), "sem histórico financeiro comparável", source=source)
    currencies = {run.currency for run in items if run.currency}
    if len(currencies) != 1:
        return unavailable_forecast(
            *tuple(notes),
            "histórico comparável possui múltiplas moedas; o RASAi não faz conversão cambial implícita",
            source=source,
        )
    pages = max(int(target_pages), 1)
    success_rates = [run.success_cost / run.page_count for run in items]
    rates = [run.billable_cost / run.page_count for run in items]
    expected = median(rates) * pages
    low = min(_percentile(rates, 0.25) * pages, expected)
    high = max(_percentile(rates, 0.75) * pages, expected)
    potential = max(_percentile(rates, 0.90) * pages, high)
    baseline = median(success_rates) * pages
    calls = sum(run.known_calls for run in items)
    repriced = sum(run.repriced_calls for run in items)
    share = repriced / calls if calls else 0.0
    extra = list(notes)
    if share < 1:
        extra.append("parte do histórico não pôde ser reprecificada por tokens e usou o custo técnico persistido")
    extra.append("estimativa técnica histórica; não substitui invoice/fatura do provider")
    monetary = max(baseline, expected, high, potential) > 0
    return CostForecast(
        monetary, monetary, next(iter(currencies)), round(baseline, 8), round(expected, 8),
        round(low, 8), round(high, 8), round(potential, 8), len(items), calls, pages,
        _confidence(len(items), share), source, round(share, 4), tuple(dict.fromkeys(extra)),
    )


def _value(row: Mapping[str, Any], key: str) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _current_cost(row: Mapping[str, Any]) -> tuple[float | None, str | None, bool]:
    provider, model = str(_value(row, "provider") or "").upper(), str(_value(row, "model") or "")
    if provider and model:
        usage = ProviderUsage(
            _integer(_value(row, "input_tokens")), _integer(_value(row, "cached_input_tokens")),
            _integer(_value(row, "output_tokens")), _integer(_value(row, "reasoning_tokens")),
            _integer(_value(row, "total_tokens")),
        )
        amount, currency, _ = estimate_cost(provider, model, usage, datetime.now(timezone.utc))
        if amount is not None and currency:
            return float(amount), str(currency), True
    amount = _number(_value(row, "estimated_cost"))
    currency = str(_value(row, "cost_currency") or "").strip() or None
    return (amount, currency, False) if amount is not None and currency else (None, currency, False)


def _provider(selection: str, model: Any = None) -> tuple[str | None, str | None]:
    key = str(selection or "none").strip().casefold()
    if key in {"none", "auto"}:
        return None, None
    registration = get_provider_registration(key)
    if registration is None:
        return key.upper(), str(model or "").strip() or None
    return registration.provider_name, str(model or "").strip() or registration.default_model


def _projection(connection: sqlite3.Connection) -> dict[str, Any] | None:
    try:
        row = connection.execute(
            "SELECT configuration FROM console_execution_projections ORDER BY projected_at DESC LIMIT 1"
        ).fetchone()
        value = json.loads(str(row[0])) if row and row[0] else None
        return value if isinstance(value, dict) else None
    except (sqlite3.Error, json.JSONDecodeError):
        return None


def _local_comparable(state: Any, cfg: Mapping[str, Any] | None) -> bool:
    if not cfg:
        return True
    if str(cfg.get("ai_provider") or "none").casefold() != str(getattr(state, "ai_provider", "none")).casefold():
        return False
    if str(cfg.get("device") or "") not in {"", str(getattr(state, "device", ""))}:
        return False
    if bool(cfg.get("content_remediation", False)) != bool(getattr(state, "content_remediation", False)):
        return False
    current, old = str(getattr(state, "ai_model", "") or ""), str(cfg.get("ai_model") or "")
    return not (current and old and current != old)


def _improvement_history(connection: sqlite3.Connection) -> tuple[str | None, str | None, str | None]:
    try:
        row = connection.execute(
            "SELECT contract_version,provider,model FROM improvement_intelligence_runs ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error:
        return None, None, None
    return (
        (str(row[0] or "") or None, str(row[1] or "").upper() or None, str(row[2] or "") or None)
        if row else (None, None, None)
    )


def _read_local_run(state: Any, database: Path) -> HistoricalRunCost | None:
    standard_selection = str(getattr(state, "ai_provider", "none")).casefold()
    standard_provider, standard_model = _provider(standard_selection, getattr(state, "ai_model", None))
    improvement_enabled = bool(getattr(state, "improvement_enabled", False))
    improvement_selection = str(getattr(state, "improvement_provider", "") or "").casefold()
    improvement_provider, improvement_model = (
        _provider(improvement_selection, getattr(state, "improvement_model", None))
        if improvement_enabled and improvement_selection else (None, None)
    )
    if standard_selection == "none" and not improvement_provider:
        return None
    try:
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True, timeout=0.5)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error:
        return None
    try:
        if not _local_comparable(state, _projection(connection)):
            return None
        improvement_contract, old_improvement_provider, old_improvement_model = _improvement_history(connection)
        if improvement_provider and (
            old_improvement_provider != improvement_provider
            or (improvement_model and old_improvement_model and improvement_model != old_improvement_model)
        ):
            return None
        try:
            page_count = int(connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0])
            audit = connection.execute("SELECT audit_id FROM audits ORDER BY created_at DESC LIMIT 1").fetchone()
        except sqlite3.Error:
            return None
        if page_count <= 0:
            return None

        rows: list[tuple[str, sqlite3.Row]] = []
        try:
            rows.extend(("semantic", row) for row in connection.execute("SELECT * FROM ai_provider_attempts"))
        except sqlite3.Error:
            pass
        if bool(getattr(state, "content_remediation", False)):
            try:
                rows.extend(("content", row) for row in connection.execute("SELECT * FROM content_remediation_attempts"))
            except sqlite3.Error:
                pass

        success = total = 0.0
        known = repriced = 0
        currency: str | None = None
        for family, row in rows:
            provider, model = str(_value(row, "provider") or "").upper(), str(_value(row, "model") or "")
            if family == "semantic" and improvement_contract and str(_value(row, "semantic_contract_version") or "") == improvement_contract:
                if not improvement_provider or provider != improvement_provider or (improvement_model and model != improvement_model):
                    continue
            else:
                if standard_selection == "none" or (standard_provider and provider != standard_provider) or (standard_model and model != standard_model):
                    continue
            amount, item_currency, was_repriced = _current_cost(row)
            if amount is None or not item_currency:
                continue
            if currency is None:
                currency = item_currency
            elif currency != item_currency:
                return None
            known += 1
            repriced += int(was_repriced)
            total += amount
            success += amount if str(_value(row, "status") or "").upper() in _SUCCESS else 0.0
        if not currency or not known:
            return None
        return HistoricalRunCost(
            str(audit[0]) if audit and audit[0] else database.parent.name,
            page_count, success, total, currency, known, repriced,
        )
    finally:
        connection.close()


def _target_local(state: Any, runs: list[HistoricalRunCost]) -> int:
    from rasai.console_cost import _configured_page_range
    minimum, maximum = _configured_page_range(state)
    if minimum == maximum:
        return max(minimum, 1)
    observed = [run.page_count for run in runs if run.page_count > 0]
    return max(minimum, min(maximum, int(round(median(observed))))) if observed else max(minimum, 1)


def forecast_local_cost(state: Any) -> CostForecast:
    standard = str(getattr(state, "ai_provider", "none")).casefold() != "none"
    improvement = bool(getattr(state, "improvement_enabled", False)) and bool(str(getattr(state, "improvement_provider", "") or "").strip())
    if not standard and not improvement:
        return unavailable_forecast("nenhuma IA com telemetria financeira está ativa na configuração", source="local-audit-history")
    root = Path(str(getattr(state, "audits_root", "audits")))
    if not root.is_dir():
        return unavailable_forecast("raiz de auditorias ainda não possui histórico", source="local-audit-history")
    databases = sorted(
        (path / "audit.db" for path in root.glob("AUD-*") if (path / "audit.db").is_file()),
        key=lambda path: path.stat().st_mtime_ns, reverse=True,
    )[:200]
    runs = [run for run in (_read_local_run(state, db) for db in databases) if run is not None]
    if not runs:
        return unavailable_forecast("não há execuções locais comparáveis com custo monetário conhecido", source="local-audit-history")
    notes = ["Improvement Intelligence entra no histórico quando provider/model e contrato são comparáveis"] if improvement else []
    return _forecast_from_runs(runs, target_pages=_target_local(state, runs), source="local-audit-history", notes=notes)


def _job_payload(job: Any) -> dict[str, Any] | None:
    if str(getattr(job, "job_type", "")).upper() != "AUDIT" or not isinstance(getattr(job, "payload", None), Mapping):
        return None
    try:
        return normalize_audit_job_payload(job.payload)
    except (TypeError, ValueError):
        return None


def _job_comparable(current: Mapping[str, Any], historical: Mapping[str, Any]) -> bool:
    if any(current.get(key) != historical.get(key) for key in (
        "device_context", "ai_provider", "ai_content_remediation", "ai_technical_remediation"
    )):
        return False
    current_model, historical_model = str(current.get("ai_model") or ""), str(historical.get("ai_model") or "")
    return not (current_model and historical_model and current_model != historical_model)


def _group_cost(group: Mapping[str, Any]) -> tuple[float | None, str | None, bool]:
    dimensions = group.get("dimensions") or {}
    provider, model = str(dimensions.get("provider") or "").upper(), str(dimensions.get("model") or "")
    if provider and model:
        usage = ProviderUsage(
            _integer(group.get("input_tokens")), _integer(group.get("cached_input_tokens")),
            _integer(group.get("output_tokens")), _integer(group.get("reasoning_tokens")),
            _integer(group.get("total_tokens")),
        )
        amount, currency, _ = estimate_cost(provider, model, usage, datetime.now(timezone.utc))
        if amount is not None and currency:
            return float(amount), str(currency), True
    costs = dict(group.get("cost_by_currency") or {})
    if len(costs) == 1:
        currency, amount = next(iter(costs.items()))
        return float(amount), str(currency), False
    return None, None, False


def _target_saas(payload: Mapping[str, Any], runs: list[HistoricalRunCost]) -> int:
    urls = tuple(dict.fromkeys(str(item).strip() for item in payload.get("urls", ()) if str(item).strip()))
    maximum = max(int(payload.get("max_pages") or 1), 1)
    if urls:
        return max(1, min(len(urls), maximum))
    observed = [run.page_count for run in runs if run.page_count > 0]
    return max(1, min(maximum, int(round(median(observed))))) if observed else 1


def forecast_saas_cost(
    store: Any, *, organization_id: str, project_id: str, property_id: str,
    environment_id: str, payload: Mapping[str, Any],
) -> CostForecast:
    current = normalize_audit_job_payload(payload)
    provider_selection = str(current.get("ai_provider") or "none").casefold()
    if provider_selection == "none":
        return unavailable_forecast("nenhuma IA padrão tarifável está ativa na configuração", source="saas-usage-ledger")

    comparable_jobs = {
        str(job.job_id)
        for job in store.list_execution_jobs(project_id=project_id, limit=1000)
        if str(job.property_id) == property_id
        and str(job.environment_id) == environment_id
        and (historical := _job_payload(job)) is not None
        and _job_comparable(current, historical)
    }
    if not comparable_jobs:
        return unavailable_forecast(
            "não há execution jobs históricos comparáveis neste projeto/property/environment",
            source="saas-usage-ledger",
        )

    common = dict(project_id=project_id, property_id=property_id, environment_id=environment_id, limit=50000)
    ai = store.usage_analytics(
        organization_id, category="AI_PROVIDER_CALL",
        group_by=("audit", "job", "provider", "model", "status", "operation"), **common,
    )
    urls = store.usage_analytics(
        organization_id, category="URL_PROCESSED", group_by=("audit", "job"), **common,
    )
    pages: dict[str, int] = {}
    for group in urls.get("groups", ()):
        dims = group.get("dimensions") or {}
        if str(dims.get("job") or "") in comparable_jobs and dims.get("audit"):
            pages[str(dims["audit"])] = max(int(round(float((group.get("quantity_by_unit") or {}).get("url", 0) or 0))), 0)

    provider_filter, model_filter = _provider(provider_selection, current.get("ai_model"))
    aggregated: dict[str, dict[str, Any]] = {}
    for group in ai.get("groups", ()):
        dims = group.get("dimensions") or {}
        audit_id, job_id = str(dims.get("audit") or ""), str(dims.get("job") or "")
        provider, model = str(dims.get("provider") or "").upper(), str(dims.get("model") or "")
        operation = str(dims.get("operation") or "").upper()
        if job_id not in comparable_jobs or audit_id not in pages or operation not in _AI_OPS:
            continue
        if operation == "CONTENT_REMEDIATION" and not bool(current.get("ai_content_remediation")):
            continue
        if (provider_filter and provider != provider_filter) or (model_filter and model != model_filter):
            continue
        amount, currency, was_repriced = _group_cost(group)
        if amount is None or not currency:
            continue
        item = aggregated.setdefault(audit_id, dict(success=0.0, total=0.0, currency=currency, known=0, repriced=0))
        if item["currency"] != currency:
            item["currency"] = ""
            continue
        calls = int(group.get("event_count") or 0)
        item["known"] += calls
        item["repriced"] += calls if was_repriced else 0
        item["total"] += amount
        item["success"] += amount if str(dims.get("status") or "").upper() in _SUCCESS else 0.0

    runs = [
        HistoricalRunCost(audit_id, pages[audit_id], float(item["success"]), float(item["total"]),
                          str(item["currency"]), int(item["known"]), int(item["repriced"]))
        for audit_id, item in aggregated.items()
        if item["currency"] and pages.get(audit_id, 0) > 0 and item["known"] > 0
    ]
    if not runs:
        return unavailable_forecast(
            "usage ledger não possui custo monetário comparável com cobertura suficiente",
            source="saas-usage-ledger",
        )
    notes = (
        ["AI auto usa o mix histórico real de providers/modelos do mesmo escopo; o browser não presume credenciais do worker"]
        if provider_selection == "auto" else []
    )
    return _forecast_from_runs(
        runs, target_pages=_target_saas(current, runs), source="saas-usage-ledger", notes=notes
    )
