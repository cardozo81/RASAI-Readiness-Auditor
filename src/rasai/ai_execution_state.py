"""Process-local handoff of AI execution telemetry to final derivations/report projection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rasai.ai_exchange_log import AiExchangeRecorder


@dataclass(frozen=True, slots=True)
class AiExecutionState:
    provider: Any
    recorder: AiExchangeRecorder


_CURRENT: list[AiExecutionState] = []


def set_current_ai_execution(provider: Any, recorder: AiExchangeRecorder) -> None:
    """Remember every distinct recorder created during one audit."""
    for index, item in enumerate(_CURRENT):
        if item.recorder is recorder:
            _CURRENT[index] = AiExecutionState(provider=provider, recorder=recorder)
            return
    _CURRENT.append(AiExecutionState(provider=provider, recorder=recorder))


def current_ai_executions() -> tuple[AiExecutionState, ...]:
    return tuple(_CURRENT)


def consume_all_ai_executions() -> tuple[AiExecutionState, ...]:
    value = tuple(_CURRENT)
    _CURRENT.clear()
    return value


def consume_current_ai_execution() -> AiExecutionState | None:
    values = consume_all_ai_executions()
    return values[0] if values else None


def clear_current_ai_execution() -> None:
    _CURRENT.clear()


__all__ = [
    "AiExecutionState",
    "clear_current_ai_execution",
    "consume_all_ai_executions",
    "consume_current_ai_execution",
    "current_ai_executions",
    "set_current_ai_execution",
]
