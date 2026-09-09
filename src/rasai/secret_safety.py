"""Central secret classification, redaction and repository leak detection.

The module is intentionally provider-neutral. Secrets may be consumed from environment
variables or a future secret manager, but their values must never become product
configuration, reports, manifests, logs, exceptions or versioned repository content.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


REDACTED = "[REDACTED]"
PRIVATE_KEY_REDACTED = "[REDACTED_PRIVATE_KEY]"

_SENSITIVE_NAME_TOKENS = (
    "API_KEY",
    "APIKEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "PRIVATE_KEY",
    "ACCESS_KEY",
    "AUTHORIZATION",
    "COOKIE",
)
_SECRET_REFERENCE_SUFFIXES = (
    "_ENV",
    "_REF",
    "_SECRET_REF",
    "_CREDENTIAL_REF",
)
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_URI_WITH_AUTH_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/@:]+:[^\s/@]+@[^\s]+")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+([^\s,;]+)")
_HEADER_RE = re.compile(
    r"(?im)^(\s*(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key|api-key)\s*:\s*)(.+)$"
)
_SENSITIVE_FIELD_PATTERN = (
    r"[A-Za-z0-9_.-]*(?:api[_-]?key|token|secret|password|passwd|credential|"
    r"private[_-]?key|access[_-]?key)[A-Za-z0-9_.-]*"
)
_QUOTED_ASSIGNMENT_RE = re.compile(
    rf"(?im)\b({_SENSITIVE_FIELD_PATTERN})\b\s*[:=]\s*([\"'])([^\"'\n]+)\2"
)
_ENV_ASSIGNMENT_RE = re.compile(
    rf"(?im)^\s*({_SENSITIVE_FIELD_PATTERN})\s*=\s*([^\s#]+)\s*$"
)
_PRIVATE_KEY_BEGIN = "-----BEGIN " + "PRIVATE KEY-----"
_PRIVATE_KEY_END = "-----END " + "PRIVATE KEY-----"
_PRIVATE_KEY_BLOCK_RE = re.compile(
    re.escape(_PRIVATE_KEY_BEGIN) + r".*?" + re.escape(_PRIVATE_KEY_END),
    re.DOTALL,
)

_SAFE_PLACEHOLDER_WORDS = (
    "change_me",
    "changeme",
    "replace_me",
    "example",
    "placeholder",
    "redacted",
    "dummy",
    "fake",
    "test_only",
    "test-password",
    "test_password",
    "rasai_test_",
)


@dataclass(frozen=True, slots=True)
class SecretExposure:
    path: str
    line: int
    kind: str
    detail: str


def is_sensitive_name(name: str) -> bool:
    """Return True when a field/environment/header name denotes secret material."""

    normalized = name.upper().replace("-", "_").replace(".", "_")
    return any(token in normalized for token in _SENSITIVE_NAME_TOKENS)


def is_secret_reference_name(name: str) -> bool:
    normalized = name.upper().replace("-", "_").replace(".", "_")
    return normalized.endswith(_SECRET_REFERENCE_SUFFIXES)


def validate_environment_reference(value: str) -> str:
    text = value.strip()
    if not _ENV_NAME_RE.fullmatch(text):
        raise ValueError(f"secret environment reference must be an environment variable name: {value!r}")
    return text


def is_safe_placeholder(value: str) -> bool:
    """Recognize documentation/test placeholders, never real runtime secrets."""

    text = value.strip().strip("\"'")
    if not text:
        return True
    lowered = text.casefold()
    if text.startswith("<") and text.endswith(">"):
        return True
    if text.startswith("${") and text.endswith("}"):
        return True
    if text.startswith("[") and text.endswith("]"):
        return True
    if _ENV_NAME_RE.fullmatch(text) and is_sensitive_name(text):
        return True
    return any(word in lowered for word in _SAFE_PLACEHOLDER_WORDS)


def redact_url(value: str) -> str:
    """Remove passwords and sensitive query parameters from a URL/DSN."""

    text = value.strip()
    try:
        parsed = urlsplit(text)
    except ValueError:
        return REDACTED if "://" in text and "@" in text else value
    if not parsed.scheme or not parsed.netloc:
        return value

    username = quote(parsed.username or "", safe="")
    auth = f"{username}@" if username else ""
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        port = ""

    query_items: list[tuple[str, str]] = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        query_items.append((key, REDACTED if is_sensitive_name(key) else item))
    query = urlencode(query_items)
    return urlunsplit((parsed.scheme, f"{auth}{host}{port}", parsed.path, query, parsed.fragment))


def redact_text(value: str) -> str:
    """Scrub common credential forms from arbitrary user-visible/persisted text."""

    text = _PRIVATE_KEY_BLOCK_RE.sub(PRIVATE_KEY_REDACTED, value)
    text = _HEADER_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _BEARER_RE.sub("Bearer " + REDACTED, text)
    text = _URI_WITH_AUTH_RE.sub(lambda match: redact_url(match.group(0)), text)

    def quoted_assignment(match: re.Match[str]) -> str:
        name, quote_char, raw = match.group(1), match.group(2), match.group(3)
        if is_secret_reference_name(name) or is_safe_placeholder(raw):
            return match.group(0)
        prefix = match.group(0)[: match.group(0).find(quote_char) + 1]
        return prefix + REDACTED + quote_char

    def env_assignment(match: re.Match[str]) -> str:
        name, raw = match.group(1), match.group(2)
        if is_secret_reference_name(name) or is_safe_placeholder(raw):
            return match.group(0)
        return f"{name}={REDACTED}"

    text = _QUOTED_ASSIGNMENT_RE.sub(quoted_assignment, text)
    return _ENV_ASSIGNMENT_RE.sub(env_assignment, text)


def redact_value(value: Any, *, field_name: str | None = None) -> Any:
    """Recursively sanitize structured data before display or persistence."""

    if field_name and is_sensitive_name(field_name) and not is_secret_reference_name(field_name):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(key): redact_value(item, field_name=str(key)) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def detect_secret_exposures(text: str, *, path: str = "<memory>") -> tuple[SecretExposure, ...]:
    """Find high-confidence raw secrets while allowing explicit placeholders/references."""

    findings: list[SecretExposure] = []

    for match in _PRIVATE_KEY_BLOCK_RE.finditer(text):
        findings.append(SecretExposure(path, _line_number(text, match.start()), "PRIVATE_KEY", "private key material"))

    for match in _URI_WITH_AUTH_RE.finditer(text):
        candidate = match.group(0)
        try:
            password = urlsplit(candidate).password or ""
        except ValueError:
            password = ""
        if password and not is_safe_placeholder(password):
            findings.append(SecretExposure(path, _line_number(text, match.start()), "CREDENTIAL_URL", "URL/DSN contains inline password"))

    for match in _BEARER_RE.finditer(text):
        token = match.group(1)
        if not is_safe_placeholder(token):
            findings.append(SecretExposure(path, _line_number(text, match.start()), "BEARER_TOKEN", "Bearer token value"))

    for pattern, value_group in ((_QUOTED_ASSIGNMENT_RE, 3), (_ENV_ASSIGNMENT_RE, 2)):
        for match in pattern.finditer(text):
            name, raw = match.group(1), match.group(value_group)
            if is_secret_reference_name(name) or is_safe_placeholder(raw):
                continue
            findings.append(SecretExposure(path, _line_number(text, match.start()), "SECRET_ASSIGNMENT", f"inline value for {name}"))

    unique: dict[tuple[str, int, str], SecretExposure] = {}
    for item in findings:
        unique[(item.path, item.line, item.kind)] = item
    return tuple(unique.values())


_SCAN_SUFFIXES = frozenset({".py", ".md", ".txt", ".toml", ".ini", ".json", ".yml", ".yaml", ".cmd", ".ps1"})
_SCAN_NAMES = frozenset({".gitignore", "Dockerfile"})
_SCAN_EXCLUSIONS = frozenset({
    "src/rasai/secret_safety.py",
    "tests/test_secret_safety.py",
})


def _tracked_files(root: Path) -> tuple[Path, ...]:
    try:
        process = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        relatives = [item for item in process.stdout.decode("utf-8").split("\0") if item]
        return tuple(root / relative for relative in relatives)
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError):
        return tuple(path for path in root.rglob("*") if path.is_file())


def _should_scan(file_path: Path) -> bool:
    return (
        file_path.suffix.lower() in _SCAN_SUFFIXES
        or file_path.name in _SCAN_NAMES
        or file_path.name == ".env"
        or file_path.name.startswith(".env.")
    )


def scan_repository(root: str | Path) -> tuple[SecretExposure, ...]:
    repository = Path(root).resolve()
    findings: list[SecretExposure] = []
    for file_path in _tracked_files(repository):
        try:
            relative = file_path.relative_to(repository).as_posix()
        except ValueError:
            continue
        if relative in _SCAN_EXCLUSIONS or any(part in {".git", ".venv", "venv", "__pycache__", "audits"} for part in file_path.parts):
            continue
        if not _should_scan(file_path):
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(detect_secret_exposures(text, path=relative))
    return tuple(findings)


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    root = Path(__file__).resolve().parents[2]
    findings = scan_repository(root)
    if findings:
        print("SECRET SAFETY GATE: FAIL")
        for item in findings:
            print(f"- {item.path}:{item.line}: {item.kind}: {item.detail}")
        return 1
    print("SECRET SAFETY GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
