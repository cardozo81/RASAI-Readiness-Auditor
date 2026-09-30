"""RFC 6265 default-path rule used by both browser capture and passive security."""
from __future__ import annotations

from urllib.parse import urlsplit


def _default_cookie_path(page_url: str) -> str:
    try:
        path = urlsplit(page_url).path or "/"
    except ValueError:
        return "/"
    if not path.startswith("/") or path == "/":
        return "/"
    right = path.rfind("/")
    return "/" if right <= 0 else path[:right]
