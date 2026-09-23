"""Thin CLI adapter for the canonical consolidated-report engine."""
from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai consolidate",
        description=(
            "Generate one longitudinal consolidated report from two AUD markers using "
            "the same selection and generation engine used by the interactive console."
        ),
    )
    parser.add_argument("first_audit_id", help="first selected AUD-* marker")
    parser.add_argument("second_audit_id", help="second selected AUD-* marker")
    parser.add_argument("--audits-root", default="audits", help="directory containing AUD workspaces")
    parser.add_argument(
        "--selection-mode",
        choices=("ALL", "SUCCESS_ONLY", "MANUAL"),
        default="ALL",
        help="selection policy for compatible AUDs between the two markers",
    )
    parser.add_argument(
        "--manual-audit-id",
        action="append",
        default=[],
        help="intermediate AUD to include when --selection-mode=MANUAL; may be repeated",
    )
    parser.add_argument(
        "--specialist-ai",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="request the optional longitudinal AI layer",
    )
    parser.add_argument("--ai-provider", default="none", help="AI provider selection for specialist analysis")
    parser.add_argument("--ai-model", help="AI model override")
    parser.add_argument("--ai-reasoning", help="AI reasoning profile")
    parser.add_argument("--ai-timeout-seconds", type=float, default=180.0, help="AI timeout in seconds")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selection_mode != "MANUAL" and args.manual_audit_id:
        raise SystemExit("--manual-audit-id exige --selection-mode=MANUAL")
    if not args.specialist_ai and any((args.ai_model, args.ai_reasoning)):
        raise SystemExit("--ai-model/--ai-reasoning exigem --specialist-ai")
    if args.ai_timeout_seconds <= 0:
        raise SystemExit("--ai-timeout-seconds deve ser > 0")

    from rasai.consolidation.index import ConsolidationIndex
    from rasai.consolidation.selection import resolve_selection
    from rasai.consolidation.service import generate, normalize_filter

    root = Path(args.audits_root)
    index = ConsolidationIndex(root)
    index.refresh()
    selection = resolve_selection(
        index,
        args.first_audit_id,
        args.second_audit_id,
        selection_mode=args.selection_mode,
        manual_audit_ids=args.manual_audit_id,
    )
    filters = normalize_filter(
        devices=(selection.device,),
        urls=(selection.url,),
        audit_ids=selection.audit_ids,
        selection_mode=selection.selection_mode,
        comparison_mode="FIRST_LAST",
        specialist_ai=bool(args.specialist_ai),
        ai_provider=args.ai_provider if args.specialist_ai else None,
        ai_model=args.ai_model if args.specialist_ai else None,
        ai_reasoning=args.ai_reasoning if args.specialist_ai else None,
        ai_timeout_seconds=args.ai_timeout_seconds if args.specialist_ai else None,
    )
    result = generate(root, filters, refresh_index=False)
    print(f"CONS: {result.report_dir.name}")
    print(f"Relatório: {result.report_path}")
    print(f"Manifesto: {result.manifest_path}")
    print(f"Resultado: {'REUTILIZADO' if result.reused else 'NOVO'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
