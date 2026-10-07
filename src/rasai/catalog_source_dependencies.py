"""Track external source files actually consulted by catalog-report materialization."""
from __future__ import annotations

from contextvars import ContextVar
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence


class SourceDependencyCapture:
    """Record stable identities for external files that affect one report projection."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._records: dict[str, dict[str, Any]] = {}

    def observe(self, path: Path) -> None:
        record = _snapshot_dependency(self.root, path)
        if record is None:
            return
        key = str(record["path"])
        previous = self._records.get(key)
        if previous is not None and previous != record:
            raise RuntimeError(
                f"catalog source dependency changed during materialization: {key}"
            )
        self._records[key] = record

    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(self._records[key]) for key in sorted(self._records))


_ACTIVE_CAPTURE: ContextVar[SourceDependencyCapture | None] = ContextVar(
    "rasai_catalog_source_dependency_capture",
    default=None,
)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_dependency(root: Path, path: Path) -> dict[str, Any] | None:
    root = root.resolve()
    try:
        candidate = path.resolve(strict=False)
        relative = candidate.relative_to(root)
    except (OSError, ValueError):
        return None
    relative_text = relative.as_posix()
    try:
        if not candidate.is_file():
            return {"path": relative_text, "state": "MISSING"}
        size = candidate.stat().st_size
        return {
            "path": relative_text,
            "state": "PRESENT",
            "size_bytes": int(size),
            "sha256": _sha256_file(candidate),
        }
    except OSError as exc:
        raise RuntimeError(
            f"catalog source dependency could not be fingerprinted: {relative_text}"
        ) from exc


def begin_source_dependency_capture(root: Path):
    """Start dependency capture for the current report materialization context."""

    return _ACTIVE_CAPTURE.set(SourceDependencyCapture(Path(root)))


def end_source_dependency_capture(token: Any) -> None:
    _ACTIVE_CAPTURE.reset(token)


def record_source_dependency(path: Path) -> None:
    """Record a file presence/content decision when report output depends on it."""

    capture = _ACTIVE_CAPTURE.get()
    if capture is not None:
        capture.observe(Path(path))


def captured_source_dependencies() -> tuple[dict[str, Any], ...]:
    capture = _ACTIVE_CAPTURE.get()
    return capture.records() if capture is not None else ()


def verify_source_dependencies(
    root: Path,
    records: Sequence[Mapping[str, Any]] | None,
) -> tuple[bool, tuple[str, ...]]:
    """Revalidate dependency records without trusting their paths or hashes."""

    if records is None:
        return False, ("source_dependencies ausente no manifest",)
    if not isinstance(records, (list, tuple)):
        return False, ("source_dependencies inválido no manifest",)

    root = Path(root).resolve()
    errors: list[str] = []
    seen: set[str] = set()
    for raw in records:
        if not isinstance(raw, Mapping):
            errors.append("registro de source_dependency inválido")
            continue
        relative = str(raw.get("path") or "").strip().replace("\\", "/")
        if not relative or relative in seen:
            errors.append(f"source_dependency path inválido/duplicado: {relative or '-'}")
            continue
        seen.add(relative)
        candidate = root / relative
        current = _snapshot_dependency(root, candidate)
        if current is None:
            errors.append(f"source_dependency fora do workspace: {relative}")
            continue
        expected = dict(raw)
        if expected.get("state") == "MISSING":
            expected = {"path": relative, "state": "MISSING"}
        elif expected.get("state") == "PRESENT":
            expected = {
                "path": relative,
                "state": "PRESENT",
                "size_bytes": expected.get("size_bytes"),
                "sha256": str(expected.get("sha256") or ""),
            }
        else:
            errors.append(f"source_dependency state inválido: {relative}")
            continue
        if current != expected:
            errors.append(f"source_dependency divergente: {relative}")
    return not errors, tuple(errors)


__all__ = [
    "begin_source_dependency_capture",
    "captured_source_dependencies",
    "end_source_dependency_capture",
    "record_source_dependency",
    "verify_source_dependencies",
]
