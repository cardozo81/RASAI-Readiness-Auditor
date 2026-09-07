"""Deterministic calibration-dataset manifest for SCORE-GEO-003."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from rasai.score_geo_003 import FEATURE_ORDER, SCORING_VERSION
from rasai.score_geo_003_calibration import (
    CalibrationCollection,
    MIN_DISTINCT_DAYS,
    MIN_DOMAINS,
    MIN_ENGINES,
    MIN_OBSERVATIONS,
    MIN_QUERIES_PER_DOMAIN,
    MIN_REPETITIONS,
    MIN_VALIDATION_DOMAINS,
    TRAIN_FRACTION,
)

DATASET_FORMAT_VERSION = "SCORE-GEO-003-DATASET-001"


def build_dataset_manifest(collection: CalibrationCollection, *, dataset_version: str) -> dict[str, Any]:
    version = dataset_version.strip()
    if not version:
        raise ValueError("dataset_version is required")
    rows = tuple(collection.rows)
    domains = sorted({row.domain for row in rows})
    engines = sorted({engine for row in rows for engine in row.engines})
    observations = sum(max(0, row.total) for row in rows)
    minimum_queries = min((row.query_count for row in rows), default=0)
    minimum_repetitions = min((row.min_repetitions for row in rows), default=0)
    domain_days: dict[str, set[str]] = {}
    for row in rows:
        domain_days.setdefault(row.domain, set()).update(row.observed_days)
    minimum_days = min((len(days) for days in domain_days.values()), default=0)
    validation_domains = max(0, len(domains) - max(1, int(len(domains) * TRAIN_FRACTION))) if domains else 0

    gates = {
        "domains": {"actual": len(domains), "minimum": MIN_DOMAINS, "pass": len(domains) >= MIN_DOMAINS},
        "validation_domains_estimated": {"actual": validation_domains, "minimum": MIN_VALIDATION_DOMAINS, "pass": validation_domains >= MIN_VALIDATION_DOMAINS},
        "engines": {"actual": len(engines), "minimum": MIN_ENGINES, "pass": len(engines) >= MIN_ENGINES},
        "observations": {"actual": observations, "minimum": MIN_OBSERVATIONS, "pass": observations >= MIN_OBSERVATIONS},
        "queries_per_domain_min": {"actual": minimum_queries, "minimum": MIN_QUERIES_PER_DOMAIN, "pass": minimum_queries >= MIN_QUERIES_PER_DOMAIN},
        "repetitions_min": {"actual": minimum_repetitions, "minimum": MIN_REPETITIONS, "pass": minimum_repetitions >= MIN_REPETITIONS},
        "distinct_days_per_domain_min": {"actual": minimum_days, "minimum": MIN_DISTINCT_DAYS, "pass": minimum_days >= MIN_DISTINCT_DAYS},
    }
    ready = bool(rows) and all(bool(item["pass"]) for item in gates.values())
    serialized_rows = [
        {
            "domain": row.domain,
            "audit_id": row.audit_id,
            "device": row.device,
            "features": {feature: row.features.get(feature) for feature in FEATURE_ORDER},
            "successes": row.successes,
            "failures": row.failures,
            "total": row.total,
            "engines": list(row.engines),
            "query_count": row.query_count,
            "min_repetitions": row.min_repetitions,
            "observed_days": list(row.observed_days),
        }
        for row in sorted(rows, key=lambda item: (item.domain, item.audit_id, item.device))
    ]
    dataset_material = json.dumps(serialized_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "format_version": DATASET_FORMAT_VERSION,
        "scoring_version": SCORING_VERSION,
        "dataset_version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": hashlib.sha256(dataset_material).hexdigest(),
        "feature_order": list(FEATURE_ORDER),
        "status": "READY_FOR_MODEL_FIT" if ready else "INSUFFICIENT_FOR_PROMOTION_PROTOCOL",
        "gates": gates,
        "summary": {
            "rows": len(rows),
            "domains": len(domains),
            "engines": engines,
            "observations": observations,
            "skipped_audits": len(collection.skipped),
        },
        "skipped": list(collection.skipped),
        "rows": serialized_rows,
        "limitations": [
            "This manifest evaluates pre-fit dataset sufficiency only.",
            "AUC and Brier promotion gates are evaluated only after model fitting on domain holdout.",
            "READY_FOR_MODEL_FIT does not mean SCORE-GEO-003 model status VALIDATED.",
        ],
    }


def write_dataset_manifest(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
