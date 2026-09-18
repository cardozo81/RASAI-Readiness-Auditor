"""Trust-oriented CAT-05 projection over persisted Search/AI evidence.

This module does not collect data. It projects the effective state of SERP, GSC,
Clarity, Common Crawl, AI Overview and competitive intelligence using SOURCE-STATE-001
and persisted evidence/artifacts only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from rasai.configuration_value_labels import configuration_value_report
from rasai.source_state import SourceState

_COMMON_CRAWL_SOURCE = "COMMON_CRAWL_CDX_HISTORY"
_CLARITY_SOURCE = "MICROSOFT_CLARITY_LIVE_INSIGHTS"
_GSC_PREFIX = "GOOGLE_SEARCH_CONSOLE_"


def _safe_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list, tuple, int, float, bool)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _recursive_config(value: Any, wanted: str) -> Any:
    target = wanted.casefold()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).casefold() == target:
                return child
        for child in value.values():
            result = _recursive_config(child, wanted)
            if result is not None:
                return result
    elif isinstance(value, (list, tuple)):
        for child in value:
            result = _recursive_config(child, wanted)
            if result is not None:
                return result
    return None


def _boolish(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    raw = str(value).strip().casefold()
    if raw in {"1", "true", "yes", "on", "sim", "required", "auto", "if-compatible"}:
        return True
    if raw in {"0", "false", "no", "off", "nao", "não", "disabled"}:
        return False
    return None


def _dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age(captured_at: Any, reused_at: Any) -> str:
    captured = _dt(captured_at)
    reused = _dt(reused_at) or datetime.now(timezone.utc)
    if captured is None:
        return "-"
    seconds = max(0, int((reused - captured).total_seconds()))
    days, remainder = divmod(seconds, 86400)
    hours = remainder // 3600
    if days:
        return f"{days}d {hours}h"
    minutes = (remainder % 3600) // 60
    return f"{hours}h {minutes}min"


def _work_item(data: Any, component: str) -> Mapping[str, Any] | None:
    for item in getattr(data, "work_items", ()):
        if str(item.get("component") or "").upper() == component.upper():
            return item
    return None


def _audit_service_runs(database: Path, audit_id: str, needle: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "standards_service_runs"):
            return []
        cols = _columns(connection, "standards_service_runs")
        where = "audit_id=? AND lower(service_id) LIKE ?" if "audit_id" in cols else "lower(service_id) LIKE ?"
        params: tuple[Any, ...] = (audit_id, f"%{needle.casefold()}%") if "audit_id" in cols else (f"%{needle.casefold()}%",)
        return [dict(row) for row in connection.execute(f"SELECT * FROM standards_service_runs WHERE {where}", params)]
    finally:
        connection.close()


def _observability(database: Path) -> tuple[list[dict[str, Any]], sqlite3.Connection | None]:
    path = database.parent / "observability.db"
    if not path.is_file():
        return [], None
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    if not _table_exists(connection, "datasets"):
        connection.close()
        return [], None
    datasets = [dict(row) for row in connection.execute("SELECT * FROM datasets ORDER BY collected_at,dataset_id")]
    return datasets, connection


def _dataset_rows(connection: sqlite3.Connection | None, table: str, dataset_ids: Sequence[str]) -> int:
    if connection is None or not dataset_ids or not _table_exists(connection, table):
        return 0
    if "dataset_id" not in _columns(connection, table):
        return 0
    placeholders = ",".join("?" for _ in dataset_ids)
    row = connection.execute(
        f"SELECT COUNT(*) FROM {table} WHERE dataset_id IN ({placeholders})", tuple(dataset_ids)
    ).fetchone()
    return int(row[0]) if row else 0


def _dataset_errors(rows: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for row in rows:
        metadata = _safe_json(row.get("metadata"), {})
        if isinstance(metadata, Mapping):
            try:
                total += int(metadata.get("errors") or 0)
            except (TypeError, ValueError):
                pass
    return total


def _dataset_artifact(rows: Sequence[Mapping[str, Any]]) -> str | None:
    refs = [str(row.get("artifact_path") or "").strip() for row in rows if row.get("artifact_path")]
    return refs[-1] if refs else None


def _serp_rows(database: Path, audit_id: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "serp_observations"):
            return [], {}
        columns = _columns(connection, "serp_observations")
        if "audit_id" not in columns:
            # Never mix observations from different AUDs when a legacy/reduced schema
            # cannot prove audit ownership.
            return [], {}
        order_columns = [name for name in ("collected_at", "observation_id") if name in columns]
        order_by = ",".join(order_columns) if order_columns else "rowid"
        rows = [dict(row) for row in connection.execute(
            f"SELECT * FROM serp_observations WHERE audit_id=? ORDER BY {order_by}", (audit_id,)
        )]
        provenance: dict[str, dict[str, Any]] = {}
        if _table_exists(connection, "serp_evidence_provenance"):
            provenance_columns = _columns(connection, "serp_evidence_provenance")
            if {"audit_id", "observation_id"}.issubset(provenance_columns):
                provenance = {
                    str(row["observation_id"]): dict(row)
                    for row in connection.execute(
                        "SELECT * FROM serp_evidence_provenance WHERE audit_id=?", (audit_id,)
                    )
                }
        return rows, provenance
    finally:
        connection.close()


def _source_states(database: Path, data: Any) -> tuple[SourceState, ...]:
    serp, provenance = _serp_rows(database, data.audit_id)
    search_work = _work_item(data, "SEARCH_INTELLIGENCE")
    serp_requested = bool(search_work or serp or _recursive_config(data.configuration, "search_queries"))
    serp_errors = sum(bool(row.get("error_code") or row.get("error_message")) for row in serp)
    serp_results = sum(int(row.get("result_count") or 0) for row in serp)
    modes = {str(provenance.get(str(row.get("observation_id")), {}).get("temporal_mode") or "").strip() for row in serp}
    modes.discard("")
    freshness = next(iter(modes)) if len(modes) == 1 else "MIXED" if modes else "NOT_APPLICABLE"
    reused_rows = [p for p in provenance.values() if str(p.get("temporal_mode") or "") == "REUSED_EVIDENCE"]
    captured_values = [str((provenance.get(str(row.get("observation_id"))) or {}).get("captured_at") or row.get("collected_at") or "") for row in serp]
    source_audits = {str(row.get("source_audit_id") or "") for row in reused_rows if row.get("source_audit_id")}
    serp_status = "SUCCESS" if serp and not serp_errors else "PARTIAL" if serp else "REQUESTED_NOT_EXECUTED" if serp_requested else "NOT_REQUESTED"
    serp_state = SourceState(
        source_id="SERP",
        capability_available=True,
        configured=bool(_recursive_config(data.configuration, "RASAI_SERP_PROVIDER") or serp),
        requested=serp_requested,
        enabled=serp_requested and str(_recursive_config(data.configuration, "RASAI_SERP_MODE") or "").casefold() != "disabled",
        executed=bool(serp),
        execution_status=serp_status,
        data_available=serp_results > 0,
        data_status="AVAILABLE" if serp_results > 0 else "ERROR" if serp_errors else "NO_DATA",
        freshness_mode=freshness,
        captured_at=max(captured_values, default=None) or None,
        source_audit_id=next(iter(source_audits)) if len(source_audits) == 1 else "MULTIPLE" if source_audits else data.audit_id if serp else None,
        reused=bool(reused_rows),
        error_count=serp_errors,
        result_count=serp_results,
        artifact_reference=str(serp[-1].get("raw_evidence_ref") or "") or None if serp else None,
        detail="Search Intelligence solicitado na AUD" if serp_requested else "Search Intelligence não solicitado na AUD",
    ).validate()

    datasets, obs = _observability(database)
    try:
        gsc_sets = [row for row in datasets if str(row.get("source_type") or "").startswith(_GSC_PREFIX)]
        clarity_sets = [row for row in datasets if str(row.get("source_type") or "") == _CLARITY_SOURCE]
        cc_sets = [row for row in datasets if str(row.get("source_type") or "") == _COMMON_CRAWL_SOURCE]
        gsc_runs = _audit_service_runs(database, data.audit_id, "google-search-console")
        gsc_site = _recursive_config(data.configuration, "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL")
        gsc_enabled_raw = _recursive_config(data.configuration, "RASAI_GSC_ENABLED")
        gsc_requested = bool(gsc_sets or gsc_runs or _boolish(gsc_enabled_raw) is True)
        gsc_executed = bool(gsc_sets or gsc_runs)
        gsc_errors = sum(str(row.get("state") or row.get("status") or "").upper() in {"ERROR", "FAILED", "UNAVAILABLE"} for row in gsc_runs)
        gsc_results = sum(_dataset_rows(obs, table, [str(row["dataset_id"]) for row in gsc_sets]) for table in ("search_performance", "index_observations"))
        gsc_state = SourceState(
            source_id="GOOGLE_SEARCH_CONSOLE",
            capability_available=True,
            configured=bool(gsc_site or gsc_sets),
            requested=gsc_requested,
            enabled=gsc_requested and _boolish(gsc_enabled_raw) is not False,
            executed=gsc_executed,
            execution_status="SUCCESS" if gsc_executed and not gsc_errors else "PARTIAL" if gsc_executed else "NOT_REQUESTED" if not gsc_requested else "REQUESTED_NOT_EXECUTED",
            data_available=bool(gsc_sets),
            data_status="AVAILABLE" if gsc_sets else "NO_DATA",
            freshness_mode="OBSERVED_EXTERNAL_DATA" if gsc_sets else "NOT_APPLICABLE",
            captured_at=max((str(row.get("collected_at") or "") for row in gsc_sets), default=None) or None,
            source_audit_id=data.audit_id if gsc_executed else None,
            error_count=gsc_errors,
            result_count=gsc_results or len(gsc_sets),
            artifact_reference=_dataset_artifact(gsc_sets),
            detail=("GSC configurado, mas não solicitado nesta AUD" if bool(gsc_site) and not gsc_requested else "Google Search Console"),
        ).validate()

        clarity_enabled = _boolish(_recursive_config(data.configuration, "RASAI_CLARITY_ENABLED"))
        clarity_requested = bool(clarity_sets or clarity_enabled is True)
        clarity_ids = [str(row["dataset_id"]) for row in clarity_sets]
        clarity_results = _dataset_rows(obs, "behavioral_observations", clarity_ids)
        clarity_state = SourceState(
            source_id="MICROSOFT_CLARITY",
            capability_available=True,
            configured=bool(clarity_sets or clarity_enabled is True),
            requested=clarity_requested,
            enabled=clarity_requested and clarity_enabled is not False,
            executed=bool(clarity_sets),
            execution_status="SUCCESS" if clarity_sets else "NOT_REQUESTED" if not clarity_requested else "REQUESTED_NOT_EXECUTED",
            data_available=clarity_results > 0,
            data_status="AVAILABLE" if clarity_results > 0 else "NO_DATA",
            freshness_mode="OBSERVED_EXTERNAL_DATA" if clarity_sets else "NOT_APPLICABLE",
            captured_at=max((str(row.get("collected_at") or "") for row in clarity_sets), default=None) or None,
            source_audit_id=data.audit_id if clarity_sets else None,
            result_count=clarity_results,
            artifact_reference=_dataset_artifact(clarity_sets),
            detail="Microsoft Clarity",
        ).validate()

        cc_enabled = _boolish(_recursive_config(data.configuration, "RASAI_COMMON_CRAWL_ENABLED"))
        cc_requested = bool(cc_sets or cc_enabled is True)
        cc_ids = [str(row["dataset_id"]) for row in cc_sets]
        cc_results = _dataset_rows(obs, "web_archive_observations", cc_ids)
        cc_errors = _dataset_errors(cc_sets)
        cc_state = SourceState(
            source_id="COMMON_CRAWL",
            capability_available=True,
            configured=True,
            requested=cc_requested,
            enabled=cc_requested and cc_enabled is not False,
            executed=bool(cc_sets),
            execution_status="SUCCESS" if cc_sets and not cc_errors else "PARTIAL" if cc_sets else "NOT_REQUESTED" if not cc_requested else "REQUESTED_NOT_EXECUTED",
            data_available=cc_results > 0,
            data_status="AVAILABLE" if cc_results > 0 else "ERROR" if cc_errors else "NO_DATA",
            freshness_mode="HISTORICAL_WEB_ARCHIVE" if cc_sets else "NOT_APPLICABLE",
            captured_at=max((str(row.get("collected_at") or "") for row in cc_sets), default=None) or None,
            source_audit_id=data.audit_id if cc_sets else None,
            error_count=cc_errors,
            result_count=cc_results,
            artifact_reference=_dataset_artifact(cc_sets),
            detail="Common Crawl é histórico; não representa indexação atual em Google/Bing",
        ).validate()
    finally:
        if obs is not None:
            obs.close()
    return serp_state, gsc_state, clarity_state, cc_state


def _state_label(state: SourceState) -> str:
    if not state.requested:
        return "Desabilitado para esta AUD" if state.configured else "Não solicitado"
    if not state.executed:
        return "Solicitado, não executado"
    if state.error_count and state.result_count == 0:
        return "Executado com erro e sem dados"
    if state.error_count:
        return "Executado parcialmente"
    return "Executado com dados" if state.data_available else "Executado sem dados"


def _scope_html(database: Path, data: Any) -> str:
    from rasai import catalog_report_page as page
    rows=[]
    for state in _source_states(database, data):
        rows.append((
            state.source_id.replace("_", " ").title(),
            "Sim" if state.configured else "Não",
            "Sim" if state.requested else "Não",
            "Sim" if state.enabled else "Não",
            "Sim" if state.executed else "Não",
            "Sim" if state.data_available else "Não",
            _state_label(state),
        ))
    return page._section(
        "scope",
        "Escopo solicitado",
        page._table(("Capacidade / fonte","Configurado","Solicitado","Habilitado","Executado","Dados","Estado"), rows)
        + "<p class='muted'>Configuração, solicitação, execução e disponibilidade de dados são estados independentes. Uma fonte configurada não é apresentada como solicitada quando não participou desta AUD.</p>",
    )


def _safe_artifact(database: Path, reference: Any) -> Path | None:
    text = str(reference or "").strip().replace("\\", "/")
    if not text:
        return None
    candidate = (database.parent / text).resolve()
    try:
        candidate.relative_to(database.parent.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _raw_serp_artifact(database: Path, observation: Mapping[str, Any]) -> Any:
    path = _safe_artifact(database, observation.get("raw_evidence_ref"))
    if path is None or path.suffix.casefold() != ".json":
        return None
    try:
        if path.stat().st_size > 8 * 1024 * 1024:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _overview_values(payload: Any) -> list[Any]:
    found=[]
    def visit(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                normalized=str(key).casefold().replace("-", "_")
                if normalized in {"ai_overview", "ai_overview_result", "ai_overview_results"} and value not in (None, "", [], {}):
                    found.append(value)
                visit(value)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(payload)
    return found


def _urls(value: Any) -> list[str]:
    result=[]
    def visit(node: Any) -> None:
        if isinstance(node, Mapping):
            for child in node.values(): visit(child)
        elif isinstance(node, list):
            for child in node: visit(child)
        elif isinstance(node, str):
            for raw in re.findall(r"https?://[^\s<>'\"]+", node):
                url=raw.rstrip(".,);]")
                if url not in result: result.append(url)
    visit(value)
    return result[:30]


def _overview_references(values: Sequence[Any]) -> list[dict[str, Any]]:
    """Return only provider-declared AI Overview references/sources, excluding assets."""
    rows: list[dict[str, Any]] = []
    for overview in values:
        if not isinstance(overview, Mapping):
            continue
        candidates = overview.get("references")
        if not isinstance(candidates, list):
            candidates = overview.get("sources")
        if not isinstance(candidates, list):
            continue
        for position, raw in enumerate(candidates, 1):
            if isinstance(raw, Mapping):
                link = raw.get("link") or raw.get("url") or raw.get("href")
                if not link:
                    continue
                rows.append({
                    "index": raw.get("index") if raw.get("index") is not None else position - 1,
                    "source": raw.get("source") or raw.get("title") or "-",
                    "title": raw.get("title") or "-",
                    "link": str(link),
                })
            elif isinstance(raw, str) and raw.startswith(("http://", "https://")):
                rows.append({"index": position - 1, "source": "-", "title": "-", "link": raw})
    return rows


def _artifact_json(database: Path, reference: Any) -> Mapping[str, Any]:
    path = _safe_artifact(database, reference)
    if path is None or path.suffix.casefold() != ".json":
        return {}
    try:
        if path.stat().st_size > 8 * 1024 * 1024:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, Mapping) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _common_crawl_error_rows(database: Path, dataset: Mapping[str, Any]) -> list[tuple[Any, ...]]:
    payload = _artifact_json(database, dataset.get("artifact_path"))
    raw_details = payload.get("error_details") if isinstance(payload.get("error_details"), list) else []
    rows: list[tuple[Any, ...]] = []
    for raw in raw_details:
        if not isinstance(raw, Mapping):
            continue
        rows.append((
            raw.get("collection") or "-",
            raw.get("target_url") or "-",
            raw.get("error_type") or "Erro externo",
            raw.get("message") or "Mensagem não informada pelo provider",
            raw.get("endpoint") or "-",
        ))
    if rows:
        return rows
    legacy = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    for raw in legacy:
        text = str(raw or "")
        if not text:
            continue
        collection = "-"
        target = "-"
        error_type = text
        if ":" in text:
            collection, rest = text.split(":", 1)
            if ":" in rest:
                target, error_type = rest.rsplit(":", 1)
        rows.append((collection or "-", target or "-", error_type or "Erro externo", "Detalhe não persistido nesta execução", "-"))
    return rows


def _common_crawl_no_capture(error_rows: Sequence[Sequence[Any]]) -> bool:
    for row in error_rows:
        message = str(row[3] if len(row) > 3 else "").casefold()
        if "404" in message and "no captures found" in message:
            return True
    return False


def _overview_text(value: Any) -> str:
    strings=[]
    def visit(node: Any, key: str="") -> None:
        if isinstance(node, Mapping):
            for k, child in node.items():
                if str(k).casefold() in {"text", "summary", "answer", "snippet", "content", "title"}:
                    visit(child, str(k))
        elif isinstance(node, list):
            for child in node: visit(child, key)
        elif isinstance(node, str) and node.strip() and not node.startswith("http"):
            text=re.sub(r"\s+", " ", node.strip())
            if text not in strings: strings.append(text)
    visit(value)
    joined=" · ".join(strings)
    return joined[:1600] + ("…" if len(joined)>1600 else "") if joined else "Conteúdo estruturado disponível no artefato bruto; sem campo textual reconhecido."


def _target_hosts(data: Any) -> set[str]:
    hosts=set()
    for target in getattr(data, "targets", ()):
        try:
            host=str(urlsplit(str(target)).hostname or "").casefold().removeprefix("www.")
        except Exception:
            host=""
        if host: hosts.add(host)
    return hosts


def _serp_html(database: Path, data: Any) -> str:
    from rasai import catalog_report_page as page
    observations, provenance = _serp_rows(database, data.audit_id)
    connection=sqlite3.connect(database); connection.row_factory=sqlite3.Row
    rows=[]; modals=[]; overview_rows=[]; overview_modals=[]
    try:
        for index, obs in enumerate(observations, 1):
            oid=str(obs.get("observation_id") or "")
            results=[]
            if oid and _table_exists(connection, "serp_results"):
                results=[dict(row) for row in connection.execute("SELECT * FROM serp_results WHERE observation_id=? ORDER BY position",(oid,))]
            prov=provenance.get(oid,{})
            mode=str(prov.get("temporal_mode") or "LEGACY")
            captured=prov.get("captured_at") or obs.get("collected_at")
            reused=mode=="REUSED_EVIDENCE"
            modal_id=f"cat05-serp-{index}"
            rows.append((obs.get("query") or "-",obs.get("engine") or "-",obs.get("country") or obs.get("region") or "-",obs.get("language") or "-",page._device_label(obs.get("device")),obs.get("requested_depth") or "-",len(results),obs.get("provider") or "-",mode,captured or "-",page._modal_button(modal_id,"Ver proveniência")))
            body=page._kv((("Consulta",obs.get("query")),("Engine",obs.get("engine") or "-"),("Provedor",obs.get("provider")),("Modo de dados",obs.get("data_mode")),("Estado da observação",page._status_label(obs.get("observation_status"))),("Capturado em",captured),("Atualidade dos dados",page._temporal_mode_label(mode)),("Reutilizada","Sim" if reused else "Não"),("AUD de origem",prov.get("source_audit_id") or data.audit_id),("Observação de origem",prov.get("source_observation_id") or oid),("Idade no reuso",_age(captured,prov.get("reused_at")) if reused else "Não aplicável"),("Motivo do reuso",prov.get("reuse_reason") or "Não aplicável"),("Artefato bruto",obs.get("raw_evidence_ref") or "-"),("SHA-256",obs.get("raw_evidence_sha256") or "-"),("ID da requisição",obs.get("provider_request_id") or "-")))
            result_rows=[(r.get("position"),r.get("domain"),r.get("url"),r.get("result_type")) for r in results]
            body+="<h3>Resultados persistidos</h3>"+page._table(("Posição","Domínio","URL","Tipo"),result_rows,empty="Nenhum resultado individual persistido.",sortable=bool(result_rows),page_size=10 if len(result_rows)>10 else None)
            modals.append(page._modal(modal_id,"SERP · proveniência",str(obs.get("query") or "Consulta"),body))

            raw=_raw_serp_artifact(database,obs)
            overview=_overview_values(raw)
            overview_id=f"cat05-aio-{index}"
            target_hosts=_target_hosts(data)
            references=_overview_references(overview)
            reference_urls=[str(item.get("link") or "") for item in references if item.get("link")]
            present_hosts={str(urlsplit(url).hostname or "").casefold().removeprefix("www.") for url in reference_urls}
            brand_present=bool(target_hosts & present_hosts)
            detected=bool(overview)
            overview_rows.append((obs.get("query") or "-","Sim" if detected else "Não","Sim" if brand_present else "Não" if detected else "Não determinável",len(references),captured or "-",page._modal_button(overview_id,"Ver AI Overview")))
            overview_body=page._kv((("Detectado","Sim" if detected else "Não"),("Site auditado entre as referências","Sim" if brand_present else "Não" if detected else "Não determinável"),("Provedor",obs.get("provider") or "-"),("Capturado em",captured or "-"),("Artefato",obs.get("raw_evidence_ref") or "-"),("Referências declaradas pelo provider",len(references))))
            if overview:
                overview_body+="<h3>Conteúdo / resumo persistido</h3><div class='pre'>"+escape(_overview_text(overview))+"</div>"
                reference_rows=[(item.get("index"),item.get("source"),item.get("title"),item.get("link")) for item in references]
                overview_body+="<h3>Referências do AI Overview</h3>"+page._table(("Índice","Fonte","Título","URL"),reference_rows,empty="O provider retornou AI Overview sem lista estruturada de referências.")
                overview_body+="<p class='muted'>A contagem considera somente itens declarados em <code>references</code>/<code>sources</code>. Favicons, thumbnails e outros assets auxiliares não são contabilizados como fontes.</p>"
            else:
                overview_body+="<div class='notice'>Nenhum campo <code>ai_overview</code> foi encontrado no artefato SERP persistido desta observação. O relatório não infere que a feature estava ausente quando o provider não fornece esse campo.</div>"
            overview_modals.append(page._modal(overview_id,"AI Overview",str(obs.get("query") or "Consulta"),overview_body))
    finally:
        connection.close()
    serp_table=page._table(("Consulta","Engine","País/região","Idioma","Dispositivo","Profundidade","Resultados","Provedor","Atualidade dos dados","Capturado em","Detalhe"),rows,empty="Nenhuma observação SERP persistida.",sortable=bool(rows),page_size=10 if len(rows)>10 else None)+"".join(modals)
    aio_table=page._table(("Consulta","AI Overview detectado","Site citado","Referências","Capturado em","Detalhe"),overview_rows,empty="Nenhuma SERP disponível para verificar AI Overview.",sortable=bool(overview_rows))+"".join(overview_modals)
    return "<div class='subsection'><h3>SERP</h3>"+serp_table+"</div><div class='subsection'><h3>AI Overview / recursos de busca por IA</h3>"+aio_table+"</div>"


def _search_contract(data: Any) -> dict[str, Any]:
    for item in getattr(data, "work_items", ()):
        if str(item.get("component") or "").upper() != "SEARCH_INTELLIGENCE":
            continue
        raw = _safe_json(item.get("configuration"), {})
        if isinstance(raw, Mapping):
            return dict(raw)
    return {}


def _artifact_integrity(database: Path, reference: Any, expected_sha: Any) -> str:
    ref = str(reference or "").strip().replace("\\", "/")
    expected = str(expected_sha or "").strip().casefold()
    if not ref:
        return "Sem artefato"
    root = database.parent.resolve()
    path = (root / ref).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return "Referência fora do workspace"
    if not path.is_file():
        return "Artefato não encontrado"
    if not expected:
        return "Arquivo presente; SHA-256 esperado não persistido"
    actual = sha256(path.read_bytes()).hexdigest().casefold()
    return "Íntegro - SHA-256 confere" if actual == expected else "INCONSISTENTE - SHA-256 divergente"


def _competitive_governance(
    connection: sqlite3.Connection,
    *,
    audit_id: str,
    observation_id: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any] | None, list[dict[str, Any]]]:
    task: dict[str, Any] | None = None
    rounds: list[dict[str, Any]] = []
    snapshot: dict[str, Any] | None = None
    attempts: list[dict[str, Any]] = []
    if _table_exists(connection, "ai_tasks"):
        row = connection.execute(
            """SELECT * FROM ai_tasks
               WHERE audit_id=? AND purpose='COMPETITIVE_INTELLIGENCE' AND scope_key=?
               ORDER BY created_at DESC,rowid DESC LIMIT 1""",
            (audit_id, observation_id),
        ).fetchone()
        task = dict(row) if row is not None else None
    if task and _table_exists(connection, "ai_request_rounds"):
        rounds = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM ai_request_rounds WHERE ai_task_id=? ORDER BY round_index,started_at",
                (task.get("ai_task_id"),),
            ).fetchall()
        ]
    if task and _table_exists(connection, "ai_evidence_versions"):
        row = connection.execute(
            "SELECT * FROM ai_evidence_versions WHERE evidence_snapshot_id=?",
            (task.get("evidence_snapshot_id"),),
        ).fetchone()
        snapshot = dict(row) if row is not None else None
    if task and _table_exists(connection, "ai_provider_attempts"):
        cols = _columns(connection, "ai_provider_attempts")
        if "ai_task_id" in cols:
            order_parts = [name for name in ("started_at", "attempt_index", "attempt_id") if name in cols]
            order_by = ",".join(order_parts) if order_parts else "rowid"
            attempts = [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM ai_provider_attempts WHERE audit_id=? AND ai_task_id=? ORDER BY {order_by}",
                    (audit_id, task.get("ai_task_id")),
                ).fetchall()
            ]
    return task, rounds, snapshot, attempts


def _contract_rows(configuration: Mapping[str, Any]) -> list[tuple[Any, ...]]:
    if not configuration:
        return []
    def yes(value: Any) -> str:
        return "Sim" if bool(value) else "Não"
    return [
        ("Termos de busca", ", ".join(str(v) for v in configuration.get("queries", []) if str(v)) or "-"),
        ("Localidade", configuration.get("region") or "-"),
        ("Profundidade desejada", configuration.get("depth") or "-"),
        ("Dispositivo", configuration_value_report("RASAI_DEVICE_CONTEXT", configuration.get("device") or "-")),
        ("Análise de concorrentes", yes(configuration.get("competitive"))),
        ("Comparação de conteúdo", yes(configuration.get("compare_content"))),
        ("Máx. páginas concorrentes", configuration.get("max_content_pages") if configuration.get("max_content_pages") is not None else "-"),
        ("Timeout conteúdo", f"{configuration.get('content_timeout_seconds')} s" if configuration.get("content_timeout_seconds") is not None else "-"),
        ("Máx. bytes por página", configuration.get("content_max_bytes") if configuration.get("content_max_bytes") is not None else "-"),
        ("Máx. redirects", configuration.get("content_max_redirects") if configuration.get("content_max_redirects") is not None else "-"),
        ("IA competitiva", yes(configuration.get("ai_competitive"))),
        ("Contexto YMYL da IA", configuration_value_report("SEARCH_YMYL_MODE", configuration.get("ymyl_mode") or "-")),
        ("Modo SERP", configuration_value_report("RASAI_SERP_MODE", configuration.get("mode") or "-")),
        ("Provider SERP", configuration.get("provider") or "-"),
        ("Engine", configuration.get("engine") or "-"),
        ("Limite de queries", configuration.get("max_queries") if configuration.get("max_queries") is not None else "-"),
        ("Limite de requests", configuration.get("max_requests") if configuration.get("max_requests") is not None else "-"),
        ("Profundidade máxima", configuration.get("max_depth") if configuration.get("max_depth") is not None else "-"),
        ("Máximo de concorrentes", configuration.get("max_competitors") if configuration.get("max_competitors") is not None else "-"),
        ("Retries SERP", configuration.get("retries") if configuration.get("retries") is not None else "-"),
        ("Timeout SERP", f"{configuration.get('timeout_seconds')} s" if configuration.get("timeout_seconds") is not None else "-"),
        ("Intervalo mínimo", f"{configuration.get('min_interval_seconds')} s" if configuration.get("min_interval_seconds") is not None else "-"),
        ("Market", configuration.get("market") or "-"),
        ("Idioma", configuration.get("language") or "-"),
        ("IA principal solicitada", configuration_value_report("RASAI_AI_PROVIDER", configuration.get("ai_provider") or "-")),
        ("Modelo solicitado", configuration.get("ai_model") or "Seleção automática / padrão do provider"),
    ]



def _competitive_validation_rows(
    configuration: Mapping[str, Any],
    item: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    pages: Sequence[Mapping[str, Any]],
    ai: Mapping[str, Any] | None,
    task: Mapping[str, Any] | None,
    rounds: Sequence[Mapping[str, Any]],
    snapshot: Mapping[str, Any] | None,
    runtime_policy: Mapping[str, Any] | None = None,
) -> list[tuple[Any, ...]]:
    """Validate the CAT-05 persisted contract without treating configuration as observed execution."""
    def yes(value: Any) -> str:
        return "Sim" if bool(value) else "Não"

    def persisted(key: str) -> str:
        return "Sim" if key in configuration else "Não"

    selected_count = sum(1 for row in candidates if row.get("selected_for_content_comparison"))
    runtime_policy = dict(runtime_policy or {})
    comparison_status = str(item.get("comparison_status") or "").upper()
    artifact_ref = str(item.get("evidence_ref") or "").strip()
    configured_competitive = bool(configuration.get("competitive"))
    configured_compare = bool(configuration.get("compare_content"))
    configured_ai = bool(configuration.get("ai_competitive"))

    rows: list[tuple[Any, ...]] = []

    competitive_state = (
        "OK"
        if configured_competitive and bool(item)
        else "INCONSISTENTE"
        if not configured_competitive and (bool(candidates) or bool(item))
        else "NÃO EXECUTADO"
    )
    rows.append((
        "Análise de concorrentes",
        yes(configured_competitive),
        persisted("competitive"),
        f"{len(candidates)} candidato(s) classificado(s)" if item else "Não executado",
        "Sim",
        "serp_competitive_analyses / serp_competitive_results",
        competitive_state,
    ))

    runtime_content_enabled = runtime_policy.get("content_enabled")
    if configured_compare:
        if runtime_content_enabled is False:
            comparison_state = "INCONSISTENTE"
        elif comparison_status == "CONSOLIDATED":
            comparison_state = "OK"
        elif comparison_status == "CONTENT_COMPARISON_DISABLED":
            comparison_state = "INCONSISTENTE"
        elif comparison_status:
            comparison_state = "COM LIMITAÇÃO"
        else:
            comparison_state = "SEM EVIDÊNCIA"
    else:
        comparison_state = (
            "INCONSISTENTE"
            if comparison_status == "CONSOLIDATED" or bool(pages)
            else "NÃO EXECUTADO"
        )
    rows.append((
        "Comparação de conteúdo",
        yes(configured_compare),
        persisted("compare_content"),
        comparison_status or "Não executado",
        "Sim",
        (
            f"{artifact_ref or 'serp_competitive_pages'}; runtime content_enabled="
            f"{runtime_content_enabled if runtime_content_enabled is not None else 'não materializado'}"
        ),
        comparison_state,
    ))

    customer_source = str(runtime_policy.get("customer_source") or "").upper()
    customer_source_label = {
        "AUDIT_RENDERED_ARTIFACT": "Captura renderizada da própria AUD",
        "PUBLIC_WEB_HTTP": "Aquisição HTTP pública",
    }.get(customer_source, "Não materializado")
    customer_source_state = (
        "NÃO APLICÁVEL"
        if not configured_compare
        else "OK"
        if customer_source in {"AUDIT_RENDERED_ARTIFACT", "PUBLIC_WEB_HTTP"}
        else "COM LIMITAÇÃO"
    )
    rows.append((
        "Fonte do conteúdo do site auditado",
        "Reutilizar captura renderizada da AUD quando disponível",
        "Sim" if "customer_source" in runtime_policy else "Não",
        customer_source_label,
        "Sim",
        "artifact.acquisition_policy.customer_source",
        customer_source_state,
    ))

    max_pages = configuration.get("max_content_pages")
    try:
        max_pages_int = int(max_pages) if max_pages is not None else None
    except (TypeError, ValueError):
        max_pages_int = None
    runtime_max_pages = runtime_policy.get("max_competitor_pages")
    try:
        runtime_max_pages_int = int(runtime_max_pages) if runtime_max_pages is not None else None
    except (TypeError, ValueError):
        runtime_max_pages_int = None
    max_pages_state = (
        "SEM EVIDÊNCIA"
        if max_pages_int is None
        else "INCONSISTENTE"
        if selected_count > max_pages_int
        else "COM LIMITAÇÃO"
        if runtime_max_pages_int is None
        else "INCONSISTENTE"
        if runtime_max_pages_int != max_pages_int
        else "OK"
    )
    rows.append((
        "Máx. páginas concorrentes",
        max_pages if max_pages is not None else "-",
        persisted("max_content_pages"),
        selected_count,
        "Sim",
        (
            "serp_competitive_results.selected_for_content_comparison; "
            f"runtime max_competitor_pages={runtime_max_pages if runtime_max_pages is not None else 'não materializado'}"
        ),
        max_pages_state,
    ))

    timeout = configuration.get("content_timeout_seconds")
    runtime_timeout = runtime_policy.get("timeout_seconds")
    try:
        timeout_num = float(timeout) if timeout is not None else None
        runtime_timeout_num = float(runtime_timeout) if runtime_timeout is not None else None
    except (TypeError, ValueError):
        timeout_num = None
        runtime_timeout_num = None
    timeout_state = (
        "SEM EVIDÊNCIA"
        if timeout_num is None
        else "COM LIMITAÇÃO"
        if runtime_timeout_num is None
        else "OK"
        if abs(runtime_timeout_num - timeout_num) < 1e-9
        else "INCONSISTENTE"
    )
    rows.append((
        "Timeout conteúdo",
        f"{timeout} s" if timeout is not None else "-",
        persisted("content_timeout_seconds"),
        f"{runtime_timeout} s" if runtime_timeout is not None else "Não materializado no artefato",
        "Sim",
        "artifact.acquisition_policy.timeout_seconds",
        timeout_state,
    ))

    max_bytes = configuration.get("content_max_bytes")
    byte_values = [
        int(row.get("bytes_read"))
        for row in pages
        if row.get("bytes_read") is not None
    ]
    try:
        max_bytes_int = int(max_bytes) if max_bytes is not None else None
    except (TypeError, ValueError):
        max_bytes_int = None
    max_observed_bytes = max(byte_values, default=None)
    runtime_max_bytes = runtime_policy.get("max_bytes")
    try:
        runtime_max_bytes_int = int(runtime_max_bytes) if runtime_max_bytes is not None else None
    except (TypeError, ValueError):
        runtime_max_bytes_int = None
    bytes_state = (
        "SEM EVIDÊNCIA"
        if max_bytes_int is None
        else "INCONSISTENTE"
        if max_observed_bytes is not None and max_observed_bytes > max_bytes_int
        else "COM LIMITAÇÃO"
        if runtime_max_bytes_int is None
        else "INCONSISTENTE"
        if runtime_max_bytes_int != max_bytes_int
        else "OK"
    )
    rows.append((
        "Máx. bytes por página",
        max_bytes if max_bytes is not None else "-",
        persisted("content_max_bytes"),
        f"máx. observado {max_observed_bytes} bytes"
        if max_observed_bytes is not None
        else "Sem página observada",
        "Sim",
        (
            f"artifact.acquisition_policy.max_bytes={runtime_max_bytes if runtime_max_bytes is not None else 'não materializado'}; "
            "serp_competitive_pages.bytes_read"
        ),
        bytes_state,
    ))

    max_redirects = configuration.get("content_max_redirects")
    redirect_counts = [len(_safe_json(row.get("redirects_json"), [])) for row in pages]
    try:
        max_redirects_int = int(max_redirects) if max_redirects is not None else None
    except (TypeError, ValueError):
        max_redirects_int = None
    max_observed_redirects = max(redirect_counts, default=None)
    runtime_max_redirects = runtime_policy.get("max_redirects")
    try:
        runtime_max_redirects_int = int(runtime_max_redirects) if runtime_max_redirects is not None else None
    except (TypeError, ValueError):
        runtime_max_redirects_int = None
    redirects_state = (
        "SEM EVIDÊNCIA"
        if max_redirects_int is None
        else "INCONSISTENTE"
        if max_observed_redirects is not None
        and max_observed_redirects > max_redirects_int
        else "COM LIMITAÇÃO"
        if runtime_max_redirects_int is None
        else "INCONSISTENTE"
        if runtime_max_redirects_int != max_redirects_int
        else "OK"
    )
    rows.append((
        "Máx. redirects",
        max_redirects if max_redirects is not None else "-",
        persisted("content_max_redirects"),
        f"máx. observado {max_observed_redirects}"
        if max_observed_redirects is not None
        else "Sem página observada",
        "Sim",
        (
            f"artifact.acquisition_policy.max_redirects={runtime_max_redirects if runtime_max_redirects is not None else 'não materializado'}; "
            "serp_competitive_pages.redirects_json"
        ),
        redirects_state,
    ))

    ai_state = str((ai or {}).get("state") or "").upper()
    if configured_ai:
        if ai is not None and task is not None:
            competitive_ai_state = "OK" if ai_state == "AVAILABLE" else "COM LIMITAÇÃO"
        elif comparison_status != "CONSOLIDATED":
            competitive_ai_state = "NÃO ELEGÍVEL"
        else:
            competitive_ai_state = "INCONSISTENTE"
    else:
        competitive_ai_state = (
            "INCONSISTENTE" if ai is not None or task is not None else "NÃO EXECUTADO"
        )
    rows.append((
        "IA competitiva",
        yes(configured_ai),
        persisted("ai_competitive"),
        ai_state or "Não executada",
        "Sim",
        (ai or {}).get("evidence_ref") or (task or {}).get("ai_task_id") or "-",
        competitive_ai_state,
    ))

    ymyl_mode = str(configuration.get("ymyl_mode") or "AUTO").upper()
    ymyl_assessment = str((ai or {}).get("ymyl_assessment") or "").strip()
    rows.append((
        "YMYL",
        ymyl_mode,
        persisted("ymyl_mode"),
        ymyl_assessment
        or ("Não elegível sem IA competitiva" if not configured_ai else "Não materializado"),
        "Sim",
        (ai or {}).get("evidence_ref") or "-",
        "OK"
        if ai is not None and ymyl_assessment
        else "NÃO ELEGÍVEL"
        if not configured_ai or comparison_status != "CONSOLIDATED"
        else "COM LIMITAÇÃO",
    ))

    snapshot_id = str((task or {}).get("evidence_snapshot_id") or "")
    sealed_at = str((snapshot or {}).get("sealed_at") or "")
    if not configured_ai or comparison_status != "CONSOLIDATED":
        seal_state = "NÃO ELEGÍVEL"
    elif task is not None and snapshot_id and sealed_at:
        seal_state = "OK"
    else:
        seal_state = "SEM EVIDÊNCIA"
    rows.append((
        "Evidence seal",
        "n/a",
        snapshot_id or "Não materializado",
        sealed_at or "Não materializado",
        "Sim",
        snapshot_id or "-",
        seal_state,
    ))

    first_round = min(
        (str(row.get("started_at") or "") for row in rounds if row.get("started_at")),
        default="",
    )
    sealed_dt = _dt(sealed_at)
    round_dt = _dt(first_round)
    if not configured_ai or comparison_status != "CONSOLIDATED":
        post_seal_state = "NÃO ELEGÍVEL"
        post_seal_execution = "IA competitiva não elegível"
    elif task is None or snapshot is None or not first_round:
        post_seal_state = "SEM EVIDÊNCIA"
        post_seal_execution = "Ordem temporal não comprovável"
    elif sealed_dt is not None and round_dt is not None and round_dt >= sealed_dt:
        post_seal_state = "OK"
        post_seal_execution = f"{first_round} >= {sealed_at}"
    elif sealed_dt is not None and round_dt is not None:
        post_seal_state = "INCONSISTENTE"
        post_seal_execution = f"{first_round} < {sealed_at}"
    else:
        post_seal_state = "SEM EVIDÊNCIA"
        post_seal_execution = "Timestamps insuficientes"
    rows.append((
        "IA pós-selo",
        "n/a",
        (task or {}).get("ai_task_id") or "-",
        post_seal_execution,
        "Sim",
        f"snapshot={snapshot_id or '-'} / task={(task or {}).get('ai_task_id') or '-'}",
        post_seal_state,
    ))
    return rows


def _competitive_html(database: Path, data: Any) -> str:
    from rasai import catalog_report_page as page

    configuration = _search_contract(data)
    connection=sqlite3.connect(database); connection.row_factory=sqlite3.Row
    try:
        analyses=(
            [dict(row) for row in connection.execute(
                "SELECT * FROM serp_competitive_analyses WHERE audit_id=? ORDER BY observation_id",
                (data.audit_id,),
            )]
            if _table_exists(connection,"serp_competitive_analyses")
            else []
        )
        rows=[]; modals=[]
        for index,item in enumerate(analyses,1):
            oid=str(item.get("observation_id") or "")
            obs_row=connection.execute("SELECT * FROM serp_observations WHERE observation_id=?",(oid,)).fetchone() if _table_exists(connection,"serp_observations") else None
            obs=dict(obs_row) if obs_row is not None else {}
            candidates=[dict(row) for row in connection.execute("SELECT * FROM serp_competitive_results WHERE observation_id=? ORDER BY position",(oid,))] if _table_exists(connection,"serp_competitive_results") else []
            pages=[dict(row) for row in connection.execute("SELECT * FROM serp_competitive_pages WHERE observation_id=? ORDER BY role,requested_url",(oid,))] if _table_exists(connection,"serp_competitive_pages") else []
            ai=connection.execute("SELECT * FROM serp_competitive_ai_analyses WHERE observation_id=?",(oid,)).fetchone() if _table_exists(connection,"serp_competitive_ai_analyses") else None
            ai=dict(ai) if ai is not None else None
            task, rounds, snapshot, attempts = _competitive_governance(
                connection,
                audit_id=data.audit_id,
                observation_id=oid,
            )
            modal_id=f"cat05-competitive-{index}"
            selected_count=sum(1 for r in candidates if r.get("selected_for_content_comparison"))
            rows.append((
                obs.get("query") or "-",
                page._status_label(item.get("comparison_status")),
                len(candidates),
                selected_count,
                item.get("observed_competitor_pages") or 0,
                item.get("gap_count") or 0,
                page._status_label(ai.get("state")) if ai else "Não materializada",
                item.get("methodology") or "-",
                page._modal_button(modal_id,"Ver análise"),
            ))
            candidate_rows=[(
                r.get("position"),
                r.get("domain"),
                r.get("url") or "-",
                r.get("classification"),
                "Sim" if r.get("eligible_for_content_comparison") else "Não",
                "Sim" if r.get("selected_for_content_comparison") else "Não",
                r.get("reason") or "-",
            ) for r in candidates]
            page_rows=[(
                r.get("role"),
                r.get("domain"),
                r.get("requested_url") or "-",
                r.get("final_url") or "-",
                page._status_label(r.get("fetch_status")),
                r.get("http_status") or "-",
                r.get("content_type") or "-",
                r.get("bytes_read") if r.get("bytes_read") is not None else "-",
                len(_safe_json(r.get("redirects_json"), [])),
                r.get("content_sha256") or "-",
                r.get("error_message") or r.get("error_code") or "-",
            ) for r in pages]
            body=page._kv((
                ("Consulta",obs.get("query") or "-"),
                ("Resultados SERP recebidos",obs.get("result_count") if obs.get("result_count") is not None else "-"),
                ("Posição do domínio auditado",obs.get("customer_position") if obs.get("customer_position") is not None else "Não encontrado / não informado"),
                ("Estado do domínio auditado",page._status_label(obs.get("domain_status")) if obs.get("domain_status") else "-"),
                ("Status da comparação",page._status_label(item.get("comparison_status"))),
                ("Metodologia",item.get("methodology") or "-"),
                ("Artefato determinístico",item.get("evidence_ref") or "-"),
                ("SHA-256 determinístico",item.get("evidence_sha256") or "-"),
                ("Integridade do artefato",_artifact_integrity(database,item.get("evidence_ref"),item.get("evidence_sha256"))),
            ))
            inconsistencies=[]
            if bool(configuration.get("compare_content")) and str(item.get("comparison_status") or "").upper()=="CONTENT_COMPARISON_DISABLED":
                inconsistencies.append("A configuração efetiva exige comparação de conteúdo, mas a análise persistida indica comparação desabilitada.")
            max_pages=configuration.get("max_content_pages")
            try:
                if max_pages is not None and selected_count>int(max_pages):
                    inconsistencies.append(f"Foram selecionadas {selected_count} páginas concorrentes, acima do limite configurado de {int(max_pages)}.")
            except (TypeError,ValueError):
                pass
            if bool(configuration.get("ai_competitive")) and str(item.get("comparison_status") or "").upper()=="CONSOLIDATED" and ai is None:
                inconsistencies.append("A IA competitiva foi solicitada e a comparação está consolidada, mas nenhum resultado de IA foi materializado.")
            if ai and task is None:
                inconsistencies.append("Existe resultado persistido da IA competitiva, mas a task governada correspondente não foi encontrada.")
            if inconsistencies:
                body+="<div class='notice warn'><strong>Inconsistência de contrato:</strong><ul>"+"".join("<li>"+escape(v)+"</li>" for v in inconsistencies)+"</ul></div>"


            deterministic_payload = _artifact_json(database, item.get("evidence_ref"))
            runtime_policy = (
                deterministic_payload.get("acquisition_policy")
                if isinstance(deterministic_payload.get("acquisition_policy"), Mapping)
                else {}
            )
            validation_rows = _competitive_validation_rows(
                configuration,
                item,
                candidates,
                pages,
                ai,
                task,
                rounds,
                snapshot,
                runtime_policy,
            )
            body += (
                "<h3>Validação ponta a ponta - configuração, evidência e IA</h3>"
                + page._table(
                    ("Controle","Configurado","Persistido","Executado","Reportado","Evidência","Estado"),
                    validation_rows,
                    empty="Nenhum controle competitivo pôde ser validado.",
                )
                + "<p class='muted'>Configurado representa o contrato efetivo persistido no work item desta AUD. "
                "Os limites de aquisição executados são confrontados com o snapshot <code>acquisition_policy</code> "
                "do artefato competitivo; evidência ausente é marcada como COM LIMITAÇÃO/SEM EVIDÊNCIA em vez de ser presumida.</p>"
            )

            body+="<h3>Candidatos e classificação</h3>"+page._table(
                ("Posição","Domínio","URL","Classificação","Elegível","Selecionado","Motivo"),
                candidate_rows,
                empty="Nenhum candidato persistido.",
                sortable=bool(candidate_rows),
                page_size=10 if len(candidate_rows)>10 else None,
            )
            body+="<h3>Aquisição e comparação de conteúdo</h3>"+page._table(
                ("Papel","Domínio","URL solicitada","URL final","Coleta","HTTP","Content-Type","Bytes","Redirects","SHA-256","Erro"),
                page_rows,
                empty="Nenhuma página comparativa persistida.",
                sortable=bool(page_rows),
                page_size=10 if len(page_rows)>10 else None,
            )
            gaps=_safe_json(item.get("gaps_json"),[])
            gap_rows=[]
            if isinstance(gaps,list):
                for gap in gaps:
                    if not isinstance(gap,Mapping):
                        continue
                    customer_value=gap.get("customer_value")
                    leader=gap.get("leader_reference")
                    gap_rows.append((
                        gap.get("code") or "-",
                        gap.get("severity") or "-",
                        gap.get("message") or "-",
                        json.dumps(customer_value,ensure_ascii=False) if isinstance(customer_value,(dict,list)) else customer_value if customer_value is not None else "-",
                        json.dumps(leader,ensure_ascii=False) if isinstance(leader,(dict,list)) else leader if leader is not None else "-",
                        ", ".join(str(v) for v in gap.get("evidence_urls",[]) if str(v)) or "-",
                    ))
            body+="<h3>Lacunas correlacionais determinísticas</h3>"+page._table(
                ("Código","Severidade","Diferença observada","Valor do site auditado","Referência observada","Evidências/URLs"),
                gap_rows,
                empty="Nenhuma lacuna determinística foi persistida.",
                sortable=bool(gap_rows),
            )

            if ai:
                opportunities=_safe_json(ai.get("opportunities_json"),[])
                body+="<h3>Análise competitiva por IA</h3>"+page._kv((
                    ("Estado",page._status_label(ai.get("state"))),
                    ("Provider efetivo",ai.get("provider") or "-"),
                    ("Modelo efetivo",ai.get("model") or "-"),
                    ("Contrato",ai.get("contract_version") or "-"),
                    ("Prompt",f"{ai.get('prompt_id') or '-'} v{ai.get('prompt_version') or '-'}"),
                    ("Request ID",ai.get("provider_request_id") or "-"),
                    ("Intenção da query",ai.get("query_intent") or "-"),
                    ("Avaliação YMYL",ai.get("ymyl_assessment") or "-"),
                    ("Resumo",ai.get("summary") or ai.get("reason") or "-"),
                    ("Artefato da IA",ai.get("evidence_ref") or "-"),
                    ("SHA-256 da IA",ai.get("evidence_sha256") or "-"),
                    ("Integridade do artefato da IA",_artifact_integrity(database,ai.get("evidence_ref"),ai.get("evidence_sha256"))),
                ))
                opportunity_rows=[(
                    row.get("priority") or "-",
                    row.get("category") or "-",
                    row.get("title") or "-",
                    row.get("recommendation") or "-",
                    row.get("rationale") or "-",
                    ", ".join(row.get("evidence_ids") or []),
                    row.get("confidence") if row.get("confidence") is not None else "-",
                    row.get("causality_note") or "-",
                ) for row in opportunities if isinstance(row,Mapping)]
                body+=page._table(
                    ("Prioridade","Categoria","Oportunidade","Recomendação","Racional","Evidências","Confiança","Nota de causalidade"),
                    opportunity_rows,
                    empty="A IA não materializou oportunidades para esta observação.",
                    page_size=10 if len(opportunity_rows)>10 else None,
                )

            if task:
                sealed_at=snapshot.get("sealed_at") if snapshot else None
                first_round=min((str(r.get("started_at") or "") for r in rounds if r.get("started_at")),default="")
                sealed_dt=_dt(sealed_at); round_dt=_dt(first_round)
                order_label=(
                    "Sim" if sealed_dt is not None and round_dt is not None and round_dt>=sealed_dt
                    else "Não - ordem temporal inconsistente" if sealed_dt is not None and round_dt is not None
                    else "Não determinável"
                )
                total_cost=sum(float(r.get("estimated_cost") or 0) for r in attempts)
                total_tokens=sum(int(r.get("total_tokens") or 0) for r in attempts)
                body+="<h3>Governança da IA competitiva</h3>"+page._kv((
                    ("Purpose",task.get("purpose") or "-"),
                    ("Scope",f"{task.get('scope_type') or '-'} / {task.get('scope_key') or '-'}"),
                    ("Evidence snapshot",task.get("evidence_snapshot_id") or "-"),
                    ("Evidência selada em",sealed_at or "-"),
                    ("Primeiro round iniciado em",first_round or "-"),
                    ("IA iniciou após o selo",order_label),
                    ("Requirements",", ".join(_safe_json(task.get("requirements_json"),[])) or "-"),
                    ("Estado da task",page._status_label(task.get("status"))),
                    ("Rounds persistidos",len(rounds)),
                    ("Tentativas de provider",len(attempts)),
                    ("Tokens persistidos",total_tokens),
                    ("Custo observado",f"{attempts[0].get('cost_currency') or 'USD'} {total_cost:.8f}" if attempts else "Não materializado"),
                ))
                round_rows=[(
                    r.get("round_index"),
                    page._status_label(r.get("status")),
                    r.get("started_at") or "-",
                    r.get("finished_at") or "-",
                    r.get("input_hash") or "-",
                    r.get("output_hash") or "-",
                    ", ".join(_safe_json(r.get("missing_json"),[])) or "-",
                ) for r in rounds]
                body+=page._table(
                    ("Round","Estado","Início","Fim","Hash entrada","Hash saída","Pendências"),
                    round_rows,
                    empty="Nenhum round governado persistido.",
                )
                attempt_rows=[(
                    r.get("provider") or "-",
                    r.get("model") or "-",
                    r.get("reasoning_profile") or "-",
                    page._status_label(r.get("status")),
                    r.get("decision") or "-",
                    r.get("input_tokens") or 0,
                    r.get("output_tokens") or 0,
                    r.get("total_tokens") or 0,
                    f"{r.get('cost_currency') or 'USD'} {float(r.get('estimated_cost') or 0):.8f}",
                    r.get("error_code") or "-",
                ) for r in attempts]
                body+=page._table(
                    ("Provider","Modelo","Esforço","Estado","Roteamento","Input","Output","Total","Custo","Erro"),
                    attempt_rows,
                    empty="Nenhuma tentativa de provider vinculada a esta task foi persistida.",
                )
            elif bool(configuration.get("ai_competitive")):
                body+="<div class='notice warn'><strong>Governança da IA:</strong> a configuração solicitou IA competitiva, mas não há task governada vinculada a esta observação.</div>"

            body+="<div class='notice'>A classificação e a comparação determinística são autoritativas para as evidências. A IA, quando solicitada, é executada somente depois do selo de evidências e produz interpretação advisory; não declara causalidade de ranking nem concorrência comercial.</div>"
            modals.append(page._modal(modal_id,"Inteligência competitiva",str(obs.get("query") or oid),body))

        contract_html=(
            "<div class='subsection'><h3>Contrato competitivo efetivo desta AUD</h3>"
            + page._table(("Parâmetro","Valor efetivo"),_contract_rows(configuration),empty="O work item de Search Intelligence não contém configuração competitiva persistida.")
            + "<p class='muted'>Estes valores vêm do work item persistido desta AUD e são usados para confrontar configuração, execução e resultado competitivo.</p></div>"
        )
        table=page._table(
            ("Consulta","Status","Classificados","Selecionados","Páginas observadas","Lacunas","IA","Metodologia","Detalhe"),
            rows,
            empty="Nenhuma análise competitiva persistida. A configuração efetiva permanece exposta acima para distinguir não execução, não elegibilidade e falha de materialização.",
            sortable=bool(rows),
        )
        return contract_html+table+"".join(modals)
    finally:
        connection.close()

def _external_html(database: Path, data: Any) -> str:
    from rasai import catalog_report_page as page
    datasets, connection=_observability(database)
    if connection is None:
        return "<div class='notice'>Nenhum observability.db persistido para esta AUD.</div>"
    try:
        blocks=[]
        for source,title,table in ((_COMMON_CRAWL_SOURCE,"Common Crawl","web_archive_observations"),(_CLARITY_SOURCE,"Microsoft Clarity","behavioral_observations")):
            rows=[row for row in datasets if str(row.get("source_type") or "")==source]
            ids=[str(row.get("dataset_id")) for row in rows]
            count=_dataset_rows(connection,table,ids)
            errors=_dataset_errors(rows)
            details=[]; source_modals=[]
            for index,row in enumerate(rows,1):
                meta=_safe_json(row.get("metadata"),{})
                detail_cell: Any = "-"
                if source==_COMMON_CRAWL_SOURCE and int(meta.get("errors") or 0) > 0:
                    modal_id=f"common-crawl-error-{index}"
                    error_rows=_common_crawl_error_rows(database,row)
                    no_capture=_common_crawl_no_capture(error_rows)
                    state_label=(
                        "Execução parcial · coleção sem captura"
                        if no_capture and count
                        else "Sem captura nas coleções consultadas"
                        if no_capture
                        else "Falha reprocessável"
                        if not count
                        else "Execução parcial"
                    )
                    body=page._kv((
                        ("Estado",state_label),
                        ("Conjunto de dados",row.get("dataset_id") or "-"),
                        ("Tentativas de API",meta.get("requests") or "-"),
                        ("Registros obtidos",meta.get("rows") or 0),
                        ("Erros",meta.get("errors") or len(error_rows)),
                        ("Artefato",row.get("artifact_path") or "-"),
                    ))
                    display_error_rows=[
                        (
                            item[0],
                            item[1],
                            item[2],
                            page._Html(escape(str(item[3] or "-"))),
                            item[4],
                        )
                        for item in error_rows
                    ]
                    body+="<h3>Erros observados</h3>"+page._table(
                        ("Coleção","URL auditada","Tipo","Mensagem","Endpoint"),
                        display_error_rows,
                        empty="O dataset informa erro, mas não há detalhe individual persistido.",
                        sortable=bool(display_error_rows),
                        page_size=10 if len(display_error_rows)>10 else None,
                    )
                    if no_capture:
                        body+=(
                            "<h3>Como interpretar e tratar</h3><ol>"
                            "<li>O HTTP 404 com <code>No Captures found</code> indica que o endpoint do Common Crawl respondeu, mas não encontrou captura da URL na coleção consultada. Não é evidência de falha de DNS, proxy, firewall ou conectividade local.</li>"
                            "<li>Esse estado descreve cobertura do arquivo público naquela coleção; não implica erro no site e não comprova ausência de indexação em mecanismos de busca.</li>"
                            "<li>Se for necessário ampliar a evidência histórica, consulte outras coleções disponíveis em uma nova coleta ou aguarde atualização do arquivo público. Não altere a URL auditada apenas por esse retorno.</li>"
                            "<li>Repetir imediatamente a mesma coleção pode retornar o mesmo resultado enquanto a cobertura do Common Crawl não mudar.</li>"
                            "</ol>"
                        )
                        detail_label="Ver diagnóstico e orientação"
                    else:
                        body+=(
                            "<h3>Como resolver</h3><ol>"
                            "<li>Verifique conectividade HTTPS, proxy, firewall e resolução DNS para <code>index.commoncrawl.org</code> e para o endpoint CDX indicado acima.</li>"
                            "<li>Confirme se a coleção Common Crawl indicada ainda responde pelo endpoint público CDX. O RASAi consulta somente o índice; não baixa WARC.</li>"
                            "<li>Quando houver dependência realmente pendente/reprocessável no fulfillment, use o reprocessamento seletivo da mesma AUD.</li>"
                            "<li>Se o erro persistir em coleções diferentes, valide disponibilidade do serviço público e o detalhe da exceção antes de alterar a URL auditada.</li>"
                            "</ol>"
                            "<div class='notice'>Falha do Common Crawl não implica erro no site e não comprova ausência de indexação em mecanismos de busca.</div>"
                        )
                        detail_label="Ver erro e como corrigir"
                    detail_cell=page._modal_button(modal_id,detail_label)
                    source_modals.append(page._modal(modal_id,"Common Crawl - diagnóstico de coleta",str(row.get("dataset_id") or "Dataset"),body))
                details.append((row.get("dataset_id"),row.get("capture_method"),row.get("collected_at"),meta.get("requests") if isinstance(meta,Mapping) else "-",meta.get("rows") if isinstance(meta,Mapping) else count,meta.get("errors") if isinstance(meta,Mapping) else errors,row.get("artifact_path"),detail_cell))
            lead=f"<div class='metric-grid'>{page._metric('Execuções/datasets',len(rows))}{page._metric('Resultados',count)}{page._metric('Erros',errors)}</div>"
            if source==_COMMON_CRAWL_SOURCE:
                lead+="<div class='notice'>Common Crawl representa histórico do arquivo público e não comprova indexação atual em Google/Bing. Não participa diretamente do score. Quando houver limitação ou erro, use o detalhe do dataset para distinguir ausência de captura, indisponibilidade do provider e falha de transporte.</div>"
            blocks.append("<div class='subsection'><h3>"+escape(title)+"</h3>"+lead+page._table(("Conjunto de dados","Método","Coletado em","Requisições","Registros","Erros","Artefato","Diagnóstico"),details,empty=f"{title} não executado/não persistido nesta AUD.")+"".join(source_modals)+"</div>")
        gsc=[row for row in datasets if str(row.get("source_type") or "").startswith(_GSC_PREFIX)]
        gsc_rows=[]
        for row in gsc:
            meta=_safe_json(row.get("metadata"),{})
            gsc_rows.append((str(row.get("source_type") or "").removeprefix(_GSC_PREFIX).replace("_"," ").title(),row.get("capture_method"),row.get("collected_at"),row.get("period_start") or "-",row.get("period_end") or "-",row.get("artifact_path"),meta.get("rows") if isinstance(meta,Mapping) else "-"))
        blocks.append("<div class='subsection'><h3>Google Search Console</h3>"+page._table(("Conjunto de dados","Método","Coletado em","Período inicial","Período final","Artefato","Registros"),gsc_rows,empty="Nenhum dataset GSC persistido nesta AUD.")+"</div>")
        return "".join(blocks)
    finally:
        connection.close()


def _search_intelligence_html(database: Path, data: Any) -> str:
    return (
        _serp_html(database,data)
        + "<div class='subsection'><h3>Inteligência competitiva</h3>"+_competitive_html(database,data)+"</div>"
        + _external_html(database,data)
    )


def _replace_scope(html: str, replacement: str) -> str:
    return re.sub(
        r"<section id='scope' class='panel'>.*?</section>",
        replacement,
        html,
        count=1,
        flags=re.DOTALL,
    )


def _apply() -> None:
    from rasai import catalog_report_metrics as metrics
    from rasai import catalog_report_page as page

    metrics._search_intelligence_html=_search_intelligence_html
    page._search_intelligence_html=_search_intelligence_html
    current=page._catalog_body
    original=getattr(current,"_rasai_search_trust_original",current)

    def catalog_body(database: Path, data: Any, catalog_id: str) -> str:
        html=original(database,data,catalog_id)
        if catalog_id=="CAT-05":
            html=_replace_scope(html,_scope_html(database,data))
        return html

    catalog_body._rasai_search_trust_original=original
    page._catalog_body=catalog_body


def install() -> None:
    # Re-apply on every materialization because earlier report refinement layers may
    # intentionally reinstall their own projections before this final trust layer.
    _apply()


__all__=["install","_search_intelligence_html","_source_states"]
