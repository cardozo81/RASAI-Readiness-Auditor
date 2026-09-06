"""CLI do M26 — importação/report de Observed Generative Visibility."""
from __future__ import annotations

import argparse
from pathlib import Path

from searchgeo.m26_reporting import enrich_m26_report_site
from searchgeo.m26_visibility import import_visibility_file
from searchgeo.operational_log import try_append_operational_event
from searchgeo.persistence import AuditWorkspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="searchgeo visibility",
        description="Importa outcomes observados de AI Search sem alterar o SearchGEO Readiness Index.",
    )
    subparsers = parser.add_subparsers(dest="visibility_command", required=True)

    import_parser = subparsers.add_parser("import", help="importar JSON normalizado OGV-IMPORT-001")
    _workspace_arguments(import_parser)
    import_parser.add_argument("--file", required=True, help="arquivo JSON UTF-8 no contrato OGV-IMPORT-001")

    report_parser = subparsers.add_parser("report", help="regenerar ai-visibility.html a partir do audit.db")
    _workspace_arguments(report_parser)
    return parser


def _workspace_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--audit-id", required=True, help="audit_id existente, por exemplo AUD-...")
    parser.add_argument("--audits-root", default="audits", help="diretório que contém os workspaces de auditoria")


def _workspace(args: argparse.Namespace) -> AuditWorkspace:
    return AuditWorkspace.open(Path(args.audits_root) / args.audit_id)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        workspace = _workspace(args)
        if args.visibility_command == "import":
            result = import_visibility_file(audit_id=args.audit_id, workspace=workspace, path=args.file)
            report = enrich_m26_report_site(audit_id=args.audit_id, workspace=workspace)
            try_append_operational_event(
                workspace,
                "M26_OBSERVED_GENERATIVE_VISIBILITY_IMPORTED",
                audit_id=args.audit_id,
                import_id=result.import_id,
                source_type=result.source_type,
                capture_method=result.capture_method,
                period_start=result.period_start,
                period_end=result.period_end,
                page_observations=result.page_observations,
                grounding_queries=result.grounding_queries,
                query_runs=result.query_runs,
                valid_query_runs=result.valid_query_runs,
                cited_query_runs=result.cited_query_runs,
                scoring_impact="NONE",
            )
            print(f"Visibilidade generativa importada: {result.import_id}")
            print(f"Fonte declarada: {result.source_type}")
            print(f"Método de captura: {result.capture_method}")
            print(f"Período: {result.period_start} → {result.period_end}")
            print(f"Query-runs válidos: {result.valid_query_runs}/{result.query_runs}")
            if result.citation_presence_rate is not None:
                print(f"Citation Presence Rate: {result.citation_presence_rate * 100:.1f}%")
                print(
                    "IC Wilson 95%: "
                    f"{result.citation_presence_ci95_low * 100:.1f}%–{result.citation_presence_ci95_high * 100:.1f}%"
                )
            print(f"Artifact preservado: {result.artifact_path}")
            print(f"Relatório: {report}")
            print("Impacto no SGRI/SCORE-GEO: NENHUM")
            return 0

        if args.visibility_command == "report":
            report = enrich_m26_report_site(audit_id=args.audit_id, workspace=workspace)
            print(f"Relatório de visibilidade generativa: {report}")
            return 0
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))

    parser.error(f"comando de visibility não suportado: {args.visibility_command}")
    return 2