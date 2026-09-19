"""Cross-cutting consistency guards for governed execution and catalog projection.

The runtime keeps existing collection/report structures intact while enforcing that:

* collector terminal states use the canonical governance vocabulary;
* the secret-free execution plan is persisted as soon as the AUD row exists;
* in-AUD Search Intelligence records a real fulfillment attempt;
* report-catalog finality reflects the durable AUD/fulfillment state;
* report values are projections of persisted evidence rather than optimistic inference.

It is intentionally idempotent and does not add network, AI or scoring work.
"""
from __future__ import annotations

from pathlib import Path
from rasai.observability.store import observability_database_path
import json
import re
import sqlite3
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


_INSTALLED = False

_STATE_ALIASES = {
    "UNAVAILABLE": "ERROR",
    "FAILURE": "ERROR",
    "FAILED": "ERROR",
    "NO_CONTEXTS": "NO_DATA",
    "NO_PAGES": "NO_DATA",
    "COMPLETE_WITH_LIMITATIONS": "PARTIAL",
    "COMPLETED_WITH_LIMITATIONS": "PARTIAL",
}


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _safe_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _install_collection_state_normalization() -> None:
    from rasai import audit_phase_runtime as phase

    current = phase._normalized_state
    if bool(getattr(current, "_rasai_execution_consistency", False)):
        return

    def normalized(result: Mapping[str, Any] | None) -> str:
        state = str(current(result) or "UNKNOWN").strip().upper()
        return _STATE_ALIASES.get(state, state)

    normalized._rasai_execution_consistency = True
    normalized._rasai_original = current
    phase._normalized_state = normalized


def _install_configuration_persistence() -> None:
    """Persist the execution plan immediately after the durable AUD row is inserted."""
    from rasai import audit_configuration_reuse_runtime as runtime
    from rasai.audit_configuration_reuse import configuration_hash
    from rasai.persistence import AuditRepository

    current_persist = runtime.persist_current_configuration
    if not bool(getattr(current_persist, "_rasai_execution_consistency", False)):
        def persist_idempotent(workspace: str | Path, audit_id: str) -> bool:
            pending = runtime.current_configuration()
            if pending is None:
                try:
                    pending = runtime.load_subprocess_configuration_handoff()
                except ValueError:
                    raise
            if pending is None:
                return False
            database = Path(workspace)
            if database.name != "audit.db":
                database = database / "audit.db"
            if database.is_file():
                connection = sqlite3.connect(database, timeout=2.0)
                try:
                    if _table_exists(connection, "audit_execution_configurations"):
                        row = connection.execute(
                            "SELECT configuration_kind,configuration_hash FROM audit_execution_configurations WHERE audit_id=?",
                            (audit_id,),
                        ).fetchone()
                        if row is not None:
                            expected = configuration_hash(pending.configuration)
                            if str(row[0]) == pending.kind and str(row[1]) == expected:
                                return True
                finally:
                    connection.close()
            return current_persist(workspace, audit_id)

        persist_idempotent._rasai_execution_consistency = True
        persist_idempotent._rasai_original = current_persist
        runtime.persist_current_configuration = persist_idempotent

    current_add = AuditRepository.add
    if bool(getattr(current_add, "_rasai_execution_consistency", False)):
        return

    def add_with_configuration(self: Any, audit: Any) -> None:
        current_add(self, audit)
        row = self._connection.execute("PRAGMA database_list").fetchone()
        if row is None or len(row) < 3 or not str(row[2] or "").strip():
            return
        database = Path(str(row[2]))
        runtime.persist_current_configuration(database.parent, str(audit.audit_id))

    add_with_configuration._rasai_execution_consistency = True
    add_with_configuration._rasai_original = current_add
    AuditRepository.add = add_with_configuration


def _search_queries(search: Any) -> tuple[str, ...]:
    args = search._parsed_args()
    return tuple(
        dict.fromkeys(
            " ".join(str(item).split())
            for item in (getattr(args, "search_queries", ()) if args is not None else ())
            if str(item).strip()
        )
    )


def _install_search_attempt_ledger() -> None:
    """Make the pre-seal Search collector own the attempt it actually executes."""
    from rasai import search_audit_runtime as search
    from rasai.audit_fulfillment import (
        FAILED_RETRYABLE,
        LIVE_RECOLLECTION,
        SUCCESS,
        begin_attempt,
        finish_attempt,
        list_work_items,
        register_work_item,
    )

    current = search._collector
    if bool(getattr(current, "_rasai_execution_consistency", False)):
        return

    def collector(*, audit_id: str, workspace: Any, source_blocked: bool = False):
        queries = _search_queries(search)
        attempt_id: str | None = None
        if queries:
            register_work_item(
                workspace,
                audit_id=audit_id,
                component=search._COMPONENT,
                required=True,
                temporal_mode=LIVE_RECOLLECTION,
                retryable=True,
                configuration={"requested": True, "queries": list(queries)},
            )
            item = next(
                (
                    value for value in list_work_items(workspace, audit_id)
                    if value.component == search._COMPONENT and value.scope_key == "AUDIT"
                ),
                None,
            )
            if item is not None and item.status != SUCCESS:
                attempt_id = begin_attempt(
                    workspace,
                    audit_id=audit_id,
                    component=search._COMPONENT,
                    metadata={"surface": "audit-collection", "queries": len(queries)},
                )
        try:
            result = dict(current(audit_id=audit_id, workspace=workspace, source_blocked=source_blocked) or {})
        except Exception as exc:
            if attempt_id is not None:
                finish_attempt(
                    workspace,
                    attempt_id,
                    status=FAILED_RETRYABLE,
                    error_class=type(exc).__name__,
                    error_code="SEARCH_INTELLIGENCE_RUNTIME_ERROR",
                    error_message=str(exc),
                    retryable=True,
                )
            raise
        if attempt_id is not None:
            state = _STATE_ALIASES.get(
                str(result.get("collection_state") or result.get("status") or "ERROR").upper(),
                str(result.get("collection_state") or result.get("status") or "ERROR").upper(),
            )
            if state == "SUCCESS":
                finish_attempt(
                    workspace,
                    attempt_id,
                    status=SUCCESS,
                    result_ref="search-intelligence:effective",
                    retryable=False,
                    metadata={"collection_state": state},
                )
            else:
                finish_attempt(
                    workspace,
                    attempt_id,
                    status=FAILED_RETRYABLE,
                    error_class="SEARCH_PROVIDER" if state == "ERROR" else "ORCHESTRATION",
                    error_code=str(result.get("reason") or result.get("detail") or state),
                    error_message=str(result.get("detail") or result.get("reason") or state),
                    retryable=True,
                    metadata={"collection_state": state},
                )
        return result

    collector._rasai_execution_consistency = True
    collector._rasai_original = current
    search._collector = collector


def _publication_state(database: Path, audit_id: str) -> str:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        audit = connection.execute(
            "SELECT status,completion_status FROM audits WHERE audit_id=?", (audit_id,)
        ).fetchone()
        if audit is None:
            return "PRELIMINARY"
        status = str(audit["status"] or "").upper()
        completion = str(audit["completion_status"] or "").upper()
        base_final = status == "COMPLETED" and completion in {
            "COMPLETE", "COMPLETE_WITH_LIMITATIONS", "COMPLETED", "COMPLETED_WITH_LIMITATIONS"
        }
        if not base_final:
            return "PRELIMINARY"
        if not _table_exists(connection, "audit_fulfillment_contracts"):
            return "FINAL"
        row = connection.execute(
            "SELECT * FROM audit_fulfillment_contracts WHERE audit_id=? ORDER BY rowid DESC LIMIT 1",
            (audit_id,),
        ).fetchone()
        if row is None:
            return "PRELIMINARY"
        processing = str(row["processing_status"] or "").upper()
        score = str(row["score_status"] or "").upper()
        report = str(row["report_status"] or "").upper()
        eligible = bool(row["consolidation_eligible"])
        return "FINAL" if (
            processing in {"COMPLETE", "COMPLETE_WITH_LIMITATIONS", "COMPLETED", "COMPLETED_WITH_LIMITATIONS"}
            and score == "FINAL"
            and report == "FINAL"
            and eligible
        ) else "PRELIMINARY"
    finally:
        connection.close()


def _install_catalog_finality() -> None:
    from rasai import catalog_report_site as site

    current = site.materialize_catalog_report_site
    if bool(getattr(current, "_rasai_execution_consistency", False)):
        return

    def materialize(*, audit_id: str, workspace: Any) -> Path:
        path = current(audit_id=audit_id, workspace=workspace)
        manifest_path = Path(workspace.root) / site.CATALOG_REPORT_DIR / "manifest.json"
        if not manifest_path.is_file():
            return path
        desired = _publication_state(Path(workspace.database), audit_id)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if str(payload.get("freshness") or "") != desired:
            payload["freshness"] = desired
            payload["publication_state"] = desired
            manifest_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        return path

    materialize._rasai_execution_consistency = True
    materialize._rasai_original = current
    site.materialize_catalog_report_site = materialize
    # Console projection imports this callable by value in some compositions.
    for module_name in ("rasai.execution_adherence_refinement", "rasai.report_completion"):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "materialize_catalog_report_site"):
            setattr(module, "materialize_catalog_report_site", materialize)


def _plan_available(data: Any) -> bool:
    return bool(
        getattr(data, "configuration", None)
        and getattr(data, "config_hash", "")
        and getattr(data, "computed_hash", "")
        and data.config_hash == data.computed_hash
    )


def _consistent_audit_hero(data: Any, title: str, subtitle: str) -> str:
    from html import escape
    from rasai import catalog_report_adherence as adherence
    from rasai import catalog_report_presentation as p

    target = data.targets[0] if getattr(data, "targets", ()) else "—"
    audit = data.audit if isinstance(getattr(data, "audit", None), Mapping) else {}
    fulfillment = data.fulfillment if isinstance(getattr(data, "fulfillment", None), Mapping) else {}
    project = str(audit.get("project_name") or "—")
    logical_raw = fulfillment.get("processing_status") or audit.get("completion_status") or audit.get("status")
    base_raw = audit.get("completion_status") or audit.get("status")
    limitations = adherence._audit_limitations(data)
    selected_value: Any = len(getattr(data, "selected", ())) if _plan_available(data) else "Indeterminado"

    metrics = "<div class='metric-grid'>"
    metrics += p._metric("URL auditada", target)
    metrics += p._metric("Projeto", project)
    metrics += p._metric("Resultado lógico da AUD", p._status_label(logical_raw))
    metrics += p._metric("Auditoria-base", p._status_label(base_raw))
    metrics += p._metric("Catálogos selecionados", selected_value)
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


def _consistent_execution_evidence_body(database: Path, data: Any) -> str:
    from rasai import catalog_report_governance as g

    plan = _plan_available(data)
    rows = []
    for catalog in g.CATALOGS:
        status, tone, detail = g._catalog_status(database, data, catalog.id)
        selected = ("Sim" if catalog.id in data.selected else "Não") if plan else "Indeterminado"
        rows.append((catalog.id, catalog.label, selected, g._Html(g._badge(status, tone)), detail))
    integrity = "Íntegro" if data.config_hash and data.computed_hash == data.config_hash else "Plano não encontrado" if not data.config_hash else "Integridade divergente"
    work_rows = []
    modals = []
    for index, row in enumerate(data.work_items, 1):
        modal_id = f"fulfillment-{index}"
        work_status = g._technical_work_status(row.get("status"))
        work_rows.append((g._friendly_component(row.get("component")), work_status, g._attempt_count_label(row.get("attempt_count")), g._modal_button(modal_id, "Ver etapa")))
        modals.append(g._modal(modal_id, g._friendly_component(row.get("component")), "Etapa técnica persistida da execução", g._kv((("Conclusão da etapa", work_status), ("Tentativas registradas na etapa", g._attempt_count_label(row.get("attempt_count"))), ("Obrigatória", "Sim" if row.get("required") else "Não"), ("Escopo técnico", row.get("scope_key") or "—"), ("Resultado", row.get("effective_result_ref") or "—"), ("Último erro", row.get("last_error_message") or row.get("last_error_code") or "—"), ("Identificador", row.get("work_item_id") or "—")))))
    selected_count: Any = len(data.selected) if plan else "Indeterminado"
    body = g._audit_hero(data, "Evidências da execução", "O que foi solicitado, o estado funcional de cada catálogo e as etapas técnicas persistidas.")
    body += g._outline((("matrix", "Plano × execução"), ("integrity", "Plano congelado"), ("technical", "Etapas técnicas")))
    body += g._section("matrix", "Plano × execução", g._table(("Catálogo", "Contexto", "Selecionado", "Estado funcional", "Interpretação"), rows, sortable=True))
    body += g._section("integrity", "Plano congelado", f"<div class='metric-grid'>{g._metric('Integridade', integrity)}{g._metric('Catálogos selecionados', selected_count)}{g._metric('Etapas técnicas persistidas', len(data.work_items))}{g._metric('Resultado lógico', g._audit_state(data))}</div><p class='muted'>Ausência de plano é estado indeterminado; nunca é convertida em “não solicitado”.</p>")
    body += g._section("technical", "Etapas técnicas", g._table(("Etapa", "Conclusão técnica", "Tentativas", "Detalhe"), work_rows, empty="Nenhuma etapa técnica persistida.", sortable=bool(work_rows)) + "".join(modals) + "<p class='muted'>Conclusão técnica indica se a etapa executou. O estado funcional do catálogo pode permanecer parcial quando a própria metodologia considera a cobertura insuficiente, como em um grupo Apdex pequeno.</p>")
    return body


def _w3c_fix_hint(message: Any, *, css: bool = False) -> str:
    text = str(message or "").casefold()
    if css:
        if "property" in text and ("doesn't exist" in text or "does not exist" in text or "unknown" in text):
            return "Remover a propriedade inválida ou substituí-la por uma propriedade CSS válida e suportada."
        if "value" in text or "valor" in text:
            return "Corrigir o valor da propriedade conforme a gramática CSS indicada pelo validator."
        if "parse" in text or "syntax" in text or "sintax" in text:
            return "Corrigir a sintaxe da declaração indicada, revisando chaves, dois-pontos, ponto e vírgula e valor."
        return "Corrigir a declaração CSS indicada pela mensagem W3C e executar novamente a validação."
    if "duplicate id" in text or "id already defined" in text:
        return "Garantir que cada atributo id seja único no documento."
    if "attribute" in text and ("not allowed" in text or "bad value" in text or "invalid" in text):
        return "Remover ou corrigir o atributo/valor inválido no elemento indicado pela mensagem W3C."
    if "element" in text and ("not allowed" in text or "not permitted" in text):
        return "Reposicionar ou substituir o elemento para respeitar o modelo de conteúdo HTML permitido."
    if "stray end tag" in text or "end tag" in text:
        return "Corrigir o aninhamento e o fechamento das tags no trecho indicado."
    if "unclosed" in text or "not closed" in text:
        return "Fechar corretamente o elemento HTML indicado antes de continuar a estrutura."
    if "required attribute" in text or "missing" in text:
        return "Adicionar o atributo obrigatório indicado, usando um valor compatível com o elemento."
    return "Corrigir o markup indicado pela mensagem W3C e executar novamente a validação."


def _w3c_detail_modal(e: Any, item: Mapping[str, Any], *, index: int) -> tuple[Any, str]:
    key = str(item.get("metric_id") or item.get("metric_key") or "")
    details = _safe_json(item.get("details_json"), {})
    if not isinstance(details, Mapping):
        details = {}
    css = key == "w3c_css_conformance"
    modal_id = f"standards-w3c-{index}"
    errors = int(float(item.get("value") or 0)) if item.get("value") is not None else 0
    criterion = (
        "Aprovado quando o W3C CSS Validator retornar valid=true e 0 erros CSS."
        if css
        else "Aprovado quando o W3C Nu Checker retornar 0 erros HTML e 0 erros de documento."
    )
    diagnostic_rows: list[tuple[Any, ...]] = []
    if css:
        raw_rows = details.get("error_details") if isinstance(details.get("error_details"), list) else []
        for row in raw_rows:
            if not isinstance(row, Mapping):
                continue
            location = f"Linha {row.get('line')}" if row.get("line") not in (None, "") else "-"
            message = row.get("message") or row.get("type") or "Erro CSS informado pelo W3C"
            context = row.get("context") or row.get("skipped_string") or "-"
            diagnostic_rows.append((location, message, context, _w3c_fix_hint(message, css=True)))
    else:
        raw_rows = details.get("messages") if isinstance(details.get("messages"), list) else []
        for row in raw_rows:
            if not isinstance(row, Mapping) or str(row.get("type") or "") == "info":
                continue
            line = row.get("first_line") or row.get("last_line")
            column = row.get("first_column") or row.get("last_column")
            location = (
                f"Linha {line}, coluna {column}" if line not in (None, "") and column not in (None, "")
                else f"Linha {line}" if line not in (None, "")
                else "-"
            )
            message = row.get("message") or "Erro HTML informado pelo W3C"
            diagnostic_rows.append((location, message, row.get("extract") or "-", _w3c_fix_hint(message)))
    body = e._kv((
        ("Resultado", e._status_label(item.get("state") or item.get("status"))),
        ("Erros", errors),
        ("Alvo validado", item.get("target") or "-"),
        ("Fonte", item.get("source") or "-"),
        ("Critério para aprovação", criterion),
        ("Metodologia", item.get("methodology") or "-"),
    ))
    if diagnostic_rows:
        body += "<h3>Erros retornados pelo W3C</h3>" + e._table(
            ("Localização", "Mensagem", "Trecho / contexto", "O que corrigir"),
            diagnostic_rows,
            sortable=bool(diagnostic_rows),
            page_size=10 if len(diagnostic_rows) > 10 else None,
        )
    elif errors:
        body += (
            "<div class='notice warn'><strong>Detalhe não persistido nesta execução:</strong> "
            "a contagem de erros existe, mas esta AUD foi coletada antes do contrato que preserva as mensagens "
            "individuais do validator. Reexecute a validação W3C para obter linha, mensagem, trecho e orientação.</div>"
        )
    else:
        body += "<div class='notice good'>Nenhum erro W3C foi persistido para este alvo.</div>"
    body += (
        "<div class='notice'><strong>Como aprovar:</strong> corrija todos os erros listados, publique a alteração "
        "e reexecute a auditoria/validação. Warnings podem exigir revisão técnica, mas o estado FAIL é determinado "
        "pelos erros do validator conforme o contrato acima.</div>"
    )
    return e._modal_button(modal_id, "Ver erros e correção"), e._modal(
        modal_id,
        "Conformidade CSS W3C" if css else "Conformidade HTML W3C",
        str(item.get("target") or "Validação W3C"),
        body,
    )


def _consistent_standards_summary(database: Path, data: Any) -> str:
    from rasai import catalog_report_evidence as e

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        metrics = e._audit_rows(connection, "standards_metric_observations", data.audit_id)
        services = e._audit_rows(connection, "standards_service_runs", data.audit_id)
    finally:
        connection.close()
    wanted = {
        "w3c_html_conformance": "Conformidade HTML W3C",
        "w3c_css_conformance": "Conformidade CSS W3C",
        "web_platform_widely_available_count": "Recursos amplamente disponíveis",
        "web_platform_newly_available_count": "Recursos recentemente disponíveis",
        "web_platform_limited_availability_count": "Recursos com disponibilidade limitada",
    }
    rows: list[Sequence[Any]] = []
    modals: list[str] = []
    for index, item in enumerate(metrics, 1):
        key = str(item.get("metric_id") or item.get("metric_key") or "")
        if key not in wanted:
            continue
        raw_value = item.get("value") if "value" in item else item.get("value_num")
        unit = str(item.get("unit") or "")
        if raw_value is None:
            value: Any = "-"
        elif unit == "error_count":
            value = f"{int(float(raw_value))} erro(s)"
        else:
            number = float(raw_value)
            value = int(number) if number.is_integer() else round(number, 3)
        detail: Any = "-"
        if key in {"w3c_html_conformance", "w3c_css_conformance"}:
            detail, modal = _w3c_detail_modal(e, item, index=index)
            detail = e._Html(
                str(detail)
                + " · <a href='cat-09.html#w3c-remediation'>Ver remediações no CAT-09</a>"
            )
            modals.append(modal)
        rows.append((wanted[key], value, e._status_label(item.get("state") or item.get("status")), detail))
    for item in services:
        service_id = str(item.get("service_id") or "")
        if service_id not in {"w3c-validator", "mdn-observatory", "w3c-css-validator", "web-platform-baseline"}:
            continue
        details = _safe_json(item.get("details_json"), {})
        result: Any = f"{item.get('targets_succeeded', 0)}/{item.get('targets_attempted', 0)} alvo(s)"
        if service_id == "mdn-observatory" and isinstance(details, Mapping):
            score = details.get("score") or details.get("observatory_score")
            grade = details.get("grade") or details.get("observatory_grade")
            if score is not None or grade:
                result = " · ".join(str(value) for value in (score, grade) if value not in (None, ""))
        rows.append((e._friendly_service(service_id) + " · execução", result, e._status_label(item.get("state")), "-"))
    return e._table(
        ("Verificação", "Resultado", "Estado", "Detalhe"),
        rows,
        empty="Nenhuma métrica de padrões web foi persistida.",
        sortable=bool(rows),
    ) + "".join(modals)


def _consistent_catalog_sources(database: Path, data: Any, catalog_id: str):
    from rasai import catalog_report_catalog_state as state

    original = getattr(_consistent_catalog_sources, "_base", None)
    if original is None:
        return []
    rows = list(original(database, data, catalog_id))
    if catalog_id != "CAT-03":
        return rows
    names = {str(item[0]) for item in rows}
    connection = sqlite3.connect(database)
    try:
        if _table_exists(connection, "page_snapshots") and _table_exists(connection, "pages"):
            count = connection.execute(
                """SELECT COUNT(*) FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
                   WHERE p.audit_id=? AND ps.main_content_ref IS NOT NULL AND trim(ps.main_content_ref)<>''""",
                (data.audit_id,),
            ).fetchone()[0]
            if count and "page_snapshots (main_content)" not in names:
                rows.append(("page_snapshots (main_content)", "Conteúdo principal renderizado", int(count)))
        if _table_exists(connection, "rule_executions"):
            rule_ids = ("BR-GEO-019", "BR-GEO-020", "BR-GEO-025", "BR-GEO-026", "BR-GEO-027")
            placeholders = ",".join("?" for _ in rule_ids)
            count = connection.execute(
                f"SELECT COUNT(*) FROM rule_executions WHERE audit_id=? AND rule_id IN ({placeholders})",
                (data.audit_id, *rule_ids),
            ).fetchone()[0]
            if count and "rule_executions (content-semantic)" not in names:
                rows.append(("rule_executions (content-semantic)", "Validações determinísticas de conteúdo e semântica", int(count)))
    finally:
        connection.close()
    return rows


def _format_history_metric(metric: str, value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value or "—")
    key = metric.casefold()
    if "paint" in key or "inp" in key or "lcp" in key or "ttfb" in key:
        return f"{number:,.0f} ms".replace(",", " ")
    if "shift" in key or "cls" in key:
        return f"{number:.3f}".rstrip("0").rstrip(".")
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _consistent_web_metric_rows(database: Path, audit_id: str):
    original = getattr(_consistent_web_metric_rows, "_base", None)
    rows = list(original(database, audit_id)) if callable(original) else []
    labels = {str(row[0]) for row in rows if row}
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if _table_exists(connection, "standards_metric_observations"):
            for raw in connection.execute(
                """SELECT metric_id,label,state,value,unit FROM standards_metric_observations
                   WHERE audit_id=? AND source='OPEN-WEB-METRICS-001' ORDER BY metric_id,observed_at""",
                (audit_id,),
            ).fetchall():
                item = dict(raw)
                if item.get("value") is None:
                    continue
                label = "Navegador · " + str(item.get("label") or item.get("metric_id") or "Métrica")
                if label in labels:
                    continue
                unit = str(item.get("unit") or "")
                value = _format_history_metric(str(item.get("metric_id") or ""), item.get("value")) if unit == "ms" else str(item.get("value"))
                rows.append((label, value, "Medição da sessão do navegador"))
                labels.add(label)
    finally:
        connection.close()

    obs = observability_database_path(database.parent)
    if obs.is_file():
        connection = sqlite3.connect(obs)
        connection.row_factory = sqlite3.Row
        try:
            if _table_exists(connection, "crux_history"):
                all_rows = [dict(row) for row in connection.execute("SELECT * FROM crux_history ORDER BY period_end,record_id").fetchall()]
                if all_rows:
                    rows.append(("CrUX History · pontos persistidos", len(all_rows), "Série histórica de campo"))
                    latest: dict[tuple[str, str], dict[str, Any]] = {}
                    for item in all_rows:
                        latest[(str(item.get("metric") or ""), str(item.get("form_factor") or ""))] = item
                    for (metric, form_factor), item in sorted(latest.items()):
                        if item.get("p75") is None:
                            continue
                        label = f"CrUX History · {metric.replace('_', ' ').title()}"
                        if form_factor:
                            label += f" · {form_factor.replace('_', ' ').title()}"
                        rows.append((label, _format_history_metric(metric, item.get("p75")), "p75 histórico persistido"))
        finally:
            connection.close()
    return rows


def _replace_metric_value(html: str, label: str, value: str) -> str:
    pattern = re.compile(
        r"(<div class='metric'><small>" + re.escape(label) + r"</small><strong>)(.*?)(</strong>(?:<small>.*?</small>)?</div>)",
        flags=re.DOTALL,
    )
    return pattern.sub(lambda match: match.group(1) + value + match.group(3), html, count=1)


def _install_ai_cost_projection() -> None:
    from rasai import catalog_report_integrations as integrations

    current = integrations._ai_integrations_body
    if bool(getattr(current, "_rasai_execution_consistency", False)):
        return

    def body(database: Any, data: Any) -> str:
        html = current(database, data)
        forecast = integrations._cost_forecast(database, data.audit_id)
        if not forecast:
            return html
        if forecast.get("deviation_amount") is None:
            html = _replace_metric_value(html, "Desvio monetário", "—")
        if forecast.get("deviation_percent") is None:
            html = _replace_metric_value(html, "Desvio percentual", "—")
        if forecast.get("deviation_amount") is None or forecast.get("deviation_percent") is None:
            html = re.sub(
                r"<div class='notice (?:good|bad)'><strong>Conciliação:</strong>.*?</div>",
                "<div class='notice'><strong>Conciliação:</strong> o desvio não foi materializado pela execução persistida; esta projeção não o recalcula.</div>",
                html,
                count=1,
                flags=re.DOTALL,
            )
        return html

    body._rasai_execution_consistency = True
    body._rasai_original = current
    integrations._ai_integrations_body = body
    site = sys.modules.get("rasai.catalog_report_site")
    if site is not None:
        site._ai_integrations_body = body


def _apply_report_patches() -> None:
    from rasai import catalog_report_adherence as adherence
    from rasai import catalog_report_catalog_state as state
    from rasai import catalog_report_evidence as evidence
    from rasai import catalog_report_governance as governance
    from rasai import catalog_report_metrics as metrics
    from rasai import catalog_report_page as page
    from rasai import catalog_report_presentation as presentation

    presentation._audit_hero = _consistent_audit_hero
    adherence._audit_hero = _consistent_audit_hero
    governance._audit_hero = _consistent_audit_hero
    page._audit_hero = _consistent_audit_hero

    governance._execution_evidence_body = _consistent_execution_evidence_body
    evidence._standards_summary = _consistent_standards_summary
    page._standards_summary = _consistent_standards_summary

    if not hasattr(_consistent_catalog_sources, "_base"):
        _consistent_catalog_sources._base = state._catalog_sources
    state._catalog_sources = _consistent_catalog_sources
    page._catalog_sources = _consistent_catalog_sources

    current_web = metrics._web_metric_rows
    if current_web is not _consistent_web_metric_rows:
        _consistent_web_metric_rows._base = current_web
    metrics._web_metric_rows = _consistent_web_metric_rows

    site = sys.modules.get("rasai.catalog_report_site")
    if site is not None:
        if hasattr(site, "_audit_hero"):
            site._audit_hero = _consistent_audit_hero
        if hasattr(site, "_execution_evidence_body"):
            site._execution_evidence_body = _consistent_execution_evidence_body
        if hasattr(site, "_standards_summary"):
            site._standards_summary = _consistent_standards_summary
        if hasattr(site, "_catalog_sources"):
            site._catalog_sources = _consistent_catalog_sources
    _install_ai_cost_projection()


def _wrap_report_installers() -> None:
    from rasai import catalog_report_adherence as adherence
    from rasai import catalog_report_final_refinements as refinements
    from rasai import catalog_report_search_trust as search_trust

    for module, name in (
        (refinements, "install_catalog_report_refinements"),
        (adherence, "install_catalog_report_adherence"),
        (search_trust, "install"),
    ):
        current = getattr(module, name)
        if bool(getattr(current, "_rasai_execution_consistency", False)):
            continue
        def wrapped(*args: Any, __current=current, **kwargs: Any):
            result = __current(*args, **kwargs)
            _apply_report_patches()
            return result
        wrapped._rasai_execution_consistency = True
        wrapped._rasai_original = current
        setattr(module, name, wrapped)
    _apply_report_patches()


def _host(value: Any) -> str:
    try:
        return str(urlsplit(str(value or "")).hostname or "").casefold().removeprefix("www.")
    except Exception:
        return ""


def _install_request_remediation_filter() -> None:
    from rasai import request_remediation_intelligence as request

    current = request.collect_request_error_evidence
    if bool(getattr(current, "_rasai_execution_consistency", False)):
        return

    def collect(database: Any, audit_id: str, *, sources: set[str] | None = None):
        events, samples = current(database, audit_id, sources=sources)
        connection = sqlite3.connect(database)
        try:
            row = connection.execute(
                "SELECT normalized_url FROM pages WHERE audit_id=? ORDER BY rowid LIMIT 1", (audit_id,)
            ).fetchone() if _table_exists(connection, "pages") else None
            target_host = _host(row[0]) if row else ""
        finally:
            connection.close()
        filtered = []
        for raw in events:
            item = dict(raw)
            if str(item.get("error_type") or "").upper() == "SHARED_ACQUISITION":
                continue
            if str(item.get("family") or "").upper() == "CORS":
                message = str(item.get("message") or "")
                candidates = re.findall(r"https?://[^\s<>'\"\])]+", message)
                resource = next((value.rstrip(".,;:") for value in candidates if _host(value) and _host(value) != target_host), None)
                if resource:
                    item["source_url"] = resource
                    item["normalized_url"] = request._normalized_url(resource)
                    item["first_party"] = (_host(resource) == target_host) if target_host else None
            filtered.append(item)
        return filtered, samples

    collect._rasai_execution_consistency = True
    collect._rasai_original = current
    request.collect_request_error_evidence = collect


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_collection_state_normalization()
    _install_configuration_persistence()
    _install_search_attempt_ledger()
    _install_catalog_finality()
    _wrap_report_installers()
    _install_request_remediation_filter()
    _INSTALLED = True


__all__ = ["install"]
