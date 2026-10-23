"""Shared resource ceilings for the optional networkless architecture preview.

Host acquisition and OCI worker import the same constants. The worker runs from
a locally rebuilt image of this source; the host never weakens transport or
container isolation in response to a budget failure.
"""
from __future__ import annotations

MAX_ASSETS = 64  # Additional unique resources, excluding the HTML document.
MAX_ROOT_BYTES = 1_000_000
MAX_ASSET_BYTES = 500_000
MAX_ENTRIES = MAX_ASSETS + 1
MAX_RESOURCE_BYTES = MAX_ROOT_BYTES + MAX_ASSETS * MAX_ASSET_BYTES
MAX_BUNDLE_BYTES = 52_000_000  # JSON/base64 plus bounded URL/header overhead.
MAX_MANIFEST_BYTES = MAX_BUNDLE_BYTES
MAX_BROWSER_REQUESTS = MAX_ENTRIES + 5  # Preserve limited retry/duplicate headroom.
