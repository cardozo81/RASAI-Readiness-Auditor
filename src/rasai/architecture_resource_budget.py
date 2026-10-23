"""Shared resource ceilings for the optional networkless architecture preview.

Host acquisition and OCI worker import the same constants. The worker runs from
a locally rebuilt image of this source; the host never weakens transport or
container isolation in response to a budget failure.
"""
from __future__ import annotations

MAX_ASSETS = 64  # Additional unique resources, excluding the HTML document.
MAX_ROOT_BYTES = 1_000_000
MAX_ASSET_BYTES = 500_000  # Default limit for small/static assets.
MAX_STYLESHEET_BYTES = 2_000_000  # Layout may determine DOM visibility.
MAX_SCRIPT_BYTES = 4_000_000  # Bundled JavaScript is common in large web apps.

# Strict response MIME checks, independent of URL or file extension.
# Larger scripts are eligible only when *both* the HTML declares executable
# JavaScript AND the server responds with one of these JavaScript media types.
JAVASCRIPT_MIME_TYPES = frozenset({
    "text/javascript", "application/javascript",
    "text/ecmascript", "application/ecmascript", "application/x-javascript",
})
RESOURCE_KINDS = frozenset({
    "document", "script", "stylesheet", "image", "iframe",
    "source", "preload", "modulepreload", "icon", "unknown",
})


def normalized_mime(content_type: str) -> str:
    if not isinstance(content_type, str):
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def resource_byte_limit(kind: str, content_type: str) -> int:
    """Fail closed on misleading MIME/role combinations.

    This pure policy is shared by host and OCI worker. No network or I/O.
    MIME matching does not authenticate the actual bytes or classify the page.
    """
    mime = normalized_mime(content_type)
    if kind == "stylesheet" and mime == "text/css":
        return MAX_STYLESHEET_BYTES
    if kind in {"script", "modulepreload"} and mime in JAVASCRIPT_MIME_TYPES:
        return MAX_SCRIPT_BYTES
    return MAX_ASSET_BYTES

MAX_ENTRIES = MAX_ASSETS + 1
# Independent aggregate ceiling: larger CSS/JS assets consume the existing total
# budget rather than silently expanding the worker's memory/manifest surface.
MAX_RESOURCE_BYTES = MAX_ROOT_BYTES + MAX_ASSETS * MAX_ASSET_BYTES
MAX_BUNDLE_BYTES = 52_000_000  # JSON/base64 plus bounded URL/header overhead.
MAX_MANIFEST_BYTES = MAX_BUNDLE_BYTES
MAX_BROWSER_REQUESTS = MAX_ENTRIES + 5  # Preserve limited retry/duplicate headroom.
