"""Job-scoped AI pricing snapshots for SaaS/control-plane workers.

This adapter deliberately does not mutate the process-global pricing policy. A control
plane validates a document, creates an immutable snapshot and materializes that snapshot
for the worker process before RASAi imports the cost engine. This keeps organization
pricing isolated even when the control plane itself is multi-tenant.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from rasai.ai_pricing_catalog import (
    PRICING_FILE_ENV,
    PRICING_SOURCE_ENV,
    PricingCatalog,
    pricing_catalog_from_mapping,
)

_SAFE_JOB_ID = re.compile(r"[^A-Za-z0-9_.-]+")
_WEEKDAY_NAMES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


@dataclass(frozen=True, slots=True)
class PricingJobSnapshot:
    catalog_version: str
    reference_date: str
    sha256: str
    toml: str

    @property
    def short_hash(self) -> str:
        return self.sha256[:16]


def _quoted(value: str) -> str:
    # JSON basic strings are also valid TOML basic strings for the characters emitted
    # by json.dumps. ensure_ascii=False keeps provider/model names readable.
    return json.dumps(str(value), ensure_ascii=False)


def _minute_text(value: int) -> str:
    hour, minute = divmod(int(value), 60)
    return f"{hour:02d}:{minute:02d}"


def pricing_catalog_to_toml(catalog: PricingCatalog) -> str:
    """Serialize the validated schema-1 catalog deterministically for worker bootstrap."""
    meta = catalog.metadata
    lines = [
        "# RASAi immutable AI pricing snapshot",
        f"# catalog_version: {meta.catalog_version}",
        f"# reference_date: {meta.reference_date}",
        "",
        "[metadata]",
        f"schema_version = {meta.schema_version}",
        f"catalog_version = {_quoted(meta.catalog_version)}",
        f"reference_date = {_quoted(meta.reference_date)}",
        f"verified_on = {_quoted(meta.verified_on)}",
        f"review_recommended_on = {_quoted(meta.review_recommended_on)}",
    ]
    for policy in catalog.models:
        lines.extend([
            "",
            "[[models]]",
            f"provider = {_quoted(policy.provider)}",
            f"model = {_quoted(policy.model)}",
            f"pricing_model = {_quoted(policy.pricing_model)}",
            f"reasoning_billing = {_quoted(policy.reasoning_billing)}",
            f"region = {_quoted(policy.region)}",
            f"currency = {_quoted(policy.currency)}",
            f"source_reference = {_quoted(policy.source_reference)}",
        ])
        for rule in policy.rules:
            lines.extend([
                "",
                "  [[models.rules]]",
                f"  rule_id = {_quoted(rule.rule_id)}",
                f"  context = {_quoted(rule.context)}",
                f"  priority = {rule.priority}",
                f"  effective_from = {_quoted(rule.effective_from)}",
            ])
            if rule.effective_until is not None:
                lines.append(f"  effective_until = {_quoted(rule.effective_until)}")
            for field in ("input_tokens_gte", "input_tokens_gt", "input_tokens_lte", "input_tokens_lt"):
                value = getattr(rule, field)
                if value is not None:
                    lines.append(f"  {field} = {value}")
            if rule.weekdays_utc:
                days = ", ".join(_quoted(_WEEKDAY_NAMES[index]) for index in rule.weekdays_utc)
                lines.append(f"  weekdays_utc = [{days}]")
            if rule.time_windows_utc:
                windows = ", ".join(
                    _quoted(f"{_minute_text(start)}-{_minute_text(end)}")
                    for start, end in rule.time_windows_utc
                )
                lines.append(f"  time_windows_utc = [{windows}]")
            lines.extend([
                f"  input_price_per_million = {rule.input_price_per_million:.12g}",
                f"  cached_input_price_per_million = {rule.cached_input_price_per_million:.12g}",
                f"  output_price_per_million = {rule.output_price_per_million:.12g}",
            ])
    return "\n".join(lines) + "\n"


def build_pricing_job_snapshot(document: Mapping[str, Any]) -> PricingJobSnapshot:
    """Validate a control-plane document and freeze its deterministic worker payload."""
    catalog = pricing_catalog_from_mapping(document, source="SAAS_CONTROL_PLANE")
    payload = pricing_catalog_to_toml(catalog)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return PricingJobSnapshot(
        catalog_version=catalog.metadata.catalog_version,
        reference_date=catalog.metadata.reference_date,
        sha256=digest,
        toml=payload,
    )


def materialize_pricing_job_snapshot(
    snapshot: PricingJobSnapshot,
    directory: Path | str,
    *,
    job_id: str,
) -> Path:
    """Atomically materialize one immutable snapshot for a worker/job."""
    root = Path(directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    safe_job = _SAFE_JOB_ID.sub("_", str(job_id).strip()) or "job"
    target = root / f"ai-pricing-{safe_job}-{snapshot.short_hash}.toml"
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if hashlib.sha256(existing.encode("utf-8")).hexdigest() != snapshot.sha256:
            raise ValueError(f"pricing snapshot hash mismatch for existing file: {target}")
        return target
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(snapshot.toml, encoding="utf-8", newline="\n")
    os.replace(temporary, target)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def pricing_worker_environment(snapshot_path: Path | str) -> dict[str, str]:
    """Environment overlay to apply before starting/importing the RASAi worker runtime."""
    path = Path(snapshot_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"pricing snapshot not found: {path}")
    return {
        PRICING_SOURCE_ENV: "file",
        PRICING_FILE_ENV: str(path),
    }
