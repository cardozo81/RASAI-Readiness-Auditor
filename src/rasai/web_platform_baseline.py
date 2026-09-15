"""Deterministic Web Platform Baseline / WebDX materialization.

The collector uses only audit-owned page artifacts for feature detection. It does not
re-fetch target CSS/JS assets. In ``auto`` mode it downloads the canonical
``web-features`` npm package once per AUD, freezes the exact ``data.json`` inside the
audit workspace, and records version + SHA-256 for reproducibility.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tarfile
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from rasai.persistence import AuditWorkspace
from rasai.standards_metrics import _init, _record, _service_run
from rasai.standards_service_registry import (
    DEFAULT_STANDARDS_TIMEOUT_SECONDS,
    STANDARDS_TIMEOUT_ENV,
    WEB_FEATURES_DATASET_ENV,
    service,
    service_state,
)

CONTRACT_VERSION = "WEB-PLATFORM-BASELINE-001"
AUTO_SELECTOR = "auto"
NPM_LATEST_URL = "https://registry.npmjs.org/web-features/latest"
NPM_HOST = "registry.npmjs.org"
DATA_ARTIFACT = Path("artifacts", "standards", "web-features", "data.json")
METADATA_ARTIFACT = Path("artifacts", "standards", "web-features", "metadata.json")
OBSERVATIONS_ARTIFACT = Path("artifacts", "standards", "web-features", "observations.json")
MAX_REGISTRY_BYTES = 2 * 1024 * 1024
MAX_TARBALL_BYTES = 64 * 1024 * 1024
MAX_DATASET_BYTES = 32 * 1024 * 1024
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
MAX_FEATURES_PER_SNAPSHOT = 250

_CSS_DECLARATION_RE = re.compile(r"(?<![-\w])([A-Za-z-][\w-]*)\s*:\s*([^;{}]+)")
_CSS_AT_RULE_RE = re.compile(r"@([A-Za-z-]+)")
_CSS_PSEUDO_RE = re.compile(r"(?<!:):{1,2}([A-Za-z-]+)")
_CSS_VALUE_TOKEN_RE = re.compile(r"[-A-Za-z][\w-]*")
_JS_LITERAL_OR_COMMENT_RE = re.compile(
    r'''(?s)(?://[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`)'''
)
_JS_MEMBER_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\.\s*([A-Za-z_$][\w$]*)")
_JS_NEW_RE = re.compile(r"\bnew\s+([A-Z][A-Za-z0-9_$]*)\s*\(")
_JS_WINDOW_INTERFACE_RE = re.compile(r"\bwindow\s*\.\s*([A-Z][A-Za-z0-9_$]*)\b")
_JS_GLOBAL_FUNCTION_RE = re.compile(
    r"(?<![\w$.])(" 
    r"fetch|queueMicrotask|requestAnimationFrame|cancelAnimationFrame|"
    r"structuredClone|atob|btoa|matchMedia"
    r")\s*\("
)

_JS_OBJECT_TO_BCD = {
    "document": "api.Document",
    "navigator": "api.Navigator",
    "window": "api.Window",
    "history": "api.History",
    "location": "api.Location",
    "performance": "api.Performance",
    "crypto": "api.Crypto",
    "screen": "api.Screen",
    "CSS": "api.CSS",
}
_JS_BUILTINS = {
    "Array", "ArrayBuffer", "Atomics", "BigInt", "DataView", "Date", "Error",
    "Intl", "JSON", "Map", "Math", "Number", "Object", "Promise", "Reflect",
    "RegExp", "Set", "String", "Symbol", "TypedArray", "WeakMap", "WeakSet",
}


class WebPlatformBaselineError(RuntimeError):
    """Expected dataset/source/materialization error for the advisory service."""


class _SourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, tuple[tuple[str, str | None], ...]]] = []
        self.css_chunks: list[str] = []
        self.js_chunks: list[str] = []
        self.external_scripts = 0
        self.external_stylesheets = 0
        self._capture: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        normalized = tuple((name.casefold(), value) for name, value in attrs)
        self.elements.append((lowered, normalized))
        attr_map = {name: value for name, value in normalized}
        style = attr_map.get("style")
        if style:
            self.css_chunks.append(style)
        if lowered == "style":
            self._capture = "style"
        elif lowered == "script":
            if attr_map.get("src"):
                self.external_scripts += 1
            else:
                self._capture = "script"
        elif lowered == "link":
            rel = (attr_map.get("rel") or "").casefold().split()
            if "stylesheet" in rel and attr_map.get("href"):
                self.external_stylesheets += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"style", "script"}:
            self._capture = None

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self._capture == "style":
            self.css_chunks.append(data)
        elif self._capture == "script":
            self.js_chunks.append(data)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def _dataset_metadata_dir(workspace: AuditWorkspace) -> Path:
    path = workspace.root / DATA_ARTIFACT.parent
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _timeout(environment: Mapping[str, str]) -> float:
    raw = (environment.get(STANDARDS_TIMEOUT_ENV) or "").strip()
    if not raw:
        return DEFAULT_STANDARDS_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise WebPlatformBaselineError(f"{STANDARDS_TIMEOUT_ENV} must be numeric") from exc
    if not 0 < value < 3600:
        raise WebPlatformBaselineError(f"{STANDARDS_TIMEOUT_ENV} must be > 0 and < 3600")
    return value


def _read_url_bytes(url: str, *, timeout: float, limit: int, allowed_host: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != allowed_host:
        raise WebPlatformBaselineError(f"unexpected WebDX source URL: {url}")
    request = Request(
        url,
        headers={
            "Accept": "application/json, application/octet-stream;q=0.9",
            "User-Agent": "RASAi-Readiness-Auditor/0.1 WebDX",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != allowed_host:
            raise WebPlatformBaselineError(f"unexpected WebDX redirect: {response.geturl()}")
        declared = response.headers.get("Content-Length")
        if declared:
            try:
                if int(declared) > limit:
                    raise WebPlatformBaselineError("WebDX source exceeds bounded size")
            except ValueError:
                pass
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise WebPlatformBaselineError("WebDX source exceeds bounded size")
    return payload


def _validate_dataset_bytes(payload: bytes) -> dict[str, Any]:
    if len(payload) > MAX_DATASET_BYTES:
        raise WebPlatformBaselineError("web-features data.json exceeds bounded size")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebPlatformBaselineError("web-features dataset is not valid UTF-8 JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("features"), dict):
        raise WebPlatformBaselineError("web-features dataset must contain a features object")
    if not data["features"]:
        raise WebPlatformBaselineError("web-features dataset contains no features")
    return data


def _extract_data_json(tarball: bytes) -> bytes:
    try:
        with tarfile.open(fileobj=BytesIO(tarball), mode="r:gz") as archive:
            try:
                member = archive.getmember("package/data.json")
            except KeyError as exc:
                raise WebPlatformBaselineError("web-features package does not contain package/data.json") from exc
            if not member.isfile() or member.size > MAX_DATASET_BYTES:
                raise WebPlatformBaselineError("web-features package data.json is invalid or too large")
            stream = archive.extractfile(member)
            if stream is None:
                raise WebPlatformBaselineError("web-features package data.json cannot be read")
            payload = stream.read(MAX_DATASET_BYTES + 1)
    except WebPlatformBaselineError:
        raise
    except (tarfile.TarError, OSError) as exc:
        raise WebPlatformBaselineError("web-features npm package is not a valid bounded tarball") from exc
    if len(payload) > MAX_DATASET_BYTES:
        raise WebPlatformBaselineError("web-features package data.json exceeds bounded size")
    return payload


def _read_local_dataset(path: Path) -> tuple[bytes, str | None]:
    try:
        if not path.is_file():
            raise WebPlatformBaselineError("configured web-features dataset file does not exist")
        if path.stat().st_size > MAX_DATASET_BYTES:
            raise WebPlatformBaselineError("configured web-features dataset exceeds bounded size")
        payload = path.read_bytes()
    except OSError as exc:
        raise WebPlatformBaselineError("configured web-features dataset cannot be read") from exc

    version: str | None = None
    package_json = path.parent / "package.json"
    if package_json.is_file():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
            if isinstance(package, dict) and isinstance(package.get("version"), str):
                version = package["version"].strip() or None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            version = None
    return payload, version


def _load_frozen_dataset(workspace: AuditWorkspace) -> tuple[dict[str, Any], dict[str, Any]]:
    data_path = workspace.root / DATA_ARTIFACT
    metadata_path = workspace.root / METADATA_ARTIFACT
    if not data_path.is_file() and not metadata_path.is_file():
        raise FileNotFoundError
    if not data_path.is_file() or not metadata_path.is_file():
        raise WebPlatformBaselineError("AUD WebDX snapshot is incomplete; refusing silent dataset replacement")
    try:
        payload = data_path.read_bytes()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebPlatformBaselineError("AUD WebDX snapshot cannot be reopened") from exc
    data = _validate_dataset_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    if not isinstance(metadata, dict) or metadata.get("sha256") != digest:
        raise WebPlatformBaselineError("AUD WebDX snapshot SHA-256 does not match metadata")
    return data, metadata


def _resolve_dataset(
    workspace: AuditWorkspace,
    environment: Mapping[str, str],
    *,
    read_url: Callable[..., bytes] = _read_url_bytes,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        return _load_frozen_dataset(workspace)
    except FileNotFoundError:
        pass

    selector = (environment.get(WEB_FEATURES_DATASET_ENV) or AUTO_SELECTOR).strip()
    if not selector:
        selector = AUTO_SELECTOR
    timeout = _timeout(environment)

    if selector.casefold() == AUTO_SELECTOR:
        metadata_payload = read_url(
            NPM_LATEST_URL,
            timeout=timeout,
            limit=MAX_REGISTRY_BYTES,
            allowed_host=NPM_HOST,
        )
        try:
            registry = json.loads(metadata_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WebPlatformBaselineError("npm web-features metadata is invalid") from exc
        if not isinstance(registry, dict):
            raise WebPlatformBaselineError("npm web-features metadata has unexpected shape")
        version = registry.get("version")
        dist = registry.get("dist")
        if not isinstance(version, str) or not version.strip() or not isinstance(dist, dict):
            raise WebPlatformBaselineError("npm web-features metadata lacks version/dist")
        tarball_url = dist.get("tarball")
        if not isinstance(tarball_url, str):
            raise WebPlatformBaselineError("npm web-features metadata lacks tarball URL")
        tarball = read_url(
            tarball_url,
            timeout=timeout,
            limit=MAX_TARBALL_BYTES,
            allowed_host=NPM_HOST,
        )
        payload = _extract_data_json(tarball)
        source_metadata: dict[str, Any] = {
            "contract_version": CONTRACT_VERSION,
            "selector": AUTO_SELECTOR,
            "source": "NPM_WEB_FEATURES",
            "package": "web-features",
            "version": version.strip(),
            "registry": NPM_LATEST_URL,
            "tarball": tarball_url,
            "npm_integrity": dist.get("integrity"),
            "npm_shasum": dist.get("shasum"),
            "frozen_at": _utc_now(),
        }
    else:
        local_path = Path(selector).expanduser().resolve()
        payload, local_version = _read_local_dataset(local_path)
        source_metadata = {
            "contract_version": CONTRACT_VERSION,
            "selector": "local",
            "source": "LOCAL_OVERRIDE",
            "package": "web-features",
            "version": local_version or "local-unversioned",
            "source_filename": local_path.name,
            "frozen_at": _utc_now(),
        }

    data = _validate_dataset_bytes(payload)
    source_metadata["sha256"] = hashlib.sha256(payload).hexdigest()
    source_metadata["bytes"] = len(payload)
    source_metadata["feature_count"] = len(data["features"])
    _dataset_metadata_dir(workspace)
    _atomic_write(workspace.root / DATA_ARTIFACT, payload)
    _atomic_write(workspace.root / METADATA_ARTIFACT, _json_bytes(source_metadata))
    return data, source_metadata


def _compat_index(dataset: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    reverse: dict[str, list[str]] = defaultdict(list)
    features = dataset.get("features")
    if not isinstance(features, dict):
        return {}
    for feature_id, raw in features.items():
        if not isinstance(feature_id, str) or not isinstance(raw, dict) or raw.get("kind") != "feature":
            continue
        compat = raw.get("compat_features")
        if not isinstance(compat, list):
            continue
        for key in compat:
            if isinstance(key, str) and key:
                reverse[key].append(feature_id)
    return {key: tuple(values) for key, values in reverse.items()}


def _candidate_variants(value: str) -> tuple[str, ...]:
    raw = value.strip().casefold()
    if not raw:
        return ()
    normalized = raw.replace("-", "_")
    return (raw,) if normalized == raw else (raw, normalized)


def _add_signal(
    signals: dict[str, list[dict[str, str]]],
    known: set[str],
    candidates: Iterable[str],
    *,
    kind: str,
    evidence: str,
) -> None:
    for candidate in candidates:
        if candidate not in known:
            continue
        bucket = signals[candidate]
        item = {"kind": kind, "evidence": evidence[:240]}
        if item not in bucket and len(bucket) < 5:
            bucket.append(item)


def _html_candidates(tag: str, attrs: Iterable[tuple[str, str | None]]) -> list[tuple[tuple[str, ...], str]]:
    results: list[tuple[tuple[str, ...], str]] = []
    tag_variants = _candidate_variants(tag)
    for namespace in ("html.elements", "svg.elements", "mathml.elements"):
        results.append((tuple(f"{namespace}.{variant}" for variant in tag_variants), f"<{tag}>"))
    for name, value in attrs:
        name_variants = _candidate_variants(name)
        for namespace in ("html.elements", "svg.elements", "mathml.elements"):
            candidates = []
            for tag_value in tag_variants:
                for attr_value in name_variants:
                    candidates.append(f"{namespace}.{tag_value}.{attr_value}")
                    if value:
                        for enum_value in _candidate_variants(value.split()[0]):
                            candidates.append(f"{namespace}.{tag_value}.{attr_value}_{enum_value}")
                            candidates.append(f"{namespace}.{tag_value}.{attr_value}.{enum_value}")
            results.append((tuple(candidates), f"<{tag} {name}>"))
        global_candidates = []
        for attr_value in name_variants:
            global_candidates.append(f"html.global_attributes.{attr_value}")
            if value:
                for enum_value in _candidate_variants(value.split()[0]):
                    global_candidates.append(f"html.global_attributes.{attr_value}_{enum_value}")
                    global_candidates.append(f"html.global_attributes.{attr_value}.{enum_value}")
        results.append((tuple(global_candidates), f"global attribute {name}"))
    return results


def _detect_css(css: str, known: set[str], signals: dict[str, list[dict[str, str]]]) -> None:
    for match in _CSS_DECLARATION_RE.finditer(css):
        prop = match.group(1).casefold()
        if prop.startswith("--"):
            continue
        prop_variants = _candidate_variants(prop)
        _add_signal(
            signals, known, (f"css.properties.{value}" for value in prop_variants),
            kind="CSS_PROPERTY", evidence=prop,
        )
        value_text = match.group(2)
        for token in _CSS_VALUE_TOKEN_RE.findall(value_text):
            token_variants = _candidate_variants(token)
            candidates = (
                f"css.properties.{prop_value}.{token_value}"
                for prop_value in prop_variants for token_value in token_variants
            )
            _add_signal(
                signals, known, candidates, kind="CSS_PROPERTY_VALUE",
                evidence=f"{prop}: {token}",
            )
    for match in _CSS_AT_RULE_RE.finditer(css):
        name = match.group(1).casefold()
        _add_signal(
            signals, known, (f"css.at-rules.{value}" for value in _candidate_variants(name)),
            kind="CSS_AT_RULE", evidence=f"@{name}",
        )
    for match in _CSS_PSEUDO_RE.finditer(css):
        name = match.group(1).casefold()
        _add_signal(
            signals, known, (f"css.selectors.{value}" for value in _candidate_variants(name)),
            kind="CSS_SELECTOR", evidence=f":{name}",
        )


def _detect_js(js: str, known: set[str], signals: dict[str, list[dict[str, str]]]) -> None:
    source = _JS_LITERAL_OR_COMMENT_RE.sub(" ", js)
    for match in _JS_MEMBER_RE.finditer(source):
        owner, member = match.groups()
        prefix = _JS_OBJECT_TO_BCD.get(owner)
        if prefix:
            _add_signal(
                signals, known, (f"{prefix}.{member}",),
                kind="JS_API_MEMBER", evidence=f"{owner}.{member}",
            )
        if owner in _JS_BUILTINS:
            _add_signal(
                signals, known, (f"javascript.builtins.{owner}.{member}",),
                kind="JS_BUILTIN_MEMBER", evidence=f"{owner}.{member}",
            )
    for match in _JS_NEW_RE.finditer(source):
        interface = match.group(1)
        _add_signal(
            signals, known, (f"api.{interface}",), kind="JS_CONSTRUCTOR",
            evidence=f"new {interface}()",
        )
    for match in _JS_WINDOW_INTERFACE_RE.finditer(source):
        interface = match.group(1)
        _add_signal(
            signals, known, (f"api.{interface}",), kind="JS_GLOBAL_INTERFACE",
            evidence=f"window.{interface}",
        )
    for match in _JS_GLOBAL_FUNCTION_RE.finditer(source):
        member = match.group(1)
        _add_signal(
            signals, known, (f"api.Window.{member}",), kind="JS_GLOBAL_FUNCTION",
            evidence=f"{member}()",
        )


def detect_compat_features(
    html: str,
    known_compat_keys: Iterable[str],
) -> tuple[dict[str, tuple[dict[str, str], ...]], dict[str, Any]]:
    """Return directly observable BCD keys and bounded detector metadata."""
    known = set(known_compat_keys)
    parser = _SourceParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        raise WebPlatformBaselineError(f"persisted HTML cannot be parsed: {type(exc).__name__}") from exc

    signals: dict[str, list[dict[str, str]]] = defaultdict(list)
    for tag, attrs in parser.elements:
        for candidates, evidence in _html_candidates(tag, attrs):
            _add_signal(signals, known, candidates, kind="HTML_SOURCE", evidence=evidence)
    css = "\n".join(parser.css_chunks)
    js = "\n".join(parser.js_chunks)
    _detect_css(css, known, signals)
    _detect_js(js, known, signals)
    return (
        {key: tuple(values) for key, values in signals.items()},
        {
            "html_elements_observed": len(parser.elements),
            "inline_css_chars": len(css),
            "inline_js_chars": len(js),
            "external_scripts_not_refetched": parser.external_scripts,
            "external_stylesheets_not_refetched": parser.external_stylesheets,
        },
    )


def _status_for_key(feature: Mapping[str, Any], compat_key: str) -> tuple[str, Mapping[str, Any]]:
    status = feature.get("status")
    if not isinstance(status, dict):
        return "UNKNOWN", {}
    by_key = status.get("by_compat_key")
    effective: Mapping[str, Any] = status
    if isinstance(by_key, dict) and isinstance(by_key.get(compat_key), dict):
        effective = by_key[compat_key]
    baseline = effective.get("baseline")
    if baseline == "high":
        return "WIDELY_AVAILABLE", effective
    if baseline == "low":
        return "NEWLY_AVAILABLE", effective
    if baseline is False:
        return "LIMITED_AVAILABILITY", effective
    return "UNKNOWN", effective


_STATUS_RANK = {
    "WIDELY_AVAILABLE": 1,
    "UNKNOWN": 2,
    "NEWLY_AVAILABLE": 3,
    "LIMITED_AVAILABILITY": 4,
}


def _feature_observations(
    dataset: Mapping[str, Any],
    reverse: Mapping[str, tuple[str, ...]],
    signals: Mapping[str, tuple[dict[str, str], ...]],
) -> list[dict[str, Any]]:
    features = dataset["features"]
    mapped: dict[str, list[str]] = defaultdict(list)
    for compat_key in signals:
        for feature_id in reverse.get(compat_key, ()):
            mapped[feature_id].append(compat_key)

    observations: list[dict[str, Any]] = []
    for feature_id in sorted(mapped)[:MAX_FEATURES_PER_SNAPSHOT]:
        feature = features.get(feature_id)
        if not isinstance(feature, dict) or feature.get("kind") != "feature":
            continue
        per_key: dict[str, dict[str, Any]] = {}
        chosen: str | None = None
        for compat_key in sorted(set(mapped[feature_id])):
            classification, effective = _status_for_key(feature, compat_key)
            if chosen is None or _STATUS_RANK[classification] > _STATUS_RANK[chosen]:
                chosen = classification
            per_key[compat_key] = {
                "classification": classification,
                "baseline": effective.get("baseline"),
                "baseline_low_date": effective.get("baseline_low_date"),
                "baseline_high_date": effective.get("baseline_high_date"),
                "support": effective.get("support"),
                "signals": list(signals.get(compat_key, ())),
            }
        discouraged = feature.get("discouraged")
        discouraged_details: dict[str, Any] | None = None
        if isinstance(discouraged, dict):
            discouraged_details = {
                "reason": discouraged.get("reason"),
                "alternatives": discouraged.get("alternatives"),
                "removal_date": discouraged.get("removal_date"),
            }
        observations.append(
            {
                "feature_id": feature_id,
                "name": feature.get("name") or feature_id,
                "description": feature.get("description"),
                "classification": chosen or "UNKNOWN",
                "compat_keys": sorted(set(mapped[feature_id])),
                "per_compat_key": per_key,
                "discouraged": discouraged_details,
            }
        )
    return observations


def _safe_artifact(
    workspace: AuditWorkspace,
    rendered_ref: str | None,
    raw_ref: str | None,
) -> tuple[str, str, bool] | None:
    root = workspace.root.resolve()
    for reference in (rendered_ref, raw_ref):
        if not reference:
            continue
        try:
            path = (workspace.root / reference).resolve()
            path.relative_to(root)
            if not path.is_file():
                continue
            payload = path.read_bytes()
        except (OSError, ValueError):
            continue
        truncated = len(payload) > MAX_ARTIFACT_BYTES
        payload = payload[:MAX_ARTIFACT_BYTES]
        text = payload.decode("utf-8", errors="replace")
        return text, reference, truncated
    return None


def _snapshot_rows(connection: sqlite3.Connection, audit_id: str) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """SELECT ps.snapshot_id,ps.device,ps.rendered_artifact_ref,ps.raw_artifact_ref,
                      p.normalized_url
               FROM page_snapshots ps
               JOIN pages p ON p.page_id=ps.page_id
               WHERE p.audit_id=?
               ORDER BY p.normalized_url,ps.device,ps.snapshot_id""",
            (audit_id,),
        ).fetchall()
    )


def _service_details_base(metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "dataset": dict(metadata or {}),
        "detector_scope": "AUD-owned rendered/raw HTML plus inline CSS and inline JavaScript",
        "external_assets_analyzed": False,
        "external_target_assets_refetched": False,
        "dynamic_runtime_usage_traced": False,
        "complete_page_feature_inventory": False,
        "boundary": (
            "SUCCESS means deterministic classification of directly observable feature signals "
            "within this bounded detector scope; it is not an exhaustive inventory of code hidden "
            "inside external assets or unexecuted dynamic paths."
        ),
    }


def materialize_web_platform_baseline(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    env: Mapping[str, str] | None = None,
    read_url: Callable[..., bytes] = _read_url_bytes,
) -> dict[str, Any]:
    """Materialize WebDX classifications over persisted audit artifacts."""
    environment = env if env is not None else os.environ
    item = service("web-platform-baseline")
    state_info = service_state(item, environment)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    result: dict[str, Any] = {"state": str(state_info["state"]), "attempted": 0, "succeeded": 0}
    try:
        with connection:
            _init(connection)
            connection.execute(
                "DELETE FROM standards_metric_observations "
                "WHERE audit_id=? AND metric_id GLOB 'web_platform_*'",
                (audit_id,),
            )
            if not bool(state_info["effective_enabled"]):
                _service_run(
                    connection, audit_id=audit_id, service_id=item.id,
                    state_info=state_info, state=str(state_info["state"]),
                    details=_service_details_base(),
                )
                return result

            rows = _snapshot_rows(connection, audit_id)
            attempted = len(rows)
            result["attempted"] = attempted
            if not rows:
                details = _service_details_base()
                details["reason"] = "No page snapshots are available for WebDX detection."
                _service_run(
                    connection, audit_id=audit_id, service_id=item.id, state_info=state_info,
                    state="NO_DATA", attempted=0, succeeded=0, details=details,
                )
                result["state"] = "NO_DATA"
                return result

            readable = [
                (row, _safe_artifact(
                    workspace,
                    str(row["rendered_artifact_ref"]) if row["rendered_artifact_ref"] else None,
                    str(row["raw_artifact_ref"]) if row["raw_artifact_ref"] else None,
                ))
                for row in rows
            ]
            if not any(artifact is not None for _, artifact in readable):
                details = _service_details_base()
                details["reason"] = "No re-openable HTML artifact is available for WebDX detection."
                _service_run(
                    connection, audit_id=audit_id, service_id=item.id, state_info=state_info,
                    state="NO_DATA", attempted=attempted, succeeded=0, details=details,
                )
                result["state"] = "NO_DATA"
                return result

            try:
                dataset, dataset_metadata = _resolve_dataset(
                    workspace, environment, read_url=read_url,
                )
            except Exception as exc:
                details = _service_details_base()
                details["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
                _service_run(
                    connection, audit_id=audit_id, service_id=item.id, state_info=state_info,
                    state="ERROR", attempted=attempted, succeeded=0, details=details,
                )
                result["state"] = "ERROR"
                result["error"] = details["error"]
                return result

            reverse = _compat_index(dataset)
            if not reverse:
                details = _service_details_base(dataset_metadata)
                details["error"] = "web-features dataset has no usable compat_features mappings"
                _service_run(
                    connection, audit_id=audit_id, service_id=item.id, state_info=state_info,
                    state="ERROR", attempted=attempted, succeeded=0, details=details,
                )
                result["state"] = "ERROR"
                result["error"] = details["error"]
                return result

            succeeded = 0
            total_features = 0
            snapshot_payloads: list[dict[str, Any]] = []
            for row, artifact in readable:
                snapshot_id = str(row["snapshot_id"])
                device = str(row["device"])
                target = str(row["normalized_url"])
                if artifact is None:
                    snapshot_payloads.append({
                        "snapshot_id": snapshot_id, "device": device, "target": target,
                        "state": "NO_ARTIFACT",
                    })
                    continue
                html, artifact_ref, truncated = artifact
                try:
                    signals, detector = detect_compat_features(html, reverse.keys())
                    feature_rows = _feature_observations(dataset, reverse, signals)
                except Exception as exc:
                    snapshot_payloads.append({
                        "snapshot_id": snapshot_id, "device": device, "target": target,
                        "state": "DETECTION_ERROR",
                        "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    })
                    continue
                succeeded += 1
                total_features += len(feature_rows)
                counts = {
                    "WIDELY_AVAILABLE": 0, "NEWLY_AVAILABLE": 0,
                    "LIMITED_AVAILABILITY": 0, "UNKNOWN": 0,
                }
                for feature_row in feature_rows:
                    counts[feature_row["classification"]] += 1
                    _record(
                        connection,
                        audit_id=audit_id,
                        metric_id=f"web_platform_feature::{feature_row['feature_id']}",
                        label=f"Web Feature · {feature_row['name']}",
                        scope="DEVICE_SNAPSHOT",
                        target=target,
                        device=device,
                        state=feature_row["classification"],
                        source="W3C WebDX web-features",
                        methodology=f"RASAi {CONTRACT_VERSION} deterministic source-to-BCD mapping",
                        relation_degree=item.relation_degree,
                        details={
                            **feature_row,
                            "snapshot_id": snapshot_id,
                            "artifact_reference": artifact_ref,
                            "artifact_truncated": truncated,
                            "dataset_version": dataset_metadata.get("version"),
                            "dataset_sha256": dataset_metadata.get("sha256"),
                        },
                    )
                for classification, metric_id, label in (
                    ("WIDELY_AVAILABLE", "web_platform_widely_available_count", "Web Features · Widely Available"),
                    ("NEWLY_AVAILABLE", "web_platform_newly_available_count", "Web Features · Newly Available"),
                    ("LIMITED_AVAILABILITY", "web_platform_limited_availability_count", "Web Features · Limited Availability"),
                    ("UNKNOWN", "web_platform_unknown_count", "Web Features · Baseline não classificável"),
                ):
                    _record(
                        connection,
                        audit_id=audit_id,
                        metric_id=metric_id,
                        label=label,
                        scope="DEVICE_SNAPSHOT",
                        target=target,
                        device=device,
                        state="MEASURED",
                        value=float(counts[classification]),
                        unit="feature_count",
                        source="W3C WebDX web-features",
                        methodology=f"RASAi {CONTRACT_VERSION} count over directly observed features",
                        relation_degree=item.relation_degree,
                        details={
                            "snapshot_id": snapshot_id,
                            "classification": classification,
                            "artifact_reference": artifact_ref,
                            "artifact_truncated": truncated,
                            "dataset_version": dataset_metadata.get("version"),
                            "dataset_sha256": dataset_metadata.get("sha256"),
                        },
                    )
                snapshot_payloads.append({
                    "snapshot_id": snapshot_id,
                    "device": device,
                    "target": target,
                    "state": "ANALYZED",
                    "artifact_reference": artifact_ref,
                    "artifact_truncated": truncated,
                    "detector": detector,
                    "feature_count": len(feature_rows),
                    "counts": counts,
                    "features": feature_rows,
                })

            observation_artifact = {
                "contract_version": CONTRACT_VERSION,
                "audit_id": audit_id,
                "dataset": dataset_metadata,
                "detector": _service_details_base(dataset_metadata),
                "snapshots": snapshot_payloads,
                "observed_at": _utc_now(),
            }
            _atomic_write(workspace.root / OBSERVATIONS_ARTIFACT, _json_bytes(observation_artifact))

            if succeeded == 0:
                final_state = "NO_DATA"
            elif succeeded < attempted:
                final_state = "PARTIAL"
            elif total_features == 0:
                final_state = "NO_DATA"
            else:
                final_state = "SUCCESS"
            details = _service_details_base(dataset_metadata)
            details.update({
                "attempted_snapshots": attempted,
                "analyzed_snapshots": succeeded,
                "detected_features": total_features,
                "observations_artifact": OBSERVATIONS_ARTIFACT.as_posix(),
            })
            if total_features == 0:
                details["reason"] = (
                    "No directly observable source signal mapped to a web-features compat_features key."
                )
            _service_run(
                connection, audit_id=audit_id, service_id=item.id, state_info=state_info,
                state=final_state, attempted=attempted, succeeded=succeeded, details=details,
            )
            result.update({
                "state": final_state,
                "succeeded": succeeded,
                "detected_features": total_features,
                "dataset_version": dataset_metadata.get("version"),
                "dataset_sha256": dataset_metadata.get("sha256"),
            })
            return result
    finally:
        connection.close()
