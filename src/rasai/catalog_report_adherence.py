"""Final public-report adherence for the current pre-publication contract.

This module is presentation-only: it never changes persisted audit evidence or scores.
It runs after the report renderers are composed so the public projection uses one
consistent Portuguese vocabulary and the canonical provenance of each measurement.
"""
from __future__ import annotations

from collections import defaultdict
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
    "PASS": "Aprovado",
    "FAIL": "Não aprovado",
    "WARNING": "Atenção",
    "INFO": "Informativo",
    "PARTIAL": "Parcial",
    "FAILED_RETRYABLE": "Falha reprocessável",
    "FAILED_PERMANENT": "Falha permanente",
    "FAILED_FATAL": "Falha fatal",
    "FAILURE": "Falha",
    "ERROR": "Erro",
    "TECHNICAL_ERROR": "Erro técnico",
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
    "NO_DATA": "Sem dados",
    "INCOMPLETE": "Incompleto",
    "PRELIMINARY": "Preliminar",
    "RUNNING": "Em execução",
    "PENDING": "Pendente",
    "PROCESSING": "Em processamento",
    "WAITING_FOR_DATA": "Aguardando dados",
    "NOT_DETERMINABLE": "Não determinável com os dados desta auditoria",
    "UNKNOWN": "Não determinado",
    "COMPLETE_WITH_LIMITATIONS": "Concluído com limitações",
    "COMPLETED_WITH_LIMITATIONS": "Concluído com limitações",
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
    "GENERATIVE_VISIBILITY": "Visibilidade em respostas de IA",
    "OBSERVABILITY": "Observabilidade externa",
    "EXTERNAL_OBSERVABILITY": "Observabilidade externa",
    "IMPROVEMENT_INTELLIGENCE": "Análise profunda e melhorias",
    "SYNTHETIC_APDEX": "Apdex de navegação",
    "EXPERIENCE_APDEX": "Apdex de experiência",
    "SYNTHETIC_UX_APDEX": "Apdex de experiência",
}

_LIMITATION_PT = {
    "RENDERED_DISCOVERY_GAP": "Lacuna na descoberta renderizada",
    "RENDER_DISCOVERY_GAP": "Lacuna na descoberta renderizada",
    "DISCOVERY_GAP": "Lacuna de descoberta",
    "PARTIAL_RENDERED_DISCOVERY": "Descoberta renderizada parcial",
}

_STRUCTURED_EXPECTED_PT = {
    "structured data is syntactically interpretable when present": "Dados estruturados são sintaticamente interpretáveis quando presentes",
    "structured data types and relevant properties are identifiable": "Os tipos e as propriedades relevantes dos dados estruturados são identificáveis",
    "structured data remains consistent with visible page content": "Os dados estruturados permanecem consistentes com o conteúdo visível da página",
    "structured data entities remain consistent with observed page entities": "As entidades dos dados estruturados permanecem consistentes com as entidades observadas na página",
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
    """Expose logical AUD state without repeating the full base limitation on every CAT."""
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
    if limitations and title in {"Visão geral por catálogos", "Captura e contexto"}:
        limitation_html = (
            "<div class='notice warn'><strong>Limitações da auditoria-base:</strong> "
            + escape("; ".join(limitations))
            + ". Elas descrevem o escopo/cobertura da auditoria-base e não transformam, por si só, catálogos concluídos em falha.</div>"
        )
    elif limitations:
        limitation_html = (
            f"<div class='notice warn'><strong>Auditoria-base com {len(limitations)} limitação(ões).</strong> "
            "O estado funcional desta página é independente. <a href='capture-context.html'>Ver contexto e limitações da auditoria-base</a>.</div>"
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


def _sample_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("url") or ""),
        str(row.get("device") or "").upper(),
        str(row.get("profile_id") or ""),
    )


def _acquisition_timestamp_map(
    connection: sqlite3.Connection,
    audit_id: str,
    samples: Sequence[Mapping[str, Any]],
    *,
    experience: bool,
) -> dict[str, str]:
    """Match samples to their physical acquisition timestamp without inventing a time."""
    if not _table_exists(connection, "synthetic_apdex_acquisitions"):
        return {}
    if experience:
        rows = connection.execute(
            """SELECT * FROM synthetic_apdex_acquisitions
               WHERE audit_id=? AND source='SYNTHETIC_USER_EXPERIENCE_APDEX'
               ORDER BY created_at, rowid""",
            (audit_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            """SELECT * FROM synthetic_apdex_acquisitions
               WHERE audit_id=? AND consumed_by_navigation=1
               ORDER BY created_at, rowid""",
            (audit_id,),
        ).fetchall()

    acquisitions: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        acquisitions[_sample_key(item)].append(item)

    grouped_samples: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for sample in samples:
        grouped_samples[_sample_key(sample)].append(sample)

    result: dict[str, str] = {}
    for key, group in grouped_samples.items():
        ordered_samples = sorted(group, key=lambda item: int(item.get("run_index") or 0))
        ordered_acquisitions = acquisitions.get(key, [])
        for sample, acquisition in zip(ordered_samples, ordered_acquisitions):
            sample_id = str(sample.get("sample_id") or "")
            created_at = str(acquisition.get("created_at") or "")
            if sample_id and created_at:
                result[sample_id] = created_at
    return result


def _duration_only_apdex(samples: Sequence[Mapping[str, Any]], run: Mapping[str, Any]) -> tuple[float | None, int, int, int, int]:
    try:
        satisfied_ms = float(run.get("satisfied_threshold_seconds")) * 1000.0
        frustrated_ms = float(run.get("frustrated_threshold_seconds")) * 1000.0
    except (TypeError, ValueError):
        return None, 0, 0, 0, 0
    satisfied = tolerating = frustrated = valid = 0
    for sample in samples:
        if sample.get("classification") in (None, ""):
            continue
        raw = sample.get("kpm_value_ms") if sample.get("kpm_value_ms") is not None else sample.get("user_action_duration_ms")
        try:
            duration = float(raw)
        except (TypeError, ValueError):
            continue
        valid += 1
        if duration <= satisfied_ms:
            satisfied += 1
        elif duration <= frustrated_ms:
            tolerating += 1
        else:
            frustrated += 1
    score = (satisfied + 0.5 * tolerating) / valid if valid else None
    return score, valid, satisfied, tolerating, frustrated


def _install_apdex_projection() -> None:
    from rasai import catalog_report_analysis as analysis
    from rasai import catalog_report_page as page

    current = page._apdex_samples_html
    if getattr(current, "_rasai_canonical_apdex_projection", False):
        return

    def apdex_samples_html(database: Any, data: Any, *, experience: bool) -> str:
        table = "synthetic_ux_apdex_samples" if experience else "synthetic_apdex_samples"
        run_table = "synthetic_ux_apdex_runs" if experience else "synthetic_apdex_runs"
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        try:
            samples = analysis._audit_rows(connection, table, data.audit_id)
            run = analysis._last(connection, run_table, data.audit_id)
            timestamp_map = _acquisition_timestamp_map(connection, data.audit_id, samples, experience=experience)
        finally:
            connection.close()

        samples = sorted(samples, key=lambda item: (int(item.get("run_index") or 0), str(item.get("sample_id") or "")))
        rows: list[Sequence[Any]] = []
        modals: list[str] = []
        fallback_count = 0
        for index, sample in enumerate(samples, 1):
            modal_id = ("ux" if experience else "nav") + f"-sample-{index}"
            sample_id = str(sample.get("sample_id") or "")
            measured_at = timestamp_map.get(sample_id)
            displayed_at = measured_at or sample.get("captured_at") or "—"
            timestamp_label = "Medição em" if measured_at else "Persistida em"
            if not measured_at:
                fallback_count += 1

            if experience:
                duration = sample.get("kpm_value_ms") if sample.get("kpm_value_ms") is not None else sample.get("user_action_duration_ms")
                rows.append((sample.get("run_index", index), displayed_at, analysis._device_label(sample.get("device")), analysis._classification_label(sample.get("classification")), analysis._fmt_number(duration, "ms"), analysis._fmt_number(sample.get("lcp_ms"), "ms"), sample.get("request_failed_count") or 0, analysis._status_label(sample.get("status")), analysis._modal_button(modal_id, "Ver amostra")))
                fields = (
                    ("Amostra", sample.get("sample_id")), (timestamp_label, displayed_at), ("URL", sample.get("url")), ("URL final", sample.get("final_url")),
                    ("Classificação", analysis._classification_label(sample.get("classification"))), ("Duração da ação", analysis._fmt_number(sample.get("user_action_duration_ms"), "ms")),
                    ("Navegação", analysis._fmt_number(sample.get("navigation_duration_ms"), "ms")), ("LCP", analysis._fmt_number(sample.get("lcp_ms"), "ms")), ("CLS", sample.get("cls")),
                    ("Requisições XHR/fetch", sample.get("xhr_fetch_count")), ("Recursos dinâmicos", sample.get("dynamic_resource_count")), ("Erros JavaScript", sample.get("javascript_error_count")),
                    ("Erros de console", sample.get("console_error_count")), ("Requisições com falha", sample.get("request_failed_count")), ("Falhas em recursos próprios", sample.get("first_party_request_failed_count")),
                    ("Respostas HTTP com erro", sample.get("http_error_count")), ("Erros HTTP em recursos próprios", sample.get("first_party_http_error_count")),
                    ("Rede estabilizada", "Sim" if sample.get("network_settled") else "Não"), ("Frustração forçada por erro", "Sim" if sample.get("error_forced_frustrated") else "Não"),
                    ("Erro", sample.get("error_message") or sample.get("error_code") or "—"),
                )
                if measured_at:
                    note = "<div class='notice'>A data/hora vem do registro da aquisição física associado a esta medição. O horário de persistência em lote não é apresentado como horário da chamada.</div>"
                else:
                    note = "<div class='notice warn'>Esta amostra não possui aquisição física individual vinculável no ledger. O horário exibido é o de persistência da amostra e está rotulado como tal; o relatório não inventa o horário da chamada.</div>"
                note += "<div class='notice'>A amostra persiste contagens de falhas por requisição; quando a lista individual de URLs não foi persistida, o relatório não a reconstrói.</div>"
            else:
                duration = sample.get("duration_ms")
                rows.append((sample.get("run_index", index), displayed_at, analysis._device_label(sample.get("device")), analysis._classification_label(sample.get("classification")), analysis._fmt_number(duration, "ms"), analysis._status_label(sample.get("status")), analysis._modal_button(modal_id, "Ver amostra")))
                fields = (("Amostra", sample.get("sample_id")), (timestamp_label, displayed_at), ("URL", sample.get("url")), ("URL final", sample.get("final_url")), ("Classificação", analysis._classification_label(sample.get("classification"))), ("Duração", analysis._fmt_number(duration, "ms")), ("HTTP", sample.get("http_status")), ("Perfil técnico", sample.get("profile_id")), ("Política de cache", analysis._session_label(sample.get("cache_policy"))), ("Erro", sample.get("error_message") or sample.get("error_code") or "—"))
                diagnostics = analysis._safe_json(sample.get("browser_diagnostics"), {})
                note = "<h3>Diagnóstico de navegador</h3><div class='pre'>" + escape(json.dumps(diagnostics, ensure_ascii=False, indent=2)) + "</div>" if diagnostics else ""
                if not measured_at:
                    note += "<div class='notice'>Não existe aquisição reutilizada vinculável a esta amostra; por isso o horário permanece explicitamente identificado como persistência.</div>"
            modals.append(analysis._modal(modal_id, f"Amostra {sample.get('run_index', index)}", f"{'Apdex de experiência' if experience else 'Apdex de navegação'} · {sample.get('url') or '—'}", analysis._kv(fields) + note))

        lead = ""
        if experience and run:
            duration_score, duration_valid, duration_satisfied, duration_tolerating, duration_frustrated = _duration_only_apdex(samples, run)
            effective_valid = sum(1 for sample in samples if sample.get("classification") not in (None, ""))
            effective_satisfied = sum(1 for sample in samples if _norm(sample.get("classification")) == "SATISFIED")
            effective_tolerating = sum(1 for sample in samples if _norm(sample.get("classification")) == "TOLERATING")
            effective_score = (effective_satisfied + 0.5 * effective_tolerating) / effective_valid if effective_valid else None
            forced = sum(1 for sample in samples if bool(sample.get("error_forced_frustrated")))
            lead += "<div class='metric-grid'>"
            lead += analysis._metric("Apdex por duração", f"{duration_score:.3f}" if duration_score is not None else "—", f"{duration_valid} amostra(s); sem aplicar a política de erros")
            lead += analysis._metric("Apdex efetivo", f"{effective_score:.3f}" if effective_score is not None else "—", "classificação final persistida")
            lead += analysis._metric("Forçadas por erro", forced, f"de {effective_valid} amostra(s) válida(s)")
            lead += "</div>"
            if bool(run.get("errors_affect_apdex")):
                scope = analysis._error_scope_label(run.get("error_scope"))
                lead += f"<div class='notice warn'><strong>Política de erro do Apdex:</strong> {escape(scope)}. A leitura por duração resultou em {duration_satisfied} satisfatória(s), {duration_tolerating} tolerável(is) e {duration_frustrated} frustrada(s); após a política de erro, {forced} amostra(s) foram forçadas para Frustrada. Isso permite distinguir lentidão de falhas funcionais.</div>"
        if fallback_count:
            lead += f"<div class='notice'><strong>Proveniência temporal:</strong> {len(samples)-fallback_count} amostra(s) usam o horário da aquisição física e {fallback_count} usam somente o horário de persistência, explicitamente identificado.</div>"

        headers = ("Amostra", "Data/hora", "Dispositivo", "Classificação", "Duração", "LCP", "Falhas de requisição", "Medição", "Detalhe") if experience else ("Amostra", "Data/hora", "Dispositivo", "Classificação", "Duração", "Medição", "Detalhe")
        return lead + analysis._table(headers, rows, empty="Nenhuma amostra foi persistida para este Apdex.", sortable=bool(rows), page_size=10 if len(rows) > 10 else None) + "".join(modals)

    apdex_samples_html._rasai_canonical_apdex_projection = True  # type: ignore[attr-defined]
    apdex_samples_html._rasai_original = current  # type: ignore[attr-defined]
    page._apdex_samples_html = apdex_samples_html
    analysis._apdex_samples_html = apdex_samples_html


def _install_structured_condition_labels() -> None:
    from rasai import catalog_report_evidence as evidence
    from rasai import catalog_report_page as page

    current = evidence._structured_data_html
    if getattr(current, "_rasai_structured_conditions_pt", False):
        return

    def structured_data_html(database: Any, data: Any) -> str:
        html = current(database, data)
        for source, target in _STRUCTURED_EXPECTED_PT.items():
            pattern = re.compile(re.escape(source), flags=re.I)
            html = pattern.sub(target, html)
        return html

    structured_data_html._rasai_structured_conditions_pt = True  # type: ignore[attr-defined]
    structured_data_html._rasai_original = current  # type: ignore[attr-defined]
    evidence._structured_data_html = structured_data_html
    for module_name in ("rasai.catalog_report_analysis", "rasai.catalog_report_page"):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "_structured_data_html"):
            setattr(module, "_structured_data_html", structured_data_html)
    if hasattr(page, "_structured_data_html"):
        page._structured_data_html = structured_data_html


def install_catalog_report_adherence() -> None:
    """Install the current public-report contract after all lower renderers are composed."""
    _install_public_labels()
    _install_hero()
    _install_cat05_scope_states()
    _install_apdex_projection()
    _install_structured_condition_labels()


__all__ = [
    "_audit_hero",
    "_audit_limitations",
    "_cat05_capability_states",
    "_duration_only_apdex",
    "_human_status_value",
    "install_catalog_report_adherence",
]
