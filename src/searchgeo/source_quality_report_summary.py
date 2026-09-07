"""Analyst-facing blocked-source summary for every generated audit report page.

This module does not change acquisition, scoring, TLS validation, or measurement
policies. It only makes a definitive source blocker explicit and traceable after
all report pages and downstream Web Performance externo/Synthetic Navigation Apdex states have been materialized.
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any

from searchgeo.operational_log import try_append_operational_event
from searchgeo.persistence import AuditWorkspace
from searchgeo.source_quality import (
    SOURCE_QUALITY_AI_ARTIFACT,
    SOURCE_QUALITY_ARTIFACT,
    SourceQualityAssessment,
    load_assessment,
)
from searchgeo.source_quality_browser import SOURCE_QUALITY_PREFLIGHT_ARTIFACT


SUMMARY_MARKER_START = "<!-- searchgeo-source-blocker-summary:start -->"
SUMMARY_MARKER_END = "<!-- searchgeo-source-blocker-summary:end -->"


def enrich_source_quality_blocker_summary(*, audit_id: str, workspace: AuditWorkspace) -> Path | None:
    """Add a prominent diagnostic summary when the source remains hard blocked.

    The summary is intentionally repeated on every HTML page so analysts do not
    misread unavailable/partial metrics as ordinary low scores. Full technical
    evidence remains in ``audit.log`` and the structured source-quality artifacts.
    """

    assessment = load_assessment(workspace)
    if assessment is None or not assessment.all_pages_hard_blocked:
        return None

    ai_payload = _read_json(workspace.root / SOURCE_QUALITY_AI_ARTIFACT)
    measurements = _measurement_state(workspace.database)
    browser = _browser_state(workspace.database)
    block = _build_block(
        assessment=assessment,
        ai_payload=ai_payload,
        measurements=measurements,
        browser=browser,
    )

    report_dir = workspace.root / "report"
    if not report_dir.is_dir():
        return None

    for path in sorted(report_dir.glob("*.html")):
        try:
            html = path.read_text(encoding="utf-8")
        except OSError:
            continue
        html = _replace_or_insert(html, block)
        path.write_text(html, encoding="utf-8", newline="\n")

    _append_diagnostic_event_once(
        audit_id=audit_id,
        workspace=workspace,
        assessment=assessment,
        measurements=measurements,
        browser=browser,
        ai_payload=ai_payload,
    )
    index = report_dir / "index.html"
    return index if index.is_file() else None


def _replace_or_insert(html: str, block: str) -> str:
    if SUMMARY_MARKER_START in html and SUMMARY_MARKER_END in html:
        start = html.index(SUMMARY_MARKER_START)
        end = html.index(SUMMARY_MARKER_END, start) + len(SUMMARY_MARKER_END)
        return html[:start] + block + html[end:]
    if "</header>" in html:
        return html.replace("</header>", "</header>" + block, 1)
    main = html.find("<main")
    if main >= 0:
        marker_end = html.find(">", main)
        if marker_end >= 0:
            return html[: marker_end + 1] + block + html[marker_end + 1 :]
    return html


def _build_block(
    *,
    assessment: SourceQualityAssessment,
    ai_payload: dict[str, Any] | None,
    measurements: dict[str, Any],
    browser: list[dict[str, Any]],
) -> str:
    issue = next((item for item in assessment.issues if item.hard_blocker), assessment.issues[0])
    actions = "".join(f"<li>{escape(item)}</li>" for item in issue.recommended_actions)

    web = measurements.get("web_performance") or {}
    apdex = measurements.get("synthetic_apdex") or {}
    impact_items = [
        (
            "Web Performance",
            _measurement_text(
                status=web.get("status"),
                attempts=web.get("attempts"),
                reason=web.get("reason"),
                unit="tentativa(s) externa(s)",
            ),
        ),
        (
            "Synthetic Apdex",
            _measurement_text(
                status=apdex.get("status"),
                attempts=apdex.get("attempts"),
                reason=apdex.get("reason"),
                unit="navegação(ões) sintética(s)",
            ),
        ),
        (
            "Readiness Search & AI e análises de conteúdo",
            "Não interpretar valores dependentes de DOM/conteúdo como diagnóstico completo: a origem não produziu um documento validado pelo navegador.",
        ),
    ]
    impact_html = "".join(
        f"<li><strong>{escape(label)}:</strong> {escape(text)}</li>"
        for label, text in impact_items
    )

    browser_html = ""
    if browser:
        rows = []
        for item in browser:
            identity = item.get("identity") or {}
            rows.append(
                "<tr>"
                f"<td>{escape(str(item.get('device') or '-'))}</td>"
                f"<td><code>{escape(str(item.get('requested_url') or '-'))}</code></td>"
                f"<td><code>{escape(str(item.get('final_url') or 'não resolvida'))}</code></td>"
                f"<td>{escape(str(item.get('render_error') or 'nenhum'))}</td>"
                f"<td>{escape(str(identity.get('channel') or '-'))}</td>"
                f"<td>{escape(str(identity.get('browser_version') or item.get('browser_version') or '-'))}</td>"
                "</tr>"
            )
        browser_html = (
            "<details class='notice notice-info source-blocker-browser'>"
            "<summary><strong>Observação do navegador utilizada na confirmação</strong></summary>"
            "<div class='table-wrap'><table><thead><tr>"
            "<th>Dispositivo</th><th>URL solicitada</th><th>URL final</th><th>Resultado</th><th>Canal</th><th>Versão</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table></div>"
            "</details>"
        )

    ai_html = _ai_block(ai_payload)
    final_status = str(issue.http_status) if issue.http_status is not None else "não obtido"
    log_href = "../logs/audit.log"
    preflight_href = f"../{SOURCE_QUALITY_PREFLIGHT_ARTIFACT}"
    assessment_href = f"../{SOURCE_QUALITY_ARTIFACT}"
    ai_href = f"../{SOURCE_QUALITY_AI_ARTIFACT}"

    return (
        SUMMARY_MARKER_START
        + "<section class='panel source-blocker-summary' id='source-blocker-summary'>"
        "<div class='notice notice-warning'>"
        "<h2>Auditoria limitada por bloqueio técnico da origem</h2>"
        "<p><strong>As métricas dependentes do conteúdo não puderam ser coletadas de forma representativa.</strong> "
        "O RASAI interrompeu medições repetitivas ou externas depois que a falha foi confirmada, evitando produzir números enganosos ou consumir APIs sem utilidade.</p>"
        f"<p><strong>URL informada:</strong> <code>{escape(issue.requested_url)}</code><br>"
        f"<strong>URL final observada:</strong> <code>{escape(issue.final_url or 'não resolvida')}</code><br>"
        f"<strong>Classificação:</strong> {escape(issue.classification)} · "
        f"<strong>Severidade:</strong> {escape(issue.severity)} · "
        f"<strong>HTTP final:</strong> {escape(final_status)}</p>"
        f"<p>{escape(issue.deterministic_summary)}</p>"
        "</div>"
        "<h3>Impacto sobre esta auditoria</h3>"
        f"<ul>{impact_html}</ul>"
        "<h3>O que deve ser corrigido antes de reexecutar</h3>"
        + (f"<ol>{actions}</ol>" if actions else "<p>Consulte o diagnóstico técnico completo no log.</p>")
        + ai_html
        + browser_html
        + "<h3>Evidência técnica e investigação</h3>"
        "<p>Para troubleshooting, use os artefatos abaixo. O <code>audit.log</code> contém os eventos operacionais completos e um evento consolidado de diagnóstico da origem.</p>"
        "<ul>"
        f"<li><a href='{escape(log_href)}'><code>logs/audit.log</code></a> — log técnico completo</li>"
        f"<li><a href='{escape(preflight_href)}'><code>{escape(SOURCE_QUALITY_PREFLIGHT_ARTIFACT)}</code></a> — evidência HTTP anterior ao navegador</li>"
        f"<li><a href='{escape(assessment_href)}'><code>{escape(SOURCE_QUALITY_ARTIFACT)}</code></a> — estado reconciliado utilizado pelo pipeline</li>"
        + (f"<li><a href='{escape(ai_href)}'><code>{escape(SOURCE_QUALITY_AI_ARTIFACT)}</code></a> — interpretação complementar da IA</li>" if ai_payload else "")
        + "</ul>"
        "</section>"
        + SUMMARY_MARKER_END
    )


def _measurement_text(*, status: Any, attempts: Any, reason: Any, unit: str) -> str:
    status_text = str(status or "não disponível")
    attempts_text = "?" if attempts is None else str(attempts)
    reason_text = str(reason or "sem motivo persistido")
    if status_text == "SKIPPED_SOURCE_BLOCKER":
        return f"não executado por bloqueio técnico; {attempts_text} {unit}; motivo: {reason_text}."
    return f"estado persistido: {status_text}; {attempts_text} {unit}; motivo: {reason_text}."


def _ai_block(ai_payload: dict[str, Any] | None) -> str:
    if not ai_payload:
        return (
            "<div class='notice notice-info'><h3>Interpretação complementar por IA</h3>"
            "<p>Não disponível nesta execução. A classificação técnica acima permanece suficiente para troubleshooting inicial.</p></div>"
        )
    explanation = ai_payload.get("explanation")
    if not isinstance(explanation, dict):
        return ""
    summary = str(explanation.get("summary_pt") or "").strip()
    cause = str(explanation.get("likely_root_cause_pt") or "").strip()
    actions = [
        str(item).strip()
        for item in explanation.get("recommended_actions_pt", [])
        if str(item).strip()
    ]
    actions_html = "".join(f"<li>{escape(item)}</li>" for item in actions)
    provider = str(ai_payload.get("provider") or "-")
    model = str(ai_payload.get("model") or "-")
    human = bool(explanation.get("human_validation_required"))
    return (
        "<details class='notice notice-info source-blocker-ai' open>"
        "<summary><strong>Interpretação complementar por IA</strong> — baseada nas evidências técnicas persistidas</summary>"
        f"<p><strong>Provider/modelo:</strong> {escape(provider)} / {escape(model)}</p>"
        + (f"<p>{escape(summary)}</p>" if summary else "")
        + (f"<p><strong>Causa provável:</strong> {escape(cause)}</p>" if cause else "")
        + (f"<ol>{actions_html}</ol>" if actions_html else "")
        + ("<p><strong>Validação humana necessária.</strong> A IA não altera a classificação HTTP/TLS determinística.</p>" if human else "")
        + "</details>"
    )


def _measurement_state(database: Path) -> dict[str, Any]:
    output: dict[str, Any] = {}
    if not database.is_file():
        return output
    try:
        con = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True, timeout=0.5)
        con.row_factory = sqlite3.Row
        try:
            row = _first_row(
                con,
                "SELECT status,context_attempts,reason FROM web_performance_runs LIMIT 1",
            )
            if row is not None:
                output["web_performance"] = {
                    "status": row["status"],
                    "attempts": int(row["context_attempts"] or 0),
                    "reason": row["reason"],
                }
            row = _first_row(
                con,
                "SELECT status,attempted_samples,valid_samples,invalid_samples,reason FROM synthetic_apdex_runs LIMIT 1",
            )
            if row is not None:
                output["synthetic_apdex"] = {
                    "status": row["status"],
                    "attempts": int(row["attempted_samples"] or 0),
                    "valid_samples": int(row["valid_samples"] or 0),
                    "invalid_samples": int(row["invalid_samples"] or 0),
                    "reason": row["reason"],
                }
        finally:
            con.close()
    except sqlite3.Error:
        return output
    return output


def _browser_state(database: Path) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if not database.is_file():
        return output
    try:
        con = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True, timeout=0.5)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT device,requested_url,final_url,http_status,browser_metadata FROM page_snapshots ORDER BY captured_at"
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return output
    for row in rows:
        try:
            metadata = json.loads(str(row["browser_metadata"] or "{}"))
        except json.JSONDecodeError:
            metadata = {}
        identity = metadata.get("browser_identity") if isinstance(metadata, dict) else None
        if not isinstance(identity, dict):
            identity = {}
        output.append(
            {
                "device": row["device"],
                "requested_url": row["requested_url"],
                "final_url": row["final_url"],
                "http_status": row["http_status"],
                "render_error": metadata.get("render_error") if isinstance(metadata, dict) else None,
                "render_succeeded": bool(metadata.get("render_succeeded")) if isinstance(metadata, dict) else False,
                "browser_version": metadata.get("browser_version") if isinstance(metadata, dict) else None,
                "identity": identity,
                "navigation_trace": metadata.get("navigation_trace") if isinstance(metadata, dict) else None,
                "navigation_request_headers": metadata.get("navigation_request_headers") if isinstance(metadata, dict) else None,
                "raw_http": metadata.get("raw_http") if isinstance(metadata, dict) else None,
            }
        )
    return output


def _first_row(con: sqlite3.Connection, query: str) -> sqlite3.Row | None:
    try:
        return con.execute(query).fetchone()
    except sqlite3.Error:
        return None


def _append_diagnostic_event_once(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    assessment: SourceQualityAssessment,
    measurements: dict[str, Any],
    browser: list[dict[str, Any]],
    ai_payload: dict[str, Any] | None,
) -> None:
    log_path = workspace.root / "logs" / "audit.log"
    try:
        if log_path.is_file() and "SOURCE_QUALITY_TECHNICAL_DIAGNOSTIC" in log_path.read_text(encoding="utf-8", errors="replace"):
            return
    except OSError:
        pass
    issues = [
        {
            "requested_url": issue.requested_url,
            "final_url": issue.final_url,
            "http_status": issue.http_status,
            "network_error": issue.network_error,
            "network_error_message": issue.network_error_message,
            "classification": issue.classification,
            "severity": issue.severity,
            "redirects": [
                {
                    "status": hop.status,
                    "source_url": hop.source_url,
                    "location": hop.location,
                    "target_url": hop.target_url,
                }
                for hop in issue.redirects
            ],
            "recommended_actions": list(issue.recommended_actions),
        }
        for issue in assessment.issues
    ]
    try_append_operational_event(
        workspace,
        "SOURCE_QUALITY_TECHNICAL_DIAGNOSTIC",
        level="ERROR",
        audit_id=audit_id,
        all_pages_hard_blocked=True,
        blockers=assessment.hard_blocker_kinds,
        issues=issues,
        browser_observations=browser,
        downstream_measurements=measurements,
        ai_diagnostic={
            "state": ai_payload.get("state"),
            "provider": ai_payload.get("provider"),
            "model": ai_payload.get("model"),
        } if ai_payload else None,
        evidence_paths={
            "log": "logs/audit.log",
            "preflight": SOURCE_QUALITY_PREFLIGHT_ARTIFACT,
            "assessment": SOURCE_QUALITY_ARTIFACT,
            "ai": SOURCE_QUALITY_AI_ARTIFACT if ai_payload else None,
        },
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None
