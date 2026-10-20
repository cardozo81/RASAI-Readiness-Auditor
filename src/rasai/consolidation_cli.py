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
        "--comparison-mode",
        choices=("SAME_URL_LONGITUDINAL", "SAME_DOMAIN_COMPARATIVE"),
        default="SAME_URL_LONGITUDINAL",
        help="strict same-URL CONS-3 (default), or standalone same-host CDOM",
    )
    parser.add_argument(
        "--additional-audit-id", action="append", default=[],
        help="extra explicit source AUD for same-domain comparison (2..100)",
    )
    parser.add_argument(
        "--verify-source-bytes", action="store_true",
        help="required for same-domain comparison: bounded physical SHA-256",
    )
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

    if args.comparison_mode == "SAME_DOMAIN_COMPARATIVE":
        # Never pass different URLs through the production CONS-3 selector,
        # history generator, AI routing or an implicit index refresh.
        if args.selection_mode != "ALL" or args.manual_audit_id:
            raise SystemExit("SAME_DOMAIN_COMPARATIVE não aceita seleção longitudinal")
        if args.specialist_ai or args.ai_provider.strip().lower() != "none" or any(
            (args.ai_model, args.ai_reasoning)
        ):
            raise SystemExit("SAME_DOMAIN_COMPARATIVE não admite IA ou provedores")
        if not args.verify_source_bytes:
            raise SystemExit("SAME_DOMAIN_COMPARATIVE exige --verify-source-bytes")
        import sqlite3
        from rasai.consolidation.domain_comparative_package import (
            materialize_same_domain_package,
        )
        try:
            outcome = materialize_same_domain_package(
                Path(args.audits_root),
                (args.first_audit_id, args.second_audit_id, *args.additional_audit_id),
                verify_source_bytes=True,
            )
        except (ValueError, OSError, sqlite3.DatabaseError) as exc:
            raise SystemExit(f"Comparação não publicada: {exc}") from exc
        print(f"CDOM: {outcome['package_id']}")
        print(f"Relatório: {outcome['html_path']}")
        print(f"Manifesto: {outcome['manifest_path']}")
        print(f"Resultado: {outcome['status']}")
        print("Comparação descritiva entre URLs: sem deltas de score, Apdex ou CWV.")
        return 0
    if args.additional_audit_id or args.verify_source_bytes:
        raise SystemExit(
            "--additional-audit-id/--verify-source-bytes exigem SAME_DOMAIN_COMPARATIVE"
        )

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
