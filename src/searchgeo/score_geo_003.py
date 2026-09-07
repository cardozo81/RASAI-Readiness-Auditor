"""SCORE-GEO-003 calibrated model contract and deterministic logistic inference.

SCORE-GEO-003 changes only the Overall aggregation. Dimension evidence, rule
factors, coverage and applicability remain deterministic. A consolidated Overall
is emitted only when a validated calibration artifact is available; the runtime
never fabricates coefficients to keep a number available.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping


SCORING_VERSION = "SCORE-GEO-003"
LEGACY_SCORING_VERSION = "SCORE-GEO-002"
MODEL_FORMAT_VERSION = "SG003-MODEL-001"
DEFAULT_MODEL_VERSION = "GEO-LR-001"
DEFAULT_MODEL_RELATIVE_PATH = Path(".searchgeo") / "scoring" / "score-geo-003-model.json"
MODEL_PATH_ENV = "SEARCHGEO_SCORE_GEO_003_MODEL"

FEATURE_ORDER = (
    "TECHNICAL_ACCESSIBILITY",
    "INDEXABILITY",
    "CONTENT_EXTRACTABILITY",
    "SEMANTIC_STRUCTURE",
    "ENTITY_CLARITY",
    "STRUCTURED_DATA",
    "ANSWERABILITY",
    "CITATION_READINESS",
    "EVIDENCE_TRUST",
    "INTENT_COVERAGE",
)

VALIDATED_STATUS = "VALIDATED"
EXPERIMENTAL_STATUS = "EXPERIMENTAL"


@dataclass(frozen=True, slots=True)
class CalibrationModel:
    format_version: str
    scoring_version: str
    model_version: str
    dataset_version: str
    status: str
    trained_at: str
    intercept: float
    coefficients: dict[str, float]
    imputation_means: dict[str, float]
    engines: tuple[str, ...]
    training: dict[str, float | int | str]
    validation: dict[str, float | int | str]
    protocol: dict[str, Any]
    calibration_confidence: str
    artifact_sha256: str

    @property
    def validated(self) -> bool:
        return self.status == VALIDATED_STATUS

    def predict_probability(self, values: Mapping[str, float | None]) -> float:
        if not self.validated:
            raise ValueError("SCORE-GEO-003 requires a VALIDATED calibration model")
        linear = self.intercept
        for feature in FEATURE_ORDER:
            value = values.get(feature)
            if value is None:
                value = self.imputation_means[feature]
            numeric = float(value)
            if not 0.0 <= numeric <= 1.0:
                raise ValueError(f"feature {feature} must be normalized to 0..1")
            linear += self.coefficients[feature] * numeric
        if linear >= 0:
            exp = math.exp(-linear)
            return 1.0 / (1.0 + exp)
        exp = math.exp(linear)
        return exp / (1.0 + exp)


def resolve_model_path(workspace_root: Path | None = None) -> Path:
    override = os.getenv(MODEL_PATH_ENV)
    if override:
        return Path(override).expanduser()
    if workspace_root is not None:
        root = Path(workspace_root)
        if root.parent.name == "audits":
            return root.parent.parent / DEFAULT_MODEL_RELATIVE_PATH
    return Path.cwd() / DEFAULT_MODEL_RELATIVE_PATH


def load_model(path: str | Path, *, require_validated: bool = True) -> CalibrationModel:
    model_path = Path(path)
    raw = model_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid SCORE-GEO-003 model JSON: {model_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("SCORE-GEO-003 model root must be a JSON object")
    model = _parse_model(payload, digest)
    if require_validated and not model.validated:
        raise ValueError(
            f"SCORE-GEO-003 model {model.model_version} is {model.status}; VALIDATED is required"
        )
    return model


def load_model_for_workspace(workspace_root: Path, *, require_validated: bool = True) -> CalibrationModel | None:
    path = resolve_model_path(workspace_root)
    if not path.is_file():
        return None
    try:
        return load_model(path, require_validated=require_validated)
    except (OSError, ValueError):
        return None


def write_model(path: str | Path, payload: Mapping[str, Any]) -> CalibrationModel:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = dict(payload)
    normalized.setdefault("format_version", MODEL_FORMAT_VERSION)
    normalized.setdefault("scoring_version", SCORING_VERSION)
    normalized.setdefault("model_version", DEFAULT_MODEL_VERSION)
    normalized.setdefault("trained_at", datetime.now(timezone.utc).isoformat())
    raw = (json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    target.write_bytes(raw)
    return load_model(target, require_validated=False)


def model_trace_limitations(model: CalibrationModel) -> tuple[str, ...]:
    return (
        f"CALIBRATION_MODEL:{model.model_version}",
        f"CALIBRATION_DATASET:{model.dataset_version}",
        f"CALIBRATION_MODEL_SHA256:{model.artifact_sha256}",
    )


def _parse_model(payload: Mapping[str, Any], digest: str) -> CalibrationModel:
    if payload.get("format_version") != MODEL_FORMAT_VERSION:
        raise ValueError(f"model format_version must be {MODEL_FORMAT_VERSION}")
    if payload.get("scoring_version") != SCORING_VERSION:
        raise ValueError(f"model scoring_version must be {SCORING_VERSION}")
    model_version = _required_text(payload, "model_version")
    dataset_version = _required_text(payload, "dataset_version")
    status = _required_text(payload, "status").upper()
    if status not in {VALIDATED_STATUS, EXPERIMENTAL_STATUS}:
        raise ValueError("model status must be VALIDATED or EXPERIMENTAL")
    trained_at = _required_text(payload, "trained_at")
    intercept = _finite_float(payload.get("intercept"), "intercept")

    feature_order = payload.get("feature_order")
    if tuple(feature_order or ()) != FEATURE_ORDER:
        raise ValueError("model feature_order does not match SCORE-GEO-003 contract")

    coefficients = _feature_map(payload.get("coefficients"), "coefficients")
    imputation_means = _feature_map(payload.get("imputation_means"), "imputation_means")
    if any(not 0.0 <= value <= 1.0 for value in imputation_means.values()):
        raise ValueError("imputation_means must be normalized to 0..1")

    engines_raw = payload.get("engines")
    if not isinstance(engines_raw, list) or not engines_raw or any(not isinstance(v, str) or not v.strip() for v in engines_raw):
        raise ValueError("engines must be a non-empty list of strings")
    engines = tuple(sorted(dict.fromkeys(v.strip() for v in engines_raw)))

    training = _object(payload.get("training"), "training")
    validation = _object(payload.get("validation"), "validation")
    protocol = _object(payload.get("protocol"), "protocol")
    confidence = _required_text(payload, "calibration_confidence").upper()
    if confidence not in {"HIGH", "MEDIUM", "LOW"}:
        raise ValueError("calibration_confidence must be HIGH, MEDIUM or LOW")

    return CalibrationModel(
        format_version=MODEL_FORMAT_VERSION,
        scoring_version=SCORING_VERSION,
        model_version=model_version,
        dataset_version=dataset_version,
        status=status,
        trained_at=trained_at,
        intercept=intercept,
        coefficients=coefficients,
        imputation_means=imputation_means,
        engines=engines,
        training=dict(training),
        validation=dict(validation),
        protocol=dict(protocol),
        calibration_confidence=confidence,
        artifact_sha256=digest,
    )


def _feature_map(value: Any, field: str) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != set(FEATURE_ORDER):
        raise ValueError(f"{field} must contain exactly the ten SCORE-GEO-003 features")
    return {feature: _finite_float(value[feature], f"{field}.{feature}") for feature in FEATURE_ORDER}


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a JSON object")
    return dict(value)


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _finite_float(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field} must be finite")
    return numeric
