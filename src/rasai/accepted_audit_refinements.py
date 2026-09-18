"""Accepted targeted refinements for Improvement Intelligence and catalog reporting.

This module is intentionally additive and installed after canonical AI orchestration.
It keeps evidence binding strict while salvaging valid partial AI output, bounds the
wall-clock wait for deep-analysis provider calls, and refines CAT-05/CAT-08/CAT-09
presentation without changing scoring or audited facts.
"""
from __future__ import annotations

from dataclasses import replace
from html import escape
import json
import queue
import re
import sqlite3
import threading
import time
from typing import Any, Mapping, Sequence


REPAIR_TIMEOUT_CAP_SECONDS = 60.0
_INSTALLED = False
_REPORT_INSTALL_WRAPPED = False


def _safe_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list, tuple, int, float, bool)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _deadline_candidate_call(
    provider: Any,
    *,
    body: bytes,
    timeout: float,
    candidate_call: Any,
) -> tuple[Any, Any, Any, Any, int]:
    """Apply a real wall-clock deadline around a provider transport.

    urllib/socket timeout values are I/O timeouts rather than a reliable end-to-end
    deadline. A daemon worker lets the audit continue/fallback when that deadline is
    exceeded. The abandoned transport may finish later, but it cannot hold the audit
    pipeline beyond the configured deadline.
    """
    from rasai.m18_ai import AttemptStatus, ProviderDiagnostic, ProviderErrorClass

    limit = max(0.001, float(timeout))
    output: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
    started = time.perf_counter()

    def run() -> None:
        try:
            output.put(("result", candidate_call(provider, body=body, timeout=limit)))
        except BaseException as exc:
            output.put(("error", exc))

    worker = threading.Thread(
        target=run,
        name=f"rasai-improvement-{getattr(provider, 'name', 'provider')}",
        daemon=True,
    )
    worker.start()
    try:
        kind, value = output.get(timeout=limit)
    except queue.Empty:
        elapsed = max(0, int((time.perf_counter() - started) * 1000))
        return (
            None,
            None,
            ProviderDiagnostic(
                ProviderErrorClass.TIMEOUT_ERROR,
                error_type="WallClockDeadlineExceeded",
                error_code="IMPROVEMENT_WALL_CLOCK_TIMEOUT",
            ),
            AttemptStatus.TECHNICAL_ERROR,
            elapsed,
        )
    if kind == "error":
        elapsed = max(0, int((time.perf_counter() - started) * 1000))
        return (
            None,
            None,
            ProviderDiagnostic(
                ProviderErrorClass.UNKNOWN_PROVIDER_ERROR,
                error_type=type(value).__name__,
                error_code="IMPROVEMENT_CALL_WRAPPER_ERROR",
            ),
            AttemptStatus.TECHNICAL_ERROR,
            elapsed,
        )
    return value


def _validate_partial_recommendations(
    improvement: Any,
    payload: Any,
    findings: list[dict[str, Any]],
    maximum: int,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate recommendations independently so one bad item cannot erase good output."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("recommendations"), list):
        return "", [], [{"finding_id": "", "reason": "invalid recommendation envelope", "raw": payload}]

    summary = str(payload.get("summary") or payload.get("ai_summary") or "").strip()
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in payload["recommendations"][: max(0, int(maximum))]:
        finding_id = str(raw.get("finding_id") or "") if isinstance(raw, Mapping) else ""
        if finding_id and finding_id in seen:
            rejected.append({"finding_id": finding_id, "reason": "duplicate finding_id", "raw": raw})
            continue
        candidate = dict(payload)
        candidate["recommendations"] = [raw]
        try:
            item_summary, normalized = improvement._validate_ai_payload(candidate, findings, 1)
            if not summary and item_summary:
                summary = str(item_summary)
            if not normalized:
                raise ValueError("recommendation normalized to empty result")
            item = normalized[0]
            normalized_id = str(item.get("finding_id") or finding_id)
            if normalized_id in seen:
                raise ValueError("duplicate finding_id")
            seen.add(normalized_id)
            accepted.append(item)
        except Exception as exc:
            rejected.append(
                {
                    "finding_id": finding_id,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "raw": dict(raw) if isinstance(raw, Mapping) else raw,
                }
            )
    return summary, accepted, rejected


def _repair_findings(
    findings: list[dict[str, Any]], rejected: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    ids = {str(item.get("finding_id") or "") for item in rejected if item.get("finding_id")}
    if not ids:
        return []
    return [item for item in findings if str(item.get("finding_id") or "") in ids]


def _required_missing_ymyl_findings(
    findings: Sequence[Mapping[str, Any]],
    accepted: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    accepted_ids = {
        str(item.get("finding_id") or "")
        for item in accepted
        if item.get("finding_id")
    }
    return [
        dict(item)
        for item in findings
        if str(item.get("source") or "").upper() == "SEMANTIC_COHERENCE_YMYL"
        and str(item.get("finding_id") or "")
        and str(item.get("finding_id")) not in accepted_ids
    ]


def _required_missing_actionable_findings(
    findings: Sequence[Mapping[str, Any]],
    accepted: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    from rasai.improvement_intelligence import _required_actionable_recommendation_finding_ids

    required=set(_required_actionable_recommendation_finding_ids(findings))
    accepted_ids={
        str(item.get("finding_id") or "")
        for item in accepted
        if item.get("finding_id")
    }
    return [
        dict(item)
        for item in findings
        if str(item.get("finding_id") or "") in required
        and str(item.get("finding_id") or "") not in accepted_ids
    ]


def _repair_scope_findings(
    findings: list[dict[str, Any]],
    rejected: Sequence[Mapping[str, Any]],
    accepted: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {
        str(item.get("finding_id")): item
        for item in _repair_findings(findings, rejected)
        if item.get("finding_id")
    }
    for item in _required_missing_ymyl_findings(findings, accepted):
        selected.setdefault(str(item.get("finding_id")), item)
    for item in _required_missing_actionable_findings(findings, accepted):
        selected.setdefault(str(item.get("finding_id")), item)
    return list(selected.values())


def _merge_recommendations(
    first: Sequence[Mapping[str, Any]], second: Sequence[Mapping[str, Any]], maximum: int
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in (*first, *second):
        item = dict(raw)
        fid = str(item.get("finding_id") or "")
        if fid and fid in seen:
            continue
        if fid:
            seen.add(fid)
        out.append(item)
        if len(out) >= maximum:
            break
    return out


def _attempt_with_summary(attempt: Any, *, summary: str) -> Any:
    try:
        return replace(attempt, request_message_summary=summary)
    except Exception:
        return attempt


def _install_improvement_runtime_patch() -> None:
    from rasai import ai_orchestration_unification as orchestration
    from rasai import improvement_intelligence as improvement
    from rasai.ai_resilience import (
        DECISION_FALLBACK,
        DECISION_FALLBACK_SUCCESS,
        DECISION_STOP,
        DECISION_SUCCESS,
        DECISION_SUCCESS_AFTER_RETRY,
    )
    from rasai.m18_ai import AttemptStatus, ProviderDiagnostic, ProviderErrorClass

    current = improvement._ai_analyze
    if getattr(current, "_rasai_partial_repair_v1", False):
        return

    def persist_attempt(
        *, provider: Any, index: int, started: Any, duration_ms: int, status: Any,
        diagnostic: Any, usage: Any, request_hash: str, context: Any, workspace: Any,
        audit_id: str, coordinator: Any, decision: str, summary: str,
        fallback_from: str | None = None, fallback_reason: str | None = None,
    ) -> Any:
        attempt = orchestration._attempt(
            provider,
            index=index,
            started=started,
            duration_ms=duration_ms,
            status=status,
            diagnostic=diagnostic,
            usage=usage,
            request_hash=request_hash,
            contract=improvement.CONTRACT_VERSION,
            url=context.url,
            snapshot_id=context.snapshot_id,
            decision=decision,
        )
        if fallback_from:
            attempt = replace(
                attempt,
                fallback_from_provider=fallback_from,
                fallback_reason=fallback_reason,
            )
        attempt = _attempt_with_summary(attempt, summary=summary)
        improvement._persist_attempt(workspace, audit_id, context, attempt)
        if coordinator is not None:
            coordinator.record_attempt(attempt, page_url=context.url, scope="IMPROVEMENT_INTELLIGENCE")
        return attempt

    def ai_analyze(
        *, audit_id: str, workspace: Any, context: Any, config: Any,
        findings: list[dict[str, Any]], evidence_context: Mapping[str, Any],
        language: str, progress: Any = None,
    ) -> tuple[str, list[dict[str, Any]], str | None]:
        runtime = improvement._build_provider(config)
        schema = improvement._schema(findings, config.max_recommendations)
        request_context, instructions = improvement.build_improvement_request_context(
            audit_id=audit_id,
            workspace=workspace,
            context=context,
            config=config,
            findings=findings,
            evidence_context=evidence_context,
            language=language,
        )
        user_text = "Persisted RASAi evidence for one URL:\n" + json.dumps(
            request_context, ensure_ascii=False, default=str
        )
        hint = orchestration._token_hint(
            user_text,
            output_tokens=min(8000, 1600 + config.max_recommendations * 180),
        )
        candidates = orchestration._provider_candidates(runtime, hint, scope="IMPROVEMENT_INTELLIGENCE")
        if not candidates:
            return "", [], (
                "AI_NOT_CONFIGURED" if str(config.provider or "").casefold() in {"", "none"}
                else "AI_PROVIDER_CHAIN_EXHAUSTED"
            )

        coordinator = getattr(runtime, "coordinator", None)
        last_reason: str | None = None
        fallback_from: str | None = None
        fallback_reason: str | None = None
        attempt_index = 0

        for ordinal, provider in enumerate(candidates, 1):
            if progress:
                progress(
                    "AI_ANALYSIS",
                    min(92.0, 72.0 + ordinal * 6.0),
                    f"consultando {provider.name}/{provider.model}; candidato {ordinal}/{len(candidates)}",
                )
            payload = orchestration._structured_payload(
                provider,
                schema_name="rasai_improvement_intelligence",
                instructions=instructions,
                user_text=user_text,
                schema=schema,
            )
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request_hash = orchestration.sha256(body).hexdigest()
            started = orchestration.datetime.now(orchestration.timezone.utc)
            attempt_index += 1
            raw, usage, diagnostic, status, duration_ms = _deadline_candidate_call(
                provider,
                body=body,
                timeout=float(config.timeout_seconds),
                candidate_call=orchestration._candidate_call,
            )

            ai_summary = ""
            accepted: list[dict[str, Any]] = []
            rejected: list[dict[str, Any]] = []
            if status is AttemptStatus.SUCCESS and raw is not None:
                try:
                    extracted = orchestration._provider_extract(provider, raw)
                    ai_summary, accepted, rejected = _validate_partial_recommendations(
                        improvement, extracted, findings, config.max_recommendations
                    )
                    if not accepted and rejected:
                        status = AttemptStatus.CONTRACT_ERROR
                        diagnostic = ProviderDiagnostic(
                            ProviderErrorClass.CONTRACT_ERROR,
                            error_type="PartialRecommendationValidation",
                            error_code="IMPROVEMENT_OUTPUT_INVALID",
                        )
                    elif rejected:
                        status = AttemptStatus.CONTRACT_ERROR
                        diagnostic = ProviderDiagnostic(
                            ProviderErrorClass.CONTRACT_ERROR,
                            error_type="PartialRecommendationValidation",
                            error_code="IMPROVEMENT_OUTPUT_PARTIAL",
                        )
                except Exception as exc:
                    status = AttemptStatus.CONTRACT_ERROR
                    diagnostic = ProviderDiagnostic(
                        ProviderErrorClass.CONTRACT_ERROR,
                        error_type=type(exc).__name__,
                        error_code="IMPROVEMENT_OUTPUT_INVALID",
                    )

            if accepted:
                initial_decision = "REPAIR_PARTIAL" if rejected else (
                    DECISION_FALLBACK_SUCCESS if fallback_from else DECISION_SUCCESS
                )
                persist_attempt(
                    provider=provider,
                    index=attempt_index,
                    started=started,
                    duration_ms=duration_ms,
                    status=status,
                    diagnostic=diagnostic,
                    usage=usage,
                    request_hash=request_hash,
                    context=context,
                    workspace=workspace,
                    audit_id=audit_id,
                    coordinator=coordinator,
                    decision=initial_decision,
                    summary=(
                        f"contract={improvement.CONTRACT_VERSION};findings={len(findings)};"
                        f"accepted={len(accepted)};rejected={len(rejected)};mode=initial"
                    ),
                    fallback_from=fallback_from,
                    fallback_reason=fallback_reason,
                )
                required_ymyl_missing = _required_missing_ymyl_findings(findings, accepted)
                required_actionable_missing = _required_missing_actionable_findings(findings, accepted)
                required_missing = [*required_ymyl_missing, *required_actionable_missing]
                if not rejected and not required_missing:
                    return ai_summary, accepted, None

                repair_findings = _repair_scope_findings(findings, rejected, accepted)
                if not repair_findings:
                    return (
                        ai_summary,
                        accepted,
                        f"PARTIAL_RECOMMENDATIONS:accepted={len(accepted)};rejected={len(rejected)};repair=not_addressable",
                    )

                repair_limit = min(
                    max(1, config.max_recommendations - len(accepted)), len(repair_findings)
                )
                repair_schema = improvement._schema(repair_findings, repair_limit)
                repair_context = {
                    "contract_version": improvement.CONTRACT_VERSION,
                    "repair_of_partial_response": True,
                    "required_ymyl_completion": bool(required_ymyl_missing),
                    "required_actionable_completion": bool(required_actionable_missing),
                    "target": request_context["target"],
                    "page": request_context["page"],
                    "findings": repair_findings,
                    "editorial_risk_context": request_context["editorial_risk_context"],
                    "governance": request_context["governance"],
                }
                repair_text = (
                    "Complete only the rejected recommendations and any required YMYL/actionable findings below. "
                    "Do not re-analyze or repeat findings that were already accepted. Use only evidence_ids "
                    "listed inside each supplied finding; never add another evidence id.\n"
                    + json.dumps(repair_context, ensure_ascii=False, default=str)
                )
                repair_instructions = (
                    instructions
                    + " This is a bounded repair pass for rejected items and required YMYL/actionable coverage. "
                    "Return exactly one recommendation for every supplied required finding and use only explicitly "
                    "listed evidence_ids. When an element-level accessibility fix can be illustrated safely, include "
                    "suggested_html or suggested_text plus a concrete verification step."
                )
                repair_payload = orchestration._structured_payload(
                    provider,
                    schema_name="rasai_improvement_intelligence_repair",
                    instructions=repair_instructions,
                    user_text=repair_text,
                    schema=repair_schema,
                )
                repair_body = json.dumps(
                    repair_payload, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                repair_hash = orchestration.sha256(repair_body).hexdigest()
                repair_timeout = min(
                    REPAIR_TIMEOUT_CAP_SECONDS,
                    max(15.0, float(config.timeout_seconds) * 0.25),
                )
                if progress:
                    progress(
                        "AI_ANALYSIS",
                        94.0,
                        f"completando {len(repair_findings)} item(ns) rejeitado(s); tentativa curta",
                    )
                repair_started = orchestration.datetime.now(orchestration.timezone.utc)
                attempt_index += 1
                repair_raw, repair_usage, repair_diag, repair_status, repair_duration = _deadline_candidate_call(
                    provider,
                    body=repair_body,
                    timeout=repair_timeout,
                    candidate_call=orchestration._candidate_call,
                )
                repaired: list[dict[str, Any]] = []
                still_rejected: list[dict[str, Any]] = list(rejected)
                repair_summary = ""
                if repair_status is AttemptStatus.SUCCESS and repair_raw is not None:
                    try:
                        repair_extracted = orchestration._provider_extract(provider, repair_raw)
                        repair_summary, repaired, still_rejected = _validate_partial_recommendations(
                            improvement, repair_extracted, repair_findings, repair_limit
                        )
                        expected_ids = {
                            str(item.get("finding_id") or "")
                            for item in repair_findings
                            if item.get("finding_id")
                        }
                        returned_ids = {
                            str(item.get("finding_id") or "")
                            for item in repaired
                            if item.get("finding_id")
                        }
                        for missing_id in sorted(expected_ids - returned_ids):
                            still_rejected.append({
                                "finding_id": missing_id,
                                "reason": "required repair recommendation omitted",
                            })
                        if still_rejected:
                            repair_status = AttemptStatus.CONTRACT_ERROR
                            repair_diag = ProviderDiagnostic(
                                ProviderErrorClass.CONTRACT_ERROR,
                                error_type="PartialRepairValidation",
                                error_code="IMPROVEMENT_REPAIR_PARTIAL",
                            )
                    except Exception as exc:
                        repair_status = AttemptStatus.CONTRACT_ERROR
                        repair_diag = ProviderDiagnostic(
                            ProviderErrorClass.CONTRACT_ERROR,
                            error_type=type(exc).__name__,
                            error_code="IMPROVEMENT_REPAIR_INVALID",
                        )
                        still_rejected = list(rejected)

                merged = _merge_recommendations(accepted, repaired, int(config.max_recommendations))
                repair_complete = bool(repaired) and not still_rejected
                persist_attempt(
                    provider=provider,
                    index=attempt_index,
                    started=repair_started,
                    duration_ms=repair_duration,
                    status=repair_status,
                    diagnostic=repair_diag,
                    usage=repair_usage,
                    request_hash=repair_hash,
                    context=context,
                    workspace=workspace,
                    audit_id=audit_id,
                    coordinator=coordinator,
                    decision=DECISION_SUCCESS_AFTER_RETRY if repair_complete else DECISION_STOP,
                    summary=(
                        f"contract={improvement.CONTRACT_VERSION};findings={len(repair_findings)};"
                        f"accepted={len(repaired)};rejected={len(still_rejected)};mode=partial-repair"
                    ),
                )
                if repair_complete:
                    return ai_summary or repair_summary, merged, None
                return (
                    ai_summary or repair_summary,
                    merged,
                    f"PARTIAL_RECOMMENDATIONS:accepted={len(merged)};"
                    f"rejected={len(still_rejected)};repair=bounded",
                )

            decision = DECISION_FALLBACK if ordinal < len(candidates) else DECISION_STOP
            persist_attempt(
                provider=provider,
                index=attempt_index,
                started=started,
                duration_ms=duration_ms,
                status=status,
                diagnostic=diagnostic,
                usage=usage,
                request_hash=request_hash,
                context=context,
                workspace=workspace,
                audit_id=audit_id,
                coordinator=coordinator,
                decision=decision,
                summary=(
                    f"contract={improvement.CONTRACT_VERSION};findings={len(findings)};"
                    "accepted=0;mode=initial"
                ),
                fallback_from=fallback_from,
                fallback_reason=fallback_reason,
            )
            last_reason = diagnostic.reason if diagnostic is not None else "AI_PROVIDER_UNAVAILABLE"
            fallback_from = str(provider.name)
            fallback_reason = last_reason

        return "", [], last_reason or "AI_PROVIDER_CHAIN_EXHAUSTED"

    ai_analyze._rasai_partial_repair_v1 = True
    ai_analyze._rasai_original = current
    improvement._ai_analyze = ai_analyze


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, name: str) -> set[str]:
    if not _table_exists(connection, name):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({name})")}


def _rows(connection: sqlite3.Connection, table: str, audit_id: str) -> list[dict[str, Any]]:
    if not _table_exists(connection, table) or "audit_id" not in _columns(connection, table):
        return []
    try:
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table} WHERE audit_id=?", (audit_id,)).fetchall()]
    except sqlite3.Error:
        return []


def _serp_completion_reason(observation: Mapping[str, Any], result_count: int) -> str:
    try:
        requested = int(observation.get("requested_depth") or 0)
    except (TypeError, ValueError):
        requested = 0
    if requested and result_count >= requested:
        return "Profundidade solicitada atingida"
    quality = _safe_json(observation.get("quality_metadata"), {})
    if isinstance(quality, Mapping):
        if quality.get("pagination_ended_before_requested_depth"):
            return "Provider encerrou a paginação antes da profundidade solicitada"
        if quality.get("request_budget_ended_before_requested_depth"):
            return "Limite de requisições encerrou a coleta antes da profundidade solicitada"
    if observation.get("error_code") or observation.get("error_message"):
        return "Coleta encerrada com diagnóstico do provider"
    if requested and result_count < requested:
        return "Provider retornou menos resultados que a profundidade solicitada"
    return "Coleta concluída"


def _search_intelligence_html(database: Any, data: Any) -> str:
    from rasai import catalog_report_metrics as m

    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        observations = m._audit_rows(con, "serp_observations", data.audit_id)
        result_cols = m._columns(con, "serp_results")
        rows: list[Sequence[Any]] = []
        modals: list[str] = []
        for index, obs in enumerate(observations, 1):
            oid = obs.get("observation_id")
            results: list[dict[str, Any]] = []
            if oid and _table_exists(con, "serp_results") and "observation_id" in result_cols:
                results = m._dict_rows(
                    m._rows(con, "SELECT * FROM serp_results WHERE observation_id=? ORDER BY position", (oid,))
                )
            positions: list[int] = []
            for result in results:
                try:
                    positions.append(int(result.get("position")))
                except (TypeError, ValueError):
                    pass
            modal_id = f"serp-{index}"
            device = m._device_label(obs.get("device")) if obs.get("device") else "-"
            position = f"{min(positions)} a {max(positions)}" if positions else "-"
            reason = _serp_completion_reason(obs, len(results))
            rows.append((
                obs.get("query") or "-", obs.get("region") or "-", device,
                len(results), position, reason, m._modal_button(modal_id, "Ver observação")
            ))
            result_rows = [
                (r.get("position") or "-", r.get("title") or "-", r.get("url") or "-")
                for r in results[:50]
            ]
            body = m._kv((
                ("Consulta", obs.get("query") or "-"),
                ("Região", obs.get("region") or "-"),
                ("Dispositivo", device),
                ("Profundidade solicitada", obs.get("requested_depth") or "-"),
                ("Resultados persistidos", len(results)),
            ))
            body += "<h3>Resultados persistidos</h3>" + m._table(
                ("Posição", "Título", "URL"), result_rows,
                empty="Nenhum resultado individual persistido para esta observação."
            )
            modals.append(m._modal(
                modal_id, "Observação de busca", str(obs.get("query") or "Consulta SERP"), body
            ))
        return m._table(
            ("Consulta", "Região", "Dispositivo", "Resultados", "Posições", "Motivo", "Detalhe"),
            rows, empty="Nenhuma observação SERP persistida.", sortable=bool(rows)
        ) + "".join(modals)
    finally:
        con.close()


_LIGHTHOUSE_PT: tuple[tuple[str, str], ...] = (
    ("low-contrast text is difficult or impossible", "Contraste insuficiente entre texto e plano de fundo"),
    ("background and foreground colors do not have a sufficient contrast ratio", "Contraste insuficiente entre texto e plano de fundo"),
    ("links do not have a discernible name", "Links sem nome acessível identificável"),
    ("avoid enormous network payloads", "Evitar payloads de rede excessivamente grandes"),
    ("document request latency", "Latência de requisições precisa de atenção"),
    ("legacy javascript", "JavaScript legado identificado"),
    ("render-blocking requests", "Requisições estão bloqueando a renderização"),
    ("accessibility tree is not well-formed", "Árvore de acessibilidade malformada"),
    ("browser errors were logged to the console", "Erros do navegador foram registrados no console"),
    ("displays images with incorrect aspect ratio", "Imagens exibidas com proporção incorreta"),
    ("missing source maps for large first-party javascript", "Source maps ausentes para JavaScript first-party de grande porte"),
    ("heading elements are not in a sequentially-descending order", "A hierarquia de títulos (headings) não segue uma ordem sequencial"),
    ("elements with role=\"dialog\"", "Diálogo sem nome acessível ou associação ARIA suficiente"),
    ("elements with role='dialog'", "Diálogo sem nome acessível ou associação ARIA suficiente"),
    ("image elements do not have", "Imagem sem texto alternativo adequado"),
    ("canonical", "Declaração de URL canônica ausente, conflitante ou inadequada"),
    ("largest contentful paint", "Largest Contentful Paint (LCP) precisa de melhoria"),
    ("reduce unused javascript", "JavaScript não utilizado está aumentando o custo de carregamento"),
    ("unused javascript", "JavaScript não utilizado está aumentando o custo de carregamento"),
    ("total byte weight", "Peso total transferido pela página está elevado"),
    ("aria", "Problema de semântica ou atributo ARIA identificado"),
)


def _finding_public_title(finding: Mapping[str, Any]) -> str:
    original = str(finding.get("title") or finding.get("observation") or "Problema identificado").strip()
    haystack = " ".join(
        str(finding.get(key) or "") for key in ("title", "observation", "source", "evidence_ids_json")
    ).casefold()
    for token, translated in _LIGHTHOUSE_PT:
        if token.casefold() in haystack:
            return translated
    return original


def _extract_urls(text: Any) -> list[str]:
    found: list[str] = []
    for raw in re.findall(r"https?://[^\s<>'\"]+", str(text or "")):
        url = raw.rstrip(".,);]")
        if url not in found:
            found.append(url)
    return found[:6]


def _technical_reference_links(domain: str = "", rule_id: str = "", source_text: str = "") -> str:
    domain = str(domain or "").upper()
    rule_id = str(rule_id or "").upper()
    links: list[tuple[str, str]] = []
    for url in _extract_urls(source_text):
        links.append(("Referência informada pela fonte", url))
    if domain == "ACCESSIBILITY":
        links.append(("W3C WAI · ARIA/WCAG", "https://www.w3.org/WAI/standards-guidelines/"))
    elif domain == "PERFORMANCE":
        links.append(("web.dev · Performance", "https://web.dev/learn/performance/"))
    elif domain == "SEMANTICS_STRUCTURE":
        links.append(("MDN · HTML", "https://developer.mozilla.org/docs/Web/HTML"))
    elif domain == "FILES_DISCOVERY":
        links.append(("Google Search Central · Crawling", "https://developers.google.com/search/docs/crawling-indexing/overview"))
    elif domain == "SEARCH_RANKING" or rule_id in {"BR-GEO-013", "BR-GEO-014"}:
        links.append(("Google Search Central · Canonicalização", "https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls"))
    elif domain in {"CONTENT", "AI_ACCESS"}:
        links.append(("Google Search Central · Conteúdo útil", "https://developers.google.com/search/docs/fundamentals/creating-helpful-content"))
    if "JSON-LD" in str(source_text).upper() or domain == "SEMANTICS_STRUCTURE":
        links.append(("Schema.org", "https://schema.org/docs/documents.html"))
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, url in links:
        if url in seen:
            continue
        seen.add(url)
        unique.append((label, url))
    if not unique:
        return ""
    items = "".join(
        f"<li><a href='{escape(url)}' target='_blank' rel='noopener noreferrer'>{escape(label)}</a></li>"
        for label, url in unique
    )
    return "<h3>Referências técnicas</h3><ul>" + items + "</ul>"


def _coverage_by_finding(connection: sqlite3.Connection, audit_id: str) -> dict[str, set[str]]:
    coverage: dict[str, set[str]] = {}
    def add(fid: Any, label: str) -> None:
        token = str(fid or "").strip()
        if token:
            coverage.setdefault(token, set()).add(label)
    for row in _rows(connection, "improvement_intelligence_recommendations", audit_id):
        add(row.get("finding_id") or row.get("source_finding_id"), "IA · análise profunda")
    for table, label in (
        ("content_remediation_suggestions", "IA · conteúdo"),
        ("jsonld_remediation_suggestions", "Dados estruturados"),
    ):
        for row in _rows(connection, table, audit_id):
            add(row.get("finding_id") or row.get("source_finding_id"), label)
    groups = {
        str(row.get("group_id")): row for row in _rows(connection, "remediation_groups", audit_id)
        if row.get("group_id")
    }
    for row in _rows(connection, "recommendations", audit_id):
        if row.get("finding_id"):
            add(row.get("finding_id"), "Determinística")
        group = groups.get(str(row.get("remediation_group_id") or ""))
        if group:
            for fid in _safe_json(group.get("affected_findings"), []):
                add(fid, "Determinística")
    return coverage


def _cell_html(cell: Any) -> str:
    if cell is None:
        return "-"
    if cell.__class__.__name__ == "_Html":
        return str(cell)
    return escape(str(cell))


def _filterable_findings_table(
    headers: Sequence[str], rows: Sequence[tuple[Sequence[Any], Mapping[str, str]]], *, table_id: str,
) -> str:
    if not rows:
        return "<div class='notice'>A análise foi concluída sem materializar problemas correlacionados.</div>"
    domains = sorted({meta.get("domain", "") for _, meta in rows if meta.get("domain")})
    severities = sorted({meta.get("severity", "") for _, meta in rows if meta.get("severity")})
    domain_options = "".join(f"<option value='{escape(v)}'>{escape(v)}</option>" for v in domains)
    severity_options = "".join(f"<option value='{escape(v)}'>{escape(v)}</option>" for v in severities)
    controls = f"""
<div class='grid' data-filters-for='{escape(table_id)}'>
  <label>Domínio<select data-filter-domain><option value=''>Todos</option>{domain_options}</select></label>
  <label>Severidade<select data-filter-severity><option value=''>Todas</option>{severity_options}</select></label>
  <label>Cobertura de remediação<select data-filter-remediation><option value=''>Todas</option><option value='com'>Com remediação</option><option value='sem'>Sem remediação</option></select></label>
  <div><button type='button' class='action' data-filter-clear>Limpar filtros</button></div>
</div>
"""
    head = "".join(f"<th>{escape(str(item))}</th>" for item in headers)
    body_parts: list[str] = []
    for cells, meta in rows:
        attrs = " ".join(f"data-{key}='{escape(str(value))}'" for key, value in meta.items())
        body_parts.append(f"<tr {attrs}>" + "".join(f"<td>{_cell_html(cell)}</td>" for cell in cells) + "</tr>")
    table = (
        f"<div class='table-wrap'><table id='{escape(table_id)}'><thead><tr>{head}</tr></thead><tbody>{''.join(body_parts)}</tbody></table></div>"
        "<div class='table-controls'><button type='button' data-local-prev>Página anterior</button>"
        "<span class='table-page-info' data-local-info></span>"
        "<button type='button' data-local-next>Próxima página</button></div>"
    )
    script = f"""
<script>(()=>{{
const table=document.getElementById({json.dumps(table_id)}); if(!table)return;
const controls=document.querySelector(`[data-filters-for={json.dumps(table_id)}]`); if(!controls)return;
const all=Array.from(table.tBodies[0].rows); let rows=all.slice(); let page=1; const size=10;
let sortIndex=-1,sortDirection=1;
const nav=table.closest('.table-wrap').nextElementSibling; const info=nav.querySelector('[data-local-info]'); const prev=nav.querySelector('[data-local-prev]'); const next=nav.querySelector('[data-local-next]');
const norm=(v)=>(v||'').trim().toLocaleLowerCase('pt-BR');
const render=()=>{{all.forEach(row=>row.style.display='none');const pages=Math.max(1,Math.ceil(rows.length/size));page=Math.min(Math.max(page,1),pages);const start=(page-1)*size;rows.slice(start,start+size).forEach(row=>row.style.display='table-row');info.textContent=`Página ${{page}} de ${{pages}} · ${{rows.length}} registro(s)`;prev.disabled=page<=1;next.disabled=page>=pages;}};
const apply=()=>{{const d=controls.querySelector('[data-filter-domain]').value;const s=controls.querySelector('[data-filter-severity]').value;const r=controls.querySelector('[data-filter-remediation]').value;rows=all.filter(row=>(!d||row.dataset.domain===d)&&(!s||row.dataset.severity===s)&&(!r||row.dataset.remediation===r));if(sortIndex>=0)rows.sort((a,b)=>norm(a.cells[sortIndex]?.innerText).localeCompare(norm(b.cells[sortIndex]?.innerText),'pt-BR',{{numeric:true}})*sortDirection);page=1;render();}};
controls.querySelectorAll('select').forEach(el=>el.addEventListener('change',apply));controls.querySelector('[data-filter-clear]').addEventListener('click',()=>{{controls.querySelectorAll('select').forEach(el=>el.value='');apply();}});prev.addEventListener('click',()=>{{page--;render();}});next.addEventListener('click',()=>{{page++;render();}});Array.from(table.tHead.rows[0].cells).forEach((th,index)=>th.addEventListener('click',()=>{{sortDirection=sortIndex===index?-sortDirection:1;sortIndex=index;rows.sort((a,b)=>norm(a.cells[index]?.innerText).localeCompare(norm(b.cells[index]?.innerText),'pt-BR',{{numeric:true}})*sortDirection);page=1;render();}}));apply();
}})();</script>
"""
    return controls + table + script


def _ymyl_analysis_context_html(database: Any, audit_id: str, a: Any) -> str:
    from rasai.editorial_risk_context import build_editorial_risk_context

    context = build_editorial_risk_context(database, audit_id)
    ymyl = context.get("ymyl", {})
    if not isinstance(ymyl, Mapping) or not bool(ymyl.get("active")):
        return ""

    relation = ymyl.get("configuration_relation") or {}
    configured = ymyl.get("configured_category") or "auto"
    effective = ymyl.get("effective_category") or "auto"
    interpretation = context.get("auto_interpretations", {}).get("ymyl_category", {})
    origin = (
        "Inferência de IA desta execução"
        if isinstance(interpretation, Mapping)
        and str(interpretation.get("status") or "").upper() == "INTERPRETED"
        else "Configuração declarada / não determinável"
    )

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        findings = _rows(connection, "improvement_intelligence_findings", audit_id)
        recommendations = _rows(connection, "improvement_intelligence_recommendations", audit_id)
        coverage = _coverage_by_finding(connection, audit_id)
    finally:
        connection.close()

    recommendation_by_finding={
        str(item.get("finding_id")): item
        for item in recommendations
        if item.get("finding_id")
    }
    criterion_findings: dict[str, str] = {}
    for finding in findings:
        fid = str(finding.get("finding_id") or "")
        if not fid.startswith("SEMANTIC-YMYL:"):
            continue
        parts = fid.split(":")
        if len(parts) >= 2:
            criterion_findings[parts[1]] = fid

    top_rows = (
        ("Perfil de risco efetivo", ymyl.get("effective_risk_profile") or "-"),
        ("Categoria YMYL configurada", configured),
        ("Categoria YMYL efetiva", effective),
        ("Origem da categoria efetiva", origin),
        ("Relação com a parametrização do usuário", relation.get("label") or "Não determinável"),
        ("Conclusão conteúdo × YMYL", ymyl.get("alignment_label") or "-"),
        ("Necessidade de mudança no conteúdo", ymyl.get("content_change_label") or "Não determinável"),
    )

    criterion_labels = {
        "SC-P11": "Suporte observável de claims",
        "SC-P12": "Autoria e responsabilidade",
        "SC-P13": "Atualização e sensibilidade temporal",
    }
    detail_rows: list[tuple[Any, ...]] = []
    detail_modals: list[str] = []
    for item in sorted(
        ymyl.get("coherence", []) or [],
        key=lambda value: (str(value.get("criterion_id") or ""), str(value.get("page_url") or "")),
    ):
        criterion = str(item.get("criterion_id") or "")
        result = str(item.get("result") or "NOT_DETERMINABLE").upper()
        fid = criterion_findings.get(criterion)
        remediation = sorted(coverage.get(fid, set())) if fid else []
        if result in {"PARTIAL", "INCOHERENT"}:
            action = "Mudança recomendada" if remediation else "Remediação necessária ainda sem ação individual"
        elif result in {"COHERENT", "NOT_APPLICABLE"}:
            action = "Nenhuma mudança indicada por este critério"
        else:
            action = "Sem conclusão suficiente para exigir mudança"
        remediation_cell: Any = " · ".join(remediation) if remediation else "-"
        if remediation:
            remediation_cell = a._Html(
                escape(" · ".join(remediation))
                + " - <a href='cat-09.html'>ver CAT-09</a>"
            )
        rec=recommendation_by_finding.get(str(fid or ""))
        orientation=rec.get("recommendation") or rec.get("title") if rec else "-"
        detail_cell: Any="-"
        if rec:
            modal_id=f"ymyl-remediation-{criterion.casefold()}-{len(detail_modals)+1}"
            detail_body=a._kv((
                ("Critério",f"{criterion} - {criterion_labels.get(criterion, 'Critério YMYL')}"),
                ("Orientação da IA",rec.get("recommendation") or rec.get("title") or "-"),
                ("Onde aplicar",rec.get("selector") or "Conteúdo/página relacionada à evidência persistida"),
                ("Racional",rec.get("rationale") or "-"),
                ("Confiança",a._confidence_label(rec.get("confidence"))),
            ))
            if rec.get("suggested_html"):
                detail_body+="<h3>Exemplo técnico sugerido</h3><div class='pre'>"+escape(str(rec.get("suggested_html")))+"</div>"
            if rec.get("suggested_text"):
                detail_body+="<h3>Texto sugerido</h3><div class='pre rich-text'>"+str(a._rich_text(rec.get("suggested_text")))+"</div>"
            if rec.get("verification"):
                detail_body+="<h3>Como validar a correção</h3><p>"+str(a._rich_text(rec.get("verification")))+"</p>"
            detail_body+="<p><a href='cat-09.html'>Ver implementação consolidada no CAT-09</a></p>"
            detail_cell=a._modal_button(modal_id,"Ver orientação e exemplo")
            detail_modals.append(a._modal(modal_id,"Remediação YMYL orientada pela IA",criterion,detail_body))
        detail_rows.append(
            (
                f"{criterion} - {criterion_labels.get(criterion, 'Critério YMYL')}",
                a._status_label(result),
                a._confidence_label(item.get("confidence")),
                item.get("reasoning_summary") or item.get("observed_context") or "-",
                action,
                orientation,
                remediation_cell,
                detail_cell,
            )
        )

    if bool(relation.get("conflict")):
        explanation = (
            "<div class='notice warn'><strong>Parametrização × interpretação:</strong> "
            "há divergência material entre a configuração canônica e o contexto efetivo. "
            "O RASAi não substitui a parametrização; exige revisão humana antes de tratá-la como mudança de conteúdo.</div>"
        )
    else:
        explanation = (
            "<div class='notice'><strong>Parametrização × interpretação:</strong> "
            + escape(str(relation.get("label") or "A configuração canônica foi preservada."))
            + " Portanto, eventuais mudanças recomendadas abaixo decorrem de lacunas observadas no conteúdo, "
            "não de a IA ter sobrescrito ou rejeitado a parametrização do usuário.</div>"
        )

    detail_html = (
        a._table(
            ("Critério", "Resultado", "Confiança", "Motivo observado", "Implicação", "Orientação da IA", "Remediação", "Detalhe"),
            detail_rows,
            sortable=bool(detail_rows),
            page_size=10 if len(detail_rows) > 10 else None,
        )
        if detail_rows
        else "<div class='notice'>Nenhum critério YMYL persistido foi suficiente para concluir aderência ou necessidade de mudança.</div>"
    )
    return (
        "<div class='subsection'><h3>Contexto YMYL aplicado à análise profunda</h3>"
        + a._table(("Leitura", "Resultado"), top_rows)
        + explanation
        + "<h4>Por que o conteúdo está aderente, parcial ou incoerente</h4>"
        + detail_html
        + "".join(detail_modals)
        + "<p class='muted'>SC-P11, SC-P12 e SC-P13 são avaliados contra evidência observada. "
        "A conclusão não declara conformidade legal/regulatória. Findings YMYL parciais ou incoerentes "
        "são obrigatórios no pedido de remediação da análise profunda e devem chegar ao CAT-09 quando acionáveis.</p></div>"
    )

def _improvement_html(database: Any, data: Any) -> str:
    from rasai import catalog_report_analysis as a
    con = sqlite3.connect(database); con.row_factory = sqlite3.Row
    try:
        run = a._last(con, "improvement_intelligence_runs", data.audit_id)
        findings = a._audit_rows(con, "improvement_intelligence_findings", data.audit_id)
        recs = a._audit_rows(con, "improvement_intelligence_recommendations", data.audit_id)
        coverage = _coverage_by_finding(con, data.audit_id)
    finally:
        con.close()
    if not run:
        return "<div class='notice bad'><strong>Resultado funcional ausente:</strong> a análise profunda foi solicitada, mas o resultado consolidado não está persistido.</div>"
    status = a._norm(run.get("status"))
    if status not in a._STATUS_SUCCESS and not findings:
        return "<div class='metric-grid'>" + a._metric("Estado da análise", a._status_label(run.get("status"))) + a._metric("Problemas persistidos", 0) + a._metric("Recomendações persistidas", 0) + "</div>"
    rec_by_finding = {str(r.get("finding_id")): r for r in recs if r.get("finding_id")}
    filter_rows: list[tuple[Sequence[Any], Mapping[str, str]]] = []
    modals: list[str] = []
    distribution: dict[str, int] = {}
    for index, finding in enumerate(findings, 1):
        fid = str(finding.get("finding_id") or "")
        rec = rec_by_finding.get(fid)
        domain = a._norm(finding.get("domain")); distribution[domain] = distribution.get(domain, 0) + 1
        source_cat = a._DOMAIN_CATALOG.get(domain); modal_id = f"improvement-{index}"
        reference = a._Html(f"<a class='ref' href='{a.CATALOG_PAGE_BY_ID[source_cat].filename}'>Origem: {source_cat}</a>") if source_cat in a.CATALOG_PAGE_BY_ID else "-"
        labels = sorted(coverage.get(fid, set())); coverage_label = " · ".join(labels) if labels else "Não disponível"
        public_title = _finding_public_title(finding); severity = a._level_label(finding.get("severity"))
        original_problem = str(finding.get("observation") or finding.get("title") or "-")
        original_title = str(finding.get("title") or original_problem)
        public_title_cell = a._translated_text(public_title, original_title) if public_title != original_title else public_title
        filter_rows.append(((public_title_cell, a._domain_label(domain), severity, coverage_label, reference, a._modal_button(modal_id, "Ver análise")), {"domain": a._domain_label(domain), "severity": severity, "remediation": "com" if labels else "sem"}))
        body = a._kv((("Problema", public_title), ("Domínio", a._domain_label(domain)), ("Severidade", severity), ("Fonte", finding.get("source") or "-"), ("Catálogo de origem", source_cat or "-"), ("Seletor / path", finding.get("selector") or "Não se aplica / não identificado"), ("Cobertura de remediação", coverage_label)))
        if public_title != original_problem:
            body += "<h3>Texto original da fonte</h3><div class='pre rich-text'>" + str(a._rich_text(original_problem)) + "</div>"
        if finding.get("original_html"):
            body += "<h3>Trecho observado</h3><div class='pre'>" + escape(str(finding.get("original_html"))) + "</div>"
        evidence = a._safe_json(finding.get("evidence_ids_json"), [])
        if isinstance(evidence, list) and evidence:
            body += "<h3>Evidências vinculadas</h3><p>" + escape(" · ".join(str(v) for v in evidence)) + "</p>"
        if rec:
            body += "<h3>Melhoria recomendada</h3><p>" + str(a._rich_text(rec.get("recommendation") or rec.get("title") or "-")) + "</p>"
            if rec.get("rationale"):
                body += "<h3>Por que esta correção é recomendada</h3><p>" + str(a._rich_text(rec.get("rationale"))) + "</p>"
            if rec.get("suggested_html"):
                body += "<h3>Exemplo técnico sugerido pela IA</h3><div class='pre'>" + escape(str(rec.get("suggested_html"))) + "</div>"
            if rec.get("suggested_text"):
                body += "<h3>Texto / exemplo sugerido pela IA</h3><div class='pre rich-text'>" + str(a._rich_text(rec.get("suggested_text"))) + "</div>"
            if rec.get("verification"):
                body += "<h3>Como validar a correção</h3><p>" + str(a._rich_text(rec.get("verification"))) + "</p>"
            body += "<p><a href='cat-09.html'>Ver implementação no CAT-09</a></p>"
        else:
            body += "<div class='notice'>Não há recomendação individual do Improvement Intelligence para este finding. Outras camadas de remediação, quando existentes, são indicadas na cobertura acima.</div>"
        body += _technical_reference_links(domain, source_text=original_problem)
        modals.append(a._modal(modal_id, public_title, f"Análise profunda · {source_cat or 'evidência transversal'}", body))
    unique_recs = len({str(r.get("finding_id")) for r in recs if r.get("finding_id")}); without = max(0, len(findings) - unique_recs)
    intro = _ymyl_analysis_context_html(database, data.audit_id, a) + "<div class='metric-grid'>" + a._metric("Problemas correlacionados", len(findings)) + a._metric("Melhorias da análise profunda", len(recs)) + a._metric("Achados sem recomendação individual da análise profunda", without) + a._metric("Estado", a._status_label(run.get("status"))) + a._metric("Idioma da análise", run.get("analysis_language") or run.get("language") or "-") + "</div>"
    maximum = run.get("max_recommendations")
    if maximum and len(findings) > len(recs):
        intro += f"<div class='notice'><strong>Cobertura da análise profunda:</strong> a execução correlacionou {len(findings)} problema(s) e foi configurada para no máximo {int(maximum)} recomendações. A coluna de cobertura também considera remediações persistidas por outras camadas do CAT-09.</div>"
    if distribution:
        intro += "<details><summary>Distribuição dos problemas por domínio</summary><div class='detail-body'>" + a._table(("Domínio", "Problemas"), [(a._domain_label(k), v) for k, v in sorted(distribution.items())]) + "</div></details>"
    summary = run.get("ai_summary") or run.get("summary")
    if summary:
        intro += f"<div class='notice'><strong>Síntese da análise:</strong> {escape(str(summary))}</div>"
    return intro + _filterable_findings_table(("Problema", "Domínio", "Severidade", "Cobertura de remediação", "Referência", "Detalhe"), filter_rows, table_id="cat08-findings") + "".join(modals)


def _group_findings(group: Mapping[str, Any] | None) -> list[str]:
    if not group:
        return []
    raw = _safe_json(group.get("affected_findings"), [])
    return [str(value) for value in raw if str(value)] if isinstance(raw, list) else []


def _root_for_recommendation(rec: Mapping[str, Any], root_by_find: Mapping[str, Mapping[str, Any]], group_by_id: Mapping[str, Mapping[str, Any]]) -> tuple[Mapping[str, Any], list[str], Mapping[str, Any] | None]:
    direct = str(rec.get("finding_id") or "")
    if direct and direct in root_by_find:
        return root_by_find[direct], [direct], None
    group = group_by_id.get(str(rec.get("remediation_group_id") or "")); finding_ids = _group_findings(group)
    for fid in finding_ids:
        if fid in root_by_find:
            return root_by_find[fid], finding_ids, group
    return {}, finding_ids, group


def _render_observed_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    parsed = _safe_json(value, value)
    text = json.dumps(parsed, ensure_ascii=False, indent=2) if isinstance(parsed, (dict, list)) else str(parsed)
    if len(text) > 6000:
        text = text[:6000] + "\n… trecho limitado pelo relatório …"
    return "<h3>Trecho / valor observado</h3><div class='pre'>" + escape(text) + "</div>"


def _w3c_remediation_html(database: Any, audit_id: str, a: Any) -> tuple[list[Sequence[Any]], list[str]]:
    """Project persisted W3C failures into CAT-09 without changing diagnostic ownership."""
    from rasai.execution_consistency_runtime import _w3c_fix_hint

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        metrics = a._audit_rows(connection, "standards_metric_observations", audit_id)
    finally:
        connection.close()

    rows: list[Sequence[Any]] = []
    modals: list[str] = []
    wanted = {
        "w3c_html_conformance": ("Conformidade HTML W3C", False),
        "w3c_css_conformance": ("Conformidade CSS W3C", True),
    }
    for index, item in enumerate(metrics, 1):
        metric_id = str(item.get("metric_id") or item.get("metric_key") or "")
        if metric_id not in wanted:
            continue
        title, css = wanted[metric_id]
        try:
            errors = int(float(item.get("value") or 0))
        except (TypeError, ValueError):
            errors = 0
        state = str(item.get("state") or item.get("status") or "").upper()
        if errors <= 0 and state not in {"FAIL", "FAILED", "ERROR", "UNAVAILABLE"}:
            continue

        details = _safe_json(item.get("details_json"), {})
        if not isinstance(details, Mapping):
            details = {}
        diagnostic_rows: list[tuple[Any, ...]] = []
        if css:
            raw_rows = details.get("error_details") if isinstance(details.get("error_details"), list) else []
            for raw in raw_rows:
                if not isinstance(raw, Mapping):
                    continue
                location = f"Linha {raw.get('line')}" if raw.get("line") not in (None, "") else "-"
                message = raw.get("message") or raw.get("type") or "Erro CSS informado pelo W3C"
                context = raw.get("context") or raw.get("skipped_string") or "-"
                diagnostic_rows.append((location, message, context, _w3c_fix_hint(message, css=True)))
        else:
            raw_rows = details.get("messages") if isinstance(details.get("messages"), list) else []
            for raw in raw_rows:
                if not isinstance(raw, Mapping) or str(raw.get("type") or "") == "info":
                    continue
                line = raw.get("first_line") or raw.get("last_line")
                column = raw.get("first_column") or raw.get("last_column")
                location = (
                    f"Linha {line}, coluna {column}"
                    if line not in (None, "") and column not in (None, "")
                    else f"Linha {line}" if line not in (None, "") else "-"
                )
                message = raw.get("message") or "Erro HTML informado pelo W3C"
                diagnostic_rows.append((location, message, raw.get("extract") or "-", _w3c_fix_hint(message)))

        criterion = (
            "W3C CSS Validator com valid=true e 0 erros CSS."
            if css
            else "W3C Nu Checker com 0 erros HTML e 0 erros de documento."
        )
        modal_id = f"rem-w3c-{index}"
        rows.append((
            f"Corrigir {title}",
            "Padrões web",
            "Alta" if errors else "-",
            "CAT-01 - padrões e validação W3C",
            a._modal_button(modal_id, "Ver erros e correção"),
        ))
        body = a._kv((
            ("Diagnóstico", title),
            ("Estado observado", a._status_label(item.get("state") or item.get("status"))),
            ("Erros persistidos", errors),
            ("Alvo validado", item.get("target") or "-"),
            ("Fonte", item.get("source") or "-"),
            ("Metodologia", item.get("methodology") or "-"),
            ("Identificador técnico", metric_id),
            ("Critério de aceite", criterion),
        ))
        if diagnostic_rows:
            body += "<h3>Erros que precisam ser corrigidos</h3>" + a._table(
                ("Localização", "Mensagem original", "Trecho / contexto", "Orientação técnica"),
                diagnostic_rows,
                sortable=bool(diagnostic_rows),
                page_size=10 if len(diagnostic_rows) > 10 else None,
            )
            body += (
                "<div class='notice'><strong>Passo a passo:</strong> corrija os itens listados no código-fonte, "
                "publique a alteração e execute novamente a validação W3C. O item só deve ser considerado resolvido "
                "quando o validator atingir o critério de aceite acima.</div>"
            )
        elif errors:
            body += (
                "<div class='notice warn'><strong>Detalhe individual não materializado nesta AUD:</strong> "
                "a contagem de erros foi persistida, mas as mensagens individuais não estão disponíveis. "
                "Reexecute a validação W3C com a versão atual para obter localização, trecho e orientação por erro.</div>"
            )
        body += (
            "<p class='muted'>Esta remediação é determinística e deriva diretamente do resultado do validator W3C. "
            "Não é inferência da IA e não altera retroativamente a evidência do CAT-03.</p>"
        )
        modals.append(a._modal(modal_id, f"Remediação - {title}", str(item.get("target") or "Validação W3C"), body))
    return rows, modals


def _remediation_html(database: Any, data: Any) -> str:
    from rasai import catalog_report_analysis as a
    con = sqlite3.connect(database); con.row_factory = sqlite3.Row
    try:
        roots = a._audit_rows(con, "root_cause_analyses", data.audit_id)
        deterministic = a._audit_rows(con, "recommendations", data.audit_id)
        groups = a._audit_rows(con, "remediation_groups", data.audit_id)
        core_findings = a._audit_rows(con, "findings", data.audit_id)
        content = a._audit_rows(con, "content_remediation_suggestions", data.audit_id)
        jsonld = a._audit_rows(con, "jsonld_remediation_suggestions", data.audit_id)
        deep = a._audit_rows(con, "improvement_intelligence_recommendations", data.audit_id)
        deep_findings = a._audit_rows(con, "improvement_intelligence_findings", data.audit_id)
        deep_run = a._last(con, "improvement_intelligence_runs", data.audit_id)
    finally:
        con.close()
    ai_discovery, policy_note = a._m24_ai_guidance(database, data.audit_id)
    rows: list[Sequence[Any]] = []; modals: list[str] = []; index = 0
    w3c_rows, w3c_modals = _w3c_remediation_html(database, data.audit_id, a)
    rows.extend(w3c_rows)
    modals.extend(w3c_modals)
    root_by_find = {str(row.get("finding_id")): row for row in roots if row.get("finding_id")}
    group_by_id = {str(row.get("group_id")): row for row in groups if row.get("group_id")}
    core_finding_by_id = {str(row.get("finding_id")): row for row in core_findings if row.get("finding_id")}
    deep_finding_by_id = {str(row.get("finding_id")): row for row in deep_findings if row.get("finding_id")}
    covered = {str(row.get("finding_id")) for row in deep if row.get("finding_id")}
    ai_codes = {str(item.get("diagnostic_code") or "") for item in ai_discovery}; suppressed_rules: set[str] = set()
    if "M24-ROBOTS-ABSENT" in ai_codes: suppressed_rules.update({"BR-GEO-017", "BR-GEO-056"})
    if "M24-SITEMAP-ABSENT" in ai_codes: suppressed_rules.update({"BR-GEO-003", "BR-GEO-055"})

    for action in ai_discovery:
        index += 1; modal_id = f"rem-discovery-{index}"; code = str(action.get("diagnostic_code") or ""); title, priority = a._discovery_title(action)
        rows.append((title, a._domain_label("FILES_DISCOVERY"), priority, "CAT-01 → CAT-09 · IA técnica", a._modal_button(modal_id, "Ver orientação")))
        body = a._kv((("Situação / objetivo", title), ("Como proceder", action.get("recommended_change_pt") or "-"), ("Validação humana necessária", "Sim" if action.get("human_validation_required") else "Não"), ("Evidências", ", ".join(str(v) for v in action.get("evidence_ids", []) if str(v)) or "-"))) + _technical_reference_links("FILES_DISCOVERY", source_text=title)
        modals.append(a._modal(modal_id, title, f"Orientação assistida por IA · {code or 'evidência persistida'}", body))

    for rec in deep:
        index += 1; modal_id = f"rem-deep-{index}"; title = rec.get("title") or "Melhoria da análise profunda"; domain = a._norm(rec.get("domain")); source_cat = a._DOMAIN_CATALOG.get(domain); finding = deep_finding_by_id.get(str(rec.get("finding_id")), {})
        rows.append((title, a._domain_label(domain), a._level_label(rec.get("priority")), f"CAT-08 → {source_cat or 'evidência transversal'}", a._modal_button(modal_id, "Ver implementação")))
        rationale = a._rationale_parts(rec.get("rationale")); problem = finding.get("observation") or finding.get("title") or "-"
        body = a._kv((("Problema observado", _finding_public_title(finding) if finding else problem), ("Catálogo de origem", source_cat or "-"), ("Domínio", a._domain_label(domain)), ("Severidade", a._level_label(rec.get("severity"))), ("Prioridade", a._level_label(rec.get("priority"))), ("Seletor / path", rec.get("selector") or finding.get("selector") or "Não se aplica / não identificado"), ("Como corrigir", rec.get("recommendation") or "-"), ("Risco de manter como está", rationale.get("risk") or rec.get("rationale") or "-"), ("Benefício esperado da correção", rationale.get("benefit") or "-"), ("Justificativa técnica", rationale.get("technical") or "-"), ("Impactos relacionados", a._impact_summary(rec.get("impacts_json"))), ("Esforço", a._level_label(rec.get("effort"))), ("Confiança", a._confidence_label(rec.get("confidence"))), ("Problema de origem", rec.get("finding_id") or "-")))
        original = rec.get("original_html") or finding.get("original_html")
        if original: body += "<h3>Situação atual</h3><div class='pre'>" + escape(str(original)) + "</div>"
        if rec.get("suggested_html"): body += "<h3>Proposta corrigida</h3><div class='pre'>" + escape(str(rec.get("suggested_html"))) + "</div>"
        if rec.get("suggested_text"): body += "<h3>Texto sugerido</h3><div class='pre'>" + escape(str(rec.get("suggested_text"))) + "</div>"
        if rec.get("verification"): body += "<h3>Critério de validação / como revalidar</h3><p>" + escape(str(rec.get("verification"))) + "</p>"
        evidence = a._safe_json(rec.get("evidence_ids_json"), [])
        if isinstance(evidence, list) and evidence: body += "<details><summary>Ver referências de evidência</summary><div class='detail-body'><p>" + escape(" · ".join(str(v) for v in evidence)) + "</p></div></details>"
        body += _technical_reference_links(domain, source_text=str(problem)); modals.append(a._modal(modal_id, str(title), f"Remediação da análise CAT-08 · origem {source_cat or 'transversal'}", body))

    for rec in deterministic:
        root, affected_ids, group = _root_for_recommendation(rec, root_by_find, group_by_id)
        if affected_ids and covered.intersection(affected_ids): continue
        rule_id = str(root.get("rule_id") or (group or {}).get("rule_id") or "")
        if rule_id in suppressed_rules: continue
        index += 1; modal_id = f"rem-det-{index}"; title = a._friendly_deterministic_title(rec, root)
        rows.append((title, "Técnico / determinístico", a._level_label(rec.get("priority_class")), "Diagnóstico persistido", a._modal_button(modal_id, "Ver correção")))
        body = a._kv((("Problema / objetivo", rec.get("description") or root.get("cause_summary") or (group or {}).get("root_cause") or "-"), ("Regra", rule_id or "-"), ("Impacto", a._level_label(rec.get("impact") or (group or {}).get("impact"))), ("Esforço", a._level_label(rec.get("effort") or (group or {}).get("effort"))), ("Confiança", a._confidence_label(rec.get("confidence") or (group or {}).get("confidence"))), ("Problemas de origem", ", ".join(affected_ids) or rec.get("finding_id") or "-"))) + _render_observed_value(root.get("observed_value"))
        if root:
            body += "<h3>Implementação sugerida</h3>" + a._kv((("Mudança exata", root.get("exact_change") or "-"), ("Exemplo após correção", root.get("example_after") or "-"), ("Decisão humana necessária", root.get("human_decision_required") or "Não indicada"), ("Critério de aceite", root.get("acceptance_criteria") or "-"), ("Como revalidar", root.get("revalidation_steps") or "-")))
        if group:
            affected_pages = _safe_json(group.get("affected_pages"), []); affected_elements = _safe_json(root.get("affected_elements"), [])
            body += "<details><summary>Escopo técnico relacionado</summary><div class='detail-body'>" + a._kv((("Grupo de remediação", group.get("group_id") or "-"), ("Páginas afetadas", ", ".join(str(v) for v in affected_pages) if isinstance(affected_pages, list) else affected_pages), ("Elementos afetados", ", ".join(str(v) for v in affected_elements) if isinstance(affected_elements, list) else affected_elements))) + "</div></details>"
        body += _technical_reference_links("TECHNICAL_HTML", rule_id, str(root.get("cause_summary") or title)); modals.append(a._modal(modal_id, str(title), "Remediação determinística derivada de problema persistido", body))

    for rec in content:
        fid = str(rec.get("finding_id") or rec.get("source_finding_id") or "")
        if fid and fid in covered: continue
        index += 1; modal_id = f"rem-content-{index}"; title = rec.get("objective") or "Melhoria de conteúdo"; root = root_by_find.get(fid, {}); finding = core_finding_by_id.get(fid, {})
        rows.append((title, a._domain_label("CONTENT"), "-", "IA · conteúdo", a._modal_button(modal_id, "Ver sugestão")))
        body = a._kv((("Objetivo", title), ("Problema observado", finding.get("title") or root.get("cause_summary") or "-"), ("Onde aplicar", rec.get("target_location") or "-"), ("Texto proposto", rec.get("proposed_text") or "-"), ("Confiança", a._confidence_label(rec.get("confidence"))), ("Problema de origem", fid or "-"))) + _render_observed_value(root.get("observed_value"))
        review = str(rec.get("review_note") or "")
        if review: body += "<h3>Explicação técnica / impacto</h3><div class='pre'>" + escape(review) + "</div>"
        if root: body += "<h3>Critério de validação</h3>" + a._kv((("Critério de aceite", root.get("acceptance_criteria") or "-"), ("Como revalidar", root.get("revalidation_steps") or "-")))
        body += _technical_reference_links("CONTENT", str(root.get("rule_id") or ""), str(title)); modals.append(a._modal(modal_id, str(title), "Conteúdo assistido por IA", body))

    for rec in jsonld:
        fid = str(rec.get("finding_id") or rec.get("source_finding_id") or "")
        if fid and fid in covered: continue
        index += 1; modal_id = f"rem-jsonld-{index}"; title = a._jsonld_title(rec)
        rows.append((title, "Dados estruturados", "-", "CAT-03 → CAT-09", a._modal_button(modal_id, "Ver JSON-LD")))
        proposed = a._safe_json(rec.get("proposed_json"), rec.get("proposed_json")); existing = a._safe_json(rec.get("existing_types"), [])
        body = a._kv((("Situação", a._status_label(rec.get("status"))), ("Tipos existentes", ", ".join(existing) if isinstance(existing, list) and existing else "Nenhum"), ("Melhorias", rec.get("improvements") or "-"), ("Problema de origem", fid or "-")))
        root = root_by_find.get(fid, {}); body += _render_observed_value(root.get("observed_value")); body += "<h3>JSON-LD sugerido</h3><div class='pre'>" + escape(json.dumps(proposed, ensure_ascii=False, indent=2) if isinstance(proposed, (dict, list)) else str(proposed or "-")) + "</div>"
        if root: body += "<h3>Validação</h3>" + a._kv((("Critério de aceite", root.get("acceptance_criteria") or "-"), ("Como revalidar", root.get("revalidation_steps") or "-")))
        body += _technical_reference_links("SEMANTICS_STRUCTURE", str(root.get("rule_id") or ""), "JSON-LD"); modals.append(a._modal(modal_id, "Dados estruturados", "Sugestão persistida; exige revisão humana", body))

    lead = ""
    if policy_note: lead = "<div class='notice'><strong>Política para arquivos de descoberta:</strong> " + escape(policy_note) + "</div>"
    unique_findings = len({str(row.get("finding_id")) for row in deep_findings if row.get("finding_id")}); unique_deep = len(covered); without = max(0, unique_findings - unique_deep)
    if deep_run and deep_run.get("max_recommendations") and without: lead += f"<div class='notice'><strong>Cobertura da análise profunda:</strong> {unique_findings} problema(s) foram correlacionados; {unique_deep} possuem remediação individual persistida. O limite configurado foi {int(deep_run.get('max_recommendations'))} recomendações.</div>"
    if rows: lead += "<div class='metric-grid'>" + a._metric("Correções e melhorias apresentadas", len(rows)) + a._metric("Remediações W3C", len(w3c_rows)) + a._metric("Remediações da análise profunda", len(deep)) + a._metric("Achados sem remediação IA individual", without) + a._metric("Orientações técnicas de descoberta", len(ai_discovery)) + "</div>"
    anchor = "<span id='w3c-remediation'></span>" if w3c_rows else ""
    return lead + anchor + a._table(("Correção / melhoria", "Domínio", "Prioridade", "Origem", "Detalhe"), rows, empty="Nenhuma remediação persistida para esta auditoria.", sortable=bool(rows), page_size=10 if len(rows) > 10 else None) + "".join(modals)


def _apply_report_overrides() -> None:
    from rasai import catalog_report_analysis as analysis
    from rasai import catalog_report_metrics as metrics
    from rasai import catalog_report_page as page
    metrics._search_intelligence_html = _search_intelligence_html
    page._search_intelligence_html = _search_intelligence_html
    analysis._improvement_html = _improvement_html
    page._improvement_html = _improvement_html
    analysis._remediation_html = _remediation_html
    page._remediation_html = _remediation_html


def _install_report_patch() -> None:
    global _REPORT_INSTALL_WRAPPED
    if _REPORT_INSTALL_WRAPPED:
        return
    from rasai import catalog_report_final_refinements as refinements
    original = refinements.install_catalog_report_refinements
    if getattr(original, "_rasai_accepted_refinements_v1", False):
        _REPORT_INSTALL_WRAPPED = True
        return
    def install_catalog_report_refinements() -> None:
        original()
        _apply_report_overrides()
    install_catalog_report_refinements._rasai_accepted_refinements_v1 = True
    install_catalog_report_refinements._rasai_original = original
    refinements.install_catalog_report_refinements = install_catalog_report_refinements
    _REPORT_INSTALL_WRAPPED = True


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_improvement_runtime_patch()
    _install_report_patch()
    _INSTALLED = True


__all__ = [
    "REPAIR_TIMEOUT_CAP_SECONDS",
    "_deadline_candidate_call",
    "_merge_recommendations",
    "_repair_findings",
    "_root_for_recommendation",
    "_serp_completion_reason",
    "_validate_partial_recommendations",
    "install",
]
