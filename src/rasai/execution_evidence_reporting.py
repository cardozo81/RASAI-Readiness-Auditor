"""Execution configuration/evidence report and presentation reconciliation.

This module is read-only with respect to audit evidence and scoring. It projects the
secret-free execution configuration already persisted for the AUD, the canonical
fulfillment work-items and persisted collector/service states into one operator-facing
matrix. It also repairs a narrow presentation mismatch: a capability that was not
requested by the effective execution configuration must be shown as not requested,
not as a failed or unavailable collection.

The module deliberately never reads secret values into HTML. Missing configuration is
reported only by variable/setting name when that information was already persisted by
an integration contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Iterable, Mapping, Sequence

from rasai.audit_configuration_reuse import configuration_hash
from rasai.persistence import AuditWorkspace
from rasai.report_navigation import render_report_navigation
from rasai.standards_service_registry import services

REPORT_FILE = "execution-evidence.html"
REPORT_LABEL = "Evidências da execução"
_INSTALLED = False

_TRUE = {"1", "true", "yes", "on", "sim", "s"}
_FAILURE_STATUSES = {
    "FAILED_RETRYABLE",
    "FAILED_PERMANENT",
    "FAILED_FATAL",
    "BLOCKED",
    "ERROR",
    "FAILURE",
    "UNAVAILABLE",
}
_PENDING_STATUSES = {
    "PENDING",
    "RUNNING",
    "WAITING_FOR_DATA",
    "REQUESTED_NOT_EXECUTED",
    "PROCESSING",
}
_NEUTRAL_STATUSES = {"DISABLED", "NOT_APPLICABLE", "NOT_REQUESTED"}
_SUCCESS_STATUSES = {"SUCCESS", "COMPLETE", "COMPLETED", "READY", "MEASURED", "FINAL"}
_CONFIG_STATUSES = {"NOT_CONFIGURED", "CONFIGURATION_REQUIRED"}
_ENV_NAME_RE = re.compile(r"\bRASAI_[A-Z0-9_]+\b")


@dataclass(frozen=True, slots=True)
class ExecutionEvidenceRow:
    capability: str
    requested: bool
    source: str
    status: str
    tone: str
    technical_ref: str
    missing_configuration: tuple[str, ...] = ()
    detail: str = ""


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    try:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone() is not None
    except sqlite3.Error:
        return False


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    try:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def _one(
    connection: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...] = (),
) -> sqlite3.Row | None:
    try:
        return connection.execute(sql, params).fetchone()
    except sqlite3.Error:
        return None


def _many(
    connection: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...] = (),
) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.Error:
        return []


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _json_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        material = value
    else:
        try:
            material = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            material = []
    if not isinstance(material, list):
        return ()
    return tuple(str(item).strip() for item in material if str(item).strip())


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    raw = str(value or "").strip().casefold()
    if not raw:
        return default
    return raw in _TRUE


def _nested(configuration: Mapping[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = configuration
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _settings(configuration: Mapping[str, Any]) -> Mapping[str, Any]:
    value = configuration.get("settings")
    return value if isinstance(value, Mapping) else {}


def _environment(configuration: Mapping[str, Any]) -> Mapping[str, Any]:
    value = _nested(configuration, "settings", "environment", default={})
    return value if isinstance(value, Mapping) else {}


def _profile(configuration: Mapping[str, Any]) -> Mapping[str, Any]:
    value = configuration.get("execution_profile")
    return value if isinstance(value, Mapping) else {}


def _profile_source(configuration: Mapping[str, Any], capability: str) -> str:
    profile = _profile(configuration)
    if not profile:
        return "Configuração da execução"
    label = str(profile.get("label") or profile.get("profile_id") or "perfil")
    overrides = {str(item) for item in profile.get("manual_overrides", ()) if str(item)}
    mapping = {
        "SEMANTIC_AI": "ai",
        "TECHNICAL_AI": "remediation",
        "CONTENT_REMEDIATION_AI": "remediation",
        "WEB_PERFORMANCE": "web",
        "LIGHTHOUSE_PERFORMANCE": "web",
        "LIGHTHOUSE_ACCESSIBILITY": "web",
        "LIGHTHOUSE_BEST_PRACTICES": "web",
        "LIGHTHOUSE_SEO": "web",
        "LIGHTHOUSE_AGENTIC": "web",
        "SYNTHETIC_APDEX": "experience",
        "EXPERIENCE_APDEX": "experience",
        "SEARCH_INTELLIGENCE": "search",
        "IMPROVEMENT_INTELLIGENCE": "deep",
    }
    domain = mapping.get(capability)
    if domain and domain in overrides:
        return f"Ajuste explícito do usuário após perfil {label}"
    return f"Perfil {label} + configuração da sessão"


def _load_configuration(
    connection: sqlite3.Connection,
    audit_id: str,
) -> tuple[dict[str, Any], str, str, str]:
    """Return configuration, persisted hash, computed hash and integrity label."""
    if not _table_exists(connection, "audit_execution_configurations"):
        return {}, "", "", "SNAPSHOT AUSENTE"
    row = _one(
        connection,
        "SELECT configuration_json,configuration_hash FROM audit_execution_configurations WHERE audit_id=?",
        (audit_id,),
    )
    if row is None:
        return {}, "", "", "SNAPSHOT AUSENTE"
    try:
        configuration = json.loads(str(row["configuration_json"] or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}, str(row["configuration_hash"] or ""), "", "SNAPSHOT CORROMPIDO"
    if not isinstance(configuration, dict):
        return {}, str(row["configuration_hash"] or ""), "", "SNAPSHOT CORROMPIDO"
    persisted = str(row["configuration_hash"] or "")
    computed = configuration_hash(configuration)
    integrity = "ÍNTEGRO" if persisted and persisted == computed else "HASH DIVERGENTE"
    return configuration, persisted, computed, integrity


def _work_items(connection: sqlite3.Connection, audit_id: str) -> dict[str, list[sqlite3.Row]]:
    output: dict[str, list[sqlite3.Row]] = {}
    if not _table_exists(connection, "audit_fulfillment_work_items"):
        return output
    columns = _columns(connection, "audit_fulfillment_work_items")
    wanted = [
        "component",
        "scope_key",
        "required",
        "status",
        "attempt_count",
        "retryable",
        "last_error_class",
        "last_error_code",
        "last_error_message",
        "effective_result_ref",
        "configuration",
    ]
    projection = ",".join(name if name in columns else f"NULL AS {name}" for name in wanted)
    for row in _many(
        connection,
        f"SELECT {projection} FROM audit_fulfillment_work_items WHERE audit_id=? ORDER BY component,scope_key",
        (audit_id,),
    ):
        output.setdefault(str(row["component"] or "UNKNOWN").upper(), []).append(row)
    return output


def _aggregate_status(items: Sequence[sqlite3.Row]) -> tuple[str, str, str, tuple[str, ...], str]:
    if not items:
        return "", "neutral", "", (), ""
    statuses = [str(row["status"] or "UNKNOWN").upper() for row in items]
    failed = [row for row in items if str(row["status"] or "").upper() in _FAILURE_STATUSES]
    config = [row for row in items if str(row["status"] or "").upper() in _CONFIG_STATUSES]
    pending = [row for row in items if str(row["status"] or "").upper() in _PENDING_STATUSES]
    success = [row for row in items if str(row["status"] or "").upper() in _SUCCESS_STATUSES]
    neutral = [row for row in items if str(row["status"] or "").upper() in _NEUTRAL_STATUSES]

    if config:
        label, tone, chosen = "CONFIGURAÇÃO NECESSÁRIA", "warn", config[0]
    elif failed:
        label, tone, chosen = "FALHA", "bad", failed[0]
    elif pending:
        label = "PARCIAL / PENDENTE" if success else "PENDENTE"
        tone, chosen = "warn", pending[0]
    elif success and len(success) == len(items):
        label, tone, chosen = "CONCLUÍDO", "good", success[0]
    elif success and (neutral or len(success) < len(items)):
        label, tone, chosen = "CONCLUÍDO COM ITENS NÃO APLICÁVEIS", "good", success[0]
    elif neutral and len(neutral) == len(items):
        label, tone, chosen = "NÃO SOLICITADO / NÃO APLICÁVEL", "neutral", neutral[0]
    else:
        label, tone, chosen = "/".join(sorted(set(statuses))), "neutral", items[0]

    error_parts = [
        str(chosen[name]).strip()
        for name in ("last_error_class", "last_error_code", "last_error_message")
        if name in chosen.keys() and chosen[name]
    ]
    detail = " · ".join(error_parts)
    missing = tuple(sorted(set(_ENV_NAME_RE.findall(detail))))
    result_ref = str(chosen["effective_result_ref"] or "") if "effective_result_ref" in chosen.keys() else ""
    return label, tone, detail, missing, result_ref


def _work_item_row(
    capability: str,
    label: str,
    requested: bool,
    source: str,
    items: Sequence[sqlite3.Row],
    *,
    technical_ref: str,
    fallback_status: str = "",
    fallback_tone: str = "neutral",
    fallback_detail: str = "",
    missing: Iterable[str] = (),
) -> ExecutionEvidenceRow:
    status, tone, detail, work_missing, result_ref = _aggregate_status(items)
    if not requested and not items:
        return ExecutionEvidenceRow(
            label,
            False,
            source,
            "NÃO SOLICITADO",
            "neutral",
            technical_ref,
            (),
            "A capacidade não fazia parte do contrato efetivo desta execução.",
        )
    if not status:
        status = fallback_status or ("SOLICITADO · SEM ESTADO PERSISTIDO" if requested else "NÃO SOLICITADO")
        tone = fallback_tone if fallback_status else ("warn" if requested else "neutral")
        detail = fallback_detail
    combined_missing = tuple(sorted(set((*missing, *work_missing))))
    if result_ref:
        detail = (detail + " · " if detail else "") + f"resultado={result_ref}"
    return ExecutionEvidenceRow(
        label,
        bool(requested or items),
        source,
        status,
        tone,
        technical_ref,
        combined_missing,
        detail,
    )


def _web_state(connection: sqlite3.Connection, audit_id: str) -> tuple[bool, set[str], str, str]:
    run = _one(
        connection,
        "SELECT enabled,status,reason,categories FROM web_performance_runs WHERE audit_id=?",
        (audit_id,),
    )
    if run is None:
        return False, set(), "", ""
    categories = {item.casefold() for item in _json_list(run["categories"])}
    return bool(run["enabled"]), categories, str(run["status"] or ""), str(run["reason"] or "")


def _score_available(connection: sqlite3.Connection, audit_id: str, column: str) -> bool:
    if not _table_exists(connection, "web_performance_observations"):
        return False
    if column not in _columns(connection, "web_performance_observations"):
        return False
    row = _one(
        connection,
        f"SELECT 1 FROM web_performance_observations WHERE audit_id=? AND {column} IS NOT NULL LIMIT 1",
        (audit_id,),
    )
    return row is not None


def _lighthouse_row(
    connection: sqlite3.Connection,
    audit_id: str,
    configuration: Mapping[str, Any],
    *,
    capability: str,
    label: str,
    category: str,
    column: str,
    web_enabled: bool,
    categories: set[str],
    web_status: str,
    web_reason: str,
) -> ExecutionEvidenceRow:
    requested = web_enabled and category in categories
    source = _profile_source(configuration, capability)
    if not requested:
        return ExecutionEvidenceRow(
            label,
            False,
            source,
            "NÃO SOLICITADO",
            "neutral",
            "audit.db → web_performance_runs.categories",
            (),
            f"Categoria Lighthouse '{category}' não integrou a configuração efetiva desta execução.",
        )
    if _score_available(connection, audit_id, column):
        return ExecutionEvidenceRow(
            label,
            True,
            source,
            "CONCLUÍDO",
            "good",
            f"audit.db → web_performance_observations.{column}",
            (),
            "Há score Lighthouse persistido para ao menos um contexto elegível.",
        )
    status_upper = web_status.upper()
    if status_upper in _FAILURE_STATUSES:
        tone, status = "bad", "FALHA"
    elif status_upper in _CONFIG_STATUSES:
        tone, status = "warn", "CONFIGURAÇÃO NECESSÁRIA"
    else:
        tone, status = "warn", "SOLICITADO · SEM RESULTADO UTILIZÁVEL"
    return ExecutionEvidenceRow(
        label,
        True,
        source,
        status,
        tone,
        "audit.db → web_performance_runs / web_performance_attempts / web_performance_observations",
        tuple(sorted(set(_ENV_NAME_RE.findall(web_reason)))),
        web_reason or "A categoria foi solicitada, mas nenhum score utilizável foi persistido.",
    )


def _standard_rows(
    connection: sqlite3.Connection,
    audit_id: str,
    configuration: Mapping[str, Any],
) -> list[ExecutionEvidenceRow]:
    persisted: dict[str, sqlite3.Row] = {}
    if _table_exists(connection, "standards_service_runs"):
        columns = _columns(connection, "standards_service_runs")
        wanted = [
            "service_id",
            "requested",
            "configured",
            "effective_enabled",
            "state",
            "targets_attempted",
            "targets_succeeded",
            "details_json",
        ]
        projection = ",".join(name if name in columns else f"NULL AS {name}" for name in wanted)
        for row in _many(
            connection,
            f"SELECT {projection} FROM standards_service_runs WHERE audit_id=? ORDER BY service_id",
            (audit_id,),
        ):
            persisted[str(row["service_id"] or "")] = row

    env = _environment(configuration)
    rows: list[ExecutionEvidenceRow] = []
    for item in services():
        row = persisted.get(item.id)
        if row is not None:
            details = _json_object(row["details_json"])
            requested = bool(row["requested"])
            configured = bool(row["configured"])
            state = str(row["state"] or "UNKNOWN").upper()
            attempted = int(row["targets_attempted"] or 0)
            succeeded = int(row["targets_succeeded"] or 0)
            missing = tuple(
                str(name)
                for name in details.get("missing_configuration", ())
                if str(name)
            )
            if not missing and requested and not configured:
                missing = tuple(
                    name
                    for name in (*item.credential_envs, *item.config_envs, *((item.dataset_env,) if item.dataset_env else ()))
                    if name
                )
            source = str(details.get("configuration_source") or "Estado persistido da integração")
            if not requested:
                label, tone = "NÃO SOLICITADO", "neutral"
            elif not configured or state == "NOT_CONFIGURED":
                label, tone = "CONFIGURAÇÃO NECESSÁRIA", "warn"
            elif state in _SUCCESS_STATUSES and (attempted == 0 or succeeded >= attempted):
                label, tone = "CONCLUÍDO", "good"
            elif state in _FAILURE_STATUSES:
                label, tone = "FALHA", "bad"
            elif state in {"NO_DATA", "EMPTY", "PARTIAL"}:
                label, tone = "CONCLUÍDO SEM DADO UTILIZÁVEL" if state == "NO_DATA" else "PARCIAL", "warn"
            else:
                label, tone = state.replace("_", " "), "warn" if requested else "neutral"
            rows.append(
                ExecutionEvidenceRow(
                    item.label,
                    requested,
                    source,
                    label,
                    tone,
                    f"audit.db → standards_service_runs[{item.id}]",
                    tuple(sorted(set(missing))),
                    f"state={state}; alvos={succeeded}/{attempted}",
                )
            )
            continue

        explicit = str(env.get(item.enabled_env) or "").strip()
        if explicit:
            requested = _bool(explicit, default=item.default_enabled)
            source = "Configuração explícita persistida"
        elif item.default_enabled and not item.credential_envs:
            requested = True
            source = "Padrão operacional"
        else:
            requested = False
            source = "Não solicitado na configuração persistida"
        rows.append(
            ExecutionEvidenceRow(
                item.label,
                requested,
                source,
                "SOLICITADO · SEM ESTADO PERSISTIDO" if requested else "NÃO SOLICITADO",
                "warn" if requested else "neutral",
                f"audit.db → standards_service_runs[{item.id}]",
                (),
                "Nenhuma linha de execução do serviço foi encontrada para este AUD." if requested else "",
            )
        )
    return rows


def _core_rows(
    connection: sqlite3.Connection,
    audit_id: str,
    configuration: Mapping[str, Any],
) -> list[ExecutionEvidenceRow]:
    settings = _settings(configuration)
    ai = settings.get("ai") if isinstance(settings.get("ai"), Mapping) else {}
    web_cfg = settings.get("web_performance") if isinstance(settings.get("web_performance"), Mapping) else {}
    apdex_cfg = settings.get("synthetic_apdex") if isinstance(settings.get("synthetic_apdex"), Mapping) else {}
    ux_cfg = settings.get("synthetic_apdex_experience") if isinstance(settings.get("synthetic_apdex_experience"), Mapping) else {}
    search = configuration.get("search_intelligence") if isinstance(configuration.get("search_intelligence"), Mapping) else {}
    env = _environment(configuration)
    work = _work_items(connection, audit_id)

    provider = str(ai.get("provider") or "none").strip().casefold()
    semantic_requested = provider not in {"", "none"}
    technical_requested = _bool(ai.get("technical_remediation"))
    content_requested = _bool(ai.get("content_remediation"))
    web_requested = _bool(web_cfg.get("enabled"))
    apdex_requested = _bool(apdex_cfg.get("enabled"))
    ux_requested = _bool(ux_cfg.get("enabled"))
    search_requested = _bool(search.get("enabled"), default=bool(search.get("queries")))
    improvement_requested = _bool(env.get("RASAI_IMPROVEMENT_INTELLIGENCE"))

    web_enabled, categories, web_status, web_reason = _web_state(connection, audit_id)
    if not web_cfg and web_enabled:
        web_requested = True

    rows = [
        _work_item_row(
            "CORE_AUDIT",
            "Coleta e análise principal",
            True,
            "Contrato base da auditoria",
            work.get("CORE_AUDIT", ()),
            technical_ref="audit.db → audits / pages / page_snapshots / audit_fulfillment_work_items[CORE_AUDIT]",
            fallback_status="CONCLUÍDO" if _table_exists(connection, "audits") else "SEM ESTADO PERSISTIDO",
            fallback_tone="good" if _table_exists(connection, "audits") else "warn",
        ),
        _work_item_row(
            "SEMANTIC_AI",
            "Análise semântica por IA",
            semantic_requested,
            _profile_source(configuration, "SEMANTIC_AI"),
            work.get("SEMANTIC_AI", ()),
            technical_ref="audit.db → ai_audit_sessions / ai_provider_attempts / audit_fulfillment_work_items[SEMANTIC_AI]",
        ),
        _work_item_row(
            "TECHNICAL_AI",
            "Análise técnica de crawling/discovery por IA",
            technical_requested,
            _profile_source(configuration, "TECHNICAL_AI"),
            work.get("TECHNICAL_AI", ()),
            technical_ref="audit.db → m24_runs / ai_provider_attempts / audit_fulfillment_work_items[TECHNICAL_AI]",
        ),
        _work_item_row(
            "CONTENT_REMEDIATION_AI",
            "Remediação textual / conteúdo por IA",
            content_requested,
            _profile_source(configuration, "CONTENT_REMEDIATION_AI"),
            work.get("CONTENT_REMEDIATION_AI", ()),
            technical_ref="audit.db → content_remediation_runs / ai_provider_attempts / audit_fulfillment_work_items[CONTENT_REMEDIATION_AI]",
        ),
        _work_item_row(
            "IMPROVEMENT_INTELLIGENCE",
            "Análise profunda e melhorias",
            improvement_requested,
            _profile_source(configuration, "IMPROVEMENT_INTELLIGENCE"),
            work.get("IMPROVEMENT_INTELLIGENCE", ()),
            technical_ref="audit.db → improvement_intelligence_runs / ai_provider_attempts / audit_fulfillment_work_items[IMPROVEMENT_INTELLIGENCE]",
        ),
        _work_item_row(
            "WEB_PERFORMANCE",
            "Web Performance / PageSpeed / Lighthouse",
            web_requested or web_enabled,
            _profile_source(configuration, "WEB_PERFORMANCE"),
            work.get("WEB_PERFORMANCE", ()),
            technical_ref="audit.db → web_performance_runs / web_performance_attempts / web_performance_observations",
            fallback_status="CONCLUÍDO" if web_status.upper() == "SUCCESS" else ("NÃO SOLICITADO" if not (web_requested or web_enabled) else "SOLICITADO · SEM RESULTADO UTILIZÁVEL"),
            fallback_tone="good" if web_status.upper() == "SUCCESS" else ("neutral" if not (web_requested or web_enabled) else "warn"),
            fallback_detail=web_reason,
        ),
    ]

    lighthouse_specs = (
        ("LIGHTHOUSE_PERFORMANCE", "Lighthouse Performance", "performance", "performance_score"),
        ("LIGHTHOUSE_ACCESSIBILITY", "Lighthouse Accessibility", "accessibility", "accessibility_score"),
        ("LIGHTHOUSE_BEST_PRACTICES", "Lighthouse Best Practices", "best-practices", "best_practices_score"),
        ("LIGHTHOUSE_SEO", "Lighthouse SEO técnico", "seo", "seo_score"),
        ("LIGHTHOUSE_AGENTIC", "Lighthouse Agentic Browsing (experimental)", "agentic-browsing", "agentic_browsing_score"),
    )
    rows.extend(
        _lighthouse_row(
            connection,
            audit_id,
            configuration,
            capability=capability,
            label=label,
            category=category,
            column=column,
            web_enabled=web_enabled,
            categories=categories,
            web_status=web_status,
            web_reason=web_reason,
        )
        for capability, label, category, column in lighthouse_specs
    )

    rows.extend(
        (
            _work_item_row(
                "SYNTHETIC_APDEX",
                "Synthetic Navigation Apdex",
                apdex_requested,
                _profile_source(configuration, "SYNTHETIC_APDEX"),
                work.get("SYNTHETIC_APDEX", ()),
                technical_ref="audit.db → synthetic_apdex_runs / synthetic_apdex_summaries / audit_fulfillment_work_items[SYNTHETIC_APDEX]",
            ),
            _work_item_row(
                "EXPERIENCE_APDEX",
                "Synthetic User Experience Apdex",
                ux_requested,
                _profile_source(configuration, "EXPERIENCE_APDEX"),
                work.get("EXPERIENCE_APDEX", ()),
                technical_ref="audit.db → synthetic_ux_apdex_runs / synthetic_ux_apdex_summaries / audit_fulfillment_work_items[EXPERIENCE_APDEX]",
            ),
            _work_item_row(
                "SEARCH_INTELLIGENCE",
                "Search Intelligence / SERP",
                search_requested,
                _profile_source(configuration, "SEARCH_INTELLIGENCE"),
                work.get("SEARCH_INTELLIGENCE", ()),
                technical_ref="audit.db → serp_observations / audit_fulfillment_work_items[SEARCH_INTELLIGENCE]",
            ),
        )
    )
    return rows


def _summary(connection: sqlite3.Connection, audit_id: str) -> Mapping[str, Any]:
    if not _table_exists(connection, "audit_fulfillment_contracts"):
        return {}
    row = _one(
        connection,
        "SELECT processing_status,score_status,report_status,consolidation_eligible,required_items,successful_items,pending_items,blocked_items,reprocess_count FROM audit_fulfillment_contracts WHERE audit_id=?",
        (audit_id,),
    )
    return dict(row) if row is not None else {}


def _status_chip(status: str, tone: str) -> str:
    return f"<span class='execution-state execution-state-{escape(tone, quote=True)}'>{escape(status)}</span>"


def _render_rows(rows: Sequence[ExecutionEvidenceRow]) -> str:
    body: list[str] = []
    for row in rows:
        missing = "<br>".join(f"<code>{escape(item)}</code>" for item in row.missing_configuration) or "—"
        detail = f"<br><small>{escape(row.detail)}</small>" if row.detail else ""
        body.append(
            "<tr>"
            f"<td><strong>{escape(row.capability)}</strong>{detail}</td>"
            f"<td>{'Sim' if row.requested else 'Não'}</td>"
            f"<td>{escape(row.source)}</td>"
            f"<td>{_status_chip(row.status, row.tone)}</td>"
            f"<td><code>{escape(row.technical_ref)}</code></td>"
            f"<td>{missing}</td>"
            "</tr>"
        )
    return "".join(body)


def _integrity_tone(label: str) -> str:
    return "good" if label == "ÍNTEGRO" else "bad" if label in {"HASH DIVERGENTE", "SNAPSHOT CORROMPIDO"} else "warn"


def _profile_metrics(configuration: Mapping[str, Any]) -> str:
    profile = _profile(configuration)
    if not profile:
        return (
            "<div class='metric'><small>Perfil de execução</small><strong>Personalizado / sem preset persistido</strong></div>"
            "<div class='metric'><small>Overrides após perfil</small><strong>—</strong></div>"
        )
    label = str(profile.get("label") or profile.get("profile_id") or "-")
    modules = ", ".join(str(item) for item in profile.get("modules", ()) if str(item)) or "—"
    overrides = ", ".join(str(item) for item in profile.get("manual_overrides", ()) if str(item)) or "nenhum"
    ai_mode = str(profile.get("ai_mode") or "-")
    return (
        f"<div class='metric'><small>Perfil de execução</small><strong>{escape(label)}</strong></div>"
        f"<div class='metric'><small>Módulos do perfil</small><strong>{escape(modules)}</strong></div>"
        f"<div class='metric'><small>IA do perfil</small><strong>{escape(ai_mode)}</strong></div>"
        f"<div class='metric'><small>Overrides após perfil</small><strong>{escape(overrides)}</strong></div>"
    )


def write_execution_evidence_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    """Write the complete execution option/configuration/evidence matrix for one AUD."""
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        configuration, persisted_hash, computed_hash, integrity = _load_configuration(connection, audit_id)
        rows = _core_rows(connection, audit_id, configuration)
        rows.extend(_standard_rows(connection, audit_id, configuration))
        summary = _summary(connection, audit_id)
    finally:
        connection.close()

    nav = render_report_navigation(report_dir, REPORT_FILE)
    required = int(summary.get("required_items") or 0)
    successful = int(summary.get("successful_items") or 0)
    processing = str(summary.get("processing_status") or "SEM CONTRATO DE FULFILLMENT")
    consolidation = "ELEGÍVEL" if bool(summary.get("consolidation_eligible")) else "NÃO ELEGÍVEL"
    persisted_short = persisted_hash[:16] + "…" if len(persisted_hash) > 16 else (persisted_hash or "—")
    computed_short = computed_hash[:16] + "…" if len(computed_hash) > 16 else (computed_hash or "—")

    style = """
<style id='rasai-execution-evidence-style'>
.execution-state{display:inline-flex;padding:4px 8px;border-radius:999px;font-size:.74rem;font-weight:760;white-space:nowrap;border:1px solid transparent}
.execution-state-good{background:#edf7f0;color:#3f7452;border-color:rgba(63,116,82,.25)}
.execution-state-warn{background:#fff7e8;color:#7b5728;border-color:rgba(123,87,40,.25)}
.execution-state-bad{background:#fff0f0;color:#8f4447;border-color:rgba(143,68,71,.25)}
.execution-state-neutral{background:#f4f6f8;color:#5d6878;border-color:rgba(93,104,120,.22)}
.execution-evidence-table td:nth-child(1){min-width:220px}.execution-evidence-table td:nth-child(3){min-width:180px}.execution-evidence-table td:nth-child(5){min-width:280px}.execution-evidence-table code{font-size:.78rem;overflow-wrap:anywhere}.execution-evidence-integrity{border-left:4px solid var(--blue,#657fc6)}
@media(max-width:900px){.execution-evidence-table{font-size:.82rem}.execution-evidence-table td:nth-child(5){min-width:220px}}
</style>
"""
    html = f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Evidências da execução - RASAi - Search & AI Readiness Auditor</title><link rel='stylesheet' href='css/site.css'>{style}</head><body>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>Rastreabilidade da execução</div><h1>Evidências da execução</h1><p class='lead'>Matriz read-only do que a auditoria podia executar, do que o usuário/perfil efetivamente solicitou e do estado materializado. Capacidades não solicitadas são neutras: não representam falha e não devem reduzir o fulfillment do AUD.</p><div class='metric-grid'><div class='metric'><small>Audit ID</small><strong>{escape(audit_id)}</strong></div><div class='metric'><small>Status lógico do AUD</small><strong>{escape(processing)}</strong></div><div class='metric'><small>Requisitos aplicáveis</small><strong>{successful}/{required} atendidos</strong></div><div class='metric'><small>Consolidação</small><strong>{escape(consolidation)}</strong></div>{_profile_metrics(configuration)}</div></header>
<section class='panel execution-evidence-integrity'><div class='kicker'>Integridade da configuração</div><h2>Contrato efetivo persistido</h2><p class='intro'>O snapshot é secret-free e representa a configuração efetiva da execução depois da aplicação do perfil e dos overrides explícitos do usuário. O hash permite detectar divergência do conteúdo persistido sem depender do INI ou do ambiente atual da máquina.</p><div class='metric-grid'><div class='metric'><small>Integridade</small><strong>{_status_chip(integrity, _integrity_tone(integrity))}</strong></div><div class='metric'><small>Hash persistido</small><strong><code>{escape(persisted_short)}</code></strong></div><div class='metric'><small>Hash recalculado</small><strong><code>{escape(computed_short)}</code></strong></div></div><div class='notice'><strong>Limite de segurança:</strong> credenciais, tokens, secrets e senhas não são persistidos nem renderizados. Quando faltarem, esta página mostra somente o nome da variável/configuração esperada.</div></section>
<section class='panel'><div class='kicker'>Configuração × execução</div><h2>Todas as capacidades e o estado desta auditoria</h2><p class='intro'>“Ativada = Não” significa decisão de configuração, não indisponibilidade. “Configuração necessária” significa que a capacidade foi solicitada, mas faltou um requisito. “Falha” significa que houve execução/tentativa materializada e o diagnóstico técnico deve ser consultado na referência indicada.</p><div class='table-wrap'><table class='execution-evidence-table'><thead><tr><th>Opção / capacidade</th><th>Ativada?</th><th>Origem da decisão</th><th>Estado</th><th>Onde verificar tecnicamente</th><th>Configuração faltante</th></tr></thead><tbody>{_render_rows(rows)}</tbody></table></div></section>
<section class='notice'><strong>Regra de leitura:</strong> somente requisitos solicitados/aplicáveis participam do contrato de conclusão. Capacidades desabilitadas, não solicitadas ou não aplicáveis não devem transformar a auditoria em preliminar. Um erro de API/provider também não é finding do website.</section>
<footer class='footer'>Fonte: audit.db e contratos persistidos da própria execução. Esta página não executa coletores, não chama IA, não recalcula score e não altera evidências.</footer></main></body></html>\n"""
    path = report_dir / REPORT_FILE
    path.write_text(html, encoding="utf-8", newline="\n")
    return path


_ARTICLE_RE_TEMPLATE = (
    r"<article(?P<attrs>[^>]*\bindicator-card\b[^>]*)>"
    r"(?P<body>.*?<h3>{title}</h3>.*?)</article>"
)


def _rewrite_indicator_card(html: str, title: str, *, value: str, detail: str) -> str:
    pattern = re.compile(
        _ARTICLE_RE_TEMPLATE.format(title=re.escape(title)),
        flags=re.IGNORECASE | re.DOTALL,
    )

    def replace(match: re.Match[str]) -> str:
        attrs = re.sub(r"\bcondition-[A-Za-z0-9_-]+\b", "condition-neutral", match.group("attrs"))
        body = match.group("body")
        body, count_values = re.subn(
            r"<div class=['\"]indicator-values['\"]>.*?</div>",
            f"<div class='score-number indicator-score'>{escape(value)}</div>",
            body,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not count_values:
            body, count_score = re.subn(
                r"<div class=['\"]score-number indicator-score['\"]>.*?</div>",
                f"<div class='score-number indicator-score'>{escape(value)}</div>",
                body,
                count=1,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not count_score:
                body = re.sub(
                    rf"(<h3>{re.escape(title)}</h3>)",
                    rf"\1<div class='score-number indicator-score'>{escape(value)}</div>",
                    body,
                    count=1,
                    flags=re.IGNORECASE,
                )
        body = re.sub(
            r"<span class=['\"]indicator-condition['\"]>.*?</span>",
            "<span class='indicator-condition'>Não solicitado</span>",
            body,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        body = re.sub(
            r"<p class=['\"]intro['\"]>.*?</p>",
            f"<p class='intro'>{escape(detail)}</p>",
            body,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return f"<article{attrs}>{body}</article>"

    return pattern.sub(replace, html, count=1)


_FALSE_DISABLED_DEPENDENCY_RE = re.compile(
    r"<section class=['\"][^'\"]*\breport-dependency-state\b[^'\"]*['\"][^>]*"
    r"data-report-dependency-state=['\"]true['\"][^>]*>"
    r"(?:(?!</section>).)*?desabilitad[oa](?:\s+por\s+configura(?:ç|c)ão)?\s+nesta\s+execu(?:ç|c)ão\.?.*?</section>",
    flags=re.IGNORECASE | re.DOTALL,
)


def reconcile_execution_state_presentation(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Align HTML wording with the effective requested/not-requested execution state."""
    report_dir = workspace.root / "report"
    index = report_dir / "index.html"
    accessibility = report_dir / "accessibility.html"
    if not report_dir.is_dir():
        return

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        web_enabled, categories, _, _ = _web_state(connection, audit_id)
    finally:
        connection.close()

    if index.is_file():
        try:
            html = index.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            html = ""
        if html:
            specs = (
                ("Lighthouse Performance", "performance"),
                ("Lighthouse Accessibility", "accessibility"),
                ("Lighthouse Best Practices", "best-practices"),
                ("Lighthouse SEO técnico", "seo"),
            )
            if not web_enabled:
                html = _rewrite_indicator_card(
                    html,
                    "Core Web Vitals",
                    value="DESABILITADO",
                    detail="Web Performance/CrUX não foi solicitado nesta execução.",
                )
            for title, category in specs:
                if not web_enabled:
                    html = _rewrite_indicator_card(
                        html,
                        title,
                        value="DESABILITADO",
                        detail="Web Performance/Lighthouse não foi solicitado nesta execução.",
                    )
                elif category not in categories:
                    html = _rewrite_indicator_card(
                        html,
                        title,
                        value="NÃO SOLICITADO",
                        detail=f"A categoria Lighthouse '{category}' não foi solicitada pelo perfil/configuração efetiva desta execução.",
                    )
            html = _FALSE_DISABLED_DEPENDENCY_RE.sub("", html)
            try:
                index.write_text(html, encoding="utf-8", newline="\n")
            except OSError:
                pass

    if accessibility.is_file() and (not web_enabled or "accessibility" not in categories):
        try:
            html = accessibility.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            html = ""
        if html:
            html = _FALSE_DISABLED_DEPENDENCY_RE.sub("", html)
            if web_enabled:
                replacement = "Categoria accessibility não solicitada pelo perfil/configuração desta execução."
                html = html.replace("NÃO DISPONÍVEL", "NÃO SOLICITADO")
                html = html.replace("Sem dados suficientes", "Não solicitado nesta execução")
                html = html.replace("Nenhum contexto válido", replacement)
            try:
                accessibility.write_text(html, encoding="utf-8", newline="\n")
            except OSError:
                pass

    # Intentional disabled states are neutral on every specialized page. The common
    # reader-status layer will still explain the disabled/not-requested capability.
    for path in report_dir.glob("*.html"):
        if path.name in {"index.html", "accessibility.html"}:
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        updated = _FALSE_DISABLED_DEPENDENCY_RE.sub("", html)
        if updated != html:
            try:
                path.write_text(updated, encoding="utf-8", newline="\n")
            except OSError:
                pass


def _patch_project_report_validity() -> None:
    """Refresh the matrix after fulfillment reaches its final state for this pass."""
    from rasai import audit_fulfillment

    original = audit_fulfillment.project_report_validity
    if bool(getattr(original, "_rasai_execution_evidence_reporting", False)):
        return

    def project_with_execution_evidence(*args: Any, **kwargs: Any):
        summary = original(*args, **kwargs)
        workspace = kwargs.get("workspace")
        audit_id = str(kwargs.get("audit_id") or "")
        if workspace is not None and audit_id:
            try:
                write_execution_evidence_report(audit_id=audit_id, workspace=workspace)
                reconcile_execution_state_presentation(audit_id=audit_id, workspace=workspace)
                from rasai import report_navigation

                report_navigation.normalize_report_navigation(workspace.root / "report")
            except Exception:
                # Presentation must not rewrite or invalidate already persisted audit evidence.
                pass
        return summary

    project_with_execution_evidence._rasai_execution_evidence_reporting = True  # type: ignore[attr-defined]
    project_with_execution_evidence._rasai_original = original  # type: ignore[attr-defined]
    audit_fulfillment.project_report_validity = project_with_execution_evidence

    # Several recovery modules import the function by value. Replace only references
    # still pointing to the exact predecessor, preserving wrapper ownership/order.
    for module_name in (
        "rasai.audit_fulfillment_runtime",
        "rasai.audit_reprocess",
        "rasai.core_reprocessing",
        "rasai.core_reprocessing_context",
        "rasai.fulfillment_execution_contract",
    ):
        module = sys.modules.get(module_name)
        if module is not None and getattr(module, "project_report_validity", None) is original:
            module.project_report_validity = project_with_execution_evidence


def install() -> None:
    """Install final fulfillment-state projection without changing runtime execution."""
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_project_report_validity()
    _INSTALLED = True
