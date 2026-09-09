"""Opaque raw-evidence storage for SERP observations."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol

_SENSITIVE_TOKENS = ("api_key", "apikey", "token", "secret", "password", "authorization", "credential")


@dataclass(frozen=True, slots=True)
class StoredEvidence:
    reference: str
    sha256: str


class SerpEvidenceSink(Protocol):
    def store(self, observation_id: str, payload: bytes, content_type: str) -> StoredEvidence: ...


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).casefold().replace("-", "_")
            if any(token in lowered for token in _SENSITIVE_TOKENS):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = _redact(item)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def sanitize_raw_evidence(payload: bytes, content_type: str) -> bytes:
    if "json" not in content_type.casefold():
        return payload
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return payload
    return json.dumps(
        _redact(parsed), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


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
