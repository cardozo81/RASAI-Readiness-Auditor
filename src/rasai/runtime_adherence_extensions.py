"""Runtime adherence fixes shared by the public CLI and interactive console.

This module is intentionally additive. It closes integration gaps between the dynamic
AI router, post-audit Search Intelligence, the console execution clock/progress model,
and Synthetic User Experience Apdex device scope without changing scoring contracts.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime
from html import escape
import io
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


_INSTALLED = False


def _scope_experience_config(config: Any, audit_device: str) -> Any:
    """Restrict M25 synthetic population to the audit's canonical device scope.

    The current core audit contract has two canonical contexts: MOBILE and DESKTOP.
    M25 may model TABLET in isolation, but a console/CLI audit must not silently execute
    devices that the audit selector excluded. Singular audit scopes therefore become
    100% of that device; BOTH renormalizes only MOBILE/DESKTOP weights.
    """
    if not bool(getattr(config, "enabled", False)):
        return config
    selected = str(audit_device or "mobile").strip().casefold()
    if selected == "mobile":
        mix = (("MOBILE", 100.0),)
    elif selected == "desktop":
        mix = (("DESKTOP", 100.0),)
    elif selected == "both":
        configured = config.device_mix_dict()
        mobile = max(float(configured.get("MOBILE", 0.0)), 0.0)
        desktop = max(float(configured.get("DESKTOP", 0.0)), 0.0)
        total = mobile + desktop
        if total <= 0:
            # BOTH is an explicit request for the two canonical audit contexts. If a
            # legacy mix contained only TABLET, use an even canonical distribution
            # rather than executing a device outside the selected audit scope.
            mix = (("MOBILE", 50.0), ("DESKTOP", 50.0))
        else:
            rows: list[tuple[str, float]] = []
            if mobile > 0:
                rows.append(("MOBILE", mobile * 100.0 / total))
            if desktop > 0:
                rows.append(("DESKTOP", desktop * 100.0 / total))
            mix = tuple(rows)
    else:
        # The public core currently supports mobile, desktop and both. Keep this
        # guard explicit so TABLET is never mislabeled as MOBILE in the core audit.
        raise ValueError(
            "audit device must be mobile, desktop or both; tablet is currently an M25 synthetic profile, not a canonical core audit context"
        )
    return replace(config, device_mix=mix).validate()


def _serp_issue_category(code: str | None, message: str | None) -> str:
    """Classify a provider limitation for operator-facing diagnostics.

    Categories distinguish commercial/account limitations from technical/transient
    failures while preserving the provider's original code/message as the evidence.
    """
    text = f"{code or ''} {message or ''}".casefold()
    if any(token in text for token in ("http 402", "credit", "credits", "billing", "payment", "saldo", "sem crédito", "out of searches", "no searches left")):
        return "BUSINESS_CREDIT_OR_BILLING"
    if any(token in text for token in ("http 401", "http 403", "unauthor", "forbidden", "invalid api key", "api key invalid", "authentication", "permission")):
        return "BUSINESS_AUTHENTICATION_OR_PERMISSION"
    if any(token in text for token in ("quota exceeded", "quota exhausted", "monthly limit", "search limit", "plan limit")):
        return "BUSINESS_QUOTA_OR_PLAN"
    if any(token in text for token in ("timeout", "timed out", "serp_provider_timeout")):
        return "TECHNICAL_TIMEOUT"
    if "http 429" in text or "rate limit" in text or "too many requests" in text:
        return "TECHNICAL_RATE_LIMIT"
    if any(token in text for token in ("http 500", "http 502", "http 503", "http 504", "unavailable", "connection", "network", "dns")):
        return "TECHNICAL_TRANSIENT_PROVIDER"
    return "TECHNICAL_PROVIDER_OR_RUNTIME"


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone() is not None


def _serp_rows(workspace: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    database = workspace / "audit.db"
    if not database.is_file():
        return [], []
    try:
        connection = sqlite3.connect(database, timeout=0.5)
        connection.row_factory = sqlite3.Row
        try:
            if not _table_exists(connection, "serp_observations"):
                return [], []
            issues = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT observation_id,query,provider,domain_status,error_code,error_message,
                           domain_of_interest,customer_position,collected_at
                    FROM serp_observations
                    WHERE domain_status IN ('ERROR','UNAVAILABLE')
                    ORDER BY collected_at,observation_id
                    """
                ).fetchall()
            ]
            found = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT observation_id,query,provider,domain_of_interest,customer_position,collected_at
                    FROM serp_observations
                    WHERE domain_status='FOUND' AND customer_position IS NOT NULL
                    ORDER BY collected_at,observation_id
                    """
                ).fetchall()
            ]
            return issues, found
        finally:
            connection.close()
    except sqlite3.Error:
        return [], []


def _remove_managed_block(html: str, start_marker: str, end_marker: str) -> str:
    while start_marker in html:
        start = html.find(start_marker)
        end = html.find(end_marker, start)
        if end < 0:
            return html[:start]
        html = html[:start] + html[end + len(end_marker):]
    return html


def _issue_notice(issues: Sequence[Mapping[str, Any]], *, title: str) -> str:
    if not issues:
        return ""
    rows = []
    for item in issues[:12]:
        code = str(item.get("error_code") or "SERP_PROVIDER_ERROR")
        message = str(item.get("error_message") or "provider error")
        category = _serp_issue_category(code, message)
        query = str(item.get("query") or "-")
        provider = str(item.get("provider") or "-")
        rows.append(
            "<li>"
            f"<strong>{escape(query)}</strong> · {escape(provider)} · "
            f"<code>{escape(category)}</code> · <code>{escape(code)}</code>: "
            f"{escape(message)}"
            "</li>"
        )
    extra = len(issues) - len(rows)
    suffix = f"<p>Há mais {extra} ocorrência(s) registrada(s) no audit.db/log técnico.</p>" if extra > 0 else ""
    return (
        "<section class='panel rasai-serp-runtime-limitation'>"
        f"<div class='kicker'>Search Intelligence · execução com limitação</div><h2>{escape(title)}</h2>"
        "<div class='notice'><strong>A auditoria principal foi preservada.</strong> "
        "A coleta SERP é fail-open e não altera SARI-001/SCORE-GEO-004. "
        "O motivo abaixo deve ser tratado separadamente conforme a categoria de negócio ou técnica.</div>"
        f"<ul>{''.join(rows)}</ul>{suffix}</section>"
    )


def _enrich_serp_reports(workspace: Path, issues: Sequence[Mapping[str, Any]], found: Sequence[Mapping[str, Any]]) -> None:
    """Add operator-facing SERP limitation and customer-position emphasis to reports."""
    start_marker = "<!-- RASAI_SERP_RUNTIME_ADHERENCE_START -->"
    end_marker = "<!-- RASAI_SERP_RUNTIME_ADHERENCE_END -->"
    search_path = workspace / "report" / "search-intelligence.html"
    if search_path.is_file():
        try:
            html = search_path.read_text(encoding="utf-8")
            html = _remove_managed_block(html, start_marker, end_marker)
            additions: list[str] = []
            if found:
                hit_rows = []
                for row in found:
                    hit_rows.append(
                        "<li>"
                        f"<strong>{escape(str(row.get('query') or '-'))}</strong>: "
                        f"domínio principal <code>{escape(str(row.get('domain_of_interest') or '-'))}</code> "
                        f"encontrado na posição <strong>#{escape(str(row.get('customer_position') or '-'))}</strong>."
                        "</li>"
                    )
                additions.append(
                    "<section class='panel rasai-serp-customer-highlight' style='border-width:2px'>"
                    "<div class='kicker'>Domínio principal localizado</div>"
                    "<h2>Posição do domínio auditado na SERP</h2>"
                    "<div class='notice'><strong>Destaque:</strong> estas posições correspondem ao mesmo domínio derivado da URL principal da auditoria.</div>"
                    f"<ul>{''.join(hit_rows)}</ul></section>"
                )
            notice = _issue_notice(issues, title="Falha ou indisponibilidade na coleta SERP")
            if notice:
                additions.append(notice)
            if additions:
                block = start_marker + "".join(additions) + end_marker
                anchor = "</header>"
                html = html.replace(anchor, anchor + block, 1) if anchor in html else html + block
            search_path.write_text(html, encoding="utf-8", newline="\n")
        except (OSError, UnicodeError):
            pass

    index_path = workspace / "report" / "index.html"
    if index_path.is_file():
        try:
            html = index_path.read_text(encoding="utf-8")
            html = _remove_managed_block(html, start_marker, end_marker)
            notice = _issue_notice(issues, title="Search Intelligence concluído com limitações")
            if notice:
                block = start_marker + notice + end_marker
                anchor = "</header>"
                html = html.replace(anchor, anchor + block, 1) if anchor in html else html + block
            index_path.write_text(html, encoding="utf-8", newline="\n")
        except (OSError, UnicodeError):
            pass


def _append_serp_events(workspace: Path, state: Any, issues: Sequence[Mapping[str, Any]], duration: float, runner_errors: Sequence[str]) -> None:
    try:
        from rasai.operational_log import try_append_operational_event
        from rasai.persistence import AuditWorkspace

        audit_workspace = AuditWorkspace.open(workspace)
    except Exception:
        return

    for item in issues:
        code = str(item.get("error_code") or "SERP_PROVIDER_ERROR")
        message = str(item.get("error_message") or "provider error")
        try_append_operational_event(
            audit_workspace,
            "SERP_PROVIDER_LIMITATION",
            level="WARNING",
            audit_id=str(getattr(state, "audit_id", "") or ""),
            query=str(item.get("query") or ""),
            provider=str(item.get("provider") or ""),
            category=_serp_issue_category(code, message),
            error_code=code,
            error_message=message,
            scoring_impact="NONE",
            completion_policy="FAIL_OPEN",
        )
    for message in runner_errors:
        try_append_operational_event(
            audit_workspace,
            "SERP_RUNTIME_LIMITATION",
            level="WARNING",
            audit_id=str(getattr(state, "audit_id", "") or ""),
            category=_serp_issue_category("SERP_CONSOLE_RUNTIME_ERROR", message),
            error_code="SERP_CONSOLE_RUNTIME_ERROR",
            error_message=message,
            scoring_impact="NONE",
            completion_policy="FAIL_OPEN",
        )
    status = "COMPLETE_WITH_LIMITATIONS" if issues or runner_errors else "COMPLETE"
    try_append_operational_event(
        audit_workspace,
        "SEARCH_INTELLIGENCE_COMPLETED",
        level="WARNING" if status != "COMPLETE" else "INFO",
        audit_id=str(getattr(state, "audit_id", "") or ""),
        status=status,
        query_count=len(tuple(getattr(state, "search_queries", ()) or ())),
        issue_count=len(issues) + len(runner_errors),
        duration_seconds=round(float(duration), 3),
        scoring_impact="NONE",
    )


def _resume_console_clock(state: Any) -> None:
    try:
        from rasai import console_runtime

        timing = console_runtime._RUN_TIMINGS.get(id(state))
        if timing is not None:
            timing.finished_at = None
            timing.duration_seconds = None
    except Exception:
        pass


def _serp_progress(state: Any, *, completed: int, total: int, detail: str, render: bool = True) -> None:
    try:
        from rasai import console_runtime

        total = max(int(total), 1)
        stage = min(max(float(completed) / total * 100.0, 0.0), 100.0)
        overall = 97.0 + (stage / 100.0 * 2.0)
        state.status = "SEARCH_INTELLIGENCE"
        state.operation = "API:SERP"
        progress_type = getattr(console_runtime, "_RunProgress", None)
        progress_store = getattr(console_runtime, "_RUN_PROGRESS", None)
        if progress_type is not None and isinstance(progress_store, dict):
            progress_store[id(state)] = progress_type(
                label="Search Intelligence / SERP",
                percent=stage,
                detail=detail,
                exact=True,
                stage_percent=stage,
                stage_exact=True,
                overall_percent=overall,
                overall_exact=False,
            )
        else:
            console_runtime.set_runtime_progress(
                state,
                "Search Intelligence / SERP",
                overall,
                detail=detail,
                exact=False,
            )
        if render:
            console_runtime.render_header(state)
    except Exception:
        pass


def _finalize_console_clock(state: Any, workspace: Path, *, limited: bool, detail: str) -> None:
    try:
        from rasai import console_runtime
        from rasai.console_cost import estimate_exposure, persist_execution_projection

        state.status = "COMPLETE_WITH_LIMITATIONS" if limited else "COMPLETE"
        state.operation = "INTEGRATION:SEARCH_INTELLIGENCE_LIMITATION" if limited else "LOCAL:DONE"
        console_runtime.set_runtime_progress(
            state,
            "Concluído com limitações" if limited else "Concluído",
            100.0,
            detail=detail,
            exact=True,
        )
        console_runtime._finish_timing(state)
        timing = console_runtime._RUN_TIMINGS.get(id(state))
        if timing is None or timing.finished_at is None or timing.duration_seconds is None:
            return
        projected_at = timing.started_at.isoformat()
        database = workspace / "audit.db"
        if database.is_file() and getattr(state, "audit_id", ""):
            try:
                connection = sqlite3.connect(database, timeout=0.5)
                try:
                    row = connection.execute(
                        "SELECT projected_at FROM console_execution_projections WHERE audit_id=?",
                        (str(state.audit_id),),
                    ).fetchone()
                    if row and row[0]:
                        projected_at = str(row[0])
                finally:
                    connection.close()
            except sqlite3.Error:
                pass
        persist_execution_projection(
            workspace,
            state,
            estimate_exposure(state),
            projected_at=projected_at,
            started_at=timing.started_at.isoformat(),
            finished_at=timing.finished_at.isoformat(),
            duration_ms=max(int(round(timing.duration_seconds * 1000.0)), 0),
        )
    except Exception:
        pass


def _install_search_console_adherence() -> None:
    try:
        from rasai import console_search_intelligence as search_console
    except Exception:
        return
    original = search_console.execute_search_for_audit
    if bool(getattr(original, "_rasai_runtime_adherence", False)):
        return

    def execute_search_for_audit(
        state: Any,
        *,
        target_url: str,
        runner: Any = None,
    ) -> int:
        workspace = search_console.audit_workspace(state)
        if workspace is None:
            state.search_last_status = "UNAVAILABLE"
            state.search_last_detail = "workspace AUD da sessão não encontrado"
            state.search_last_report = ""
            return 1
        if runner is None:
            from rasai.search_intelligence.cli import main as runner

        _resume_console_clock(state)
        queries = tuple(getattr(state, "search_queries", ()) or ())
        full_argv = search_console.build_search_argv(
            state,
            workspace=workspace,
            target_url=target_url,
        )
        try:
            option_index = full_argv.index("--domain")
        except ValueError:
            option_index = len(queries)
        shared_options = full_argv[option_index:]
        outputs: list[str] = []
        runner_errors: list[str] = []
        any_nonzero = False
        started = time.monotonic()

        for index, query in enumerate(queries, 1):
            state.current_device = str(getattr(state, "search_device", "mobile")).upper()
            _serp_progress(
                state,
                completed=index - 1,
                total=len(queries),
                detail=f"consultando termo {index}/{len(queries)}: {query}; provider SERP; depth={getattr(state, 'search_depth', 20)}",
            )
            output = io.StringIO()
            try:
                with redirect_stdout(output), redirect_stderr(output):
                    code = int(runner([query, *shared_options]) or 0)
            except SystemExit as exc:
                raw_code = exc.code if isinstance(exc.code, int) else 2
                code = int(raw_code)
            except Exception as exc:  # Search Intelligence is explicitly fail-open.
                code = 2
                message = f"{type(exc).__name__}: {str(exc)[:512]}"
                output.write(message)
                runner_errors.append(message)
            any_nonzero = any_nonzero or code != 0
            captured = output.getvalue().strip()
            if captured:
                outputs.append(captured)
            _serp_progress(
                state,
                completed=index,
                total=len(queries),
                detail=f"termo {index}/{len(queries)} finalizado; persistindo observação e atualizando relatório Search Intelligence",
            )

        duration = max(time.monotonic() - started, 0.0)
        issues, found = _serp_rows(workspace)
        _append_serp_events(workspace, state, issues, duration, runner_errors)
        _serp_progress(
            state,
            completed=len(queries),
            total=len(queries),
            detail="SERP concluído; consolidando destaque do domínio, limitações e relatório geral",
        )
        _enrich_serp_reports(workspace, issues, found)

        report = workspace / "report" / "search-intelligence.html"
        state.search_last_duration_seconds = duration
        state.search_last_report = str(report) if report.is_file() else ""
        limited = bool(any_nonzero or issues or runner_errors or not report.is_file())
        if limited:
            state.search_last_status = "COMPLETE_WITH_LIMITATIONS"
            details: list[str] = []
            for item in issues[:4]:
                code = str(item.get("error_code") or "SERP_PROVIDER_ERROR")
                message = str(item.get("error_message") or "provider error")
                details.append(
                    f"{_serp_issue_category(code, message)} / {code}: {message}"
                )
            details.extend(runner_errors[:2])
            if not report.is_file():
                details.append("search-intelligence.html não foi materializado")
            state.search_last_detail = (
                f"{len(queries)} termo(s); duração SERP={duration:.1f}s; "
                + (" | ".join(details) if details else "uma ou mais consultas retornaram limitação")
            )
        else:
            state.search_last_status = "COMPLETE"
            state.search_last_detail = (
                f"{len(queries)} termo(s) observados; relatório={report.name}; duração SERP={duration:.1f}s"
            )

        _finalize_console_clock(
            state,
            workspace,
            limited=limited,
            detail=(
                "processo finalizado; Search Intelligence registrou limitação detalhada no relatório e no log"
                if limited
                else "processo finalizado incluindo Search Intelligence e atualização final dos relatórios"
            ),
        )
        return 1 if limited else 0

    setattr(execute_search_for_audit, "_rasai_runtime_adherence", True)
    setattr(execute_search_for_audit, "_rasai_original", original)
    search_console.execute_search_for_audit = execute_search_for_audit


def _install_apdex_scope_adherence() -> None:
    try:
        from rasai import cli_extensions, console_m23, m23_cli
        from rasai.m25_runtime import peek_pending_config, set_pending_config
    except Exception:
        return

    original_cli = m23_cli.configured_apdex
    if not bool(getattr(original_cli, "_rasai_device_scope_adherence", False)):
        def configured_apdex(args: Any, env: Any = None):
            result = original_cli(args, env)
            pending = peek_pending_config()
            if pending.enabled:
                set_pending_config(
                    _scope_experience_config(pending, str(getattr(args, "device", "mobile")))
                )
            return result

        setattr(configured_apdex, "_rasai_device_scope_adherence", True)
        setattr(configured_apdex, "_rasai_original", original_cli)
        m23_cli.configured_apdex = configured_apdex
        if getattr(cli_extensions, "configured_apdex", None) is original_cli:
            cli_extensions.configured_apdex = configured_apdex

    original_console = console_m23.experience_from_state
    if not bool(getattr(original_console, "_rasai_device_scope_adherence", False)):
        def experience_from_state(state: Any):
            config = original_console(state)
            return _scope_experience_config(config, str(getattr(state, "device", "mobile")))

        setattr(experience_from_state, "_rasai_device_scope_adherence", True)
        setattr(experience_from_state, "_rasai_original", original_console)
        console_m23.experience_from_state = experience_from_state


def _install_dynamic_provider_contract() -> None:
    try:
        from rasai.dynamic_ai_routing import (
            DynamicContentRemediationRoutingSession,
            DynamicProviderRoutingSession,
        )
    except Exception:
        return
    for cls in (DynamicProviderRoutingSession, DynamicContentRemediationRoutingSession):
        if not hasattr(cls, "name"):
            setattr(cls, "name", property(lambda self: str(self.strategy)))


def install_runtime_adherence_extensions() -> None:
    """Install idempotent runtime-contract fixes before a public command executes."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_dynamic_provider_contract()
    _install_apdex_scope_adherence()
    _install_search_console_adherence()
    _INSTALLED = True
