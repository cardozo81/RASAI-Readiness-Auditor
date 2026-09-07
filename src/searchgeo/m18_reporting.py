"""Análise semântica por IA, roteamento e telemetria operational AI context for report.html and remediation.html."""

from __future__ import annotations

from html import escape
import json
import re
import sqlite3
from typing import Any

from searchgeo.persistence import AuditWorkspace


_CSS = """
<style>
.m18-ai{margin:2rem 0;padding:1.25rem;border:1px solid #d7dce2;border-radius:12px;background:#fff;min-width:0;max-width:100%}
.m18-ai h2,.m18-ai h3{margin-top:.25rem}.m18-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.75rem;margin:1rem 0}
.m18-metric{padding:.75rem;border:1px solid #e2e6ea;border-radius:8px;min-width:0}.m18-metric strong{display:block;font-size:.78rem;text-transform:uppercase;letter-spacing:.03em;margin-bottom:.3rem}
.m18-table-wrap{display:block;width:100%;max-width:100%;overflow-x:auto;overscroll-behavior-inline:contain}.m18-ai table{border-collapse:collapse;width:100%;min-width:1050px;font-size:.86rem}.m18-ai th,.m18-ai td{border-bottom:1px solid #e5e7eb;padding:.55rem;text-align:left;vertical-align:top;white-space:nowrap}
.m18-ai td.m18-error{max-width:28rem;overflow:hidden;text-overflow:ellipsis}.m18-note{font-size:.9rem;color:#4b5563}
@media(min-width:821px){.page.m15-main{box-sizing:border-box;width:calc(100% - var(--m15-sidebar));max-width:1280px;margin-right:0;min-width:0}}
@media(max-width:820px){.page.m15-main{width:100%;max-width:100%}}
</style>
"""


def enrich_report_html(html: str, *, audit_id: str, workspace: AuditWorkspace) -> str:
    session, attempts, snapshot_count = _load(audit_id, workspace)
    if session is None:
        return html
    html = _correct_legacy_ai_metrics(html, session, attempts)
    html = _insert_before_head_end(html, _CSS)
    return _insert_before_main_end_or_body(html, _report_section(session, attempts, snapshot_count))


def enrich_remediation_html(html: str, *, audit_id: str, workspace: AuditWorkspace) -> str:
    session, attempts, snapshot_count = _load(audit_id, workspace)
    if session is None:
        return html
    html = _insert_before_head_end(html, _CSS)
    return _insert_before_main_end_or_body(html, _remediation_context(session, attempts, snapshot_count))


def enrich_written_reports(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Enrich the two static Relatório HTML estático projections after they are materialized."""

    report = workspace.root / "report.html"
    remediation = workspace.root / "remediation.html"
    if report.is_file():
        report.write_text(enrich_report_html(report.read_text(encoding="utf-8"), audit_id=audit_id, workspace=workspace), encoding="utf-8")
    if remediation.is_file():
        remediation.write_text(enrich_remediation_html(remediation.read_text(encoding="utf-8"), audit_id=audit_id, workspace=workspace), encoding="utf-8")


def _provider_configured(session: sqlite3.Row) -> bool:
    return bool(session["enabled"]) and str(session["status"]) != "NOT_CONFIGURED"


def _correct_legacy_ai_metrics(html: str, session: sqlite3.Row, attempts: list[sqlite3.Row]) -> str:
    success = [row for row in attempts if row["status"] == "SUCCESS"]
    if success:
        usage = "SIM"
    elif attempts:
        usage = "TENTATIVA SEM SUCESSO"
    else:
        usage = "NÃO"
    html = re.sub(
        r"(<div class='metric'><small>Uso de IA</small><strong>)(.*?)(</strong></div>)",
        lambda match: match.group(1) + escape(usage) + match.group(3),
        html,
        count=1,
    )
    if success:
        models = sorted({str(row["model"]) for row in success if row["model"]})
        model_display = ", ".join(models) or "NÃO APLICÁVEL"
    elif str(session["status"]) == "NOT_CONFIGURED":
        model_display = str(session["initial_model"] or "NÃO CONFIGURADO") + " · PROVIDER NÃO CONFIGURADO"
    elif bool(session["enabled"]):
        model_display = str(session["initial_model"] or "CONFIGURADO · NÃO CONFIRMADO PELA API")
    else:
        model_display = "NÃO APLICÁVEL"
    html = re.sub(
        r"(<div class='metric'><small>Modelo</small><strong>)(.*?)(</strong></div>)",
        lambda match: match.group(1) + escape(model_display) + match.group(3),
        html,
        count=1,
    )
    return html


def _load(audit_id: str, workspace: AuditWorkspace) -> tuple[sqlite3.Row | None, list[sqlite3.Row], int]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            session = connection.execute("SELECT * FROM ai_audit_sessions WHERE audit_id=?", (audit_id,)).fetchone()
            attempts = list(connection.execute(
                "SELECT * FROM ai_provider_attempts WHERE audit_id=? ORDER BY started_at,attempt_index,attempt_id",
                (audit_id,),
            ).fetchall())
        except sqlite3.OperationalError:
            return None, [], 0
        snapshot_count = int(connection.execute(
            """SELECT COUNT(*) FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=?""",
            (audit_id,),
        ).fetchone()[0])
        return session, attempts, snapshot_count
    finally:
        connection.close()


def _report_section(session: sqlite3.Row, attempts: list[sqlite3.Row], snapshot_count: int) -> str:
    enabled = bool(session["enabled"])
    configured = _provider_configured(session)
    success = [row for row in attempts if row["status"] == "SUCCESS"]
    failures = [row for row in attempts if row["status"] != "SUCCESS"]
    provider_counts: dict[str, set[str]] = {}
    for row in success:
        provider_counts.setdefault(str(row["provider"]), set()).add(str(row["url"]))
    counts_html = "<br>".join(f"{escape(provider)}: {len(urls)}" for provider, urls in sorted(provider_counts.items())) or "NENHUMA"
    configured_chain = _json_list(session["configured_chain"])
    initial = _provider_label(session["initial_provider"], session["initial_model"])
    effective = _provider_label(session["effective_provider"], session["effective_model"])
    if not session["effective_provider"]:
        effective = "NÃO HOUVE RESULTADO SEMÂNTICO VÁLIDO"
    retry_count = sum(1 for row in attempts if _row_value(row, "decision") == "RETRY")
    fallback_used = any(_row_value(row, "fallback_from_provider") for row in attempts)
    failed_cost = sum(float(_row_value(row, "estimated_cost", 0.0) or 0.0) for row in failures)

    metrics = (
        _metric("IA habilitada pelo comando", "SIM" if enabled else "NÃO")
        + _metric("Provider configurado", "SIM" if configured else "NÃO")
        + _metric("Estratégia", str(session["strategy"]))
        + _metric("Provider que deveria atender primeiro", initial or "NÃO APLICÁVEL")
        + _metric("Provider efetivamente utilizado", effective)
        + _metric("Fallback utilizado", "SIM" if fallback_used else "NÃO")
        + _metric("Retries transitórios", str(retry_count))
        + _metric("Modelo efetivo", str(session["effective_model"] or "NÃO APLICÁVEL"))
        + _metric("Profundidade", str(session["effective_reasoning_profile"] or session["initial_reasoning_profile"] or "NÃO APLICÁVEL"))
        + _metric("Status", str(session["status"]))
        + _metric("Chamadas externas realizadas", str(len(attempts)))
        + _metric("Tentativas com sucesso", str(len(success)))
        + _metric("Custo estimado de tentativas sem sucesso", f"{failed_cost:.8f} USD" if failed_cost else "0 ou não mensurável")
        + _metric("URLs analisadas com sucesso por provider", counts_html)
    )
    chain = " → ".join(
        f"{escape(str(item.get('provider','?')))} / {escape(str(item.get('model','?')))}"
        for item in configured_chain if isinstance(item, dict)
    ) or "NENHUMA IA ELEGÍVEL"
    failover = _failover_summary(attempts)
    failure_detail = _failure_detail(attempts)
    rows = "".join(_attempt_row(row) for row in attempts)
    if not rows:
        rows = "<tr><td colspan='19'>Nenhuma chamada externa foi realizada.</td></tr>"
    coverage = f"{len(success)}/{snapshot_count} contextos Desktop/Mobile com tentativa bem-sucedida" if snapshot_count else "NÃO APLICÁVEL"
    return (
        "<section id='ai-runtime' class='m18-ai'>"
        "<h2>Uso de IA — execução, erros, retry e fallback</h2>"
        "<p class='m18-note'>Falhas de provider são limitações operacionais da auditoria; não são findings do website. Retry só ocorre para erro transitório, no máximo uma vez por provider/contexto; AUTO também possui teto global de chamadas.</p>"
        f"<div class='m18-grid'>{metrics}</div>"
        f"<p><strong>Cadeia inicial imutável:</strong> {chain}</p>"
        f"<p><strong>Cobertura semântica externa:</strong> {escape(coverage)}</p>"
        f"<p><strong>Fallback:</strong> {failover}</p>"
        f"{failure_detail}"
        "<h3>Relatório detalhado de uso da IA</h3><div class='m18-table-wrap'><table>"
        "<thead><tr><th>URL</th><th>Device</th><th>Operação</th><th>Tentativa</th><th>Provider</th><th>Model</th><th>Status</th><th>Error class</th><th>Error type</th><th>HTTP</th><th>Error code</th><th>Request ID</th><th>Retryable</th><th>Decisão</th><th>Fallback de</th><th>Tokens input</th><th>Tokens output</th><th>Estimated cost</th><th>Duration</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
        "<p class='m18-note'>Estimated cost usa catálogo versionado local e não representa invoice/billing. Uma tentativa falha pode ter custo quando o provider reporta tokens; quando não há telemetria suficiente, o relatório não inventa custo zero.</p>"
        "</section>"
    )

def _remediation_context(session: sqlite3.Row, attempts: list[sqlite3.Row], snapshot_count: int) -> str:
    success = [row for row in attempts if row["status"] == "SUCCESS"]
    effective = _provider_label(session["effective_provider"], session["effective_model"])
    coverage = f"{len(success)}/{snapshot_count} contextos Desktop/Mobile" if snapshot_count else "NÃO APLICÁVEL"
    limitations: list[str] = []
    if session["status"] == "CHAIN_EXHAUSTED":
        limitations.append("AI_PROVIDER_CHAIN_EXHAUSTED")
    if session["status"] == "NOT_CONFIGURED":
        limitations.append("provider de IA selecionado, mas sem configuração/credencial elegível")
    if any(row["status"] != "SUCCESS" for row in attempts):
        limitations.append("houve tentativa(s) de provider sem resultado válido")
    if not bool(session["enabled"]):
        limitations.append("IA externa desabilitada")
    return (
        "<section id='ai-remediation-context' class='m18-ai'>"
        "<h2>Contexto da análise semântica</h2>"
        f"<p><strong>Provider configurado:</strong> {'SIM' if _provider_configured(session) else 'NÃO'}</p>"
        f"<p><strong>Provider efetivo:</strong> {escape(effective or 'NENHUM')}</p>"
        f"<p><strong>Chamadas externas:</strong> {len(attempts)}</p>"
        f"<p><strong>Cobertura semântica:</strong> {escape(coverage)}</p>"
        f"<p><strong>Limitações:</strong> {escape('; '.join(limitations) if limitations else 'NENHUMA LIMITAÇÃO DE PROVIDER COM IMPACTO DE COBERTURA')}</p>"
        "<p class='m18-note'>Este bloco é informativo. Falha de IA não é atribuída ao website e não cria finding nem recommendation GEO.</p>"
        "</section>"
    )


def _metric(label: str, value: str) -> str:
    # counts_html may intentionally contain <br>; all other values are escaped before input.
    safe_value = value if "<br>" in value else escape(value)
    return f"<div class='m18-metric'><strong>{escape(label)}</strong><span>{safe_value}</span></div>"


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    try:
        keys = row.keys()
    except AttributeError:
        keys = row
    try:
        if key in keys:
            return row[key]
    except (KeyError, TypeError):
        pass
    return default


def _operation(row: Any) -> str:
    contract = str(_row_value(row, "semantic_contract_version", "") or "")
    return "Remediação textual" if contract.startswith("M20-") else "Análise semântica"


def _attempt_row(row: sqlite3.Row) -> str:
    cost = "—"
    if _row_value(row, "estimated_cost") is not None:
        cost = f"{float(_row_value(row, 'estimated_cost')):.8f} {_row_value(row, 'cost_currency', '') or ''}".strip()
    retryable = "SIM" if bool(_row_value(row, "retry_eligible", 0)) else "NÃO"
    return (
        "<tr>"
        f"<td title='{escape(str(row['url']))}'>{escape(_truncate(str(row['url']), 72))}</td>"
        f"<td>{escape(str(row['device'] or '—'))}</td>"
        f"<td>{escape(_operation(row))}</td>"
        f"<td>{escape(str(row['attempt_index']))}</td>"
        f"<td>{escape(str(row['provider']))}</td>"
        f"<td>{escape(str(row['model'] or '—'))}</td>"
        f"<td>{escape(str(row['status']))}</td>"
        f"<td>{escape(str(_row_value(row, 'error_class', '—') or '—'))}</td>"
        f"<td>{escape(str(_row_value(row, 'error_type', '—') or '—'))}</td>"
        f"<td>{escape(str(_row_value(row, 'http_status', '—') or '—'))}</td>"
        f"<td>{escape(str(_row_value(row, 'error_code', '—') or '—'))}</td>"
        f"<td>{escape(str(_row_value(row, 'request_id', '—') or '—'))}</td>"
        f"<td>{retryable}</td>"
        f"<td>{escape(str(_row_value(row, 'decision', '—') or '—'))}</td>"
        f"<td>{escape(str(_row_value(row, 'fallback_from_provider', '—') or '—'))}</td>"
        f"<td>{_nullable(_row_value(row, 'input_tokens'))}</td>"
        f"<td>{_nullable(_row_value(row, 'output_tokens'))}</td>"
        f"<td>{escape(cost)}</td>"
        f"<td>{int(row['duration_ms'])} ms</td>"
        "</tr>"
    )


def _failure_detail(attempts: list[sqlite3.Row]) -> str:
    failures = [row for row in attempts if str(row["status"]) != "SUCCESS"]
    if not failures:
        return "<p><strong>Diagnóstico:</strong> nenhuma falha de integração de IA registrada.</p>"
    items: list[str] = []
    for row in failures[:12]:
        parts = [
            f"{row['provider']}/{row['model'] or '—'}",
            str(_row_value(row, "error_class", row["status"]) or row["status"]),
        ]
        if _row_value(row, "error_type"):
            parts.append(f"type={_row_value(row, 'error_type')}")
        if _row_value(row, "http_status"):
            parts.append(f"HTTP={_row_value(row, 'http_status')}")
        if _row_value(row, "error_code"):
            parts.append(f"code={_row_value(row, 'error_code')}")
        parts.append(f"retryable={'SIM' if bool(_row_value(row, 'retry_eligible', 0)) else 'NÃO'}")
        parts.append(f"decisão={_row_value(row, 'decision', 'STOP')}")
        items.append("<li>" + escape(" · ".join(parts)) + "</li>")
    return (
        "<div class='m18-note'><strong>Diagnóstico das falhas:</strong><ul>"
        + "".join(items)
        + "</ul><p>Erros de autenticação, permissão, crédito, quota, modelo e contrato não são repetidos automaticamente. Erros transitórios podem ter uma única nova tentativa.</p></div>"
    )


def _failover_summary(attempts: list[sqlite3.Row]) -> str:
    events: list[str] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in attempts:
        source = str(_row_value(row, "fallback_from_provider", "") or "")
        if not source:
            continue
        target = str(row["provider"])
        reason = str(_row_value(row, "fallback_reason", "AI_PROVIDER_UNAVAILABLE") or "AI_PROVIDER_UNAVAILABLE")
        outcome = str(row["status"])
        key = (source, target, reason, str(row["url"]))
        if key in seen:
            continue
        seen.add(key)
        events.append(f"{source} deveria atender o contexto, falhou por {reason}; fallback para {target} ({outcome})")
    if events:
        return escape("; ".join(events))

    # Compatibility for pre-migration audit DBs.
    by_context: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in attempts:
        by_context.setdefault((str(row["url"]), str(row["device"])), []).append(row)
    legacy: list[str] = []
    for rows in by_context.values():
        successful = next((row for row in rows if row["status"] == "SUCCESS"), None)
        failed = [row for row in rows if row["status"] != "SUCCESS"]
        if successful and failed and str(successful["provider"]) != str(failed[0]["provider"]):
            legacy.append(f"{failed[0]['provider']} falhou; fallback para {successful['provider']}")
    return escape("; ".join(legacy)) if legacy else "NÃO OCORREU"

def _provider_label(provider: Any, model: Any) -> str:
    if not provider:
        return ""
    return f"{provider} / {model}" if model else str(provider)


def _nullable(value: Any) -> str:
    return "—" if value is None else escape(str(value))


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _insert_before_head_end(html: str, block: str) -> str:
    marker = "</head>"
    if marker in html:
        return html.replace(marker, block + marker, 1)
    return block + html


def _insert_before_main_end_or_body(html: str, block: str) -> str:
    main_marker = "</main>"
    if main_marker in html:
        return html.replace(main_marker, block + main_marker, 1)
    body_marker = "</body>"
    if body_marker in html:
        return html.replace(body_marker, block + body_marker, 1)
    return html + block
