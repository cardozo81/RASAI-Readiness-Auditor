"""CLI for read-only RASAI monitoring and release gates."""
from __future__ import annotations

import argparse
from pathlib import Path

from .compare import compare_audits, evaluate_release_gate
from .impact import analyze_change_impact, write_impact_report
from .models import GatePolicy
from .reporting import write_monitoring_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai monitor",
        description="Compara auditorias persistidas sem alterar audit.db e detecta regressões/mudanças.",
    )
    sub = parser.add_subparsers(dest="monitor_command", required=True)

    compare = sub.add_parser("compare", help="comparar baseline e auditoria atual; gerar MON-*/report.html")
    _pair(compare)
    compare.add_argument("--report-root", help="diretório opcional para MON-*; padrão <audits-root>/monitoring")

    impact = sub.add_parser("impact", help="comparar também outcomes observados; sem inferir causalidade")
    _pair(impact)
    impact.add_argument("--report-root", help="diretório opcional para MON-*; padrão <audits-root>/monitoring")

    gate = sub.add_parser("gate", help="release gate; 0=PASS, 1=deterioração bloqueante, 2=erro")
    _pair(gate)
    gate.add_argument("--include-semantic", action="store_true", help="permitir regras semânticas/IA no gate")
    gate.add_argument(
        "--allow-new-failures",
        action="store_true",
        help="não bloquear sinais NEW materialmente ruins; use somente quando a mudança de universo for deliberada",
    )
    gate.add_argument("--include-performance", action="store_true", help="incluir Lighthouse/field performance explicitamente")
    gate.add_argument("--include-synthetic", action="store_true", help="incluir Synthetic Navigation/UX Apdex explicitamente")
    gate.add_argument("--include-finding-aggregates", action="store_true", help="incluir contagens agregadas de findings explicitamente")
    gate.add_argument("--include-score-dimensions", action="store_true", help="incluir deltas de dimensões SCORE-GEO-003 explicitamente")
    gate.add_argument("--max-high-regressions", type=int, default=0)
    gate.add_argument("--max-medium-regressions", type=int, default=3)
    gate.add_argument("--dimension-drop-points", type=float, default=5.0)
    return parser


def _pair(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--audits-root", default="audits")
    parser.add_argument("--baseline", required=True, help="audit_id baseline ou caminho do workspace")
    parser.add_argument("--current", required=True, help="audit_id atual ou caminho do workspace")


def _workspace(root: str, value: str) -> Path:
    path = Path(value)
    if path.is_dir():
        return path
    return Path(root) / value


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        baseline = _workspace(args.audits_root, args.baseline)
        current = _workspace(args.audits_root, args.current)
        result = compare_audits(baseline, current)
        if args.monitor_command in {"compare", "impact"}:
            report = write_monitoring_report(args.audits_root, result, report_root=args.report_root)
            print(f"RASAI Monitor: {result.baseline.audit_id} → {result.current.audit_id}")
            print(f"Regressões materiais: {len(result.regressions)}")
            print(f"Melhorias/resoluções: {len(result.improvements)}")
            print(f"Relatório: {report.report_path}")
            print(f"Manifest: {report.manifest_path}")
            if args.monitor_command == "impact":
                analysis = analyze_change_impact(result)
                impact_path = write_impact_report(report.report_dir, result, analysis)
                print(f"Outcomes alterados: {len(analysis.outcome_changes)}")
                print(f"Associações temporais elegíveis: {len(analysis.associations)}")
                for item in analysis.window_comparability:
                    print(
                        f"Janela {item['source']}: {item['status']} | "
                        f"{item.get('baseline_period') or '-'} | {item.get('current_period') or '-'}"
                    )
                print(f"Change Impact: {impact_path}")
            if result.compatibility_notes:
                print("Limitações de comparabilidade:")
                for note in result.compatibility_notes:
                    print(f"- {note}")
            return 0

        if args.monitor_command == "gate":
            policy = GatePolicy(
                deterministic_only=not args.include_semantic,
                block_new_failures=not args.allow_new_failures,
                include_performance=args.include_performance,
                include_synthetic=args.include_synthetic,
                include_finding_aggregates=args.include_finding_aggregates,
                include_score_dimensions=args.include_score_dimensions,
                max_high_regressions=max(0, args.max_high_regressions),
                max_medium_regressions=max(0, args.max_medium_regressions),
                dimension_drop_points=max(0.0, args.dimension_drop_points),
            )
            gate = evaluate_release_gate(result, policy)
            print(f"RASAI Release Gate: {'PASS' if gate.passed else 'FAIL'}")
            print(gate.reason)
            print(f"Regras: {'determinísticas' if policy.deterministic_only else 'inclui semânticas'}")
            print(f"New failures: {'bloqueiam' if policy.block_new_failures else 'permitidos por opt-out'}")
            print(
                "Opt-ins: "
                f"performance={policy.include_performance}, synthetic={policy.include_synthetic}, "
                f"finding_aggregates={policy.include_finding_aggregates}, score_dimensions={policy.include_score_dimensions}"
            )
            for event in gate.blocking_events:
                print(
                    f"BLOCK {event.status} {event.severity} {event.rule_id or event.label} "
                    f"{event.device or '-'} {event.url or '-'}: {event.before!r} → {event.after!r}"
                )
            return 0 if gate.passed else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"RASAI monitor error: {exc}")
        return 2
    parser.error(f"unsupported monitor command: {args.monitor_command}")
    return 2
