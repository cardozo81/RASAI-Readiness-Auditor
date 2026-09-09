"""Central secret classification, redaction and repository leak detection.

The module is provider-neutral. Secrets may be consumed from environment variables
or a future secret manager, but their values must never become product configuration,
reports, manifests, logs, exceptions or versioned repository content.
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

_SECRET_REFERENCE_SUFFIXES = ("_SECRET_REF", "_CREDENTIAL_REF", "_ENV", "_REF")
_SENSITIVE_EXACT_NAMES = frozenset({
    "API_KEY", "APIKEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL",
    "PRIVATE_KEY", "ACCESS_KEY", "AUTHORIZATION", "PROXY_AUTHORIZATION", "COOKIE",
    "SET_COOKIE", "X_API_KEY",
})
_SENSITIVE_NAME_SUFFIXES = (
    "_API_KEY", "_APIKEY", "_TOKEN", "_SECRET", "_PASSWORD", "_PASSWD",
    "_CREDENTIAL", "_PRIVATE_KEY", "_ACCESS_KEY", "_AUTHORIZATION", "_COOKIE",
)
_SENSITIVE_ARG_NAMES = frozenset({
    "DATABASE_URL", "DB_URL", "DSN", "CONNECTION_STRING", "CONNECTION_URL",
})
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_URI_WITH_AUTH_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/@:]+:[^\s/@]+@[^\s]+")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+([^\s,;]+)")
_HEADER_RE = re.compile(
    r"(?im)^(\s*(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key|api-key)\s*:\s*)(.+)$"
)
_SENSITIVE_FIELD_PATTERN = (
    r"[A-Za-z0-9_.-]*(?:api[_-]?key|token|secret|password|passwd|credential|"
    r"private[_-]?key|access[_-]?key|authorization|cookie)[A-Za-z0-9_.-]*"
)
_QUOTED_ASSIGNMENT_RE = re.compile(
    rf"(?im)\b({_SENSITIVE_FIELD_PATTERN})\b\s*[:=]\s*([\"'])([^\"'\n]+)\2"
)
_UNQUOTED_ASSIGNMENT_RE = re.compile(
    rf"(?im)\b({_SENSITIVE_FIELD_PATTERN})\b\s*[:=]\s*([^\s\"'#,;}}]+)"
)
_PRIVATE_KEY_BEGIN = "-----BEGIN " + "PRIVATE KEY-----"
_PRIVATE_KEY_END = "-----END " + "PRIVATE KEY-----"
_PRIVATE_KEY_BLOCK_RE = re.compile(
    re.escape(_PRIVATE_KEY_BEGIN) + r".*?" + re.escape(_PRIVATE_KEY_END), re.DOTALL
)
_KNOWN_SECRET_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|AIza[A-Za-z0-9_-]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{12,}|AKIA[A-Z0-9]{16})"
)

_SAFE_PLACEHOLDER_WORDS = (
    "change_me", "changeme", "replace_me", "example", "placeholder", "redacted",
    "dummy", "fake", "test_only", "test-password", "test_password", "rasai_test_",
    "seu-token", "your-token", "your_token", "seu-password", "sua-senha",
)
_SAFE_EXACT_PLACEHOLDERS = frozenset({
    "token", "tokens", "password", "pass", "passwd", "secret", "secrets",
    "credential", "credentials", "value", "key", "senha",
})
_CONFIG_LIKE_SUFFIXES = frozenset({
    ".toml", ".ini", ".json", ".yml", ".yaml", ".env",
})
_SCAN_SUFFIXES = frozenset({
    ".py", ".md", ".txt", ".toml", ".ini", ".json", ".yml", ".yaml", ".cmd", ".ps1",
})
_SCAN_NAMES = frozenset({".gitignore", "Dockerfile"})
_SCAN_EXCLUSIONS = frozenset({"src/rasai/secret_safety.py", "tests/test_secret_safety.py"})
_SAFE_ENV_EXAMPLE_NAMES = frozenset({
    ".env.example", ".env.sample", ".env.template", ".env.postgres.example",
})


@dataclass(frozen=True, slots=True)
class SecretExposure:
    path: str
    line: int
    kind: str
    detail: str


def _normalize_name(name: str) -> str:
    return name.upper().replace("-", "_").replace(".", "_")


def is_secret_reference_name(name: str) -> bool:
    normalized = _normalize_name(name)
    return normalized.endswith(_SECRET_REFERENCE_SUFFIXES)


def _secret_name_core(name: str) -> str:
    normalized = _normalize_name(name)
    for suffix in _SECRET_REFERENCE_SUFFIXES:
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def is_sensitive_name(name: str) -> bool:
    """Classify credential-bearing field names without misclassifying token metrics."""
    core = _secret_name_core(name)
    return core in _SENSITIVE_EXACT_NAMES or core.endswith(_SENSITIVE_NAME_SUFFIXES)


def validate_environment_reference(value: str) -> str:
    text = value.strip()
    if not _ENV_NAME_RE.fullmatch(text):
        raise ValueError(f"secret environment reference must be an environment variable name: {value!r}")
    return text


def _placeholder_candidate(value: str) -> str:
    return value.strip().strip("\"'`*_.,:;()")


def is_safe_placeholder(value: str) -> bool:
    text = _placeholder_candidate(value)
    if not text:
        return True
    lowered = text.casefold()
    if lowered in _SAFE_EXACT_PLACEHOLDERS:
        return True
    if text.startswith("<") and text.endswith(">"):
        return True
    if text.startswith("${") and text.endswith("}"):
        return True
    if text.startswith("[") and text.endswith("]"):
        return True
    if "{" in text and "}" in text:
        return True
    if "..." in text or "xxx" in lowered:
        return True
    if _ENV_NAME_RE.fullmatch(text) and is_sensitive_name(text):
        return True
    return any(word in lowered for word in _SAFE_PLACEHOLDER_WORDS)


def _looks_high_confidence_secret(value: str) -> bool:
    text = _placeholder_candidate(value)
    if not text or is_safe_placeholder(text):
        return False
    if _KNOWN_SECRET_RE.search(text):
        return True
    if len(text) < 24 or any(ch.isspace() for ch in text):
        return False
    classes = sum((
        any(ch.islower() for ch in text),
        any(ch.isupper() for ch in text),
        any(ch.isdigit() for ch in text),
        any(not ch.isalnum() for ch in text),
    ))
    return classes >= 2


def _is_config_like_path(path: str) -> bool:
    candidate = Path(path)
    lowered_name = candidate.name.casefold()
    if lowered_name == ".env" or lowered_name.startswith(".env."):
        return True
    return candidate.suffix.casefold() in _CONFIG_LIKE_SUFFIXES


def redact_url(value: str) -> str:
    """Remove URL userinfo passwords and sensitive query parameters."""
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
    query_items = [
        (key, REDACTED if is_sensitive_name(key) else item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, f"{auth}{host}{port}", parsed.path, urlencode(query_items), parsed.fragment))


def redact_text(value: str) -> str:
    """Scrub credential material from arbitrary runtime text.

    Runtime redaction is stricter than repository leak detection: placeholder-looking
    values are still removed once they enter logs, exceptions, reports or evidence.
    """
    text = _PRIVATE_KEY_BLOCK_RE.sub(PRIVATE_KEY_REDACTED, value)
    text = _HEADER_RE.sub(lambda match: match.group(1) + REDACTED, text)
    text = _BEARER_RE.sub("Bearer " + REDACTED, text)
    text = _URI_WITH_AUTH_RE.sub(lambda match: redact_url(match.group(0)), text)
    text = _KNOWN_SECRET_RE.sub(REDACTED, text)

    def quoted_assignment(match: re.Match[str]) -> str:
        name, quote_char, raw = match.group(1), match.group(2), match.group(3)
        if not is_sensitive_name(name) or is_secret_reference_name(name):
            return match.group(0)
        prefix = match.group(0)[: match.group(0).find(quote_char) + 1]
        return prefix + REDACTED + quote_char

    def unquoted_assignment(match: re.Match[str]) -> str:
        name, raw = match.group(1), match.group(2)
        if not is_sensitive_name(name) or is_secret_reference_name(name):
            return match.group(0)
        prefix = match.group(0)[: match.group(0).rfind(raw)]
        return prefix + REDACTED

    text = _QUOTED_ASSIGNMENT_RE.sub(quoted_assignment, text)
    return _UNQUOTED_ASSIGNMENT_RE.sub(unquoted_assignment, text)


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


def validate_secret_free_mapping(value: Mapping[str, Any], *, context: str = "configuration") -> None:
    """Reject inline secrets in durable configuration while allowing references."""

    def visit(node: Any, path: str, key: str | None = None) -> None:
        if isinstance(node, Mapping):
            for raw_key, child in node.items():
                child_key = str(raw_key)
                child_path = f"{path}.{child_key}" if path else child_key
                if is_sensitive_name(child_key) and not is_secret_reference_name(child_key):
                    raise ValueError(
                        f"{context} must not persist inline secret field {child_path!r}; use an *_env or *_ref reference"
                    )
                if is_secret_reference_name(child_key):
                    if not isinstance(child, str):
                        raise ValueError(f"secret reference {child_path!r} must be a string")
                    if _normalize_name(child_key).endswith("_ENV"):
                        validate_environment_reference(child)
                visit(child, child_path, child_key)
            return
        if isinstance(node, (list, tuple)):
            for index, child in enumerate(node):
                visit(child, f"{path}[{index}]", key)
            return
        if isinstance(node, str) and not (key and is_secret_reference_name(key)):
            if detect_secret_exposures(node, path=path or context, strict=True):
                raise ValueError(
                    f"{context} contains inline credential-like material at {path or '<root>'}; store the value outside persistence and reference it instead"
                )

    visit(value, context)


def validate_command_argv_secret_free(command_argv: Sequence[str], *, context: str = "schedule command") -> None:
    """Reject raw secrets/DSNs in durable scheduler command arguments."""
    values = tuple(str(item) for item in command_argv)
    previous_option: str | None = None
    for index, item in enumerate(values):
        if previous_option is not None:
            normalized_previous = _normalize_name(previous_option.lstrip("-"))
            if (is_sensitive_name(normalized_previous) or normalized_previous in _SENSITIVE_ARG_NAMES) and not is_secret_reference_name(normalized_previous):
                raise ValueError(
                    f"{context} must not persist a value for credential-bearing option {previous_option!r}; use environment/secret references"
                )
            previous_option = None

        if detect_secret_exposures(item, path=context, strict=True):
            raise ValueError(f"{context} contains credential material in argument {index}; use environment/secret references")
        if not item.startswith("-"):
            continue
        option, separator, inline_value = item.partition("=")
        normalized = _normalize_name(option.lstrip("-"))
        sensitive_option = is_sensitive_name(normalized) or normalized in _SENSITIVE_ARG_NAMES
        if sensitive_option and not is_secret_reference_name(normalized):
            raise ValueError(
                f"{context} must not persist credential-bearing option {option!r}; inject the secret through environment/secret management at runtime"
            )
        if separator and inline_value and detect_secret_exposures(inline_value, path=context, strict=True):
            raise ValueError(f"{context} contains credential material in argument {index}")
        if not separator:
            previous_option = option


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def detect_secret_exposures(
    text: str,
    *,
    path: str = "<memory>",
    strict: bool = True,
) -> tuple[SecretExposure, ...]:
    """Find raw secret material.

    ``strict=True`` is used at runtime/configuration boundaries. Repository scanning
    uses ``strict=False`` so source code, tests and prose fail only for high-confidence
    secret material or credential literals in config-like files.
    """
    findings: list[SecretExposure] = []
    config_like = _is_config_like_path(path)

    for match in _PRIVATE_KEY_BLOCK_RE.finditer(text):
        findings.append(SecretExposure(path, _line_number(text, match.start()), "PRIVATE_KEY", "private key material"))

    for match in _KNOWN_SECRET_RE.finditer(text):
        findings.append(SecretExposure(path, _line_number(text, match.start()), "KNOWN_SECRET_PATTERN", "known credential token pattern"))

    for match in _URI_WITH_AUTH_RE.finditer(text):
        candidate = match.group(0)
        try:
            password = urlsplit(candidate).password or ""
        except ValueError:
            password = ""
        if password and not is_safe_placeholder(password):
            if strict or config_like or _looks_high_confidence_secret(password):
                findings.append(SecretExposure(path, _line_number(text, match.start()), "CREDENTIAL_URL", "URL/DSN contains inline password"))

    for match in _BEARER_RE.finditer(text):
        token = match.group(1)
        if is_safe_placeholder(token):
            continue
        if strict or config_like or _looks_high_confidence_secret(token):
            findings.append(SecretExposure(path, _line_number(text, match.start()), "BEARER_TOKEN", "Bearer token value"))

    python_source = str(path).casefold().endswith(".py")
    if not python_source:
        for pattern, value_group in ((_QUOTED_ASSIGNMENT_RE, 3), (_UNQUOTED_ASSIGNMENT_RE, 2)):
            for match in pattern.finditer(text):
                name, raw = match.group(1), match.group(value_group)
                if not is_sensitive_name(name) or is_secret_reference_name(name) or is_safe_placeholder(raw):
                    continue
                if strict or config_like or _looks_high_confidence_secret(raw):
                    findings.append(SecretExposure(path, _line_number(text, match.start()), "SECRET_ASSIGNMENT", f"inline value for {name}"))

    unique: dict[tuple[str, int, str], SecretExposure] = {}
    for item in findings:
        unique[(item.path, item.line, item.kind)] = item
    return tuple(unique.values())


def _tracked_files(root: Path) -> tuple[Path, ...]:
    try:
        process = subprocess.run(
            ["git", "ls-files", "-z"], cwd=root, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
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
        lowered_name = file_path.name.casefold()
        if (lowered_name == ".env" or lowered_name.startswith(".env.")) and lowered_name not in _SAFE_ENV_EXAMPLE_NAMES:
            findings.append(SecretExposure(relative, 1, "VERSIONED_ENV_FILE", "runtime environment files must not be versioned"))
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(detect_secret_exposures(text, path=relative, strict=False))
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
