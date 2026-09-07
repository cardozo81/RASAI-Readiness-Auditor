"""CLI for SCORE-GEO-003 calibration, dataset readiness and model inspection."""
from __future__ import annotations

import argparse
from pathlib import Path

from searchgeo.runtime_paths import CANONICAL_RUNTIME_DIR
from searchgeo.score_geo_003 import load_model, write_model
from searchgeo.score_geo_003_calibration import collect_calibration_rows, fit_calibration_model
from searchgeo.score_geo_003_dataset import build_dataset_manifest, write_dataset_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai scoring",
        description="Prepara dataset, calibra e inspeciona o modelo versionado do SCORE-GEO-003.",
    )
    subparsers = parser.add_subparsers(dest="scoring_command", required=True)
    scoring_dir = Path(CANONICAL_RUNTIME_DIR) / "scoring"

    dataset = subparsers.add_parser("dataset", help="materializar dataset elegível e avaliar gates pré-fit")
    dataset.add_argument("--audits-root", default="audits", help="diretório com AUD-*/audit.db")
    dataset.add_argument("--dataset-version", required=True, help="versão imutável do dataset, por exemplo GEO-CAL-001")
    dataset.add_argument(
        "--output",
        default=str(scoring_dir / "score-geo-003-dataset.json"),
        help="manifest JSON do dataset",
    )

    calibrate = subparsers.add_parser("calibrate", help="calibrar modelo a partir de AUDs + query-runs observados")
    calibrate.add_argument("--audits-root", default="audits", help="diretório com AUD-*/audit.db")
    calibrate.add_argument("--dataset-version", required=True, help="versão imutável do dataset, por exemplo GEO-CAL-001")
    calibrate.add_argument(
        "--output",
        default=str(scoring_dir / "score-geo-003-model.json"),
        help="artifact JSON do modelo; por padrão .rasai/scoring/score-geo-003-model.json",
    )

    inspect = subparsers.add_parser("inspect", help="inspecionar artifact SCORE-GEO-003")
    inspect.add_argument(
        "--model",
        default=str(scoring_dir / "score-geo-003-model.json"),
        help="artifact JSON do modelo",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.scoring_command == "dataset":
            collection = collect_calibration_rows(args.audits_root)
            payload = build_dataset_manifest(collection, dataset_version=args.dataset_version)
            path = write_dataset_manifest(args.output, payload)
            print(f"SCORE-GEO-003 dataset manifest: {path}")
            print(f"Status: {payload['status']}")
            print(f"Dataset: {payload['dataset_version']}")
            print(f"SHA-256: {payload['dataset_sha256']}")
            summary = payload["summary"]
            print(
                f"Rows={summary['rows']} domains={summary['domains']} "
                f"observations={summary['observations']} engines={', '.join(summary['engines']) or '-'}"
            )
            print(f"AUDs ignorados: {summary['skipped_audits']}")
            for name, gate in payload["gates"].items():
                print(f"{'PASS' if gate['pass'] else 'FAIL'} {name}: {gate['actual']} / mínimo {gate['minimum']}")
            print("Observação: AUC e Brier só podem ser avaliados após fitting/holdout; READY_FOR_MODEL_FIT != VALIDATED.")
            return 0

        if args.scoring_command == "calibrate":
            collection = collect_calibration_rows(args.audits_root)
            fit = fit_calibration_model(collection.rows, dataset_version=args.dataset_version)
            model = write_model(args.output, fit.payload)
            print(f"SCORE-GEO-003 calibration artifact: {Path(args.output)}")
            print(f"Status: {model.status}")
            print(f"Modelo: {model.model_version}")
            print(f"Dataset: {model.dataset_version}")
            print(f"Engines: {', '.join(model.engines)}")
            print(f"Confidence da calibração: {model.calibration_confidence}")
            print(f"AUDs/linhas elegíveis: {len(collection.rows)}")
            print(f"AUDs ignorados: {len(collection.skipped)}")
            validation = model.validation
            print(
                "Validação: "
                f"domains={validation.get('domains')} observations={validation.get('observations')} "
                f"AUC={float(validation.get('auc', 0.0)):.4f} "
                f"Brier={float(validation.get('brier', 0.0)):.4f}"
            )
            if fit.promotion_reasons:
                print("Promotion gate: NÃO ATENDIDO")
                for reason in fit.promotion_reasons:
                    print(f"- {reason}")
                print("O runtime não usará este artifact para consolidar SCORE-GEO-003 enquanto status != VALIDATED.")
            else:
                print("Promotion gate: ATENDIDO — artifact VALIDATED")
            return 0

        if args.scoring_command == "inspect":
            model = load_model(args.model, require_validated=False)
            print(f"SCORE-GEO-003 model: {args.model}")
            print(f"Status: {model.status}")
            print(f"Modelo: {model.model_version}")
            print(f"Dataset: {model.dataset_version}")
            print(f"Treinado em: {model.trained_at}")
            print(f"Engines: {', '.join(model.engines)}")
            print(f"Confidence da calibração: {model.calibration_confidence}")
            print(f"SHA-256: {model.artifact_sha256}")
            return 0
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    parser.error(f"comando scoring não suportado: {args.scoring_command}")
    return 2
