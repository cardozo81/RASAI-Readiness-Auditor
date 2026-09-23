"""Provider-independent hostname normalization and domain matching."""
from __future__ import annotations

from urllib.parse import urlsplit


def canonical_hostname(value: str, *, strip_www: bool = True) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("domain must not be empty")
    candidate = raw if "://" in raw else f"//{raw}"
    parsed = urlsplit(candidate, scheme="https") if "://" in raw else urlsplit(candidate)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("domain must not contain credentials")
    host = parsed.hostname
    if host is None:
        raise ValueError(f"invalid domain/URL: {value!r}")
    try:
        normalized = host.rstrip(".").encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise ValueError(f"invalid internationalized hostname: {value!r}") from exc
    if strip_www and normalized.startswith("www."):
        normalized = normalized[4:]
    if not normalized:
        raise ValueError(f"invalid domain/URL: {value!r}")
    return normalized


def domain_from_result_url(url: str) -> str | None:
    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme.casefold() not in {"http", "https"}:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        if parsed.hostname is None:
            return None
        return canonical_hostname(parsed.hostname)
    except (TypeError, ValueError, UnicodeError):
        return None


def domain_matches(candidate: str, domain_of_interest: str) -> bool:
    """Match a result host to the configured customer domain.

    The root domain matches its subdomains, while a configured subdomain does not
    implicitly claim the parent domain. ``www`` is treated as a presentation alias.
    """
    result = canonical_hostname(candidate)
    interest = canonical_hostname(domain_of_interest)
    return result == interest or result.endswith("." + interest)
