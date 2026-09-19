"""Shared passive-security analysis core for CAT-10 and Improvement Intelligence.

The module is deliberately passive. It consumes evidence already persisted by the
RASAi acquisition/browser pipeline and may query vulnerability-intelligence services
with normalized component/version identifiers. It never probes, fuzzes, submits forms,
tests credentials or sends attack payloads to the audited target.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from rasai.secret_safety import redact_url, redact_value

CONTRACT_VERSION = "PASSIVE-SECURITY-001"

ENABLED_ENV = "RASAI_PASSIVE_SECURITY"
HEADERS_ENV = "RASAI_SECURITY_HEADERS"
COOKIES_ENV = "RASAI_SECURITY_COOKIES"
RESOURCES_ENV = "RASAI_SECURITY_RESOURCES"
THIRD_PARTY_ENV = "RASAI_SECURITY_THIRD_PARTY"
RUNTIME_ENV = "RASAI_SECURITY_RUNTIME_CORRELATION"
OSV_ENV = "RASAI_SECURITY_OSV"
KEV_ENV = "RASAI_SECURITY_CISA_KEV"
EXTERNAL_TIMEOUT_ENV = "RASAI_SECURITY_EXTERNAL_TIMEOUT_SECONDS"

DEFAULT_OSV_ENDPOINT = "https://api.osv.dev/v1/query"
DEFAULT_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
DEFAULT_EXTERNAL_TIMEOUT_SECONDS = 15.0

FINDING_TYPES = frozenset({
    "OBSERVATION",
    "CONFIGURATION_WEAKNESS",
    "EXPOSURE",
    "POTENTIAL_VULNERABILITY",
    "KNOWN_VULNERABILITY",
    "THREAT_REPUTATION",
    "RUNTIME_FAILURE",
    "INFORMATION_DISCLOSURE",
})

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
KNOWN_NPM_LIBRARIES = {
    "jquery": "jquery",
    "react-dom": "react-dom",
    "react": "react",
    "vue": "vue",
    "angular": "angular",
    "lodash": "lodash",
    "bootstrap": "bootstrap",
    "moment": "moment",
    "axios": "axios",
    "backbone": "backbone",
    "underscore": "underscore",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS passive_security_runs (
    audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
    contract_version TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    status TEXT NOT NULL,
    pages_analyzed INTEGER NOT NULL DEFAULT 0,
    resources_count INTEGER NOT NULL DEFAULT 0,
    components_count INTEGER NOT NULL DEFAULT 0,
    findings_count INTEGER NOT NULL DEFAULT 0,
    remediations_count INTEGER NOT NULL DEFAULT 0,
    coverage_json TEXT NOT NULL DEFAULT '{}',
    limitations_json TEXT NOT NULL DEFAULT '[]',
    integration_states_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS passive_security_resources (
    resource_id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
    page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,
    snapshot_id TEXT,
    page_url TEXT NOT NULL,
    resource_url TEXT,
    resource_kind TEXT NOT NULL,
    party TEXT NOT NULL,
    protocol TEXT,
    domain TEXT,
    attributes_json TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_passive_security_resources_audit
    ON passive_security_resources(audit_id,resource_kind,party);
CREATE TABLE IF NOT EXISTS passive_security_components (
    component_id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
    resource_id TEXT NOT NULL REFERENCES passive_security_resources(resource_id) ON DELETE CASCADE,
    library TEXT NOT NULL,
    version TEXT,
    ecosystem TEXT,
    identification_method TEXT NOT NULL,
    confidence TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_passive_security_components_audit
    ON passive_security_components(audit_id,library,version);
CREATE TABLE IF NOT EXISTS passive_security_integrations (
    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
    integration_id TEXT NOT NULL,
    requested INTEGER NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    successes INTEGER NOT NULL DEFAULT 0,
    artifact_reference TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    error_type TEXT,
    error_message TEXT,
    observed_at TEXT NOT NULL,
    PRIMARY KEY(audit_id,integration_id)
);
CREATE TABLE IF NOT EXISTS passive_security_advisories (
    row_id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
    component_id TEXT NOT NULL REFERENCES passive_security_components(component_id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    advisory_id TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    severity_json TEXT NOT NULL,
    references_json TEXT NOT NULL,
    kev_state TEXT NOT NULL DEFAULT 'NOT_CHECKED',
    kev_details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_passive_security_advisories_audit
    ON passive_security_advisories(audit_id,source,advisory_id);
CREATE TABLE IF NOT EXISTS passive_security_findings (
    finding_id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
    page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,
    url_scope TEXT,
    category TEXT NOT NULL,
    finding_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence TEXT NOT NULL,
    source TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    party_context TEXT NOT NULL,
    origin_kind TEXT NOT NULL,
    impact TEXT NOT NULL,
    containment TEXT NOT NULL,
    remediation TEXT NOT NULL,
    validation TEXT NOT NULL,
    cwe TEXT,
    cve_json TEXT NOT NULL DEFAULT '[]',
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_passive_security_findings_audit
    ON passive_security_findings(audit_id,severity,finding_type,category);
CREATE TABLE IF NOT EXISTS passive_security_remediations (
    remediation_id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
    finding_id TEXT NOT NULL REFERENCES passive_security_findings(finding_id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    containment TEXT NOT NULL,
    correction TEXT NOT NULL,
    implementation_order TEXT NOT NULL,
    regression_risk TEXT NOT NULL,
    validation TEXT NOT NULL,
    advisory_only INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_passive_security_remediations_audit
    ON passive_security_remediations(audit_id,finding_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truthy(raw: Any, default: bool = False) -> bool:
    if raw in (None, ""):
        return default
    return str(raw).strip().casefold() in {"1", "true", "yes", "on", "sim", "s"}


def enabled(env: Mapping[str, str] | None = None) -> bool:
    environment = os.environ if env is None else env
    return _truthy(environment.get(ENABLED_ENV), False)


def external_timeout(env: Mapping[str, str] | None = None) -> float:
    environment = os.environ if env is None else env
    raw = str(environment.get(EXTERNAL_TIMEOUT_ENV) or DEFAULT_EXTERNAL_TIMEOUT_SECONDS).strip()
    value = float(raw)
    if value <= 0:
        raise ValueError(f"{EXTERNAL_TIMEOUT_ENV} deve ser > 0")
    return value


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_SCHEMA)


def _dump(value: Any) -> str:
    safe = redact_value(value)
    return json.dumps(safe, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _load(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list, tuple)):
        return raw
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _artifact_text(workspace: Any, reference: Any, *, limit: int = 5 * 1024 * 1024) -> str:
    if not reference:
        return ""
    root = Path(workspace.root).resolve()
    try:
        path = (root / str(reference)).resolve()
        path.relative_to(root)
    except (OSError, ValueError):
        return ""
    if not path.is_file():
        return ""
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _artifact_json(workspace: Any, stem: str, payload: Any) -> str:
    directory = Path(workspace.artifacts) / "security"
    directory.mkdir(parents=True, exist_ok=True)
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip("-")[:100] + ".json"
    path = directory / filename
    path.write_text(_dump(payload), encoding="utf-8", newline="\n")
    return Path("artifacts", "security", filename).as_posix()


def _stable(prefix: str, *parts: Any) -> str:
    raw = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}-{sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def _party(resource_url: str | None, page_url: str) -> str:
    if not resource_url:
        return "UNKNOWN"
    resolved = urljoin(page_url, resource_url)
    resource = urlsplit(resolved)
    page = urlsplit(page_url)
    if not resource.hostname:
        return "UNKNOWN"
    return "FIRST_PARTY" if resource.hostname.casefold() == (page.hostname or "").casefold() else "THIRD_PARTY"


def _resolved(resource_url: str | None, page_url: str) -> str | None:
    if not resource_url:
        return None
    try:
        return urljoin(page_url, resource_url)
    except ValueError:
        return resource_url


def _redact_urlish(value: Any) -> Any:
    """Redact credential-bearing URL material before CAT-10 persistence.

    Security analysis only needs scheme/host/path/query-key structure. Raw signed
    query values remain in the canonical source evidence and are not duplicated
    into the CAT-10 tables.
    """
    if isinstance(value, Mapping):
        return {str(key): _redact_urlish(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_redact_urlish(item) for item in value)
    if isinstance(value, list):
        return [_redact_urlish(item) for item in value]
    if isinstance(value, str):
        lowered=value.strip().casefold()
        if lowered.startswith(("http://","https://")):
            return redact_url(value)
    return value


class _PassiveHTMLParser(HTMLParser):
    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.items: list[dict[str, Any]] = []
        self.inputs: dict[int, list[dict[str, str]]] = defaultdict(list)
        self._form_stack: list[int] = []
        self.comments: list[str] = []
        self.generators: list[str] = []

    def handle_comment(self, data: str) -> None:
        text = " ".join(str(data).split())
        if text:
            self.comments.append(text[:500])

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        attrs = {str(k).casefold(): str(v or "") for k, v in attrs_list}
        if tag == "meta" and attrs.get("name", "").casefold() == "generator" and attrs.get("content"):
            self.generators.append(attrs["content"][:300])
        if tag == "script":
            self._add("SCRIPT", attrs.get("src"), attrs, inline=not bool(attrs.get("src")))
        elif tag == "link":
            rel = {item.casefold() for item in attrs.get("rel", "").split()}
            if "stylesheet" in rel or "preload" in rel or "modulepreload" in rel:
                self._add("STYLESHEET" if "stylesheet" in rel else "RESOURCE", attrs.get("href"), attrs)
        elif tag in {"img", "source", "video", "audio", "track"}:
            self._add(tag.upper(), attrs.get("src") or attrs.get("srcset"), attrs)
        elif tag == "iframe":
            self._add("IFRAME", attrs.get("src"), attrs)
        elif tag == "form":
            self._add("FORM", attrs.get("action") or self.page_url, attrs)
            self._form_stack.append(len(self.items) - 1)
        elif tag == "input" and self._form_stack:
            self.inputs[self._form_stack[-1]].append({
                "type": attrs.get("type", "text").casefold(),
                "name": attrs.get("name", "")[:120],
                "autocomplete": attrs.get("autocomplete", "")[:120],
            })

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "form" and self._form_stack:
            self._form_stack.pop()

    def _add(self, kind: str, url: str | None, attrs: Mapping[str, str], *, inline: bool = False) -> None:
        safe_attrs = {
            key: value
            for key, value in attrs.items()
            if key in {
                "type", "async", "defer", "integrity", "crossorigin", "sandbox", "allow",
                "method", "autocomplete", "rel", "referrerpolicy", "src", "href", "action", "nonce",
            }
        }
        nonce = safe_attrs.pop("nonce", "")
        if nonce:
            safe_attrs["nonce_sha256"] = sha256(nonce.encode("utf-8")).hexdigest()
            safe_attrs["nonce_length"] = len(nonce)
        for url_attribute in ("src","href","action"):
            if safe_attrs.get(url_attribute):
                safe_attrs[url_attribute] = _redact_urlish(
                    _resolved(safe_attrs[url_attribute], self.page_url)
                )
        self.items.append({
            "kind": kind,
            "url": _resolved(url, self.page_url),
            "party": "INLINE" if inline else _party(url, self.page_url),
            "attributes": safe_attrs,
            "inline": inline,
        })


def _page_rows(connection: sqlite3.Connection, audit_id: str) -> list[sqlite3.Row]:
    if not (_table_exists(connection, "pages") and _table_exists(connection, "page_snapshots")):
        return []
    return list(connection.execute(
        """SELECT p.page_id,p.normalized_url,ps.snapshot_id,ps.requested_url,ps.final_url,
                  ps.device,ps.rendered_artifact_ref,ps.raw_artifact_ref,ps.browser_metadata
           FROM pages p
           LEFT JOIN page_snapshots ps ON ps.page_id=p.page_id
           WHERE p.audit_id=?
           ORDER BY p.rowid,CASE ps.device WHEN 'MOBILE' THEN 0 WHEN 'DESKTOP' THEN 1 ELSE 2 END,ps.rowid""",
        (audit_id,),
    ))


def _headers_for_page(connection: sqlite3.Connection, audit_id: str, page_id: str) -> tuple[dict[str, list[str]], list[str]]:
    headers: dict[str, list[str]] = defaultdict(list)
    evidence_ids: list[str] = []
    if not _table_exists(connection, "evidence"):
        return {}, []
    rows = connection.execute(
        """SELECT evidence_id,observed_value FROM evidence
           WHERE audit_id=? AND page_id=? AND evidence_type='HTTP_HEADER'
           ORDER BY captured_at,rowid""",
        (audit_id, page_id),
    ).fetchall()
    for row in rows:
        payload = _load(row["observed_value"], {})
        if isinstance(payload, Mapping):
            for pair in payload.get("headers", ()) or ():
                if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                    headers[str(pair[0]).casefold()].append(str(pair[1]))
        evidence_ids.append(str(row["evidence_id"]))
    return dict(headers), evidence_ids


def _http_response_for_page(connection: sqlite3.Connection, audit_id: str, page_id: str) -> tuple[dict[str, Any], list[str]]:
    if not _table_exists(connection, "evidence"):
        return {}, []
    rows = connection.execute(
        """SELECT evidence_id,observed_value FROM evidence
           WHERE audit_id=? AND page_id=? AND evidence_type='HTTP_RESPONSE'
           ORDER BY captured_at,rowid""",
        (audit_id, page_id),
    ).fetchall()
    observed: dict[str, Any] = {}
    ids: list[str] = []
    for row in rows:
        payload = _load(row["observed_value"], {})
        if isinstance(payload, Mapping):
            observed = dict(payload)
        ids.append(str(row["evidence_id"]))
    return observed, ids


def _component_from_url(url: str | None) -> tuple[str, str, str, str] | None:
    if not url:
        return None
    name = Path(urlsplit(url).path).name.casefold()
    for token, package in KNOWN_NPM_LIBRARIES.items():
        if token not in name:
            continue
        pattern = rf"(?:^|[-_.]){re.escape(token)}(?:[-_.]?(?:min|prod))?[-_.]?v?(\d+\.\d+(?:\.\d+)?(?:[-+][0-9a-z.-]+)?)"
        match = re.search(pattern, name, re.IGNORECASE)
        if not match:
            match = re.search(r"[-_.]v?(\d+\.\d+(?:\.\d+)?(?:[-+][0-9a-z.-]+)?)", name, re.IGNORECASE)
        if match:
            return package, match.group(1), "npm", "MEDIUM"
        return package, "", "npm", "LOW"
    return None


def _resource_inventory(connection: sqlite3.Connection, workspace: Any, audit_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    resources: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    page_context: dict[str, dict[str, Any]] = {}
    seen_snapshots: set[str] = set()
    for row in _page_rows(connection, audit_id):
        page_id = str(row["page_id"])
        raw_page_url = str(row["final_url"] or row["requested_url"] or row["normalized_url"] or "")
        page_url = str(_redact_urlish(raw_page_url) or "")
        snapshot_id = str(row["snapshot_id"] or "")
        headers, header_evidence = _headers_for_page(connection, audit_id, page_id)
        http, http_evidence = _http_response_for_page(connection, audit_id, page_id)
        page_context.setdefault(page_id, {
            "page_id": page_id,
            "page_url": page_url,
            "headers": headers,
            "header_evidence": header_evidence,
            "http": _redact_urlish(http),
            "http_evidence": http_evidence,
            "runtime": [],
        })
        if snapshot_id:
            meta = _load(row["browser_metadata"], {})
            runtime = meta.get("runtime_diagnostics", {}) if isinstance(meta, Mapping) else {}
            items = runtime.get("items", ()) if isinstance(runtime, Mapping) else ()
            page_context[page_id]["runtime"].extend(
                dict(item) for item in items if isinstance(item, Mapping)
            )
        if not snapshot_id or snapshot_id in seen_snapshots:
            continue
        seen_snapshots.add(snapshot_id)
        html = _artifact_text(workspace, row["rendered_artifact_ref"] or row["raw_artifact_ref"])
        if not html:
            continue
        parser = _PassiveHTMLParser(raw_page_url)
        try:
            parser.feed(html)
        except Exception:
            pass
        page_context[page_id]["generators"] = parser.generators
        page_context[page_id]["comments"] = parser.comments
        for index, item in enumerate(parser.items):
            attrs = dict(item["attributes"])
            if item["kind"] == "FORM":
                attrs["sensitive_fields"] = [
                    entry["type"]
                    for entry in parser.inputs.get(index, ())
                    if entry.get("type") in {"password", "email", "tel", "number"}
                ]
            resolved = item.get("url")
            safe_resolved = _redact_urlish(resolved)
            parsed = urlsplit(resolved or "") if resolved else None
            resource_id = _stable("PSR", audit_id, snapshot_id, item["kind"], index, resolved)
            resource = {
                "resource_id": resource_id,
                "audit_id": audit_id,
                "page_id": page_id,
                "snapshot_id": snapshot_id,
                "page_url": page_url,
                "resource_url": safe_resolved,
                "resource_kind": item["kind"],
                "party": item["party"],
                "protocol": parsed.scheme.casefold() if parsed else "",
                "domain": parsed.hostname.casefold() if parsed and parsed.hostname else "",
                "attributes": attrs,
                "evidence_ids": [snapshot_id, *header_evidence],
            }
            resources.append(resource)
            if item["kind"] == "SCRIPT" and resolved:
                detected = _component_from_url(resolved)
                if detected:
                    library, version, ecosystem, confidence = detected
                    components.append({
                        "component_id": _stable("PSC", audit_id, resource_id, library, version),
                        "resource_id": resource_id,
                        "library": library,
                        "version": version or None,
                        "ecosystem": ecosystem,
                        "identification_method": "filename",
                        "confidence": confidence,
                        "evidence_ids": [resource_id],
                    })
    return resources, components, page_context


def _persist_inventory(
    connection: sqlite3.Connection,
    audit_id: str,
    resources: Iterable[Mapping[str, Any]],
    components: Iterable[Mapping[str, Any]],
    *,
    preserve_advisories: bool = False,
) -> None:
    resource_rows = tuple(resources)
    component_rows = tuple(components)
    advisories: tuple[dict[str, Any], ...] = ()
    if preserve_advisories and _table_exists(connection, "passive_security_advisories"):
        advisories = tuple(
            dict(row)
            for row in connection.execute(
                "SELECT * FROM passive_security_advisories WHERE audit_id=?",
                (audit_id,),
            ).fetchall()
        )
    connection.execute("DELETE FROM passive_security_advisories WHERE audit_id=?", (audit_id,))
    connection.execute("DELETE FROM passive_security_components WHERE audit_id=?", (audit_id,))
    connection.execute("DELETE FROM passive_security_resources WHERE audit_id=?", (audit_id,))
    connection.executemany(
        """INSERT INTO passive_security_resources
           (resource_id,audit_id,page_id,snapshot_id,page_url,resource_url,resource_kind,party,protocol,domain,attributes_json,evidence_ids_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(
            item["resource_id"], audit_id, item.get("page_id"), item.get("snapshot_id"),
            item.get("page_url") or "", item.get("resource_url"), item["resource_kind"],
            item["party"], item.get("protocol") or "", item.get("domain") or "",
            _dump(item.get("attributes") or {}), _dump(item.get("evidence_ids") or []),
        ) for item in resource_rows],
    )
    connection.executemany(
        """INSERT INTO passive_security_components
           (component_id,audit_id,resource_id,library,version,ecosystem,identification_method,confidence,evidence_ids_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        [(
            item["component_id"], audit_id, item["resource_id"], item["library"],
            item.get("version"), item.get("ecosystem"), item["identification_method"],
            item["confidence"], _dump(item.get("evidence_ids") or []),
        ) for item in component_rows],
    )
    if advisories:
        valid_components = {str(item["component_id"]) for item in component_rows}
        preserved = [row for row in advisories if str(row.get("component_id") or "") in valid_components]
        connection.executemany(
            """INSERT INTO passive_security_advisories
               (row_id,audit_id,component_id,source,advisory_id,aliases_json,severity_json,references_json,kev_state,kev_details_json)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    row["row_id"], row["audit_id"], row["component_id"], row["source"],
                    row["advisory_id"], row["aliases_json"], row["severity_json"],
                    row["references_json"], row["kev_state"], row["kev_details_json"],
                )
                for row in preserved
            ],
        )


def _http_json(url: str, *, timeout: float, body: Mapping[str, Any] | None = None) -> Any:
    encoded = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = {"Accept": "application/json", "User-Agent": "RASAi-Passive-Security/1"}
    if encoded is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=encoded, headers=headers, method="POST" if encoded is not None else "GET")
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError("EXTERNAL_RESPONSE_TOO_LARGE")
        return json.loads(raw.decode("utf-8", errors="strict"))


def _integration_row(connection: sqlite3.Connection, *, audit_id: str, integration_id: str, requested: bool, state: str, attempts: int = 0, successes: int = 0, artifact_reference: str | None = None, details: Mapping[str, Any] | None = None, error: Exception | None = None) -> None:
    connection.execute(
        """INSERT INTO passive_security_integrations
           (audit_id,integration_id,requested,state,attempts,successes,artifact_reference,details_json,error_type,error_message,observed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(audit_id,integration_id) DO UPDATE SET
             requested=excluded.requested,state=excluded.state,attempts=excluded.attempts,
             successes=excluded.successes,artifact_reference=excluded.artifact_reference,
             details_json=excluded.details_json,error_type=excluded.error_type,
             error_message=excluded.error_message,observed_at=excluded.observed_at""",
        (
            audit_id, integration_id, 1 if requested else 0, state, attempts, successes,
            artifact_reference, _dump(details or {}),
            type(error).__name__ if error else None,
            str(error)[:500] if error else None,
            _now(),
        ),
    )


def collect_external_intelligence(*, audit_id: str, workspace: Any, source_blocked: bool = False) -> dict[str, Any]:
    """Collect OSV/KEV only from normalized persisted component evidence.

    This function never contacts the audited target. The source_blocked value is recorded
    but does not block package/CVE intelligence because those calls contain no target URL.
    """
    environment = os.environ
    if not enabled(environment):
        return {"collection_state": "DISABLED", "reason": "PASSIVE_SECURITY_NOT_SELECTED"}
    timeout = external_timeout(environment)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            ensure_schema(connection)
            resources, components, _ = _resource_inventory(connection, workspace, audit_id)
            _persist_inventory(connection, audit_id, resources, components)

        osv_requested = _truthy(environment.get(OSV_ENV), True)
        kev_requested = _truthy(environment.get(KEV_ENV), True)
        osv_successes = 0
        osv_attempts = 0
        cves: set[str] = set()
        last_artifact: str | None = None

        if not osv_requested:
            with connection:
                _integration_row(connection, audit_id=audit_id, integration_id="OSV", requested=False, state="DISABLED")
        else:
            queryable = [
                item for item in components
                if item.get("version") and item.get("ecosystem") and item.get("confidence") in {"HIGH", "MEDIUM"}
            ]
            if not queryable:
                with connection:
                    _integration_row(
                        connection, audit_id=audit_id, integration_id="OSV", requested=True,
                        state="NO_DATA", details={"reason": "NO_VERSIONED_COMPONENT_IDENTIFIED"},
                    )
            else:
                last_error: Exception | None = None
                for component in queryable:
                    osv_attempts += 1
                    logical = {
                        "package": {"name": component["library"], "ecosystem": component["ecosystem"]},
                        "version": component["version"],
                    }
                    try:
                        payload = _http_json(DEFAULT_OSV_ENDPOINT, timeout=timeout, body=logical)
                        last_artifact = _artifact_json(
                            workspace,
                            f"osv-{component['library']}-{component['version']}-{component['component_id']}",
                            {"logical_request": logical, "response": payload},
                        )
                        osv_successes += 1
                        vulns = payload.get("vulns", ()) if isinstance(payload, Mapping) else ()
                        with connection:
                            for vuln in vulns or ():
                                if not isinstance(vuln, Mapping):
                                    continue
                                aliases = [str(v) for v in vuln.get("aliases", ()) or () if str(v)]
                                cves.update(alias.upper() for alias in aliases if re.fullmatch(r"CVE-\d{4}-\d+", alias, re.I))
                                severity = vuln.get("severity", ()) or ()
                                if not severity:
                                    for affected in vuln.get("affected", ()) or ():
                                        if isinstance(affected, Mapping):
                                            candidate = affected.get("ecosystem_specific", {})
                                            if isinstance(candidate, Mapping) and candidate.get("severity"):
                                                severity = [{"type": "ECOSYSTEM", "score": candidate.get("severity")}]
                                                break
                                refs = [
                                    ref.get("url") for ref in vuln.get("references", ()) or ()
                                    if isinstance(ref, Mapping) and ref.get("url")
                                ]
                                row_id = _stable("PSA", audit_id, component["component_id"], vuln.get("id"))
                                connection.execute(
                                    """INSERT OR REPLACE INTO passive_security_advisories
                                       (row_id,audit_id,component_id,source,advisory_id,aliases_json,severity_json,references_json,kev_state,kev_details_json)
                                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                    (
                                        row_id, audit_id, component["component_id"], "OSV",
                                        str(vuln.get("id") or row_id), _dump(aliases), _dump(severity),
                                        _dump(refs), "NOT_CHECKED", "{}",
                                    ),
                                )
                    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                        last_error = exc
                state = "COMPLETED" if osv_successes == osv_attempts else "PARTIAL" if osv_successes else "UNAVAILABLE"
                with connection:
                    _integration_row(
                        connection, audit_id=audit_id, integration_id="OSV", requested=True,
                        state=state, attempts=osv_attempts, successes=osv_successes,
                        artifact_reference=last_artifact,
                        details={"queryable_components": len(queryable), "source_blocked": source_blocked},
                        error=last_error,
                    )

        if not kev_requested:
            with connection:
                _integration_row(connection, audit_id=audit_id, integration_id="CISA_KEV", requested=False, state="DISABLED")
        elif not cves:
            with connection:
                _integration_row(
                    connection, audit_id=audit_id, integration_id="CISA_KEV", requested=True,
                    state="NO_DATA", details={"reason": "NO_CVE_FROM_OSV"},
                )
        else:
            try:
                payload = _http_json(DEFAULT_KEV_URL, timeout=timeout)
                artifact = _artifact_json(workspace, "cisa-kev", payload)
                entries = payload.get("vulnerabilities", ()) if isinstance(payload, Mapping) else ()
                by_cve = {
                    str(item.get("cveID") or "").upper(): dict(item)
                    for item in entries or () if isinstance(item, Mapping) and item.get("cveID")
                }
                matched = {cve.upper(): by_cve[cve.upper()] for cve in cves if cve.upper() in by_cve}
                with connection:
                    advisory_rows = connection.execute(
                        "SELECT row_id,aliases_json FROM passive_security_advisories WHERE audit_id=?",
                        (audit_id,),
                    ).fetchall()
                    for row in advisory_rows:
                        aliases = _load(row["aliases_json"], [])
                        matches = [matched[str(alias).upper()] for alias in aliases if str(alias).upper() in matched]
                        connection.execute(
                            "UPDATE passive_security_advisories SET kev_state=?,kev_details_json=? WHERE row_id=?",
                            ("MATCHED" if matches else "NOT_MATCHED", _dump(matches), row["row_id"]),
                        )
                    _integration_row(
                        connection, audit_id=audit_id, integration_id="CISA_KEV", requested=True,
                        state="COMPLETED", attempts=1, successes=1, artifact_reference=artifact,
                        details={"cves_checked": len(cves), "matched": len(matched)},
                    )
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                with connection:
                    _integration_row(
                        connection, audit_id=audit_id, integration_id="CISA_KEV", requested=True,
                        state="UNAVAILABLE", attempts=1, successes=0,
                        details={"cves_checked": len(cves)}, error=exc,
                    )

        with connection:
            if _table_exists(connection, "standards_service_runs"):
                row = connection.execute(
                    "SELECT * FROM standards_service_runs WHERE audit_id=? AND service_id='mdn-observatory' ORDER BY rowid DESC LIMIT 1",
                    (audit_id,),
                ).fetchone()
            else:
                row = None
            if row is None:
                _integration_row(connection, audit_id=audit_id, integration_id="MDN_OBSERVATORY", requested=False, state="NOT_REQUESTED")
            else:
                _integration_row(
                    connection, audit_id=audit_id, integration_id="MDN_OBSERVATORY",
                    requested=bool(row["requested"]), state=str(row["state"] or "NO_DATA").upper(),
                    attempts=int(row["targets_attempted"] or 0), successes=int(row["targets_succeeded"] or 0),
                    details={"reused_from": "standards_service_runs"},
                )
            _integration_row(connection, audit_id=audit_id, integration_id="TLS_EXTERNAL", requested=False, state="NOT_REQUESTED", details={"reason": "OPTIONAL_DEEP_TLS_NOT_ENABLED_IN_INITIAL_SCOPE"})
            _integration_row(connection, audit_id=audit_id, integration_id="THREAT_REPUTATION", requested=False, state="NOT_REQUESTED", details={"reason": "URL_REPUTATION_REQUIRES_EXPLICIT_PRIVACY_AND_PROVIDER_POLICY"})
        return {
            "collection_state": (
                "SUCCESS"
                if (not osv_requested or osv_successes or not [
                    item for item in components
                    if item.get("version") and item.get("ecosystem") and item.get("confidence") in {"HIGH", "MEDIUM"}
                ])
                else "PARTIAL"
            ),
            "components": len(components),
            "osv_attempts": osv_attempts,
            "osv_successes": osv_successes,
            "cves": len(cves),
        }
    finally:
        connection.close()


def _finding(
    *,
    audit_id: str,
    page_id: str | None,
    url: str | None,
    code: str,
    category: str,
    finding_type: str,
    title: str,
    description: str,
    severity: str,
    confidence: str = "HIGH",
    source: str = "RASAI Passive Security Analyzer",
    evidence_ids: Iterable[str] = (),
    party: str = "FIRST_PARTY",
    origin: str = "DETERMINISTIC",
    impact: str,
    containment: str,
    remediation: str,
    validation: str,
    cwe: str | None = None,
    cves: Iterable[str] = (),
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if finding_type not in FINDING_TYPES:
        raise ValueError(f"finding_type inválido: {finding_type}")
    return {
        "finding_id": _stable("SEC", audit_id, page_id, code, title),
        "audit_id": audit_id,
        "page_id": page_id,
        "url_scope": url,
        "category": category,
        "finding_type": finding_type,
        "title": title,
        "description": description,
        "severity": severity,
        "confidence": confidence,
        "source": source,
        "evidence_ids": list(dict.fromkeys(str(v) for v in evidence_ids if str(v))),
        "party_context": party,
        "origin_kind": origin,
        "impact": impact,
        "containment": containment,
        "remediation": remediation,
        "validation": validation,
        "cwe": cwe,
        "cves": list(dict.fromkeys(str(v).upper() for v in cves if str(v))),
        "details": dict(details or {}),
    }


def _parse_csp(values: Iterable[str]) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for policy in values:
        for raw in str(policy).split(";"):
            parts = raw.strip().split()
            if parts:
                directives.setdefault(parts[0].casefold(), []).extend(parts[1:])
    return directives


def _safe_csp_sources(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        raw = str(value)
        lowered = raw.casefold().strip("'")
        if lowered.startswith("nonce-"):
            out.append("'nonce-[REDACTED]'")
        elif re.match(r"^sha(?:256|384|512)-", lowered):
            algorithm = lowered.split("-", 1)[0]
            out.append(f"'{algorithm}-[HASH]'")
        else:
            out.append(raw)
    return out


def _cookie_attributes(raw: str) -> dict[str, Any]:
    parts = [part.strip() for part in str(raw).split(";") if part.strip()]
    cookie_name = parts[0].split("=", 1)[0].strip() if parts else ""
    attrs: dict[str, Any] = {
        "name_hash": sha256(cookie_name.encode("utf-8")).hexdigest()[:12] if cookie_name else "",
        "sensitive_name_hint": bool(re.search(r"(?:session|sess|auth|token|jwt|sid|login|credential)", cookie_name, re.I)),
        "secure": False,
        "httponly": False,
        "samesite": None,
        "domain": None,
        "path": None,
    }
    for part in parts[1:]:
        key, _, value = part.partition("=")
        lower = key.strip().casefold()
        if lower == "secure":
            attrs["secure"] = True
        elif lower == "httponly":
            attrs["httponly"] = True
        elif lower == "samesite":
            attrs["samesite"] = value.strip()
        elif lower == "domain":
            attrs["domain"] = value.strip()
        elif lower == "path":
            attrs["path"] = value.strip()
    return attrs


def _analyze_headers(audit_id: str, page: Mapping[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    url = str(page["page_url"])
    page_id = str(page["page_id"])
    headers = page.get("headers") or {}
    ev = page.get("header_evidence") or page.get("http_evidence") or []
    scheme = urlsplit(url).scheme.casefold()
    http = page.get("http") or {}
    requested = str(http.get("requested_url") or "")
    final = str(http.get("final_url") or url)
    chain = http.get("redirect_chain") or []

    if scheme != "https":
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="HTTPS",category="Transport",
            finding_type="CONFIGURATION_WEAKNESS",title="URL final não utiliza HTTPS",
            description=f"Esquema final observado: {scheme or 'desconhecido'}.",
            severity="HIGH",evidence_ids=ev,impact="Transporte sem proteção HTTPS para esta URL observada.",
            containment="Evitar exposição de dados sensíveis nesta rota enquanto HTTPS não estiver ativo.",
            remediation="Publicar a rota em HTTPS e redirecionar HTTP para HTTPS sem downgrade.",
            validation="Reexecutar a auditoria e confirmar URL final HTTPS e cadeia de redirects sem downgrade.",
        ))
    if requested.casefold().startswith("https://") and final.casefold().startswith("http://"):
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="HTTPS_DOWNGRADE",category="Transport",
            finding_type="CONFIGURATION_WEAKNESS",title="Redirect HTTPS para HTTP observado",
            description="A cadeia persistida termina em HTTP após uma URL inicialmente HTTPS.",
            severity="HIGH",evidence_ids=ev,impact="Downgrade de transporte reduz as garantias de confidencialidade e integridade.",
            containment="Remover o redirect de downgrade ou bloquear a rota até correção.",
            remediation="Manter todos os hops e o destino final em HTTPS.",
            validation="Validar a cadeia de redirects persistida após nova auditoria.",
            details={"redirect_chain": chain},
        ))

    if scheme == "https" and "strict-transport-security" not in headers:
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="HSTS",category="HTTP Security",
            finding_type="CONFIGURATION_WEAKNESS",title="Strict-Transport-Security não observado",
            description="A resposta HTTPS persistida não contém HSTS. A ausência é postura defensiva, não prova exploração.",
            severity="MEDIUM",evidence_ids=ev,impact="Navegadores não recebem desta resposta uma política explícita de transporte estrito.",
            containment="Preservar HTTPS e evitar redirects para HTTP.",
            remediation="Avaliar e configurar Strict-Transport-Security com parâmetros compatíveis com o domínio.",
            validation="Revalidar o header na resposta HTTPS e confirmar comportamento de subdomínios antes de includeSubDomains/preload.",
        ))
    elif any(re.search(r"(?:^|;)\s*max-age\s*=\s*0(?:\s*;|$)", value, re.I) for value in headers.get("strict-transport-security", ())):
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="HSTS_ZERO",category="HTTP Security",
            finding_type="CONFIGURATION_WEAKNESS",title="HSTS observado com max-age=0",
            description="A política HSTS persistida instrui o navegador a remover/desativar o estado HSTS.",
            severity="MEDIUM",evidence_ids=ev,impact="A proteção de transporte estrito fica desativada após o processamento desta política.",
            containment="Manter todos os acessos HTTPS enquanto a política é corrigida.",
            remediation="Definir max-age positivo compatível com a estratégia de implantação; revisar subdomínios antes de ampliar escopo.",
            validation="Revalidar o header e a cadeia de redirects.",
        ))

    csp_values = headers.get("content-security-policy", ())
    if not csp_values:
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="CSP",category="Browser Security",
            finding_type="CONFIGURATION_WEAKNESS",title="Content-Security-Policy não observada",
            description="Nenhum header Content-Security-Policy foi observado na resposta persistida.",
            severity="MEDIUM",evidence_ids=ev,impact="O navegador não recebe desta resposta uma política CSP para restringir origens e execução de conteúdo.",
            containment="Reduzir dependências de scripts inline/terceiros e revisar origens permitidas.",
            remediation="Definir CSP incrementalmente, preferindo diretivas explícitas e nonces/hashes quando aplicável.",
            validation="Executar em Report-Only quando necessário, revisar violações e reauditar a política final.",
        ))
        csp = {}
    else:
        csp = _parse_csp(csp_values)
        effective_script = csp.get("script-src", csp.get("default-src", []))
        if "'unsafe-eval'" in effective_script:
            findings.append(_finding(
                audit_id=audit_id,page_id=page_id,url=url,code="CSP_UNSAFE_EVAL",category="Browser Security",
                finding_type="CONFIGURATION_WEAKNESS",title="CSP permite 'unsafe-eval'",
                description="A diretiva efetiva de script contém 'unsafe-eval'.",
                severity="MEDIUM",evidence_ids=ev,impact="A política permite formas de avaliação dinâmica de código que reduzem a contenção oferecida pela CSP.",
                containment="Mapear dependências que exigem avaliação dinâmica antes da remoção.",
                remediation="Remover 'unsafe-eval' após eliminar dependências incompatíveis.",
                validation="Executar testes funcionais e confirmar a ausência de violações CSP necessárias ao produto.",
                details={"script_sources": _safe_csp_sources(effective_script)},
            ))
        if "*" in effective_script:
            findings.append(_finding(
                audit_id=audit_id,page_id=page_id,url=url,code="CSP_SCRIPT_WILDCARD",category="Browser Security",
                finding_type="CONFIGURATION_WEAKNESS",title="CSP permite wildcard em origem de scripts",
                description="A diretiva efetiva de script contém '*'.",
                severity="MEDIUM",evidence_ids=ev,impact="O escopo de origens autorizadas para script fica excessivamente amplo.",
                containment="Inventariar as origens efetivamente necessárias.",
                remediation="Substituir wildcard por origens explícitas e minimizar a allowlist.",
                validation="Reauditar CSP e verificar recursos observados contra a allowlist.",
            ))
        if "data:" in effective_script:
            findings.append(_finding(
                audit_id=audit_id,page_id=page_id,url=url,code="CSP_SCRIPT_DATA",category="Browser Security",
                finding_type="CONFIGURATION_WEAKNESS",title="CSP permite data: como origem de script",
                description="A diretiva efetiva de script contém data:, ampliando os formatos de conteúdo executável aceitos pela política.",
                severity="MEDIUM",evidence_ids=ev,impact="A origem data: pode reduzir a contenção de scripts quando combinada com conteúdo controlável.",
                containment="Revisar dependências que exigem data: antes de alterar a política.",
                remediation="Remover data: de script-src quando não for estritamente necessário.",
                validation="Validar em CSP Report-Only e reexecutar testes funcionais antes do enforcement.",
                details={"script_sources": _safe_csp_sources(effective_script)},
            ))
        if "'unsafe-inline'" in effective_script:
            findings.append(_finding(
                audit_id=audit_id,page_id=page_id,url=url,code="CSP_UNSAFE_INLINE",category="Browser Security",
                finding_type="CONFIGURATION_WEAKNESS",title="CSP contém 'unsafe-inline' para scripts",
                description="A política contém 'unsafe-inline'. Em políticas com nonce/hash a efetividade depende do navegador e das demais fontes; o finding não presume exploração.",
                severity="LOW",evidence_ids=ev,impact="Pode reduzir a proteção contra execução de script inline conforme a política efetiva.",
                containment="Verificar se nonces/hashes já cobrem scripts inline legítimos.",
                remediation="Migrar scripts inline necessários para nonce/hash e remover 'unsafe-inline' quando compatível.",
                validation="Validar em CSP Report-Only/testes antes de endurecer a política.",
            ))
        if "object-src" not in csp:
            findings.append(_finding(
                audit_id=audit_id,page_id=page_id,url=url,code="CSP_OBJECT_SRC",category="Browser Security",
                finding_type="OBSERVATION",title="CSP não declara object-src explicitamente",
                description="A política não possui diretiva object-src explícita; a efetividade depende do fallback para default-src.",
                severity="INFO",evidence_ids=ev,impact="Menor explicitude na restrição de conteúdo de plugin/objeto.",
                containment="Revisar o fallback atual antes de alterar.",
                remediation="Avaliar object-src 'none' quando objetos/plugins não forem necessários.",
                validation="Revalidar a política e funcionalidades dependentes.",
            ))
        if "base-uri" not in csp:
            findings.append(_finding(
                audit_id=audit_id,page_id=page_id,url=url,code="CSP_BASE_URI",category="Browser Security",
                finding_type="OBSERVATION",title="CSP não declara base-uri explicitamente",
                description="A política não possui base-uri explícita. A ausência não comprova exploração; indica oportunidade de restringir alteração da URL base do documento.",
                severity="INFO",evidence_ids=ev,impact="Uma política base-uri explícita pode reduzir superfícies associadas ao elemento base quando ele não é necessário.",
                containment="Confirmar se a aplicação utiliza <base> legitimamente.",
                remediation="Avaliar base-uri 'none' ou uma origem explicitamente necessária.",
                validation="Testar navegação/resolução de URLs relativas e reauditar a CSP.",
            ))

    has_frame_ancestors = "frame-ancestors" in csp
    if "x-frame-options" not in headers and not has_frame_ancestors:
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="FRAME_ANCESTORS",category="Browser Security",
            finding_type="CONFIGURATION_WEAKNESS",title="Proteção explícita contra framing não observada",
            description="Não foi observado X-Frame-Options nem CSP frame-ancestors.",
            severity="MEDIUM",evidence_ids=ev,impact="A resposta não declara restrição explícita de embedding em frames.",
            containment="Evitar fluxos sensíveis em páginas que possam ser embutidas até revisar a necessidade.",
            remediation="Definir CSP frame-ancestors e, quando necessário para compatibilidade, X-Frame-Options.",
            validation="Testar embeddings legítimos e reauditar headers.",
            cwe="CWE-1021",
        ))
    if "x-content-type-options" not in headers:
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="NOSNIFF",category="HTTP Security",
            finding_type="CONFIGURATION_WEAKNESS",title="X-Content-Type-Options não observado",
            description="O header X-Content-Type-Options não consta na resposta persistida.",
            severity="LOW",evidence_ids=ev,impact="O navegador não recebe a diretiva nosniff nesta resposta.",
            containment="Garantir Content-Type correto em recursos servidos.",
            remediation="Configurar X-Content-Type-Options: nosniff.",
            validation="Reauditar e verificar os Content-Types dos recursos.",
        ))
    elif not any(value.strip().casefold() == "nosniff" for value in headers.get("x-content-type-options", ())):
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="NOSNIFF_VALUE",category="HTTP Security",
            finding_type="CONFIGURATION_WEAKNESS",title="X-Content-Type-Options possui valor não reconhecido como nosniff",
            description="O header existe, mas o valor observado não é 'nosniff'.",
            severity="LOW",evidence_ids=ev,impact="A política pretendida pode não ser aplicada pelo navegador.",
            containment="Manter tipos MIME corretos.",
            remediation="Usar exatamente X-Content-Type-Options: nosniff.",
            validation="Reauditar o valor efetivo.",
        ))
    if "referrer-policy" not in headers:
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="REFERRER_POLICY",category="Privacy / Browser",
            finding_type="CONFIGURATION_WEAKNESS",title="Referrer-Policy não observada",
            description="A resposta não declara política explícita de referrer.",
            severity="LOW",evidence_ids=ev,impact="O comportamento depende do default do navegador e do contexto da navegação.",
            containment="Evitar dados sensíveis em URLs.",
            remediation="Definir uma Referrer-Policy compatível com analytics e requisitos de privacidade.",
            validation="Testar navegação/analytics e reauditar o header.",
        ))
    elif any(value.strip().casefold() == "unsafe-url" for value in headers.get("referrer-policy", ())):
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="REFERRER_UNSAFE_URL",category="Privacy / Browser",
            finding_type="EXPOSURE",title="Referrer-Policy usa unsafe-url",
            description="A política observada usa unsafe-url.",
            severity="MEDIUM",evidence_ids=ev,impact="URLs completas podem ser encaminhadas como referrer em contextos onde isso seja permitido.",
            containment="Remover segredos e dados pessoais de query strings.",
            remediation="Avaliar política mais restritiva compatível com o produto.",
            validation="Testar integrações e reauditar.",
        ))
    if "permissions-policy" not in headers:
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="PERMISSIONS_POLICY",category="Browser Security",
            finding_type="OBSERVATION",title="Permissions-Policy não observada",
            description="Não há Permissions-Policy explícita nesta resposta. A ausência não é, isoladamente, uma vulnerabilidade.",
            severity="INFO",evidence_ids=ev,impact="Recursos de navegador não são restringidos por uma política explícita desta resposta.",
            containment="Inventariar APIs de navegador realmente necessárias.",
            remediation="Definir restrições somente para capacidades relevantes ao produto.",
            validation="Testar funcionalidades que usam APIs controladas pela política.",
        ))
    for header, label in (
        ("cross-origin-opener-policy", "COOP"),
        ("cross-origin-embedder-policy", "COEP"),
        ("cross-origin-resource-policy", "CORP"),
    ):
        if header not in headers:
            findings.append(_finding(
                audit_id=audit_id,page_id=page_id,url=url,code=label,category="Cross-Origin",
                finding_type="OBSERVATION",title=f"{label} não observado",
                description=f"{label} não está declarado nesta resposta. A aplicabilidade depende da arquitetura cross-origin.",
                severity="INFO",evidence_ids=ev,impact="Nenhuma conclusão de exploração é feita; trata-se de postura observada.",
                containment="Mapear dependências cross-origin antes de endurecer.",
                remediation=f"Avaliar {label} conforme a necessidade de isolamento/compartilhamento da aplicação.",
                validation="Executar testes funcionais cross-origin e reauditar.",
            ))

    acao = [value.strip() for value in headers.get("access-control-allow-origin", ())]
    credentials = any(value.strip().casefold() == "true" for value in headers.get("access-control-allow-credentials", ()))
    if "*" in acao and credentials:
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="CORS_WILDCARD_CREDENTIALS",category="CORS",
            finding_type="CONFIGURATION_WEAKNESS",title="CORS combina origem wildcard e credentials",
            description="Access-Control-Allow-Origin '*' e Access-Control-Allow-Credentials true foram observados na resposta persistida. A combinação é inconsistente para requisições credenciadas em navegadores.",
            severity="MEDIUM",evidence_ids=ev,impact="Indica política CORS mal configurada; não é tratada como exploração confirmada.",
            containment="Revisar endpoints que realmente precisam de credenciais cross-origin.",
            remediation="Usar allowlist explícita e variar resposta por Origin quando credenciais forem necessárias.",
            validation="Testar preflight/respostas com origens permitidas e não permitidas.",
        ))
    elif "*" in acao:
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="CORS_WILDCARD",category="CORS",
            finding_type="EXPOSURE",title="CORS permite origem wildcard",
            description="Access-Control-Allow-Origin '*' foi observado. Isso pode ser intencional para recurso público e não implica vulnerabilidade por si só.",
            severity="LOW",evidence_ids=ev,impact="Conteúdo legível cross-origin por qualquer origem quando o navegador aplicar essa política.",
            containment="Confirmar que o recurso é realmente público.",
            remediation="Restringir origens apenas se o dado/recurso não deva ser público cross-origin.",
            validation="Revalidar com casos de uso cross-origin esperados.",
        ))

    if _truthy(os.environ.get(COOKIES_ENV), True):
        for index, raw_cookie in enumerate(headers.get("set-cookie", ())[:50], 1):
            attrs = _cookie_attributes(raw_cookie)
            if scheme == "https" and not attrs["secure"]:
                findings.append(_finding(
                    audit_id=audit_id,page_id=page_id,url=url,code=f"COOKIE_SECURE_{index}",category="Cookies",
                    finding_type="CONFIGURATION_WEAKNESS",title="Cookie definido sem Secure em contexto HTTPS",
                    description=f"Set-Cookie #{index} não contém Secure. O valor do cookie não é persistido pelo CAT-10.",
                    severity="HIGH" if attrs["sensitive_name_hint"] else "MEDIUM",evidence_ids=ev,impact="O cookie pode ser elegível para envio em transporte não HTTPS conforme escopo e comportamento do cliente.",
                    containment="Evitar uso do cookie para sessão/autorização até revisar seus atributos.",
                    remediation="Adicionar Secure quando o cookie for destinado a contexto HTTPS.",
                    validation="Reauditar Set-Cookie e fluxo de autenticação.",
                    details={"cookie": attrs},
                ))
            if not attrs["httponly"]:
                findings.append(_finding(
                    audit_id=audit_id,page_id=page_id,url=url,code=f"COOKIE_HTTPONLY_{index}",category="Cookies",
                    finding_type="OBSERVATION",title="Cookie sem HttpOnly observado",
                    description=f"Set-Cookie #{index} não contém HttpOnly. Nem todo cookie precisa de HttpOnly; classificar o papel do cookie antes de alterar.",
                    severity="MEDIUM" if attrs["sensitive_name_hint"] else "INFO",evidence_ids=ev,impact="Se contiver sessão/autorização, o acesso por JavaScript amplia exposição em caso de script malicioso.",
                    containment="Identificar se o cookie precisa ser acessível por JavaScript.",
                    remediation="Adicionar HttpOnly a cookies de sessão/autorização que não precisem de acesso por script.",
                    validation="Testar o fluxo funcional e reauditar os atributos.",
                    details={"cookie": attrs},
                ))
            same = str(attrs.get("samesite") or "")
            if not same:
                findings.append(_finding(
                    audit_id=audit_id,page_id=page_id,url=url,code=f"COOKIE_SAMESITE_{index}",category="Cookies",
                    finding_type="CONFIGURATION_WEAKNESS",title="Cookie sem SameSite explícito",
                    description=f"Set-Cookie #{index} não declara SameSite.",
                    severity="MEDIUM" if attrs["sensitive_name_hint"] else "LOW",evidence_ids=ev,impact="O comportamento cross-site depende do default do navegador.",
                    containment="Mapear fluxos cross-site legítimos antes da mudança.",
                    remediation="Definir SameSite=Lax/Strict ou None conforme necessidade real.",
                    validation="Testar login, redirects e integrações cross-site.",
                    details={"cookie": attrs},
                ))
            if same.casefold() == "none" and not attrs["secure"]:
                findings.append(_finding(
                    audit_id=audit_id,page_id=page_id,url=url,code=f"COOKIE_NONE_SECURE_{index}",category="Cookies",
                    finding_type="CONFIGURATION_WEAKNESS",title="SameSite=None observado sem Secure",
                    description=f"Set-Cookie #{index} combina SameSite=None sem Secure.",
                    severity="MEDIUM",evidence_ids=ev,impact="Navegadores modernos podem rejeitar o cookie e a configuração não atende ao requisito de Secure para SameSite=None.",
                    containment="Revisar imediatamente o fluxo cross-site que depende deste cookie.",
                    remediation="Adicionar Secure ou alterar SameSite conforme o fluxo pretendido.",
                    validation="Testar em navegadores suportados e reauditar.",
                    details={"cookie": attrs},
                ))

    server = "; ".join(headers.get("server", ()))
    powered = "; ".join(headers.get("x-powered-by", ()))
    if re.search(r"\d+(?:\.\d+)+", server):
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="SERVER_VERSION",category="Information Disclosure",
            finding_type="INFORMATION_DISCLOSURE",title="Header Server aparenta expor versão",
            description="O header Server contém marcador de versão. O CAT-10 não converte esta exposição em CVE sem correlação objetiva.",
            severity="LOW",evidence_ids=ev,impact="A versão declarada pode auxiliar fingerprinting; não confirma a versão real do software.",
            containment="Evitar depender do banner como controle de segurança.",
            remediation="Reduzir detalhes do banner quando operacionalmente possível e manter componentes atualizados.",
            validation="Reauditar headers; validar versão real por inventário interno, não pelo banner.",
        ))
    if powered:
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code="X_POWERED_BY",category="Information Disclosure",
            finding_type="INFORMATION_DISCLOSURE",title="X-Powered-By expõe tecnologia declarada",
            description="X-Powered-By foi observado. O valor é tratado como declaração informacional, não prova de versão.",
            severity="LOW",evidence_ids=ev,impact="Aumenta fingerprinting passivo da aplicação.",
            containment="Não usar ocultação de banner como substituto de atualização/patching.",
            remediation="Remover ou minimizar o header quando não houver necessidade operacional.",
            validation="Reauditar headers.",
        ))
    for index, generator in enumerate(page.get("generators", ()) or (), 1):
        if not re.search(r"\d+(?:\.\d+)+", str(generator)):
            continue
        findings.append(_finding(
            audit_id=audit_id,page_id=page_id,url=url,code=f"GENERATOR_VERSION_{index}",category="Information Disclosure",
            finding_type="INFORMATION_DISCLOSURE",title="Meta generator aparenta expor tecnologia/versionamento",
            description="Meta generator com marcador de versão foi observado no HTML persistido. É tratado como fingerprinting declarado, não como prova do componente em execução.",
            severity="LOW",evidence_ids=ev,impact="Pode facilitar identificação passiva de stack/versão declarada.",
            containment="Não depender da remoção do banner como controle primário.",
            remediation="Remover ou reduzir a identificação de versão quando não for necessária e manter o componente efetivamente utilizado atualizado.",
            validation="Reauditar o HTML e confirmar a versão real pelo inventário de build/dependências.",
        ))
    return findings


def _analyze_resources(audit_id: str, resources: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    third_party_analysis = _truthy(os.environ.get(THIRD_PARTY_ENV), True)
    items = list(resources)
    nonce_uses: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        attrs = item.get("attributes") or {}
        nonce_hash = str(attrs.get("nonce_sha256") or "")
        if nonce_hash:
            nonce_uses[nonce_hash].append(item)
    for nonce_hash, uses in nonce_uses.items():
        snapshots = {str(item.get("snapshot_id") or "") for item in uses if item.get("snapshot_id")}
        if len(snapshots) <= 1:
            continue
        first = uses[0]
        findings.append(_finding(
            audit_id=audit_id,page_id=str(first.get("page_id") or "") or None,
            url=str(first.get("page_url") or ""),code=f"NONCE_REUSE_{nonce_hash[:12]}",
            category="Browser Security",finding_type="CONFIGURATION_WEAKNESS",
            title="Nonce de script reutilizado entre snapshots",
            description=f"O mesmo hash de nonce foi observado em {len(snapshots)} snapshots distintos. O valor bruto do nonce não é persistido pelo CAT-10.",
            severity="MEDIUM",confidence="MEDIUM",evidence_ids=[str(item.get("snapshot_id") or "") for item in uses],
            impact="Se esse nonce participar da CSP, reutilização entre respostas pode reduzir a propriedade de unicidade esperada do nonce.",
            containment="Revisar a geração/cache da resposta antes de endurecer a política.",
            remediation="Gerar nonce criptograficamente imprevisível por resposta e manter o mesmo nonce apenas dentro da resposta que o declara.",
            validation="Capturar respostas independentes e confirmar hashes de nonce distintos entre snapshots.",
        ))
    for item in items:
        kind = str(item["resource_kind"])
        url = str(item.get("resource_url") or "")
        page_url = str(item.get("page_url") or "")
        page_id = str(item.get("page_id") or "")
        attrs = item.get("attributes") or {}
        ev = item.get("evidence_ids") or []
        party = str(item.get("party") or "UNKNOWN")
        if page_url.casefold().startswith("https://") and url.casefold().startswith("http://"):
            findings.append(_finding(
                audit_id=audit_id,page_id=page_id,url=page_url,code=f"MIXED_{item['resource_id']}",category="Mixed Content",
                finding_type="CONFIGURATION_WEAKNESS",title=f"Recurso {kind.lower()} declarado via HTTP em página HTTPS",
                description=f"Recurso HTTP declarado no HTML: {url}. A observação é de markup; o bloqueio efetivo pelo navegador depende do tipo/contexto.",
                severity="HIGH" if kind in {"SCRIPT","STYLESHEET","IFRAME"} else "MEDIUM",
                evidence_ids=ev,party=party,impact="Mixed content pode ser bloqueado ou reduzir garantias de integridade/confidencialidade do recurso.",
                containment="Evitar carregar o recurso até disponibilizá-lo por HTTPS.",
                remediation="Migrar a URL do recurso para HTTPS e remover dependências HTTP.",
                validation="Reauditar HTML e runtime; confirmar que não há request HTTP observado.",
            ))
        if third_party_analysis and party == "THIRD_PARTY" and kind in {"SCRIPT", "STYLESHEET"} and not str(attrs.get("integrity") or "").strip():
            findings.append(_finding(
                audit_id=audit_id,page_id=page_id,url=page_url,code=f"SRI_{item['resource_id']}",category="Resource Integrity",
                finding_type="EXPOSURE",title=f"Recurso third-party {kind.lower()} sem SRI observado",
                description="O recurso externo não declara integrity. SRI não é universalmente obrigatório; a aplicabilidade depende de URL estável, CORS/CDN e modelo de deployment.",
                severity="LOW",evidence_ids=ev,party=party,impact="Quando SRI é aplicável, sua ausência deixa a integridade do recurso dependente apenas do transporte/origem remota.",
                containment="Fixar versão/origem e reduzir dependências externas mutáveis.",
                remediation="Avaliar Subresource Integrity e crossorigin quando o recurso/fornecedor suportar conteúdo estável.",
                validation="Testar hash, CORS, atualização do fornecedor e reauditar.",
            ))
        integrity = str(attrs.get("integrity") or "").strip()
        if third_party_analysis and party == "THIRD_PARTY" and kind in {"SCRIPT", "STYLESHEET"} and integrity:
            tokens=[token for token in integrity.split() if token]
            supported=any(re.match(r"^sha(?:256|384|512)-[A-Za-z0-9+/=_-]+$", token, re.I) for token in tokens)
            if not supported:
                findings.append(_finding(
                    audit_id=audit_id,page_id=page_id,url=page_url,code=f"SRI_INVALID_{item['resource_id']}",category="Resource Integrity",
                    finding_type="CONFIGURATION_WEAKNESS",title=f"SRI de recurso third-party {kind.lower()} sem hash suportado",
                    description="O atributo integrity existe, mas não foi observado hash sha256/sha384/sha512 sintaticamente utilizável.",
                    severity="MEDIUM",evidence_ids=ev,party=party,impact="O navegador pode ignorar a proteção SRI pretendida para este recurso.",
                    containment="Fixar a versão do recurso até corrigir o hash.",
                    remediation="Gerar um hash SRI sha256/sha384/sha512 válido para o conteúdo exato servido e revisar crossorigin quando aplicável.",
                    validation="Recarregar o recurso em navegador suportado e reauditar o atributo integrity.",
                ))
        if kind == "FORM":
            method = str(attrs.get("method") or "get").casefold()
            sensitive = list(attrs.get("sensitive_fields") or [])
            if url.casefold().startswith("http://"):
                findings.append(_finding(
                    audit_id=audit_id,page_id=page_id,url=page_url,code=f"FORM_HTTP_{item['resource_id']}",category="Forms",
                    finding_type="CONFIGURATION_WEAKNESS",title="Formulário aponta para destino HTTP",
                    description=f"action observado: {url}; método={method.upper()}. O formulário não foi submetido.",
                    severity="HIGH" if sensitive else "MEDIUM",evidence_ids=ev,party=party,
                    impact="Dados submetidos podem sair do contexto HTTPS quando o navegador seguir a action.",
                    containment="Não coletar dados sensíveis por este formulário até correção.",
                    remediation="Usar destino HTTPS e revisar o endpoint.",
                    validation="Inspecionar action/método e testar submissão apenas em ambiente controlado pela equipe responsável.",
                ))
            if method == "get" and sensitive:
                findings.append(_finding(
                    audit_id=audit_id,page_id=page_id,url=page_url,code=f"FORM_GET_SENSITIVE_{item['resource_id']}",category="Forms",
                    finding_type="EXPOSURE",title="Formulário com campo sensível utiliza GET",
                    description=f"Campos semanticamente sensíveis ({', '.join(sensitive)}) foram observados em formulário GET. O CAT-10 não submeteu o formulário.",
                    severity="HIGH" if "password" in sensitive else "MEDIUM",evidence_ids=ev,party=party,
                    impact="Valores submetidos por GET podem compor a URL e aparecer em histórico, logs, analytics ou referrers.",
                    containment="Evitar inserir dados sensíveis neste fluxo até revisar o método.",
                    remediation="Usar POST quando a semântica do endpoint permitir e remover dados sensíveis de query strings.",
                    validation="Revisar markup/endpoint e confirmar que dados sensíveis não aparecem na URL após o fluxo controlado.",
                ))
            if third_party_analysis and party == "THIRD_PARTY" and sensitive:
                findings.append(_finding(
                    audit_id=audit_id,page_id=page_id,url=page_url,code=f"FORM_THIRD_{item['resource_id']}",category="Forms",
                    finding_type="EXPOSURE",title="Formulário com campo sensível aponta para third-party",
                    description=f"Campos semanticamente sensíveis ({', '.join(sensitive)}) e destino third-party foram observados. Nenhuma submissão foi realizada.",
                    severity="MEDIUM",evidence_ids=ev,party=party,impact="Dados podem ser enviados a uma origem externa quando o usuário submeter o formulário.",
                    containment="Confirmar contrato/necessidade do terceiro e minimizar dados.",
                    remediation="Validar o destino, base legal/política de dados e preferir first-party quando aplicável.",
                    validation="Revisão humana do fluxo e nova auditoria do markup.",
                ))
        if third_party_analysis and kind == "IFRAME" and party == "THIRD_PARTY" and not str(attrs.get("sandbox") or "").strip():
            findings.append(_finding(
                audit_id=audit_id,page_id=page_id,url=page_url,code=f"IFRAME_SANDBOX_{item['resource_id']}",category="Iframes",
                finding_type="OBSERVATION",title="Iframe third-party sem sandbox observado",
                description="Iframe externo sem atributo sandbox. A ausência pode ser intencional conforme a integração e não é classificada como vulnerabilidade confirmada.",
                severity="INFO",evidence_ids=ev,party=party,impact="O iframe não recebe restrições sandbox declaradas pelo documento host.",
                containment="Revisar permissões realmente necessárias ao conteúdo embutido.",
                remediation="Avaliar sandbox mínimo e Permissions-Policy/allow compatíveis com a integração.",
                validation="Testar a integração após qualquer restrição.",
            ))
    return findings


def _analyze_runtime(audit_id: str, page_context: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for page_id, page in page_context.items():
        groups = Counter(str(item.get("type") or "UNKNOWN").upper() for item in page.get("runtime", ()) if isinstance(item, Mapping))
        for kind, count in groups.items():
            if kind not in {"REQUEST_FAILED","HTTP_ERROR","CONSOLE_ERROR","PAGE_ERROR"}:
                continue
            findings.append(_finding(
                audit_id=audit_id,page_id=page_id,url=str(page.get("page_url") or ""),code=f"RUNTIME_{kind}",category="Runtime",
                finding_type="RUNTIME_FAILURE",title=f"{kind.replace('_',' ').title()} observado no runtime",
                description=f"{count} ocorrência(s) persistida(s) nas capturas de navegador. O CAT-10 apenas consome esta telemetria e não altera Apdex.",
                severity="MEDIUM" if kind in {"PAGE_ERROR","REQUEST_FAILED"} else "LOW",
                evidence_ids=[str(page_id)],impact="Falhas de runtime podem indicar dependência indisponível, erro JavaScript ou recurso com resposta de erro.",
                containment="Identificar a origem afetada e reduzir dependência crítica enquanto a causa é corrigida.",
                remediation="Corrigir a causa no recurso/aplicação correspondente; priorizar first-party e erros repetidos.",
                validation="Reexecutar a captura e confirmar ausência/redução das ocorrências.",
                details={"runtime_type": kind, "count": count},
            ))
        disclosures=[]
        for item in page.get("runtime", ()) or ():
            if not isinstance(item, Mapping):
                continue
            message=str(item.get("message") or "")
            if re.search(r"(?:[A-Za-z]:\\[^\s]+|/(?:home|var/www|srv|app|usr/src)/[^\s]+)", message):
                disclosures.append(message[:240])
            elif re.search(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b", message):
                disclosures.append(message[:240])
            elif "Traceback (most recent call last)" in message:
                disclosures.append(message[:240])
        if disclosures:
            findings.append(_finding(
                audit_id=audit_id,page_id=page_id,url=str(page.get("page_url") or ""),
                code="RUNTIME_DISCLOSURE",category="Information Disclosure",
                finding_type="INFORMATION_DISCLOSURE",title="Runtime aparenta expor detalhe interno",
                description=f"{len(disclosures)} mensagem(ns) de runtime contém(êm) padrão de caminho interno, IP privado ou traceback.",
                severity="LOW",confidence="MEDIUM",evidence_ids=[str(page_id)],
                impact="Detalhes internos podem facilitar fingerprinting e diagnóstico por terceiros.",
                containment="Evitar expor mensagens detalhadas ao cliente em produção.",
                remediation="Sanitizar mensagens client-side/servidor e registrar detalhes completos apenas em observabilidade interna.",
                validation="Reexecutar a captura em produção equivalente e confirmar ausência dos padrões internos.",
                details={"sample_count": len(disclosures), "samples": disclosures[:3]},
            ))
    return findings


def _advisory_findings(connection: sqlite3.Connection, audit_id: str) -> list[dict[str, Any]]:
    if not _table_exists(connection, "passive_security_advisories"):
        return []
    rows = connection.execute(
        """SELECT a.*,c.library,c.version,c.resource_id,r.page_id,r.page_url,r.party
           FROM passive_security_advisories a
           JOIN passive_security_components c ON c.component_id=a.component_id
           JOIN passive_security_resources r ON r.resource_id=c.resource_id
           WHERE a.audit_id=?""",
        (audit_id,),
    ).fetchall()
    findings: list[dict[str, Any]] = []
    for row in rows:
        aliases = _load(row["aliases_json"], [])
        cves = [str(v).upper() for v in aliases if re.fullmatch(r"CVE-\d{4}-\d+", str(v), re.I)]
        kev = str(row["kev_state"] or "NOT_CHECKED").upper()
        title = f"{row['library']} {row['version']} correlacionado a {row['advisory_id']}"
        description = (
            f"OSV retornou advisory para componente/versionamento identificado por filename com confiança moderada e versão explícita. "
            f"KEV={kev}. Esta correlação é objetiva para o identificador observado, mas não prova que o código vulnerável seja alcançável nesta página."
        )
        severity = "HIGH" if kev == "MATCHED" else "MEDIUM"
        findings.append(_finding(
            audit_id=audit_id,page_id=str(row["page_id"] or "") or None,url=str(row["page_url"] or ""),
            code=f"OSV_{row['row_id']}",category="Vulnerability Intelligence",
            finding_type="POTENTIAL_VULNERABILITY",title=title,description=description,severity=severity,
            confidence="MEDIUM",source="OSV + CISA KEV" if kev == "MATCHED" else "OSV",
            evidence_ids=[str(row["component_id"]), str(row["resource_id"])],party=str(row["party"] or "UNKNOWN"),
            origin="EXTERNAL",impact="O identificador de componente/versionamento observado correlaciona com advisory conhecido; como a identificação veio do nome do recurso, o CAT-10 mantém o finding como potencial até confirmação por inventário/build/SBOM. KEV, quando presente, eleva a prioridade operacional.",
            containment="Reduzir exposição do componente afetado, restringir funcionalidade dependente ou isolar a rota enquanto a atualização é planejada.",
            remediation="Atualizar para versão não afetada indicada pelo advisory/fonte do fornecedor, validando compatibilidade.",
            validation="Reidentificar a versão, consultar novamente OSV e confirmar ausência do CVE/advisory; executar testes de regressão.",
            cves=cves,details={
                "advisory_id": row["advisory_id"],
                "aliases": aliases,
                "severity": _load(row["severity_json"], []),
                "references": _load(row["references_json"], []),
                "kev_state": kev,
                "kev": _load(row["kev_details_json"], {}),
            },
        ))
    return findings


def _persist_findings(connection: sqlite3.Connection, audit_id: str, findings: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM passive_security_remediations WHERE audit_id=?", (audit_id,))
    connection.execute("DELETE FROM passive_security_findings WHERE audit_id=?", (audit_id,))
    now = _now()
    for item in findings:
        connection.execute(
            """INSERT INTO passive_security_findings
               (finding_id,audit_id,page_id,url_scope,category,finding_type,title,description,severity,confidence,source,evidence_ids_json,party_context,origin_kind,impact,containment,remediation,validation,cwe,cve_json,details_json,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item["finding_id"], audit_id, item.get("page_id"), item.get("url_scope"),
                item["category"], item["finding_type"], item["title"], item["description"],
                item["severity"], item["confidence"], item["source"], _dump(item["evidence_ids"]),
                item["party_context"], item["origin_kind"], item["impact"], item["containment"],
                item["remediation"], item["validation"], item.get("cwe"), _dump(item["cves"]),
                _dump(item["details"]), now,
            ),
        )
        connection.execute(
            """INSERT INTO passive_security_remediations
               (remediation_id,audit_id,finding_id,source,containment,correction,implementation_order,regression_risk,validation,advisory_only,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                _stable("PSREM", item["finding_id"]), audit_id, item["finding_id"],
                "DETERMINISTIC" if item["origin_kind"] != "AI" else "AI",
                item["containment"], item["remediation"],
                "Priorizar por severidade, KEV e dependências técnicas; validar em ambiente controlado antes de produção.",
                "A alteração pode impactar integrações, cookies, CSP, CORS ou recursos third-party; aplicar incrementalmente com rollback disponível.",
                item["validation"], 1, now,
            ),
        )


def analyze_passive_security(*, audit_id: str, workspace: Any, source_blocked: bool = False) -> dict[str, Any]:
    if not enabled():
        return {"status": "DISABLED", "reason": "PASSIVE_SECURITY_NOT_SELECTED"}
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            ensure_schema(connection)
            resources, components, page_context = _resource_inventory(connection, workspace, audit_id)
            _persist_inventory(
                connection,
                audit_id,
                resources,
                components,
                preserve_advisories=True,
            )

            findings: list[dict[str, Any]] = []
            for page in page_context.values():
                if _truthy(os.environ.get(HEADERS_ENV), True):
                    findings.extend(_analyze_headers(audit_id, page))
            if _truthy(os.environ.get(RESOURCES_ENV), True):
                findings.extend(_analyze_resources(audit_id, resources))
            if _truthy(os.environ.get(RUNTIME_ENV), True):
                findings.extend(_analyze_runtime(audit_id, page_context))
            findings.extend(_advisory_findings(connection, audit_id))

            deduped = list({item["finding_id"]: item for item in findings}.values())
            deduped.sort(key=lambda item: (SEVERITY_ORDER.get(item["severity"], 9), item["category"], item["title"]))
            _persist_findings(connection, audit_id, deduped)

            integration_rows = connection.execute(
                "SELECT integration_id,state FROM passive_security_integrations WHERE audit_id=?",
                (audit_id,),
            ).fetchall()
            integration_states = {str(row["integration_id"]): str(row["state"]) for row in integration_rows}
            osv_state = str(integration_states.get("OSV") or "NOT_REQUESTED").upper()
            kev_state = str(integration_states.get("CISA_KEV") or "NOT_REQUESTED").upper()
            osv_covered = osv_state in {"COMPLETED", "NO_DATA"}
            kev_covered = kev_state in {"COMPLETED", "NO_DATA"}
            coverage = {
                "transport": True,
                "headers": _truthy(os.environ.get(HEADERS_ENV), True),
                "csp": _truthy(os.environ.get(HEADERS_ENV), True),
                "cookies": _truthy(os.environ.get(COOKIES_ENV), True),
                "cors_cross_origin": _truthy(os.environ.get(HEADERS_ENV), True),
                "scripts_resources": _truthy(os.environ.get(RESOURCES_ENV), True),
                "third_party": _truthy(os.environ.get(THIRD_PARTY_ENV), True),
                "mixed_content": _truthy(os.environ.get(RESOURCES_ENV), True),
                "forms_iframes": _truthy(os.environ.get(RESOURCES_ENV), True),
                "runtime": _truthy(os.environ.get(RUNTIME_ENV), True),
                "component_inventory": bool(components),
                "osv_intelligence": osv_covered,
                "cisa_kev": kev_covered,
                "vulnerability_intelligence": osv_covered,
                "active_scanning": False,
            }
            limitations: list[str] = []
            if not page_context:
                limitations.append("NO_PERSISTED_PAGE_CONTEXT")
            if integration_states.get("OSV") in {"UNAVAILABLE", "PARTIAL"}:
                limitations.append("OSV_REDUCED_COVERAGE")
            if integration_states.get("CISA_KEV") == "UNAVAILABLE":
                limitations.append("CISA_KEV_REDUCED_COVERAGE")
            failed_integrations = {
                key: value for key, value in integration_states.items()
                if value in {"UNAVAILABLE", "PARTIAL", "FAILED_RETRYABLE", "FAILED_TERMINAL"}
            }
            status = "PARTIAL" if limitations or failed_integrations else "COMPLETED"
            now = _now()
            existing = connection.execute(
                "SELECT created_at FROM passive_security_runs WHERE audit_id=?", (audit_id,)
            ).fetchone()
            created = str(existing["created_at"]) if existing else now
            connection.execute(
                """INSERT INTO passive_security_runs
                   (audit_id,contract_version,enabled,status,pages_analyzed,resources_count,components_count,findings_count,remediations_count,coverage_json,limitations_json,integration_states_json,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(audit_id) DO UPDATE SET
                     contract_version=excluded.contract_version,enabled=excluded.enabled,status=excluded.status,
                     pages_analyzed=excluded.pages_analyzed,resources_count=excluded.resources_count,
                     components_count=excluded.components_count,findings_count=excluded.findings_count,
                     remediations_count=excluded.remediations_count,coverage_json=excluded.coverage_json,
                     limitations_json=excluded.limitations_json,integration_states_json=excluded.integration_states_json,
                     updated_at=excluded.updated_at""",
                (
                    audit_id, CONTRACT_VERSION, 1, status, len(page_context), len(resources),
                    len(components), len(deduped), len(deduped), _dump(coverage),
                    _dump(limitations), _dump(integration_states), created, now,
                ),
            )
        return {
            "status": status,
            "pages": len(page_context),
            "resources": len(resources),
            "components": len(components),
            "findings": len(deduped),
            "limitations": limitations,
            "source_blocked": source_blocked,
        }
    finally:
        connection.close()


def improvement_findings(connection: sqlite3.Connection, audit_id: str, page_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    """Project CAT-10 deterministic findings into the existing Improvement SECURITY domain."""
    if not _table_exists(connection, "passive_security_findings"):
        return None
    rows = connection.execute(
        "SELECT * FROM passive_security_findings WHERE audit_id=? AND page_id=? ORDER BY created_at,finding_id",
        (audit_id, page_id),
    ).fetchall()
    if not rows:
        return None
    findings: list[dict[str, Any]] = []
    for row in rows:
        findings.append({
            "finding_id": str(row["finding_id"]),
            "domain": "SECURITY",
            "severity": str(row["severity"]),
            "source": str(row["source"]),
            "title": str(row["title"]),
            "observation": str(row["description"]),
            "evidence_ids": _load(row["evidence_ids_json"], []),
            "impacts": {"security": 3 if str(row["severity"]) in {"CRITICAL","HIGH"} else 2 if str(row["severity"]) == "MEDIUM" else 1},
            "details": {
                "finding_type": row["finding_type"],
                "category": row["category"],
                "confidence": row["confidence"],
                "party_context": row["party_context"],
                "origin_kind": row["origin_kind"],
                "impact": row["impact"],
                "containment": row["containment"],
                "deterministic_remediation": row["remediation"],
                "validation": row["validation"],
                "cwe": row["cwe"],
                "cves": _load(row["cve_json"], []),
            },
        })
    run = connection.execute(
        "SELECT * FROM passive_security_runs WHERE audit_id=?", (audit_id,)
    ).fetchone() if _table_exists(connection, "passive_security_runs") else None
    summary = {
        "mode": "PASSIVE_ONLY",
        "active_exploitation": False,
        "shared_security_core": True,
        "catalog": "CAT-10",
        "status": str(run["status"]) if run else "UNKNOWN",
        "coverage": _load(run["coverage_json"], {}) if run else {},
        "limitations": _load(run["limitations_json"], []) if run else [],
        "note": "Findings determinísticos reutilizados do CAT-10; IA não decide presença de headers, versão ou CVE.",
    }
    return findings, summary


__all__ = [
    "CONTRACT_VERSION",
    "ENABLED_ENV",
    "HEADERS_ENV",
    "COOKIES_ENV",
    "RESOURCES_ENV",
    "THIRD_PARTY_ENV",
    "RUNTIME_ENV",
    "OSV_ENV",
    "KEV_ENV",
    "EXTERNAL_TIMEOUT_ENV",
    "ensure_schema",
    "enabled",
    "collect_external_intelligence",
    "analyze_passive_security",
    "improvement_findings",
]
