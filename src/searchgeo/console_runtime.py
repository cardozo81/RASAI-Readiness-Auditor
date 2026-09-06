"""Live runtime observation for the optional interactive console."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import sqlite3
import subprocess
import threading
import time

from searchgeo import __version__
from searchgeo.console_config import State, build_command, environment_summary, preflight, PROVIDERS
from searchgeo.console_cost import estimate_exposure, persist_execution_projection
from searchgeo.console_ui import BLUE, CYAN, DIM, GREEN, MAGENTA, RED, YELLOW, clear_screen, paint, status_color


@dataclass(slots=True)
class _RunTiming:
    started_at: datetime
    started_monotonic: float
    finished_at: datetime | None = None
    duration_seconds: float | None = None


@dataclass(slots=True)
class _RunProgress:
    label: str
    percent: float | None
    detail: str = ""
    exact: bool = False


_RUN_TIMINGS: dict[int, _RunTiming] = {}
_RUN_PROGRESS: dict[int, _RunProgress] = {}
_PHASE_PROGRESS: dict[str, tuple[str, float]] = {
    "STARTING": ("Preparação da execução", 2.0),
    "INITIALIZING": ("Inicialização da auditoria", 5.0),
    "DISCOVERING": ("Descoberta de URLs e recursos", 10.0),
    "ACQUIRING": ("Aquisição HTTP e renderização", 22.0),
    "ANALYZING": ("Extração, regras e análise semântica", 42.0),
    "COMPARING": ("Comparação de contextos/dispositivos", 56.0),
    "SCORING": ("Cálculo de score e confiabilidade", 66.0),
    "RECOMMENDING": ("Priorização e recomendações", 74.0),
    "REPORTING": ("Geração do relatório base", 82.0),
    "WEB_PERFORMANCE": ("Web Performance externo", 88.0),
    "SYNTHETIC_APDEX": ("Synthetic Apdex", 92.0),
    "SOURCE_BLOCKED": ("Bloqueio técnico da origem", 100.0),
    "FINALIZING": ("Enriquecimentos e finalização", 97.0),
    "COMPLETE": ("Concluído", 100.0),
    "COMPLETE_WITH_LIMITATIONS": ("Concluído com limitações", 100.0),
    "FAILED": ("Falha de execução", 100.0),
}


def set_runtime_progress(state: State, label: str, percent: float | None, *, detail: str = "", exact: bool = False) -> None:
    bounded = None if percent is None else min(max(float(percent), 0.0), 100.0)
    _RUN_PROGRESS[id(state)] = _RunProgress(label=label, percent=bounded, detail=detail, exact=exact)


def clear_runtime_progress(state: State) -> None:
    _RUN_PROGRESS.pop(id(state), None)


def runtime_progress_summary(state: State) -> _RunProgress | None:
    progress = _RUN_PROGRESS.get(id(state))
    if progress is not None:
        return progress
    phase = _PHASE_PROGRESS.get(state.status.upper())
    if phase is None:
        return None
    label, percent = phase
    return _RunProgress(label=label, percent=percent, exact=False)


def _set_phase_progress(state: State, *, detail: str = "") -> None:
    phase = _PHASE_PROGRESS.get(state.status.upper())
    if phase is not None:
        label, percent = phase
        set_runtime_progress(state, label, percent, detail=detail, exact=False)


def _start_timing(state: State) -> None:
    _RUN_TIMINGS[id(state)] = _RunTiming(datetime.now().astimezone(), time.monotonic())
    clear_runtime_progress(state)
    set_runtime_progress(state, "Preparação da execução", 2.0, exact=False)


def _finish_timing(state: State) -> None:
    timing = _RUN_TIMINGS.get(id(state))
    if timing is None or timing.finished_at is not None:
        return
    timing.finished_at = datetime.now().astimezone()
    timing.duration_seconds = max(time.monotonic() - timing.started_monotonic, 0.0)


def _format_duration(seconds: float) -> str:
    total = max(int(round(seconds)), 0)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def timing_summary(state: State) -> tuple[str, str, str] | None:
    timing = _RUN_TIMINGS.get(id(state))
    if timing is None:
        return None
    elapsed = timing.duration_seconds if timing.duration_seconds is not None else max(time.monotonic() - timing.started_monotonic, 0.0)
    started = timing.started_at.strftime("%Y-%m-%d %H:%M:%S %z")
    finished = timing.finished_at.strftime("%Y-%m-%d %H:%M:%S %z") if timing.finished_at else "-"
    return started, finished, _format_duration(elapsed)


def _operation_color(operation: str) -> str:
    upper = operation.upper()
    if upper.startswith("API:"):
        return MAGENTA
    if upper.startswith("INTEGRATION:"):
        return CYAN
    if upper.startswith("LOCAL:"):
        return BLUE
    return YELLOW


def _colored_environment_item(item: str) -> str:
    upper = item.upper()
    if "=[SET]" in upper:
        return paint(item, GREEN, bold=True)
    value = item.rsplit("=", 1)[-1].strip().casefold() if "=" in item else ""
    if value in {"true", "1", "yes", "on"}:
        return paint(item, GREEN, bold=True)
    if value in {"false", "0", "no", "off"}:
        return paint(item, DIM)
    return paint(item, CYAN)


def render_header(state: State) -> None:
    clear_screen()
    print("=" * 100)
    print(f"SearchGEO Readiness Auditor | versão {__version__}")
    print(f"Status      : {paint(state.status, status_color(state.status), bold=True)}")
    print(f"URL         : {state.current_url}")
    print(f"Dispositivo : {paint(state.current_device, CYAN)}")
    print(f"Operação    : {paint(state.operation, _operation_color(state.operation), bold=True)}")
    variables = environment_summary()
    print(
        "Ambiente    : "
        + (
            " | ".join(_colored_environment_item(item) for item in variables)
            if variables
            else paint("nenhuma variável relevante configurada", DIM)
        )
    )
    timing = timing_summary(state)
    if timing:
        started, finished, duration = timing
        print(f"Início      : {started}")
        print(f"Fim         : {finished}")
        print(f"Duração     : {paint(duration, CYAN, bold=True)}")
    progress = runtime_progress_summary(state)
    if progress:
        print(f"Etapa       : {paint(progress.label, CYAN, bold=True)}")
        if progress.percent is not None:
            prefix = "" if progress.exact else "~"
            qualifier = "medido" if progress.exact else "estimativa por etapa"
            print(
                f"Progresso   : {paint(f'{prefix}{progress.percent:.0f}%', GREEN if progress.exact else CYAN, bold=True)} "
                f"[{qualifier}]"
            )
        if progress.detail:
            print(f"Detalhe     : {progress.detail}")
    if state.error:
        print(f"Erro        : {paint(state.error, RED, bold=True)}")
    print("=" * 100)


def _audit_dirs(root: Path) -> set[Path]:
    return {path for path in root.iterdir() if path.is_dir() and path.name.startswith("AUD-")} if root.is_dir() else set()


def _new_workspace(root: Path, before: set[Path]) -> Path | None:
    found = _audit_dirs(root) - before
    return max(found, key=lambda path: path.stat().st_mtime_ns) if found else None


def _tail_text_lines(path: Path, *, max_bytes: int = 32768) -> list[str]:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            start = max(size - max_bytes, 0)
            stream.seek(start)
            payload = stream.read()
    except OSError:
        return []
    lines = payload.decode("utf-8", errors="replace").splitlines()
    return lines[1:] if start and lines else lines


def _last_log_event(workspace: Path) -> dict[str, object] | None:
    path = workspace / "logs" / "audit.log"
    if not path.is_file():
        return None
    for line in reversed(_tail_text_lines(path)[-80:]):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _completion_status(workspace: Path) -> str | None:
    database = workspace / "audit.db"
    if not database.is_file():
        return None
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.2)
        try:
            row = connection.execute(
                "SELECT completion_status FROM audits ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    return str(row[0]) if row and row[0] else None


def observe_workspace(workspace: Path, state: State) -> None:
    database = workspace / "audit.db"
    progress_detail = ""
    if database.is_file():
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.2)
            connection.row_factory = sqlite3.Row
            try:
                row = connection.execute(
                    "SELECT audit_id,status FROM audits ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if row:
                    state.audit_id = str(row["audit_id"])
                    state.status = str(row["status"])
                snapshot = connection.execute(
                    """SELECT p.normalized_url,ps.device FROM page_snapshots ps
                       JOIN pages p ON p.page_id=ps.page_id
                       ORDER BY ps.captured_at DESC LIMIT 1"""
                ).fetchone()
                if snapshot:
                    state.current_url = str(snapshot["normalized_url"])
                    state.current_device = str(snapshot["device"])
                try:
                    page_count = int(connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0])
                    snapshot_count = int(connection.execute("SELECT COUNT(*) FROM page_snapshots").fetchone()[0])
                    progress_detail = f"{page_count} página(s) materializada(s); {snapshot_count} snapshot(s)"
                except sqlite3.Error:
                    pass
                if state.status.upper() == "ANALYZING":
                    try:
                        ai_attempt = connection.execute(
                            "SELECT provider,url,device FROM ai_provider_attempts ORDER BY started_at DESC LIMIT 1"
                        ).fetchone()
                    except sqlite3.Error:
                        ai_attempt = None
                    if ai_attempt:
                        state.operation = f"API:{ai_attempt['provider']}"
                        state.current_url = str(ai_attempt["url"] or state.current_url)
                        state.current_device = str(ai_attempt["device"] or state.current_device)
            finally:
                connection.close()
        except (sqlite3.Error, OSError):
            pass

    status = state.status.upper()
    if status == "ANALYZING" and not state.operation.startswith("API:"):
        state.operation = f"API:{state.ai_provider.upper()}" if state.ai_provider != "none" else "LOCAL:SEMANTIC_RULES"
    elif status in {"DISCOVERING", "ACQUIRING"}:
        state.operation = "INTEGRATION:HTTP"
    elif status in {"COMPARING", "SCORING", "RECOMMENDING"}:
        state.operation = "LOCAL:RULES/SCORE"
    elif status == "REPORTING":
        state.operation = "LOCAL:REPORT"
    _set_phase_progress(state, detail=progress_detail)

    event = _last_log_event(workspace)
    if not event:
        return
    name = str(event.get("event") or "")
    if name == "SOURCE_QUALITY_BLOCKED":
        blockers = ", ".join(str(item) for item in event.get("blockers", []) if str(item)) or "origem indisponível"
        state.status, state.operation = "SOURCE_BLOCKED", "LOCAL:SOURCE_DIAGNOSTIC"
        set_runtime_progress(
            state,
            "Bloqueio técnico da origem",
            100.0,
            detail=f"{blockers}; etapas repetitivas/externas serão interrompidas",
            exact=True,
        )
    elif name == "SOURCE_QUALITY_DOWNSTREAM_SKIPPED":
        component = str(event.get("component") or "etapa dependente")
        blockers = ", ".join(str(item) for item in event.get("blockers", []) if str(item)) or "bloqueio técnico"
        state.status, state.operation = "SOURCE_BLOCKED", "LOCAL:FAIL_FAST"
        set_runtime_progress(
            state,
            "Bloqueio técnico preservado",
            100.0,
            detail=f"{component} não executado por {blockers}; sem tentativas redundantes",
            exact=True,
        )
    elif name == "M21_STARTED" and event.get("enabled"):
        state.status, state.operation = "WEB_PERFORMANCE", "API:PAGESPEED/CRUX"
        set_runtime_progress(
            state,
            "Web Performance externo",
            88.0,
            detail="coleta externa PageSpeed/CrUX",
            exact=False,
        )
    elif name == "M21_EXTERNAL_ATTEMPT":
        state.status = "WEB_PERFORMANCE"
        state.operation = f"API:{event.get('service', 'EXTERNAL')}"
        state.current_url = str(event.get("url") or state.current_url)
        state.current_device = str(event.get("device") or state.current_device)
        service = str(event.get("service") or "EXTERNAL")
        set_runtime_progress(
            state,
            "Web Performance externo",
            88.0,
            detail=f"chamada {service} em {state.current_device}",
            exact=False,
        )
    elif name == "M21_COMPLETED":
        if str(event.get("status") or "") == "SKIPPED_SOURCE_BLOCKER":
            state.status, state.operation = "SOURCE_BLOCKED", "LOCAL:FAIL_FAST"
            set_runtime_progress(
                state,
                "Web Performance não executado",
                100.0,
                detail="bloqueio técnico da origem detectado antes de chamadas externas",
                exact=True,
            )
        else:
            state.status, state.operation = "FINALIZING", "LOCAL:REPORT_ENRICHMENT"
            set_runtime_progress(state, "Enriquecimentos e finalização", 97.0, exact=False)
    elif name == "AUDIT_FAILED":
        state.status, state.operation = "FAILED", "LOCAL:ERROR"
        set_runtime_progress(state, "Falha de execução", 100.0, exact=True)


def apply_runtime_provider_blocks(workspace: Path, state: State) -> None:
    database = workspace / "audit.db"
    if not database.is_file():
        return
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.2)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT provider_states FROM ai_audit_sessions ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            states = json.loads(str(row["provider_states"])) if row else {}
            if not isinstance(states, dict):
                return
            for provider, runtime_state in states.items():
                selection = str(provider).casefold()
                if runtime_state != "QUARANTINED_FOR_AUDIT" or selection not in PROVIDERS:
                    continue
                attempt = connection.execute(
                    """SELECT status,error_class,http_status,error_type,error_code
                       FROM ai_provider_attempts WHERE provider=? ORDER BY started_at DESC LIMIT 1""",
                    (str(provider).upper(),),
                ).fetchone()
                if not attempt:
                    state.runtime_blocks[selection] = "provider quarantined"
                    continue
                parts = [str(attempt["error_class"] or attempt["status"] or "UNAVAILABLE")]
                if attempt["http_status"] is not None:
                    parts.append(f"HTTP {attempt['http_status']}")
                if attempt["error_code"]:
                    parts.append(str(attempt["error_code"]))
                elif attempt["error_type"]:
                    parts.append(str(attempt["error_type"]))
                state.runtime_blocks[selection] = "/".join(parts)
        finally:
            connection.close()
    except (sqlite3.Error, OSError, json.JSONDecodeError):
        pass


def _read_output(stream, output_queue: queue.Queue[str]) -> None:
    for line in iter(stream.readline, ""):
        output_queue.put(line.rstrip())
    stream.close()


def run_audit_from_console(state: State) -> int:
    # stdout remains captured for error recovery and audit.log remains the complete
    # technical trace. The normal single-screen UX intentionally does not dump raw logs.
    state.error, state.output, state.audit_id = "", [], ""
    try:
        targets = preflight(state)
    except (OSError, ValueError, UnicodeError) as exc:
        state.status, state.operation, state.error = "PRECHECK_FAILED", "LOCAL:PRECHECK", str(exc)
        return 2

    projection = estimate_exposure(state)
    projected_at = datetime.now().astimezone().isoformat()
    state.current_url = targets[0] if len(targets) == 1 else f"{targets[0]} (+{len(targets)-1})"
    state.current_device = state.device.upper()
    state.status, state.operation = "STARTING", "LOCAL:PRECHECK_OK"
    root = Path(state.audits_root)
    before = _audit_dirs(root)
    output_queue: queue.Queue[str] = queue.Queue()
    _start_timing(state)
    try:
        process = subprocess.Popen(
            build_command(state),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=dict(os.environ),
        )
    except OSError as exc:
        _finish_timing(state)
        state.status, state.operation, state.error = "START_FAILED", "LOCAL:SUBPROCESS", str(exc)
        return 2
    assert process.stdout is not None
    thread = threading.Thread(target=_read_output, args=(process.stdout, output_queue), daemon=True)
    thread.start()
    workspace: Path | None = None

    while process.poll() is None:
        while True:
            try:
                line = output_queue.get_nowait()
            except queue.Empty:
                break
            if line:
                state.output.append(line)
                state.output[:] = state.output[-12:]
        workspace = workspace or _new_workspace(root, before)
        if workspace:
            observe_workspace(workspace, state)
        render_header(state)
        if state.audit_id:
            print(f"Audit ID    : {state.audit_id}")
        print(f"Log técnico: {(workspace / 'logs' / 'audit.log') if workspace else 'será informado ao criar a auditoria'}")
        time.sleep(1.0)

    thread.join(timeout=1)
    while True:
        try:
            line = output_queue.get_nowait()
        except queue.Empty:
            break
        if line:
            state.output.append(line)
            state.output[:] = state.output[-20:]
    workspace = workspace or _new_workspace(root, before)
    if workspace:
        observe_workspace(workspace, state)
        apply_runtime_provider_blocks(workspace, state)

    code = int(process.returncode or 0)
    completion = _completion_status(workspace) if workspace else None
    if code == 0:
        final_status = completion or "COMPLETE"
        if final_status not in {"COMPLETE", "COMPLETE_WITH_LIMITATIONS"}:
            final_status = "COMPLETE"
        state.status = final_status
        state.operation = "LOCAL:DONE"
        label = "Concluído com limitações" if final_status == "COMPLETE_WITH_LIMITATIONS" else "Concluído"
        detail = (
            "processo finalizado; consulte as limitações e o diagnóstico técnico no relatório"
            if final_status == "COMPLETE_WITH_LIMITATIONS"
            else "processo finalizado"
        )
    else:
        state.status, state.operation = "FAILED", "LOCAL:ERROR"
        if state.output:
            state.error = state.output[-1]
        label = "Falha de execução"
        detail = "processo finalizado com erro; consulte o log técnico"
    set_runtime_progress(state, label, 100.0, detail=detail, exact=True)
    _finish_timing(state)

    timing = _RUN_TIMINGS.get(id(state))
    if workspace and timing and timing.finished_at is not None and timing.duration_seconds is not None:
        persist_execution_projection(
            workspace,
            state,
            projection,
            projected_at=projected_at,
            started_at=timing.started_at.isoformat(),
            finished_at=timing.finished_at.isoformat(),
            duration_ms=max(int(round(timing.duration_seconds * 1000)), 0),
        )

    render_header(state)
    if state.audit_id:
        print(f"Audit ID    : {state.audit_id}")
    if workspace:
        print(f"Log técnico: {workspace / 'logs' / 'audit.log'}")
        print(f"Relatórios : {workspace / 'report'}")
    return code
