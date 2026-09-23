"""Persistência derivada da execução do relatório consolidado.

A execução do consolidado não pertence a nenhuma AUD individual. Este módulo grava
somente artifacts reconstruíveis em audits/consolidated/executions/CONRUN-* e nunca
altera audit.db, coleta, scoring, providers ou contratos das auditorias fonte.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from rasai.secret_safety import redact_value

EXECUTION_CONTRACT = "CONSOLIDATED-EXECUTION-001"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _cost_reconciliation(run_payload: Mapping[str, Any]) -> dict[str, Any]:
    attempts = [item for item in run_payload.get("attempts", ()) if isinstance(item, Mapping)]
    forecast = run_payload.get("forecast") if isinstance(run_payload.get("forecast"), Mapping) else {}
    currencies: dict[str, float] = {}
    unpriced = 0
    for item in attempts:
        amount = item.get("estimated_cost")
        currency = str(item.get("currency") or "").strip()
        if amount is None or not currency:
            unpriced += 1
            continue
        try:
            currencies[currency] = currencies.get(currency, 0.0) + float(amount)
        except (TypeError, ValueError):
            unpriced += 1
    forecast_currency = str(forecast.get("currency") or "").strip()
    expected = forecast.get("expected_cost")
    observed = currencies.get(forecast_currency) if forecast_currency else None
    deviation = deviation_percent = None
    if expected is not None and observed is not None:
        try:
            expected_value = float(expected)
            deviation = observed - expected_value
            deviation_percent = None if expected_value == 0 else deviation / abs(expected_value) * 100.0
        except (TypeError, ValueError):
            deviation = deviation_percent = None
    return {
        "expected_cost": expected,
        "observed_cost": observed,
        "currency": forecast_currency or None,
        "deviation_amount": deviation,
        "deviation_percent": deviation_percent,
        "observed_costs_by_currency": currencies,
        "unpriced_attempts": unpriced,
        "forecast_pricing_version": forecast.get("pricing_version"),
        "rounds": run_payload.get("rounds"),
    }


@dataclass(frozen=True, slots=True)
class ConsolidationExecutionLog:
    run_id: str
    run_dir: Path
    execution_path: Path
    exchanges_path: Path

    @classmethod
    def start(cls, audits_root: str | Path, filters: Any) -> "ConsolidationExecutionLog":
        root = Path(audits_root) / "consolidated" / "executions"
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")[:-3]
        run_id = f"CONRUN-{stamp}-{uuid4().hex[:8].upper()}"
        run_dir = root / run_id
        run_dir.mkdir(parents=False, exist_ok=False)
        item = cls(
            run_id=run_id,
            run_dir=run_dir,
            execution_path=run_dir / "execution.json",
            exchanges_path=run_dir / "ai-exchanges.json",
        )
        canonical = filters.canonical() if hasattr(filters, "canonical") else _jsonable(filters)
        payload = {
            "contract": EXECUTION_CONTRACT,
            "run_id": run_id,
            "status": "PREPARING",
            "stage": "PREPARING",
            "started_at": _now(),
            "updated_at": _now(),
            "finished_at": None,
            "filters": canonical,
            "events": [
                {
                    "at": _now(),
                    "stage": "PREPARING",
                    "status": "STARTED",
                    "message": "Execução do relatório consolidado iniciada.",
                }
            ],
            "preview": None,
            "ai": None,
            "result": None,
            "error": None,
        }
        item._write(payload)
        item._write_exchanges(())
        return item

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.execution_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, payload: Mapping[str, Any]) -> None:
        safe = redact_value(_jsonable(payload))
        self.execution_path.write_text(
            json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def _write_exchanges(self, exchanges: Any) -> None:
        payload = {
            "contract": EXECUTION_CONTRACT,
            "run_id": self.run_id,
            "updated_at": _now(),
            "exchanges": redact_value(_jsonable(exchanges)),
        }
        self.exchanges_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def event(
        self,
        *,
        stage: str,
        status: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        payload = self._read()
        payload["status"] = str(status)
        payload["stage"] = str(stage)
        payload["updated_at"] = _now()
        events = payload.setdefault("events", [])
        events.append({
            "at": _now(),
            "stage": str(stage),
            "status": str(status),
            "message": str(message),
            "details": _jsonable(details or {}),
        })
        self._write(payload)

    def record_preview(self, preview: Any) -> None:
        payload = self._read()
        payload["preview"] = _jsonable(preview)
        payload["updated_at"] = _now()
        self._write(payload)

    def record_ai(self, run: Any) -> None:
        payload = self._read()
        ai_payload = _jsonable(run)
        exchanges = getattr(run, "exchanges", ()) if run is not None else ()
        if isinstance(ai_payload, dict):
            ai_payload["cost_reconciliation"] = _cost_reconciliation(ai_payload)
            ai_payload.pop("exchanges", None)
            ai_payload["exchanges_file"] = "ai-exchanges.json"
        payload["ai"] = ai_payload
        payload["updated_at"] = _now()
        self._write(payload)
        self._write_exchanges(exchanges)

    def complete(self, result: Any) -> None:
        payload = self._read()
        payload["status"] = "COMPLETE"
        payload["stage"] = "COMPLETE"
        payload["updated_at"] = _now()
        payload["finished_at"] = _now()
        payload["result"] = {
            "report_dir": str(getattr(result, "report_dir", "")),
            "report_path": str(getattr(result, "report_path", "")),
            "manifest_path": str(getattr(result, "manifest_path", "")),
            "request_fingerprint": str(getattr(result, "request_fingerprint", "")),
            "reused": bool(getattr(result, "reused", False)),
        }
        payload.setdefault("events", []).append({
            "at": _now(),
            "stage": "COMPLETE",
            "status": "COMPLETE",
            "message": "Relatório consolidado concluído.",
        })
        self._write(payload)

    def reused(self, result: Any) -> None:
        payload = self._read()
        payload["status"] = "REUSED"
        payload["stage"] = "COMPLETE"
        payload["updated_at"] = _now()
        payload["finished_at"] = _now()
        payload["result"] = {
            "report_dir": str(getattr(result, "report_dir", "")),
            "report_path": str(getattr(result, "report_path", "")),
            "manifest_path": str(getattr(result, "manifest_path", "")),
            "request_fingerprint": str(getattr(result, "request_fingerprint", "")),
            "reused": True,
        }
        payload.setdefault("events", []).append({
            "at": _now(),
            "stage": "COMPLETE",
            "status": "REUSED",
            "message": "Relatório consolidado idêntico reutilizado.",
        })
        self._write(payload)

    def fail(self, exc: BaseException, *, stage: str = "FAILED") -> None:
        payload = self._read()
        payload["status"] = "FAILED"
        payload["stage"] = str(stage)
        payload["updated_at"] = _now()
        payload["finished_at"] = _now()
        payload["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        payload.setdefault("events", []).append({
            "at": _now(),
            "stage": str(stage),
            "status": "FAILED",
            "message": str(exc),
        })
        self._write(payload)


class ConsolidationExecutionError(RuntimeError):
    """Erro de consolidação com referência persistida da execução."""

    def __init__(self, message: str, *, execution: ConsolidationExecutionLog):
        super().__init__(message)
        self.execution = execution
        self.execution_dir = execution.run_dir
        self.execution_path = execution.execution_path
        self.exchanges_path = execution.exchanges_path


__all__ = [
    "EXECUTION_CONTRACT",
    "ConsolidationExecutionError",
    "ConsolidationExecutionLog",
]
