"""M3 execution glue: browser rendering and independent device snapshots."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Protocol

from searchgeo.browser_identity_renderer import BrowserIdentityRenderer
from searchgeo.device_context import runtime_devices
from searchgeo.domain import DeviceContext, Evidence, EvidenceType, PageSnapshot, new_id, utc_now
from searchgeo.m14_persistence import ElementObservation, M14Persistence
from searchgeo.m2 import M2ExecutionResult
from searchgeo.persistence import AuditPersistence, AuditWorkspace
from searchgeo.rendering import (
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


def execute_m3(
    m2_result: M2ExecutionResult,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
    *,
    renderer: Renderer | None = None,
) -> M3ExecutionResult:
    """Render every M2 page for the configured device context and persist snapshots.

    ``SEARCHGEO_DEVICE_CONTEXT`` accepts ``mobile``, ``desktop`` or ``both``.
    When M3 is called directly without that environment variable, the legacy
    internal behavior remains both devices. The CLI always resolves an explicit
    context and defaults it to mobile.

    The default renderer uses a browser identity aligned to the actual Playwright
    browser version. This avoids stale User-Agent/browser-version combinations that
    can trigger divergent CDN/WAF redirect policies while keeping the context
    stateless and TLS validation enabled.
    """

    active_renderer: Renderer = renderer or BrowserIdentityRenderer()
    renderer_context = active_renderer if isinstance(active_renderer, BrowserRenderer) else nullcontext(active_renderer)
    snapshot_ids: dict[str, dict[DeviceContext, str]] = {}
    visual_artifact_refs: dict[str, dict[DeviceContext, str | None]] = {}
    failures: list[RenderFailure] = []
    devices = runtime_devices()

    with M14Persistence(workspace) as m14, renderer_context as session_renderer:
        for discovered in m2_result.discovery.pages:
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
            for device in devices:
                preflight_navigation_trace = [
                    {
                        "url": hop.source_url,
                        "status": hop.status,
                        "location": hop.location,
                    }
                    for hop in acquisition.redirects
                ]
                try:
                    if isinstance(session_renderer, BrowserIdentityRenderer):
                        render_result = session_renderer.render(
                            url,
                            device,
                            preflight_navigation_trace=preflight_navigation_trace,
                        )
                    else:
                        render_result = session_renderer.render(url, device)
                except Exception:
                    render_result = _unexpected_failure(url, device)

                snapshot_id = new_id("SNP")
                captured_at = utc_now()
                rendered_artifact_ref = _write_rendered_artifact(
                    workspace,
                    page_id,
                    device,
                    snapshot_id,
                    render_result.rendered_html,
                )
                visual_artifact_ref = _write_visual_artifact(
                    workspace,
                    page_id,
                    device,
                    snapshot_id,
                    render_result.screenshot_png,
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
                }
                browser_metadata["render_succeeded"] = render_result.succeeded
                browser_metadata["visual_artifact_ref"] = visual_artifact_ref
                browser_metadata["audit_device_context"] = [item.value for item in devices]

                snapshot = PageSnapshot(
                    snapshot_id=snapshot_id,
                    page_id=page_id,
                    device=device,
                    requested_url=url,
                    final_url=render_result.final_url or acquisition.final_url,
                    captured_at=captured_at,
                    http_status=(
                        render_result.http_status
                        if render_result.http_status is not None
                        else acquisition.status
                    ),
                    content_type=(
                        render_result.content_type
                        or acquisition.header("Content-Type")
                    ),
                    rendering_mode=_RENDERING_MODE,
                    raw_artifact_ref=raw_artifact_ref,
                    rendered_artifact_ref=rendered_artifact_ref,
                    browser_metadata=browser_metadata,
                )
                persistence.snapshots.add(snapshot)
                per_device[device] = snapshot.snapshot_id
                per_device_visual[device] = visual_artifact_ref

                if visual_artifact_ref is not None:
                    viewport = (
                        browser_metadata.get("profile", {}).get("viewport", {})
                        if isinstance(browser_metadata.get("profile"), dict)
                        else {}
                    )
                    persistence.evidence.add(
                        Evidence(
                            evidence_id=new_id("EV-GEO"),
                            audit_id=page.audit_id,
                            page_id=page_id,
                            snapshot_id=snapshot_id,
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
                            captured_at=captured_at,
                        )
                    )

                observations = _align_title_observation_to_rendered_artifact(render_result)
                for observed in observations:
                    observation_artifact_ref = (
                        rendered_artifact_ref
                        if observed.tag_name.casefold() == "title" and rendered_artifact_ref is not None
                        else visual_artifact_ref
                    )
                    m14.add_element_observation(
                        ElementObservation(
                            element_observation_id=new_id("ELM"),
                            audit_id=page.audit_id,
                            page_id=page_id,
                            snapshot_id=snapshot_id,
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
                            captured_at=captured_at,
                        )
                    )

                if render_result.error_kind is not None:
                    failures.append(
                        RenderFailure(
                            page_id=page_id,
                            device=device,
                            error_kind=render_result.error_kind.value,
                        )
                    )
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
    """Bind title evidence to the serialized DOM consumed by M4/M7.

    Chromium pages may mutate document.title after ``page.content()`` is
    captured but before the live observation pass runs. In that case a later
    live ``<title>`` must not be linked as exact evidence for a semantic result
    computed from the earlier persisted DOM. Other live observations remain
    unchanged because this hotfix only resolves the demonstrated title race.
    """

    if render_result.rendered_html is None:
        return render_result.element_observations

    non_title = tuple(
        observation
        for observation in render_result.element_observations
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
) -> str | None:
    if rendered_html is None:
        return None
    directory = workspace.artifacts / "rendered" / page_id / device.value.lower()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{snapshot_id}.html"
    path.write_text(rendered_html, encoding="utf-8", newline="\n")
    return Path("artifacts", "rendered", page_id, device.value.lower(), path.name).as_posix()


def _write_visual_artifact(
    workspace: AuditWorkspace,
    page_id: str,
    device: DeviceContext,
    snapshot_id: str,
    screenshot_png: bytes | None,
) -> str | None:
    if screenshot_png is None:
        return None
    if not screenshot_png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("renderer screenshot is not a PNG payload")
    directory = workspace.artifacts / "visual" / page_id / device.value.lower()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{snapshot_id}.png"
    path.write_bytes(screenshot_png)
    return Path("artifacts", "visual", page_id, device.value.lower(), path.name).as_posix()


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
