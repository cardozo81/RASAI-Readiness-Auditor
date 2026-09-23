"""Leitura longitudinal dos catálogos a partir de evidência persistida.

Este módulo é somente leitura. Ele não materializa CATs, não reexecuta coletores e não
interpreta HTML. A finalidade é oferecer ao consolidado uma visão transversal de todos
os catálogos usando as mesmas fontes estruturadas que alimentam o report-catalog.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from rasai.audit_catalog import CATALOGS
from rasai.catalog_report_catalog_state import (
    _catalog_sources,
    _catalog_source_specs,
    _catalog_status,
    _configuration_rows,
    _cat08_rpr_configuration_rows,
)
from rasai.catalog_report_metrics import _catalog_metrics
from rasai.catalog_report_model import _audit_rows, _columns, _load_data, _table_exists
from rasai.monitoring.models import AuditSnapshot
from rasai.monitoring.reader import read_audit_snapshot
from rasai.secret_safety import redact_value

CATALOG_LONGITUDINAL_CONTRACT = "CONSOLIDATED-CATALOG-LONGITUDINAL-006"

_VOLATILE_FIELDS = frozenset({
    "audit_id",
    "snapshot_id",
    "page_id",
    "run_id",
    "attempt_id",
    "execution_id",
    "analysis_id",
    "observation_id",
    "created_at",
    "updated_at",
    "started_at",
    "finished_at",
    "completed_at",
    "captured_at",
    "calculated_at",
    "executed_at",
    "generated_at",
    "observed_at",
    # Identificadores e referências emitidos novamente a cada AUD não representam
    # mudança semântica da evidência entre marcos.
    "diagnostic_id",
    "suggestion_id",
    "recommendation_id",
    "remediation_group_id",
    "finding_id",
    "summary_id",
    "sample_id",
    "assessment_id",
    "entity_observation_id",
    "interpretation_id",
    "acquisition_id",
    "group_id",
    "governance_id",
    "remediation_id",
    "resource_id",
    "source_audit_id",
    "source_observation_id",
    "source_id",
    "evidence_ids",
    "evidence_ids_json",
    "source_evidence_json",
    "affected_findings",
    "affected_pages",
    "collected_at",
    "materialized_at",
    "consumed_at",
    "lighthouse_fetch_time",
})
_ACCEPTED_GLOBAL_DEVICES = frozenset({"", "GLOBAL", "ALL", "BOTH", "POPULATION", "UNKNOWN"})
_NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    audit_id: str
    event_time: str
    url: str
    device: str
    catalogs: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class CatalogInterval:
    interval_id: str
    baseline_audit_id: str
    current_audit_id: str
    baseline_event_time: str
    current_event_time: str
    changes: tuple[dict[str, Any], ...]
    stable_expected: int
    stable_attention: int


def _jsonable(value: Any) -> Any:
    clean = redact_value(value)
    if isinstance(clean, Mapping):
        return {str(key): _jsonable(item) for key, item in clean.items()}
    if isinstance(clean, tuple):
        return [_jsonable(item) for item in clean]
    if isinstance(clean, list):
        return [_jsonable(item) for item in clean]
    if isinstance(clean, (str, int, float, bool)) or clean is None:
        return clean
    return str(clean)


def _semantic_row(row: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for raw_key, raw_value in row.items():
        key = str(raw_key)
        lowered = key.casefold()
        if key in _VOLATILE_FIELDS or lowered.endswith("_timestamp"):
            continue
        payload[key] = _jsonable(raw_value)
    return payload


def _row_fingerprint(row: Mapping[str, Any]) -> str:
    material = json.dumps(_semantic_row(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(material.encode("utf-8")).hexdigest()


def _row_in_scope(row: Mapping[str, Any], *, url: str, device: str) -> bool:
    if "url" in row and row.get("url") not in (None, "", url):
        return False
    if "normalized_url" in row and row.get("normalized_url") not in (None, "", url):
        return False
    if "device" in row:
        value = str(row.get("device") or "").strip().upper()
        if value not in _ACCEPTED_GLOBAL_DEVICES and value != device.upper():
            return False
    return True


def _catalog_record_matches_source_scope(
    row: Mapping[str, Any],
    *,
    catalog_id: str,
    table: str,
) -> bool:
    """Mirror catalog-report source scoping before longitudinal fingerprinting."""
    if catalog_id == "CAT-02" and table == "web_performance_attempts":
        return str(row.get("service") or "").strip().upper() == "PAGESPEED_INSIGHTS"
    if catalog_id == "CAT-02" and table == "web_performance_observations":
        return row.get("accessibility_score") is not None
    return True


def _source_records(
    connection: sqlite3.Connection,
    audit_id: str,
    catalog_id: str,
    *,
    url: str,
    device: str,
) -> dict[str, tuple[dict[str, Any], ...]]:
    result: dict[str, tuple[dict[str, Any], ...]] = {}
    for table, _label in _catalog_source_specs(catalog_id):
        if not _table_exists(connection, table):
            continue
        rows = _audit_rows(connection, table, audit_id)
        scoped = [
            _semantic_row(dict(row))
            for row in rows
            if _row_in_scope(row, url=url, device=device)
            and _catalog_record_matches_source_scope(
                row,
                catalog_id=catalog_id,
                table=table,
            )
        ]
        if scoped:
            result[table] = tuple(scoped)
    return result


def _effective_web_performance_state(connection: sqlite3.Connection, audit_id: str) -> dict[str, Any]:
    if not (_table_exists(connection, "web_performance_attempts") and _table_exists(connection, "web_performance_observations")):
        return {}
    attempts = [dict(row) for row in _audit_rows(connection, "web_performance_attempts", audit_id)]
    observations = [dict(row) for row in _audit_rows(connection, "web_performance_observations", audit_id)]
    if not observations:
        return {}
    latest_by_snapshot: dict[str, dict[str, Any]] = {}
    for row in observations:
        latest_by_snapshot[str(row.get("snapshot_id") or row.get("observation_id") or "")] = row
    contexts=[]
    for snapshot_id, observation in latest_by_snapshot.items():
        services=[]
        for service, ref_field in (
            ("PAGESPEED_INSIGHTS", "pagespeed_artifact_reference"),
            ("CRUX_API", "crux_artifact_reference"),
        ):
            candidates=[
                row for row in attempts
                if str(row.get("snapshot_id") or "")==snapshot_id
                and str(row.get("service") or "").upper()==service
            ]
            if not candidates:
                continue
            expected_ref=str(observation.get(ref_field) or "")
            effective=None
            if expected_ref:
                effective=next(
                    (row for row in reversed(candidates) if str(row.get("artifact_reference") or "")==expected_ref),
                    None,
                )
            effective=effective or candidates[-1]
            services.append({
                "service":service,
                "status":effective.get("status"),
                "http_status":effective.get("http_status"),
                "error_code":effective.get("error_code"),
                "artifact_reference":effective.get("artifact_reference"),
                "effective_for_current_observation":True,
                "superseded_attempts":max(0,len(candidates)-1),
            })
        contexts.append({
            "snapshot_id":snapshot_id,
            "observation_status":observation.get("status"),
            "url":observation.get("url"),
            "device":observation.get("device"),
            "services":services,
        })
    return {
        "semantics":"effective_for_current_observation=true is the final attempt represented by the latest persisted observation; superseded attempts are historical only",
        "contexts":contexts,
    }


def _metric_value(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value or "").strip().replace(" ", "")
    if not text:
        return None
    match = _NUMBER_RE.search(text.replace(",", "."))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def build_catalog_snapshot(
    workspace: str | Path,
    *,
    url: str,
    device: str,
    audit_snapshot: AuditSnapshot | None = None,
) -> CatalogSnapshot:
    root = Path(workspace)
    database = root / "audit.db"
    audit = audit_snapshot or read_audit_snapshot(root)
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        data = _load_data(audit.audit_id, database, connection=connection)
        catalogs: list[dict[str, Any]] = []
        for catalog in CATALOGS:
            raw_sources = _catalog_sources(
                database,
                data,
                catalog.id,
                connection=connection,
            )
            status, _tone, detail = _catalog_status(
                database,
                data,
                catalog.id,
                connection=connection,
                sources=raw_sources,
            )
            metrics = tuple(
                {
                    "name": str(name),
                    "value": _jsonable(value),
                    "kind": str(kind),
                    "numeric_value": _metric_value(value),
                }
                for name, value, kind in _catalog_metrics(
                    database,
                    data,
                    catalog.id,
                    connection=connection,
                )
            )
            sources = tuple(
                {"source": table, "label": label, "count": int(count)}
                for table, label, count in raw_sources
            )
            configuration_rows = list(_configuration_rows(data, catalog.id))
            if catalog.id == "CAT-08":
                configuration_rows.extend(_cat08_rpr_configuration_rows(database, data, connection=connection))
            configuration = tuple(
                {"name": str(name), "value": _jsonable(value), "origin": str(origin)}
                for name, value, origin in configuration_rows
            )
            source_records = _source_records(
                connection,
                audit.audit_id,
                catalog.id,
                url=url,
                device=device,
            )
            source_labels = {str(item["source"]): str(item["label"]) for item in sources}
            records = tuple(
                {
                    "source": source,
                    "source_label": source_labels.get(source, source),
                    "fingerprints": tuple(sorted(_row_fingerprint(row) for row in rows)),
                    "rows": rows,
                }
                for source, rows in sorted(source_records.items())
            )
            catalogs.append({
                "catalog_id": catalog.id,
                "label": catalog.label,
                "purpose": catalog.purpose,
                "expected_result": catalog.expected_result,
                "status": status,
                "status_detail": detail,
                "metrics": metrics,
                "sources": sources,
                "configuration": configuration,
                "effective_external_state": (
                    _effective_web_performance_state(connection, audit.audit_id)
                    if catalog.id == "CAT-04"
                    else {}
                ),
                "records": records,
            })
    finally:
        connection.close()
    return CatalogSnapshot(
        audit_id=audit.audit_id,
        event_time=audit.event_time,
        url=url,
        device=device.upper(),
        catalogs=tuple(catalogs),
    )

def _by(items: tuple[dict[str, Any], ...], *keys: str) -> dict[tuple[str, ...], dict[str, Any]]:
    result: dict[tuple[str, ...], dict[str, Any]] = {}
    for item in items:
        key = tuple(str(item.get(field) or "") for field in keys)
        result[key] = item
    return result


def _status_stability(status: str) -> str:
    normalized = str(status or "").strip().upper()
    return "ESTAVEL_DENTRO_ESPERADO" if normalized == "CONCLUÍDO" else "PERSISTENTE_ATENCAO"


def _change(
    catalog_id: str,
    catalog_label: str,
    category: str,
    status: str,
    label: str,
    before: Any,
    after: Any,
    *,
    delta: float | None = None,
    delta_percent: float | None = None,
    detail: str | None = None,
    evidence: Any = None,
) -> dict[str, Any]:
    return {
        "catalog_id": catalog_id,
        "catalog_label": catalog_label,
        "category": category,
        "status": status,
        "label": label,
        "before": _jsonable(before),
        "after": _jsonable(after),
        "delta": delta,
        "delta_percent": delta_percent,
        "detail": detail,
        "evidence": _jsonable(evidence),
    }


def compare_catalog_snapshots(before: CatalogSnapshot, after: CatalogSnapshot, *, interval_index: int) -> CatalogInterval:
    if before.url != after.url:
        raise ValueError("snapshots de catálogo com URLs diferentes não são comparáveis")
    if before.device.upper() != after.device.upper():
        raise ValueError("snapshots de catálogo com dispositivos diferentes não são comparáveis")
    changes: list[dict[str, Any]] = []
    stable_expected = 0
    stable_attention = 0
    before_catalogs = {str(item["catalog_id"]): item for item in before.catalogs}
    after_catalogs = {str(item["catalog_id"]): item for item in after.catalogs}
    for catalog_id in sorted(set(before_catalogs) | set(after_catalogs)):
        left = before_catalogs.get(catalog_id) or {}
        right = after_catalogs.get(catalog_id) or {}
        label = str(right.get("label") or left.get("label") or catalog_id)
        old_status = left.get("status")
        new_status = right.get("status")
        if old_status == new_status:
            state = _status_stability(str(new_status or ""))
            if state == "ESTAVEL_DENTRO_ESPERADO":
                stable_expected += 1
            else:
                stable_attention += 1
            changes.append(_change(catalog_id, label, "ESTADO_CATALOGO", state, "Estado do catálogo", old_status, new_status, detail=str(right.get("status_detail") or left.get("status_detail") or "")))
        else:
            changes.append(_change(catalog_id, label, "ESTADO_CATALOGO", "ALTERADO", "Estado do catálogo", old_status, new_status, detail=str(right.get("status_detail") or "")))

        left_metrics = _by(tuple(left.get("metrics") or ()), "name", "kind")
        right_metrics = _by(tuple(right.get("metrics") or ()), "name", "kind")
        for key in sorted(set(left_metrics) | set(right_metrics)):
            old = left_metrics.get(key)
            new = right_metrics.get(key)
            if old is None:
                changes.append(_change(catalog_id, label, "METRICA", "NOVO", key[0], None, new.get("value") if new else None))
                continue
            if new is None:
                changes.append(_change(catalog_id, label, "METRICA", "DADO_INDISPONIVEL", key[0], old.get("value"), None, detail="A ausência posterior não é interpretada como correção."))
                continue
            old_value = old.get("value")
            new_value = new.get("value")
            if old_value == new_value:
                changes.append(_change(catalog_id, label, "METRICA", "ESTAVEL", key[0], old_value, new_value))
                continue
            old_num = old.get("numeric_value")
            new_num = new.get("numeric_value")
            delta = None
            delta_percent = None
            if isinstance(old_num, (int, float)) and isinstance(new_num, (int, float)):
                delta = float(new_num) - float(old_num)
                delta_percent = None if float(old_num) == 0 else delta / abs(float(old_num)) * 100.0
            changes.append(_change(catalog_id, label, "METRICA", "ALTERADO", key[0], old_value, new_value, delta=delta, delta_percent=delta_percent))

        left_cfg = _by(tuple(left.get("configuration") or ()), "name")
        right_cfg = _by(tuple(right.get("configuration") or ()), "name")
        for key in sorted(set(left_cfg) | set(right_cfg)):
            old = left_cfg.get(key)
            new = right_cfg.get(key)
            old_value = old.get("value") if old else None
            new_value = new.get("value") if new else None
            if old_value != new_value:
                changes.append(_change(catalog_id, label, "CONFIGURACAO", "CONFIGURACAO_ALTERADA", key[0], old_value, new_value, detail="Mudança de configuração pode limitar a interpretação longitudinal."))

        left_sources = _by(tuple(left.get("sources") or ()), "source")
        right_sources = _by(tuple(right.get("sources") or ()), "source")
        for key in sorted(set(left_sources) | set(right_sources)):
            old_count = int((left_sources.get(key) or {}).get("count") or 0)
            new_count = int((right_sources.get(key) or {}).get("count") or 0)
            source_label = str((right_sources.get(key) or left_sources.get(key) or {}).get("label") or key[0])
            if old_count == new_count:
                continue
            changes.append(_change(catalog_id, label, "FONTE_PERSISTIDA", "ALTERADO", source_label, old_count, new_count, delta=float(new_count - old_count)))

        left_records = {str(item.get("source")): item for item in tuple(left.get("records") or ())}
        right_records = {str(item.get("source")): item for item in tuple(right.get("records") or ())}
        for source in sorted(set(left_records) | set(right_records)):
            old_item = left_records.get(source) or {}
            new_item = right_records.get(source) or {}
            old_rows = tuple(old_item.get("rows") or ())
            new_rows = tuple(new_item.get("rows") or ())
            old_map = {_row_fingerprint(row): row for row in old_rows}
            new_map = {_row_fingerprint(row): row for row in new_rows}
            added_keys = sorted(set(new_map) - set(old_map))
            removed_keys = sorted(set(old_map) - set(new_map))
            if not added_keys and not removed_keys:
                continue
            source_label = str(new_item.get("source_label") or old_item.get("source_label") or source)
            changes.append(_change(
                catalog_id,
                label,
                "EVIDENCIA_PERSISTIDA",
                "ALTERADO",
                source_label,
                len(old_map),
                len(new_map),
                delta=float(len(new_map) - len(old_map)),
                detail=f"{len(added_keys)} registro(s) novo(s) e {len(removed_keys)} registro(s) não encontrado(s) no estado posterior.",
                evidence={
                    "added_count": len(added_keys),
                    "removed_count": len(removed_keys),
                    "added": [new_map[key] for key in added_keys[:20]],
                    "removed": [old_map[key] for key in removed_keys[:20]],
                    "examples_limited": len(added_keys) > 20 or len(removed_keys) > 20,
                },
            ))

    return CatalogInterval(
        interval_id=f"INTERVALO-{interval_index:03d}",
        baseline_audit_id=before.audit_id,
        current_audit_id=after.audit_id,
        baseline_event_time=before.event_time,
        current_event_time=after.event_time,
        changes=tuple(changes),
        stable_expected=stable_expected,
        stable_attention=stable_attention,
    )


def build_catalog_intervals(
    workspaces: tuple[Path, ...],
    *,
    url: str,
    device: str,
    audit_snapshots: Mapping[str, AuditSnapshot] | None = None,
) -> tuple[tuple[CatalogSnapshot, ...], tuple[CatalogInterval, ...]]:
    cached = audit_snapshots or {}
    snapshots = tuple(
        build_catalog_snapshot(
            path,
            url=url,
            device=device,
            audit_snapshot=cached.get(str(path.resolve())),
        )
        for path in workspaces
    )
    if len(snapshots) < 2:
        raise ValueError("a análise longitudinal por catálogo exige pelo menos duas auditorias")
    intervals = tuple(
        compare_catalog_snapshots(snapshots[index - 1], snapshots[index], interval_index=index)
        for index in range(1, len(snapshots))
    )
    return snapshots, intervals


__all__ = [
    "CATALOG_LONGITUDINAL_CONTRACT",
    "CatalogSnapshot",
    "CatalogInterval",
    "build_catalog_snapshot",
    "compare_catalog_snapshots",
    "build_catalog_intervals",
]
