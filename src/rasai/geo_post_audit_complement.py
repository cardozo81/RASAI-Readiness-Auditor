"""#318: external GEO supplement for a *completed, sealed* RASAi AUD.

The source AUD and its report-catalog remain strictly read-only. A separate,
versioned, audit-linked SQLite workspace hosts Perplexity Search API provenance
and its existing M18 pricing/attempt ledger. Never rerun collectors, scoring,
SERP, other AI, PSI or Apdex. A local intent reservation is *at most one send*,
not a commercial idempotency guarantee after unknown network outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence

from rasai.domain import Audit, AuditStatus, CompletionStatus
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.search_intelligence.perplexity import (
    PerplexityTransport,
    execute_perplexity_search,
    _validate_queries,
    _validate_search_type,
)
from rasai.search_intelligence.perplexity_request_policy import validate_request_options

SUPPLEMENT_VERSION = "RASAI-GEO-EXTERNAL-SUPPLEMENT-001"
_INTENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


@dataclass(frozen=True, slots=True)
class GeoSupplementResult:
    audit_id: str
    intent_id: str
    directory: Path | None
    status: str
    request_executed: bool
    detail: str
    billability: str = "NOT_ATTEMPTED"


def _digest(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _valid_provider_interval(started_at: object, finished_at: object) -> bool:
    """Verify an offset-aware, ordered run window before promoting evidence.

    Matching result.json and a rehashed SQLite ledger is not enough: both
    can contain the same impossible or timezone-ambiguous timestamps.
    """
    if not isinstance(started_at, str) or not isinstance(finished_at, str):
        return False
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        return (
            started.tzinfo is not None
            and finished.tzinfo is not None
            and started.utcoffset() is not None
            and finished.utcoffset() is not None
            and started.astimezone(timezone.utc) <= finished.astimezone(timezone.utc)
        )
    except (ValueError, TypeError, OverflowError):
        return False


def _write_json(path: Path, data: dict[str, Any]) -> None:
    pending = path.with_name(path.name + ".tmp")
    pending.write_text(
        json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(pending, path)


def _safe_supplement_scope_root(workspace: AuditWorkspace, audit_id: str) -> Path:
    """Reject linked parent directories before reserving any billable intent.

    The read-only inventory already rejected symlinked roots, but the paid
    entrypoint could follow a linked .rasai-geo-supplements/AUD scope on mkdir.
    Both paths must enforce the same fail-closed containment boundary.
    """
    root = workspace.root.parent / ".rasai-geo-supplements"
    scope = root / audit_id
    if workspace.root.is_symlink() or workspace.database.is_symlink():
        raise ValueError("original AUD workspace cannot be linked")
    if root.is_symlink() or scope.is_symlink():
        raise ValueError("external supplement root or scope cannot be linked")
    if (root.exists() and not root.is_dir()) or (
        scope.exists() and not scope.is_dir()
    ):
        raise ValueError("external supplement root or scope is not a directory")
    return scope


def _sealed_audit(workspace: AuditWorkspace, audit_id: str) -> tuple[str, str, str]:
    # No CREATE, UPDATE, connections in read/write mode or manifest rewrite.
    report_root = workspace.root / "report-catalog"
    report_manifest = report_root / "manifest.json"
    if not report_manifest.is_file():
        raise ValueError("AUD COMPLETE requires an existing catalog manifest")
    from rasai.catalog_report_site import verify_catalog_report_package
    verified, problems = verify_catalog_report_package(report_root)
    if not verified:
        raise ValueError("original report-catalog failed package verification: " + str(problems[:2]))
    # Package self-integrity alone cannot prove that the report still
    # represents the live AUD state. This prevents a post-AUD paid search
    # from binding a valid OLD report to a modified/new source database.
    from rasai.catalog_report_site import catalog_report_is_fresh
    if not catalog_report_is_fresh(audit_id=audit_id, workspace=workspace):
        raise ValueError("original report-catalog stale against source AUD")
    db_uri = f"file:{workspace.database.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(db_uri, uri=True) as connection:
        row = connection.execute(
            "SELECT status, completion_status FROM audits WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
        if (row is None or str(row[0] or "").upper() != "COMPLETED"
                or str(row[1] or "").upper() != "COMPLETE"):
            raise ValueError("source AUD must be COMPLETE before external supplement")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("source audit.db integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("source audit.db foreign keys invalid")
    from rasai.catalog_report_site import _source_fingerprint
    return _digest(workspace.database), _digest(report_manifest), _source_fingerprint(workspace.database)


def _existing(
    directory: Path, *,
    audit_id: str, intent_id: str, request_fingerprint: str,
    source_db_sha: str, source_manifest_sha: str,
    source_state_fingerprint: str,
) -> GeoSupplementResult:
    # A previously reserved intent must never silently bind to a changed AUD.
    # Refuse linked files through symlinks, which could escape the sidecar.
    if directory.is_symlink():
        raise ValueError("supplement directory is a symlink; reuse denied")
    record_path = directory / "intent.json"
    if record_path.is_symlink():
        raise ValueError("supplement intent is a symlink; reuse denied")
    if not record_path.is_file():
        return GeoSupplementResult(
            audit_id, intent_id, directory, "PENDING_UNCERTAIN", False,
            "reservação incompleta; nenhum reenvio automático por possível cobrança",
        )
    try:
        saved = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return GeoSupplementResult(
            audit_id, intent_id, directory, "PENDING_UNCERTAIN", False,
            "registro de intenção corrompido; não reenviar",
        )
    if not isinstance(saved, dict):
        return GeoSupplementResult(
            audit_id, intent_id, directory, "PENDING_UNCERTAIN", False,
            "registro de intenção inválido; não reenviar",
        )
    if saved.get("request_fingerprint") != request_fingerprint:
        raise ValueError("same intent_id cannot be reused for different queries/options")
    expected_original = {
        "source_audit_db_sha256": source_db_sha,
        "source_catalog_manifest_sha256": source_manifest_sha,
        "source_audit_state_fingerprint": source_state_fingerprint,
    }
    if any(saved.get(key) != value for key, value in expected_original.items()):
        raise ValueError("source AUD changed since intent reservation; manual review required")
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("supplement manifest is a symlink; reuse denied")
    if not manifest_path.is_file():
        return GeoSupplementResult(
            audit_id, intent_id, directory, "PENDING_UNCERTAIN", False,
            "tentativa não finalizada; situação faturável desconhecida; não reenviar",
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return GeoSupplementResult(
            audit_id, intent_id, directory, "PENDING_UNCERTAIN", False,
            "manifesto inválido; nenhuma repetição automática",
        )
    if not isinstance(manifest, dict) or any(
        manifest.get(key) != expected
        for key, expected in {
            "version": SUPPLEMENT_VERSION,
            "audit_id": audit_id,
            "intent_id": intent_id,
            "request_fingerprint": request_fingerprint,
            "source_audit_db_sha256": source_db_sha,
            "source_catalog_manifest_sha256": source_manifest_sha,
        }.items()
    ):
        raise ValueError("supplement manifest provenance mismatch; do not retry")
    files = manifest.get("files")
    required_paths = {
        "intent.json", "result.json", "supplement.html", "evidence/audit.db",
    }
    if (
        not isinstance(files, list)
        or len(files) != len(required_paths)
        or any(not isinstance(f, dict) for f in files)
        or {str(f.get("path") or "") for f in files} != required_paths
    ):
        raise ValueError("supplement manifest is incomplete; do not retry")
    for file in files:
        if not isinstance(file, dict):
            raise ValueError("supplement manifest has invalid file record")
        relative = Path(str(file.get("path") or ""))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("supplement manifest has unsafe file path")
        candidate = directory / relative
        if (
            candidate.is_symlink()
            or candidate.parent.is_symlink()
            or not candidate.is_file()
            or candidate.parent not in {directory, directory / "evidence"}
            or candidate.stat().st_size != file.get("bytes")
            or _digest(candidate) != file.get("sha256")
        ):
            raise ValueError("supplement manifest integrity failed; do not retry automatically")
    # The same path is reached by a second paid-action click. Never report
    # ALREADY_RECORDED solely from self-consistent file hashes: a rehashed
    # result.json could claim a fabricated source, clock or free request.
    # Reuse requires the same semantic checks as the read-only inventory.
    _verify_recorded_supplement(
        directory, audit_id=audit_id, intent_id=intent_id,
        request_fingerprint=request_fingerprint,
        source_db_sha=source_db_sha,
        source_manifest_sha=source_manifest_sha,
        source_state_fingerprint=source_state_fingerprint,
        scope=saved.get("scope"), manifest=manifest,
    )
    return GeoSupplementResult(
        audit_id, intent_id, directory, "ALREADY_RECORDED", False,
        f"Reutilizado suplemento independente: {manifest.get('run_status', 'UNKNOWN')}",
        str(manifest.get("billability") or "UNKNOWN"),
    )




def _same_ledger_quantity(reported: object, recorded: object) -> bool:
    """Compare finite numeric usage/cost while rejecting bool, NaN and Infinity.

    result.json records zero usage when the provider returned no native
    consumption item; the canonical ledger uses SQL NULL in that case.
    This is a representation allowance, not an invented provider charge.
    """
    if recorded is None:
        return reported is None or type(reported) in (int, float) and reported == 0
    if (
        type(reported) not in (int, float)
        or type(recorded) not in (int, float)
        or not math.isfinite(reported) or not math.isfinite(recorded)
        or reported < 0 or recorded < 0
    ):
        return False
    return reported == recorded


def _verify_recorded_supplement(
    directory: Path, *,
    audit_id: str, intent_id: str, request_fingerprint: str,
    source_db_sha: str, source_manifest_sha: str,
    source_state_fingerprint: str,
    scope: object, manifest: dict,
) -> tuple[dict[str, Any], int]:
    """Verify derived provider evidence, not just user-rehashable file digests.

    Used by repeat intent handling and inspection. A failed verification must
    never cause a second request, nor imply that a possibly charged request
    was free. This function is strictly read-only.
    """
    if not isinstance(scope, dict) or any(
        scope.get(k) != v for k, v in {
            "audit_id": audit_id, "intent_id": intent_id,
            "version": SUPPLEMENT_VERSION,
        }.items()
    ):
        raise ValueError("supplement scope identity mismatch; do not retry")
    recalculated = sha256(
        json.dumps(scope, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if recalculated != request_fingerprint:
        raise ValueError("supplement intent fingerprint mismatch; do not retry")
    queries = scope.get("queries")
    mode = scope.get("search_type")
    if (
        not isinstance(queries, list) or not 1 <= len(queries) <= 5
        or any(not isinstance(q, str) or not q.strip() for q in queries)
        or mode not in {"web", "fast"}
    ):
        raise ValueError("supplement query scope invalid; do not retry")
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    if (
        not isinstance(result, dict)
        or result.get("version") != SUPPLEMENT_VERSION
        or result.get("source_audit_id") != audit_id
        or result.get("supplement_intent_id") != intent_id
        or result.get("request_fingerprint") != request_fingerprint
        or result.get("source_audit_db_sha256") != source_db_sha
        or result.get("source_catalog_manifest_sha256") != source_manifest_sha
        or result.get("source_audit_state_fingerprint") != source_state_fingerprint
        or result.get("query_count") != len(queries)
        or result.get("queries") != queries
        or result.get("search_type") != mode
        or result.get("status") != manifest.get("run_status")
        or result.get("billability") != manifest.get("billability")
        or not isinstance(result.get("run_id"), str)
        or not isinstance(result.get("started_at"), str)
        or not isinstance(result.get("finished_at"), str)
        or not isinstance(result.get("sources"), list)
        or any(
            not isinstance(item, dict)
            or not all(isinstance(item.get(k), str) for k in
                       ("url", "title", "snippet"))
            for item in result["sources"]
        )
    ):
        raise ValueError("supplement result provenance mismatch; do not retry")
    if not _valid_provider_interval(result["started_at"], result["finished_at"]):
        raise ValueError("supplement temporal provenance invalid; do not retry")
    evidence_db = directory / "evidence" / "audit.db"
    with sqlite3.connect(evidence_db.resolve().as_uri() + "?mode=ro",
                         uri=True, timeout=2) as con:
        con.execute("PRAGMA query_only=ON")
        rows = con.execute(
            "SELECT audit_id, status, query_json, search_type, purpose, "
            "request_payload_hash, started_at, finished_at, billable, "
            "native_usage_unit, native_usage_quantity, estimated_cost, "
            "cost_currency, pricing_version "
            "FROM perplexity_search_runs WHERE run_id=?",
            (result["run_id"],),
        ).fetchall()
        if len(rows) != 1:
            raise ValueError("supplement run identity missing; do not retry")
        row = rows[0]
        charged = ("UNKNOWN" if row[8] is None
                   else "TRUE" if row[8] == 1 else "FALSE" if row[8] == 0
                   else "INVALID")
        if (
            row[0] != audit_id or row[1] != result["status"]
            or json.loads(row[2]) != queries
            or str(row[3] or "").lower() != mode
            or row[4] != "POST_AUD_GEO_SUPPLEMENT"
            or row[5] != result.get("request_payload_hash")
            or row[6] != result["started_at"]
            or row[7] != result["finished_at"]
            or charged != result["billability"]
            # The report-facing economic metadata cannot be altered by
            # rewriting result.json and re-hashing manifest.json. Neither
            # estimated cost nor usage is proof of an actual provider invoice.
            or row[9] != result.get("native_usage_unit")
            or not _same_ledger_quantity(result.get("native_usage_quantity"), row[10])
            or not _same_ledger_quantity(result.get("posthoc_estimated_cost"), row[11])
            or row[12] != result.get("cost_currency")
            or row[13] != result.get("pricing_version")
            or con.execute("PRAGMA quick_check").fetchone()[0] != "ok"
            or con.execute("PRAGMA foreign_key_check").fetchone() is not None
        ):
            raise ValueError("supplement SQLite ledger mismatch; do not retry")
        sources = con.execute(
            "SELECT url, title, snippet FROM perplexity_search_sources "
            "WHERE run_id=? ORDER BY position, url",
            (result["run_id"],),
        ).fetchall()
        if result["sources"] != [
            {"url": url, "title": title, "snippet": snippet}
            for url, title, snippet in sources
        ]:
            raise ValueError("supplement source ledger mismatch; do not retry")
    return result, len(sources)


@dataclass(frozen=True, slots=True)
class GeoSupplementInventoryItem:
    """Only facts verified against the current sealed AUD and supplement files."""
    intent_id: str
    state: str
    query_count: int | None
    search_type: str | None
    billability: str
    directory: Path
    detail: str
    # Independently verified Search API outcome, distinct from package integrity.
    # Uncertain and invalid packages never expose an inferred provider result.
    run_status: str | None = None
    source_count: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    # Available ONLY when content is verified against the derived M18 ledger.
    # Post-hoc estimate, not observed provider invoice or original AUD cost.
    posthoc_estimated_cost: float | None = None
    cost_currency: str | None = None
    pricing_version: str | None = None


def list_post_audit_geo_supplements(
    original_workspace: AuditWorkspace, *, audit_id: str,
) -> tuple[GeoSupplementInventoryItem, ...]:
    """Read-only listing. Never reserves an intent or executes a provider.

    A structurally valid manifest is not alone a valid successful observation:
    manifest SHA, original hashes, recorded request identity, result JSON and
    the derived Perplexity ledger must all agree. Uncertain attempts never
    silently become reusable or "not charged".
    """
    original_workspace = AuditWorkspace.open(original_workspace.root)
    if audit_id != original_workspace.root.name:
        raise ValueError("source workspace and audit_id mismatch")
    db_sha, report_sha, state_hash = _sealed_audit(original_workspace, audit_id)
    scope_dir = _safe_supplement_scope_root(original_workspace, audit_id)
    if not scope_dir.exists():
        return ()
    if not scope_dir.is_dir():
        raise ValueError("external supplement scope is not a directory")
    rows: list[GeoSupplementInventoryItem] = []
    for folder in sorted(scope_dir.iterdir(), key=lambda x: x.name):
        if folder.is_symlink() or not folder.is_dir():
            # Symlinked evidence can escape the user's audit scope. Never follow.
            rows.append(GeoSupplementInventoryItem(
                "N/D", "INVALID", None, None, "UNKNOWN", folder,
                "diretório vinculado ou inválido; leitura recusada",
            ))
            continue
        intent_path = folder / "intent.json"
        if intent_path.is_symlink():
            rows.append(GeoSupplementInventoryItem(
                "N/D", "INVALID", None, None, "UNKNOWN", folder,
                "registro de intenção vinculado; leitura recusada",
            ))
            continue
        try:
            saved = json.loads(intent_path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict) or not isinstance(saved.get("scope"), dict):
                raise ValueError("intent structure")
            data = saved["scope"]
            intent = data.get("intent_id")
            if (
                not isinstance(intent, str)
                or not _INTENT_PATTERN.fullmatch(intent)
                or folder.name != sha256(intent.encode("utf-8")).hexdigest()[:32]
                or data.get("audit_id") != audit_id
                or data.get("version") != SUPPLEMENT_VERSION
                or saved.get("authorization") != "EXPLICIT_PER_INTENT"
            ):
                raise ValueError("intent identity mismatch")
            expected = sha256(
                json.dumps(
                    data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            if saved.get("request_fingerprint") != expected:
                raise ValueError("intent request fingerprint mismatch")
            request = data.get("queries")
            mode = data.get("search_type")
            if (
                not isinstance(request, (list, tuple))
                or not 1 <= len(request) <= 5
                or any(not isinstance(q, str) or not q.strip() for q in request)
                or mode not in {"web", "fast"}
            ):
                raise ValueError("query provenance invalid")
            query_count = len(request)
        except (OSError, UnicodeError, ValueError, TypeError):
            rows.append(GeoSupplementInventoryItem(
                "N/D", "PENDING_UNCERTAIN", None, None, "UNKNOWN", folder,
                "registro de intenção ausente, corrompido ou não verificável; não reenviar",
            ))
            continue
        try:
            checked = _existing(
                folder, audit_id=audit_id, intent_id=intent,
                request_fingerprint=expected, source_db_sha=db_sha,
                source_manifest_sha=report_sha,
                source_state_fingerprint=state_hash,
            )
            if checked.status == "PENDING_UNCERTAIN":
                rows.append(GeoSupplementInventoryItem(
                    intent, "PENDING_UNCERTAIN", query_count, mode, "UNKNOWN",
                    folder, checked.detail,
                ))
                continue
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            result, source_count = _verify_recorded_supplement(
                folder, audit_id=audit_id, intent_id=intent,
                request_fingerprint=expected, source_db_sha=db_sha,
                source_manifest_sha=report_sha,
                source_state_fingerprint=state_hash, scope=data, manifest=manifest,
            )
            rows.append(GeoSupplementInventoryItem(
                intent, "VERIFIED", query_count, mode, str(result["billability"]),
                folder, f"suplemento {result['status']}; fonte e ledger verificados",
                run_status=str(result["status"]),
                source_count=source_count,
                started_at=result["started_at"],
                finished_at=result["finished_at"],
                posthoc_estimated_cost=result.get("posthoc_estimated_cost"),
                cost_currency=result.get("cost_currency"),
                pricing_version=result.get("pricing_version"),
            ))
        except (OSError, UnicodeError, ValueError, TypeError, sqlite3.Error):
            rows.append(GeoSupplementInventoryItem(
                intent, "INVALID", query_count, mode, "UNKNOWN", folder,
                "manifesto, fonte ou ledger inconsistente; não reenviar",
            ))
    return tuple(rows)


def run_post_audit_geo_supplement(
    original_workspace: AuditWorkspace,
    *,
    audit_id: str,
    intent_id: str,
    query: str | Sequence[str],
    search_type: str = "web",
    search_options: Mapping[str, Any] | None = None,
    explicit_cost_authorization: bool = False,
    env: Mapping[str, str] | None = None,
    transport: PerplexityTransport | None = None,
) -> GeoSupplementResult:
    """One explicitly authorized external request, isolated outside the sealed AUD.

    This is an internal application entrypoint; it deliberately does NOT attach
    to the audited report catalog or make any promise about human GUI exposure.
    A new intent_id represents a new, independently authorized billable action.
    """
    if not explicit_cost_authorization:
        raise PermissionError("explicit billing authorization is mandatory")
    if not _INTENT_PATTERN.fullmatch(str(intent_id or "")):
        raise ValueError("intent_id must be 1..80 safe ASCII characters")
    original_workspace = AuditWorkspace.open(original_workspace.root)
    if audit_id != original_workspace.root.name:
        raise ValueError("source workspace and audit_id mismatch")
    terms = _validate_queries(query)
    mode = _validate_search_type(search_type)
    options = validate_request_options(search_options or {}, search_type=mode)
    environment = os.environ if env is None else env
    # Gate before any filesystem reservation or call, consistently with CAT-05.
    from rasai.console_search_intelligence import perplexity_enabled
    if not perplexity_enabled(environment):
        return GeoSupplementResult(
            audit_id, intent_id, None, "DISABLED", False, "integração desabilitada",
        )
    from rasai.search_intelligence.perplexity import perplexity_configuration_status
    if not perplexity_configuration_status(environment)["configured"]:
        # Do not reserve an irreversible intent for a request that cannot be
        # submitted. Missing local credentials are NOT a provider 401: key
        # validity cannot be proved without a billable external request.
        return GeoSupplementResult(
            audit_id, intent_id, None, "NOT_CONFIGURED", False,
            "credencial Perplexity não configurada; nenhuma intenção reservada",
        )

    source_db_sha, source_manifest_sha, source_state_fingerprint = _sealed_audit(original_workspace, audit_id)
    scope = {
        "audit_id": audit_id,
        "intent_id": intent_id,
        "queries": terms,
        "search_type": mode,
        "search_options": options,
        "version": SUPPLEMENT_VERSION,
    }
    fingerprint = sha256(
        json.dumps(scope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    supplement_root = (
        _safe_supplement_scope_root(original_workspace, audit_id)
        / sha256(intent_id.encode("utf-8")).hexdigest()[:32]
    )
    try:
        supplement_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return _existing(
            supplement_root, audit_id=audit_id, intent_id=intent_id,
            request_fingerprint=fingerprint,
            source_db_sha=source_db_sha,
            source_manifest_sha=source_manifest_sha,
            source_state_fingerprint=source_state_fingerprint,
        )
    # Persistent reservation precedes network. A crash/timeout blocks automatic
    # retry, because the provider may have billed the first POST.
    _write_json(
        supplement_root / "intent.json",
        {
            "request_fingerprint": fingerprint,
            "scope": scope,
            "source_audit_db_sha256": source_db_sha,
            "source_audit_state_fingerprint": source_state_fingerprint,
            "source_catalog_manifest_sha256": source_manifest_sha,
            "authorization": "EXPLICIT_PER_INTENT",
        },
    )

    # Minimal, entirely independent SQLite workspace; it has the canonical
    # schema/parent AUD FK so the existing adapter + M18 ledger are reused.
    derived = AuditWorkspace.create(supplement_root, "evidence")
    with AuditPersistence(derived) as store:
        store.audits.add(
            Audit(
                audit_id=audit_id,
                project_name="Derived external GEO supplement (not original AUD)",
                status=AuditStatus.COMPLETED,
                completion_status=CompletionStatus.COMPLETE,
            )
        )
    run = execute_perplexity_search(
        derived,
        audit_id=audit_id,
        query=terms,
        purpose="POST_AUD_GEO_SUPPLEMENT",
        search_type=mode,
        search_options=options,
        env=environment,
        transport=transport,
    )
    # No original report re-projection: separate report+manifest belong to the
    # derived package only and retain their own provenance and verification.
    result_data = {
        "version": SUPPLEMENT_VERSION,
        "source_audit_id": audit_id,
        "source_audit_db_sha256": source_db_sha,
        "source_audit_state_fingerprint": source_state_fingerprint,
        "source_catalog_manifest_sha256": source_manifest_sha,
        "supplement_intent_id": intent_id,
        "request_fingerprint": fingerprint,
        "run_id": run.run_id,
        "request_payload_hash": run.request_payload_hash,
        "status": run.status,
        "purpose": run.purpose,
        "search_type": run.search_type,
        "query_count": len(run.queries),
        "queries": list(run.queries),
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat(),
        "sources": [
            {"url": s.url, "title": s.title, "snippet": s.snippet}
            for s in run.sources
        ],
        "native_usage_unit": run.native_usage[0].unit if run.native_usage else None,
        "native_usage_quantity": run.native_usage[0].quantity if run.native_usage else 0,
        "billability": (
            "UNKNOWN" if not run.native_usage or run.native_usage[0].billable is None
            else "TRUE" if run.native_usage[0].billable else "FALSE"
        ),
        "posthoc_estimated_cost": run.pricing.estimated_cost,
        "cost_currency": run.pricing.currency,
        "pricing_version": run.pricing.pricing_version,
        "original_audit_modified": False,
    }
    _write_json(supplement_root / "result.json", result_data)
    rows = "".join(
        f"<li><a href='{escape(s.url, quote=True)}' rel='noopener noreferrer'>"
        f"{escape(s.title or s.url)}</a> — {escape(s.snippet)}</li>"
        for s in run.sources
        if s.url.startswith(("https://", "http://"))
    )
    html = (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<title>RASAi — Complemento externo GEO</title></head><body>"
        "<h1>Complemento externo GEO (após a auditoria)</h1>"
        f"<p>Auditoria original: {escape(audit_id)}; intenção: {escape(intent_id)}; "
        f"status: {escape(run.status)}.</p>"
        "<p>Pesquisa externa Perplexity Search API. Não integra a evidência "
        "original, não altera score/Apdex, nem comprova citação em IA generativa.</p>"
        "<p>AUD original e seu relatório permanecem preservados. "
        "Custos e tempos pertencem somente a este suplemento.</p>"
        f"<ol>{rows}</ol></body></html>"
    )
    (supplement_root / "supplement.html").write_text(html, encoding="utf-8")
    with sqlite3.connect(derived.database) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("supplement SQLite integrity failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("supplement SQLite FK validation failed")
    from rasai.catalog_report_site import _source_fingerprint
    if (
        _digest(original_workspace.database) != source_db_sha
        or _source_fingerprint(original_workspace.database) != source_state_fingerprint
        or _digest(original_workspace.root / "report-catalog" / "manifest.json")
        != source_manifest_sha
    ):
        # Do not retry after a possible billable request; report explicit gate.
        raise RuntimeError("source AUD changed during supplement; intervention required")
    manifest_files = (
        "intent.json", "result.json", "supplement.html", "evidence/audit.db",
    )
    manifest = {
        "version": SUPPLEMENT_VERSION,
        "audit_id": audit_id,
        "intent_id": intent_id,
        "request_fingerprint": fingerprint,
        "run_status": run.status,
        "billability": result_data["billability"],
        "source_audit_db_sha256": source_db_sha,
        "source_catalog_manifest_sha256": source_manifest_sha,
        "files": [
            {
                "path": path,
                "sha256": _digest(supplement_root / path),
                "bytes": (supplement_root / path).stat().st_size,
            }
            for path in manifest_files
        ],
    }
    _write_json(supplement_root / "manifest.json", manifest)
    return GeoSupplementResult(
        audit_id, intent_id, supplement_root, run.status, True,
        "suplemento independente persistido; pacote AUD original não modificado",
        result_data["billability"],
    )
