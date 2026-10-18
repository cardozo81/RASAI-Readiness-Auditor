"""Canonical opt-in architecture acquisition entrypoint for console and audit adapters.

Does not mutate a sealed AUD or any catalog. Optional capability errors abstain
without propagating failure to independent consumers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from rasai.architecture_acquisition_preferences import STATIC, DYNAMIC, SKIP
from rasai.architecture_discovery import ArchitectureAssessment, assess_architecture
from rasai.architecture_probe import probe_architecture, ProbeCaptures
from rasai.domain import DeviceContext


@dataclass(frozen=True)
class DiscoveryExecution:
    executed: bool
    mode: str
    assessment: ArchitectureAssessment
    reason: str | None = None


def run_optional_discovery(
    url: str,
    device: DeviceContext,
    *,
    mode: str,
    consent: Callable[[str], bool],
    static_capture: Callable[[str, DeviceContext], ProbeCaptures] | None = None,
    dynamic_capture: Callable[[str, DeviceContext], ProbeCaptures] | None = None,
    prepare: Callable[..., object] | None = None,
    probe: Callable[..., ArchitectureAssessment] | None = None,
) -> DiscoveryExecution:
    """Run only the requested optional capability; refuse unsafe fallback.

    The returned assessment is consultative. No score, collector selection,
    database or IA task is modified. Callers may safely omit this result.
    """
    probe_runner = probe or probe_architecture
    if mode not in {STATIC, DYNAMIC, SKIP}:
        raise ValueError("Unsupported architecture acquisition mode")
    if mode == SKIP:
        return DiscoveryExecution(False, mode, assess_architecture(
            raw_html=None, rendered_html=None,
            quality_reason="DISCOVERY_DECLINED",
        ), "DISCOVERY_DECLINED")
    if mode == STATIC:
        if static_capture is None:
            from rasai.architecture_static_capture import capture_static_public_architecture
            static_capture = capture_static_public_architecture
        try:
            assessment = probe_runner(url, device, capture=static_capture)
        except (OSError, RuntimeError):
            return DiscoveryExecution(False, mode, assess_architecture(
                raw_html=None, rendered_html=None,
                quality_reason="OPTIONAL_DISCOVERY_UNAVAILABLE",
            ), "OPTIONAL_DISCOVERY_UNAVAILABLE")
        return DiscoveryExecution(True, mode, assessment, assessment.limitation)
    if prepare is None:
        from rasai.runtime_prerequisites import prepare_prerequisite
        prepare = prepare_prerequisite
    from rasai.runtime_prerequisites import ARCHITECTURE_BROWSER
    readiness = prepare(ARCHITECTURE_BROWSER, consent=consent)
    if not readiness.ready:
        code = readiness.reason
        return DiscoveryExecution(False, mode, assess_architecture(
            raw_html=None, rendered_html=None, quality_reason=code,
        ), code)
    if dynamic_capture is None:
        from rasai.architecture_isolated_capture import capture_isolated_public_architecture
        dynamic_capture = capture_isolated_public_architecture
    try:
        assessment = probe_runner(url, device, capture=dynamic_capture)
    except (OSError, RuntimeError):
        return DiscoveryExecution(False, mode, assess_architecture(
            raw_html=None, rendered_html=None,
            quality_reason="OPTIONAL_DISCOVERY_UNAVAILABLE",
        ), "OPTIONAL_DISCOVERY_UNAVAILABLE")
    return DiscoveryExecution(True, mode, assessment, assessment.limitation)
