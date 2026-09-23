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
        description="Inspeciona o Método de Pontuação de Prontidão vigente do RASAi.",
    )
    subparsers = parser.add_subparsers(dest="scoring_command", required=True)
    subparsers.add_parser("inspect", help="mostrar versão pública, contrato técnico, fórmula e critérios críticos do método vigente")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.scoring_command == "inspect":
        print("Método de Pontuação de Prontidão - versão pública 001")
        print(f"Contrato técnico: {SCORING_VERSION}")
        print(f"Agregação técnica: {OVERALL_AGGREGATION_VERSION}")
        print(f"Dimensões: {len(FEATURE_ORDER)}")
        print(f"Coverage mínima para consolidar: {MIN_OVERALL_COVERAGE * 100:.0f}%")
        print("Confiança mínima para consolidar: MEDIUM")
        print(f"Coverage mínima para resultado parcial: {MIN_PARTIAL_COVERAGE * 100:.0f}%")
        print("Calibração externa: não requerida e não usada como entrada da pontuação")
        print("Lighthouse/CWV/Acessibilidade/Apdex: independentes do Índice de Prontidão Search & IA (ID técnico SARI-001)")
        return 0
    parser.error(f"comando de pontuação não suportado: {args.scoring_command}")
    return 2
