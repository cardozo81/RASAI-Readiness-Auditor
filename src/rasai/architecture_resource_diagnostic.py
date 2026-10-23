"""Safe, bounded reasons for an isolated architecture resource preflight failure.

No URL, hostname, response body, exception string, cookie or credential is
stored. This diagnostic is in-memory advisory metadata, never AUD evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

RESOURCE_KINDS = frozenset({
    "script", "stylesheet", "image", "iframe", "source",
    "preload", "modulepreload", "icon", "unknown",
})
RESOURCE_PHASES = frozenset({"inventory", "pre_fetch", "fetch"})


@dataclass(frozen=True, slots=True)
class ResourcePreflightDiagnostic:
    kind: str
    phase: str
    ordinal: int | None = None
    candidates: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in RESOURCE_KINDS or self.phase not in RESOURCE_PHASES:
            raise ValueError("Unexpected resource diagnostic category")
        if self.ordinal is not None and (
            type(self.ordinal) is not int or not 1 <= self.ordinal <= 64
        ):
            raise ValueError("Invalid resource diagnostic ordinal")
        if self.candidates is not None and (
            type(self.candidates) is not int or not 0 <= self.candidates <= 64
        ):
            raise ValueError("Invalid resource diagnostic candidate count")
        if self.ordinal is not None and self.candidates is not None and self.ordinal > self.candidates:
            raise ValueError("Resource ordinal exceeds candidate inventory")
