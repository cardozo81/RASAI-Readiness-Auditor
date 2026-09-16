"""Late report adherence corrections for the pre-production catalog projection.

This module changes presentation only. Persisted values remain untouched.  The
installer is deliberately repairable because ``catalog_report_final_refinements`` is
reapplied on every materialization and may rebind selected renderer functions.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import threading
from html import escape
from typing import Any, Mapping, Sequence

_CONTEXT = threading.local()

_STATUS_PT = {
    "SUCCESS": "Concluído",
    "COMPLETE": "Concluído",
    "COMPLETED": "Concluído",
    "FINAL": "Concluído",
    "READY": "Disponível",
    "AVAILABLE": "Disponível",
    "MEASURED": "Medido",
    "GENERATED": "Gerado",
    "CONSOLIDATED": "Consolidado",
    "PARTIAL": "Parcial",
    "FAILED_RETRYABLE": "Falha reprocessável",
    "FAILED_PERMANENT": "Falha permanente",
    "FAILED_FATAL": "Falha fatal",
    "FAILURE": "Falha",
    "ERROR": "Erro",
    "CONTRACT_ERROR": "Erro de resposta contratual",
    "BLOCKED": "Bloqueado",
    "DISABLED": "Desabilitado",
    "NOT_REQUESTED": "Não solicitado",
    "NOT_APPLICABLE": "Não aplicável",
    "REQUESTED_NOT_EXECUTED": "Solicitado, não executado",
    "NOT_CONFIGURED": "Não configurado",
    "SKIPPED": "Ignorado",
    "ABSENT": "Não encontrado",
    "UNAVAILABLE": "Sem dados disponíveis",
    "RUNNING": "Em execução",
    "PENDING": "Pendente",
    "PROCESSING": "Em processamento",
    "WAITING_FOR_DATA": "Aguardando dados",
    "NOT_DETERMINABLE": "Não determinável com os dados desta auditoria",
    "UNKNOWN": "Não determinado",
    "COMPLETE_WITH_LIMITATIONS": "Concluído com limitações",
    "APPLICATION_ERROR": "Erro da aplicação",
    "INVALID_SAMPLE": "Amostra inválida",
    "BROWSER_UNAVAILABLE": "Navegador indisponível",
    "TIMEOUT": "Tempo limite excedido",
    "NAVIGATION_ERROR": "Erro de navegação",
}

_CAPABILITY_PT = {
    "web-performance": "Desempenho web",
    "search-intelligence": "Inteligência de busca / SERP",
}

_COMPONENT_PT = {
    "WEB_PERFORMANCE": "Desempenho web",
    "SEARCH_INTELLIGENCE": "Inteligência de busca / SERP",
    "GSC": "Google Search Console",
    "GOOGLE_SEARCH_CONSOLE": "Google Search Console",
    "AI_VISIBILITY": "Visibilidade em respostas de IA",
    "OBSERVABILITY": "Observabilidade externa",
    "SYNTHETIC_UX_APDEX": "Apdex de experiência",
}

_LIMITATION_PT = {
    "RENDERED_DISCOVERY_GAP": "Lacuna na descoberta renderizada",
    "RENDER_DISCOVERY_GAP": "Lacuna na descoberta renderizada",
    "DISCOVERY_GAP": "Lacuna de descoberta",
    "PARTIAL_RENDERED_DISCOVERY": "Descoberta renderizada parcial",
}


def _norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").upper()).strip("_")


def _human_status_value(value: Any, fallback: Any | None = None) -> str:
    direct = _STATUS_PT.get(_norm(value))
    if direct:
        return direct
    if callable(fallback):
        return str(fallback(value))
    return str(value or "—").replace("_", " ").title()


def _human_limitation(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Limitação registrada"
    code, separator, detail = raw.partition(":")
    label = _LIMITATION_PT.get(_norm(code))
    if label:
        return f"{label}: {detail.strip()}" if separator and detail.strip() else label
    return f"Limitação técnica registrada ({raw})"


def _audit_limitations(data: Any) -> tuple[str, ...]:
    raw = getattr(data, "audit", {}).get("limitations") if isinstance(getattr(data, "audit", None), Mapping) else None
    if raw in (None, "", [], ()):
        return ()
    value: Any = raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            value = [raw]
    if isinstance(value, Mapping):
        value = list(value.values())
    if not isinstance(value, (list, tuple, set)):
        value = [value]
    return tuple(_human_limitation(item) for item in value if str(item or "").strip())


def _audit_hero(data: Any, title: str, subtitle: str) -> str:
    """Expose logical AUD state and base-audit limitations as separate dimensions."""
    from rasai import catalog_report_presentation as p

    target = data.targets[0] if getattr(data, "targets", ()) else "—"
    audit = data.audit if isinstance(getattr(data, "audit", None), Mapping) else {}
    fulfillment = data.fulfillment if isinstance(getattr(data, "fulfillment", None), Mapping) else {}
    project = str(audit.get("project_name") or "—")
    logical_raw = fulfillment.get("processing_status") or audit.get("completion_status") or audit.get("status")
    base_raw = audit.get("completion_status") or audit.get("status")
    limitations = _audit_limitations(data)

    metrics = "<div class='metric-grid'>"
    metrics += p._metric("URL auditada", target)
    metrics += p._metric("Projeto", project)
    metrics += p._metric("Resultado lógico da AUD", p._status_label(logical_raw))
    metrics += p._metric("Auditoria-base", p._status_label(base_raw))
    metrics += p._metric("Catálogos selecionados", len(getattr(data, "selected", ())))
    metrics += "</div>"

    limitation_html = ""
    if limitations:
        limitation_html = (
            "<div class='notice warn'><strong>Limitações registradas na auditoria-base:</strong> "
            + escape("; ".join(limitations))
            + ". O resultado lógico da AUD e o estado de cada catálogo são apresentados separadamente.</div>"
        )
    return (
        f"<header class='hero'><div class='eyebrow'>Auditoria {escape(str(data.audit_id))}</div>"
        f"<h1>{escape(title)}</h1><p>{escape(subtitle)}</p>{metrics}{limitation_html}</header>"
    )


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone() is not None


def _audit_count(connection: sqlite3.Connection, table: str, audit_id: str) -> int:
    if not _table_exists(connection, table):
        return 0
    columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if "audit_id" not in columns:
        return 0
    row = connection.execute(f"SELECT COUNT(*) FROM {table} WHERE audit_id=?", (audit_id,)).fetchone()
    return int(row[0] or 0) if row else 0


def _work_state(data: Any, components: set[str]) -> str | None:
    rows = [
        row for row in getattr(data, "work_items", ())
        if _norm(row.get("component")) in components
    ]
    if not rows:
        return None
    states = [_norm(row.get("status")) for row in rows]
    failure = next((state for state in states if state.startswith("FAILED") or state in {"ERROR", "FAILURE", "BLOCKED", "CONTRACT_ERROR", "UNAVAILABLE"}), None)
    if failure:
        return _human_status_value(failure)
    pending = next((state for state in states if state in {"PARTIAL", "PENDING", "RUNNING", "PROCESSING", "WAITING_FOR_DATA", "REQUESTED_NOT_EXECUTED", "NOT_CONFIGURED"}), None)
    if pending:
        return _human_status_value(pending)
    success = next((state for state in states if state in {"SUCCESS", "COMPLETE", "COMPLETED", "READY", "AVAILABLE", "FINAL"}), None)
    if success:
        return "Concluída"
    return _human_status_value(states[-1]) if states else None


def _cat05_capability_states(database: Any, data: Any) -> dict[str, str]:
    """Resolve each independent CAT-05 capability from its own evidence/work state."""
    if "CAT-05" not in getattr(data, "selected", set()):
        return {
            "search-intelligence": "Não solicitada",
            "google-search-console": "Não solicitada",
            "ai-visibility": "Não solicitada",
            "observability": "Não solicitada",
        }

    connection = sqlite3.connect(database)
    try:
        serp = _audit_count(connection, "serp_observations", data.audit_id)
        gsc = _audit_count(connection, "gsc_search_performance", data.audit_id)
        ai_visibility = (
            _audit_count(connection, "generative_visibility_query_runs", data.audit_id)
            + _audit_count(connection, "generative_visibility_page_citations", data.audit_id)
        )
    finally:
        connection.close()

    search_work = _work_state(data, {"SEARCH_INTELLIGENCE"})
    gsc_work = _work_state(data, {"GSC", "GOOGLE_SEARCH_CONSOLE"})
    ai_work = _work_state(data, {"AI_VISIBILITY", "GENERATIVE_VISIBILITY"})
    obs_work = _work_state(data, {"OBSERVABILITY", "EXTERNAL_OBSERVABILITY"})

    search_cfg = getattr(data, "configuration", {}).get("search_intelligence") if isinstance(getattr(data, "configuration", None), Mapping) else None
    search_requested = bool(search_cfg.get("enabled")) if isinstance(search_cfg, Mapping) else False

    return {
        "search-intelligence": "Concluída" if serp else (search_work or ("Solicitada sem resultado" if search_requested else "Não requerida nesta AUD")),
        "google-search-console": "Concluída" if gsc else (gsc_work or "Não requerida nesta AUD"),
        "ai-visibility": "Concluída" if ai_visibility else (ai_work or "Não requerida nesta AUD"),
        "observability": obs_work or "Não requerida nesta AUD",
    }


def _normalize_configuration_rows(rows: Sequence[Sequence[Any]], catalog_id: str) -> list[Sequence[Any]]:
    from rasai import catalog_report_presentation as p

    normalized: list[Sequence[Any]] = []
    for row in rows:
        values = list(row)
        if not values:
            normalized.append(row)
            continue
        label = str(values[0])
        if label == "Search Intelligence":
            values[0] = "Inteligência de busca / SERP"
        elif label == "Web Performance":
            values[0] = "Desempenho web"

        if len(values) > 1 and catalog_id == "CAT-05" and str(values[0]) == "Dispositivo":
            values[1] = p._device_label(values[1])
        if len(values) > 1 and str(values[0]) == "Fonte de dados de campo":
            field_source = str(values[1] or "").strip().casefold()
            values[1] = {
                "auto": "Automática",
                "automatic": "Automática",
                "none": "Sem dados de campo",
                "crux": "Chrome UX Report (CrUX)",
            }.get(field_source, values[1])
        if len(values) > 1 and str(values[0]) == "Categorias Lighthouse":
            text = str(values[1] or "")
            replacements = {
                "performance": "desempenho",
                "accessibility": "acessibilidade",
                "best-practices": "boas práticas",
                "best practices": "boas práticas",
            }
            for source, target in replacements.items():
                text = re.sub(rf"\b{re.escape(source)}\b", target, text, flags=re.I)
            values[1] = text
        normalized.append(tuple(values))
    return normalized


def _install_public_labels() -> None:
    from rasai import catalog_report_catalog_state as state
    from rasai import catalog_report_presentation as presentation

    current_status = presentation._status_label
    if not getattr(current_status, "_rasai_adherence_pt", False):
        original_status = getattr(current_status, "_rasai_original", current_status)

        def status_label(value: Any) -> str:
            return _human_status_value(value, original_status)

        status_label._rasai_adherence_pt = True  # type: ignore[attr-defined]
        status_label._rasai_original = original_status  # type: ignore[attr-defined]
    else:
        status_label = current_status

    current_capability = presentation._capability_label
    if not getattr(current_capability, "_rasai_adherence_pt", False):
        original_capability = getattr(current_capability, "_rasai_original", current_capability)

        def capability_label(value: Any) -> str:
            raw = str(value or "")
            return _CAPABILITY_PT.get(raw, original_capability(value))

        capability_label._rasai_adherence_pt = True  # type: ignore[attr-defined]
        capability_label._rasai_original = original_capability  # type: ignore[attr-defined]
    else:
        capability_label = current_capability

    current_component = state._friendly_component
    if not getattr(current_component, "_rasai_adherence_pt", False):
        original_component = getattr(current_component, "_rasai_original", current_component)

        def friendly_component(value: Any) -> str:
            return _COMPONENT_PT.get(_norm(value), original_component(value))

        friendly_component._rasai_adherence_pt = True  # type: ignore[attr-defined]
        friendly_component._rasai_original = original_component  # type: ignore[attr-defined]
    else:
        friendly_component = current_component

    current_domain = presentation._domain_label
    if not getattr(current_domain, "_rasai_adherence_pt", False):
        original_domain = getattr(current_domain, "_rasai_original", current_domain)

        def domain_label(value: Any) -> str:
            if _norm(value) == "PERFORMANCE":
                return "Desempenho"
            return original_domain(value)

        domain_label._rasai_adherence_pt = True  # type: ignore[attr-defined]
        domain_label._rasai_original = original_domain  # type: ignore[attr-defined]
    else:
        domain_label = current_domain

    presentation._status_label = status_label
    presentation._capability_label = capability_label
    presentation._domain_label = domain_label
    state._friendly_component = friendly_component

    module_names = (
        "rasai.catalog_report_catalog_state",
        "rasai.catalog_report_metrics",
        "rasai.catalog_report_evidence",
        "rasai.catalog_report_analysis",
        "rasai.catalog_report_page",
        "rasai.catalog_report_governance",
        "rasai.catalog_report_integrations",
        "rasai.catalog_report_site",
    )
    for name in module_names:
        module = sys.modules.get(name)
        if module is None:
            continue
        if hasattr(module, "_status_label"):
            setattr(module, "_status_label", status_label)
        if hasattr(module, "_capability_label"):
            setattr(module, "_capability_label", capability_label)
        if hasattr(module, "_friendly_component"):
            setattr(module, "_friendly_component", friendly_component)
        if hasattr(module, "_domain_label"):
            setattr(module, "_domain_label", domain_label)

    # Preserve branded metric names/acronyms while translating generic English labels.
    from rasai import catalog_report_metrics as metrics
    translated = {
        "performance_score": "Lighthouse · Desempenho",
        "accessibility_score": "Lighthouse · Acessibilidade",
        "best_practices_score": "Lighthouse · Boas práticas",
        "seo_score": "Lighthouse · SEO",
        "speed_index_lab_ms": "Índice de velocidade (Speed Index)",
        "tbt_lab_ms": "Tempo total de bloqueio (TBT)",
    }
    metrics._WEB_METRICS = tuple(
        (field, translated.get(field, label), unit) for field, label, unit in metrics._WEB_METRICS
    )


def _install_hero() -> None:
    from rasai import catalog_report_presentation as presentation

    presentation._audit_hero = _audit_hero
    for name in (
        "rasai.catalog_report_catalog_state",
        "rasai.catalog_report_metrics",
        "rasai.catalog_report_evidence",
        "rasai.catalog_report_analysis",
        "rasai.catalog_report_page",
        "rasai.catalog_report_governance",
        "rasai.catalog_report_integrations",
        "rasai.catalog_report_site",
    ):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "_audit_hero"):
            setattr(module, "_audit_hero", _audit_hero)


def _install_cat05_scope_states() -> None:
    from rasai import catalog_report_page as page

    current_table = page._table
    if not getattr(current_table, "_rasai_cat05_capability_state", False):
        original_table = getattr(current_table, "_rasai_original", current_table)

        def table(headers: Sequence[str], rows: Sequence[Sequence[Any]], **kwargs: Any) -> str:
            state_by_label = getattr(_CONTEXT, "cat05_state_by_label", None)
            effective_headers = headers
            effective_rows = rows
            if state_by_label and tuple(headers) == ("Capacidade", "Situação"):
                effective_headers = ("Capacidade", "Estado nesta AUD")
                effective_rows = [
                    (row[0], state_by_label.get(str(row[0]), row[1])) if len(row) >= 2 else row
                    for row in rows
                ]
            return original_table(effective_headers, effective_rows, **kwargs)

        table._rasai_cat05_capability_state = True  # type: ignore[attr-defined]
        table._rasai_original = original_table  # type: ignore[attr-defined]
        page._table = table

    current_body = page._catalog_body
    if not getattr(current_body, "_rasai_cat05_capability_state", False):
        original_body = getattr(current_body, "_rasai_original", current_body)

        def catalog_body(database: Any, data: Any, catalog_id: str) -> str:
            previous = getattr(_CONTEXT, "cat05_state_by_label", None)
            if catalog_id == "CAT-05":
                states = _cat05_capability_states(database, data)
                _CONTEXT.cat05_state_by_label = {
                    page._capability_label(capability_id): status for capability_id, status in states.items()
                }
            try:
                return original_body(database, data, catalog_id)
            finally:
                if previous is None:
                    try:
                        delattr(_CONTEXT, "cat05_state_by_label")
                    except AttributeError:
                        pass
                else:
                    _CONTEXT.cat05_state_by_label = previous

        catalog_body._rasai_cat05_capability_state = True  # type: ignore[attr-defined]
        catalog_body._rasai_original = original_body  # type: ignore[attr-defined]
        page._catalog_body = catalog_body

    current_config = page._configuration_rows
    if not getattr(current_config, "_rasai_adherence_pt", False):
        original_config = getattr(current_config, "_rasai_original", current_config)

        def configuration_rows(data: Any, catalog_id: str) -> list[Sequence[Any]]:
            return _normalize_configuration_rows(original_config(data, catalog_id), catalog_id)

        configuration_rows._rasai_adherence_pt = True  # type: ignore[attr-defined]
        configuration_rows._rasai_original = original_config  # type: ignore[attr-defined]
        page._configuration_rows = configuration_rows


def _install_cat07_timestamp_copy() -> None:
    from rasai import catalog_report_analysis as analysis
    from rasai import catalog_report_page as page

    current = page._apdex_samples_html
    if getattr(current, "_rasai_individual_sample_time", False):
        return

    original = current

    def apdex_samples_html(database: Any, data: Any, *, experience: bool) -> str:
        html = original(database, data, experience=experience)
        if experience:
            html = html.replace(
                "O horário representa o <strong>momento persistido da captura da amostra</strong>; não é apresentado como horário de início da navegação.",
                "O horário representa o <strong>registro individual da medição</strong>, gravado quando cada amostra conclui sua coleta. Não é o horário de persistência em lote.",
            )
        return html

    apdex_samples_html._rasai_individual_sample_time = True  # type: ignore[attr-defined]
    apdex_samples_html._rasai_original = original  # type: ignore[attr-defined]
    page._apdex_samples_html = apdex_samples_html
    analysis._apdex_samples_html = apdex_samples_html


def install_catalog_report_adherence() -> None:
    """Install/repair all presentation corrections after late report refinements."""
    _install_public_labels()
    _install_hero()
    _install_cat05_scope_states()
    _install_cat07_timestamp_copy()


__all__ = [
    "_audit_hero",
    "_audit_limitations",
    "_cat05_capability_states",
    "_human_status_value",
    "install_catalog_report_adherence",
]
