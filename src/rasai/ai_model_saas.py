"""Immutable AI model-catalog snapshots for SaaS/control-plane workers."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from rasai.ai_model_catalog import (
    MODEL_FILE_ENV,
    MODEL_SOURCE_ENV,
    AiModelCatalog,
    model_catalog_from_mapping,
)

_SAFE_JOB_ID = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class ModelJobSnapshot:
    catalog_version: str
    reference_date: str
    sha256: str
    toml: str

    @property
    def short_hash(self) -> str:
        return self.sha256[:16]


def _quoted(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _array(values: tuple[str, ...]) -> str:
    return "[" + ", ".join(_quoted(value) for value in values) + "]"


def model_catalog_to_toml(catalog: AiModelCatalog) -> str:
    meta = catalog.metadata
    lines = [
        "# RASAi immutable AI model snapshot",
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
    for item in catalog.models:
        lines.extend([
            "",
            "[[models]]",
            f"provider = {_quoted(item.provider)}",
            f"model = {_quoted(item.model)}",
            f"enabled = {_bool(item.enabled)}",
            f"selectable = {_bool(item.selectable)}",
            f"adapter_default = {_bool(item.adapter_default)}",
            f"public_default = {_bool(item.public_default)}",
            f"auto_eligible = {_bool(item.auto_eligible)}",
            f"qualification = {_quoted(item.qualification)}",
            f"rasai_class = {_quoted(item.rasai_class)}",
            f"rank = {item.rank}",
            f"recommended_depth = {_quoted(item.recommended_depth)}",
            f"recommended_use = {_quoted(item.recommended_use)}",
            f"reasoning_values = {_array(item.reasoning_values)}",
            f"default_reasoning = {_quoted(item.default_reasoning)}",
            f"capabilities = {_array(item.capabilities)}",
        ])
        if item.context_window is not None:
            lines.append(f"context_window = {item.context_window}")
        if item.max_output_tokens is not None:
            lines.append(f"max_output_tokens = {item.max_output_tokens}")
        if item.effective_from is not None:
            lines.append(f"effective_from = {_quoted(item.effective_from)}")
        if item.effective_until is not None:
            lines.append(f"effective_until = {_quoted(item.effective_until)}")
        lines.append(f"source_reference = {_quoted(item.source_reference)}")
    return "\n".join(lines) + "\n"


def build_model_job_snapshot(document: Mapping[str, Any]) -> ModelJobSnapshot:
    catalog = model_catalog_from_mapping(document, source="SAAS_CONTROL_PLANE")
    payload = model_catalog_to_toml(catalog)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return ModelJobSnapshot(
        catalog_version=catalog.metadata.catalog_version,
        reference_date=catalog.metadata.reference_date,
        sha256=digest,
        toml=payload,
    )


def materialize_model_job_snapshot(
    snapshot: ModelJobSnapshot,
    directory: Path | str,
    *,
    job_id: str,
) -> Path:
    root = Path(directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    safe_job = _SAFE_JOB_ID.sub("_", str(job_id).strip()) or "job"
    target = root / f"ai-models-{safe_job}-{snapshot.short_hash}.toml"
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if hashlib.sha256(existing.encode("utf-8")).hexdigest() != snapshot.sha256:
            raise ValueError(f"model snapshot hash mismatch for existing file: {target}")
        return target
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(snapshot.toml, encoding="utf-8", newline="\n")
    os.replace(temporary, target)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def model_worker_environment(snapshot_path: Path | str) -> dict[str, str]:
    path = Path(snapshot_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"model snapshot not found: {path}")
    return {
        MODEL_SOURCE_ENV: "file",
        MODEL_FILE_ENV: str(path),
    }
