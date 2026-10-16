"""#375: offline, source-preserving integrity review of one completed AUD.

The v0.8.0 release remains the behavioral baseline; this utility does not
re-run audits, reinterpret SARI/Apdex, materialize reports or open a provider.
It composes the CURRENT canonical catalog report package/freshness verifiers
with SQLite integrity/FK/identity checks and optional console count checks.

No claim is made that deterministic structural integrity proves semantic
accuracy or independently verifies an external provider invoice.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
from typing import Any, Sequence

_BASELINE = "v0.8.0"
_BASELINE_SHA = "4e9a3026ec0bbf6f46a4f30f3659fc2ab5a02a08"
_AUD_ID = re.compile(r"^AUD-[A-Za-z0-9]{10,100}$")
_MAX_ERRORS = 20


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_fingerprints(root: Path) -> dict[str, str]:
    """Track only audit-owned critical files. No chmod/open-for-write calls."""
    paths = (
        root / "audit.db", root / "audit.db-wal",
        root / "report-catalog" / "manifest.json",
        root / "report-catalog" / "integrity" / "audit-snapshot.db",
    )
    return {
        path.relative_to(root).as_posix(): _hash_file(path)
        for path in paths if path.is_file() and not path.is_symlink()
    }


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(con: sqlite3.Connection, name: str) -> set[str]:
    if not _table_exists(con, name):
        return set()
    return {str(row[1]) for row in con.execute("PRAGMA table_info(" + name + ")")}


def _apdex_evidence(con: sqlite3.Connection, audit_id: str, prefix: str) -> dict[str, Any]:
    table, samples = prefix + "_runs", prefix + "_samples"
    required = {"audit_id", "attempted_samples", "valid_samples", "invalid_samples", "status"}
    if not required.issubset(_columns(con, table)):
        return {"status": "NOT_AVAILABLE", "source": table}
    row = con.execute(
        "SELECT attempted_samples,valid_samples,invalid_samples,status "
        f"FROM {table} WHERE audit_id=?", (audit_id,),
    ).fetchall()
    if len(row) != 1:
        return {"status": "NOT_AVAILABLE" if not row else "AMBIGUOUS_RUN", "source": table}
    attempts, valid, invalid, state = row[0]
    expected = [attempts, valid, invalid]
    if any(type(x) is not int or x < 0 for x in expected):
        return {"status": "COUNTERS_INVALID", "source": table}
    count = None
    if "audit_id" in _columns(con, samples):
        count = int(con.execute(
            f"SELECT COUNT(*) FROM {samples} WHERE audit_id=?", (audit_id,),
        ).fetchone()[0])
    consistent = (attempts == valid + invalid and (count is None or attempts == count))
    return {
        "status": "CONSISTENT" if consistent else "COUNTERS_DIVERGE",
        "source": table,
        "run_status": str(state or "N/D"),
        "attempts": attempts, "valid": valid, "invalid": invalid,
        "persisted_samples": count,
    }


def inspect_audit_integrity(
    audit_dir: Path,
    *, expected_ai_attempts: int | None = None,
    expected_web_calls: int | None = None,
    expected_navigation_attempts: int | None = None,
) -> dict[str, Any]:
    """Read an existing AUD without collector bootstrap, mutation or HTTP."""
    root = Path(audit_dir).resolve()
    result: dict[str, Any] = {
        "contract_version": "RASAI-AUD-LOCAL-INTEGRITY-375-001",
        "baseline_tag": _BASELINE, "baseline_commit": _BASELINE_SHA,
        "audit_id": root.name,
        "status": "NOT_VERIFIED",
        "checks": {},
        "observed": {},
        "errors": [],
        "audit_writes": 0, "provider_requests": 0,
        "caveat": (
            "Consistencia SQLite, chaves, registros e pacote final não comprova "
            "exatidão semântica de conclusões externas nem fatura de IA."
        ),
    }
    errors: list[str] = result["errors"]

    if not _AUD_ID.fullmatch(root.name):
        errors.append("IDENTIDADE_DO_DIRETORIO_INVALIDA")
        return result
    original = Path(audit_dir)
    if original.is_symlink() or not root.is_dir():
        errors.append("DIRETORIO_AUD_NAO_SEGURO")
        return result
    db, artifacts, reports = root / "audit.db", root / "artifacts", root / "report-catalog"
    if (
        not db.is_file() or db.is_symlink()
        or not artifacts.is_dir() or artifacts.is_symlink()
    ):
        errors.append("AUD_INCOMPLETA_OU_ARQUIVOS_BASE_AUSENTES")
        return result
    baseline_hashes = _source_fingerprints(root)
    try:
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=5.0) as con:
            con.execute("PRAGMA query_only=ON")
            integrity = [str(row[0]) for row in con.execute("PRAGMA integrity_check").fetchmany(_MAX_ERRORS)]
            result["checks"]["sqlite_integrity"] = integrity == ["ok"]
            if integrity != ["ok"]:
                errors.append("SQLITE_INTEGRITY_CHECK_FAILED")
            violations = con.execute("PRAGMA foreign_key_check").fetchmany(_MAX_ERRORS)
            result["checks"]["foreign_keys"] = not violations
            if violations:
                errors.append("SQLITE_FOREIGN_KEY_VIOLATIONS")
            required = {"audit_id", "status", "completion_status"}
            if not required.issubset(_columns(con, "audits")):
                errors.append("AUDIT_METADATA_SCHEMA_UNAVAILABLE")
            else:
                rows = con.execute(
                    "SELECT status,completion_status FROM audits WHERE audit_id=?",
                    (root.name,),
                ).fetchall()
                all_audits = int(con.execute("SELECT COUNT(*) FROM audits").fetchone()[0])
                result["checks"]["audit_identity"] = len(rows) == all_audits == 1
                if len(rows) != 1 or all_audits != 1:
                    errors.append("AUDIT_IDENTITY_MISMATCH_OR_MULTIPLE_AUDS")
                else:
                    status, completion = rows[0]
                    result["observed"]["audit_status"] = str(status)
                    result["observed"]["completion_status"] = str(completion)
                    result["checks"]["completed"] = str(completion) == "COMPLETE"
                    if str(completion) != "COMPLETE":
                        errors.append("AUD_NOT_COMPLETE")
            for label, prefix in (
                ("navigation_apdex", "synthetic_apdex"),
                ("experience_apdex", "synthetic_ux_apdex"),
            ):
                evidence = _apdex_evidence(con, root.name, prefix)
                result["observed"][label] = evidence
                if evidence["status"] in {"COUNTERS_DIVERGE", "COUNTERS_INVALID", "AMBIGUOUS_RUN"}:
                    errors.append(label.upper() + "_DATA_INCONSISTENT")
            if _table_exists(con, "perplexity_search_runs"):
                columns = _columns(con, "perplexity_search_runs")
                if "audit_id" in columns:
                    result["observed"]["perplexity_runs"] = int(con.execute(
                        "SELECT COUNT(*) FROM perplexity_search_runs WHERE audit_id=?",
                        (root.name,),
                    ).fetchone()[0])
            else:
                result["observed"]["perplexity_runs"] = 0
    except (OSError, sqlite3.Error) as exc:
        errors.append("SQLITE_READ_FAILED:" + type(exc).__name__)
        return result

    # Reuse the production report verifier; do not recreate a parallel
    # interpretation of HTML, manifests, source dependencies or assurances.
    from rasai.catalog_report_site import (
        catalog_report_is_fresh, verify_catalog_report_package,
    )
    if reports.is_symlink() or not reports.is_dir():
        errors.append("REPORT_CATALOG_ABSENT_OR_UNSAFE")
    else:
        ok, problems = verify_catalog_report_package(reports)
        result["checks"]["report_package_sha256_assurance"] = bool(ok)
        if not ok:
            errors.append("REPORT_PACKAGE_INVALID")
            result["observed"]["report_package_problems"] = list(problems[:_MAX_ERRORS])
        try:
            fresh = catalog_report_is_fresh(
                audit_id=root.name, workspace=SimpleNamespace(root=root, database=db),
            )
        except (OSError, RuntimeError, sqlite3.Error) as exc:
            fresh = False
            result["observed"]["freshness_error_class"] = type(exc).__name__
        result["checks"]["report_matches_current_audit"] = bool(fresh)
        if not fresh:
            errors.append("REPORT_SOURCE_MISMATCH_OR_NOT_FINAL")

    # This helper is a read-only projection of both IA ledgers plus WebPerf;
    # counting only ai_provider_attempts would omit Content Remediation.
    from rasai.console_cost import actual_usage
    usage = actual_usage(root)
    if usage is None:
        errors.append("PERSISTED_USAGE_NOT_READABLE")
    else:
        result["observed"]["usage"] = {
            "ai_attempts": usage.ai_attempts,
            "ai_successes": usage.ai_successes,
            "input_tokens": usage.input_tokens,
            "cached_input_tokens": usage.cached_input_tokens,
            "output_tokens": usage.output_tokens,
            "reasoning_tokens": usage.reasoning_tokens,
            "total_tokens": usage.total_tokens,
            "estimated_ai_costs": dict(usage.costs),
            "web_calls": usage.web_external_calls,
            "web_services": dict(usage.web_services),
        }
        if expected_ai_attempts is not None and usage.ai_attempts != expected_ai_attempts:
            errors.append("AI_ATTEMPT_COUNT_VS_CONSOLE_MISMATCH")
        if expected_web_calls is not None and usage.web_external_calls != expected_web_calls:
            errors.append("WEB_CALL_COUNT_VS_CONSOLE_MISMATCH")
    if expected_navigation_attempts is not None:
        nav = result["observed"].get("navigation_apdex", {})
        if nav.get("attempts") != expected_navigation_attempts:
            errors.append("NAVIGATION_APDEX_COUNT_VS_CONSOLE_MISMATCH")
    result["checks"]["source_files_unchanged_by_review"] = (
        _source_fingerprints(root) == baseline_hashes
    )
    if not result["checks"]["source_files_unchanged_by_review"]:
        errors.append("SOURCE_FILES_CHANGED_DURING_REVIEW")
    result["status"] = "STRUCTURALLY_VERIFIED" if not errors else "NOT_VERIFIED"
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only AUD integrity/consistency report; no providers.")
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--expected-ai-attempts", type=int)
    parser.add_argument("--expected-web-calls", type=int)
    parser.add_argument("--expected-navigation-attempts", type=int)
    args = parser.parse_args(argv)
    value = inspect_audit_integrity(
        args.audit_dir,
        expected_ai_attempts=args.expected_ai_attempts,
        expected_web_calls=args.expected_web_calls,
        expected_navigation_attempts=args.expected_navigation_attempts,
    )
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if value["status"] == "STRUCTURALLY_VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
