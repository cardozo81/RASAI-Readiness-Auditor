"""#657 A: opt-in, bounded, non-authoritative local architecture preview ledger.

This store is deliberately outside AUD workspaces/SQLite. It holds no HTML,
resource URLs, headers, cookies, exception strings, or provider credentials.
Stored previews are never authoritative M6 classifications.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import uuid
from urllib.parse import urlsplit

from rasai.architecture_acquisition_preferences import _root, STATIC, DYNAMIC
from rasai.architecture_discovery import ArchitectureAssessment
from rasai.domain import DeviceContext
from rasai.url_utils import normalize_url

CONTRACT = "RASAI-ARCH-PREVIEW-657-A-v1"
MAX_RECORD_BYTES = 4096
MAX_RECORDS = 20
KEEP_DAYS = 30
_FILE = re.compile(r"^pv-[0-9a-f]{32}\.json$")
_CODE = re.compile(r"^[A-Z0-9_]{1,72}$")


def _canonical(url: str) -> str:
    normalized = normalize_url(url)
    split = urlsplit(normalized)
    host = split.hostname
    if (split.scheme not in ("http", "https") or not host
            or split.username is not None or split.password is not None
            or len(normalized) > 4096):
        raise ValueError("INVALID_PUBLIC_PREVIEW_SCOPE")
    if host.casefold() in {"localhost", "localhost.localdomain"} or host.casefold().endswith((".local", ".internal")):
        raise ValueError("INVALID_PUBLIC_PREVIEW_SCOPE")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass  # No DNS here. Actual public-IP validation belongs to the capture adapter.
    else:
        if not address.is_global:
            raise ValueError("INVALID_PUBLIC_PREVIEW_SCOPE")
    return normalized


def _origin(url: str) -> str:
    url = urlsplit(url)
    return f"{url.scheme}://{url.netloc.lower()}"


def _scope_hash(url: str) -> str:
    # The exact path/query is deliberately excluded from the readable ledger.
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _directory(root: Path | None = None, *, create: bool = False) -> Path:
    base = (root if root is not None else _root()).absolute()
    directory = base / ".rasai-runtime" / "architecture" / "previews"
    # Reject preexisting symlinks in every part we control (Windows junctions
    # are still subject to the local filesystem's ACLs).
    for component in (base, *list(directory.parents)[:-1][::-1], directory):
        if component.is_symlink():
            raise ValueError("PREVIEW_STORAGE_SYMLINK")
    if create:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.exists() and not directory.is_dir():
        raise ValueError("PREVIEW_STORAGE_NOT_DIRECTORY")
    return directory


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_reason(reason: object) -> str:
    value = str(reason or "NONE")
    return value if _CODE.fullmatch(value) else "NOT_VERIFIABLE"


def _payload(url: str, device: DeviceContext, mode: str, assessment: ArchitectureAssessment,
             *, observed_at: datetime) -> dict:
    canonical = _canonical(url)
    if device not in {DeviceContext.MOBILE, DeviceContext.DESKTOP} or mode not in {STATIC, DYNAMIC}:
        raise ValueError("INVALID_PREVIEW_MODE_OR_DEVICE")
    hypothesis = getattr(assessment, "hypothesis", None)
    shape = getattr(hypothesis, "structure", None) if hypothesis is not None else None
    shape = shape if shape and _CODE.fullmatch(str(shape)) else None
    class_name = assessment.architecture.value
    if not _CODE.fullmatch(class_name):
        raise ValueError("INVALID_ARCHITECTURE_CLASS")
    return {
        "contract": CONTRACT,
        "preview_id": "pv-" + uuid.uuid4().hex,
        "created_utc": observed_at.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "retention_days": KEEP_DAYS,
        "scope_sha256": _scope_hash(canonical),
        "requested_public_origin": _origin(canonical),
        # Assessment does not expose a verified final redirect URL. Abstain.
        "final_public_origin": None,
        "final_origin_status": "NOT_VERIFIED_FROM_ASSESSMENT",
        "device": device.value,
        "mode": mode,
        "method": _safe_reason(assessment.method_version.upper().replace("-", "_")),
        "architecture": class_name,
        "limitations": [_safe_reason(assessment.limitation)],
        "raw_observed": bool(assessment.raw_available),
        "rendered_observed": bool(assessment.rendered_available),
        "hypothesis_structure": shape,
        "hypothesis_confidence": "LOW" if shape else None,
        "status": "PRELIMINARY_UNVERIFIED",
        "audit_id": None,
        "audit_writes": 0,
        "provider_requests": 0,
    }


def save_preview(
    root: Path | None, url: str, device: DeviceContext, mode: str,
    assessment: ArchitectureAssessment, *, now: datetime | None = None,
) -> dict:
    """Explicitly called on user save; no capture or network side effects."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_PREVIEW_TIMESTAMP")
    value = _payload(url, device, mode, assessment, observed_at=now)
    value["record_sha256"] = hashlib.sha256(_json_bytes(value)).hexdigest()
    encoded = _json_bytes(value)
    if len(encoded) > MAX_RECORD_BYTES:
        raise ValueError("PREVIEW_RECORD_TOO_LARGE")
    directory = _directory(root, create=True)
    destination = directory / (value["preview_id"] + ".json")
    temporary = directory / ("." + value["preview_id"] + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        if destination.exists() or destination.is_symlink():
            raise ValueError("PREVIEW_RECORD_ALREADY_EXISTS")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    _prune(directory, now=now)
    return value


def _read(path: Path, *, now: datetime, include_expired: bool = False) -> dict | None:
    if not _FILE.fullmatch(path.name) or path.is_symlink() or not path.is_file():
        return None
    try:
        if not 0 < path.stat().st_size <= MAX_RECORD_BYTES:
            return None
        obj = json.loads(path.read_bytes())
        if not isinstance(obj, dict) or obj.get("contract") != CONTRACT:
            return None
        digest = obj.pop("record_sha256", None)
        if not isinstance(digest, str) or digest != hashlib.sha256(_json_bytes(obj)).hexdigest():
            return None
        if obj.get("preview_id") + ".json" != path.name or obj.get("status") != "PRELIMINARY_UNVERIFIED":
            return None
        if obj.get("audit_id") is not None or obj.get("audit_writes") != 0 or obj.get("provider_requests") != 0:
            return None
        if obj.get("device") not in {"MOBILE", "DESKTOP"} or obj.get("mode") not in {STATIC, DYNAMIC}:
            return None
        timestamp = datetime.fromisoformat(obj["created_utc"])
        if (timestamp.tzinfo is None or timestamp > now + timedelta(minutes=5)
                or (not include_expired and timestamp < now - timedelta(days=KEEP_DAYS))):
            return None
        if not re.fullmatch(r"[0-9a-f]{64}", str(obj.get("scope_sha256"))):
            return None
        obj["record_sha256"] = digest
        return obj
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def list_previews(root: Path | None, *, url: str, device: DeviceContext,
                  now: datetime | None = None) -> tuple[dict, ...]:
    """Read-only exact-scope lookup. A different URL/device never yields results."""
    canonical = _canonical(url)
    if device not in {DeviceContext.MOBILE, DeviceContext.DESKTOP}:
        raise ValueError("INVALID_PREVIEW_DEVICE")
    directory = _directory(root)
    if not directory.exists():
        return ()
    current = now or datetime.now(timezone.utc)
    key = _scope_hash(canonical)
    found = []
    for path in sorted(directory.iterdir(), key=lambda x: x.name)[:MAX_RECORDS * 4]:
        record = _read(path, now=current)
        if record and record.get("scope_sha256") == key and record.get("device") == device.value:
            found.append(record)
    return tuple(sorted(found, key=lambda x: x["created_utc"], reverse=True)[:MAX_RECORDS])


def _prune(directory: Path, *, now: datetime) -> None:
    """Retention applies only to our own strict filename/schema, never AUD data."""
    valid = []
    for path in directory.iterdir():
        if not _FILE.fullmatch(path.name) or path.is_symlink() or not path.is_file():
            continue
        record = _read(path, now=now, include_expired=True)
        if record is None:
            # Unknown or tampered content is never deleted by this retention pass.
            continue
        timestamp = datetime.fromisoformat(record["created_utc"])
        if timestamp < now - timedelta(days=KEEP_DAYS):
            path.unlink(missing_ok=True)
        else:
            valid.append((record["created_utc"], path))
    for _, path in sorted(valid, reverse=True)[MAX_RECORDS:]:
        path.unlink(missing_ok=True)
