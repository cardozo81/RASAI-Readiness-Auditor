"""Move local-console Search Intelligence into the child AUD collection phase.

The historical console wrapper executed SERP work after the audit subprocess had
already completed.  This adapter keeps the same transient user inputs but serializes
them as explicit CLI execution arguments, suppresses the old post-AUD execution and
projects the persisted in-AUD result back into the console state.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any


_INSTALLED = False


def _append_search_args(command: list[str], state: Any) -> list[str]:
    queries = tuple(
        getattr(state, "_governed_search_queries", ())
        or getattr(state, "search_queries", ())
        or ()
    )
    if not queries:
        return command
    output = list(command)
    for query in queries:
        text = " ".join(str(query).split())
        if text:
            output.extend(("--search-query", text))
    output.extend(("--search-depth", str(int(getattr(state, "search_depth", 20) or 20))))
    region = str(getattr(state, "search_region", "") or "").strip()
    if region:
        output.extend(("--search-region", region))
    output.extend(("--search-device", str(getattr(state, "search_device", "mobile") or "mobile")))
    output.append(
        "--search-competitive"
        if bool(getattr(state, "search_competitive", True))
        else "--no-search-competitive"
    )
    return output


def _project_result(state: Any) -> None:
    audit_id = str(getattr(state, "audit_id", "") or "").strip()
    if not audit_id:
        return
    root = Path(str(getattr(state, "audits_root", "audits") or "audits")) / audit_id
    database = root / "audit.db"
    if not database.is_file():
        return
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            row = connection.execute(
                """SELECT status,result_ref,error_message FROM audit_fulfillment_work_items
                   WHERE audit_id=? AND component='SEARCH_INTELLIGENCE'
                   ORDER BY updated_at DESC,rowid DESC LIMIT 1""",
                (audit_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
    finally:
        connection.close()
    if row is None:
        state.search_last_status = "NOT_REQUESTED"
        return
    status = str(row["status"] or "UNKNOWN").upper()
    state.search_last_status = "COMPLETE" if status == "SUCCESS" else "COMPLETE_WITH_LIMITATIONS"
    state.search_last_detail = str(row["error_message"] or "")
    result_ref = str(row["result_ref"] or "")
    if result_ref:
        state.search_last_report = str(root / result_ref)
    elif (root / "report" / "search-intelligence.html").is_file():
        state.search_last_report = str(root / "report" / "search-intelligence.html")


def install(console_module: Any) -> None:
    global _INSTALLED
    if _INSTALLED or getattr(console_module, "_rasai_governed_search_runtime", False):
        return

    original_build = console_module.build_command
    original_run = console_module.run_audit_from_console

    def build_command(state: Any) -> list[str]:
        return _append_search_args(list(original_build(state)), state)

    def run_audit_from_console(state: Any) -> int:
        queries = tuple(getattr(state, "search_queries", ()) or ())
        if not queries:
            return int(original_run(state) or 0)

        # The inner historical Search wrapper checks search_queries after the subprocess
        # and would otherwise execute a duplicate SERP collection.  Keep the values in a
        # private execution snapshot for build_command while presenting an empty tuple to
        # that obsolete post-AUD branch.
        state._governed_search_queries = queries
        state.search_queries = ()
        try:
            code = int(original_run(state) or 0)
        finally:
            state.search_queries = queries
            try:
                delattr(state, "_governed_search_queries")
            except AttributeError:
                pass
        _project_result(state)
        return code

    build_command._rasai_governed_search = True
    build_command._rasai_original = original_build
    run_audit_from_console._rasai_governed_search = True
    run_audit_from_console._rasai_original = original_run
    console_module.build_command = build_command
    console_module.run_audit_from_console = run_audit_from_console
    console_module._rasai_governed_search_runtime = True
    _INSTALLED = True


__all__ = ["install"]
