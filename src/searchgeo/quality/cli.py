"""CLI for derived RASAi audit quality and verification."""
from __future__ import annotations

import argparse
from pathlib import Path

from .reporting import write_quality_report, write_timeline_report, write_verification_report
from .timeline import build_timeline
from .verification import verify_fixes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai quality",
        description="Audit Health, Evidence Confidence, Fix Verification e Evidence Timeline sem alterar SARI.",
    )
    sub = parser.add_subparsers(dest="quality_command", required=True)

    report = sub.add_parser("report", help="gerar report/quality.html para um AUD existente")
    report.add_argument("--audits-root", default="audits")
    report.add_argument("--audit", required=True)

    verify = sub.add_parser("verify", help="validar correções entre baseline e AUD atual")
    verify.add_argument("--audits-root", default="audits")
    verify.add_argument("--baseline", required=True)
    verify.add_argument("--current", required=True)
    verify.add_argument("--url")
    verify.add_argument("--rule-id")
    verify.add_argument("--report-root")

    timeline = sub.add_parser("timeline", help="gerar linha do tempo de evidência sobre AUDs persistidos")
    timeline.add_argument("--audits-root", default="audits")
    timeline.add_argument("--domain")
    timeline.add_argument("--url")
    timeline.add_argument("--report-root")
    return parser


def _workspace(root: str, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_dir() else Path(root) / value


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.quality_command == "report":
            workspace = _workspace(args.audits_root, args.audit)
            path = write_quality_report(workspace)
            print(f"RASAi Quality: {path}")
            return 0
        if args.quality_command == "verify":
            baseline = _workspace(args.audits_root, args.baseline)
            current = _workspace(args.audits_root, args.current)
            bundle = verify_fixes(baseline, current, url=args.url, rule_id=args.rule_id)
            path = write_verification_report(args.audits_root, bundle, report_root=args.report_root)
            print(f"Fix Verification: {bundle.baseline_audit_id} → {bundle.current_audit_id}")
            for status, count in sorted(bundle.counts.items()):
                print(f"{status}: {count}")
            print(f"Relatório: {path}")
            return 0
        if args.quality_command == "timeline":
            bundle = build_timeline(args.audits_root, domain=args.domain, url=args.url)
            path = write_timeline_report(args.audits_root, bundle, report_root=args.report_root)
            print(f"Evidence Timeline AUDs: {len(bundle.points)}")
            print(f"Ignorados: {len(bundle.skipped)}")
            print(f"Relatório: {path}")
            return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"RASAi quality error: {exc}")
        return 2
    return 2
