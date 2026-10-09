"""#318: external GEO supplement for a *completed, sealed* RASAi AUD.

The source AUD and its report-catalog remain strictly read-only. A separate,
versioned, audit-linked SQLite workspace hosts Perplexity Search API provenance
and its existing M18 pricing/attempt ledger. Never rerun collectors, scoring,
SERP, other AI, PSI or Apdex. A local intent reservation is *at most one send*,
not a commercial idempotency guarantee after unknown network outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape
import json
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


def _write_json(path: Path, data: dict[str, Any]) -> None:
    pending = path.with_name(path.name + ".tmp")
    pending.write_text(
        json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(pending, path)


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
    return GeoSupplementResult(
        audit_id, intent_id, directory, "ALREADY_RECORDED", False,
        f"Reutilizado suplemento independente: {manifest.get('run_status', 'UNKNOWN')}",
        str(manifest.get("billability") or "UNKNOWN"),
    )


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
        original_workspace.root.parent
        / ".rasai-geo-supplements"
        / audit_id
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
