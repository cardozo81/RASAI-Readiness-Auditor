"""Dynatrace reference values used by Synthetic User Experience Apdex.

These values are intentionally limited to settings that can be mapped without
claiming RUM equivalence. Dynatrace's current web KPM documentation states that
Visually Complete is the default KPM for load/XHR actions, while its classic
WebApplicationConfig model exposes 3s/12s load thresholds and 3s/12s fallback
thresholds. The RASAi runtime cannot calculate Dynatrace Visually Complete with
vendor-equivalent semantics, so its default executable KPM is the documented
fallback metric: User action duration.
"""
from __future__ import annotations

DYNATRACE_REFERENCE_PROFILE = "DYNATRACE_WEB_LOAD_REFERENCE_2026"
DYNATRACE_LOAD_PRIMARY_KPM = "VISUALLY_COMPLETE"
DYNATRACE_LOAD_FALLBACK_KPM = "USER_ACTION_DURATION"
DYNATRACE_LOAD_SATISFIED_SECONDS = 3.0
DYNATRACE_LOAD_FRUSTRATED_SECONDS = 12.0
DYNATRACE_LOAD_FALLBACK_SATISFIED_SECONDS = 3.0
DYNATRACE_LOAD_FALLBACK_FRUSTRATED_SECONDS = 12.0

# RASAi executable baseline. This is deliberately the Dynatrace fallback KPM,
# not a synthetic reimplementation presented as Visually Complete.
RASAI_DYNATRACE_COMPAT_KPM = DYNATRACE_LOAD_FALLBACK_KPM
RASAI_DYNATRACE_COMPAT_SATISFIED_SECONDS = DYNATRACE_LOAD_FALLBACK_SATISFIED_SECONDS
RASAI_DYNATRACE_COMPAT_FRUSTRATED_SECONDS = DYNATRACE_LOAD_FALLBACK_FRUSTRATED_SECONDS

DYNATRACE_REFERENCE_URLS = (
    "https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-rum-web-key-performance-metric-load-actions",
    "https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/analyze-and-use/work-with-key-performance-metrics",
    "https://docs.dynatrace.com/docs/dynatrace-api/configuration-api/rum/web-application-configuration-api/web-application/post-web-application",
    "https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/rum-concepts/scores-and-ratings/apdex-ratings",
)


def dynatrace_reference_contract() -> dict[str, object]:
    return {
        "profile": DYNATRACE_REFERENCE_PROFILE,
        "load_primary_kpm": DYNATRACE_LOAD_PRIMARY_KPM,
        "load_primary_satisfied_seconds": DYNATRACE_LOAD_SATISFIED_SECONDS,
        "load_primary_frustrated_seconds": DYNATRACE_LOAD_FRUSTRATED_SECONDS,
        "load_fallback_kpm": DYNATRACE_LOAD_FALLBACK_KPM,
        "load_fallback_satisfied_seconds": DYNATRACE_LOAD_FALLBACK_SATISFIED_SECONDS,
        "load_fallback_frustrated_seconds": DYNATRACE_LOAD_FALLBACK_FRUSTRATED_SECONDS,
        "rasai_executable_kpm": RASAI_DYNATRACE_COMPAT_KPM,
        "rasai_executable_satisfied_seconds": RASAI_DYNATRACE_COMPAT_SATISFIED_SECONDS,
        "rasai_executable_frustrated_seconds": RASAI_DYNATRACE_COMPAT_FRUSTRATED_SECONDS,
        "visually_complete_vendor_equivalent": False,
    }
