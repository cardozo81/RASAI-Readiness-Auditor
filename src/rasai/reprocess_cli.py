"""CLI for selective recovery of one existing logical AUD."""
from __future__ import annotations

import argparse
from pathlib import Path

from rasai.audit_fulfillment import list_work_items, read_summary
from rasai.audit_reprocess import reprocess_audit
from rasai.persistence import AuditWorkspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai reprocess",
        description=(
            "Reprocess only unresolved requirements of an existing AUD. Successful work-items are reused; "
            "the AUD remains one logical observation regardless of the number of RPR attempts."
        ),
    )
    parser.add_argument("audit_id", help="existing AUD-* identifier")
    parser.add_argument("--audits-root", default="audits", help="directory containing AUD workspaces")
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="show the current fulfillment contract without executing retries",
    )
    return parser


def _print_status(workspace: AuditWorkspace, audit_id: str) -> None:
    summary = read_summary(workspace,audit_id)
    if summary is None:
        print("Contrato de processamento: ainda não materializado; execute o reprocessamento para indexar o AUD atual.")
    else:
        print(f"Processamento: {summary.processing_status}")
        print(f"Score: {summary.score_status}")
        print(f"Relatório: {summary.report_status}")
        print(f"Consolidação: {'ELEGÍVEL' if summary.consolidation_eligible else 'NÃO ELEGÍVEL'}")
        print(f"Requisitos atendidos: {summary.successful_items}/{summary.required_items}")
        print(f"Tentativas registradas: {summary.total_attempts}")
        print(f"Reprocessamentos: {summary.reprocess_count}")
        if summary.expired_items:
            print(f"Requisitos live fora da janela de recuperação: {summary.expired_items}")
    try:
        items = list_work_items(workspace,audit_id)
    except Exception:
        items = ()
    if items:
        print("Work-items:")
        for item in items:
            required = "obrigatório" if item.required else "opcional"
            print(
                f"  - {item.component}/{item.scope_key}: {item.status} ({required}; "
                f"tentativas={item.attempt_count}; modo={item.temporal_mode})"
            )
            if item.last_error_code:
                print(f"    último erro: {item.last_error_code}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    workspace_path = Path(args.audits_root) / args.audit_id
    workspace = AuditWorkspace.open(workspace_path)
    if args.status_only:
        _print_status(workspace,args.audit_id)
        return 0

    result = reprocess_audit(args.audit_id,audits_root=args.audits_root,source="CLI")
    print(f"AUD: {result.audit_id}")
    print(f"Reprocessamento: {result.reprocess_id or 'NENHUM - AUD já integralmente atendido'}")
    print(f"Processamento: {result.processing_status}")
    print(f"Score: {result.score_status}")
    print(f"Relatório: {result.report_status}")
    print(f"Consolidação: {'ELEGÍVEL' if result.consolidation_eligible else 'NÃO ELEGÍVEL'}")
    print(f"Itens tentados nesta execução: {result.attempted_items}")
    print(f"Itens resolvidos nesta execução: {result.successful_items}")
    print(f"Sucessos preservados sem nova execução: {result.skipped_success_items}")
    print(f"Itens ainda pendentes/bloqueados: {result.remaining_items}")
    if result.temporal_expired_items:
        print(
            "Validade temporal: há requisito(s) live fora da janela de recuperação; "
            "um novo AUD é necessário para manter consistência metodológica."
        )
    print(f"Relatórios: {result.report_root}")
    return 0 if result.consolidation_eligible else 4
