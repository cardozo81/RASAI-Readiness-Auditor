"""Process-local handoff of AI execution telemetry to the final HTML projection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rasai.ai_exchange_log import AiExchangeRecorder


@dataclass(frozen=True, slots=True)
class AiExecutionState:
    provider: Any
    recorder: AiExchangeRecorder


_CURRENT: AiExecutionState | None = None


def set_current_ai_execution(provider: Any, recorder: AiExchangeRecorder) -> None:
    global _CURRENT
    _CURRENT = AiExecutionState(provider=provider, recorder=recorder)


def consume_current_ai_execution() -> AiExecutionState | None:
    global _CURRENT
    value = _CURRENT
    _CURRENT = None
    return value


def clear_current_ai_execution() -> None:
    global _CURRENT
    _CURRENT = None
