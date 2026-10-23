"""Isolated architecture probe over validated, externally supplied captures.

The adapter deliberately cannot perform network I/O. Acquisition is an
explicit dependency so unsafe browser redirects and private DNS cannot be
introduced as an accidental fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from typing import Callable
from urllib.parse import urlsplit

from rasai.architecture_discovery import ArchitectureAssessment, assess_architecture
from rasai.architecture_resource_diagnostic import ResourcePreflightDiagnostic
from rasai.domain import DeviceContext
from rasai.search_intelligence.content import _validate_public_url, _default_resolver
from rasai.url_utils import normalize_url


@dataclass(frozen=True)
class CaptureOriginDigest:
    """Capture-time checksum, never a sealed AUD/manifest attestation."""
    transport: str
    requested_url: str
    final_url: str
    device: str
    raw_sha256: str | None
    rendered_sha256: str | None
    attested: bool = False
    redirect_chain: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProbeCaptures:
    requested_url: str
    final_url: str
    device: DeviceContext
    raw_html: str | None
    rendered_html: str | None
    quality_reason: str | None = None
    origin: CaptureOriginDigest | None = None
    redirect_chain: tuple[str, ...] = ()
    resource_diagnostic: ResourcePreflightDiagnostic | None = None


def with_capture_origin(capture: ProbeCaptures, *, transport: str) -> ProbeCaptures:
    """Bind the just-acquired bytes to the capture identity before analysis."""
    if transport not in {"PINNED_HTTP_STATIC", "ISOLATED_OCI_RENDER"}:
        raise ValueError("Unknown capture transport")
    if capture.origin is not None:
        raise ValueError("Capture origin cannot be replaced")
    def digest(value: str | None) -> str | None:
        return hashlib.sha256(value.encode("utf-8")).hexdigest() if value is not None else None
    origin = CaptureOriginDigest(
        transport=transport, requested_url=capture.requested_url,
        final_url=capture.final_url, device=capture.device.value,
        raw_sha256=digest(capture.raw_html),
        rendered_sha256=digest(capture.rendered_html),
        redirect_chain=capture.redirect_chain,
    )
    return ProbeCaptures(
        capture.requested_url, capture.final_url, capture.device,
        capture.raw_html, capture.rendered_html, capture.quality_reason,
        origin, capture.redirect_chain, capture.resource_diagnostic,
    )


def probe_architecture(
    url: str,
    device: DeviceContext,
    *,
    capture: Callable[[str, DeviceContext], ProbeCaptures],
) -> ArchitectureAssessment:
    """One canonical assessment; caller supplies a guarded acquisition transport."""
    if device not in {DeviceContext.MOBILE, DeviceContext.DESKTOP}:
        raise ValueError("Unsupported probe device")
    # Avoid DNS preflight before a transport-level fail-closed gate. The
    # guarded capture owns network validation for externally acquired data.
    target = normalize_url(url)
    observation = capture(target, device)
    if normalize_url(observation.requested_url) != target or observation.device != device:
        raise ValueError("Probe capture identity mismatch")
    # A capture-time digest must still match the bytes presented to the
    # assessor. An origin record without an independently sealed AUD manifest
    # is not an authenticity assertion and must never be promoted to one.
    if observation.origin is not None:
        origin = observation.origin
        if (origin.attested
                or origin.requested_url != observation.requested_url
                or origin.final_url != observation.final_url
                or origin.device != device.value
                or origin.redirect_chain != observation.redirect_chain
                or origin.raw_sha256 != (
                    hashlib.sha256(observation.raw_html.encode("utf-8")).hexdigest()
                    if observation.raw_html is not None else None)
                or origin.rendered_sha256 != (
                    hashlib.sha256(observation.rendered_html.encode("utf-8")).hexdigest()
                    if observation.rendered_html is not None else None)):
            raise ValueError("Capture origin digest mismatch")
    final_url = normalize_url(observation.final_url)
    if final_url != target:
        from rasai.architecture_public_html import verified_public_redirect_chain
        if (
            observation.origin is None
            or not verified_public_redirect_chain(
                target, final_url, observation.redirect_chain,
            )
        ):
            raise ValueError("Probe final URL differs from the validated target")
    # Reject injected captures claiming usable evidence without valid public
    # target provenance. Inconclusive captures may return safely without DNS.
    if (observation.quality_reason is None
            and observation.raw_html is not None
            and observation.rendered_html is not None):
        _validate_public_url(final_url, _default_resolver)
    assessment = assess_architecture(
        raw_html=observation.raw_html,
        rendered_html=observation.rendered_html,
        quality_reason=observation.quality_reason,
    )
    # Resource diagnostics explain acquisition limitations, not architecture.
    # A successful physical comparison has no failure diagnostic to report.
    if observation.quality_reason is not None and observation.resource_diagnostic is not None:
        assessment = replace(
            assessment, resource_diagnostic=observation.resource_diagnostic,
        )
    # The acquisition adapter owns this *reported* redirect metadata.
    # Capture-time SHA does not imply an independently signed audit manifest.
    # Present only bounded hop counts/protocols, not potentially secret URLs.
    if observation.origin is None:
        return assessment
    before = urlsplit(target)
    after = urlsplit(final_url)
    transition = (
        "HTTP_TO_HTTPS" if before.scheme == "http" and after.scheme == "https"
        else "UNCHANGED"
    )
    return replace(
        assessment,
        redirect_hops_reported=len(observation.redirect_chain),
        protocol_transition=transition,
        acquisition_transport=observation.origin.transport,
    )
