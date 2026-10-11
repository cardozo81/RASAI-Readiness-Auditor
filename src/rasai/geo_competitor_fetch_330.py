"""#330: explicit-consent public HTML inspection with per-URL robots gate.

This is a separate optional local adapter. It neither replaces the existing
Search Intelligence collector nor updates an AUD, score, GEO or CONS snapshot.
No network request is made before the caller opts in and names exact hosts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Sequence
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from rasai.search_intelligence.content import (
    ContentFetchStatus, PublicWebFetcher, PublicWebBlocked,
    _validate_public_url, extract_page_features,
)
from rasai.url_utils import InvalidUrl


_USER_AGENT = "RASAI-Search-Intelligence/0.1"
_MAX_ROBOTS_BYTES = 64_000


def inspect_consented_public_html(
    url: str, *, query: str, role: str,
    consented_hostnames: Sequence[str],
    fetcher: PublicWebFetcher | None = None,
) -> dict[str, Any]:
    """Read robots first and return bounded HTML features, without persisting.

    Robots 404/error/redirect/malformed/oversized or disallow abstains. This
    conservative policy is stricter than general-purpose crawler conventions.
    A no-redirect transport prevents fetching unapproved redirect destinations.
    """
    if role not in {"CUSTOMER", "COMPETITOR_CANDIDATE"}:
        raise ValueError("invalid competitive content role")
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise ValueError("single nonempty query required")
    if isinstance(consented_hostnames, (str, bytes)) or not consented_hostnames:
        raise ValueError("explicit exact-host consent required")
    if (len(consented_hostnames) > 10
            or any(not isinstance(host, str) or not host
                   or host != host.strip() or "*" in host or "/" in host
                   or ":" in host for host in consented_hostnames)):
        raise ValueError("invalid exact-host consent")
    allowed = {host.lower() for host in consented_hostnames}
    base = {
        "contract_version": "RASAI-COMPETITOR-ROBOTS-LOCAL-001",
        "role": role, "requested_url": url,
        "robots_fetch_status": "NOT_READ",
        "http_status": None, "final_url": None,
        "content_evidence_status": "NOT_COMPARABLE",
        "content_sha256": None, "word_count": None,
        "query_body_terms": None, "title": None,
        "meta_description": None, "headings": [],
        "jsonld_types": [], "html_fetch_timestamp": None,
        "html_rendering": "STATIC_HTTP_ONLY_NO_JS",
        "primary_content_proven": False,
        "provider_requests": 0, "audit_writes": 0,
        "score_changed": False, "limitations": (
            "Coleta opt-in somente local; robots.txt verificado por URL. "
            "HTML estático, sem JavaScript; render SPA, dispositivo, locale, "
            "mercado ou relação causal com ranking não comprovados. "
            "O cliente HTTP faz preflight de DNS, mas não oferece proteção "
            "egress contra DNS rebinding em SaaS."
        ),
    }
    client = fetcher or PublicWebFetcher(
        max_redirects=0, max_bytes=2_000_000, user_agent=_USER_AGENT,
    )
    if not isinstance(client, PublicWebFetcher) or client.max_redirects != 0:
        raise ValueError("no-redirect PublicWebFetcher required")
    if client.max_bytes > 2_000_000 or client.timeout_seconds > 10:
        raise ValueError("fetch byte/time limits exceed local inspection budget")
    if client.user_agent != _USER_AGENT:
        raise ValueError("robots user-agent must match HTML client")
    starting_requests = client.requests_used

    def outcome(status: str, **details: Any) -> dict[str, Any]:
        return {
            **base, "status": status,
            "provider_requests": client.requests_used - starting_requests,
            **details,
        }
    # Consent must be checked *before DNS preflight* (even DNS is network).
    try:
        host = urlsplit(url).hostname
    except (TypeError, ValueError):
        return outcome("UNSAFE_PUBLIC_URL")
    if host is None or host.lower() not in allowed:
        return outcome("EXACT_HOST_CONSENT_MISSING")
    try:
        normalized = _validate_public_url(url, client.resolver)
    except (InvalidUrl, PublicWebBlocked, ValueError, OSError):
        return outcome("UNSAFE_PUBLIC_URL")

    uri = urlsplit(normalized)
    robots_url = f"{uri.scheme}://{uri.netloc}/robots.txt"
    robots = client.fetch(robots_url)
    if (robots.status is not ContentFetchStatus.OBSERVED
            or robots.http_status != 200
            or robots.final_url != robots_url
            or not robots.body or len(robots.body) > _MAX_ROBOTS_BYTES):
        return outcome("ROBOTS_UNAVAILABLE_OR_NOT_VERIFIED",
                       robots_fetch_status="NOT_VERIFIED")
    media = (robots.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if media != "text/plain":
        return outcome("ROBOTS_NOT_PLAIN_TEXT",
                       robots_fetch_status="NOT_VERIFIED")
    try:
        policy = robots.body.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return outcome("ROBOTS_INVALID_ENCODING",
                       robots_fetch_status="NOT_VERIFIED")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(policy.splitlines())
    # Python 3.13.16+ RFC 9309 robotparser stores agents in "groups",
    # while earlier Python implementations expose default_entry/entries.
    # Requiring a matching group prevents can_fetch() from accepting an
    # unrelated robots policy merely because the agent was unspecified.
    current_groups = getattr(parser, "groups", {})
    agent_name = _USER_AGENT.split("/", 1)[0].lower()
    current_match = (
        isinstance(current_groups, dict)
        and any(
            isinstance(key, str)
            and (key == "*" or agent_name.startswith(key.lower()))
            for key in current_groups
        )
    )
    legacy_match = (
        parser.default_entry is not None
        or any(entry.applies_to(_USER_AGENT) for entry in parser.entries)
    )
    if not (current_match or legacy_match):
        return outcome("ROBOTS_NO_APPLICABLE_USER_AGENT",
                       robots_fetch_status="NOT_VERIFIED")
    if not parser.can_fetch(_USER_AGENT, normalized):
        return outcome("ROBOTS_DISALLOWED", robots_fetch_status="DISALLOWED")

    observed_at = datetime.now(timezone.utc).isoformat()
    fetched = client.fetch(normalized)
    valid_html = (
        fetched.status is ContentFetchStatus.OBSERVED
        and fetched.http_status == 200
        and fetched.final_url == normalized
        and (fetched.headers.get("content-type") or "").split(";", 1)[0]
        .strip().lower() in {"text/html", "application/xhtml+xml"}
    )
    if not valid_html:
        return outcome("HTML_NOT_OBSERVED", robots_fetch_status="ALLOWED",
                       html_fetch_timestamp=observed_at,
                       http_status=fetched.http_status, final_url=fetched.final_url)
    facts = extract_page_features(
        fetched, role=role, domain=host, query=query,
    )
    # Even a successful HTTP 200 can be a navigation shell, not primary text.
    status = (
        "STATIC_HTML_FEATURES_OBSERVED"
        if facts.word_count > 0 and facts.query_terms_in_body
        else "STATIC_HTML_WITHOUT_QUERY_BODY_EVIDENCE"
    )
    return outcome(
        status, robots_fetch_status="ALLOWED",
        content_evidence_status=(
            "TRANSIENT_STATIC_HTML_FEATURES" if status == "STATIC_HTML_FEATURES_OBSERVED"
            else "NOT_COMPARABLE"
        ),
        http_status=fetched.http_status, final_url=fetched.final_url,
        html_fetch_timestamp=observed_at,
        content_sha256=facts.content_sha256,
        word_count=facts.word_count,
        query_body_terms=list(facts.query_terms_in_body),
        title=facts.title, meta_description=facts.meta_description,
        headings=list(facts.headings), jsonld_types=list(facts.jsonld_types),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Standalone local consented robots-gated HTML inspector (#330)."
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--role", choices=("CUSTOMER", "COMPETITOR_CANDIDATE"),
                        required=True)
    parser.add_argument("--consent-host", action="append", required=True)
    parser.add_argument("--allow-public-html-requests", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_public_html_requests:
        parser.error("explicit --allow-public-html-requests is required")
    try:
        result = inspect_consented_public_html(
            args.url, query=args.query, role=args.role,
            consented_hostnames=args.consent_host,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
