"""M2 execution glue: persist Discovery + HTTP into the M1 audit model."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

from rasai.discovery import DiscoveryEngine, DiscoveryResult, SitemapResult
from rasai.domain import (
    Audit,
    AuditStatus,
    AuditTarget,
    DiscoverySource,
    Evidence,
    EvidenceType,
    Page,
    RuleExecution,
    RuleResult,
    new_id,
    utc_now,
)
from rasai.m14_discovery import discover_url_set
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.url_utils import normalize_url, normalized_origin


_RULE_VERSION = "1"
_REDIRECT_FAILURES = {"REDIRECT_LOOP", "TOO_MANY_REDIRECTS", "INVALID_REDIRECT"}


@dataclass(frozen=True, slots=True)
class M2ExecutionResult:
    discovery: DiscoveryResult
    page_ids: dict[str, str]
    raw_artifact_refs: dict[str, str | None]
    evidence_ids: tuple[str, ...]
    rule_execution_ids: tuple[str, ...]


def execute_m2(
    audit: Audit,
    target: AuditTarget,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
    *,
    engine: DiscoveryEngine | None = None,
    explicit_urls: tuple[str, ...] | None = None,
) -> M2ExecutionResult:
    """Execute and persist M2 discovery/HTTP for one domain audit.

    When ``explicit_urls`` is supplied, the page universe is exactly that
    normalized URL set.  robots.txt and sitemap resources remain domain-scoped
    and are acquired once for the audit.
    """

    if target.audit_id != audit.audit_id:
        raise ValueError("audit target must belong to the audit")
    if workspace.root.name != audit.audit_id:
        raise ValueError("audit workspace must belong to the audit")

    seed = normalize_url(target.input_url)
    origin = normalized_origin(seed)
    if normalized_origin(target.normalized_origin) != origin:
        raise ValueError("audit target normalized_origin is inconsistent with input_url")

    stored_audit = persistence.audits.get(audit.audit_id)
    if stored_audit is None:
        persistence.audits.add(audit)
    stored_target = persistence.targets.get(target.target_id)
    if stored_target is None:
        persistence.targets.add(target)
    elif stored_target != target:
        raise ValueError("stored audit target differs from supplied target")

    current = persistence.audits.get(audit.audit_id) or audit
    discovering = replace(current, status=AuditStatus.DISCOVERING)
    persistence.audits.update(discovering)

    active_engine = engine or DiscoveryEngine()
    if explicit_urls is None:
        discovery = active_engine.discover(seed, max_pages=audit.max_pages)
    else:
        custom_url_set = getattr(active_engine, "discover_url_set", None)
        if callable(custom_url_set):
            discovery = custom_url_set(explicit_urls, max_pages=audit.max_pages)
        elif isinstance(active_engine, DiscoveryEngine):
            discovery = discover_url_set(active_engine, explicit_urls, max_pages=audit.max_pages)
        else:
            raise ValueError(
                "a custom discovery engine used with URL_SET must implement discover_url_set(urls, max_pages=...)"
            )

    page_ids: dict[str, str] = {}
    pages: dict[str, Page] = {}
    for discovered in discovery.pages:
        page = Page(
            page_id=new_id("PGE"),
            audit_id=audit.audit_id,
            normalized_url=discovered.normalized_url,
            discovered_url=discovered.discovered_url,
            discovery_sources=discovered.discovery_sources,
            depth=discovered.depth,
        )
        persistence.pages.add(page)
        page_ids[page.normalized_url] = page.page_id
        pages[page.normalized_url] = page

    evidence_ids: list[str] = []
    provenance_evidence: dict[str, list[str]] = {url: [] for url in page_ids}

    for record in discovery.provenance:
        page_id = page_ids.get(record.target_url)
        if page_id is None:
            continue
        evidence_type = (
            EvidenceType.SITEMAP_ENTRY if record.source is DiscoverySource.SITEMAP else EvidenceType.LINK
        )
        evidence = Evidence(
            evidence_id=new_id("EV-GEO"),
            audit_id=audit.audit_id,
            page_id=page_id,
            snapshot_id=None,
            device=None,
            evidence_type=evidence_type,
            source=f"discovery:{record.source.value}",
            observed_value={
                "source": record.source.value,
                "source_url": record.source_url,
                "discovered_url": record.discovered_url,
                "normalized_url": record.target_url,
            },
            artifact_reference=None,
            captured_at=utc_now(),
        )
        persistence.evidence.add(evidence)
        evidence_ids.append(evidence.evidence_id)
        provenance_evidence[record.target_url].append(evidence.evidence_id)

    http_evidence: dict[str, list[str]] = {}
    raw_artifact_refs: dict[str, str | None] = {}
    for url, acquisition in discovery.page_acquisitions.items():
        page_id = page_ids[url]
        artifact_reference = _write_body_artifact(
            workspace,
            f"page-{page_id}",
            acquisition.body,
        )
        raw_artifact_refs[url] = artifact_reference
        response_evidence = Evidence(
            evidence_id=new_id("EV-GEO"),
            audit_id=audit.audit_id,
            page_id=page_id,
            snapshot_id=None,
            device=None,
            evidence_type=EvidenceType.HTTP_RESPONSE,
            source="http",
            observed_value=_http_observed_value(acquisition),
            artifact_reference=artifact_reference,
            captured_at=utc_now(),
        )
        persistence.evidence.add(response_evidence)
        evidence_ids.append(response_evidence.evidence_id)
        http_evidence.setdefault(url, []).append(response_evidence.evidence_id)

        if acquisition.headers:
            header_evidence = Evidence(
                evidence_id=new_id("EV-GEO"),
                audit_id=audit.audit_id,
                page_id=page_id,
                snapshot_id=None,
                device=None,
                evidence_type=EvidenceType.HTTP_HEADER,
                source="http",
                observed_value={"headers": [list(item) for item in acquisition.headers]},
                artifact_reference=None,
                captured_at=utc_now(),
            )
            persistence.evidence.add(header_evidence)
            evidence_ids.append(header_evidence.evidence_id)
            http_evidence[url].append(header_evidence.evidence_id)

    robots_artifact = _write_body_artifact(
        workspace,
        "robots",
        discovery.robots.acquisition.body,
    )
    robots_evidence = Evidence(
        evidence_id=new_id("EV-GEO"),
        audit_id=audit.audit_id,
        page_id=None,
        snapshot_id=None,
        device=None,
        evidence_type=EvidenceType.ROBOTS_RULE,
        source=discovery.robots.url,
        observed_value={
            "state": discovery.robots.state.value,
            "http": _http_observed_value(discovery.robots.acquisition),
            "declared_sitemaps": list(discovery.robots.sitemap_urls),
            "crawler_access": discovery.robots.crawler_access,
        },
        artifact_reference=robots_artifact,
        captured_at=utc_now(),
    )
    persistence.evidence.add(robots_evidence)
    evidence_ids.append(robots_evidence.evidence_id)

    conventional_sitemap = normalize_url("/sitemap.xml", base_url=f"{discovery.origin}/")
    declared_sitemaps = set(discovery.robots.sitemap_urls)
    for sitemap in discovery.sitemaps:
        if sitemap.url in declared_sitemaps:
            discovery_origin = "ROBOTS_TXT"
        elif sitemap.url == conventional_sitemap:
            discovery_origin = "CONVENTIONAL_PATH"
        else:
            discovery_origin = "SITEMAP_INDEX"
        evidence = _persist_sitemap_evidence(
            audit,
            persistence,
            workspace,
            sitemap,
            discovery_origin=discovery_origin,
        )
        evidence_ids.append(evidence.evidence_id)

    rule_execution_ids: list[str] = []
    for url, page in pages.items():
        provenance_ids = tuple(provenance_evidence.get(url, ()))
        provenance_execution = RuleExecution(
            rule_execution_id=new_id("REX"),
            audit_id=audit.audit_id,
            rule_id="BR-GEO-002",
            rule_version=_RULE_VERSION,
            page_id=page.page_id,
            snapshot_id=None,
            device=None,
            result=RuleResult.PASS if page.discovery_sources and provenance_ids else RuleResult.ERROR,
            observed_value={"discovery_sources": [source.value for source in page.discovery_sources]},
            expected_condition="every discovered URL has traceable discovery provenance",
            evidence_ids=provenance_ids,
            executed_at=utc_now(),
            error=None if provenance_ids else "discovery provenance evidence was not persisted",
        )
        persistence.rule_executions.add(provenance_execution)
        rule_execution_ids.append(provenance_execution.rule_execution_id)

        acquisition = discovery.page_acquisitions[url]
        http_ids = tuple(http_evidence[url])
        preserved_execution = RuleExecution(
            rule_execution_id=new_id("REX"),
            audit_id=audit.audit_id,
            rule_id="BR-GEO-004",
            rule_version=_RULE_VERSION,
            page_id=page.page_id,
            snapshot_id=None,
            device=None,
            result=RuleResult.PASS,
            observed_value={
                "requested_url": acquisition.requested_url,
                "final_url": acquisition.final_url,
                "status": acquisition.status,
                "network_error": acquisition.network_error.kind.value if acquisition.network_error else None,
                "body_preserved": bool(acquisition.body),
            },
            expected_condition="HTTP acquisition result and body artifact are preserved when available",
            evidence_ids=http_ids,
            executed_at=utc_now(),
        )
        persistence.rule_executions.add(preserved_execution)
        rule_execution_ids.append(preserved_execution.rule_execution_id)

        retrievable = acquisition.network_error is None and acquisition.status is not None
        retrievable_execution = RuleExecution(
            rule_execution_id=new_id("REX"),
            audit_id=audit.audit_id,
            rule_id="BR-GEO-005",
            rule_version=_RULE_VERSION,
            page_id=page.page_id,
            snapshot_id=None,
            device=None,
            result=RuleResult.PASS if retrievable else RuleResult.FAIL,
            observed_value={
                "status": acquisition.status,
                "network_error": acquisition.network_error.kind.value if acquisition.network_error else None,
            },
            expected_condition="page yields a technical HTTP response without DNS/TLS/connection/timeout failure",
            evidence_ids=http_ids,
            executed_at=utc_now(),
        )
        persistence.rule_executions.add(retrievable_execution)
        rule_execution_ids.append(retrievable_execution.rule_execution_id)

        error_kind = acquisition.network_error.kind.value if acquisition.network_error else None
        if error_kind in _REDIRECT_FAILURES:
            redirect_result = RuleResult.FAIL
        elif acquisition.network_error is not None:
            redirect_result = RuleResult.NOT_APPLICABLE
        else:
            redirect_result = RuleResult.PASS
        redirect_execution = RuleExecution(
            rule_execution_id=new_id("REX"),
            audit_id=audit.audit_id,
            rule_id="BR-GEO-007",
            rule_version=_RULE_VERSION,
            page_id=page.page_id,
            snapshot_id=None,
            device=None,
            result=redirect_result,
            observed_value={
                "redirects": [
                    {
                        "status": hop.status,
                        "source_url": hop.source_url,
                        "location": hop.location,
                        "target_url": hop.target_url,
                    }
                    for hop in acquisition.redirects
                ],
                "network_error": error_kind,
            },
            expected_condition="redirect chain resolves without loops or invalid hops",
            evidence_ids=http_ids,
            executed_at=utc_now(),
        )
        persistence.rule_executions.add(redirect_execution)
        rule_execution_ids.append(redirect_execution.rule_execution_id)

    limitations = list(discovering.limitations)
    if discovery.limit_reached:
        limitations.append(
            f"MAX_PAGES_REACHED:discovered={discovery.total_discovered};audited={discovery.total_audited}"
        )
    acquiring = replace(discovering, status=AuditStatus.ACQUIRING, limitations=tuple(dict.fromkeys(limitations)))
    persistence.audits.update(acquiring)

    return M2ExecutionResult(
        discovery=discovery,
        page_ids=page_ids,
        raw_artifact_refs=raw_artifact_refs,
        evidence_ids=tuple(evidence_ids),
        rule_execution_ids=tuple(rule_execution_ids),
    )


def _persist_sitemap_evidence(
    audit: Audit,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
    sitemap: SitemapResult,
    *,
    discovery_origin: str,
) -> Evidence:
    digest = sha256(sitemap.url.encode("utf-8")).hexdigest()[:16]
    artifact_reference = _write_body_artifact(workspace, f"sitemap-{digest}", sitemap.acquisition.body)
    evidence = Evidence(
        evidence_id=new_id("EV-GEO"),
        audit_id=audit.audit_id,
        page_id=None,
        snapshot_id=None,
        device=None,
        evidence_type=EvidenceType.SITEMAP_ENTRY,
        source=sitemap.url,
        observed_value={
            "state": sitemap.state.value,
            "discovery_origin": discovery_origin,
            "http": _http_observed_value(sitemap.acquisition),
            "url_count": len(sitemap.page_urls),
            "page_urls": list(sitemap.page_urls),
            "child_sitemaps": list(sitemap.child_sitemaps),
            "error": sitemap.error,
        },
        artifact_reference=artifact_reference,
        captured_at=utc_now(),
    )
    persistence.evidence.add(evidence)
    return evidence


def _write_body_artifact(workspace: AuditWorkspace, stem: str, body: bytes) -> str | None:
    if not body:
        return None
    directory = workspace.artifacts / "http"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}.response"
    path.write_bytes(body)
    return Path("artifacts", "http", path.name).as_posix()


def _http_observed_value(acquisition) -> dict[str, object]:
    return {
        "requested_url": acquisition.requested_url,
        "final_url": acquisition.final_url,
        "status": acquisition.status,
        "headers": [list(item) for item in acquisition.headers],
        "redirect_chain": [
            {
                "status": hop.status,
                "source_url": hop.source_url,
                "location": hop.location,
                "target_url": hop.target_url,
            }
            for hop in acquisition.redirects
        ],
        "network_error": (
            {
                "kind": acquisition.network_error.kind.value,
                "message": acquisition.network_error.message,
            }
            if acquisition.network_error
            else None
        ),
        "elapsed_ms": acquisition.elapsed_ms,
        "body_bytes": len(acquisition.body),
        "content_type": acquisition.header("Content-Type"),
    }
