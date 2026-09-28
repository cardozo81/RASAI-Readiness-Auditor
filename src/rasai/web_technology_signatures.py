"""Versioned, secret-safe signatures for web technologies observed by RASAi.

This module classifies only evidence already visible in the audited client/runtime.
It never performs network calls and never treats a vendor signature or JavaScript API
usage as proof of malicious behaviour. Identifier extraction is allowlist-based: values
that are not explicitly known to be public are not returned in clear text.
"""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Any
from urllib.parse import urlsplit

CONTRACT_VERSION = "WEB-TECH-SIGNATURES-001"

PUBLIC_IDENTIFIER = "PUBLIC_IDENTIFIER"
PUBLIC_OPERATIONAL_KEY = "PUBLIC_OPERATIONAL_KEY"
SECRET_OR_CREDENTIAL = "SECRET_OR_CREDENTIAL"
UNKNOWN_IDENTIFIER = "UNKNOWN_IDENTIFIER"

_MAX_SOURCE_SCAN_CHARS = 512 * 1024
_MAX_SIGNAL_COUNT = 50
_MAX_PLATFORM_COUNT = 20

_PLATFORM_HOSTS: tuple[tuple[str, str, str], ...] = (
    ("googletagmanager.com", "GOOGLE_TAG_MANAGER", "Google Tag Manager"),
    ("google-analytics.com", "GOOGLE_ANALYTICS", "Google Analytics"),
    ("doubleclick.net", "GOOGLE_ADS", "Google Ads / Floodlight"),
    ("clarity.ms", "MICROSOFT_CLARITY", "Microsoft Clarity"),
    ("connect.facebook.net", "META_PIXEL", "Meta Pixel"),
    ("facebook.com", "META_PIXEL", "Meta Pixel"),
    ("analytics.tiktok.com", "TIKTOK_PIXEL", "TikTok Pixel"),
    ("snap.licdn.com", "LINKEDIN_INSIGHT", "LinkedIn Insight Tag"),
    ("pinimg.com", "PINTEREST_TAG", "Pinterest Tag"),
    ("assets.adobedtm.com", "ADOBE_LAUNCH", "Adobe Launch"),
    ("omtrdc.net", "ADOBE_ANALYTICS", "Adobe Analytics"),
    ("cdn.segment.com", "SEGMENT", "Segment"),
    ("tiqcdn.com", "TEALIUM", "Tealium"),
    ("hotjar.com", "HOTJAR", "Hotjar"),
    ("matomo", "MATOMO", "Matomo"),
    ("hs-scripts.com", "HUBSPOT", "HubSpot"),
    ("sentry.io", "SENTRY", "Sentry"),
    ("js-agent.newrelic.com", "NEW_RELIC", "New Relic"),
    ("datadoghq.com", "DATADOG_RUM", "Datadog RUM"),
    ("cookielaw.org", "ONETRUST", "OneTrust"),
    ("onetrust.com", "ONETRUST", "OneTrust"),
    ("cookiebot.com", "COOKIEBOT", "Cookiebot"),
    ("didomi.io", "DIDOMI", "Didomi"),
    ("trustarc.com", "TRUSTARC", "TrustArc"),
)

_SOURCE_MARKERS: tuple[tuple[str, str, str], ...] = (
    ("googletagmanager", "GOOGLE_TAG_MANAGER", "Google Tag Manager"),
    ("gtag(", "GOOGLE_ANALYTICS", "Google Analytics"),
    ("google-analytics", "GOOGLE_ANALYTICS", "Google Analytics"),
    ("fbq(", "META_PIXEL", "Meta Pixel"),
    ("fbevents.js", "META_PIXEL", "Meta Pixel"),
    ("ttq.", "TIKTOK_PIXEL", "TikTok Pixel"),
    ("linkedin_partner_id", "LINKEDIN_INSIGHT", "LinkedIn Insight Tag"),
    ("pintrk(", "PINTEREST_TAG", "Pinterest Tag"),
    ("clarity(", "MICROSOFT_CLARITY", "Microsoft Clarity"),
    ("_paq", "MATOMO", "Matomo"),
    ("hotjar", "HOTJAR", "Hotjar"),
    ("analytics.load(", "SEGMENT", "Segment"),
    ("utag.", "TEALIUM", "Tealium"),
    ("sentry.init", "SENTRY", "Sentry"),
    ("datadogrum", "DATADOG_RUM", "Datadog RUM"),
)

_RISK_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("DYNAMIC_EVAL", "MEDIUM", re.compile(r"\beval\s*\(", re.I)),
    ("DYNAMIC_FUNCTION", "MEDIUM", re.compile(r"\bnew\s+Function\s*\(", re.I)),
    ("DOCUMENT_WRITE", "LOW", re.compile(r"\bdocument\.write\s*\(", re.I)),
    ("DYNAMIC_SCRIPT_INJECTION", "LOW", re.compile(r"createElement\s*\(\s*['\"]script['\"]", re.I)),
    ("COOKIE_API", "INFO", re.compile(r"\bdocument\.cookie\b|\bcookieStore\s*\.", re.I)),
    ("WEB_STORAGE", "INFO", re.compile(r"\b(?:localStorage|sessionStorage|indexedDB)\b", re.I)),
    ("WEBSOCKET", "INFO", re.compile(r"\bWebSocket\s*\(", re.I)),
    ("SERVICE_WORKER", "INFO", re.compile(r"serviceWorker\s*\.\s*register\s*\(", re.I)),
    ("WORKER", "INFO", re.compile(r"\b(?:new\s+Worker|SharedWorker)\s*\(", re.I)),
    ("GEOLOCATION", "INFO", re.compile(r"navigator\s*\.\s*geolocation\b", re.I)),
    ("CLIPBOARD", "INFO", re.compile(r"navigator\s*\.\s*clipboard\b", re.I)),
    ("DYNAMIC_IMPORT", "INFO", re.compile(r"\bimport\s*\(", re.I)),
    ("FINGERPRINTING_SURFACE", "LOW", re.compile(r"canvas|AudioContext|hardwareConcurrency|deviceMemory|getClientRects", re.I)),
)

_IDENTIFIER_PATTERNS: tuple[tuple[str, str, str, re.Pattern[str]], ...] = (
    ("GOOGLE_TAG_MANAGER", "GTM_CONTAINER_ID", PUBLIC_IDENTIFIER, re.compile(r"\bGTM-[A-Z0-9]{4,20}\b", re.I)),
    ("GOOGLE_ANALYTICS", "GA_MEASUREMENT_ID", PUBLIC_IDENTIFIER, re.compile(r"\bG-[A-Z0-9]{5,20}\b", re.I)),
    ("GOOGLE_ANALYTICS", "GA_LEGACY_PROPERTY_ID", PUBLIC_IDENTIFIER, re.compile(r"\bUA-\d{4,12}-\d+\b", re.I)),
    ("GOOGLE_ADS", "GOOGLE_ADS_ID", PUBLIC_IDENTIFIER, re.compile(r"\b(?:AW|DC)-\d{4,20}\b", re.I)),
    ("MICROSOFT_CLARITY", "CLARITY_PROJECT_ID", PUBLIC_IDENTIFIER, re.compile(r"clarity(?:\.ms)?/(?:tag/)?([a-z0-9]{6,20})", re.I)),
    ("META_PIXEL", "META_PIXEL_ID", PUBLIC_IDENTIFIER, re.compile(r"fbq\s*\(\s*['\"]init['\"]\s*,\s*['\"](\d{5,25})['\"]", re.I)),
    ("TIKTOK_PIXEL", "TIKTOK_PIXEL_ID", PUBLIC_IDENTIFIER, re.compile(r"ttq\s*\.\s*load\s*\(\s*['\"]([A-Z0-9]{8,30})['\"]", re.I)),
    ("LINKEDIN_INSIGHT", "LINKEDIN_PARTNER_ID", PUBLIC_IDENTIFIER, re.compile(r"linkedin_partner_id\s*=\s*['\"]?(\d{4,20})", re.I)),
    ("PINTEREST_TAG", "PINTEREST_TAG_ID", PUBLIC_IDENTIFIER, re.compile(r"pintrk\s*\(\s*['\"]load['\"]\s*,\s*['\"](\d{4,25})['\"]", re.I)),
    ("HOTJAR", "HOTJAR_SITE_ID", PUBLIC_IDENTIFIER, re.compile(r"hotjar-(\d{4,20})\.js|hjid\s*[:=]\s*(\d{4,20})", re.I)),
    ("HUBSPOT", "HUBSPOT_PORTAL_ID", PUBLIC_IDENTIFIER, re.compile(r"hs-scripts\.com/(\d{4,20})\.js", re.I)),
    ("SEGMENT", "SEGMENT_WRITE_KEY", PUBLIC_OPERATIONAL_KEY, re.compile(r"analytics\.load\s*\(\s*['\"]([A-Za-z0-9_-]{8,80})['\"]", re.I)),
)


def _hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]


def _masked(value: str) -> str:
    if len(value) <= 6:
        return "[MASKED]"
    return value[:3] + "…" + value[-3:]


def _identifier(
    *,
    platform_id: str,
    identifier_type: str,
    identifier_class: str,
    value: str,
) -> dict[str, Any]:
    normalized = str(value or "").strip()
    if identifier_class == PUBLIC_IDENTIFIER:
        display = normalized
    else:
        display = _masked(normalized)
    return {
        "platform_id": platform_id,
        "identifier_type": identifier_type,
        "identifier_class": identifier_class,
        "identifier_display": display,
        "identifier_hash": _hash(normalized),
    }


def _host_platforms(url: str | None) -> list[dict[str, str]]:
    raw = str(url or "").strip()
    if not raw:
        return []
    try:
        host = (urlsplit(raw).hostname or "").casefold()
    except ValueError:
        host = ""
    lowered = raw.casefold()
    found: list[dict[str, str]] = []
    for marker, platform_id, name in _PLATFORM_HOSTS:
        marker_cf = marker.casefold()
        if marker_cf in host or (not host and marker_cf in lowered):
            found.append({"platform_id": platform_id, "platform_name": name, "detection_method": "HOST"})
    return found


def detect_platforms(url: str | None = None, source: str | None = None) -> list[dict[str, Any]]:
    """Return bounded vendor/platform observations without exposing unknown tokens."""
    source_text = str(source or "")[:_MAX_SOURCE_SCAN_CHARS]
    haystack = (str(url or "") + "\n" + source_text).casefold()
    platforms: dict[str, dict[str, Any]] = {}
    for item in _host_platforms(url):
        platforms[item["platform_id"]] = {
            **item,
            "confidence": "HIGH",
            "identifiers": [],
        }
    for marker, platform_id, name in _SOURCE_MARKERS:
        if marker.casefold() in haystack:
            existing = platforms.setdefault(platform_id, {
                "platform_id": platform_id,
                "platform_name": name,
                "detection_method": "SOURCE_SIGNATURE",
                "confidence": "MEDIUM",
                "identifiers": [],
            })
            if existing.get("confidence") != "HIGH":
                existing["confidence"] = "MEDIUM"

    combined = str(url or "") + "\n" + source_text
    for platform_id, identifier_type, identifier_class, pattern in _IDENTIFIER_PATTERNS:
        if platform_id not in platforms:
            continue
        for match in pattern.finditer(combined):
            groups = [group for group in match.groups() if group] if match.groups() else []
            value = groups[0] if groups else match.group(0)
            identifier = _identifier(
                platform_id=platform_id,
                identifier_type=identifier_type,
                identifier_class=identifier_class,
                value=value,
            )
            if identifier not in platforms[platform_id]["identifiers"]:
                platforms[platform_id]["identifiers"].append(identifier)
            if len(platforms[platform_id]["identifiers"]) >= 8:
                break

    return list(platforms.values())[:_MAX_PLATFORM_COUNT]


def analyze_script_source(source: str | bytes | None) -> list[dict[str, Any]]:
    """Return bounded indicators of risk/relevant APIs; never returns source snippets."""
    if source is None:
        return []
    if isinstance(source, bytes):
        text = source[:_MAX_SOURCE_SCAN_CHARS].decode("utf-8", errors="ignore")
    else:
        text = str(source)[:_MAX_SOURCE_SCAN_CHARS]
    signals: list[dict[str, Any]] = []
    for signal_id, relevance, pattern in _RISK_PATTERNS:
        count = len(pattern.findall(text))
        if count:
            signals.append({
                "signal_id": signal_id,
                "risk_relevance": relevance,
                "count": min(count, 999),
                "confidence": "HIGH",
                "basis": "STATIC_SOURCE_PATTERN",
            })
        if len(signals) >= _MAX_SIGNAL_COUNT:
            break
    return signals
