"""Last-mile organization for the public HTML report set.

This pass is presentation-only. It does not recalculate scores, modify evidence or call
external services. It runs after AI/cost enrichment so ordering and terminology cannot
be undone by a late renderer.
"""
from __future__ import annotations

from html import escape
import re
import sqlite3
from typing import Any

from rasai.persistence import AuditWorkspace

_AI_USAGE_FILE = "ai-usage.html"
_AI_COST_RE = re.compile(
    r"<section\b[^>]*data-ai-cost-attribution=['\"]true['\"][^>]*>.*?</section>",
    flags=re.IGNORECASE | re.DOTALL,
)
_FOOTER_RE = re.compile(
    r"<footer\b[^>]*class=(['\"])[^'\"]*\bfooter\b[^'\"]*\1[^>]*>.*?</footer>",
    flags=re.IGNORECASE | re.DOTALL,
)
_STYLE_MARKER = "rasai-report-final-polish-v1"

_FINAL_STYLE = r"""
<style id='rasai-report-final-polish-v1'>
/* Restrained semantic palette; result colors continue to come from report_semantics. */
:root{--report-help-bg:#f8fafc;--report-help-border:rgba(85,105,135,.18);--report-help-ink:#344054}
.notice,.metric,.score-card,.indicator-card,.page-card,.table-wrap,details{color:var(--ink)}
.notice{line-height:1.5}.notice code,.detail-body code{color:#344054}
.result-tag,.badge,.score-condition-tag,.indicator-condition{font-weight:700}
abbr.report-term{cursor:help;text-decoration:underline dotted;text-underline-offset:3px;text-decoration-color:#8a97aa}
.report-dependency-state{border-left:4px solid var(--amber);background:var(--soft-amber)}
.report-dependency-state.bad{border-left-color:var(--red);background:var(--soft-red)}
.report-dependency-state p{margin:.35rem 0 0;color:#4b5565}
.ai-cost-attribution{margin-top:28px;border-top:2px solid var(--line)}
.ai-cost-attribution .kicker{color:#68758a}
.ai-cost-attribution[data-ai-zero='true']{background:#fafbfc;box-shadow:none}
footer.footer{padding-top:16px;border-top:1px solid var(--line)}
@media (prefers-contrast:more){.intro,.muted,.label,.metric small{color:#4b5565}.table-wrap{border-color:#c7ced8}}
</style>
"""

_TERM_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("<th>Provider</th>", "<th>Provedor</th>"),
    ("<th>Providers</th>", "<th>Provedores</th>"),
    ("<th>Device</th>", "<th>Dispositivo</th>"),
    ("<th>Artifact</th>", "<th>Evidência preservada</th>"),
    ("<th>Coverage</th>", "<th><abbr class='report-term' title='Percentual do peso aplicável que foi efetivamente avaliado'>Cobertura</abbr></th>"),
    ("<th>Confidence</th>", "<th><abbr class='report-term' title='Força da conclusão considerando cobertura e qualidade das evidências'>Confiança</abbr></th>"),
    ("<small>Coverage</small>", "<small><abbr class='report-term' title='Percentual do peso aplicável efetivamente avaliado'>Cobertura</abbr></small>"),
    ("<small>Confidence</small>", "<small><abbr class='report-term' title='Força da conclusão considerando cobertura e evidências'>Confiança</abbr></small>"),
    ("<small>Reasoning tokens</small>", "<small>Tokens de raciocínio</small>"),
    ("<th>Reasoning</th>", "<th>Raciocínio</th>"),
)


def finalize_report_presentation(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Apply final ordering, concise dependency state and shared wording to all HTML."""
    report_dir = workspace.root / "report"
    if not report_dir.is_dir():
        return

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        dependency = _dependency_states(connection, audit_id)
    finally:
        connection.close()

    for path in sorted(report_dir.glob("*.html")):
        try:
            html = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue

        html = _translate_owned_labels(html)
        html = _inject_style(html)
        html = _inject_dependency_notice(html, path.name, dependency)
        if path.name != _AI_USAGE_FILE:
            html = _move_ai_cost_to_final_data_block(html)
        html = _mark_zero_ai_cost(html)
        html = _ensure_footer_last(html)

        try:
            path.write_text(html, encoding="utf-8", newline="\n")
        except OSError:
            continue


def _translate_owned_labels(html: str) -> str:
    for old, new in _TERM_REPLACEMENTS:
        html = html.replace(old, new)
    return html


def _inject_style(html: str) -> str:
    if _STYLE_MARKER in html:
        return html
    if "</head>" in html:
        return html.replace("</head>", _FINAL_STYLE + "</head>", 1)
    return html


def _move_ai_cost_to_final_data_block(html: str) -> str:
    match = _AI_COST_RE.search(html)
    if match is None:
        return html
    block = match.group(0)
    stripped = html[:match.start()] + html[match.end():]
    footer = _FOOTER_RE.search(stripped)
    if footer is not None:
        return stripped[:footer.start()] + block + stripped[footer.start():]
    if "</main>" in stripped:
        return stripped.replace("</main>", block + "</main>", 1)
    return stripped + block


def _mark_zero_ai_cost(html: str) -> str:
    if "data-ai-cost-attribution='true'" not in html or "Sem consumo IA direto" not in html:
        return html
    return html.replace(
        "data-ai-cost-attribution='true'",
        "data-ai-cost-attribution='true' data-ai-zero='true'",
        1,
    )


def _ensure_footer_last(html: str) -> str:
    footer = _FOOTER_RE.search(html)
    if footer is None or "</main>" not in html:
        return html
    block = footer.group(0)
    without = html[:footer.start()] + html[footer.end():]
    return without.replace("</main>", block + "</main>", 1)


def _one(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
    try:
        return connection.execute(sql, params).fetchone()
    except sqlite3.Error:
        return None


def _lighthouse_state(connection: sqlite3.Connection, audit_id: str) -> str | None:
    web = _one(
        connection,
        "SELECT enabled,status,reason,pagespeed_successes FROM web_performance_runs WHERE audit_id=?",
        (audit_id,),
    )
    if web is None:
        return "A coleta PageSpeed/Lighthouse não foi materializada nesta auditoria."
    if not bool(web["enabled"]):
        return "A coleta PageSpeed/Lighthouse foi desabilitada nesta execução."

    psi = _one(
        connection,
        "SELECT status,http_status,error_code,error_message FROM web_performance_attempts "
        "WHERE audit_id=? AND UPPER(service) LIKE 'PAGESPEED%' ORDER BY created_at DESC,rowid DESC LIMIT 1",
        (audit_id,),
    )
    if psi is None:
        reason = str(web["reason"] or "").strip()
        suffix = f" Motivo registrado: {reason}." if reason else ""
        return "Web Performance foi habilitado, mas nenhuma tentativa PageSpeed/Lighthouse foi persistida." + suffix
    if str(psi["status"] or "").upper() != "SUCCESS":
        parts = ["A tentativa PageSpeed/Lighthouse falhou"]
        if psi["http_status"] is not None:
            parts.append(f"HTTP {psi['http_status']}")
        if psi["error_code"]:
            parts.append(str(psi["error_code"]))
        if psi["error_message"]:
            parts.append(str(psi["error_message"])[:220])
        return " · ".join(parts) + "."

    observation = _one(
        connection,
        "SELECT status,error_summary,performance_score,accessibility_score,best_practices_score,seo_score,agentic_browsing_score "
        "FROM web_performance_observations WHERE audit_id=? ORDER BY captured_at DESC,rowid DESC LIMIT 1",
        (audit_id,),
    )
    if observation is None:
        return (
            "PageSpeed respondeu, mas nenhuma observação Lighthouse foi persistida. "
            "Consulte a telemetria de Web Performance para o contexto afetado."
        )
    score_fields = (
        "performance_score",
        "accessibility_score",
        "best_practices_score",
        "seo_score",
        "agentic_browsing_score",
    )
    has_score = any(observation[name] is not None for name in score_fields)
    if not has_score:
        detail = str(observation["error_summary"] or "").strip()
        text = (
            "PageSpeed concluiu o transporte, mas o Lighthouse não materializou nenhum score válido. "
            "HTTP/API concluído não equivale a lighthouseResult utilizável."
        )
        if detail:
            text += " Diagnóstico persistido: " + detail[:240] + "."
        return text
    if str(observation["status"] or "").upper() == "PARTIAL":
        detail = str(observation["error_summary"] or "").strip()
        if detail:
            return "Lighthouse foi materializado parcialmente. Diagnóstico persistido: " + detail[:240] + "."
    return None


def _dependency_states(connection: sqlite3.Connection, audit_id: str) -> dict[str, str]:
    states: dict[str, str] = {}

    lighthouse = _lighthouse_state(connection, audit_id)
    if lighthouse:
        states["lighthouse"] = lighthouse

    ai = _one(
        connection,
        "SELECT enabled,status,effective_provider FROM ai_audit_sessions WHERE audit_id=?",
        (audit_id,),
    )
    if ai is not None and bool(ai["enabled"]) and not ai["effective_provider"]:
        states["semantic-ai"] = (
            "A análise semântica por IA foi solicitada, mas nenhuma resposta válida de provedor foi materializada. "
            "Consulte Uso de IA para a tentativa, provedor e causa registrada."
        )

    content = _one(
        connection,
        "SELECT enabled,status FROM content_remediation_runs WHERE audit_id=?",
        (audit_id,),
    )
    if content is not None:
        enabled = bool(content["enabled"])
        status = str(content["status"] or "UNKNOWN")
        if not enabled:
            states["content-ai"] = "A remediação textual por IA foi desabilitada nesta execução."
        elif status not in {"SUCCESS", "PARTIAL", "NO_ELIGIBLE_FINDINGS"}:
            states["content-ai"] = f"A remediação textual por IA não produziu saída utilizável: estado {status}."

    improvement = _one(
        connection,
        "SELECT enabled,status,reason FROM improvement_intelligence_runs WHERE audit_id=?",
        (audit_id,),
    )
    if improvement is not None:
        enabled = bool(improvement["enabled"])
        status = str(improvement["status"] or "UNKNOWN")
        reason = str(improvement["reason"] or "").strip()
        if not enabled:
            states["improvement-ai"] = "A Análise profunda e melhorias por IA foi desabilitada nesta execução."
        elif status not in {"SUCCESS", "PARTIAL"}:
            text = f"A Análise profunda e melhorias não produziu saída utilizável: estado {status}."
            if reason:
                text += " Motivo registrado: " + reason[:220]
            states["improvement-ai"] = text

    return states


def _inject_dependency_notice(html: str, filename: str, states: dict[str, str]) -> str:
    if "data-report-dependency-state='true'" in html:
        return html

    reason: str | None = None
    if filename in {"index.html", "web-performance.html", "accessibility.html"}:
        reason = states.get("lighthouse")
    elif filename == "content-suggestions.html":
        reason = states.get("content-ai")
    elif filename == "improvement-intelligence.html":
        reason = states.get("improvement-ai")
    elif filename in {"mobile.html", "desktop.html", "readiness.html"}:
        reason = states.get("semantic-ai")

    if not reason:
        return html

    notice = (
        "<section class='notice warn report-dependency-state' data-report-dependency-state='true'>"
        "<strong>Por que parte deste relatório pode estar sem resultado</strong>"
        f"<p>{escape(reason)}</p>"
        "</section>"
    )
    if "</header>" in html:
        return html.replace("</header>", "</header>" + notice, 1)
    if "<main" in html:
        marker = html.find(">", html.find("<main"))
        if marker >= 0:
            return html[: marker + 1] + notice + html[marker + 1 :]
    return html
