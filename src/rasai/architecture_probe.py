"""Isolated architecture probe over validated, externally supplied captures.

The adapter deliberately cannot perform network I/O. Acquisition is an
explicit dependency so unsafe browser redirects and private DNS cannot be
introduced as an accidental fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from rasai.architecture_discovery import ArchitectureAssessment, assess_architecture
from rasai.domain import DeviceContext
from rasai.search_intelligence.content import _validate_public_url, _default_resolver
from rasai.url_utils import normalize_url


@dataclass(frozen=True)
class ProbeCaptures:
    requested_url: str
    final_url: str
    device: DeviceContext
    raw_html: str | None
    rendered_html: str | None
    quality_reason: str | None = None


def probe_architecture(
    url: str,
    device: DeviceContext,
    *,
    capture: Callable[[str, DeviceContext], ProbeCaptures],
) -> ArchitectureAssessment:
    """One canonical assessment; caller supplies a guarded acquisition transport."""
    if device not in {DeviceContext.MOBILE, DeviceContext.DESKTOP}:
        raise ValueError("Unsupported probe device")
    target = _validate_public_url(normalize_url(url), _default_resolver)
    observation = capture(target, device)
    if observation.requested_url != target or observation.device != device:
        raise ValueError("Probe capture identity mismatch")
    final_url = _validate_public_url(observation.final_url, _default_resolver)
    if final_url != target:
        # No follow-through across a change of origin without a separate
        # audited redirect transport guarantee.
        raise ValueError("Probe final URL differs from the validated target")
    return assess_architecture(
        raw_html=observation.raw_html,
        rendered_html=observation.rendered_html,
        quality_reason=observation.quality_reason,
    )
