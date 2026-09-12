from __future__ import annotations

from rasai.console_progress_presentation import _bar


def test_progress_bar_is_bounded_and_has_stable_width() -> None:
    empty = _bar(-10)
    half = _bar(50)
    full = _bar(120)

    assert empty == "[" + ("-" * 42) + "]"
    assert half == "[" + ("#" * 21) + ("-" * 21) + "]"
    assert full == "[" + ("#" * 42) + "]"
    assert len(empty) == len(half) == len(full) == 44
