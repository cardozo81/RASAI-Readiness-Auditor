"""Final presentation reconciliation for score bands and optional report telemetry.

This module is projection-only. It does not alter SARI/SCORE-GEO arithmetic, Apdex
classification, persisted evidence, or network execution. It makes already-persisted
states explicit and keeps visual semantics consistent across report surfaces.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from html import escape
import math
from pathlib import Path
import sqlite3
from typing import Any


_SARI_CSS_MARKER = "/* rasai-sari-score-bands-v1 */"
_SARI_CSS = r"""
/* rasai-sari-score-bands-v1 */
.score-card.low{background:rgba(169,111,56,.09);border-left-color:#a96f38}
.score-card.neutral{background:var(--soft-slate,#f1f3f6);border-left-color:var(--slate,#7d899a)}
.score-band-label{display:inline-flex;margin-top:7px;padding:3px 8px;border-radius:999px;font-size:.7rem;font-weight:760;line-height:1.3}
.score-band-label.expected{background:rgba(95,150,116,.16);color:#3f7452}
.score-band-label.near{background:rgba(182,138,80,.18);color:#855f2c}
.score-band-label.below{background:rgba(169,111,56,.18);color:#815126}
.score-band-label.critical{background:rgba(191,111,112,.18);color:#98494c}
.score-band-label.neutral{background:#eef0f3;color:#596274}
"""


def sari_band(value: float | None) -> tuple[str, str, str]:
    """Return presentation state, public label and canonical numeric range."""
    if value is None or not math.isfinite(float(value)):
        return "neutral", "Não determinado", "sem score válido"
    number = float(value)
    if number >= 90.0:
        return "expected", "Excelente", "90-100"
    if number >= 75.0:
        return "expected", "Alta", "75-89"
    if number >= 60.0:
        return "near", "Moderada", "60-74"
    if number >= 40.0:
        return "below", "Baixa", "40-59"
    return "critical", "Crítica", "0-39"


def _band_text(value: float | None) -> tuple[str, str]:
    state, label, numeric_range = sari_band(value)
    return state, label if state == "neutral" else f"{label} ({numeric_range})"


def _score_card_class(state: str) -> str:
    return {
        "expected": "good",
        "near": "warn",
        "below": "low",
        "critical": "bad",
        "neutral": "neutral",
    }[state]


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        if hasattr(row, "keys") and key not in row.keys():
            return default
        value = row[key]
    except (KeyError, IndexError, TypeError, AttributeError):
        return default
    return default if value is None else value


def _install_shared_css() -> None:
    from rasai import report_navigation

    if getattr(report_navigation, "_rasai_sari_score_band_css", False):
        return
    original = report_navigation._ensure_premium_css

    def ensure_with_sari_bands(report_dir: Path) -> None:
        original(report_dir)
        css_path = Path(report_dir) / "css" / "site.css"
        if not css_path.is_file():
            return
        css = css_path.read_text(encoding="utf-8")
        if _SARI_CSS_MARKER in css:
            return
        css_path.write_text(css.rstrip() + "\n\n" + _SARI_CSS.strip() + "\n", encoding="utf-8", newline="\n")

    report_navigation._ensure_premium_css = ensure_with_sari_bands
    report_navigation._rasai_sari_score_band_css = True


def _install_sari_visual_contract() -> None:
    from rasai import rasai_readiness_reporting as reporting
    from rasai import report_semantics

    if getattr(reporting, "_rasai_canonical_sari_score_bands", False):
        return

    def sari_condition(row: Any) -> tuple[str, str]:
        raw = _row_value(row, "value")
        value = None if raw is None else float(raw)
        return _band_text(value)

    def overall_card(scores: list[Any], device: str) -> str:
        row = next(
            (
                item for item in scores
                if str(_row_value(item, "device", "")).upper() == device
                and str(_row_value(item, "dimension", "")) == "OVERALL_READINESS"
            ),
            None,
        )
        label = "Mobile" if device == "MOBILE" else "Desktop"
        if row is None:
            return (
                f"<article class='score-card neutral'><div class='label'>{label} - {reporting.PUBLIC_METHOD_VERSION}</div>"
                "<div class='score-number'>Indisponível</div>"
                "<span class='score-band-label neutral'>Não determinado</span>"
                "<p class='intro'>Overall não persistido.</p></article>"
            )
        coverage = f"{float(_row_value(row, 'coverage', 0.0)) * 100:.0f}%"
        confidence_raw = str(_row_value(row, "confidence", "UNAVAILABLE"))
        confidence = reporting._STATUS_LABELS.get(confidence_raw, confidence_raw)
        consolidation_raw = str(_row_value(row, "consolidation_status", "NOT_CONSOLIDATED"))
        consolidation = reporting._STATUS_LABELS.get(consolidation_raw, consolidation_raw)
        raw_value = _row_value(row, "value")
        if raw_value is None:
            return (
                f"<article class='score-card neutral'><div class='label'>{label} - {reporting.PUBLIC_METHOD_VERSION}</div>"
                "<div class='score-number'>Não consolidado</div>"
                "<span class='score-band-label neutral'>Não determinado</span>"
                f"<p class='intro'>Coverage {escape(coverage)} - Confidence {escape(confidence)}. Consulte as dimensões bloqueantes.</p></article>"
            )
        value = float(raw_value)
        state, band_label = _band_text(value)
        css = _score_card_class(state)
        return (
            f"<article class='score-card {css}'><div class='label'>{label} - {reporting.PUBLIC_METHOD_VERSION}</div>"
            f"<div class='score-number'>{value:.1f}<span>/100</span></div>"
            f"<span class='score-band-label {state}'>{escape(band_label)}</span>"
            "<div class='score-meta'>"
            f"<div><small>Cobertura</small><strong>{escape(coverage)}</strong></div>"
            f"<div><small>Confiança</small><strong>{escape(confidence)}</strong></div>"
            f"<div><small>Consolidação</small><strong>{escape(consolidation)}</strong></div>"
            "</div></article>"
        )

    def score_condition(score_text: str, confidence: str, consolidation: str) -> tuple[str, str]:
        # Confidence and Consolidation qualify measurement strength; they must not
        # recolor a valid numeric score into a different quality band.
        del confidence, consolidation
        value = report_semantics._first_number(score_text)
        return _band_text(value)

    reporting._sari_condition = sari_condition
    reporting._overall_card = overall_card
    report_semantics._score_condition = score_condition
    reporting._rasai_canonical_sari_score_bands = True


def _ux_rows(report_dir: Path) -> tuple[Any | None, list[sqlite3.Row]]:
    database = Path(report_dir).parent / "audit.db"
    if not database.is_file():
        return None, []
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            run = connection.execute("SELECT * FROM synthetic_ux_apdex_runs LIMIT 1").fetchone()
            summaries = list(
                connection.execute(
                    "SELECT * FROM synthetic_ux_apdex_summaries WHERE device='POPULATION' ORDER BY url,summary_id"
                ).fetchall()
            )
        except sqlite3.OperationalError:
            return None, []
    finally:
        connection.close()
    return run, summaries


def _ux_dashboard_card(reporting: Any, report_dir: Path) -> str:
    from rasai.report_presentation import public_label

    run, population = _ux_rows(report_dir)
    page_exists = (Path(report_dir) / "apdex-experience.html").is_file()
    if run is None and not page_exists:
        return ""
    if run is None:
        return reporting._indicator_card(
            "Synthetic User Experience Apdex",
            "NÃO EXECUTADO",
            "Nenhum estado da população sintética foi persistido nesta auditoria.",
            "apdex-experience.html",
            "Apdex + população sintética controlada",
            "neutral",
            "Não executado",
        )
    if not bool(_row_value(run, "enabled", False)):
        return reporting._indicator_card(
            "Synthetic User Experience Apdex",
            "DESABILITADO",
            "Medição opcional não executada nesta auditoria.",
            "apdex-experience.html",
            "Apdex + população sintética controlada",
            "neutral",
            "Não executado",
        )
    scored = [row for row in population if _row_value(row, "apdex_score") is not None]
    if scored:
        values = [float(row["apdex_score"]) for row in scored]
        minimum, maximum = min(values), max(values)
        value = f"{minimum:.3f}" if abs(minimum - maximum) < 1e-12 else f"{minimum:.3f}-{maximum:.3f}"
        valid = sum(int(_row_value(row, "valid_samples", 0)) for row in population)
        target = sum(int(_row_value(row, "target_samples", 0)) for row in population)
        status = public_label(str(_row_value(run, "status", "-")))
        detail = f"{len(population)} população(ões)/página; {valid}/{target} amostras válidas; estado {status}."
        small_group_only = bool(scored) and not any(bool(_row_value(row, "final_group", False)) for row in scored)
        condition, condition_label = reporting._apdex_condition(scored, small_group_only=small_group_only)
    else:
        value = "NÃO DISPONÍVEL"
        status = public_label(str(_row_value(run, "status", "-")))
        detail = f"Execução materializada, mas sem população com Apdex calculável; estado {status}."
        condition, condition_label = "neutral", "Sem dados suficientes"
    return reporting._indicator_card(
        "Synthetic User Experience Apdex",
        value,
        detail,
        "apdex-experience.html",
        "Apdex + população sintética controlada",
        condition,
        condition_label,
    )


def _install_ux_dashboard_card() -> None:
    from rasai import rasai_readiness_reporting as reporting

    if getattr(reporting, "_rasai_ux_apdex_dashboard_card", False):
        return
    original = reporting._dashboard

    def dashboard_with_ux_apdex(data: dict[str, Any], report_dir: Path) -> str:
        html = original(data, report_dir)
        card = _ux_dashboard_card(reporting, Path(report_dir))
        if not card or "<h3>Synthetic User Experience Apdex</h3>" in html:
            return html
        target = "</div></section>" + reporting._DASHBOARD_END
        if target not in html:
            return html
        return html.replace(target, card + target, 1)

    reporting._dashboard = dashboard_with_ux_apdex
    reporting._rasai_ux_apdex_dashboard_card = True


def _distribution(values: list[str]) -> str:
    counts = Counter(values)
    return "; ".join(f"{key} x{counts[key]}" for key in sorted(counts)) or "-"


def profile_execution_section(data: dict[str, Any]) -> str:
    samples = list(data.get("samples") or [])
    summaries = list(data.get("summaries") or [])
    if not samples:
        return (
            "<section id='ux-profile-execution-trace' class='panel'>"
            "<div class='kicker'>Execução por perfil</div><h2>Tentativas e retornos da população sintética</h2>"
            "<div class='notice'>Nenhuma tentativa de user action sintética foi persistida nesta auditoria.</div></section>"
        )

    summary_by_key: dict[tuple[str, str, str], Any] = {}
    for row in summaries:
        device = str(_row_value(row, "device", "")).upper()
        if device == "POPULATION":
            continue
        key = (str(_row_value(row, "url", "")), device, str(_row_value(row, "profile_id", "")))
        summary_by_key[key] = row

    grouped: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for row in samples:
        key = (
            str(_row_value(row, "url", "")),
            str(_row_value(row, "device", "")).upper(),
            str(_row_value(row, "profile_id", "")),
        )
        grouped[key].append(row)

    rows: list[str] = []
    total_http_responses = 0
    for key in sorted(grouped):
        url, device, profile_id = key
        items = grouped[key]
        summary = summary_by_key.get(key)
        attempts = len(items)
        valid = sum(_row_value(row, "classification") not in (None, "") for row in items)
        invalid = attempts - valid
        target = int(_row_value(summary, "target_samples", valid)) if summary is not None else valid
        http_values = [
            str(int(_row_value(row, "http_status"))) if _row_value(row, "http_status") is not None else "sem resposta"
            for row in items
        ]
        response_count = sum(value != "sem resposta" for value in http_values)
        total_http_responses += response_count
        navigation_status = _distribution([str(_row_value(row, "status", "-") or "-") for row in items])
        http_status = _distribution(http_values)
        classifications = _distribution([
            str(_row_value(row, "classification", "INVÁLIDA") or "INVÁLIDA") for row in items
        ])
        xhr_fetch = sum(int(_row_value(row, "xhr_fetch_count", 0) or 0) for row in items)
        request_failed = sum(int(_row_value(row, "request_failed_count", 0) or 0) for row in items)
        http_errors = sum(int(_row_value(row, "http_error_count", 0) or 0) for row in items)
        rows.append(
            "<tr>"
            f"<td class='mono'>{escape(url)}</td>"
            f"<td><strong>{escape(device)}</strong></td>"
            f"<td><code>{escape(profile_id)}</code></td>"
            f"<td>{target}</td><td>{attempts}</td><td>{response_count}/{attempts}</td>"
            f"<td>{escape(http_status)}</td><td>{escape(navigation_status)}</td>"
            f"<td>{valid}/{invalid}</td><td>{escape(classifications)}</td>"
            f"<td>{xhr_fetch}</td><td>{request_failed}</td><td>{http_errors}</td>"
            "</tr>"
        )

    return (
        "<section id='ux-profile-execution-trace' class='panel'>"
        "<div class='kicker'>Execução por perfil</div><h2>Tentativas e retornos da população sintética</h2>"
        "<p class='intro'><strong>Uma tentativa</strong> corresponde a uma user action sintética com uma navegação principal. "
        "O retorno HTTP mostrado é o documento principal daquela tentativa. A página pode disparar vários subrequests; "
        "o RASAi persiste contadores de XHR/fetch, requests falhos e respostas HTTP >=400, mas não apresenta esses subrequests "
        "como se fossem novas amostras da população.</p>"
        f"<div class='metric-grid'><div class='metric'><span>Perfis executados</span><strong>{len(grouped)}</strong></div>"
        f"<div class='metric'><span>Tentativas persistidas</span><strong>{len(samples)}</strong></div>"
        f"<div class='metric'><span>Retornos HTTP principais</span><strong>{total_http_responses}/{len(samples)}</strong></div></div>"
        "<div class='table-wrap'><table><thead><tr>"
        "<th>URL</th><th>Device</th><th>Perfil efetivo</th><th>Alvo válido</th><th>Tentativas</th>"
        "<th>Retorno principal</th><th>HTTP principal</th><th>Status da navegação</th><th>Válidas/Inválidas</th>"
        "<th>Classificação</th><th>XHR/fetch</th><th>Requests falhos</th><th>HTTP >=400</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></section>"
    )


def _install_ux_profile_traceability() -> None:
    from rasai import m25_reporting

    if getattr(m25_reporting, "_rasai_ux_profile_traceability", False):
        return
    original = m25_reporting._page

    def page_with_profile_traceability(data: dict[str, Any], report_dir: Path) -> str:
        html = original(data, report_dir)
        if "ux-profile-execution-trace" in html:
            return html
        section = profile_execution_section(data)
        marker = "<div class='kicker'>Dynatrace</div>"
        index = html.find(marker)
        if index >= 0:
            start = html.rfind("<section", 0, index)
            if start >= 0:
                return html[:start] + section + html[start:]
        return html.replace("</main>", section + "</main>", 1)

    m25_reporting._page = page_with_profile_traceability
    m25_reporting._rasai_ux_profile_traceability = True


def content_remediation_diagnostic(run: Any | None, attempts_count: int) -> tuple[str, str]:
    if run is None:
        return (
            "warn",
            "O estado da remediação opcional de conteúdo por IA não foi materializado neste AUD; não é possível concluir que houve configuração ou tentativa externa.",
        )
    enabled = bool(_row_value(run, "enabled", False))
    status = str(_row_value(run, "status", "UNAVAILABLE"))
    eligible = int(_row_value(run, "eligible_findings", 0) or 0)
    reason = str(_row_value(run, "reason", "") or "").strip()
    if not enabled:
        return (
            "neutral",
            "A remediação de conteúdo por IA estava desabilitada (default OFF). Zero chamadas é o resultado esperado; habilite RASAI_AI_CONTENT_REMEDIATION ou --ai-content-remediation para esta finalidade.",
        )
    if eligible == 0:
        return (
            "neutral",
            "A remediação de conteúdo por IA estava habilitada, mas nenhum finding era elegível. Zero chamadas é esperado e não indica erro de provider.",
        )
    if status == "NOT_CONFIGURED":
        return (
            "warn",
            f"A remediação de conteúdo por IA estava habilitada e havia {eligible} finding(s) elegível(is), mas nenhum provider saudável/configurado ficou disponível para esta finalidade.",
        )
    if attempts_count == 0:
        suffix = f" Motivo persistido: {reason}." if reason else ""
        return (
            "warn",
            f"A remediação de conteúdo por IA estava habilitada e havia {eligible} finding(s) elegível(is), mas nenhuma tentativa externa foi persistida. Estado: {status}.{suffix}",
        )
    return "neutral", "A tabela contém as tentativas externas persistidas desta finalidade."


def _install_ai_content_empty_state() -> None:
    from rasai import m20_reporting

    if getattr(m20_reporting, "_rasai_content_remediation_empty_state", False):
        return
    original = m20_reporting._ai_telemetry

    def ai_telemetry_with_diagnostic(data: dict[str, Any]) -> str:
        html = original(data)
        attempts = list(data.get("attempts") or [])
        run = data.get("run")
        eligible = int(_row_value(run, "eligible_findings", 0) or 0)
        attempted = int(_row_value(run, "attempted_contexts", 0) or 0)
        generated = int(_row_value(run, "generated_suggestions", 0) or 0)
        reason = str(_row_value(run, "reason", "-") or "-")
        extras = (
            m20_reporting._metric("Findings elegíveis", eligible)
            + m20_reporting._metric("Contextos registrados", attempted)
            + m20_reporting._metric("Sugestões publicadas", generated)
            + m20_reporting._metric("Motivo da etapa", reason)
        )
        html = html.replace(
            "</div><p class='intro'><strong>Contexto editorial persistido:</strong>",
            extras + "</div><p class='intro'><strong>Contexto editorial persistido:</strong>",
            1,
        )
        if not attempts:
            severity, message = content_remediation_diagnostic(run, 0)
            notice_class = "notice warn" if severity == "warn" else "notice"
            notice = f"<div class='{notice_class}' data-content-remediation-empty-state='true'><strong>Por que a tabela está vazia:</strong> {escape(message)}</div>"
            html = html.replace("<div class='table-wrap'>", notice + "<div class='table-wrap'>", 1)
            html = html.replace(
                "Nenhuma chamada Sugestões e remediação de conteúdo por IA.",
                escape(message),
                1,
            )
        return html

    m20_reporting._ai_telemetry = ai_telemetry_with_diagnostic
    m20_reporting._rasai_content_remediation_empty_state = True


def install() -> None:
    """Install report-only reconciliation idempotently."""
    _install_shared_css()
    _install_sari_visual_contract()
    _install_ux_dashboard_card()
    _install_ux_profile_traceability()
    _install_ai_content_empty_state()
