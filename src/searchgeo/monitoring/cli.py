"""CLI for read-only RASAI monitoring and release gates."""
from __future__ import annotations

import argparse
from pathlib import Path

from .compare import compare_audits, evaluate_release_gate
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

    gate = sub.add_parser("gate", help="release gate; 0=PASS, 1=regressão bloqueante, 2=erro")
    _pair(gate)
    gate.add_argument("--include-semantic", action="store_true", help="permitir que regras semânticas/IA participem do gate")
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
        if args.monitor_command == "compare":
            report = write_monitoring_report(args.audits_root, result, report_root=args.report_root)
            print(f"RASAI Monitor: {result.baseline.audit_id} → {result.current.audit_id}")
            print(f"Regressões materiais: {len(result.regressions)}")
            print(f"Melhorias/resoluções: {len(result.improvements)}")
            print(f"Relatório: {report.report_path}")
            print(f"Manifest: {report.manifest_path}")
            if result.compatibility_notes:
                print("Limitações de comparabilidade:")
                for note in result.compatibility_notes:
                    print(f"- {note}")
            return 0

        if args.monitor_command == "gate":
            policy = GatePolicy(
                deterministic_only=not args.include_semantic,
                max_high_regressions=max(0, args.max_high_regressions),
                max_medium_regressions=max(0, args.max_medium_regressions),
                dimension_drop_points=max(0.0, args.dimension_drop_points),
            )
            gate = evaluate_release_gate(result, policy)
            print(f"RASAI Release Gate: {'PASS' if gate.passed else 'FAIL'}")
            print(gate.reason)
            print(f"Modo: {'determinístico' if policy.deterministic_only else 'inclui semântico'}")
            for event in gate.blocking_events:
                print(
                    f"BLOCK {event.severity} {event.rule_id or event.label} "
                    f"{event.device or '-'} {event.url or '-'}: {event.before!r} → {event.after!r}"
                )
            return 0 if gate.passed else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"RASAI monitor error: {exc}")
        return 2
    parser.error(f"unsupported monitor command: {args.monitor_command}")
    return 2
