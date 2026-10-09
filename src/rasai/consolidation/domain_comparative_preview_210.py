"""#210: proof-only same-domain comparative design outside productive CONS.

This module never changes strict same-URL longitudinal selection. A same-domain
pair with different paths is not a time-series of a single page and authorizes
no score, Apdex, CWV, extraction or AI trend calculations. It is an isolated,
fully deterministic design gate over candidates the existing analytical index
has already made available. No SQLite writes, network, providers or RPR.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import ipaddress
import json
from typing import Sequence
from urllib.parse import urlsplit

from .selection import AuditCandidate


def _identity(url: str) -> tuple[str, str] | None:
    """Return exact host and URL-universe identity, not a registrable-domain guess."""
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url.strip())
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        hostname = parsed.hostname.rstrip(".").lower().encode("idna").decode("ascii")
        # Public Suffix List is not proved in this contract; only the exact
        # hostname qualifies. Do not silently equate example.co.uk and co.uk,
        # www.example.org and example.org or unrelated sibling subdomains.
        if "." not in hostname or any(not part for part in hostname.split(".")):
            return None
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            return None
        port = parsed.port
        if port is not None and port < 1:
            return None
        standard = 80 if parsed.scheme.lower() == "http" else 443
        authority = hostname + (":" + str(port) if port and port != standard else "")
        normalized = (
            parsed.scheme.lower() + "://" + authority
            + (parsed.path or "/")
            + ("?" + parsed.query if parsed.query else "")
        )
        return hostname, normalized
    except (UnicodeError, ValueError):
        return None


def _instant(raw: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return value.astimezone(timezone.utc) if value.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def preview_same_domain_candidates(
    candidates: Sequence[AuditCandidate],
) -> dict:
    """Return only a methodologically gated comparison *preview*, never CONS."""
    base = {
        "contract_version": "RASAI-CONS-DOMAIN-COMPARATIVE-ADVISORY-001",
        "comparison_mode": "SAME_DOMAIN_COMPARATIVE",
        "production_cons_mode_changed": False,
        "page_level_trends_eligible": False,
        "audit_score_deltas_eligible": False,
        "apdex_or_cwv_deltas_eligible": False,
        "provider_requests": 0,
        "audit_writes": 0,
    }
    def abstain(reason: str) -> dict:
        return {
            **base, "eligible": False, "reason": reason,
            "hostname": None, "device": None, "audits": [],
            "url_universe_count": None,
        }
    if not 2 <= len(candidates) <= 100:
        return abstain("AUDIT_COUNT_OUT_OF_RANGE")
    if any(not isinstance(x, AuditCandidate) for x in candidates):
        return abstain("INVALID_CANDIDATE")
    if any(
        not all(
            isinstance(getattr(x, name), str)
            for name in ("audit_id", "url", "device", "status", "event_time")
        ) or (
            x.completion_status is not None
            and not isinstance(x.completion_status, str)
        )
        for x in candidates
    ):
        return abstain("INVALID_CANDIDATE")
    ids = [x.audit_id for x in candidates]
    if any(not x or not x.startswith("AUD-") for x in ids) or len(set(ids)) != len(ids):
        return abstain("INVALID_OR_DUPLICATE_AUD_ID")
    if any(
        x.status.strip().upper() not in {"COMPLETED", "SUCCESS", "SUCCESS_WITH_LIMITATIONS"}
        or (x.completion_status or "").strip().upper() != "COMPLETE"
        for x in candidates
    ):
        return abstain("AUD_NOT_LOGICALLY_COMPLETE")
    identities = [_identity(x.url) for x in candidates]
    if any(x is None for x in identities):
        return abstain("UNVERIFIABLE_SINGLE_URL")
    hosts = {x[0] for x in identities if x}
    if len(hosts) != 1:
        return abstain("DIFFERENT_HOSTNAMES")
    devices = {x.device.strip().upper() for x in candidates if x.device.strip()}
    if len(devices) != 1 or any(not x.device.strip() for x in candidates):
        return abstain("INCOMPATIBLE_DEVICE")
    unique_urls = {x[1] for x in identities if x}
    if len(unique_urls) == 1:
        return abstain("SAME_URL_USE_STRICT_LONGITUDINAL_MODE")
    clocks = [_instant(x.event_time) for x in candidates]
    if any(t is None for t in clocks) or len(set(clocks)) != len(clocks):
        return abstain("UNVERIFIABLE_OBSERVATION_CHRONOLOGY")
    prepared = []
    for candidate, identity, instant in zip(candidates, identities, clocks):
        assert identity is not None and instant is not None
        encoded = json.dumps([identity[1]], ensure_ascii=False, separators=(",", ":"))
        prepared.append({
            "audit_id": candidate.audit_id,
            "url": identity[1],
            "device": candidate.device.strip().upper(),
            "observed_at_utc": instant.isoformat(),
            "url_universe_fingerprint": sha256(encoded.encode("utf-8")).hexdigest(),
            "page_metrics_comparison": "N/D",
            "score_delta": None,
        })
    prepared.sort(key=lambda x: (x["observed_at_utc"], x["audit_id"]))
    return {
        **base, "eligible": True, "reason": None,
        "hostname": next(iter(hosts)),
        "device": next(iter(devices)),
        "audits": prepared,
        "url_universe_count": len(unique_urls),
        "interpretation": (
            "Different URLs of one exact hostname: independent page observations, "
            "not before/after of one URL. Any future audit-level aggregation "
            "requires explicit universe and configuration equivalence gates; "
            "all page-level trends, score deltas and Apdex/CWV deltas remain N/D."
        ),
    }
