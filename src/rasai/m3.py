"""M3 execution glue: browser rendering and independent device snapshots."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
import json
import re
import sqlite3
import time
from typing import Protocol

from rasai.browser_identity_renderer import BrowserIdentityRenderer
from rasai.device_context import runtime_devices
from rasai.domain import DeviceContext, Evidence, EvidenceType, PageSnapshot, new_id, utc_now
from rasai.m14_persistence import ElementObservation, M14Persistence
from rasai.m2 import M2ExecutionResult
from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.rendering import (
    BrowserRenderResult,
    BrowserRenderer,
    RenderErrorKind,
    RenderedElementObservation,
)

_RENDERING_MODE = "PLAYWRIGHT_CHROMIUM"
_DEVICES = (DeviceContext.DESKTOP, DeviceContext.MOBILE)  # legacy internal reference; runtime selection is configurable.
_TITLE_ELEMENT_RE = re.compile(r"<title\b[^>]*>.*?</title\s*>", re.IGNORECASE | re.DOTALL)


class Renderer(Protocol):
    def render(self, url: str, device: DeviceContext) -> BrowserRenderResult: ...


@dataclass(frozen=True, slots=True)
class RenderFailure:
    page_id: str
    device: DeviceContext
    error_kind: str


@dataclass(frozen=True, slots=True)
class M3ExecutionResult:
    snapshot_ids: dict[str, dict[DeviceContext, str]]
    failures: tuple[RenderFailure, ...]
    visual_artifact_refs: dict[str, dict[DeviceContext, str | None]] = field(default_factory=dict)


def persist_render_capture(
    *,
    page: object,
    url: str,
    acquisition: object,
    raw_artifact_ref: str | None,
    device: DeviceContext,
    render_result: BrowserRenderResult,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
    audit_device_context: tuple[DeviceContext, ...],
    snapshot_id: str | None = None,
    captured_at: object | None = None,
    replace_existing: bool = False,
    artifact_namespace: tuple[str, ...] = (),
    reprocess_metadata: dict[str, object] | None = None,
    m14: M14Persistence | None = None,
) -> tuple[PageSnapshot, str | None]:
    """Persist one canonical M3 render capture for initial execution or RPR.

    The caller may select/replace a single context, but snapshot fields, browser
    metadata, visual evidence and DOM element observations use this one persistence
    contract.  Artifact namespace is the only storage-layout distinction used by RPR.
    """
    active_snapshot_id = snapshot_id or new_id("SNP")
    active_captured_at = captured_at or utc_now()
    rendered_artifact_ref = _write_rendered_artifact(
        workspace,
        str(getattr(page, "page_id")),
        device,
        active_snapshot_id,
        render_result.rendered_html,
        namespace=artifact_namespace,
    )
    visual_artifact_ref = _write_visual_artifact(
        workspace,
        str(getattr(page, "page_id")),
        device,
        active_snapshot_id,
        render_result.screenshot_png,
        namespace=artifact_namespace,
    )

    browser_metadata = dict(render_result.browser_metadata)
    browser_metadata["raw_http"] = {
        "requested_url": acquisition.requested_url,
        "final_url": acquisition.final_url,
        "status": acquisition.status,
        "redirect_count": len(acquisition.redirects),
        "redirects": [
            {
                "status": hop.status,
                "source_url": hop.source_url,
                "location": hop.location,
                "target_url": hop.target_url,
            }
            for hop in acquisition.redirects
        ],
        "network_error": acquisition.network_error.kind.value if acquisition.network_error else None,
        # Keep the same secret-safe response-control subset used by initial M3.
        "x_robots_tag": list(acquisition.header_values("X-Robots-Tag")),
    }
    browser_metadata["render_succeeded"] = render_result.succeeded
    browser_metadata["visual_artifact_ref"] = visual_artifact_ref
    browser_metadata["audit_device_context"] = [item.value for item in audit_device_context]
    if reprocess_metadata:
        browser_metadata["reprocess_capture"] = dict(reprocess_metadata)

    snapshot = PageSnapshot(
        snapshot_id=active_snapshot_id,
        page_id=str(getattr(page, "page_id")),
        device=device,
        requested_url=url,
        final_url=render_result.final_url or acquisition.final_url,
        captured_at=active_captured_at,
        http_status=(render_result.http_status if render_result.http_status is not None else acquisition.status),
        content_type=(render_result.content_type or acquisition.header("Content-Type")),
        rendering_mode=_RENDERING_MODE,
        raw_artifact_ref=raw_artifact_ref,
        rendered_artifact_ref=rendered_artifact_ref,
        browser_metadata=browser_metadata,
    )

    if replace_existing:
        connection = sqlite3.connect(workspace.database)
        try:
            existing = connection.execute(
                "SELECT page_id,device FROM page_snapshots WHERE snapshot_id=?",
                (active_snapshot_id,),
            ).fetchone()
            if existing is None:
                raise ValueError(f"snapshot not found for replacement: {active_snapshot_id}")
            if str(existing[0]) != snapshot.page_id or str(existing[1]) != snapshot.device.value:
                raise ValueError("replacement snapshot scope differs from persisted page/device")
            with connection:
                connection.execute(
                    """UPDATE page_snapshots SET
                       requested_url=?,final_url=?,captured_at=?,http_status=?,content_type=?,
                       title=NULL,description=NULL,canonical=NULL,meta_robots=NULL,rendering_mode=?,
                       raw_artifact_ref=?,rendered_artifact_ref=?,main_content_ref=NULL,
                       structured_data_ref=NULL,browser_metadata=?,architecture_classification=?
                       WHERE snapshot_id=?""",
                    (
                        snapshot.requested_url,
                        snapshot.final_url,
                        snapshot.captured_at.isoformat(),
                        snapshot.http_status,
                        snapshot.content_type,
                        snapshot.rendering_mode,
                        snapshot.raw_artifact_ref,
                        snapshot.rendered_artifact_ref,
                        json.dumps(snapshot.browser_metadata, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
                        snapshot.architecture_classification.value,
                        snapshot.snapshot_id,
                    ),
                )
        finally:
            connection.close()
    else:
        persistence.snapshots.add(snapshot)

    if visual_artifact_ref is not None:
        viewport = (
            browser_metadata.get("profile", {}).get("viewport", {})
            if isinstance(browser_metadata.get("profile"), dict)
            else {}
        )
        persistence.evidence.add(
            Evidence(
                evidence_id=new_id("EV-GEO"),
                audit_id=str(getattr(page, "audit_id")),
                page_id=snapshot.page_id,
                snapshot_id=snapshot.snapshot_id,
                device=device,
                evidence_type=EvidenceType.VISUAL_SNAPSHOT,
                source="chromium:viewport",
                observed_value={
                    "requested_url": url,
                    "final_url": snapshot.final_url,
                    "viewport": viewport,
                    "artifact_reference": visual_artifact_ref,
                },
                artifact_reference=visual_artifact_ref,
                captured_at=active_captured_at,
            )
        )

    observations = _align_title_observation_to_rendered_artifact(render_result)
    owns_m14 = m14 is None
    active_m14 = m14 or M14Persistence(workspace)
    try:
        for observed in observations:
            observation_artifact_ref = (
                rendered_artifact_ref
                if observed.tag_name.casefold() == "title" and rendered_artifact_ref is not None
                else visual_artifact_ref
            )
            active_m14.add_element_observation(
                ElementObservation(
                    element_observation_id=new_id("ELM"),
                    audit_id=str(getattr(page, "audit_id")),
                    page_id=snapshot.page_id,
                    snapshot_id=snapshot.snapshot_id,
                    device=device,
                    url=snapshot.final_url or url,
                    selector=observed.selector,
                    tag_name=observed.tag_name,
                    element_id=observed.element_id,
                    classes=observed.classes,
                    outer_html=observed.outer_html,
                    text_excerpt=observed.text_excerpt,
                    bounding_box=observed.bounding_box,
                    artifact_reference=observation_artifact_ref,
                    captured_at=active_captured_at,
                )
            )
    finally:
        if owns_m14:
            active_m14.close()

    return snapshot, visual_artifact_ref


def execute_m3(
    m2_result: M2ExecutionResult,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
    *,
    renderer: Renderer | None = None,
) -> M3ExecutionResult:
    """Render every M2 page for the configured device context and persist snapshots."""
    active_renderer: Renderer = renderer or BrowserIdentityRenderer()
    renderer_context = active_renderer if isinstance(active_renderer, BrowserRenderer) else nullcontext(active_renderer)
    snapshot_ids: dict[str, dict[DeviceContext, str]] = {}
    visual_artifact_refs: dict[str, dict[DeviceContext, str | None]] = {}
    failures: list[RenderFailure] = []
    devices = runtime_devices()
    pages = tuple(m2_result.discovery.pages)
    total_contexts = len(pages) * len(devices)
    context_index = 0

    with M14Persistence(workspace) as m14, renderer_context as session_renderer:
        for page_index, discovered in enumerate(pages, start=1):
            url = discovered.normalized_url
            page_id = m2_result.page_ids[url]
            page = persistence.pages.get(page_id)
            if page is None or page.normalized_url != url:
                raise ValueError(f"M2 page mapping is inconsistent for {url}")

            acquisition = m2_result.discovery.page_acquisitions[url]
            raw_artifact_ref = m2_result.raw_artifact_refs.get(url)
            if acquisition.body and not raw_artifact_ref:
                raise ValueError(f"M2 RAW artifact reference is missing for {url}")
            if raw_artifact_ref and not (workspace.root / raw_artifact_ref).is_file():
                raise FileNotFoundError(f"M2 RAW artifact is not re-openable: {raw_artifact_ref}")

            per_device: dict[DeviceContext, str] = {}
            per_device_visual: dict[DeviceContext, str | None] = {}
            for device_index, device in enumerate(devices, start=1):
                context_index += 1
                preflight_navigation_trace = [
                    {"url": hop.source_url, "status": hop.status, "location": hop.location}
                    for hop in acquisition.redirects
                ]
                try_append_operational_event(
                    workspace,
                    "M3_RENDER_STARTED",
                    audit_id=page.audit_id,
                    page_id=page_id,
                    url=url,
                    device=device.value,
                    page_index=page_index,
                    page_total=len(pages),
                    device_index=device_index,
                    device_total=len(devices),
                    context_index=context_index,
                    context_total=total_contexts,
                    additional_network_requests=0,
                )
                render_started = time.monotonic()
                try:
                    if isinstance(session_renderer, BrowserIdentityRenderer):
                        render_result = session_renderer.render(
                            url,
                            device,
                            preflight_navigation_trace=preflight_navigation_trace,
                        )
                    else:
                        render_result = session_renderer.render(url, device)
                except Exception as exc:
                    try_append_operational_event(
                        workspace,
                        "M3_RENDER_EXCEPTION",
                        level="WARNING",
                        audit_id=page.audit_id,
                        page_id=page_id,
                        url=url,
                        device=device.value,
                        context_index=context_index,
                        context_total=total_contexts,
                        error_type=type(exc).__name__,
                        error_message=str(exc)[:512],
                    )
                    render_result = _unexpected_failure(url, device)

                duration_ms = int(max(time.monotonic() - render_started, 0.0) * 1000.0)
                document_source = render_result.browser_metadata.get("document_source")
                document_source_state = (
                    str(document_source.get("capture_state") or "NOT_AVAILABLE")
                    if isinstance(document_source, dict)
                    else "NOT_AVAILABLE"
                )
                try_append_operational_event(
                    workspace,
                    "M3_RENDER_COMPLETED",
                    audit_id=page.audit_id,
                    page_id=page_id,
                    url=url,
                    final_url=render_result.final_url,
                    device=device.value,
                    page_index=page_index,
                    page_total=len(pages),
                    context_index=context_index,
                    context_total=total_contexts,
                    duration_ms=duration_ms,
                    render_status=(render_result.error_kind.value if render_result.error_kind is not None else "SUCCESS"),
                    document_source_state=document_source_state,
                )

                snapshot, visual_artifact_ref = persist_render_capture(
                    page=page,
                    url=url,
                    acquisition=acquisition,
                    raw_artifact_ref=raw_artifact_ref,
                    device=device,
                    render_result=render_result,
                    persistence=persistence,
                    workspace=workspace,
                    audit_device_context=tuple(devices),
                    m14=m14,
                )
                snapshot_id = snapshot.snapshot_id
                per_device[device] = snapshot.snapshot_id
                per_device_visual[device] = visual_artifact_ref
                try_append_operational_event(
                    workspace,
                    "M3_SNAPSHOT_PERSISTED",
                    audit_id=page.audit_id,
                    page_id=page_id,
                    snapshot_id=snapshot_id,
                    url=url,
                    device=device.value,
                    context_index=context_index,
                    context_total=total_contexts,
                    render_succeeded=render_result.succeeded,
                )

                if render_result.error_kind is not None:
                    failures.append(RenderFailure(page_id=page_id, device=device, error_kind=render_result.error_kind.value))
            snapshot_ids[page_id] = per_device
            visual_artifact_refs[page_id] = per_device_visual

    return M3ExecutionResult(
        snapshot_ids=snapshot_ids,
        failures=tuple(failures),
        visual_artifact_refs=visual_artifact_refs,
    )


def _align_title_observation_to_rendered_artifact(
    render_result: BrowserRenderResult,
) -> tuple[RenderedElementObservation, ...]:
    """Bind title evidence to the serialized DOM consumed by M4/M7."""
    if render_result.rendered_html is None:
        return render_result.element_observations
    non_title = tuple(
        observation for observation in render_result.element_observations
        if observation.tag_name.casefold() != "title"
    )
    match = _TITLE_ELEMENT_RE.search(render_result.rendered_html)
    if match is None:
        return non_title
    outer_html = match.group(0)[:4096]
    title = RenderedElementObservation(
        selector="title",
        tag_name="title",
        element_id=None,
        classes=(),
        outer_html=outer_html,
        text_excerpt=None,
        bounding_box=None,
    )
    return (title, *non_title)


def _write_rendered_artifact(
    workspace: AuditWorkspace,
    page_id: str,
    device: DeviceContext,
    snapshot_id: str,
    rendered_html: str | None,
    *,
    namespace: tuple[str, ...] = (),
) -> str | None:
    if rendered_html is None:
        return None
    directory = workspace.artifacts.joinpath(*namespace, "rendered", page_id, device.value.lower())
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{snapshot_id}.html"
    path.write_text(rendered_html, encoding="utf-8", newline="\n")
    return Path("artifacts", *namespace, "rendered", page_id, device.value.lower(), path.name).as_posix()


def _write_visual_artifact(
    workspace: AuditWorkspace,
    page_id: str,
    device: DeviceContext,
    snapshot_id: str,
    screenshot_png: bytes | None,
    *,
    namespace: tuple[str, ...] = (),
) -> str | None:
    if screenshot_png is None:
        return None
    if not screenshot_png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("renderer screenshot is not a PNG payload")
    directory = workspace.artifacts.joinpath(*namespace, "visual", page_id, device.value.lower())
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{snapshot_id}.png"
    path.write_bytes(screenshot_png)
    return Path("artifacts", *namespace, "visual", page_id, device.value.lower(), path.name).as_posix()


def _unexpected_failure(url: str, device: DeviceContext) -> BrowserRenderResult:
    return BrowserRenderResult(
        requested_url=url,
        final_url=None,
        http_status=None,
        content_type=None,
        rendered_html=None,
        browser_metadata={
            "engine": "renderer-adapter",
            "profile": {"device": device.value},
            "render_error": RenderErrorKind.RENDERER_ERROR.value,
        },
        error_kind=RenderErrorKind.RENDERER_ERROR,
    )
