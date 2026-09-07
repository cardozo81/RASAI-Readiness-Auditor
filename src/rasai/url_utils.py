"""URL normalization and scope helpers for M2 discovery."""

from __future__ import annotations

import ipaddress
import posixpath
from urllib.parse import urljoin, urlsplit, urlunsplit


class InvalidUrl(ValueError):
    """Raised when a URL cannot participate in M2 HTTP discovery."""


def normalize_url(value: str, *, base_url: str | None = None) -> str:
    """Normalize one HTTP(S) URL without changing query semantics.

    Normalization is deliberately conservative: scheme/host casing and default
    ports are canonicalized, fragments are removed, empty paths become ``/``
    and dot-segments are collapsed. Query ordering and values are preserved.
    """

    raw = value.strip()
    if not raw or any(character.isspace() for character in raw):
        raise InvalidUrl("URL must be non-empty and contain no whitespace")

    if base_url is not None:
        raw = urljoin(base_url, raw)
    elif "://" not in raw:
        raw = f"https://{raw}"

    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise InvalidUrl("URL scheme must be http or https")
    if parsed.username is not None or parsed.password is not None:
        raise InvalidUrl("URL must not contain user credentials")
    if parsed.hostname is None:
        raise InvalidUrl("URL must contain a hostname")

    try:
        port = parsed.port
    except ValueError as exc:
        raise InvalidUrl("URL contains an invalid port") from exc

    hostname = parsed.hostname.rstrip(".")
    if not hostname:
        raise InvalidUrl("URL must contain a hostname")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            host = hostname.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise InvalidUrl("URL contains an invalid internationalized hostname") from exc
    else:
        host = f"[{address.compressed}]" if address.version == 6 else address.compressed

    if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    else:
        netloc = host

    path = parsed.path or "/"
    trailing_slash = path.endswith("/")
    normalized_path = posixpath.normpath(path)
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    if normalized_path == "//":
        normalized_path = "/"
    if trailing_slash and normalized_path != "/":
        normalized_path += "/"

    return urlunsplit((scheme, netloc, normalized_path, parsed.query, ""))


def normalized_origin(value: str) -> str:
    """Return normalized ``scheme://host[:port]`` for an HTTP(S) URL."""

    normalized = normalize_url(value)
    parsed = urlsplit(normalized)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def is_same_origin(value: str, origin: str) -> bool:
    """Return whether *value* belongs to the exact normalized audit origin."""

    try:
        return normalized_origin(value) == normalized_origin(origin)
    except InvalidUrl:
        return False


def resolve_http_url(base_url: str, reference: str) -> str | None:
    """Resolve and normalize a link, returning ``None`` for unsupported URLs."""

    candidate = reference.strip()
    if not candidate or candidate.startswith("#"):
        return None
    try:
        return normalize_url(candidate, base_url=base_url)
    except (InvalidUrl, ValueError):
        return None
