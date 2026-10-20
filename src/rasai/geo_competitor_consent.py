"""Local, revocable, purpose-scoped consent register for optional COBS (#330).

Explicit grants never authorize an HTTP request by themselves. Each request
still requires the opt-in flag, exact host, role, purpose and both GET scopes.
The hash chain detects accidental/tactical edits that do not recompute hashes;
it is NOT a signature and does not authenticate the consent grantor.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Sequence

_SCHEMA = "RASAI-COBS-LOCAL-CONSENT-1"
_PURPOSE = {
    "CUSTOMER": "AUD_CUSTOMER_STATIC_CONTENT_REVIEW",
    "COMPETITOR_CANDIDATE": "GEO_COMPETITOR_STATIC_CONTENT_REVIEW",
}
_OPERATIONS = ("GET_ROBOTS_TXT", "GET_STATIC_HTML")
_HOST = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAX_BYTES = 256 * 1024
_MAX_EVENTS = 512


def _encode(obj: object) -> bytes:
    return json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _clock(value: object) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 40:
        raise ValueError("invalid local consent timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid local consent timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("consent clock must be UTC")
    return parsed


def _scope(hostname: str, role: str, purpose: str) -> tuple[str, str, str]:
    if (
        not isinstance(hostname, str) or hostname != hostname.strip()
        or hostname != hostname.lower() or not _HOST.fullmatch(hostname)
        or ".." in hostname or hostname.startswith(".") or hostname.endswith(".")
        or not isinstance(role, str) or _PURPOSE.get(role) != purpose
    ):
        raise ValueError("invalid exact-host, role or purpose for local consent")
    return hostname, role, purpose


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate local consent JSON key")
        out[key] = value
    return out


def _no_constants(_: str) -> None:
    raise ValueError("invalid constant in local consent JSON")


def _safe_path(path: Path) -> Path:
    path = Path(path)
    if (not path.name or path.name in {".", ".."}
            or path.is_symlink() or path.parent.is_symlink()
            or not path.parent.is_dir()):
        raise ValueError("unsafe local consent registry path")
    if any(part.startswith(("AUD-", "RPR-", "CONS-"))
           for part in path.parts):
        raise ValueError("consent registry must remain outside sealed packages")
    return path


def _read(path: Path, *, allow_new: bool = False) -> list[dict[str, Any]]:
    path = _safe_path(path)
    if not path.exists():
        if allow_new:
            return []
        raise ValueError("local consent registry not found")
    if not path.is_file() or path.stat().st_size > _MAX_BYTES:
        raise ValueError("invalid local consent registry")
    before = path.stat()
    with path.open("rb") as fd:
        physical = os.fstat(fd.fileno())
        raw = fd.read(_MAX_BYTES + 1)
    after = path.stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if os.name != "nt":
        fields += ("st_ctime_ns",)
    if (
        path.is_symlink() or len(raw) > _MAX_BYTES
        or len(raw) != before.st_size
        or any(getattr(before, name) != getattr(snapshot, name)
               for snapshot in (physical, after) for name in fields)
    ):
        raise ValueError("local consent registry changed during read")
    try:
        decoded = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_keys,
            parse_constant=_no_constants,
        )
    except (UnicodeError, ValueError) as exc:
        raise ValueError("local consent registry encoding/structure invalid") from exc
    if (not isinstance(decoded, dict) or set(decoded) != {"schema", "events"}
            or decoded["schema"] != _SCHEMA
            or not isinstance(decoded["events"], list)
            or len(decoded["events"]) > _MAX_EVENTS):
        raise ValueError("invalid local consent schema")
    previous = "0" * 64
    result = []
    for position, event in enumerate(decoded["events"], 1):
        if not isinstance(event, dict) or set(event) != {
            "sequence", "action", "hostname", "role", "purpose",
            "operations", "recorded_at", "expires_at",
            "previous_sha256", "event_sha256",
        }:
            raise ValueError("invalid local consent event structure")
        _scope(event["hostname"], event["role"], event["purpose"])
        if (
            type(event["sequence"]) is not int or event["sequence"] != position
            or event["action"] not in {"GRANT", "REVOKE"}
            or event["operations"] != list(_OPERATIONS)
            or event["previous_sha256"] != previous
        ):
            raise ValueError("local consent event chain mismatch")
        recorded = _clock(event["recorded_at"])
        if event["action"] == "GRANT":
            expires = _clock(event["expires_at"])
            if not recorded < expires <= recorded + timedelta(days=90):
                raise ValueError("local consent expiry out of bounds")
        elif event["expires_at"] is not None:
            raise ValueError("revocation cannot carry expiry")
        body = {key: value for key, value in event.items()
                if key != "event_sha256"}
        expected = sha256(_encode(body)).hexdigest()
        if event["event_sha256"] != expected:
            raise ValueError("local consent event digest mismatch")
        previous = expected
        result.append(event)
    return result


def check_local_consent(
    registry: Path, *, hostname: str, role: str, purpose: str,
) -> str | None:
    """Return active grant's event digest, or abstain without DNS/HTTP."""
    key = _scope(hostname, role, purpose)
    events = _read(Path(registry))
    matching = [
        row for row in events
        if (row["hostname"], row["role"], row["purpose"]) == key
    ]
    if not matching:
        return None
    newest = matching[-1]
    if (newest["action"] != "GRANT"
            or _clock(newest["expires_at"]) <= datetime.now(timezone.utc)):
        return None
    return newest["event_sha256"]


def record_local_consent(
    registry: Path, *, hostname: str, role: str, purpose: str,
    action: str, expires_at: str | None = None, confirmed: bool = False,
) -> str:
    """Explicit local operator operation, atomic and serialized by lock file.

    This is a local ledger, not a server-enforced SaaS revocation system.
    """
    _scope(hostname, role, purpose)
    if not confirmed or action not in {"GRANT", "REVOKE"}:
        raise ValueError("explicit GRANT/REVOKE confirmation required")
    path = _safe_path(Path(registry))
    now = datetime.now(timezone.utc)
    if action == "GRANT":
        expires = _clock(expires_at)
        if not now < expires <= now + timedelta(days=90):
            raise ValueError("local consent expiry must be within the next 90 days")
        until = expires.isoformat()
    else:
        if expires_at is not None:
            raise ValueError("revocation must not have an expiry")
        until = None
    lock = path.with_name(path.name + ".lock")
    if lock.is_symlink():
        raise ValueError("unsafe consent registry lock")
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError as exc:
        raise ValueError("consent registry busy or lock unavailable") from exc
    temp: Path | None = None
    try:
        os.close(lock_fd)
        events = _read(path, allow_new=True)
        if len(events) >= _MAX_EVENTS:
            raise ValueError("local consent registry event limit reached")
        event = {
            "sequence": len(events) + 1, "action": action,
            "hostname": hostname, "role": role, "purpose": purpose,
            "operations": list(_OPERATIONS),
            "recorded_at": now.isoformat(), "expires_at": until,
            "previous_sha256": (
                events[-1]["event_sha256"] if events else "0" * 64
            ),
        }
        event["event_sha256"] = sha256(_encode(event)).hexdigest()
        payload = _encode({"schema": _SCHEMA, "events": [*events, event]})
        if len(payload) > _MAX_BYTES:
            raise ValueError("local consent registry exceeds size budget")
        fd, name = tempfile.mkstemp(prefix=".cobs-consent-", dir=path.parent)
        temp = Path(name)
        try:
            with os.fdopen(fd, "wb") as target:
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
            if path.is_symlink():
                raise ValueError("consent destination changed to symlink")
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()
        return event["event_sha256"]
    finally:
        lock.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline local COBS consent grant/revoke; does not request a URL."
    )
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--role", required=True, choices=tuple(_PURPOSE))
    parser.add_argument("--purpose", required=True, choices=tuple(_PURPOSE.values()))
    parser.add_argument("--action", required=True, choices=("GRANT", "REVOKE", "CHECK"))
    parser.add_argument("--expires-at", help="UTC expiry for GRANT, <= 90 days")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "CHECK":
            receipt = check_local_consent(
                args.registry, hostname=args.host, role=args.role,
                purpose=args.purpose,
            )
            status = "GRANTED_LOCALLY" if receipt else "NOT_AUTHORIZED"
        else:
            receipt = record_local_consent(
                args.registry, hostname=args.host, role=args.role,
                purpose=args.purpose, action=args.action,
                expires_at=args.expires_at, confirmed=args.confirm,
            )
            status = "LOCAL_GRANT_RECORDED" if args.action == "GRANT" else "LOCAL_REVOKE_RECORDED"
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "status": status, "event_sha256": receipt,
        "provider_requests": 0, "external_authority_attested": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
