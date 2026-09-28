"""Dynatrace reference values used by Synthetic User Experience Apdex.

These values are intentionally limited to settings that can be mapped without
claiming RUM equivalence. The Dynatrace RUM WebApplicationConfig baseline uses
Visually Complete for Load Actions with 3s/12s thresholds and User Action
Duration fallback thresholds of 3s/12s. Its XHR Action baseline is separate:
Action Duration with 2.5s/10s and 3s/12s fallback. Dynatrace Synthetic Browser
Monitor settings are a different contract and are not used here as RUM defaults.
The RASAi runtime cannot calculate Dynatrace Visually Complete with
vendor-equivalent semantics, so its default executable Load KPM is the explicit
fallback metric: User Action Duration.
"""
from __future__ import annotations

DYNATRACE_REFERENCE_PROFILE = "DYNATRACE_WEB_LOAD_REFERENCE_2026"
DYNATRACE_LOAD_PRIMARY_KPM = "VISUALLY_COMPLETE"
DYNATRACE_LOAD_FALLBACK_KPM = "USER_ACTION_DURATION"
DYNATRACE_LOAD_SATISFIED_SECONDS = 3.0
DYNATRACE_LOAD_FRUSTRATED_SECONDS = 12.0
DYNATRACE_LOAD_FALLBACK_SATISFIED_SECONDS = 3.0
DYNATRACE_LOAD_FALLBACK_FRUSTRATED_SECONDS = 12.0

# Default WebApplicationConfig contract exposed by Dynatrace for XHR actions.
DYNATRACE_XHR_PRIMARY_KPM = "ACTION_DURATION"
DYNATRACE_XHR_SATISFIED_SECONDS = 2.5
DYNATRACE_XHR_FRUSTRATED_SECONDS = 10.0
DYNATRACE_XHR_FALLBACK_SATISFIED_SECONDS = 3.0
DYNATRACE_XHR_FALLBACK_FRUSTRATED_SECONDS = 12.0

# Default error-impact posture documented by Dynatrace RUM.
# Generic console.error capture is not enabled by default in RUM; RASAi still
# observes it diagnostically, but does not make it Apdex-impacting by default.
DYNATRACE_JAVASCRIPT_ERRORS_AFFECT_APDEX = True
DYNATRACE_REQUEST_ERRORS_AFFECT_APDEX = True
DYNATRACE_CONSOLE_ERRORS_AFFECT_APDEX = False
DYNATRACE_REQUEST_ERROR_SCOPE = "all"

# RUM WebApplicationConfig capture defaults that M25 can reproduce directly.
DYNATRACE_JAVASCRIPT_ERROR_CAPTURE = True
DYNATRACE_XHR_CAPTURE = True
DYNATRACE_FETCH_CAPTURE = True
DYNATRACE_CONSOLE_ERROR_CAPTURE = False
DYNATRACE_MAX_ERRORS_TO_CAPTURE = 10

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
    "https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/additional-configuration/configure-errors",
    "https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/initial-setup/configure-dynatrace-real-user-monitoring-to-capture-xhr-actions",
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
        "xhr_primary_kpm": DYNATRACE_XHR_PRIMARY_KPM,
        "xhr_satisfied_seconds": DYNATRACE_XHR_SATISFIED_SECONDS,
        "xhr_frustrated_seconds": DYNATRACE_XHR_FRUSTRATED_SECONDS,
        "xhr_fallback_satisfied_seconds": DYNATRACE_XHR_FALLBACK_SATISFIED_SECONDS,
        "xhr_fallback_frustrated_seconds": DYNATRACE_XHR_FALLBACK_FRUSTRATED_SECONDS,
        "javascript_errors_affect_apdex": DYNATRACE_JAVASCRIPT_ERRORS_AFFECT_APDEX,
        "request_errors_affect_apdex": DYNATRACE_REQUEST_ERRORS_AFFECT_APDEX,
        "console_errors_affect_apdex": DYNATRACE_CONSOLE_ERRORS_AFFECT_APDEX,
        "request_error_scope": DYNATRACE_REQUEST_ERROR_SCOPE,
        "javascript_error_capture": DYNATRACE_JAVASCRIPT_ERROR_CAPTURE,
        "xhr_capture": DYNATRACE_XHR_CAPTURE,
        "fetch_capture": DYNATRACE_FETCH_CAPTURE,
        "console_error_capture": DYNATRACE_CONSOLE_ERROR_CAPTURE,
        "max_errors_to_capture": DYNATRACE_MAX_ERRORS_TO_CAPTURE,
        "rasai_executable_kpm": RASAI_DYNATRACE_COMPAT_KPM,
        "rasai_executable_satisfied_seconds": RASAI_DYNATRACE_COMPAT_SATISFIED_SECONDS,
        "rasai_executable_frustrated_seconds": RASAI_DYNATRACE_COMPAT_FRUSTRATED_SECONDS,
        "visually_complete_vendor_equivalent": False,
    }
