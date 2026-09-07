"""CLI inspection for the current SCORE-GEO-004 scoring contract."""
from __future__ import annotations

import argparse

from rasai.score_geo_004 import (
    FEATURE_ORDER,
    MIN_OVERALL_COVERAGE,
    MIN_PARTIAL_COVERAGE,
    OVERALL_AGGREGATION_VERSION,
    SCORING_VERSION,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai scoring",
        description="Inspeciona o contrato de scoring vigente do RASAi.",
    )
    subparsers = parser.add_subparsers(dest="scoring_command", required=True)
    subparsers.add_parser("inspect", help="mostrar versão, fórmula e gates do método vigente")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.scoring_command == "inspect":
        print(f"Scoring vigente: {SCORING_VERSION}")
        print(f"Overall: {OVERALL_AGGREGATION_VERSION}")
        print(f"Dimensões: {len(FEATURE_ORDER)}")
        print(f"Coverage mínima para consolidar: {MIN_OVERALL_COVERAGE * 100:.0f}%")
        print("Confidence mínima para consolidar: MEDIUM")
        print(f"Coverage mínima para resultado parcial: {MIN_PARTIAL_COVERAGE * 100:.0f}%")
        print("Calibração externa: não requerida e não usada como input do score")
        print("Lighthouse/CWV/Accessibility/Apdex: independentes do SARI-001")
        return 0
    parser.error(f"comando scoring não suportado: {args.scoring_command}")
    return 2
