"""Browser reconciliation for deterministic source-quality preflight blockers.

M2 intentionally uses a small deterministic HTTP client, while M3 represents a real
Chromium navigation with the configured device profile. Some origins/CDNs legitimately
route those clients differently. A hard M2 transport result therefore becomes final only
after the one Chromium navigation that M3 already needs for the audit.

This module never disables TLS validation and never retries synthetic/page-speed work.
It only decides whether the normal M3 browser observation disproved an audit-wide
preflight blocker.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlsplit

from searchgeo.persistence import AuditPersistence, AuditWorkspace
from searchgeo.source_quality import (
    SourceQualityAssessment,
    SourceQualityIssue,
    persist_assessment,
)


@dataclass(frozen=True, slots=True)
class BrowserRouteObservation:
    requested_url: str
    final_url: str
    http_status: int | None
    device: str


@dataclass(frozen=True, slots=True)
class SourceQualityBrowserReconciliation:
    assessment: SourceQualityAssessment
    recovered_urls: tuple[str, ...]
    unresolved_urls: tuple[str, ...]
    browser_observations: tuple[BrowserRouteObservation, ...]

    @property
    def recovered_any(self) -> bool:
        return bool(self.recovered_urls)



def reconcile_source_quality_with_browser(
    *,
    assessment: SourceQualityAssessment,
    m3_result: Any,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
) -> SourceQualityBrowserReconciliation:
    """Reconcile M2 hard blockers with already-executed M3 Chromium snapshots.

    A page is recovered only when at least one configured Chromium context produced a
    rendered document and did not finish with an HTTP >= 400 response. This is not a TLS
    bypass: Chromium still uses its normal certificate validation. It is a second,
    browser-representative observation of the same configured URL.
    """

    observations = _successful_browser_observations(m3_result, persistence)
    by_requested: dict[str, list[BrowserRouteObservation]] = {}
    for item in observations:
        by_requested.setdefault(item.requested_url, []).append(item)

    recovered_urls: list[str] = []
    unresolved_urls: list[str] = []
    reconciled_issues: list[SourceQualityIssue] = []

    for issue in assessment.issues:
        browser = tuple(by_requested.get(issue.requested_url, ()))
        if issue.hard_blocker and browser:
            recovered_urls.append(issue.requested_url)
            reconciled_issues.append(_recovered_issue(issue, browser))
        else:
            if issue.hard_blocker:
                unresolved_urls.append(issue.requested_url)
            reconciled_issues.append(issue)

    recovered_unique = tuple(dict.fromkeys(recovered_urls))
    unresolved_unique = tuple(dict.fromkeys(unresolved_urls))
    hard_blocked_pages = max(assessment.hard_blocked_pages - len(recovered_unique), 0)
    reconciled = SourceQualityAssessment(
        issues=tuple(reconciled_issues),
        pages_considered=assessment.pages_considered,
        hard_blocked_pages=hard_blocked_pages,
    )
    persist_assessment(workspace, reconciled)
    return SourceQualityBrowserReconciliation(
        assessment=reconciled,
        recovered_urls=recovered_unique,
        unresolved_urls=unresolved_unique,
        browser_observations=observations,
    )



def browser_reconciliation_limitations(
    reconciliation: SourceQualityBrowserReconciliation,
) -> tuple[str, ...]:
    """Return analyst-facing limitations for recovered HTTP/browser divergence."""

    values: list[str] = []
    recovered = set(reconciliation.recovered_urls)
    for issue in reconciliation.assessment.issues:
        if issue.requested_url not in recovered:
            continue
        values.append(
            "Aquisição HTTP e Chromium observaram rotas técnicas diferentes para "
            f"{issue.requested_url}. O Chromium alcançou conteúdo válido e a auditoria "
            "prosseguiu, mas a divergência de redirecionamento/TLS deve ser revisada."
        )
    return tuple(dict.fromkeys(values))



def _successful_browser_observations(
    m3_result: Any,
    persistence: AuditPersistence,
) -> tuple[BrowserRouteObservation, ...]:
    output: list[BrowserRouteObservation] = []
    for per_device in m3_result.snapshot_ids.values():
        for device, snapshot_id in per_device.items():
            snapshot = persistence.snapshots.get(snapshot_id)
            if snapshot is None:
                continue
            metadata = snapshot.browser_metadata if isinstance(snapshot.browser_metadata, dict) else {}
            if not bool(metadata.get("render_succeeded")):
                continue
            if not snapshot.rendered_artifact_ref:
                continue
            if snapshot.http_status is not None and int(snapshot.http_status) >= 400:
                continue
            final_url = str(snapshot.final_url or snapshot.requested_url or "").strip()
            requested_url = str(snapshot.requested_url or "").strip()
            if not requested_url or not final_url:
                continue
            output.append(
                BrowserRouteObservation(
                    requested_url=requested_url,
                    final_url=final_url,
                    http_status=(int(snapshot.http_status) if snapshot.http_status is not None else None),
                    device=getattr(device, "value", str(device)),
                )
            )
    return tuple(output)



def _recovered_issue(
    issue: SourceQualityIssue,
    observations: tuple[BrowserRouteObservation, ...],
) -> SourceQualityIssue:
    ordered = tuple(sorted(observations, key=lambda item: (item.device, item.final_url)))
    primary = ordered[0]
    browser_routes = "; ".join(
        f"{item.device}: {item.final_url}"
        + (f" (HTTP {item.http_status})" if item.http_status is not None else "")
        for item in ordered
    )
    preflight_route = issue.final_url or "destino não resolvido"
    preflight_error = issue.network_error or issue.classification
    summary = (
        "A aquisição HTTP preliminar observou "
        f"{preflight_route} e terminou em {preflight_error}, mas o Chromium do perfil "
        f"auditado alcançou conteúdo válido ({browser_routes}). O bloqueio global foi "
        "revogado e as métricas continuam com a evidência de navegador. A divergência "
        "permanece registrada porque pode indicar roteamento condicionado por User-Agent, "
        "CDN/proxy, política anti-bot ou configuração distinta entre clientes."
    )
    actions = (
        "Comparar a política de redirecionamento entregue a navegadores e clientes HTTP automatizados.",
        "Validar regras de CDN/proxy/WAF, canonicalização de domínio e tratamento de User-Agent sem assumir que a divergência é intencional.",
        "Confirmar que a URL final observada pelo Chromium corresponde à URL pública esperada para o dispositivo auditado.",
        "Preservar validação TLS; não usar bypass de certificado como forma de uniformizar as rotas.",
    )
    return replace(
        issue,
        final_url=primary.final_url,
        http_status=primary.http_status,
        network_error=None,
        network_error_message=None,
        hard_blocker=False,
        severity="WARNING",
        classification="HTTP_BROWSER_ROUTE_DIVERGENCE",
        deterministic_summary=summary,
        recommended_actions=actions,
        cross_host_redirect=_host(issue.requested_url) != _host(primary.final_url),
    )



def _host(value: str | None) -> str:
    if not value:
        return ""
    try:
        return (urlsplit(value).hostname or "").casefold()
    except ValueError:
        return ""
