"""Deterministic source-quality diagnostics for acquisition, redirects and transport blockers.

This module never disables TLS validation and never turns infrastructure failures into
successful observations. It centralizes a small fail-fast policy used by the core audit,
optional external enrichments and the generated report site.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable
from urllib.parse import urlsplit

from searchgeo.acquisition import HttpAcquisitionResult, NetworkErrorKind
from searchgeo.domain import DeviceContext
from searchgeo.m21_persistence import M21Persistence, WebPerformanceRun
from searchgeo.m21_web_performance import M21ExecutionResult, WebPerformanceConfig
from searchgeo.m23_apdex import M23ExecutionResult, SyntheticApdexConfig
from searchgeo.m23_persistence import M23Persistence, SyntheticApdexRun
from searchgeo.operational_log import try_append_operational_event
from searchgeo.persistence import AuditWorkspace
from searchgeo.rendering import BrowserRenderResult, RenderErrorKind


SOURCE_QUALITY_ARTIFACT = "artifacts/source-quality.json"
SOURCE_QUALITY_AI_ARTIFACT = "artifacts/source-quality-ai.json"
REPORT_MARKER_START = "<!-- searchgeo-source-quality:start -->"
REPORT_MARKER_END = "<!-- searchgeo-source-quality:end -->"

# These states are deterministic transport/topology blockers. SearchGEO must not
# spend downstream API/browser budgets trying to measure a page that was not
# technically reachable under normal certificate/redirect validation.
HARD_NETWORK_ERRORS = frozenset(
    {
        NetworkErrorKind.TLS.value,
        NetworkErrorKind.DNS.value,
        NetworkErrorKind.REDIRECT_LOOP.value,
        NetworkErrorKind.TOO_MANY_REDIRECTS.value,
        NetworkErrorKind.INVALID_REDIRECT.value,
        NetworkErrorKind.PROTOCOL.value,
    }
)


@dataclass(frozen=True, slots=True)
class RedirectDetail:
    status: int
    source_url: str
    location: str
    target_url: str


@dataclass(frozen=True, slots=True)
class SourceQualityIssue:
    requested_url: str
    final_url: str | None
    http_status: int | None
    network_error: str | None
    network_error_message: str | None
    redirects: tuple[RedirectDetail, ...]
    hard_blocker: bool
    severity: str
    classification: str
    deterministic_summary: str
    recommended_actions: tuple[str, ...]
    cross_host_redirect: bool
    http_downgrade_hop: bool

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["redirects"] = [asdict(item) for item in self.redirects]
        value["recommended_actions"] = list(self.recommended_actions)
        return value


@dataclass(frozen=True, slots=True)
class SourceQualityAssessment:
    issues: tuple[SourceQualityIssue, ...]
    pages_considered: int
    hard_blocked_pages: int

    @property
    def has_issue(self) -> bool:
        return bool(self.issues)

    @property
    def all_pages_hard_blocked(self) -> bool:
        return self.pages_considered > 0 and self.hard_blocked_pages >= self.pages_considered

    @property
    def hard_blocker_kinds(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    issue.network_error or issue.classification
                    for issue in self.issues
                    if issue.hard_blocker
                }
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": "SOURCE-QUALITY-1",
            "pages_considered": self.pages_considered,
            "hard_blocked_pages": self.hard_blocked_pages,
            "all_pages_hard_blocked": self.all_pages_hard_blocked,
            "hard_blocker_kinds": list(self.hard_blocker_kinds),
            "issues": [item.as_dict() for item in self.issues],
        }


def assess_acquisitions(acquisitions: Iterable[HttpAcquisitionResult]) -> SourceQualityAssessment:
    items = tuple(acquisitions)
    issues = tuple(_issue_from_acquisition(item) for item in items if _is_noteworthy(item))
    hard = sum(
        1
        for item in items
        if item.network_error is not None and item.network_error.kind.value in HARD_NETWORK_ERRORS
    )
    return SourceQualityAssessment(issues=issues, pages_considered=len(items), hard_blocked_pages=hard)


def assess_m2_result(m2_result: Any) -> SourceQualityAssessment:
    return assess_acquisitions(m2_result.discovery.page_acquisitions.values())


def _is_noteworthy(item: HttpAcquisitionResult) -> bool:
    return bool(
        item.redirects
        or item.network_error is not None
        or item.final_url != item.requested_url
        or (item.status is not None and item.status >= 400)
    )


def _issue_from_acquisition(item: HttpAcquisitionResult) -> SourceQualityIssue:
    network_error = item.network_error.kind.value if item.network_error else None
    hard = network_error in HARD_NETWORK_ERRORS
    redirects = tuple(
        RedirectDetail(
            status=int(hop.status),
            source_url=hop.source_url,
            location=hop.location,
            target_url=hop.target_url,
        )
        for hop in item.redirects
    )
    cross_host = _host(item.requested_url) != _host(item.final_url)
    downgrade = any(
        urlsplit(hop.source_url).scheme.casefold() == "https"
        and urlsplit(hop.target_url).scheme.casefold() == "http"
        for hop in redirects
    )
    severity, classification, summary, actions = _diagnosis(
        requested_url=item.requested_url,
        final_url=item.final_url,
        status=item.status,
        network_error=network_error,
        redirects=redirects,
        cross_host=cross_host,
        downgrade=downgrade,
    )
    return SourceQualityIssue(
        requested_url=item.requested_url,
        final_url=item.final_url,
        http_status=item.status,
        network_error=network_error,
        network_error_message=item.network_error.message if item.network_error else None,
        redirects=redirects,
        hard_blocker=hard,
        severity=severity,
        classification=classification,
        deterministic_summary=summary,
        recommended_actions=actions,
        cross_host_redirect=cross_host,
        http_downgrade_hop=downgrade,
    )


def _diagnosis(
    *,
    requested_url: str,
    final_url: str | None,
    status: int | None,
    network_error: str | None,
    redirects: tuple[RedirectDetail, ...],
    cross_host: bool,
    downgrade: bool,
) -> tuple[str, str, str, tuple[str, ...]]:
    if network_error == NetworkErrorKind.TLS.value:
        return (
            "CRITICAL",
            "TLS_CERTIFICATE_ERROR",
            "A URL final não pôde ser validada por TLS. A auditoria dependente de conteúdo foi limitada antes de repetir chamadas sem valor.",
            (
                "Corrigir o certificado apresentado pelo hostname final, incluindo correspondência CN/SAN, cadeia e configuração SNI.",
                "Confirmar que todos os destinos da cadeia de redirecionamento possuem HTTPS válido antes de reexecutar a auditoria.",
                "Não desabilitar a validação TLS no SearchGEO como forma de contornar o problema.",
            ),
        )
    if network_error == NetworkErrorKind.DNS.value:
        return (
            "HIGH",
            "DNS_RESOLUTION_ERROR",
            "O hostname não pôde ser resolvido por DNS; análises dependentes da página não são tecnicamente representativas.",
            (
                "Validar registros DNS públicos, delegação e propagação do hostname.",
                "Reexecutar somente após o hostname resolver de forma consistente.",
            ),
        )
    if network_error in {
        NetworkErrorKind.REDIRECT_LOOP.value,
        NetworkErrorKind.TOO_MANY_REDIRECTS.value,
        NetworkErrorKind.INVALID_REDIRECT.value,
    }:
        return (
            "HIGH",
            "REDIRECT_TOPOLOGY_ERROR",
            "A cadeia de redirecionamento não termina de forma tecnicamente utilizável.",
            (
                "Corrigir a cadeia para um destino único, válido e alcançável.",
                "Evitar loops, Location inválido e saltos redundantes.",
            ),
        )
    if network_error == NetworkErrorKind.PROTOCOL.value:
        return (
            "HIGH",
            "HTTP_PROTOCOL_ERROR",
            "A aquisição terminou em erro de protocolo antes de produzir uma resposta utilizável.",
            ("Validar terminadores TLS/proxy/CDN e conformidade da resposta HTTP.",),
        )
    if status is not None and status >= 500:
        return (
            "HIGH",
            "HTTP_SERVER_ERROR",
            f"O destino final respondeu HTTP {status}.",
            ("Investigar disponibilidade da aplicação/origem e repetir após estabilização.",),
        )
    if status is not None and status >= 400:
        return (
            "HIGH",
            "HTTP_CLIENT_ERROR",
            f"O destino final respondeu HTTP {status}.",
            ("Confirmar se a URL auditada existe e se o acesso automatizado é permitido.",),
        )
    if redirects:
        notes: list[str] = []
        if cross_host:
            notes.append("O redirecionamento troca o hostname; confirmar se migração/roteamento entre domínios é intencional.")
        if downgrade:
            notes.append("A cadeia contém salto HTTPS → HTTP; eliminar o downgrade quando tecnicamente possível.")
        if not notes:
            notes.append("Confirmar que o redirecionamento permanente/temporário corresponde à política publicada do site.")
        return (
            "WARNING" if (cross_host or downgrade) else "INFO",
            "HTTP_REDIRECT",
            f"A URL solicitada redireciona para {final_url or 'outro destino'}. Redirecionamento pode ser legítimo, mas deve ser analisado no contexto da arquitetura.",
            tuple(notes),
        )
    return (
        "INFO",
        "TRANSPORT_OBSERVATION",
        "A aquisição possui uma diferença de transporte que merece rastreabilidade.",
        (),
    )


def _host(value: str | None) -> str:
    if not value:
        return ""
    try:
        return (urlsplit(value).hostname or "").casefold()
    except ValueError:
        return ""


class PreflightBlockedRenderer:
    """Renderer that materializes a deterministic blocked snapshot without network I/O."""

    def __init__(self, assessment: SourceQualityAssessment) -> None:
        self._issues = {item.requested_url: item for item in assessment.issues}

    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult:
        issue = self._issues.get(url)
        return BrowserRenderResult(
            requested_url=url,
            final_url=issue.final_url if issue else None,
            http_status=issue.http_status if issue else None,
            content_type=None,
            rendered_html=None,
            browser_metadata={
                "engine": "not_started",
                "headless": True,
                "profile": {"device": device.value},
                "navigation": {
                    "wait_until": "not_started",
                    "settle_outcome": "SOURCE_QUALITY_BLOCKED",
                },
                "render_error": RenderErrorKind.NAVIGATION_ERROR.value,
                "render_skipped_reason": (
                    f"SOURCE_QUALITY_BLOCKED:{issue.network_error or issue.classification}"
                    if issue else "SOURCE_QUALITY_BLOCKED"
                ),
            },
            error_kind=RenderErrorKind.NAVIGATION_ERROR,
        )


def persist_assessment(workspace: AuditWorkspace, assessment: SourceQualityAssessment) -> Path:
    path = workspace.root / SOURCE_QUALITY_ARTIFACT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(assessment.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def load_assessment(workspace: AuditWorkspace) -> SourceQualityAssessment | None:
    path = workspace.root / SOURCE_QUALITY_ARTIFACT
    if not path.is_file():
        return _assessment_from_database(workspace.database)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _assessment_from_payload(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return _assessment_from_database(workspace.database)


def _assessment_from_payload(payload: Any) -> SourceQualityAssessment | None:
    if not isinstance(payload, dict):
        return None
    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list):
        return None
    issues: list[SourceQualityIssue] = []
    for raw in raw_issues:
        if not isinstance(raw, dict):
            continue
        redirects = tuple(
            RedirectDetail(
                status=int(item.get("status") or 0),
                source_url=str(item.get("source_url") or ""),
                location=str(item.get("location") or ""),
                target_url=str(item.get("target_url") or ""),
            )
            for item in raw.get("redirects", [])
            if isinstance(item, dict)
        )
        issues.append(
            SourceQualityIssue(
                requested_url=str(raw.get("requested_url") or ""),
                final_url=str(raw.get("final_url")) if raw.get("final_url") else None,
                http_status=int(raw["http_status"]) if raw.get("http_status") is not None else None,
                network_error=str(raw.get("network_error")) if raw.get("network_error") else None,
                network_error_message=str(raw.get("network_error_message")) if raw.get("network_error_message") else None,
                redirects=redirects,
                hard_blocker=bool(raw.get("hard_blocker")),
                severity=str(raw.get("severity") or "INFO"),
                classification=str(raw.get("classification") or "TRANSPORT_OBSERVATION"),
                deterministic_summary=str(raw.get("deterministic_summary") or ""),
                recommended_actions=tuple(str(item) for item in raw.get("recommended_actions", []) if str(item)),
                cross_host_redirect=bool(raw.get("cross_host_redirect")),
                http_downgrade_hop=bool(raw.get("http_downgrade_hop")),
            )
        )
    return SourceQualityAssessment(
        issues=tuple(issues),
        pages_considered=int(payload.get("pages_considered") or len(issues)),
        hard_blocked_pages=int(payload.get("hard_blocked_pages") or sum(item.hard_blocker for item in issues)),
    )


def _assessment_from_database(database: Path) -> SourceQualityAssessment | None:
    if not database.is_file():
        return None
    try:
        connection = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True, timeout=0.5)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT requested_url,final_url,http_status,browser_metadata FROM page_snapshots"
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    issues: list[SourceQualityIssue] = []
    for row in rows:
        try:
            metadata = json.loads(str(row["browser_metadata"] or "{}"))
        except json.JSONDecodeError:
            metadata = {}
        raw = metadata.get("raw_http") if isinstance(metadata, dict) else {}
        if not isinstance(raw, dict):
            raw = {}
        network_error = str(raw.get("network_error")) if raw.get("network_error") else None
        requested = str(raw.get("requested_url") or row["requested_url"] or "")
        final = str(raw.get("final_url") or row["final_url"] or "") or None
        redirect_count = int(raw.get("redirect_count") or 0)
        if not (network_error or redirect_count or final != requested):
            continue
        severity, classification, summary, actions = _diagnosis(
            requested_url=requested,
            final_url=final,
            status=int(row["http_status"]) if row["http_status"] is not None else None,
            network_error=network_error,
            redirects=(),
            cross_host=_host(requested) != _host(final),
            downgrade=False,
        )
        issues.append(
            SourceQualityIssue(
                requested_url=requested,
                final_url=final,
                http_status=int(row["http_status"]) if row["http_status"] is not None else None,
                network_error=network_error,
                network_error_message=None,
                redirects=(),
                hard_blocker=network_error in HARD_NETWORK_ERRORS,
                severity=severity,
                classification=classification,
                deterministic_summary=summary,
                recommended_actions=actions,
                cross_host_redirect=_host(requested) != _host(final),
                http_downgrade_hop=False,
            )
        )
    if not issues:
        return None
    return SourceQualityAssessment(
        issues=tuple(issues),
        pages_considered=len(rows),
        hard_blocked_pages=sum(item.hard_blocker for item in issues),
    )


def limitation_strings(assessment: SourceQualityAssessment) -> tuple[str, ...]:
    values: list[str] = []
    for issue in assessment.issues:
        if not issue.hard_blocker:
            continue
        values.append(
            "Aquisição técnica bloqueada "
            f"({issue.network_error or issue.classification}) para {issue.requested_url}"
            + (f" → {issue.final_url}" if issue.final_url else "")
            + ". Métricas dependentes de conteúdo não são conclusivas."
        )
    return tuple(dict.fromkeys(values))


def persist_m21_source_skip(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    config: WebPerformanceConfig,
    assessment: SourceQualityAssessment,
) -> M21ExecutionResult:
    reason = "SOURCE_QUALITY_BLOCKED:" + ",".join(assessment.hard_blocker_kinds or ("UNKNOWN",))
    with M21Persistence(workspace) as store:
        store.upsert_run(
            WebPerformanceRun(
                audit_id=audit_id,
                enabled=True,
                status="SKIPPED_SOURCE_BLOCKER",
                field_source=config.field_source,
                page_limit=config.max_pages,
                pages_considered=0,
                context_attempts=0,
                successful_contexts=0,
                pagespeed_successes=0,
                crux_successes=0,
                categories=config.categories,
                reason=reason,
                updated_at=_utc_now(),
            )
        )
    try_append_operational_event(
        workspace,
        "M21_COMPLETED",
        audit_id=audit_id,
        status="SKIPPED_SOURCE_BLOCKER",
        reason=reason,
        pages_considered=0,
        context_attempts=0,
        successful_contexts=0,
        partial_contexts=0,
        pagespeed_attempts=0,
        pagespeed_successes=0,
        crux_attempts=0,
        crux_successes=0,
    )
    return M21ExecutionResult(
        status="SKIPPED_SOURCE_BLOCKER",
        enabled=True,
        pages_considered=0,
        context_attempts=0,
        successful_contexts=0,
        pagespeed_attempts=0,
        pagespeed_successes=0,
        crux_attempts=0,
        crux_successes=0,
        partial_contexts=0,
        observation_ids=(),
    )


def persist_m23_source_skip(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    config: SyntheticApdexConfig,
    assessment: SourceQualityAssessment,
) -> M23ExecutionResult:
    reason = "SOURCE_QUALITY_BLOCKED:" + ",".join(assessment.hard_blocker_kinds or ("UNKNOWN",))
    threshold = config.threshold_seconds
    with M23Persistence(workspace) as store:
        store.upsert_run(
            SyntheticApdexRun(
                audit_id=audit_id,
                enabled=True,
                status="SKIPPED_SOURCE_BLOCKER",
                task_id="NAVIGATION_LOAD",
                threshold_seconds=threshold,
                frustration_seconds=(4.0 * threshold if threshold is not None else None),
                target_valid_samples=config.target_valid_samples,
                max_attempts_per_context=config.max_attempts_per_context,
                page_limit=config.max_pages,
                pages_considered=0,
                contexts_considered=0,
                attempted_samples=0,
                valid_samples=0,
                invalid_samples=0,
                delay_seconds=config.delay_seconds,
                concurrency=config.concurrency,
                configuration={
                    "source_quality_skip": True,
                    "target_valid_samples": config.target_valid_samples,
                    "max_attempts_per_context": config.max_attempts_per_context,
                },
                host_environment={},
                reason=reason,
                updated_at=_utc_now(),
            )
        )
    try_append_operational_event(
        workspace,
        "M23_COMPLETED",
        audit_id=audit_id,
        status="SKIPPED_SOURCE_BLOCKER",
        reason=reason,
        attempted_samples=0,
        valid_samples=0,
        invalid_samples=0,
        complete_contexts=0,
        contexts_considered=0,
    )
    return M23ExecutionResult(
        enabled=True,
        status="SKIPPED_SOURCE_BLOCKER",
        pages_considered=0,
        contexts_considered=0,
        attempted_samples=0,
        valid_samples=0,
        invalid_samples=0,
        complete_contexts=0,
        small_group_summaries=0,
    )


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def enrich_source_quality_report_site(*, audit_id: str, workspace: AuditWorkspace) -> None:
    assessment = load_assessment(workspace)
    if assessment is None or not assessment.has_issue:
        return
    ai_payload = _read_optional_json(workspace.root / SOURCE_QUALITY_AI_ARTIFACT)
    block = _report_block(assessment, ai_payload)
    report_dir = workspace.root / "report"
    if not report_dir.is_dir():
        return
    for path in sorted(report_dir.glob("*.html")):
        try:
            html = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if REPORT_MARKER_START in html and REPORT_MARKER_END in html:
            start = html.index(REPORT_MARKER_START)
            end = html.index(REPORT_MARKER_END, start) + len(REPORT_MARKER_END)
            html = html[:start] + block + html[end:]
        elif "</header>" in html:
            html = html.replace("</header>", "</header>" + block, 1)
        elif "<main" in html:
            marker_end = html.find(">", html.find("<main"))
            html = html[: marker_end + 1] + block + html[marker_end + 1 :]
        else:
            continue
        path.write_text(html, encoding="utf-8", newline="\n")


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _report_block(assessment: SourceQualityAssessment, ai_payload: dict[str, Any] | None) -> str:
    cards: list[str] = []
    for issue in assessment.issues:
        if not (issue.redirects or issue.network_error or issue.final_url != issue.requested_url):
            continue
        hops = "".join(
            "<tr>"
            f"<td>{index}</td><td>{hop.status}</td>"
            f"<td><code>{escape(hop.source_url)}</code></td>"
            f"<td><code>{escape(hop.target_url)}</code></td>"
            "</tr>"
            for index, hop in enumerate(issue.redirects, 1)
        )
        chain = (
            "<div class='table-wrap'><table><thead><tr><th>Etapa</th><th>HTTP</th><th>Origem</th><th>Destino</th></tr></thead>"
            f"<tbody>{hops}</tbody></table></div>"
            if hops else ""
        )
        actions = "".join(f"<li>{escape(item)}</li>" for item in issue.recommended_actions)
        final_status = str(issue.http_status) if issue.http_status is not None else "não obtido"
        message = (
            f"<p><strong>Erro técnico:</strong> {escape(issue.network_error)}"
            + (f" — {escape(issue.network_error_message)}" if issue.network_error_message else "")
            + "</p>"
            if issue.network_error else ""
        )
        cards.append(
            "<article class='notice notice-warning source-quality-card'>"
            f"<h3>Transporte HTTP/TLS — {escape(issue.severity)}</h3>"
            f"<p><strong>URL solicitada:</strong> <code>{escape(issue.requested_url)}</code></p>"
            f"<p><strong>URL final observada:</strong> <code>{escape(issue.final_url or 'não resolvida')}</code></p>"
            f"<p><strong>Status HTTP final:</strong> {escape(final_status)} · "
            f"<strong>Classificação:</strong> {escape(issue.classification)}</p>"
            f"{message}{chain}"
            f"<p>{escape(issue.deterministic_summary)}</p>"
            + (f"<ul>{actions}</ul>" if actions else "")
            + "</article>"
        )
    ai_html = ""
    if ai_payload:
        explanation = ai_payload.get("explanation")
        if isinstance(explanation, dict) and explanation.get("summary_pt"):
            actions = "".join(
                f"<li>{escape(str(item))}</li>"
                for item in explanation.get("recommended_actions_pt", [])
                if str(item).strip()
            )
            ai_html = (
                "<details class='notice notice-info source-quality-ai'>"
                "<summary><strong>Explicação complementar por IA</strong> — não altera a classificação técnica</summary>"
                f"<p><strong>Provider/modelo:</strong> {escape(str(ai_payload.get('provider') or '-'))} / "
                f"{escape(str(ai_payload.get('model') or '-'))}</p>"
                f"<p>{escape(str(explanation.get('summary_pt') or ''))}</p>"
                f"<p><strong>Causa provável:</strong> {escape(str(explanation.get('likely_root_cause_pt') or ''))}</p>"
                + (f"<ul>{actions}</ul>" if actions else "")
                + "<p><small>A IA recebe somente evidências técnicas persistidas. A classificação HTTP/TLS acima é determinística e prevalece.</small></p>"
                "</details>"
            )
    return (
        REPORT_MARKER_START
        + "<section class='panel source-quality-panel' id='source-quality'>"
        "<h2>Origem, redirecionamentos e integridade de transporte</h2>"
        "<p>Esta seção distingue a URL configurada no SearchGEO da URL efetivamente alcançada. "
        "Redirecionamentos podem ser normais; falhas TLS/DNS/protocolo são limitações técnicas e não são ignoradas.</p>"
        + "".join(cards)
        + ai_html
        + "</section>"
        + REPORT_MARKER_END
    )
