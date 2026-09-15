"""Absolute-last executive dashboard polish for audit-owned public reports.

This module is presentation-only. It does not recalculate SARI, Lighthouse, Core Web
Vitals or Apdex and it never changes persisted execution evidence. Its job is to make
``index.html`` express the effective execution contract in user-facing language after
all late enrichers have already materialized their cards.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
import re
import sqlite3
from typing import Any

from rasai.persistence import AuditWorkspace

_STYLE_MARKER = "rasai-indicator-cluster-layout-v1"
_GROUP_MARKER = "data-indicator-groups='true'"

_LIGHTHOUSE_TITLES = (
    "Lighthouse Performance",
    "Lighthouse Accessibility",
    "Lighthouse Best Practices",
    "Lighthouse SEO técnico",
)
_APDEX_TITLES = (
    "Synthetic Navigation Apdex",
    "Synthetic User Experience Apdex",
)
_CWV_TITLE = "Core Web Vitals"

_SUPPORTING_RE = re.compile(
    r"(?P<open><div\b[^>]*class=(?P<quote>['\"])[^'\"]*\bindicator-supporting-grid\b[^'\"]*(?P=quote)[^>]*>)"
    r"(?P<body>.*?)"
    r"(?P<close></div>\s*</section>\s*<!-- rasai-executive-dashboard:end -->)",
    flags=re.IGNORECASE | re.DOTALL,
)
_CARD_RE = re.compile(
    r"<article\b[^>]*\bindicator-card\b[^>]*>.*?</article>",
    flags=re.IGNORECASE | re.DOTALL,
)
_TITLE_RE = re.compile(r"<h3>(?P<title>.*?)</h3>", flags=re.IGNORECASE | re.DOTALL)
_DEPENDENCY_RE = re.compile(
    r"<section\b(?P<attrs>[^>]*\breport-dependency-state\b[^>]*)>(?P<body>.*?)</section>",
    flags=re.IGNORECASE | re.DOTALL,
)

_STYLE = r"""
<style id='rasai-indicator-cluster-layout-v1'>
.indicator-supporting-grid.indicator-group-shell{display:block;grid-template-columns:none}
.indicator-dashboard-groups{display:grid;gap:18px}
.indicator-cluster{border:1px solid var(--line);border-radius:14px;padding:16px;background:rgba(248,250,252,.58)}
.indicator-cluster-heading{margin-bottom:12px}.indicator-cluster-heading h3{margin:.18rem 0 .28rem;font-size:1.08rem}
.indicator-cluster-heading .intro{margin:0;max-width:1050px}
.indicator-subgroup+.indicator-subgroup{margin-top:14px}
.indicator-subgroup-label{margin:0 0 8px;color:var(--muted);font-size:.72rem;font-weight:780;text-transform:uppercase;letter-spacing:.065em}
.indicator-cluster-grid{display:grid;gap:12px;align-items:stretch}
.indicator-cwv-grid{grid-template-columns:minmax(0,420px)}
.indicator-lighthouse-grid{grid-template-columns:repeat(4,minmax(0,1fr))}
.indicator-apdex-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.indicator-other-grid{grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr))}
.indicator-cluster .indicator-card{height:100%;margin:0}
@media(max-width:1250px){.indicator-lighthouse-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:760px){.indicator-cluster{padding:12px}.indicator-lighthouse-grid,.indicator-apdex-grid,.indicator-cwv-grid{grid-template-columns:1fr;max-width:none}}
</style>
"""


def _one(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
    try:
        return connection.execute(sql, params).fetchone()
    except sqlite3.Error:
        return None


def _run_requested(connection: sqlite3.Connection, audit_id: str, table: str) -> bool:
    row = _one(
        connection,
        f"SELECT enabled FROM {table} WHERE audit_id=? ORDER BY rowid DESC LIMIT 1",
        (audit_id,),
    )
    return bool(row["enabled"]) if row is not None and "enabled" in row.keys() else False


def _seconds_from_failure(duration_ms: Any, message: str) -> int | None:
    try:
        duration = int(duration_ms or 0)
    except (TypeError, ValueError):
        duration = 0
    if duration > 0:
        return max(1, round(duration / 1000))
    match = re.search(r"(?:after|ap[oó]s)\s+(\d+(?:\.\d+)?)\s*s(?:ec(?:ond)?s?)?", message, re.I)
    if match is None:
        return None
    try:
        return max(1, round(float(match.group(1))))
    except ValueError:
        return None


def _friendly_pagespeed_failure(
    *,
    error_code: Any,
    error_message: Any,
    http_status: Any = None,
    duration_ms: Any = None,
) -> str:
    """Translate transport diagnostics into a stable public explanation.

    Raw adapter codes remain available in technical evidence/ledgers; the executive
    report intentionally uses a human-facing reason instead of implementation tokens.
    """
    code = str(error_code or "").strip()
    message = str(error_message or "").strip()
    normalized = f"{code} {message}".casefold().replace("_", " ")
    seconds = _seconds_from_failure(duration_ms, message)
    try:
        status = int(http_status) if http_status is not None else None
    except (TypeError, ValueError):
        status = None

    if any(token in normalized for token in ("timeout", "time out", "deadline", "wall clock")):
        suffix = f" de {seconds} s" if seconds is not None else " configurado"
        return f"A coleta PageSpeed/Lighthouse ultrapassou o tempo limite{suffix}."
    if status == 429 or any(token in normalized for token in ("quota", "rate limit", "too many requests")):
        return "A coleta PageSpeed/Lighthouse não concluiu porque o serviço externo limitou a requisição por quota ou excesso de chamadas."
    if status in {401, 403} or any(token in normalized for token in ("auth", "credential", "permission", "forbidden", "unauthorized")):
        return "A coleta PageSpeed/Lighthouse não concluiu por uma restrição de autenticação, permissão ou configuração do serviço externo."
    if any(token in normalized for token in ("network", "dns", "connection", "socket", "tls")):
        return "A coleta PageSpeed/Lighthouse não concluiu por uma falha de rede ou conectividade com o serviço externo."
    if status is not None and status >= 500:
        return f"A coleta PageSpeed/Lighthouse não concluiu porque o serviço externo respondeu com HTTP {status}."
    if status is not None and status >= 400:
        return f"A coleta PageSpeed/Lighthouse não concluiu porque a requisição ao serviço externo respondeu com HTTP {status}."
    return "A coleta PageSpeed/Lighthouse não concluiu por uma falha operacional do serviço externo."


def _lighthouse_public_detail(connection: sqlite3.Connection, audit_id: str) -> str | None:
    run = _one(
        connection,
        "SELECT enabled,status,reason FROM web_performance_runs WHERE audit_id=? ORDER BY rowid DESC LIMIT 1",
        (audit_id,),
    )
    if run is None or not bool(run["enabled"]):
        return None

    attempt = _one(
        connection,
        "SELECT status,http_status,duration_ms,error_code,error_message FROM web_performance_attempts "
        "WHERE audit_id=? AND UPPER(service) LIKE 'PAGESPEED%' ORDER BY created_at DESC,rowid DESC LIMIT 1",
        (audit_id,),
    )
    if attempt is None:
        return (
            "Web Performance foi solicitado, mas nenhuma tentativa PageSpeed/Lighthouse foi materializada. "
            "Consulte Web Performance para o diagnóstico operacional."
        )
    if str(attempt["status"] or "").upper() != "SUCCESS":
        return (
            _friendly_pagespeed_failure(
                error_code=attempt["error_code"],
                error_message=attempt["error_message"],
                http_status=attempt["http_status"],
                duration_ms=attempt["duration_ms"],
            )
            + " Nenhuma categoria Lighthouse válida foi materializada; Core Web Vitals/CrUX, quando disponível, permanece independente."
        )

    observation = _one(
        connection,
        "SELECT status,performance_score,accessibility_score,best_practices_score,seo_score "
        "FROM web_performance_observations WHERE audit_id=? ORDER BY captured_at DESC,rowid DESC LIMIT 1",
        (audit_id,),
    )
    if observation is None:
        return (
            "PageSpeed respondeu, mas nenhum resultado Lighthouse utilizável foi materializado. "
            "Consulte Web Performance para o diagnóstico técnico."
        )
    score_fields = ("performance_score", "accessibility_score", "best_practices_score", "seo_score")
    if not any(observation[name] is not None for name in score_fields):
        return (
            "PageSpeed respondeu, mas nenhuma categoria Lighthouse retornou score utilizável. "
            "Core Web Vitals/CrUX, quando disponível, permanece independente."
        )
    if str(observation["status"] or "").upper() == "PARTIAL":
        return (
            "Lighthouse foi materializado parcialmente; algumas categorias ou contextos podem não ter resultado utilizável. "
            "Consulte Web Performance para o detalhe técnico."
        )
    return None


def _card_title(card: str) -> str:
    match = _TITLE_RE.search(card)
    if match is None:
        return ""
    return re.sub(r"<[^>]+>", "", match.group("title")).strip()


def _article_pattern(title: str) -> re.Pattern[str]:
    """Match exactly one indicator article; never cross a previous card boundary."""
    return re.compile(
        r"<article(?P<attrs>[^>]*\bindicator-card\b[^>]*)>"
        r"(?P<body>(?:(?!</article>).)*?<h3>"
        + re.escape(title)
        + r"</h3>(?:(?!</article>).)*?)</article>",
        flags=re.IGNORECASE | re.DOTALL,
    )


def _rewrite_indicator_card(
    html: str,
    title: str,
    *,
    value: str,
    condition_label: str,
    detail: str,
) -> str:
    pattern = _article_pattern(title)

    def replace(match: re.Match[str]) -> str:
        attrs = re.sub(r"\bcondition-[A-Za-z0-9_-]+\b", "condition-neutral", match.group("attrs"))
        body = match.group("body")
        body, count = re.subn(
            r"<div class=['\"]indicator-values['\"]>.*?</div>",
            f"<div class='score-number indicator-score'>{escape(value)}</div>",
            body,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not count:
            body = re.sub(
                r"<div class=['\"]score-number indicator-score['\"]>.*?</div>",
                f"<div class='score-number indicator-score'>{escape(value)}</div>",
                body,
                count=1,
                flags=re.IGNORECASE | re.DOTALL,
            )
        body = re.sub(
            r"<span class=['\"]indicator-condition['\"]>.*?</span>",
            f"<span class='indicator-condition'>{escape(condition_label)}</span>",
            body,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        body = re.sub(
            r"<p class=['\"]intro['\"]>.*?</p>",
            f"<p class='intro'>{escape(detail)}</p>",
            body,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return f"<article{attrs}>{body}</article>"

    return pattern.sub(replace, html, count=1)


def _rewrite_lighthouse_unavailable(html: str, title: str, detail: str) -> str:
    pattern = _article_pattern(title)

    def replace(match: re.Match[str]) -> str:
        body = match.group("body")
        public_text = re.sub(r"<[^>]+>", " ", body)
        if "NÃO DISPONÍVEL" not in public_text and not any(
            token in public_text.casefold() for token in ("wall_clock_timeout", "wall-clock", "deadline exceeded")
        ):
            return match.group(0)
        attrs = re.sub(r"\bcondition-[A-Za-z0-9_-]+\b", "condition-neutral", match.group("attrs"))
        body = re.sub(
            r"<span class=['\"]indicator-condition['\"]>.*?</span>",
            "<span class='indicator-condition'>Coleta não concluída</span>",
            body,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        body = re.sub(
            r"<p class=['\"]intro['\"]>.*?</p>",
            f"<p class='intro'>{escape(detail)}</p>",
            body,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return f"<article{attrs}>{body}</article>"

    return pattern.sub(replace, html, count=1)


def _sanitize_dependency_notice(html: str, friendly_detail: str | None) -> str:
    if not friendly_detail:
        return html

    def replace(match: re.Match[str]) -> str:
        body = match.group("body")
        if "PageSpeed/Lighthouse" not in body:
            return match.group(0)
        body = re.sub(
            r"<p>.*?</p>",
            f"<p>{escape(friendly_detail)}</p>",
            body,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return f"<section{match.group('attrs')}>{body}</section>"

    return _DEPENDENCY_RE.sub(replace, html)


def _cluster(title: str, kicker: str, intro: str, body: str, css_class: str) -> str:
    return (
        f"<section class='indicator-cluster {escape(css_class, quote=True)}'>"
        "<div class='indicator-cluster-heading'>"
        f"<div class='kicker'>{escape(kicker)}</div><h3>{escape(title)}</h3><p class='intro'>{escape(intro)}</p>"
        "</div>"
        + body
        + "</section>"
    )


def _organize_indicator_groups(html: str) -> str:
    if _GROUP_MARKER in html:
        return html
    match = _SUPPORTING_RE.search(html)
    if match is None:
        return html
    cards = list(_CARD_RE.findall(match.group("body")))
    if not cards:
        return html

    by_title: dict[str, str] = {}
    ordered_titles: list[str] = []
    for card in cards:
        title = _card_title(card)
        if not title or title in by_title:
            continue
        by_title[title] = card
        ordered_titles.append(title)

    web_cards = [by_title[title] for title in (_CWV_TITLE, *_LIGHTHOUSE_TITLES) if title in by_title]
    apdex_cards = [by_title[title] for title in _APDEX_TITLES if title in by_title]
    used = {_CWV_TITLE, *_LIGHTHOUSE_TITLES, *_APDEX_TITLES}
    remaining = [by_title[title] for title in ordered_titles if title not in used]

    groups: list[str] = []
    if web_cards:
        cwv = by_title.get(_CWV_TITLE, "")
        lighthouse = "".join(by_title[title] for title in _LIGHTHOUSE_TITLES if title in by_title)
        subgroups = ""
        if cwv:
            subgroups += (
                "<div class='indicator-subgroup'><div class='indicator-subgroup-label'>Core Web Vitals / CrUX — dados de campo</div>"
                f"<div class='indicator-cluster-grid indicator-cwv-grid'>{cwv}</div></div>"
            )
        if lighthouse:
            subgroups += (
                "<div class='indicator-subgroup'><div class='indicator-subgroup-label'>Chrome Lighthouse — laboratório</div>"
                f"<div class='indicator-cluster-grid indicator-lighthouse-grid'>{lighthouse}</div></div>"
            )
        groups.append(
            _cluster(
                "Web Performance",
                "Campo + laboratório",
                "Core Web Vitals/CrUX e Lighthouse são complementares, mas independentes: uma falha de laboratório não invalida automaticamente dados de campo já obtidos.",
                subgroups,
                "indicator-cluster-web",
            )
        )
    if apdex_cards:
        groups.append(
            _cluster(
                "Apdex sintético",
                "Experiência controlada",
                "Navigation Apdex e User Experience Apdex são medições distintas. Quando não fazem parte do perfil efetivo, aparecem como não solicitadas em vez de falha ou desabilitação técnica.",
                f"<div class='indicator-cluster-grid indicator-apdex-grid'>{''.join(apdex_cards)}</div>",
                "indicator-cluster-apdex",
            )
        )
    if remaining:
        groups.append(
            _cluster(
                "Outros indicadores complementares",
                "Métricas independentes",
                "Indicadores adicionais preservam sua metodologia e página analítica próprias.",
                f"<div class='indicator-cluster-grid indicator-other-grid'>{''.join(remaining)}</div>",
                "indicator-cluster-other",
            )
        )

    open_tag = re.sub(r"\bindicator-grid\b", "indicator-group-shell", match.group("open"), count=1)
    body = f"<div class='indicator-dashboard-groups' {_GROUP_MARKER}>{''.join(groups)}</div>"
    replacement = open_tag + body + match.group("close")
    return html[: match.start()] + replacement + html[match.end() :]


def _inject_style(html: str) -> str:
    if _STYLE_MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "</head>", 1) if "</head>" in html else html


def _reconcile_index(
    html: str,
    *,
    navigation_apdex_requested: bool,
    experience_apdex_requested: bool,
    lighthouse_detail: str | None,
) -> str:
    if not navigation_apdex_requested:
        html = _rewrite_indicator_card(
            html,
            "Synthetic Navigation Apdex",
            value="NÃO SOLICITADO",
            condition_label="Não solicitado",
            detail="Synthetic Navigation Apdex não fez parte do perfil/configuração efetiva desta execução.",
        )
    if not experience_apdex_requested:
        html = _rewrite_indicator_card(
            html,
            "Synthetic User Experience Apdex",
            value="NÃO SOLICITADO",
            condition_label="Não solicitado",
            detail="Synthetic User Experience Apdex não fez parte do perfil/configuração efetiva desta execução.",
        )
    if lighthouse_detail:
        for title in _LIGHTHOUSE_TITLES:
            html = _rewrite_lighthouse_unavailable(html, title, lighthouse_detail)
    html = _sanitize_dependency_notice(html, lighthouse_detail)
    html = _organize_indicator_groups(html)
    return _inject_style(html)


def finalize_dashboard_presentation(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Apply the authoritative final dashboard semantics after every other renderer."""
    report_dir = Path(workspace.root) / "report"
    index = report_dir / "index.html"
    if not index.is_file():
        return

    database = Path(getattr(workspace, "database", Path(workspace.root) / "audit.db"))
    navigation_requested = False
    experience_requested = False
    lighthouse_detail: str | None = None
    if database.is_file():
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        try:
            navigation_requested = _run_requested(connection, audit_id, "synthetic_apdex_runs")
            experience_requested = _run_requested(connection, audit_id, "synthetic_ux_apdex_runs")
            lighthouse_detail = _lighthouse_public_detail(connection, audit_id)
        finally:
            connection.close()

    try:
        html = index.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return
    html = _reconcile_index(
        html,
        navigation_apdex_requested=navigation_requested,
        experience_apdex_requested=experience_requested,
        lighthouse_detail=lighthouse_detail,
    )
    try:
        index.write_text(html, encoding="utf-8", newline="\n")
    except OSError:
        return

    if not lighthouse_detail:
        return
    for filename in ("web-performance.html", "accessibility.html"):
        path = report_dir / filename
        if not path.is_file():
            continue
        try:
            page = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        updated = _sanitize_dependency_notice(page, lighthouse_detail)
        if updated == page:
            continue
        try:
            path.write_text(updated, encoding="utf-8", newline="\n")
        except OSError:
            continue
