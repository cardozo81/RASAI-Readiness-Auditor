"""Canonical user-facing state contract for optional integrations and collections.

This module is presentation/operational only. It never changes scoring, provider
selection, collection policy or persisted website evidence. Its purpose is to make
absence of optional data explainable: disabled is not a provider failure, missing
configuration is not a website finding, and a failed attempt is not silently rendered
as an empty table.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
from html import escape
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Mapping, Sequence
import uuid

from rasai.secret_safety import redact_text


_CANONICAL_STATES = {
    "DISABLED": "Desabilitado / não solicitado",
    "NOT_CONFIGURED": "Não configurado",
    "SUCCESS": "Executado com sucesso",
    "PARTIAL": "Executado parcialmente",
    "NO_DATA": "Executado sem dado utilizável",
    "ERROR": "Falhou / indisponível",
    "UNKNOWN": "Estado não determinado",
}

_OBSERVABILITY_SOURCES = {
    "import": "RASAI_OBSERVABILITY_IMPORT",
    "bing-import": "BING_WEBMASTER_TOOLS",
    "google-ai-import": "GOOGLE_GENERATIVE_AI_PERFORMANCE",
    "google-ai-control": "GOOGLE_GENERATIVE_AI_CONTROL",
    "gsc-sites": "GOOGLE_SEARCH_CONSOLE",
    "gsc-sitemaps": "GOOGLE_SEARCH_CONSOLE",
    "gsc-search": "GOOGLE_SEARCH_CONSOLE",
    "gsc-appearance": "GOOGLE_SEARCH_CONSOLE",
    "gsc-inspect": "GOOGLE_SEARCH_CONSOLE",
    "crux-history": "CRUX_HISTORY_API",
}


def public_integration_state(state: str) -> str:
    normalized = str(state or "UNKNOWN").strip().upper()
    return _CANONICAL_STATES.get(normalized, normalized.replace("_", " ").title())


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        if hasattr(row, "keys") and key not in row.keys():
            return default
        value = row[key]
    except (KeyError, IndexError, TypeError, AttributeError):
        return default
    return default if value is None else value


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone() is not None


def _safe_rows(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError:
        return []


def _safe_one(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
    try:
        return connection.execute(sql, params).fetchone()
    except sqlite3.OperationalError:
        return None


def _ai_failure_summary(attempts: Sequence[Any]) -> str:
    failures = [row for row in attempts if str(_row_value(row, "status", "")).upper() != "SUCCESS"]
    if not failures:
        return ""
    details: list[str] = []
    for row in failures[-3:]:
        provider = str(_row_value(row, "provider", "provider"))
        error_class = str(_row_value(row, "error_class", "") or "")
        error_code = str(_row_value(row, "error_code", "") or "")
        http = _row_value(row, "http_status")
        parts = [provider]
        if http is not None:
            parts.append(f"HTTP {http}")
        if error_class:
            parts.append(error_class)
        if error_code:
            parts.append(error_code)
        details.append(" / ".join(parts))
    return "; ".join(details)


def _semantic_ai_coverage(connection: sqlite3.Connection, audit_id: str, Coverage: Any) -> Any | None:
    session = _safe_one(connection, "SELECT * FROM ai_audit_sessions WHERE audit_id=?", (audit_id,))
    if session is None:
        return None
    enabled = bool(_row_value(session, "enabled", False))
    raw_status = str(_row_value(session, "status", "UNKNOWN")).upper()
    attempts = _safe_rows(
        connection,
        "SELECT * FROM ai_provider_attempts WHERE audit_id=? ORDER BY started_at,attempt_index,attempt_id",
        (audit_id,),
    )
    successful = sum(str(_row_value(row, "status", "")).upper() == "SUCCESS" for row in attempts)
    failed = len(attempts) - successful
    effective = str(_row_value(session, "effective_provider", "") or "")

    if not enabled or raw_status == "DISABLED":
        return Coverage(
            "Análise semântica por IA", "Não", "DESABILITADA",
            "IA desabilitada por configuração; nenhuma ausência de análise semântica deve ser interpretada como erro do website ou do provider.",
        )
    if raw_status == "NOT_CONFIGURED":
        return Coverage(
            "Análise semântica por IA", "Sim", "NÃO CONFIGURADA",
            "IA habilitada, mas nenhum provider com credencial/configuração válida estava disponível para executar a finalidade.",
        )
    if raw_status == "SUCCESS":
        return Coverage(
            "Análise semântica por IA", "Sim", "SUCESSO",
            f"Resultado semântico válido materializado{f' por {effective}' if effective else ''}; {successful} tentativa(s) concluída(s) com sucesso e {failed} falha(s) registrada(s).",
        )
    if raw_status in {"DEGRADED", "PARTIAL"}:
        detail = _ai_failure_summary(attempts)
        return Coverage(
            "Análise semântica por IA", "Sim", "PARCIAL",
            f"A IA foi executada, mas a cobertura ficou parcial/degradada. Sucessos: {successful}; falhas: {failed}."
            + (f" Últimas limitações: {detail}." if detail else ""),
        )
    if raw_status == "CHAIN_EXHAUSTED":
        detail = _ai_failure_summary(attempts)
        return Coverage(
            "Análise semântica por IA", "Sim", "FALHOU / INDISPONÍVEL",
            "A cadeia de providers configurados ficou indisponível/quarentenada antes de produzir toda a evidência semântica esperada."
            + (f" Limitações: {detail}." if detail else ""),
        )
    detail = _ai_failure_summary(attempts)
    return Coverage(
        "Análise semântica por IA", "Sim", raw_status,
        "A finalidade de IA foi habilitada, mas não há confirmação de conclusão normal."
        + (f" Limitações persistidas: {detail}." if detail else " Consulte Uso de IA para a telemetria de tentativas."),
    )


def _content_ai_coverage(connection: sqlite3.Connection, audit_id: str, Coverage: Any) -> Any | None:
    run = _safe_one(connection, "SELECT * FROM content_remediation_runs WHERE audit_id=?", (audit_id,))
    if run is None:
        return None
    enabled = bool(_row_value(run, "enabled", False))
    status = str(_row_value(run, "status", "UNKNOWN")).upper()
    eligible = int(_row_value(run, "eligible_findings", 0) or 0)
    reason = str(_row_value(run, "reason", "") or "")
    if not enabled or status == "DISABLED":
        return Coverage(
            "Remediação textual por IA", "Não", "DESABILITADA",
            "Remediação textual por IA desabilitada por configuração; zero chamadas é o comportamento esperado.",
        )
    if status in {"NO_ELIGIBLE_FINDINGS", "NO_ELIGIBLE"} or eligible == 0:
        return Coverage(
            "Remediação textual por IA", "Sim", "SEM FINDINGS ELEGÍVEIS",
            "A finalidade estava habilitada, mas não havia finding elegível para gerar uma chamada de remediação; não é erro de provider.",
        )
    if status == "NOT_CONFIGURED":
        return Coverage(
            "Remediação textual por IA", "Sim", "NÃO CONFIGURADA",
            "Havia findings elegíveis, mas nenhum provider saudável/configurado estava disponível para esta finalidade."
            + (f" Motivo: {redact_text(reason)}." if reason else ""),
        )
    if status in {"SUCCESS", "COMPLETE"}:
        return Coverage(
            "Remediação textual por IA", "Sim", "SUCESSO",
            f"Finalidade executada para o universo elegível ({eligible} finding(s)).",
        )
    if status in {"PARTIAL", "DEGRADED"}:
        return Coverage(
            "Remediação textual por IA", "Sim", "PARCIAL",
            "A remediação foi executada, mas parte do universo elegível não produziu resultado utilizável."
            + (f" Motivo persistido: {redact_text(reason)}." if reason else ""),
        )
    return Coverage(
        "Remediação textual por IA", "Sim", "FALHOU / INDISPONÍVEL",
        "A finalidade estava habilitada e havia trabalho elegível, mas não concluiu normalmente."
        + (f" Motivo persistido: {redact_text(reason)}." if reason else " Consulte Uso de IA para as tentativas."),
    )


def _m24_ai_coverage(connection: sqlite3.Connection, audit_id: str, Coverage: Any) -> Any | None:
    run = _safe_one(connection, "SELECT * FROM m24_runs WHERE audit_id=?", (audit_id,))
    if run is None:
        return None
    enabled = bool(_row_value(run, "ai_enabled", False))
    state = str(_row_value(run, "ai_state", "UNKNOWN")).upper()
    result = _safe_one(connection, "SELECT * FROM m24_ai_results WHERE audit_id=?", (audit_id,))
    reason = str(_row_value(result, "reason", "") or "")
    provider = str(_row_value(result, "provider", "") or "")
    attempts = _safe_rows(
        connection,
        "SELECT * FROM ai_provider_attempts WHERE audit_id=? AND semantic_contract_version LIKE 'M24%' ORDER BY started_at,attempt_index,attempt_id",
        (audit_id,),
    )
    if not enabled or state == "DISABLED":
        return Coverage(
            "IA técnica de crawling/discovery", "Não", "DESABILITADA",
            "IA técnica desabilitada por configuração (default OFF); os diagnósticos determinísticos continuam disponíveis e nenhuma chamada de IA era esperada.",
        )
    if state == "NOT_CONFIGURED":
        return Coverage(
            "IA técnica de crawling/discovery", "Sim", "NÃO CONFIGURADA",
            "IA técnica habilitada, mas sem provider/credencial/configuração utilizável para esta finalidade."
            + (f" Motivo: {redact_text(reason)}." if reason else ""),
        )
    if state in {"AVAILABLE", "SUCCESS"}:
        return Coverage(
            "IA técnica de crawling/discovery", "Sim", "SUCESSO",
            f"Avaliação técnica evidence-bound materializada{f' por {provider}' if provider else ''}; {len(attempts)} tentativa(s) persistida(s).",
        )
    if state in {"PARTIAL", "DEGRADED"}:
        return Coverage(
            "IA técnica de crawling/discovery", "Sim", "PARCIAL",
            "A finalidade foi executada parcialmente."
            + (f" Motivo persistido: {redact_text(reason)}." if reason else ""),
        )
    return Coverage(
        "IA técnica de crawling/discovery", "Sim", "FALHOU / INDISPONÍVEL",
        "A IA técnica foi solicitada, mas não produziu resultado utilizável."
        + (f" Motivo persistido: {redact_text(reason)}." if reason else ""),
    )


def _ux_coverage(connection: sqlite3.Connection, audit_id: str, Coverage: Any) -> Any | None:
    run = _safe_one(connection, "SELECT * FROM synthetic_ux_apdex_runs WHERE audit_id=?", (audit_id,))
    if run is None:
        return None
    enabled = bool(_row_value(run, "enabled", False))
    status = str(_row_value(run, "status", "UNKNOWN")).upper()
    attempted = int(_row_value(run, "attempted_samples", 0) or 0)
    valid = int(_row_value(run, "valid_samples", 0) or 0)
    invalid = int(_row_value(run, "invalid_samples", 0) or 0)
    reason = str(_row_value(run, "reason", "") or "")
    if not enabled:
        return Coverage(
            "Synthetic User Experience Apdex", "Não", "DESABILITADO",
            "Medição opcional desabilitada por configuração; nenhuma user action sintética era esperada.",
        )
    if status == "SUCCESS":
        return Coverage(
            "Synthetic User Experience Apdex", "Sim", "SUCESSO",
            f"{valid} amostra(s) válida(s), {invalid} inválida(s), em {attempted} tentativa(s).",
        )
    if status in {"PARTIAL", "DEGRADED"}:
        return Coverage(
            "Synthetic User Experience Apdex", "Sim", "PARCIAL",
            f"Execução parcial: {valid} válida(s), {invalid} inválida(s), em {attempted} tentativa(s)."
            + (f" Motivo persistido: {redact_text(reason)}." if reason else ""),
        )
    if attempted == 0 and not reason:
        return Coverage(
            "Synthetic User Experience Apdex", "Sim", "NÃO MATERIALIZADO",
            "A medição estava habilitada, mas nenhuma tentativa foi persistida; revisar o estado de execução antes de interpretar a ausência de Apdex.",
        )
    return Coverage(
        "Synthetic User Experience Apdex", "Sim", "FALHOU / INDISPONÍVEL",
        f"A medição estava habilitada, porém não concluiu normalmente ({attempted} tentativa(s), {valid} válida(s))."
        + (f" Motivo persistido: {redact_text(reason)}." if reason else ""),
    )


def _install_audit_coverage_contract() -> None:
    from rasai import report_consistency_v2 as reporting

    if getattr(reporting, "_rasai_universal_integration_state_contract", False):
        return
    original_coverage = reporting._coverage
    original_html = reporting._coverage_html

    def coverage(audit_id: str, workspace: Any):
        rows = list(original_coverage(audit_id, workspace))
        database = Path(workspace.database)
        if not database.is_file():
            return tuple(rows)
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        try:
            replacements = {
                "Análise semântica por IA": _semantic_ai_coverage(connection, audit_id, reporting.Coverage),
                "Remediação textual por IA": _content_ai_coverage(connection, audit_id, reporting.Coverage),
            }
            rows = [replacements.get(item.component) or item for item in rows]
            existing = {item.component for item in rows}
            for candidate in (
                _m24_ai_coverage(connection, audit_id, reporting.Coverage),
                _ux_coverage(connection, audit_id, reporting.Coverage),
            ):
                if candidate is not None and candidate.component not in existing:
                    rows.append(candidate)
                    existing.add(candidate.component)
        finally:
            connection.close()
        return tuple(rows)

    def coverage_html(rows: tuple[Any, ...]) -> str:
        html = original_html(rows)
        legend = (
            "<div class='notice' data-integration-state-contract='true'><strong>Leitura do estado:</strong> "
            "Desabilitado/não solicitado = nenhuma chamada era esperada; Não configurado = a função foi habilitada, "
            "mas faltou credencial/provider/configuração; Sucesso/Parcial = houve execução; Executado sem dado utilizável "
            "= a fonte respondeu sem evidência aproveitável; Falhou/Indisponível = houve tentativa ou bloqueio operacional "
            "que impediu o resultado. Esses estados descrevem a coleta, não a qualidade do website.</div>"
        )
        return html.replace("<div class='table-wrap'>", legend + "<div class='table-wrap'>", 1)

    reporting._coverage = coverage
    reporting._coverage_html = coverage_html
    reporting._rasai_universal_integration_state_contract = True


def _m24_ai_notice(data: Mapping[str, Any]) -> str:
    run = data.get("run")
    ai = data.get("ai")
    enabled = bool(_row_value(run, "ai_enabled", False))
    state = str(_row_value(ai, "state", _row_value(run, "ai_state", "UNKNOWN"))).upper()
    reason = str(_row_value(ai, "reason", "") or "")
    attempts = list(data.get("attempts") or [])
    if not enabled or state == "DISABLED":
        text = "IA técnica desabilitada nesta execução. Nenhuma chamada era esperada; a ausência de avaliação por IA não é erro do website nem do provider."
        css = "notice"
    elif state == "NOT_CONFIGURED":
        text = "IA técnica habilitada, mas sem provider/credencial/configuração utilizável. Nenhum resultado de IA foi coletado por esse motivo."
        css = "notice warn"
    elif state in {"AVAILABLE", "SUCCESS"}:
        text = f"IA técnica executada com sucesso. {len(attempts)} tentativa(s) de provider foram persistidas para esta finalidade."
        css = "notice"
    elif state in {"PARTIAL", "DEGRADED"}:
        text = "IA técnica executada parcialmente; parte da avaliação não produziu resultado utilizável."
        css = "notice warn"
    else:
        text = "IA técnica foi solicitada, mas falhou ou ficou indisponível antes de produzir resultado utilizável."
        css = "notice warn"
    if reason and state not in {"DISABLED", "AVAILABLE", "SUCCESS"}:
        text += f" Motivo persistido: {redact_text(reason)}."
    return f"<div class='{css}' data-integration-state='m24-technical-ai'><strong>Estado da integração:</strong> {escape(text)}</div>"


def _install_m24_ai_state_notice() -> None:
    from rasai import m24_reporting

    if getattr(m24_reporting, "_rasai_explicit_ai_collection_state", False):
        return
    original = m24_reporting._ai_block

    def ai_block(data: dict[str, Any]) -> str:
        html = original(data)
        notice = _m24_ai_notice(data)
        anchor = "<p class='intro'>A IA técnica desta página"
        return html.replace(anchor, notice + anchor, 1) if anchor in html else html.replace("</section>", notice + "</section>", 1)

    m24_reporting._ai_block = ai_block
    m24_reporting._rasai_explicit_ai_collection_state = True


def _runtime_serp_issues(workspace: Path) -> list[dict[str, str]]:
    path = Path(workspace) / "logs" / "audit.log"
    if not path.is_file():
        return []
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines[-500:]:
        try:
            item = json.loads(line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if str(item.get("event") or "") != "SERP_RUNTIME_LIMITATION":
            continue
        code = str(item.get("error_code") or "SERP_CONSOLE_RUNTIME_ERROR")
        message = str(item.get("error_message") or "Falha de runtime antes de materializar observação SERP.")
        key = (code, message)
        if key in seen:
            continue
        seen.add(key)
        output.append({
            "query": str(item.get("query") or "-"),
            "provider": str(item.get("provider") or "SERP"),
            "error_code": code,
            "error_message": message,
        })
    return output


def _install_search_runtime_visibility() -> None:
    from rasai import runtime_adherence_extensions as runtime

    if getattr(runtime, "_rasai_serp_runner_error_report_visibility", False):
        return
    original = runtime._enrich_serp_reports

    def enrich(workspace: Path, issues: Sequence[Mapping[str, Any]], found: Sequence[Mapping[str, Any]]) -> None:
        combined = [dict(item) for item in issues]
        known = {(str(item.get("error_code") or ""), str(item.get("error_message") or "")) for item in combined}
        for item in _runtime_serp_issues(Path(workspace)):
            key = (item["error_code"], item["error_message"])
            if key not in known:
                combined.append(item)
                known.add(key)
        original(Path(workspace), combined, found)

    runtime._enrich_serp_reports = enrich
    runtime._rasai_serp_runner_error_report_visibility = True


def _ensure_observability_attempt_table(workspace: Path) -> Path | None:
    workspace = Path(workspace)
    if not (workspace / "audit.db").is_file():
        return None
    database = workspace / "observability.db"
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS integration_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    metadata TEXT NOT NULL,
                    attempted_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_obs_integration_attempts_time ON integration_attempts(attempted_at,operation)"
            )
    finally:
        connection.close()
    return database


def record_observability_attempt(
    workspace: str | Path,
    *,
    operation: str,
    source_type: str,
    status: str,
    reason: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str | None:
    database = _ensure_observability_attempt_table(Path(workspace))
    if database is None:
        return None
    attempt_id = f"INT-{uuid.uuid4().hex.upper()}"
    safe_reason = redact_text(str(reason))[:1000] if reason else None
    safe_metadata = {
        str(key): redact_text(str(value)) if isinstance(value, str) else value
        for key, value in dict(metadata or {}).items()
    }
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute(
                "INSERT INTO integration_attempts(attempt_id,operation,source_type,status,reason,metadata,attempted_at) VALUES (?,?,?,?,?,?,?)",
                (
                    attempt_id,
                    str(operation),
                    str(source_type),
                    str(status).upper(),
                    safe_reason,
                    json.dumps(safe_metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
    finally:
        connection.close()
    return attempt_id


def _observability_attempts(workspace: Path) -> list[dict[str, Any]]:
    database = Path(workspace) / "observability.db"
    if not database.is_file():
        return []
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "integration_attempts"):
            return []
        return [dict(row) for row in connection.execute(
            "SELECT * FROM integration_attempts ORDER BY attempted_at DESC,attempt_id DESC"
        ).fetchall()]
    finally:
        connection.close()


def _observability_state_section(attempts: Sequence[Mapping[str, Any]]) -> str:
    if not attempts:
        body = (
            "<div class='notice'><strong>Nenhuma tentativa persistida.</strong> As integrações externas/importações deste sidecar "
            "não foram executadas por esta auditoria. Isso não representa falha da fonte, aprovação do website nem ausência de dados no sistema externo.</div>"
        )
    else:
        rows: list[str] = []
        for item in attempts[:100]:
            status = str(item.get("status") or "UNKNOWN").upper()
            reason = str(item.get("reason") or "-")
            rows.append(
                "<tr>"
                f"<td>{escape(str(item.get('operation') or '-'))}</td>"
                f"<td>{escape(str(item.get('source_type') or '-'))}</td>"
                f"<td><strong>{escape(public_integration_state(status))}</strong><br><code>{escape(status)}</code></td>"
                f"<td>{escape(reason)}</td>"
                f"<td>{escape(str(item.get('attempted_at') or '-'))}</td>"
                "</tr>"
            )
        body = (
            "<div class='table-wrap'><table><thead><tr><th>Operação</th><th>Fonte</th><th>Estado</th><th>Motivo</th><th>Timestamp</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>"
        )
    return (
        "<section class='panel' id='observability-integration-state' data-integration-state-contract='true'>"
        "<div class='kicker'>Estado das integrações</div><h2>O dado não veio: por quê?</h2>"
        "<p class='intro'>Esta tabela separa falta de configuração, falha de execução e sucesso. Uma integração sem credencial é "
        "<strong>Não configurada</strong>; uma chamada que retornou erro é <strong>Falhou/Indisponível</strong>; ausência de tentativa "
        "é <strong>Não executado</strong>. Nenhum desses estados é convertido em finding do website.</p>"
        f"{body}</section>"
    )


def _install_observability_reporting() -> None:
    from rasai.observability import reporting

    if getattr(reporting, "_rasai_integration_attempt_state", False):
        return
    original_sidecar = reporting._sidecar
    original_page = reporting._page

    def sidecar(workspace: Path):
        data = original_sidecar(workspace)
        data["attempts"] = _observability_attempts(Path(workspace))
        return data

    def page(bundle: Any, data: dict[str, Any], report_dir: Path) -> str:
        html = original_page(bundle, data, report_dir)
        section = _observability_state_section(data.get("attempts") or [])
        return html.replace("</header>", "</header>" + section, 1) if "</header>" in html else html

    reporting._sidecar = sidecar
    reporting._page = page
    reporting._rasai_integration_attempt_state = True


class _Tee(io.TextIOBase):
    def __init__(self, target: Any) -> None:
        self.target = target
        self.capture = io.StringIO()

    def write(self, text: str) -> int:
        self.capture.write(text)
        return self.target.write(text)

    def flush(self) -> None:
        self.target.flush()


def _observability_failure_reason(output: str) -> tuple[str, str]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    error = next((line.split("RASAi observe error:", 1)[1].strip() for line in reversed(lines) if "RASAi observe error:" in line), "")
    if "not configured; set environment variable" in error.casefold():
        return "NOT_CONFIGURED", error
    return "ERROR", error or "A operação terminou com erro antes de materializar o dataset esperado."


def _install_observability_cli_attempt_ledger() -> None:
    from rasai.observability import cli, reporting

    if getattr(cli, "_rasai_integration_attempt_ledger", False):
        return
    original = cli.main

    def main(argv: list[str] | None = None) -> int:
        effective = list(argv) if argv is not None else list(sys.argv[1:])
        try:
            args = cli.build_parser().parse_args(effective)
        except SystemExit:
            return original(effective)
        operation = str(getattr(args, "observe_command", "") or "")
        source = _OBSERVABILITY_SOURCES.get(operation)
        if source is None:
            return original(effective)
        workspace = cli._workspace(args.audits_root, args.audit)
        tee = _Tee(sys.stdout)
        with redirect_stdout(tee):
            code = int(original(effective) or 0)
        output = tee.capture.getvalue()
        if code == 0:
            status, reason = "SUCCESS", "Operação concluída e estado/dataset persistido pelo fluxo de observabilidade."
        else:
            status, reason = _observability_failure_reason(output)
        record_observability_attempt(
            workspace,
            operation=operation,
            source_type=source,
            status=status,
            reason=reason,
            metadata={"exit_code": code},
        )
        try:
            reporting.enrich_observability_report(audit_workspace=workspace)
        except (OSError, ValueError, RuntimeError, sqlite3.Error):
            pass
        return code

    cli.main = main
    cli._rasai_integration_attempt_ledger = True


def _install_m26_empty_state() -> None:
    from rasai import m26_reporting

    if getattr(m26_reporting, "_rasai_explicit_import_state", False):
        return
    original = m26_reporting._page

    def page(data: dict[str, Any], report_dir: Path) -> str:
        html = original(data, report_dir)
        if data.get("imports"):
            return html
        old = "Nenhum dataset de visibilidade generativa foi importado para esta auditoria."
        new = (
            "Nenhum dataset de visibilidade generativa foi importado para esta auditoria. Esta superfície é import-first: "
            "o RASAi não executou uma chamada direta a um provider de IA para preencher este dado. Portanto, ausência de dataset "
            "significa não importado/não observado por este fluxo, e não falha presumida de API ou resultado zero."
        )
        return html.replace(old, new, 1)

    m26_reporting._page = page
    m26_reporting._rasai_explicit_import_state = True


def install() -> None:
    """Install the cross-integration user-facing state contract idempotently."""
    _install_audit_coverage_contract()
    _install_m24_ai_state_notice()
    _install_search_runtime_visibility()
    _install_observability_reporting()
    _install_observability_cli_attempt_ledger()
    _install_m26_empty_state()
