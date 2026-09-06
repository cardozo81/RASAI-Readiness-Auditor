"""Integrity gate for PageSpeed/Lighthouse/CrUX evidence.

PageSpeed API transport success is not equivalent to a usable Lighthouse run.
This module validates persisted PSI artifacts after M21 collection and before
report projection. It never creates new network calls and never touches
SCORE-GEO-002.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any

from searchgeo.m21_web_performance import M21ExecutionResult
from searchgeo.operational_log import try_append_operational_event
from searchgeo.persistence import AuditWorkspace


ARTIFACT = "artifacts/external-metrics-integrity.json"
REPORT_MARKER_START = "<!-- searchgeo-external-metrics-integrity:start -->"
REPORT_MARKER_END = "<!-- searchgeo-external-metrics-integrity:end -->"
_CATEGORY_COLUMNS = {
    "performance": "performance_score",
    "accessibility": "accessibility_score",
    "best-practices": "best_practices_score",
    "seo": "seo_score",
}
_LIGHTHOUSE_PERFORMANCE_COLUMNS = (
    "performance_score",
    "fcp_lab_ms",
    "speed_index_lab_ms",
    "lcp_lab_ms",
    "tbt_lab_ms",
    "cls_lab",
)


@dataclass(frozen=True, slots=True)
class LighthouseContextIntegrity:
    observation_id: str
    url: str
    device: str
    pagespeed_artifact: str | None
    pagespeed_http_status: int | None
    lighthouse_status: str
    lighthouse_runtime_error_code: str | None
    lighthouse_runtime_error_message: str | None
    requested_categories: tuple[str, ...]
    valid_categories: tuple[str, ...]
    missing_or_invalid_categories: tuple[str, ...]
    accessibility_valid: bool
    performance_valid: bool
    field_data_valid: bool
    resulting_observation_status: str


@dataclass(frozen=True, slots=True)
class ExternalMetricsIntegrity:
    version: str
    audit_id: str
    contexts: tuple[LighthouseContextIntegrity, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "audit_id": self.audit_id,
            "semantics": {
                "pagespeed_success": "HTTP/API transport success only",
                "lighthouse_valid": "lighthouseResult exists, has no fatal runtimeError and requested category scores are usable",
                "accessibility_score": "source score supplied by Lighthouse; SearchGEO does not recalculate it",
                "score_geo_dependency": False,
            },
            "contexts": [asdict(item) for item in self.contexts],
        }


def reconcile_external_metrics_integrity(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    result: M21ExecutionResult,
) -> M21ExecutionResult:
    """Validate PSI/Lighthouse artifacts and remove invalid derived values.

    A PSI HTTP 200 remains an API-attempt success for telemetry, but Lighthouse
    values are discarded when the LHR is absent/fatally errored. Missing
    requested categories make the observation PARTIAL when other evidence is
    still usable. Raw PSI artifacts are never modified.
    """

    if not workspace.database.is_file():
        return result
    con = sqlite3.connect(workspace.database)
    con.row_factory = sqlite3.Row
    try:
        run = _one(con, "SELECT * FROM web_performance_runs WHERE audit_id=?", audit_id)
        if run is None or not bool(run["enabled"]):
            return result
        requested = tuple(_json_list(run["categories"]))
        observations = list(
            con.execute(
                "SELECT * FROM web_performance_observations WHERE audit_id=? ORDER BY observation_id",
                (audit_id,),
            ).fetchall()
        )
        contexts: list[LighthouseContextIntegrity] = []
        with con:
            for row in observations:
                context, updates = _validate_observation(
                    workspace=workspace,
                    row=row,
                    requested_categories=requested,
                )
                contexts.append(context)
                _apply_updates(con, str(row["observation_id"]), updates)

            refreshed = list(
                con.execute(
                    "SELECT status FROM web_performance_observations WHERE audit_id=?",
                    (audit_id,),
                ).fetchall()
            )
            statuses = [str(row["status"]) for row in refreshed]
            usable = sum(status in {"SUCCESS", "PARTIAL"} for status in statuses)
            partial = sum(status == "PARTIAL" for status in statuses)
            if int(run["context_attempts"] or 0) == 0:
                run_status = str(run["status"])
                reason = run["reason"]
            elif usable == 0:
                run_status = "UNAVAILABLE"
                reason = "EXTERNAL_WEB_PERFORMANCE_UNAVAILABLE"
            elif partial or usable < int(run["context_attempts"] or 0):
                run_status = "PARTIAL"
                reason = "ONE_OR_MORE_EXTERNAL_COMPONENTS_UNAVAILABLE"
            else:
                run_status = "SUCCESS"
                reason = None
            con.execute(
                "UPDATE web_performance_runs SET status=?,successful_contexts=?,reason=? WHERE audit_id=?",
                (run_status, usable, reason, audit_id),
            )
    finally:
        con.close()

    integrity = ExternalMetricsIntegrity(
        version="EXTERNAL-METRICS-INTEGRITY-1",
        audit_id=audit_id,
        contexts=tuple(contexts),
    )
    path = workspace.root / ARTIFACT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(integrity.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    valid_lighthouse = sum(item.lighthouse_status == "VALID" for item in contexts)
    valid_accessibility = sum(item.accessibility_valid for item in contexts)
    try_append_operational_event(
        workspace,
        "EXTERNAL_METRICS_INTEGRITY_RECONCILED",
        audit_id=audit_id,
        contexts=len(contexts),
        lighthouse_valid_contexts=valid_lighthouse,
        accessibility_valid_contexts=valid_accessibility,
        lighthouse_invalid_contexts=len(contexts) - valid_lighthouse,
        policy="PAGESPEED_TRANSPORT_IS_NOT_LIGHTHOUSE_VALIDITY",
        artifact=ARTIFACT,
    )
    return replace(
        result,
        status=run_status,
        successful_contexts=usable,
        partial_contexts=partial,
    )


def enrich_external_metrics_integrity_report_site(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Expose collection provenance/coverage and prevent ambiguous no-failure claims."""

    payload = _read_json(workspace.root / ARTIFACT)
    if not payload:
        return
    raw_contexts = payload.get("contexts")
    if not isinstance(raw_contexts, list):
        return
    contexts = [item for item in raw_contexts if isinstance(item, dict)]
    total = len(contexts)
    lh_valid = sum(item.get("lighthouse_status") == "VALID" for item in contexts)
    a11y_valid = sum(bool(item.get("accessibility_valid")) for item in contexts)
    perf_valid = sum(bool(item.get("performance_valid")) for item in contexts)
    field_valid = sum(bool(item.get("field_data_valid")) for item in contexts)
    rows = "".join(_context_row(item) for item in contexts) or "<tr><td colspan='7'>Nenhum contexto externo materializado.</td></tr>"
    block = (
        REPORT_MARKER_START
        + "<section class='panel' id='external-metrics-integrity'>"
        "<div class='kicker'>Integridade da evidência externa</div>"
        "<h2>PageSpeed, Lighthouse, CrUX e Acessibilidade: cobertura real</h2>"
        "<div class='notice warn'><strong>PageSpeed HTTP 200 não significa Lighthouse válido.</strong> "
        "O SearchGEO valida <code>lighthouseResult</code>, descarta métricas Lighthouse quando existe "
        "<code>runtimeError</code> fatal e trata categoria solicitada ausente como evidência incompleta. "
        "Falha/quota/timeout do PageSpeed é indisponibilidade da medição externa, não defeito do website e não reduz SCORE-GEO-002.</div>"
        f"<div class='metric-grid'>{_metric('Contextos externos', total)}"
        f"{_metric('Lighthouse válido', f'{lh_valid}/{total}')}{_metric('Performance válida', f'{perf_valid}/{total}')}"
        f"{_metric('Acessibilidade válida', f'{a11y_valid}/{total}')}{_metric('Field data válido', f'{field_valid}/{total}')}</div>"
        "<p class='intro'><strong>Acessibilidade:</strong> o valor 0–100 é o score fornecido pelo Lighthouse para a categoria "
        "<code>accessibility</code>. O SearchGEO não recalcula esse score. Médias entre páginas/dispositivos são apenas estatística "
        "descritiva sobre contextos que efetivamente possuem score válido; ausência de categoria/score nunca vira zero.</p>"
        "<div class='table-wrap'><table><thead><tr><th>URL</th><th>Dispositivo</th><th>PageSpeed HTTP</th>"
        "<th>Lighthouse</th><th>Performance</th><th>Acessibilidade</th><th>Categorias ausentes/inválidas</th></tr></thead><tbody>"
        + rows
        + "</tbody></table></div>"
        f"<p class='intro'>Evidência estruturada: <a href='../{ARTIFACT}'><code>{ARTIFACT}</code></a>.</p>"
        "</section>"
        + REPORT_MARKER_END
    )

    report_dir = workspace.root / "report"
    for name in ("index.html", "web-performance.html", "accessibility.html"):
        path = report_dir / name
        if not path.is_file():
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except OSError:
            continue
        html = _replace_or_insert(html, block)
        if name == "accessibility.html":
            html = html.replace(
                "<strong>Nenhuma falha automatizada persistida.</strong> Isso não elimina a necessidade dos checks manuais do Lighthouse/WCAG.",
                "<strong>Nenhuma falha automatizada persistida neste artifact.</strong> Esta observação só deve ser interpretada como ausência de falhas automatizadas quando a tabela de integridade acima marcar a categoria Accessibility deste contexto como válida; checks manuais continuam necessários.",
            )
            html = html.replace(
                "Contextos com artifact",
                "Contextos com artifact PageSpeed",
            )
            html = html.replace(
                "Lighthouse médio",
                "Média a11y (scores válidos)",
            )
        if name == "web-performance.html":
            html = html.replace(
                "Esta telemetria é de serviços de medição, não de IA.",
                "Esta telemetria é de serviços de medição, não de IA. Status SUCCESS na tentativa PageSpeed indica transporte/API concluído; a validade do Lighthouse é verificada separadamente acima.",
            )
            html = html.replace("Lighthouse médio", "Lighthouse médio (válidos)")
        path.write_text(html, encoding="utf-8", newline="\n")


def _validate_observation(
    *,
    workspace: AuditWorkspace,
    row: sqlite3.Row,
    requested_categories: tuple[str, ...],
) -> tuple[LighthouseContextIntegrity, dict[str, Any]]:
    artifact_ref = str(row["pagespeed_artifact_reference"] or "") or None
    payload = _read_json(workspace.root / artifact_ref) if artifact_ref else None
    result = payload.get("lighthouseResult") if isinstance(payload, dict) else None
    runtime_code = runtime_message = None
    lighthouse_status = "RESULT_MISSING"
    valid_categories: list[str] = []
    invalid_categories: list[str] = []

    if isinstance(result, dict):
        runtime = result.get("runtimeError")
        if isinstance(runtime, dict):
            code = str(runtime.get("code") or "").strip()
            message = str(runtime.get("message") or "").strip()
            if code and code != "NO_ERROR":
                runtime_code = code
                runtime_message = message or None
                lighthouse_status = "RUNTIME_ERROR"
        if lighthouse_status != "RUNTIME_ERROR":
            categories = result.get("categories") if isinstance(result.get("categories"), dict) else {}
            for category in requested_categories:
                item = categories.get(category)
                score = _number(item.get("score")) if isinstance(item, dict) else None
                if score is not None and 0.0 <= score <= 1.0:
                    valid_categories.append(category)
                else:
                    invalid_categories.append(category)
            lighthouse_status = "VALID" if not invalid_categories else "CATEGORY_INCOMPLETE"
    else:
        invalid_categories.extend(requested_categories)

    updates: dict[str, Any] = {}
    if lighthouse_status in {"RUNTIME_ERROR", "RESULT_MISSING"}:
        for column in _CATEGORY_COLUMNS.values():
            updates[column] = None
        for column in _LIGHTHOUSE_PERFORMANCE_COLUMNS[1:]:
            updates[column] = None
    else:
        for category in invalid_categories:
            column = _CATEGORY_COLUMNS.get(category)
            if column:
                updates[column] = None
            if category == "performance":
                for column in _LIGHTHOUSE_PERFORMANCE_COLUMNS:
                    updates[column] = None

    performance_valid = "performance" in valid_categories
    accessibility_valid = "accessibility" in valid_categories
    field_valid = any(row[name] is not None for name in ("lcp_p75_ms", "inp_p75_ms", "cls_p75"))
    any_lighthouse_valid = bool(valid_categories)
    old_errors = [part for part in str(row["error_summary"] or "").split(";") if part]
    integrity_errors: list[str] = []
    if lighthouse_status == "RUNTIME_ERROR":
        integrity_errors.append(f"LIGHTHOUSE_RUNTIME_ERROR:{runtime_code or 'UNKNOWN'}")
    elif lighthouse_status == "RESULT_MISSING":
        integrity_errors.append("LIGHTHOUSE_RESULT_MISSING")
    elif invalid_categories:
        integrity_errors.extend(f"LIGHTHOUSE_CATEGORY_INVALID:{item}" for item in invalid_categories)
    merged_errors = tuple(dict.fromkeys((*old_errors, *integrity_errors)))

    usable = any_lighthouse_valid or field_valid
    incomplete = lighthouse_status != "VALID" or bool(old_errors)
    status = "PARTIAL" if usable and incomplete else "SUCCESS" if usable else "UNAVAILABLE"
    updates["status"] = status
    updates["error_summary"] = ";".join(merged_errors) if merged_errors else None

    context = LighthouseContextIntegrity(
        observation_id=str(row["observation_id"]),
        url=str(row["url"]),
        device=str(row["device"]),
        pagespeed_artifact=artifact_ref,
        pagespeed_http_status=int(row["pagespeed_http_status"]) if row["pagespeed_http_status"] is not None else None,
        lighthouse_status=lighthouse_status,
        lighthouse_runtime_error_code=runtime_code,
        lighthouse_runtime_error_message=runtime_message,
        requested_categories=requested_categories,
        valid_categories=tuple(valid_categories),
        missing_or_invalid_categories=tuple(invalid_categories),
        accessibility_valid=accessibility_valid,
        performance_valid=performance_valid,
        field_data_valid=field_valid,
        resulting_observation_status=status,
    )
    return context, updates


def _apply_updates(con: sqlite3.Connection, observation_id: str, updates: dict[str, Any]) -> None:
    if not updates:
        return
    allowed = {
        "status", "error_summary", "performance_score", "accessibility_score", "best_practices_score", "seo_score",
        "fcp_lab_ms", "speed_index_lab_ms", "lcp_lab_ms", "tbt_lab_ms", "cls_lab",
    }
    items = [(key, value) for key, value in updates.items() if key in allowed]
    if not items:
        return
    assignments = ",".join(f"{key}=?" for key, _ in items)
    con.execute(
        f"UPDATE web_performance_observations SET {assignments} WHERE observation_id=?",
        tuple(value for _, value in items) + (observation_id,),
    )


def _context_row(item: dict[str, Any]) -> str:
    invalid = item.get("missing_or_invalid_categories") or []
    return (
        "<tr>"
        f"<td class='mono'>{escape(str(item.get('url') or '-'))}</td>"
        f"<td>{escape(str(item.get('device') or '-'))}</td>"
        f"<td>{escape(str(item.get('pagespeed_http_status') if item.get('pagespeed_http_status') is not None else '—'))}</td>"
        f"<td>{escape(str(item.get('lighthouse_status') or '—'))}</td>"
        f"<td>{'VÁLIDA' if item.get('performance_valid') else 'NÃO OBTIDA'}</td>"
        f"<td>{'VÁLIDA' if item.get('accessibility_valid') else 'NÃO OBTIDA'}</td>"
        f"<td>{escape(', '.join(str(value) for value in invalid) if invalid else '—')}</td>"
        "</tr>"
    )


def _replace_or_insert(html: str, block: str) -> str:
    if REPORT_MARKER_START in html and REPORT_MARKER_END in html:
        start = html.index(REPORT_MARKER_START)
        end = html.index(REPORT_MARKER_END, start) + len(REPORT_MARKER_END)
        return html[:start] + block + html[end:]
    if "</header>" in html:
        return html.replace("</header>", "</header>" + block, 1)
    return html.replace("</main>", block + "</main>", 1) if "</main>" in html else html


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>"


def _one(con: sqlite3.Connection, sql: str, audit_id: str) -> sqlite3.Row | None:
    try:
        return con.execute(sql, (audit_id,)).fetchone()
    except sqlite3.Error:
        return None


def _json_list(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
