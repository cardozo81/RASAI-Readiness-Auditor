"""Bounded read-only resource bundle for an isolated COBS browser replay.

A bundle is operator-supplied local evidence, not a live network collection,
source attestation, provider identity, or consent to fetch anything.
"""
from __future__ import annotations

import base64
import binascii
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from rasai.url_utils import normalize_url

CONTRACT = "RASAI-COBS-ISOLATED-ASSET-BUNDLE-1"
MAX_FILE_BYTES = 3_200_000
MAX_ASSETS = 16
MAX_TOTAL_ASSET_BYTES = 2_000_000
_SHA = re.compile(r"^[0-9a-f]{64}$")
_MEDIA = frozenset({
    "application/javascript", "text/javascript", "text/css",
    "application/json", "image/png", "image/jpeg", "image/webp",
    "image/gif", "image/svg+xml", "font/woff", "font/woff2",
    "application/font-woff",
})


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError("duplicated offline asset JSON key")
        fields[key] = value
    return fields


def _reject_constant(_: str) -> None:
    raise ValueError("nonstandard offline asset JSON number")


def _origin(value: str) -> tuple[str, str, int]:
    if not isinstance(value, str) or not 0 < len(value) <= 2048:
        raise ValueError("offline asset URL invalid")
    try:
        parsed = urlsplit(value)
        if (normalize_url(value) != value or parsed.scheme not in ("http", "https")
                or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.fragment
                or parsed.port not in (None, 80, 443)):
            raise ValueError("offline asset URL is not canonical public HTTP(S)")
        return (parsed.scheme, parsed.hostname.casefold(),
                parsed.port or (443 if parsed.scheme == "https" else 80))
    except ValueError as exc:
        raise ValueError("offline asset URL is not canonical HTTP(S)") from exc


def load_offline_asset_bundle(path: Path, *, target_url: str) -> tuple[list[dict[str, str]], str]:
    """Load only same-origin bytes, validated physically and cryptographically.

    The digest is local integrity, not an external provider signature. No DNS,
    browser, file output, AUD mutation, or HTTP operation is performed.
    """
    expected_origin = _origin(target_url)
    file = Path(path)
    if (file.is_symlink() or file.parent.is_symlink() or not file.is_file()
            or any(part.startswith(("AUD-", "CONS-", "RPR-")) for part in file.parts)):
        raise ValueError("unsafe offline asset bundle file")
    before = file.stat()
    if not 0 < before.st_size <= MAX_FILE_BYTES:
        raise ValueError("offline asset bundle exceeds bounded size")
    with file.open("rb") as source:
        opened = os.fstat(source.fileno())
        raw = source.read(MAX_FILE_BYTES + 1)
    after = file.stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if os.name != "nt":
        fields += ("st_ctime_ns",)
    if (file.is_symlink() or len(raw) != before.st_size
            or any(getattr(before, k) != getattr(check, k)
                   for check in (opened, after) for k in fields)):
        raise ValueError("offline asset bundle changed during read")
    try:
        parsed = json.loads(raw, object_pairs_hook=_unique,
                            parse_constant=_reject_constant)
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("offline asset bundle JSON invalid") from None
    if (not isinstance(parsed, dict)
            or set(parsed) != {"contract_version", "target_url", "resources"}
            or parsed["contract_version"] != CONTRACT
            or parsed["target_url"] != target_url
            or not isinstance(parsed["resources"], list)
            or not 1 <= len(parsed["resources"]) <= MAX_ASSETS):
        raise ValueError("offline asset bundle identity/schema invalid")
    result: list[dict[str, str]] = []
    seen: set[str] = {target_url}
    total = 0
    for entry in parsed["resources"]:
        if not isinstance(entry, dict) or set(entry) != {
            "url", "content_type", "sha256", "body_b64",
        }:
            raise ValueError("offline asset entry schema invalid")
        url = entry["url"]
        if _origin(url) != expected_origin or url in seen:
            raise ValueError("offline assets must be unique and same-origin")
        seen.add(url)
        mime = entry["content_type"]
        if (not isinstance(mime, str) or len(mime) > 120
                or mime.split(";", 1)[0].strip().lower() not in _MEDIA
                or "\r" in mime or "\n" in mime):
            raise ValueError("offline asset MIME is not supported")
        encoded = entry["body_b64"]
        if not isinstance(encoded, str) or len(encoded) > 2_800_000:
            raise ValueError("offline asset encoding exceeds budget")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("offline asset base64 invalid") from None
        total += len(data)
        if not data or total > MAX_TOTAL_ASSET_BYTES:
            raise ValueError("offline asset aggregate bytes exceed budget")
        digest = entry["sha256"]
        if not isinstance(digest, str) or not _SHA.fullmatch(digest) or sha256(data).hexdigest() != digest:
            raise ValueError("offline asset content SHA-256 mismatch")
        result.append({
            "url": url, "content_type": mime, "body_b64": encoded,
            "sha256": digest,
        })
    return result, sha256(raw).hexdigest()


__all__ = ["load_offline_asset_bundle", "CONTRACT"]
