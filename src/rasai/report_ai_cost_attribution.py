"""Reconcile persisted AI telemetry with the HTML report surfaces that own it.

The renderer is deliberately read-only. It never estimates missing provider usage,
never calls a provider, and never changes audit evidence or scoring. Each external AI
attempt is assigned to exactly one primary report surface so per-report costs can be
summed back to the audit total without double counting data reused by other reports.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path
import re
import sqlite3
from typing import Any

from rasai.persistence import AuditWorkspace
from rasai.report_contract import REPORT_SURFACES

_AI_USAGE_FILE = "ai-usage.html"
_CARD_MARKER = "data-ai-cost-attribution='true'"
_ROLLUP_MARKER = "data-ai-cost-rollup='true'"


@dataclass(frozen=True, slots=True)
class _Attempt:
    source: str
    attempt_id: str
    report_file: str
    url: str
    device: str
    provider: str
    model: str
    contract: str
    status: str
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    total_tokens: int | None
    estimated_cost: float | None
    currency: str


@dataclass(frozen=True, slots=True)
class _Usage:
    attempts: int
    successes: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    token_unknown: int
    costs: dict[str, float]
    cost_unknown: int


def enrich_ai_cost_attribution(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Add one standardized AI-cost card to every HTML report and a reconciled rollup."""
    report_dir = workspace.root / "report"
    if not report_dir.is_dir():
        return

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        attempts = _collect_attempts(connection, audit_id)
    finally:
        connection.close()

    by_report: dict[str, list[_Attempt]] = defaultdict(list)
    for attempt in attempts:
        by_report[attempt.report_file].append(attempt)

    for path in sorted(report_dir.glob("*.html")):
        if not path.is_file():
            continue
        html = _read(path)
        if html is None:
            continue
        if path.name == _AI_USAGE_FILE:
            updated = _rewrite_ai_usage(html, attempts, by_report)
        else:
            updated = _rewrite_report(html, path.name, by_report.get(path.name, ()))
        if updated != html:
            path.write_text(updated, encoding="utf-8", newline="\n")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _expr(columns: set[str], name: str, *, alias: str | None = None) -> str:
    target = alias or name
    return f"{name} AS {target}" if name in columns else f"NULL AS {target}"


def _fetch_attempt_rows(
    connection: sqlite3.Connection,
    *,
    table: str,
    audit_id: str,
    contract_column: str,
) -> list[sqlite3.Row]:
    columns = _columns(connection, table)
    if not columns or "audit_id" not in columns:
        return []
    selected = [
        _expr(columns, "attempt_id"),
        _expr(columns, "url"),
        _expr(columns, "device"),
        _expr(columns, "provider"),
        _expr(columns, "model"),
        _expr(columns, contract_column, alias="contract"),
        _expr(columns, "status"),
        _expr(columns, "input_tokens"),
        _expr(columns, "cached_input_tokens"),
        _expr(columns, "output_tokens"),
        _expr(columns, "reasoning_tokens"),
        _expr(columns, "total_tokens"),
        _expr(columns, "estimated_cost"),
        _expr(columns, "cost_currency"),
    ]
    return list(
        connection.execute(
            f"SELECT {','.join(selected)} FROM {table} WHERE audit_id=? ORDER BY rowid",
            (audit_id,),
        ).fetchall()
    )


def _collect_attempts(connection: sqlite3.Connection, audit_id: str) -> tuple[_Attempt, ...]:
    collected: list[_Attempt] = []
    for source, table, contract_column in (
        ("runtime", "ai_provider_attempts", "semantic_contract_version"),
        ("content", "content_remediation_attempts", "contract_version"),
    ):
        for row in _fetch_attempt_rows(
            connection,
            table=table,
            audit_id=audit_id,
            contract_column=contract_column,
        ):
            contract = str(row["contract"] or "")
            device = str(row["device"] or "")
            collected.append(
                _Attempt(
                    source=source,
                    attempt_id=str(row["attempt_id"] or ""),
                    report_file=_owner_report(source=source, contract=contract, device=device),
                    url=str(row["url"] or "-"),
                    device=device or "-",
                    provider=str(row["provider"] or "-"),
                    model=str(row["model"] or "-"),
                    contract=contract or "não informado",
                    status=str(row["status"] or "UNKNOWN"),
                    input_tokens=_int_or_none(row["input_tokens"]),
                    cached_input_tokens=_int_or_none(row["cached_input_tokens"]),
                    output_tokens=_int_or_none(row["output_tokens"]),
                    reasoning_tokens=_int_or_none(row["reasoning_tokens"]),
                    total_tokens=_int_or_none(row["total_tokens"]),
                    estimated_cost=_float_or_none(row["estimated_cost"]),
                    currency=str(row["cost_currency"] or "USD"),
                )
            )
    return tuple(collected)


def _owner_report(*, source: str, contract: str, device: str) -> str:
    """Return the single report that owns one AI attempt for additive reconciliation."""
    if source == "content":
        return "content-suggestions.html"
    normalized = contract.upper()
    if "IMPROVEMENT-INTELLIGENCE" in normalized:
        return "improvement-intelligence.html"
    if normalized.startswith("M24-") or "CRAWL" in normalized or "ROBOTS" in normalized:
        return "crawling-discovery.html"
    if "SOURCE-QUALITY" in normalized:
        return "context.html"
    if "COMPETITIVE" in normalized or "SEARCH-INTELLIGENCE" in normalized:
        return "search-intelligence.html"
    if normalized.startswith("M18-") or "SEMANTIC" in normalized:
        normalized_device = device.upper()
        if normalized_device == "MOBILE":
            return "mobile.html"
        if normalized_device == "DESKTOP":
            return "desktop.html"
        return "readiness.html"
    # Unknown/future contracts remain visible and reconciled instead of disappearing.
    return "index.html"


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _usage(attempts: Any) -> _Usage:
    rows = tuple(attempts)
    costs: dict[str, float] = {}
    successes = token_unknown = cost_unknown = 0
    token_sums = {"input": 0, "cache": 0, "output": 0, "reasoning": 0, "total": 0}
    for row in rows:
        if row.status.upper() == "SUCCESS":
            successes += 1
        for key, value in (
            ("input", row.input_tokens),
            ("cache", row.cached_input_tokens),
            ("output", row.output_tokens),
            ("reasoning", row.reasoning_tokens),
            ("total", row.total_tokens),
        ):
            if value is not None:
                token_sums[key] += value
        if row.total_tokens is None:
            token_unknown += 1
        if row.estimated_cost is None:
            cost_unknown += 1
        else:
            costs[row.currency] = costs.get(row.currency, 0.0) + row.estimated_cost
    return _Usage(
        attempts=len(rows),
        successes=successes,
        input_tokens=token_sums["input"],
        cached_input_tokens=token_sums["cache"],
        output_tokens=token_sums["output"],
        reasoning_tokens=token_sums["reasoning"],
        total_tokens=token_sums["total"],
        token_unknown=token_unknown,
        costs=costs,
        cost_unknown=cost_unknown,
    )


def _format_cost(usage: _Usage) -> str:
    if usage.costs:
        text = " + ".join(f"{value:.8f} {currency}" for currency, value in sorted(usage.costs.items()))
        return text + (f" + {usage.cost_unknown} tentativa(s) sem custo mensurável" if usage.cost_unknown else "")
    if usage.attempts:
        return "Não mensurável pelo provider"
    return "0 · sem chamadas"


def _metric(label: str, value: str) -> str:
    return f"<div class='metric'><small>{escape(label)}</small><strong>{escape(value)}</strong></div>"


def _usage_metrics(usage: _Usage) -> str:
    total = f"{usage.total_tokens:,}".replace(",", ".")
    if usage.token_unknown:
        total += f" + {usage.token_unknown} tentativa(s) sem total retornado"
    return "".join(
        (
            _metric("Tentativas de IA", str(usage.attempts)),
            _metric("Respostas aceitas", str(usage.successes)),
            _metric("Tokens de entrada", f"{usage.input_tokens:,}".replace(",", ".")),
            _metric("Tokens de entrada em cache", f"{usage.cached_input_tokens:,}".replace(",", ".")),
            _metric("Tokens de saída", f"{usage.output_tokens:,}".replace(",", ".")),
            _metric("Reasoning tokens", f"{usage.reasoning_tokens:,}".replace(",", ".")),
            _metric("Tokens totais", total),
            _metric("Custo financeiro estimado", _format_cost(usage)),
        )
    )


def _report_label(filename: str) -> str:
    for surface in REPORT_SURFACES:
        if surface.filename == filename:
            return surface.label
    return filename


def _standard_card(filename: str, attempts: Any) -> str:
    usage = _usage(attempts)
    badge = "Com consumo IA" if usage.attempts else "Sem consumo IA direto"
    explanation = (
        "Atribuição primária e aditiva: cada tentativa externa pertence a um único relatório, "
        "mesmo quando a evidência resultante é reutilizada em outras páginas. Isso evita dupla contagem."
    )
    zero_note = (
        "<div class='notice'><strong>Nenhum consumo direto de IA atribuído a este relatório.</strong> "
        "A página pode projetar dados produzidos em outra etapa; nesse caso o custo permanece atribuído à superfície que originou a chamada.</div>"
        if usage.attempts == 0
        else ""
    )
    return (
        f"<section class='panel ai-cost-attribution' {_CARD_MARKER}>"
        "<div class='panel-head'><div><div class='kicker'>Transparência de consumo</div>"
        f"<h2>Consumo de IA atribuído a esta página</h2></div><span class='badge info'>{escape(badge)}</span></div>"
        f"<p class='intro'>{escape(explanation)}</p>"
        f"<div class='metric-grid'>{_usage_metrics(usage)}</div>{zero_note}"
        "<details><summary>Como interpretar custo e tokens</summary><div class='detail-body'>"
        "<p>Custo é estimativa operacional baseada na telemetria e tabela de preços persistidas; não substitui billing/invoice do provider. "
        "Tentativas sem usage/custo retornado não recebem valor inferido. Reasoning tokens, quando reportados, são subconjunto de output e não devem ser somados novamente ao total.</p>"
        f"<p><strong>Superfície:</strong> <code>{escape(filename)}</code> · {escape(_report_label(filename))}.</p>"
        "</div></details></section>"
    )


def _strip_injected(html: str, marker: str) -> str:
    pattern = re.compile(
        rf"<section\b[^>]*{re.escape(marker)}[^>]*>.*?</section>",
        flags=re.DOTALL,
    )
    return pattern.sub("", html)


def _insert_before_end(html: str, section: str) -> str:
    if "</main>" in html:
        return html.replace("</main>", section + "</main>", 1)
    if "</body>" in html:
        return html.replace("</body>", section + "</body>", 1)
    return html + section


def _rewrite_report(html: str, filename: str, attempts: Any) -> str:
    html = _strip_injected(html, _CARD_MARKER)
    return _insert_before_end(html, _standard_card(filename, attempts))


def _group_detail_rows(attempts: tuple[_Attempt, ...]) -> str:
    grouped: dict[tuple[str, str, str, str, str], list[_Attempt]] = defaultdict(list)
    for row in attempts:
        grouped[(row.url, row.device, row.contract, row.provider, row.model)].append(row)
    rows: list[str] = []
    for (url, device, contract, provider, model), values in sorted(grouped.items()):
        usage = _usage(values)
        rows.append(
            "<tr>"
            f"<td class='mono'>{escape(url)}</td><td>{escape(device)}</td>"
            f"<td>{escape(contract)}</td><td>{escape(provider)} · {escape(model)}</td>"
            f"<td>{usage.attempts}</td><td>{usage.successes}</td>"
            f"<td>{usage.input_tokens}</td><td>{usage.cached_input_tokens}</td>"
            f"<td>{usage.output_tokens}</td><td>{usage.reasoning_tokens}</td><td>{usage.total_tokens}</td>"
            f"<td>{escape(_format_cost(usage))}</td>"
            "</tr>"
        )
    return "".join(rows)


def _report_breakdown(by_report: dict[str, list[_Attempt]]) -> str:
    blocks: list[str] = []
    for surface in REPORT_SURFACES:
        attempts = tuple(by_report.get(surface.filename, ()))
        if not attempts:
            continue
        usage = _usage(attempts)
        blocks.append(
            "<details class='ai-cost-report-detail'>"
            f"<summary>{escape(surface.label)} · {usage.attempts} tentativa(s) · {escape(_format_cost(usage))}</summary>"
            "<div class='detail-body'><div class='metric-grid'>"
            f"{_usage_metrics(usage)}</div>"
            "<div class='table-wrap'><table><thead><tr>"
            "<th>URL auditada</th><th>Dispositivo</th><th>Contrato/finalidade</th><th>Provider/modelo</th>"
            "<th>Tentativas</th><th>Sucessos</th><th>Input</th><th>Cache</th><th>Output</th><th>Reasoning</th><th>Total</th><th>Custo</th>"
            "</tr></thead><tbody>"
            f"{_group_detail_rows(attempts)}"
            "</tbody></table></div></div></details>"
        )
    return "".join(blocks)


def _rewrite_ai_usage(
    html: str,
    attempts: tuple[_Attempt, ...],
    by_report: dict[str, list[_Attempt]],
) -> str:
    html = _strip_injected(html, _ROLLUP_MARKER)
    total = _usage(attempts)
    zero_reports = [
        surface.label for surface in REPORT_SURFACES
        if surface.filename != _AI_USAGE_FILE and not by_report.get(surface.filename)
    ]
    zero_text = " · ".join(escape(label) for label in zero_reports) or "Nenhum"
    breakdown = _report_breakdown(by_report)
    if not breakdown:
        breakdown = "<div class='notice'>Nenhuma tentativa externa de IA foi persistida para esta auditoria.</div>"
    section = (
        f"<section class='panel ai-cost-rollup' {_ROLLUP_MARKER}>"
        "<div class='panel-head'><div><div class='kicker'>Conciliação financeira e de tokens</div>"
        "<h2>Total de IA e detalhamento por página</h2></div><span class='badge info'>Total reconciliado</span></div>"
        "<p class='intro'>Este total considera todas as tentativas externas persistidas em <code>ai_provider_attempts</code> e "
        "<code>content_remediation_attempts</code>. Cada tentativa é atribuída a exatamente uma página proprietária, de modo que a soma do detalhamento fecha com o total sem duplicação.</p>"
        f"<div class='metric-grid'>{_usage_metrics(total)}</div>"
        "<h3>Detalhamento expansível por página</h3>"
        f"{breakdown}"
        "<details><summary>Páginas sem consumo direto atribuído</summary><div class='detail-body'>"
        f"<p>{zero_text}</p><p>Essas páginas podem reutilizar evidências de IA geradas em outra superfície; esse reaproveitamento não é cobrado novamente no detalhamento.</p>"
        "</div></details>"
        "<div class='notice'><strong>Regra de conciliação:</strong> custo e tokens deste bloco vêm apenas da telemetria persistida. "
        "Valores ausentes não são inferidos. Reasoning tokens não são adicionados novamente a output/total.</div>"
        "</section>"
    )
    return _insert_before_end(html, section)
