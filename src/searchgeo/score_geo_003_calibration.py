"""Empirical calibration pipeline for SCORE-GEO-003.

The calibrator consumes previously persisted SearchGEO dimension scores and
Observed Generative Visibility controlled query-runs. Domains, not queries, are
the holdout unit. The implementation is intentionally small and transparent:
a regularized logistic model is trained with deterministic gradient descent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import sqlite3
from typing import Any, Iterable
from urllib.parse import urlsplit

from searchgeo.score_geo_003 import (
    DEFAULT_MODEL_VERSION,
    EXPERIMENTAL_STATUS,
    FEATURE_ORDER,
    MODEL_FORMAT_VERSION,
    SCORING_VERSION,
    VALIDATED_STATUS,
)


MIN_DOMAINS = 40
MIN_VALIDATION_DOMAINS = 12
MIN_ENGINES = 2
MIN_QUERIES_PER_DOMAIN = 10
MIN_REPETITIONS = 3
MIN_OBSERVATIONS = 2400
TRAIN_FRACTION = 0.70
L2_REGULARIZATION = 0.50
MAX_ITERATIONS = 4000
LEARNING_RATE = 0.35
MIN_VALIDATION_AUC = 0.60


@dataclass(frozen=True, slots=True)
class CalibrationRow:
    domain: str
    audit_id: str
    device: str
    features: dict[str, float | None]
    successes: int
    total: int
    engines: tuple[str, ...]
    query_count: int
    min_repetitions: int

    @property
    def failures(self) -> int:
        return self.total - self.successes


@dataclass(frozen=True, slots=True)
class CalibrationCollection:
    rows: tuple[CalibrationRow, ...]
    skipped: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FitResult:
    payload: dict[str, Any]
    promotion_reasons: tuple[str, ...]

    @property
    def validated(self) -> bool:
        return self.payload["status"] == VALIDATED_STATUS


def collect_calibration_rows(audits_root: str | Path) -> CalibrationCollection:
    root = Path(audits_root)
    rows: list[CalibrationRow] = []
    skipped: list[str] = []
    for database in sorted(root.glob("AUD-*/audit.db")):
        try:
            collected = _collect_database(database)
        except (OSError, sqlite3.Error, ValueError) as exc:
            skipped.append(f"{database.parent.name}:{type(exc).__name__}:{exc}")
            continue
        if not collected:
            skipped.append(f"{database.parent.name}:NO_ELIGIBLE_CONTROLLED_VISIBILITY")
            continue
        rows.extend(collected)
    return CalibrationCollection(tuple(rows), tuple(skipped))


def fit_calibration_model(rows: Iterable[CalibrationRow], *, dataset_version: str) -> FitResult:
    dataset_version = dataset_version.strip()
    if not dataset_version:
        raise ValueError("dataset_version is required")
    materialized = tuple(rows)
    if not materialized:
        raise ValueError("no eligible calibration rows")

    domains = sorted({row.domain for row in materialized}, key=_stable_key)
    split = max(1, min(len(domains) - 1, int(len(domains) * TRAIN_FRACTION))) if len(domains) > 1 else 1
    train_domains = set(domains[:split])
    validation_domains = set(domains[split:])
    train_rows = tuple(row for row in materialized if row.domain in train_domains)
    validation_rows = tuple(row for row in materialized if row.domain in validation_domains)

    if not validation_rows:
        validation_rows = train_rows
        validation_domains = train_domains

    imputation = _imputation_means(train_rows)
    intercept, coefficients = _fit_logistic(train_rows, imputation)

    train_predictions = _predictions(train_rows, intercept, coefficients, imputation)
    validation_predictions = _predictions(validation_rows, intercept, coefficients, imputation)
    train_metrics = _metrics(train_rows, train_predictions, baseline_rate=None)
    train_prevalence = float(train_metrics["positive_rate"])
    validation_metrics = _metrics(validation_rows, validation_predictions, baseline_rate=train_prevalence)

    engines = sorted({engine for row in materialized for engine in row.engines})
    unique_queries = sum(row.query_count for row in materialized)
    observations = _weighted_count(materialized)
    domain_count = len({row.domain for row in materialized})
    validation_domain_count = len(validation_domains)

    reasons: list[str] = []
    if domain_count < MIN_DOMAINS:
        reasons.append(f"DOMAINS_BELOW_MINIMUM:{domain_count}<{MIN_DOMAINS}")
    if validation_domain_count < MIN_VALIDATION_DOMAINS:
        reasons.append(f"VALIDATION_DOMAINS_BELOW_MINIMUM:{validation_domain_count}<{MIN_VALIDATION_DOMAINS}")
    if len(engines) < MIN_ENGINES:
        reasons.append(f"ENGINES_BELOW_MINIMUM:{len(engines)}<{MIN_ENGINES}")
    if observations < MIN_OBSERVATIONS:
        reasons.append(f"OBSERVATIONS_BELOW_MINIMUM:{observations}<{MIN_OBSERVATIONS}")
    if any(row.query_count < MIN_QUERIES_PER_DOMAIN for row in materialized):
        reasons.append("QUERY_COVERAGE_BELOW_MINIMUM")
    if any(row.min_repetitions < MIN_REPETITIONS for row in materialized):
        reasons.append("REPETITIONS_BELOW_MINIMUM")
    auc = float(validation_metrics["auc"])
    if auc < MIN_VALIDATION_AUC:
        reasons.append(f"VALIDATION_AUC_BELOW_MINIMUM:{auc:.6f}<{MIN_VALIDATION_AUC:.2f}")
    brier = float(validation_metrics["brier"])
    baseline_brier = float(validation_metrics["baseline_brier"])
    if not brier < baseline_brier:
        reasons.append(f"BRIER_NOT_BETTER_THAN_BASELINE:{brier:.6f}>={baseline_brier:.6f}")

    status = VALIDATED_STATUS if not reasons else EXPERIMENTAL_STATUS
    confidence = _calibration_confidence(
        status=status,
        domains=domain_count,
        validation_domains=validation_domain_count,
        observations=observations,
        auc=auc,
        brier=brier,
        baseline_brier=baseline_brier,
    )

    payload: dict[str, Any] = {
        "format_version": MODEL_FORMAT_VERSION,
        "scoring_version": SCORING_VERSION,
        "model_version": DEFAULT_MODEL_VERSION,
        "dataset_version": dataset_version,
        "status": status,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_order": list(FEATURE_ORDER),
        "intercept": intercept,
        "coefficients": coefficients,
        "imputation_means": imputation,
        "engines": engines,
        "calibration_confidence": confidence,
        "training": {
            "domains": len(train_domains),
            "rows": len(train_rows),
            "observations": _weighted_count(train_rows),
            **train_metrics,
        },
        "validation": {
            "domains": validation_domain_count,
            "rows": len(validation_rows),
            "observations": _weighted_count(validation_rows),
            **validation_metrics,
        },
        "dataset": {
            "domains": domain_count,
            "rows": len(materialized),
            "observations": observations,
            "query_slots": unique_queries,
        },
        "protocol": {
            "outcome": "CITED_BINARY",
            "model": "L2_REGULARIZED_LOGISTIC_REGRESSION",
            "split": "DOMAIN_HOLDOUT_70_30_V1",
            "train_fraction": TRAIN_FRACTION,
            "l2_regularization": L2_REGULARIZATION,
            "min_domains": MIN_DOMAINS,
            "min_validation_domains": MIN_VALIDATION_DOMAINS,
            "min_engines": MIN_ENGINES,
            "min_queries_per_domain": MIN_QUERIES_PER_DOMAIN,
            "min_repetitions": MIN_REPETITIONS,
            "min_observations": MIN_OBSERVATIONS,
            "min_validation_auc": MIN_VALIDATION_AUC,
            "brier_gate": "MODEL_LT_TRAIN_PREVALENCE_BASELINE",
        },
        "promotion_reasons": reasons,
    }
    return FitResult(payload, tuple(reasons))


def _collect_database(database: Path) -> tuple[CalibrationRow, ...]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        required = {"scores", "audit_targets", "generative_visibility_query_runs"}
        if not required.issubset(tables):
            return ()

        audit_row = connection.execute("SELECT audit_id FROM audits ORDER BY rowid LIMIT 1").fetchone()
        if audit_row is None:
            return ()
        audit_id = str(audit_row["audit_id"])
        domain = _audit_domain(connection, audit_id)
        eligible_runs = _eligible_query_runs(connection, audit_id)
        if not eligible_runs:
            return ()

        engines = tuple(sorted({str(row["engine"]) for row in eligible_runs}))
        query_count = len({str(row["query_text"]) for row in eligible_runs})
        if len(engines) < MIN_ENGINES or query_count < MIN_QUERIES_PER_DOMAIN:
            return ()
        counts: dict[tuple[str, str], int] = {}
        for row in eligible_runs:
            key = (str(row["engine"]), str(row["query_text"]))
            counts[key] = counts.get(key, 0) + 1
        min_repetitions = min(counts.values()) if counts else 0
        if min_repetitions < MIN_REPETITIONS:
            return ()

        successes = sum(bool(row["cited"]) for row in eligible_runs)
        total = len(eligible_runs)
        score_rows = connection.execute(
            """SELECT device,dimension,value,consolidation_status,calculated_at,rowid
               FROM scores WHERE audit_id=? AND dimension!='OVERALL_READINESS'
               ORDER BY rowid""",
            (audit_id,),
        ).fetchall()
        latest: dict[tuple[str, str], sqlite3.Row] = {}
        for row in score_rows:
            latest[(str(row["device"]), str(row["dimension"]))] = row

        output: list[CalibrationRow] = []
        devices = sorted({device for device, _dimension in latest})
        for device in devices:
            features: dict[str, float | None] = {}
            valid = True
            for feature in FEATURE_ORDER:
                row = latest.get((device, feature))
                if row is None:
                    valid = False
                    break
                status = str(row["consolidation_status"])
                if status == "NOT_APPLICABLE":
                    features[feature] = None
                elif status in {"CONSOLIDATED", "PARTIAL"} and row["value"] is not None:
                    features[feature] = float(row["value"]) / 100.0
                else:
                    valid = False
                    break
            if valid:
                output.append(
                    CalibrationRow(
                        domain=domain,
                        audit_id=audit_id,
                        device=device,
                        features=features,
                        successes=successes,
                        total=total,
                        engines=engines,
                        query_count=query_count,
                        min_repetitions=min_repetitions,
                    )
                )
        return tuple(output)
    finally:
        connection.close()


def _eligible_query_runs(connection: sqlite3.Connection, audit_id: str) -> list[sqlite3.Row]:
    rows = list(
        connection.execute(
            """SELECT engine,query_text,cited FROM generative_visibility_query_runs
               WHERE audit_id=? AND status='VALID' AND cited IS NOT NULL""",
            (audit_id,),
        ).fetchall()
    )
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (str(row["engine"]), str(row["query_text"]))
        counts[key] = counts.get(key, 0) + 1
    eligible = {key for key, count in counts.items() if count >= MIN_REPETITIONS}
    return [row for row in rows if (str(row["engine"]), str(row["query_text"])) in eligible]


def _audit_domain(connection: sqlite3.Connection, audit_id: str) -> str:
    origins = {
        str(row[0])
        for row in connection.execute(
            "SELECT DISTINCT normalized_origin FROM audit_targets WHERE audit_id=? AND normalized_origin IS NOT NULL",
            (audit_id,),
        ).fetchall()
    }
    domains = {urlsplit(origin).hostname for origin in origins if urlsplit(origin).hostname}
    if len(domains) != 1:
        raise ValueError("calibration audit must resolve to exactly one domain")
    return str(next(iter(domains))).lower()


def _imputation_means(rows: tuple[CalibrationRow, ...]) -> dict[str, float]:
    means: dict[str, float] = {}
    for feature in FEATURE_ORDER:
        values = [float(row.features[feature]) for row in rows if row.features.get(feature) is not None]
        means[feature] = sum(values) / len(values) if values else 0.5
    return means


def _fit_logistic(rows: tuple[CalibrationRow, ...], imputation: dict[str, float]) -> tuple[float, dict[str, float]]:
    intercept = 0.0
    coefficients = {feature: 0.0 for feature in FEATURE_ORDER}
    device_counts = _device_counts(rows)
    for _iteration in range(MAX_ITERATIONS):
        grad_intercept = 0.0
        gradients = {feature: 0.0 for feature in FEATURE_ORDER}
        total_weight = 0.0
        for row in rows:
            if row.total <= 0:
                continue
            row_weight = 1.0 / device_counts[(row.domain, row.audit_id)]
            weight = row.total * row_weight
            target = row.successes / row.total
            values = _materialize_features(row, imputation)
            probability = _sigmoid(intercept + sum(coefficients[f] * values[f] for f in FEATURE_ORDER))
            error = probability - target
            grad_intercept += weight * error
            for feature in FEATURE_ORDER:
                gradients[feature] += weight * error * values[feature]
            total_weight += weight
        if total_weight <= 0:
            break
        grad_intercept /= total_weight
        for feature in FEATURE_ORDER:
            gradients[feature] = gradients[feature] / total_weight + L2_REGULARIZATION * coefficients[feature] / total_weight
        intercept -= LEARNING_RATE * grad_intercept
        for feature in FEATURE_ORDER:
            coefficients[feature] -= LEARNING_RATE * gradients[feature]
        magnitude = abs(grad_intercept) + sum(abs(value) for value in gradients.values())
        if magnitude < 1e-8:
            break
    return round(intercept, 12), {feature: round(coefficients[feature], 12) for feature in FEATURE_ORDER}


def _predictions(
    rows: tuple[CalibrationRow, ...],
    intercept: float,
    coefficients: dict[str, float],
    imputation: dict[str, float],
) -> tuple[float, ...]:
    output: list[float] = []
    for row in rows:
        values = _materialize_features(row, imputation)
        output.append(_sigmoid(intercept + sum(coefficients[f] * values[f] for f in FEATURE_ORDER)))
    return tuple(output)


def _metrics(rows: tuple[CalibrationRow, ...], predictions: tuple[float, ...], baseline_rate: float | None) -> dict[str, float]:
    device_counts = _device_counts(rows)
    weighted_total = 0.0
    weighted_success = 0.0
    brier_sum = 0.0
    positive_points: list[tuple[float, float]] = []
    negative_points: list[tuple[float, float]] = []
    for row, probability in zip(rows, predictions, strict=True):
        row_weight = 1.0 / device_counts[(row.domain, row.audit_id)]
        positives = row.successes * row_weight
        negatives = row.failures * row_weight
        weighted_total += positives + negatives
        weighted_success += positives
        brier_sum += positives * (1.0 - probability) ** 2 + negatives * probability**2
        if positives:
            positive_points.append((probability, positives))
        if negatives:
            negative_points.append((probability, negatives))
    prevalence = weighted_success / weighted_total if weighted_total else 0.0
    baseline = prevalence if baseline_rate is None else baseline_rate
    baseline_brier = (
        (weighted_success * (1.0 - baseline) ** 2 + (weighted_total - weighted_success) * baseline**2) / weighted_total
        if weighted_total else 1.0
    )
    return {
        "positive_rate": prevalence,
        "auc": _weighted_auc(positive_points, negative_points),
        "brier": brier_sum / weighted_total if weighted_total else 1.0,
        "baseline_brier": baseline_brier,
    }


def _weighted_auc(positive: list[tuple[float, float]], negative: list[tuple[float, float]]) -> float:
    total_positive = sum(weight for _score, weight in positive)
    total_negative = sum(weight for _score, weight in negative)
    if total_positive <= 0 or total_negative <= 0:
        return 0.5
    concordance = 0.0
    for positive_score, positive_weight in positive:
        for negative_score, negative_weight in negative:
            pair_weight = positive_weight * negative_weight
            if positive_score > negative_score:
                concordance += pair_weight
            elif positive_score == negative_score:
                concordance += 0.5 * pair_weight
    return concordance / (total_positive * total_negative)


def _materialize_features(row: CalibrationRow, imputation: dict[str, float]) -> dict[str, float]:
    return {
        feature: float(row.features[feature]) if row.features.get(feature) is not None else imputation[feature]
        for feature in FEATURE_ORDER
    }


def _device_counts(rows: tuple[CalibrationRow, ...]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row.domain, row.audit_id)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _weighted_count(rows: Iterable[CalibrationRow]) -> int:
    materialized = tuple(rows)
    counts = _device_counts(materialized)
    total = sum(row.total / counts[(row.domain, row.audit_id)] for row in materialized)
    return int(round(total))


def _calibration_confidence(
    *,
    status: str,
    domains: int,
    validation_domains: int,
    observations: int,
    auc: float,
    brier: float,
    baseline_brier: float,
) -> str:
    if status != VALIDATED_STATUS:
        return "LOW"
    improvement = (baseline_brier - brier) / baseline_brier if baseline_brier > 0 else 0.0
    if domains >= 50 and validation_domains >= 15 and observations >= 3000 and auc >= 0.70 and improvement >= 0.10:
        return "HIGH"
    return "MEDIUM"


def _stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sigmoid(value: float) -> float:
    if value >= 0:
        exp = math.exp(-value)
        return 1.0 / (1.0 + exp)
    exp = math.exp(value)
    return exp / (1.0 + exp)
