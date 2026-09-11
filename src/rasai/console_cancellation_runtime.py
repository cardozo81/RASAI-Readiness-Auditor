"""Controlled Ctrl+C cancellation for the local interactive console.

The audit runs in a child process.  This adapter starts that child in its own process
group, terminates the full tree on user cancellation, marks the local audit CANCELLED
when a workspace already exists, and leaves a diagnostic event instead of an apparently
stuck ACQUIRING audit.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import signal
import sqlite3
import subprocess
import threading
import time
from typing import Any

_INSTALLED = False


def _popen_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _terminate_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except Exception:
        try:
            process.terminate()
        except Exception:
            pass
    try:
        process.wait(timeout=5)
    except Exception:
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except Exception:
            pass
        try:
            process.wait(timeout=2)
        except Exception:
            pass


def _mark_cancelled(workspace: Path) -> str | None:
    database = workspace / "audit.db"
    audit_id: str | None = None
    if database.is_file():
        try:
            connection = sqlite3.connect(database, timeout=2.0)
            try:
                row = connection.execute(
                    "SELECT audit_id FROM audits ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if row and row[0]:
                    audit_id = str(row[0])
                    connection.execute(
                        "UPDATE audits SET status='CANCELLED' WHERE audit_id=? AND status NOT IN ('COMPLETED','FAILED','CANCELLED')",
                        (audit_id,),
                    )
                    connection.commit()
            finally:
                connection.close()
        except sqlite3.Error:
            pass
    try:
        log = workspace / "logs" / "audit.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "AUDIT_CANCELLED_BY_OPERATOR",
            "level": "WARNING",
            "audit_id": audit_id,
            "reason": "CTRL_C_INTERACTIVE_CONSOLE",
            "process_tree_terminated": True,
        }
        with log.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass
    return audit_id


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import console_runtime as runtime

    def run_audit_from_console(state: Any) -> int:
        state.error, state.output, state.audit_id = "", [], ""
        try:
            targets = runtime.preflight(state)
        except (OSError, ValueError, UnicodeError) as exc:
            state.status, state.operation, state.error = "PRECHECK_FAILED", "LOCAL:PRECHECK", str(exc)
            return 2

        projection = runtime.estimate_exposure(state)
        projected_at = datetime.now().astimezone().isoformat()
        state.current_url = targets[0] if len(targets) == 1 else f"{targets[0]} (+{len(targets)-1})"
        state.current_device = state.device.upper()
        state.status, state.operation = "STARTING", "LOCAL:PRECHECK_OK"
        root = Path(state.audits_root)
        before = runtime._audit_dirs(root)
        output_queue: queue.Queue[str] = queue.Queue()
        runtime._start_timing(state)
        try:
            process = subprocess.Popen(
                runtime.build_command(state),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=dict(os.environ),
                **_popen_kwargs(),
            )
        except OSError as exc:
            runtime._finish_timing(state)
            state.status, state.operation, state.error = "START_FAILED", "LOCAL:SUBPROCESS", str(exc)
            return 2

        assert process.stdout is not None
        thread = threading.Thread(
            target=runtime._read_output, args=(process.stdout, output_queue), daemon=True
        )
        thread.start()
        workspace: Path | None = None
        cancelled = False

        try:
            while process.poll() is None:
                while True:
                    try:
                        line = output_queue.get_nowait()
                    except queue.Empty:
                        break
                    if line:
                        state.output.append(line)
                        state.output[:] = state.output[-12:]
                workspace = workspace or runtime._new_workspace(root, before)
                if workspace:
                    runtime.observe_workspace(workspace, state)
                runtime.render_header(state)
                if state.audit_id:
                    print(f"Audit ID    : {state.audit_id}")
                print(
                    f"Log técnico: {(workspace / 'logs' / 'audit.log') if workspace else 'será informado ao criar a auditoria'}"
                )
                time.sleep(1.0)
        except KeyboardInterrupt:
            cancelled = True
            _terminate_tree(process)
            workspace = workspace or runtime._new_workspace(root, before)
            if workspace:
                state.audit_id = _mark_cancelled(workspace) or state.audit_id
            state.status, state.operation = "CANCELLED", "LOCAL:CANCELLED"
            state.error = "Execução cancelada pelo operador; processo/browser encerrados."
            runtime.set_runtime_progress(
                state,
                "Execução cancelada",
                100.0,
                detail="cancelamento controlado; workspace preservado como evidência incompleta",
                exact=True,
            )
            runtime._finish_timing(state)

        thread.join(timeout=1)
        while True:
            try:
                line = output_queue.get_nowait()
            except queue.Empty:
                break
            if line:
                state.output.append(line)
                state.output[:] = state.output[-20:]

        workspace = workspace or runtime._new_workspace(root, before)
        if cancelled:
            runtime.render_header(state)
            if state.audit_id:
                print(f"Audit ID    : {state.audit_id}")
            if workspace:
                print(f"Log técnico: {workspace / 'logs' / 'audit.log'}")
                print(f"Workspace  : {workspace}")
            return 130

        if workspace:
            runtime.observe_workspace(workspace, state)
            runtime.apply_runtime_provider_blocks(workspace, state)

        code = int(process.returncode or 0)
        completion = runtime._completion_status(workspace) if workspace else None
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
        runtime.set_runtime_progress(state, label, 100.0, detail=detail, exact=True)
        runtime._finish_timing(state)

        timing = runtime._RUN_TIMINGS.get(id(state))
        if workspace and timing and timing.finished_at is not None and timing.duration_seconds is not None:
            runtime.persist_execution_projection(
                workspace,
                state,
                projection,
                projected_at=projected_at,
                started_at=timing.started_at.isoformat(),
                finished_at=timing.finished_at.isoformat(),
                duration_ms=max(int(round(timing.duration_seconds * 1000)), 0),
            )

        runtime.render_header(state)
        if state.audit_id:
            print(f"Audit ID    : {state.audit_id}")
        if workspace:
            print(f"Log técnico: {workspace / 'logs' / 'audit.log'}")
            print(f"Relatórios : {workspace / 'report'}")
        return code

    runtime.run_audit_from_console = run_audit_from_console
    _INSTALLED = True
