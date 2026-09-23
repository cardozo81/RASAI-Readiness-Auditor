"""Visual-only polish for selective reprocessing preparation and cost preview.

This layer does not change retry eligibility, pricing, routing, persistence or fulfillment.
It only makes the already computed facts easier to scan in the interactive console.
"""
from __future__ import annotations

from typing import Any

_INSTALLED = False
_LABEL_WIDTH = 22
_VALUE_WIDTH = 75
_WIDTH = 100


def _section(title: str) -> None:
    from rasai.console_ui import CYAN, DIM, paint

    print("\n" + paint(title, CYAN, bold=True))
    print(paint("-" * _WIDTH, DIM))


def _field(label: str, value: Any) -> None:
    from rasai.console_ui import GRAY, paint

    padded = f"{label:<{_LABEL_WIDTH}}"
    print(f"{paint(padded, GRAY)} : {value}")


def _wrapped_field(label: str, value: Any) -> None:
    from textwrap import wrap

    from rasai.console_ui import GRAY, paint

    text = str(value or "-").strip() or "-"
    lines = wrap(text, width=_VALUE_WIDTH, break_long_words=False, break_on_hyphens=False) or ["-"]
    padded = f"{label:<{_LABEL_WIDTH}}"
    print(f"{paint(padded, GRAY)} : {lines[0]}")
    continuation = " " * (_LABEL_WIDTH + 3)
    for line in lines[1:]:
        print(f"{continuation}{line}")


def _conditional_ai_cost_preview(
    final: Any,
    pending: tuple[Any, ...],
    downstream: tuple[str, ...],
) -> None:
    from rasai.console_ui import YELLOW, paint

    non_ai_components = tuple(
        dict.fromkeys(str(getattr(item, "component", "") or "-") for item in pending)
    )
    _section("PREVISÃO DE CUSTO DE IA")
    _field("Previsão", paint("IA CONDICIONAL — CUSTO AINDA NÃO DETERMINÁVEL", YELLOW, bold=True))
    _field("Chamadas IA imediatas", "0")
    _field("Custo IA garantido", "não é possível garantir custo zero antes da recuperação")
    if non_ai_components:
        _wrapped_field("Pendências atuais", ", ".join(non_ai_components))
    _wrapped_field("IA potencial", ", ".join(downstream))
    _wrapped_field(
        "Critério",
        "a pendência atual pode alterar evidência persistida; somente após a recuperação o RASAi saberá "
        "quais análises dependentes ficaram obsoletas e precisam de nova chamada de IA",
    )


def _zero_ai_cost_preview(final: Any, pending: tuple[Any, ...]) -> None:
    from rasai.console_ui import GREEN, paint

    non_ai_components = tuple(
        dict.fromkeys(str(getattr(item, "component", "") or "-") for item in pending)
    )
    _section("PREVISÃO DE CUSTO DE IA")
    _field("Previsão", paint("CUSTO ZERO — ESCOPO SEM IA", GREEN, bold=True))
    _field("Chamadas IA previstas", "0")
    _field("Custo IA previsto", paint("0 (zero)", GREEN, bold=True))
    _field("Confiança", paint("EXATA PARA O ESCOPO ATUAL", GREEN, bold=True))
    if non_ai_components:
        _wrapped_field("Pendências sem IA", ", ".join(non_ai_components))
    _wrapped_field(
        "Critério",
        "nenhum requisito de IA está pendente; portanto esta tentativa não fará chamada de IA e não terá custo incremental de IA",
    )


def install() -> None:
    """Install after the final reprocess owner so only presentation globals are rebound."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import console_reprocess_final_refinements as final

    original_cost_preview = final._render_reprocess_cost_preview

    def render_cost_preview(state: Any, audit_id: str, pending: tuple[Any, ...]) -> None:
        pending_ai_items = tuple(
            item
            for item in pending
            if str(getattr(item, "component", "")).upper() in final._AI_COMPONENTS
            and str(getattr(item, "status", "")).upper() not in final._EXCLUDED_STATUSES
        )
        if not pending_ai_items:
            downstream = final._conditional_ai_dependencies(state, audit_id, pending)
            if downstream:
                _conditional_ai_cost_preview(final, pending, downstream)
            else:
                _zero_ai_cost_preview(final, pending)
            return
        original_cost_preview(state, audit_id, pending)

    final._section = _section
    final._field = _field
    final._wrapped_field = _wrapped_field
    final._render_reprocess_cost_preview = render_cost_preview
    _INSTALLED = True
