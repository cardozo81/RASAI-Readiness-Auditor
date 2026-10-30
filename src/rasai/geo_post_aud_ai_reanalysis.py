"""Post-AUD consultative AI/Search replay: local-only initial scope (#682).

This standalone preflight and optional derived package never executes any
provider, reprocess collector, or writes to the original sealed AUD. Paid
re-inference/new Perplexity acquisition are deliberately separate consented
operations, not an implicit replay of historical evidence.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Sequence
from uuid import uuid4

CONTRACT = "RASAI-POST-AUD-INTEGRATION-REANALYSIS-1"


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def inspect_completed_audit(aud_dir: Path) -> dict:
    """Read-only eligibility matrix of canonical persisted AI/Search inputs."""
    from rasai.geo_post_audit_complement import _sealed_audit
    root = Path(aud_dir)
    if root.is_symlink() or not root.is_dir() or (root / "audit.db").is_symlink():
        raise ValueError("AUD path must be a non-symlink directory")
    db = root / "audit.db"
    if not db.is_file():
        raise ValueError("AUD database missing")
    audit_id = root.name
    if not audit_id.startswith("AUD-"):
        raise ValueError("invalid AUD identity")
    workspace = SimpleNamespace(root=root, database=db)
    # Reuse canonical COMPLETE, physical database/manifest integrity and
    # catalog freshness gate. Never bypass it for optional analysis.
    source_sha, manifest_sha, source_fingerprint = _sealed_audit(
        workspace, audit_id,
    )
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as con:
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        search_rows = []
        if "perplexity_search_runs" in tables:
            search_rows = con.execute(
                "SELECT run_id,query_json,status FROM perplexity_search_runs "
                "WHERE audit_id=? ORDER BY started_at,run_id", (audit_id,),
            ).fetchall()
        evidence = []
        if "perplexity_search_sources" in tables:
            evidence = con.execute(
                "SELECT s.run_id, COUNT(*) FROM perplexity_search_sources s "
                "JOIN perplexity_search_runs r ON s.run_id=r.run_id "
                "WHERE r.audit_id=? GROUP BY s.run_id", (audit_id,),
            ).fetchall()
        ai_rows = []
        if "geo_ai_interpretations" in tables:
            ai_rows = con.execute(
                "SELECT perplexity_run_id,state FROM geo_ai_interpretations "
                "WHERE audit_id=?", (audit_id,),
            ).fetchall()
    sources_by_run = {str(key): int(count) for key, count in evidence}
    interpretations = {str(key): str(state) for key, state in ai_rows}
    per_query = []
    for run_id, raw, state in search_rows:
        try:
            queries = json.loads(raw)
        except (ValueError, TypeError):
            queries = None
        if not isinstance(queries, list) or not queries or len(queries) > 5:
            queries = []
        per_query.append({
            "run_id": str(run_id), "queries": queries, "search_status": state,
            "source_count": sources_by_run.get(str(run_id), 0),
            "geo_ai_state": interpretations.get(str(run_id), "NOT_EXECUTED"),
            "source_attribution": (
                "PHYSICAL_SINGLE_QUERY" if len(queries) == 1
                else "NOT_PROVEN_MULTIQUERY"
            ),
        })
    eligible = sum(
        1 for row in per_query
        if row["search_status"] == "SUCCESS"
        and row["source_count"] > 0
        and row["source_attribution"] == "PHYSICAL_SINGLE_QUERY"
    )
    return {
        "contract": CONTRACT,
        "audit_id": audit_id,
        "source_sha256": source_sha,
        "catalog_manifest_sha256": manifest_sha,
        "source_state_fingerprint": source_fingerprint,
        "original_audit_mutated": False,
        "provider_calls": 0,
        "operations": [
            {"operation": "GEO_LOCAL_EVIDENCE_REPLAY", "state":
             "ELIGIBLE" if eligible else "NOT_ELIGIBLE",
             "eligible_query_count": eligible,
             "execution": "LOCAL_DERIVED_ONLY", "new_external_requests": 0},
            {"operation": "NEW_CANONICAL_AI_INFERENCE", "state":
             "REQUIRES_EXPLICIT_PAID_AUTHORIZATION", "execution": "NOT_EXECUTED",
             "new_external_requests": 0},
            {"operation": "NEW_PERPLEXITY_RESEARCH", "state":
             "USE_VERSIONED_GEO_SUPPLEMENT", "execution": "NOT_EXECUTED",
             "new_external_requests": 0},
            {"operation": "PHYSICAL_RECOLLECTION", "state": "NOT_ELIGIBLE",
             "execution": "PROHIBITED_IN_THIS_MODE",
             "new_external_requests": 0},
        ],
        "saved_external_observations": per_query,
        "limitation": (
            "Historical Search sources are not generative citations. Local replay "
            "does not produce new provider inference or claim current web evidence."
        ),
    }


def _report_html(report: dict) -> str:
    lines = "".join(
        "<tr><td>" + escape(str(row["run_id"])) + "</td><td>"
        + escape("; ".join(map(str, row["queries"]))) + "</td><td>"
        + escape(str(row["search_status"])) + "</td><td>"
        + escape(str(row["source_count"])) + "</td><td>"
        + escape(str(row["geo_ai_state"])) + "</td></tr>"
        for row in report["saved_external_observations"]
    )
    return (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<title>RASAi — Reanálise consultiva de integrações</title></head><body>"
        "<h1>Reanálise consultiva das evidências persistidas</h1><p>Auditoria "
        + escape(str(report["audit_id"])) + " — origem preservada, zero chamadas externas."
        "</p><p>Esta é uma projeção offline do histórico, não uma nova observação "
        "nem uma nova inferência generativa.</p><table><thead><tr><th>Run</th>"
        "<th>Consulta</th><th>Search</th><th>Fontes</th><th>GEO IA</th>"
        "</tr></thead><tbody>" + lines + "</tbody></table></body></html>"
    )


def publish_local_reanalysis(aud_dir: Path) -> dict:
    """Write only a new, deterministic sidecar after verifying source seals."""
    report = inspect_completed_audit(aud_dir)
    root = Path(aud_dir)
    target_root = root.parent / ".rasai-ai-reanalyses"
    audit_root = target_root / root.name
    if target_root.is_symlink() or audit_root.is_symlink():
        raise ValueError("unsafe reanalysis output directory")
    identity = sha256(_json({
        "contract": CONTRACT, "audit_id": report["audit_id"],
        "source": report["source_sha256"],
        "catalog": report["catalog_manifest_sha256"],
    }).encode("utf-8")).hexdigest()[:32].upper()
    package = audit_root / ("AI-REPLAY-" + identity)
    if package.exists():
        if package.is_symlink() or not package.is_dir():
            raise ValueError("invalid existing reanalysis")
        manifest = json.loads((package / "manifest.json").read_text("utf-8"))
        if manifest.get("source_sha256") != report["source_sha256"]:
            raise ValueError("stale reanalysis package")
        for name in ("reanalysis.json", "reanalysis.html"):
            candidate = package / name
            if candidate.is_symlink() or _hash_file(candidate) != manifest["files"].get(name):
                raise ValueError("reanalysis integrity mismatch")
        return {"state": "ALREADY_RECORDED", "package": str(package),
                "provider_calls": 0, "original_audit_mutated": False}

    audit_root.mkdir(parents=True, exist_ok=True)
    stage = audit_root / (".pending-" + uuid4().hex)
    stage.mkdir()
    try:
        (stage / "reanalysis.json").write_text(_json(report) + "\n", encoding="utf-8")
        (stage / "reanalysis.html").write_text(_report_html(report), encoding="utf-8")
        manifest = {
            "contract": CONTRACT, "audit_id": report["audit_id"],
            "source_sha256": report["source_sha256"],
            "files": {
                name: _hash_file(stage / name)
                for name in ("reanalysis.json", "reanalysis.html")
            },
        }
        (stage / "manifest.json").write_text(_json(manifest) + "\n", encoding="utf-8")
        again = inspect_completed_audit(root)
        if again["source_sha256"] != report["source_sha256"] or (
            again["catalog_manifest_sha256"] != report["catalog_manifest_sha256"]
        ):
            raise ValueError("source AUD changed while deriving analysis")
        stage.rename(package)
    finally:
        if stage.exists():
            for child in stage.iterdir():
                if child.is_file() and not child.is_symlink():
                    child.unlink()
            stage.rmdir()
    return {"state": "PUBLISHED", "package": str(package),
            "provider_calls": 0, "original_audit_mutated": False}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only post-AUD integrations preflight and local replay; no API calls")
    parser.add_argument("audit_dir", type=Path)
    parser.add_argument("--write-local-replay", action="store_true",
                        help="publish a separate offline consultative replay package")
    args = parser.parse_args(argv)
    try:
        result = (publish_local_reanalysis(args.audit_dir)
                  if args.write_local_replay
                  else inspect_completed_audit(args.audit_dir))
        print(_json(result))
        return 0
    except (OSError, ValueError, sqlite3.Error, KeyError) as exc:
        print(_json({"status": "NOT_ELIGIBLE", "reason": str(exc),
                     "provider_calls": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
