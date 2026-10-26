"""Issue #659: one-shot physical acceptance, with read-only preflight by default.

No network is contacted unless --authorize-active-network is supplied together
with an exact permitted public hostname already belonging to this AUD.
External network consent and target ownership must be established by operator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_acceptance(
    workspace: str | Path, audit_id: str, *, host: str | None = None,
    permitted_hostname: str | None = None, authorized: bool = False,
    include_traceroute: bool = False, series_id: str | None = None,
    asn_database: str | None = None, city_database: str | None = None,
) -> dict[str, Any]:
    """Create at most one approved probe and rebuild only derived catalog HTML."""
    from rasai.network_active_probe import (
        _ID, _audit_has_target, _host, collect_authorized_probe,
        read_authorized_probes,
    )
    from rasai.persistence import AuditWorkspace

    root = Path(workspace)
    result: dict[str, Any] = {
        "contract": "RASAI-659-ACCEPTANCE-001",
        "audit_id": audit_id,
        "status": "INVALID_WORKSPACE",
        "active_probe_executed": False,
        "audit_database_unchanged": None,
        "catalog_rebuilt_read_only": False,
        "catalog_integrity_verified": False,
        "network_report_present": False,
    }
    db = root / "audit.db"
    if (not isinstance(audit_id, str) or not _ID.fullmatch(audit_id)
            or root.is_symlink() or db.is_symlink() or not db.is_file()
            or (root / "artifacts").is_symlink()):
        return result
    try:
        workspace_obj = AuditWorkspace.open(root)
        before = _sha256_file(db)
        from rasai.network_active_probe import read_authorized_probes
        result["existing_probe_count"] = len(read_authorized_probes(root, audit_id))
        if host is not None:
            validated_host = _host(host)
            result["target_in_original_audit"] = _audit_has_target(
                root, audit_id, validated_host,
            )
        else:
            validated_host = None
            result["target_in_original_audit"] = None
    except (OSError, ValueError, TypeError):
        return result

    result["audit_database_unchanged"] = True
    if not authorized:
        result["status"] = "PREFLIGHT_READ_ONLY"
        return result
    if (validated_host is None or permitted_hostname is None
            or _host(permitted_hostname) != validated_host
            or not result["target_in_original_audit"]):
        result["status"] = "ACTIVE_SCOPE_NOT_AUTHORIZED"
        return result

    try:
        path = collect_authorized_probe(
            root, audit_id, validated_host, permitted_hostname=permitted_hostname,
            authorized=True, include_traceroute=include_traceroute,
            series_id=series_id, asn_database=asn_database,
            city_database=city_database,
        )
        result["active_probe_executed"] = True
        accepted = read_authorized_probes(root, audit_id)
        if not any(row.get("audit_id") == audit_id and
                   row.get("hostname") == validated_host for row in accepted):
            result["status"] = "PROBE_INTEGRITY_FAILED"
            return result
        result["verified_probe_count"] = len(accepted)
        result["probe_states"] = sorted({
            row.get("state") for row in accepted if isinstance(row.get("state"), str)
        })
        # This is strictly the approved read-only projection boundary. It never
        # performs new network probing or rewrites captured AUD evidence.
        from rasai.report_completion import materialize_catalog_report_projection
        completion = materialize_catalog_report_projection(
            audit_id=audit_id, workspace=workspace_obj, read_only=True,
        )
        if completion.renderer_errors:
            result["status"] = "CATALOG_REBUILD_FAILED"
            result["catalog_error_types"] = [
                text.split(":", 2)[1] if ":" in text else "RuntimeError"
                for text in completion.renderer_errors[:4]
            ]
            return result
        result["catalog_rebuilt_read_only"] = True
        from rasai.catalog_report_site import (
            verify_catalog_report_package, catalog_report_is_fresh,
        )
        report_dir = root / "report-catalog"
        ok, _errors = verify_catalog_report_package(report_dir)
        fresh = catalog_report_is_fresh(audit_id=audit_id, workspace=workspace_obj)
        page = report_dir / "network.html"
        result["network_report_present"] = page.is_file()
        report_html = page.read_text(encoding="utf-8") if page.is_file() else ""
        result["offline_report_includes_probe"] = (
            "Medição complementar autorizada" in report_html
            and validated_host in report_html
        )
        result["catalog_integrity_verified"] = bool(ok and fresh)
        result["status"] = (
            "TECHNICAL_ACCEPTANCE_READY_FOR_HUMAN_REVIEW"
            if result["catalog_integrity_verified"] and
               result["offline_report_includes_probe"]
            else "REPORT_EVIDENCE_INCOMPLETE"
        )
    except (OSError, ValueError, TypeError, RuntimeError, TimeoutError, FileExistsError) as error:
        result["status"] = "ACCEPTANCE_FAILED"
        result["failure_type"] = type(error).__name__
    finally:
        try:
            result["audit_database_unchanged"] = _sha256_file(db) == before
        except OSError:
            result["audit_database_unchanged"] = False
        if not result["audit_database_unchanged"]:
            result["status"] = "AUDIT_DATABASE_CHANGED_REQUIRES_INVESTIGATION"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Issue 659 - avaliação técnica segura da observabilidade de rede")
    parser.add_argument("--workspace", required=True, type=Path,
                        help="Diretório de uma AUD existente contendo audit.db")
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--host", help="Hostname do alvo aprovado, sem URL ou parâmetros")
    parser.add_argument("--permit-exact-host", help="Hostname com autorização expressa")
    parser.add_argument("--authorize-active-network", action="store_true",
                        help="Permite uma sondagem ativa delimitada; sem este flag só há leitura")
    parser.add_argument("--include-traceroute", action="store_true")
    parser.add_argument("--series-id")
    parser.add_argument("--asn-db")
    parser.add_argument("--city-db")
    args = parser.parse_args()
    report = run_acceptance(
        args.workspace, args.audit_id, host=args.host,
        permitted_hostname=args.permit_exact_host,
        authorized=args.authorize_active_network,
        include_traceroute=args.include_traceroute, series_id=args.series_id,
        asn_database=args.asn_db, city_database=args.city_db,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] in {
        "PREFLIGHT_READ_ONLY", "TECHNICAL_ACCEPTANCE_READY_FOR_HUMAN_REVIEW"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
