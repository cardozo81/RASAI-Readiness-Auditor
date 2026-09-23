"""Opaque raw-evidence storage for SERP observations."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Protocol

from rasai.secret_safety import redact_text, redact_value


@dataclass(frozen=True, slots=True)
class StoredEvidence:
    reference: str
    sha256: str


class SerpEvidenceSink(Protocol):
    def store(self, observation_id: str, payload: bytes, content_type: str) -> StoredEvidence: ...


def sanitize_raw_evidence(payload: bytes, content_type: str) -> bytes:
    """Sanitize provider evidence before persistence without changing opaque binary data.

    JSON receives structured recursive redaction. Any other UTF-8 textual payload is
    scrubbed as text. Truly opaque binary payloads are left byte-identical because
    decoding/re-encoding them would corrupt evidence; providers used by the SERP
    contract are expected to return JSON/text and are covered by the safe paths.
    """

    if "json" in content_type.casefold():
        try:
            parsed = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        else:
            return json.dumps(
                redact_value(parsed), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload
    return redact_text(text).encode("utf-8")


class FilesystemSerpEvidenceSink:
    def __init__(self, workspace_root: Path, artifacts_root: Path) -> None:
        self._workspace_root = workspace_root
        self._artifacts_root = artifacts_root

    def store(self, observation_id: str, payload: bytes, content_type: str) -> StoredEvidence:
        safe_payload = sanitize_raw_evidence(payload, content_type)
        safe_component = observation_id
        if not safe_component or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for ch in safe_component) or safe_component in {".", ".."}:
            safe_component = "obs-" + hashlib.sha256(observation_id.encode("utf-8", errors="replace")).hexdigest()[:24]
        directory = self._artifacts_root / "serp" / safe_component
        directory.mkdir(parents=True, exist_ok=True)
        suffix = ".json" if "json" in content_type.casefold() else ".bin"
        path = directory / f"raw{suffix}"
        path.write_bytes(safe_payload)
        digest = hashlib.sha256(safe_payload).hexdigest()
        try:
            reference = path.relative_to(self._workspace_root).as_posix()
        except ValueError:
            reference = path.as_posix()
        return StoredEvidence(reference=reference, sha256=digest)
