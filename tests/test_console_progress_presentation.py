from __future__ import annotations

from types import SimpleNamespace

from rasai.console_progress_presentation import _public_stage_status
from rasai.execution_progress_presentation import _bar


def test_progress_bar_is_bounded_and_has_stable_width() -> None:
    empty = _bar(-10)
    half = _bar(50)
    full = _bar(120)

    assert empty == "[" + ("-" * 42) + "]"
    assert half == "[" + ("#" * 21) + ("-" * 21) + "]"
    assert full == "[" + ("#" * 42) + "]"
    assert len(empty) == len(half) == len(full) == 44


def test_terminal_console_stage_does_not_remain_in_progress() -> None:
    for logical, operation, expected in (
        ("COMPLETE", "LOCAL:DONE", "CONCLUÍDA"),
        ("COMPLETE_WITH_LIMITATIONS", "LOCAL:DONE", "CONCLUÍDA COM LIMITAÇÕES"),
        ("FAILED", "LOCAL:ERROR", "FALHA"),
    ):
        state = SimpleNamespace(status=logical, operation=operation)
        completed = SimpleNamespace(overall_exact=True, overall_percent=100.0, current_status="")
        assert _public_stage_status(state, completed) == expected
        pending = SimpleNamespace(overall_exact=False, overall_percent=97.0, current_status="EM EXECUÇÃO")
        assert _public_stage_status(state, pending) == "EM EXECUÇÃO"


def test_in_progress_pipeline_keeps_explicit_stage_status() -> None:
    state = SimpleNamespace(status="REPORTING", operation="LOCAL:REPORT")
    progress = SimpleNamespace(overall_exact=False, overall_percent=90.0, current_status="COLETANDO")
    assert _public_stage_status(state, progress) == "COLETANDO"
