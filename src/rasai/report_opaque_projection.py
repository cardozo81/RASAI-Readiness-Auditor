"""Read-only omission of opaque provider payloads in distributed reports.

The original AI exchange and its hashes stay in audit.db. These functions only
project an opaque field into metadata; they never decode, inspect or publish its
bytes. The secret detector must still inspect all other visible content.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any, Mapping

OPAQUE_STATUS = "ENCRYPTED_CONTENT_OMITTED"
UNPARSEABLE_STATUS = "[OPAQUE_EXCHANGE_PAYLOAD_OMITTED_INVALID_JSON]"
_OPAQUE_MARKER = re.compile(r"encrypted[_-]?content", re.IGNORECASE)


def opaque_metadata(value: Any) -> dict[str, Any]:
    """Non-reversible integrity reference for ciphertext omitted from output."""
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
    return {
        "status": OPAQUE_STATUS,
        "size_bytes": len(raw),
        "sha256": sha256(raw).hexdigest(),
    }


def has_opaque_marker(value: str) -> bool:
    return bool(_OPAQUE_MARKER.search(value))


def project_opaque_fields(value: Any) -> Any:
    """Omit encrypted_content recursively, including JSON encoded in text fields.

    Preserve the exact persisted string if there is no opaque field. An invalid
    serialized payload mentioning the opaque field is withheld as a whole: it
    cannot be safely edited field-by-field.
    """
    projected, _changed = _project(value)
    return projected


def _project(value: Any) -> tuple[Any, bool]:
    if isinstance(value, Mapping):
        changed = False
        output = {}
        for key, item in value.items():
            if str(key).casefold() == "encrypted_content":
                output[key] = opaque_metadata(item)
                changed = True
            else:
                output[key], edited = _project(item)
                changed |= edited
        return output, changed
    if isinstance(value, (list, tuple)):
        items = [_project(item) for item in value]
        return [item for item, _ in items], any(edited for _, edited in items)
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped.startswith(("{", "[")):
            try:
                decoded = json.loads(value)
            except (ValueError, TypeError):
                return (UNPARSEABLE_STATUS, True) if has_opaque_marker(value) else (value, False)
            projected, changed = _project(decoded)
            if changed:
                return json.dumps(projected, ensure_ascii=False, separators=(",", ":")), True
        if has_opaque_marker(value):
            # No parseable structured boundary: never distribute a suspected
            # ciphertext payload in unstructured/free-form response text.
            return UNPARSEABLE_STATUS, True
    return value, False
