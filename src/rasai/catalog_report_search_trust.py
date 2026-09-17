"""Trust-oriented CAT-05 projection over persisted Search/AI evidence.

This module does not collect data. It projects the effective state of SERP, GSC,
Clarity, Common Crawl, AI Overview and competitive intelligence using SOURCE-STATE-001
and persisted evidence/artifacts only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

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
        return "—"
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
            rows.append((obs.get("query") or "—",obs.get("country") or obs.get("region") or "—",obs.get("language") or "—",page._device_label(obs.get("device")),obs.get("requested_depth") or "—",len(results),obs.get("provider") or "—",mode,captured or "—",page._modal_button(modal_id,"Ver proveniência")))
            body=page._kv((("Consulta",obs.get("query")),("Provider",obs.get("provider")),("Modo de dados",obs.get("data_mode")),("Estado da observação",page._status_label(obs.get("observation_status"))),("captured_at",captured),("Freshness",mode),("Reutilizada","Sim" if reused else "Não"),("AUD de origem",prov.get("source_audit_id") or data.audit_id),("Observação de origem",prov.get("source_observation_id") or oid),("Idade no reuso",_age(captured,prov.get("reused_at")) if reused else "Não aplicável"),("Motivo do reuso",prov.get("reuse_reason") or "Não aplicável"),("Artefato bruto",obs.get("raw_evidence_ref") or "—"),("SHA-256",obs.get("raw_evidence_sha256") or "—"),("Request ID",obs.get("provider_request_id") or "—")))
            result_rows=[(r.get("position"),r.get("domain"),r.get("url"),r.get("result_type")) for r in results]
            body+="<h3>Resultados persistidos</h3>"+page._table(("Posição","Domínio","URL","Tipo"),result_rows,empty="Nenhum resultado individual persistido.",sortable=bool(result_rows),page_size=10 if len(result_rows)>10 else None)
            modals.append(page._modal(modal_id,"SERP · proveniência",str(obs.get("query") or "Consulta"),body))

            raw=_raw_serp_artifact(database,obs)
            overview=_overview_values(raw)
            overview_id=f"cat05-aio-{index}"
            target_hosts=_target_hosts(data)
            all_urls=[]
            for item in overview:
                for url in _urls(item):
                    if url not in all_urls: all_urls.append(url)
            present_hosts={str(urlsplit(url).hostname or "").casefold().removeprefix("www.") for url in all_urls}
            brand_present=bool(target_hosts & present_hosts)
            detected=bool(overview)
            overview_rows.append((obs.get("query") or "—","Sim" if detected else "Não","Sim" if brand_present else "Não" if detected else "Não determinável",len(all_urls),captured or "—",page._modal_button(overview_id,"Ver AI Overview")))
            overview_body=page._kv((("Detectado","Sim" if detected else "Não"),("Site auditado entre as URLs citadas","Sim" if brand_present else "Não" if detected else "Não determinável"),("Provider",obs.get("provider") or "—"),("captured_at",captured or "—"),("Artefato",obs.get("raw_evidence_ref") or "—")))
            if overview:
                overview_body+="<h3>Conteúdo / resumo persistido</h3><div class='pre'>"+escape(_overview_text(overview))+"</div>"
                overview_body+="<h3>Fontes / URLs reconhecidas</h3>"+page._table(("URL",),[(url,) for url in all_urls],empty="O provider retornou AI Overview sem URLs reconhecíveis.")
            else:
                overview_body+="<div class='notice'>Nenhum campo <code>ai_overview</code> foi encontrado no artefato SERP persistido desta observação. O relatório não infere que a feature estava ausente quando o provider não fornece esse campo.</div>"
            overview_modals.append(page._modal(overview_id,"AI Overview",str(obs.get("query") or "Consulta"),overview_body))
    finally:
        connection.close()
    serp_table=page._table(("Consulta","País/região","Idioma","Dispositivo","Profundidade","Resultados","Provider","Freshness","Capturado em","Detalhe"),rows,empty="Nenhuma observação SERP persistida.",sortable=bool(rows),page_size=10 if len(rows)>10 else None)+"".join(modals)
    aio_table=page._table(("Consulta","AI Overview detectado","Site citado","Fontes","Capturado em","Detalhe"),overview_rows,empty="Nenhuma SERP disponível para verificar AI Overview.",sortable=bool(overview_rows))+"".join(overview_modals)
    return "<div class='subsection'><h3>SERP</h3>"+serp_table+"</div><div class='subsection'><h3>AI Overview / recursos de busca por IA</h3>"+aio_table+"</div>"


def _competitive_html(database: Path, data: Any) -> str:
    from rasai import catalog_report_page as page
    connection=sqlite3.connect(database); connection.row_factory=sqlite3.Row
    try:
        if not _table_exists(connection,"serp_competitive_analyses"):
            return "<div class='notice'>Nenhuma análise competitiva persistida.</div>"
        analyses=[dict(row) for row in connection.execute("SELECT * FROM serp_competitive_analyses WHERE audit_id=? ORDER BY observation_id",(data.audit_id,))]
        rows=[]; modals=[]
        for index,item in enumerate(analyses,1):
            oid=str(item.get("observation_id") or "")
            obs=connection.execute("SELECT query FROM serp_observations WHERE observation_id=?",(oid,)).fetchone() if _table_exists(connection,"serp_observations") else None
            candidates=[dict(row) for row in connection.execute("SELECT * FROM serp_competitive_results WHERE observation_id=? ORDER BY position",(oid,))] if _table_exists(connection,"serp_competitive_results") else []
            pages=[dict(row) for row in connection.execute("SELECT * FROM serp_competitive_pages WHERE observation_id=? ORDER BY role,requested_url",(oid,))] if _table_exists(connection,"serp_competitive_pages") else []
            modal_id=f"cat05-competitive-{index}"
            rows.append(((obs[0] if obs else "—"),page._status_label(item.get("comparison_status")),item.get("candidate_count") or 0,item.get("observed_competitor_pages") or 0,item.get("gap_count") or 0,item.get("methodology") or "—",page._modal_button(modal_id,"Ver análise")))
            candidate_rows=[(r.get("position"),r.get("domain"),r.get("classification"),"Sim" if r.get("selected_for_content_comparison") else "Não",r.get("reason")) for r in candidates]
            page_rows=[(r.get("role"),r.get("domain"),page._status_label(r.get("fetch_status")),r.get("http_status") or "—",r.get("error_code") or "—") for r in pages]
            body=page._kv((("Status",page._status_label(item.get("comparison_status"))),("Metodologia",item.get("methodology") or "—"),("Artefato",item.get("evidence_ref") or "—"),("SHA-256",item.get("evidence_sha256") or "—")))
            body+="<h3>Candidatos/classificação</h3>"+page._table(("Posição","Domínio","Classificação","Comparado","Motivo"),candidate_rows,empty="Nenhum candidato persistido.")
            body+="<h3>Comparação de conteúdo</h3>"+page._table(("Papel","Domínio","Fetch","HTTP","Erro"),page_rows,empty="Nenhuma página comparativa persistida.")
            gaps=_safe_json(item.get("gaps_json"),[])
            if gaps:
                body+="<h3>Lacunas correlacionais</h3><div class='pre'>"+escape(json.dumps(gaps,ensure_ascii=False,indent=2))+"</div>"
            body+="<div class='notice'>A classificação seleciona candidatos para comparação limitada; não declara causalidade de ranking nem concorrência comercial.</div>"
            modals.append(page._modal(modal_id,"Inteligência competitiva",str(obs[0] if obs else oid),body))
        return page._table(("Consulta","Status","Candidatos","Páginas observadas","Lacunas","Metodologia","Detalhe"),rows,empty="Nenhuma análise competitiva persistida.",sortable=bool(rows))+"".join(modals)
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
            details=[]
            for row in rows:
                meta=_safe_json(row.get("metadata"),{})
                details.append((row.get("dataset_id"),row.get("capture_method"),row.get("collected_at"),meta.get("requests") if isinstance(meta,Mapping) else "—",meta.get("rows") if isinstance(meta,Mapping) else count,meta.get("errors") if isinstance(meta,Mapping) else errors,row.get("artifact_path")))
            lead=f"<div class='metric-grid'>{page._metric('Execuções/datasets',len(rows))}{page._metric('Resultados',count)}{page._metric('Erros',errors)}</div>"
            if source==_COMMON_CRAWL_SOURCE:
                lead+="<div class='notice'>Common Crawl representa histórico do arquivo público e não comprova indexação atual em Google/Bing. Não participa diretamente do score.</div>"
            blocks.append("<div class='subsection'><h3>"+escape(title)+"</h3>"+lead+page._table(("Dataset","Método","Coletado em","Requests","Rows","Erros","Artefato"),details,empty=f"{title} não executado/não persistido nesta AUD.")+"</div>")
        gsc=[row for row in datasets if str(row.get("source_type") or "").startswith(_GSC_PREFIX)]
        gsc_rows=[]
        for row in gsc:
            meta=_safe_json(row.get("metadata"),{})
            gsc_rows.append((str(row.get("source_type") or "").removeprefix(_GSC_PREFIX).replace("_"," ").title(),row.get("capture_method"),row.get("collected_at"),row.get("period_start") or "—",row.get("period_end") or "—",row.get("artifact_path"),meta.get("rows") if isinstance(meta,Mapping) else "—"))
        blocks.append("<div class='subsection'><h3>Google Search Console</h3>"+page._table(("Dataset","Método","Coletado em","Período início","Período fim","Artefato","Rows"),gsc_rows,empty="Nenhum dataset GSC persistido nesta AUD.")+"</div>")
        return "".join(blocks)
    finally:
        connection.close()


def _search_intelligence_html(database: Path, data: Any) -> str:
    return (
        _serp_html(database,data)
        + "<div class='subsection'><h3>Competitive Intelligence</h3>"+_competitive_html(database,data)+"</div>"
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
