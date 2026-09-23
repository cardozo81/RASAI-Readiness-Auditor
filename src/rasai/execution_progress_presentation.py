"""Canonical execution-progress presentation shared by local console workflows.

This module is presentation-only. It renders truthful stage context supplied by the
runtime/consolidation layers and never changes collectors, retries, scoring, report
generation or persistence.
"""
from __future__ import annotations

from typing import Any, Iterable

from rasai.console_ui import CYAN, GRAY, GREEN, RED, YELLOW, paint

_WIDTH = 100
_BAR_WIDTH = 42


def _bar(percent: float) -> str:
    bounded = min(max(float(percent), 0.0), 100.0)
    filled = int(round((_BAR_WIDTH * bounded) / 100.0))
    return "[" + ("#" * filled) + ("-" * (_BAR_WIDTH - filled)) + "]"


def _stage_position(index: int | None, count: int | None, *, planned: bool) -> str:
    if index is None or count is None or count <= 0:
        return "-"
    suffix = " previstas" if planned else ""
    return f"{max(index, 1)} de {max(count, 1)}{suffix}"


def _row(label: str, value: Any) -> None:
    print(f"{label:<21}: {value}")


def _semantic_status_color(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if any(
        token in normalized
        for token in ("CONCLU", "COMPLETE", "SUCCESS", "READY", "PRONTA", "REUSED", "REUTIL", "APTO")
    ):
        return GREEN
    if any(token in normalized for token in ("FALHA", "FAIL", "ERROR", "BLOCK", "INDISPON", "CRITICAL")):
        return RED
    if any(token in normalized for token in ("NÃO SOLICIT", "NAO SOLICIT", "NOT_REQUESTED", "DESABIL", "DISABLED")):
        return GRAY
    if any(token in normalized for token in ("AGUARD", "PEND", "PARCIAL", "LIMIT", "RETRY", "NÃO ELEG", "NAO ELEG")):
        return YELLOW
    if any(token in normalized for token in ("EXECU", "PROCESS", "RUNNING", "ANAL", "REPORT", "COLET")):
        return YELLOW
    return CYAN


def _detail_value(label: str, value: Any) -> Any:
    raw_label = str(label).strip().casefold()
    raw_value = str(value)
    if raw_label in {"estado", "status", "situação", "situacao"}:
        return paint(raw_value, _semantic_status_color(raw_value), bold=True)
    if "não eleg" in raw_label or "nao eleg" in raw_label or "fora da" in raw_label:
        return paint(raw_value, YELLOW, bold=True)
    if "elegí" in raw_label or "elegi" in raw_label or "sucesso" in raw_label or "resolvido" in raw_label:
        return paint(raw_value, GREEN, bold=True)
    if any(token in raw_label for token in ("restante", "pendente", "problema", "custo")):
        return paint(raw_value, YELLOW, bold=True)
    if any(token in raw_label for token in ("provider", "modelo", "integração", "integracao", "requisito atual")):
        return paint(raw_value, CYAN, bold=True)
    if raw_label == "nova coleta da url" and raw_value.strip().upper() == "NÃO":
        return paint(raw_value, GREEN, bold=True)
    return value


def render_canonical_progress(
    *,
    current_label: str,
    current_status: str = "EM EXECUÇÃO",
    stage_index: int | None = None,
    stage_count: int | None = None,
    stage_count_planned: bool = True,
    previous_label: str | None = None,
    previous_status: str = "CONCLUÍDA",
    next_label: str | None = None,
    next_status: str = "AGUARDANDO",
    stage_percent: float | None = None,
    stage_exact: bool = False,
    overall_percent: float | None = None,
    overall_exact: bool = False,
    message: str = "",
    detail_rows: Iterable[tuple[str, Any]] = (),
    width: int = _WIDTH,
) -> None:
    """Render the canonical stage/pipeline block without clearing the terminal."""
    print("PROGRESSO DO PIPELINE")
    print("-" * width)
    _row(
        "Etapa",
        paint(_stage_position(stage_index, stage_count, planned=stage_count_planned), CYAN, bold=True),
    )
    _row(
        "Anterior",
        paint(
            f"{previous_label}  {previous_status}",
            _semantic_status_color(previous_status),
        )
        if previous_label
        else "-",
    )
    _row(
        "Atual",
        paint(
            f"{current_label}  {current_status}",
            _semantic_status_color(current_status),
            bold=True,
        ),
    )
    _row(
        "Próxima",
        paint(
            f"{next_label}  {next_status}",
            GRAY if "AGUARD" in str(next_status).upper() else _semantic_status_color(next_status),
        )
        if next_label
        else "-",
    )

    if stage_percent is None:
        _row(
            "Andamento da etapa",
            paint(
                "em execução [sem unidade interna mensurável]",
                _semantic_status_color(current_status),
                bold=True,
            ),
        )
    else:
        prefix = "" if stage_exact else "~"
        qualifier = "medido na etapa" if stage_exact else "estimado dentro da etapa"
        stage_color = (
            GREEN
            if stage_exact and float(stage_percent) >= 100.0
            else _semantic_status_color(current_status)
        )
        _row(
            "Andamento da etapa",
            paint(
                f"{_bar(stage_percent)} {prefix}{stage_percent:.0f}% [{qualifier}]",
                stage_color,
                bold=True,
            ),
        )

    if overall_percent is None:
        _row("Pipeline total", paint("indisponível", GRAY))
    else:
        prefix = "" if overall_exact else "~"
        qualifier = "medido" if overall_exact else "projeção"
        overall_color = GREEN if overall_exact and float(overall_percent) >= 100.0 else CYAN
        _row(
            "Pipeline total",
            paint(
                f"{_bar(overall_percent)} {prefix}{overall_percent:.0f}% [{qualifier}]",
                overall_color,
                bold=True,
            ),
        )
    print("=" * width)

    rows = tuple((str(label), value) for label, value in detail_rows if str(label).strip())
    if not message and not rows:
        return

    print("DETALHES DA ETAPA ATUAL")
    print("-" * width)
    for label, value in rows:
        _row(label, _detail_value(label, value))
    if message:
        _row(
            "Executando",
            paint(message, _semantic_status_color(current_status), bold=True),
        )
    print("=" * width)
