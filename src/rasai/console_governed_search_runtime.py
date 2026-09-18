"""Move local-console Search Intelligence into the child AUD collection phase.

The historical console wrapper executed SERP work after the audit subprocess had
already completed. This adapter keeps the same transient user inputs but serializes
them as explicit CLI execution arguments, suppresses the old post-AUD execution and
projects the persisted in-AUD result back into the console state.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Sequence


_INSTALLED = False


def _append_search_args(
    command: list[str],
    state: Any,
    *,
    queries: Sequence[str] | None = None,
) -> list[str]:
    effective_queries = tuple(
        queries if queries is not None else (getattr(state, "search_queries", ()) or ())
    )
    if not effective_queries:
        return command
    output = list(command)
    for query in effective_queries:
        text = " ".join(str(query).split())
        if text:
            output.extend(("--search-query", text))
    output.extend(("--search-depth", str(int(getattr(state, "search_depth", 20) or 20))))
    region = str(getattr(state, "search_region", "") or "").strip()
    if region:
        output.extend(("--search-region", region))
    output.extend(
        ("--search-device", str(getattr(state, "search_device", "mobile") or "mobile"))
    )
    output.append(
        "--search-competitive"
        if bool(getattr(state, "search_competitive", True))
        else "--no-search-competitive"
    )
    output.append(
        "--search-compare-content"
        if bool(getattr(state, "search_compare_content", False))
        else "--no-search-compare-content"
    )
    output.extend(("--search-max-content-pages", str(int(getattr(state, "search_max_content_pages", 3)))))
    output.extend(("--search-content-timeout-seconds", str(float(getattr(state, "search_content_timeout_seconds", 10.0)))))
    output.extend(("--search-content-max-bytes", str(int(getattr(state, "search_content_max_bytes", 2_000_000)))))
    output.extend(("--search-content-max-redirects", str(int(getattr(state, "search_content_max_redirects", 5)))))
    output.append(
        "--search-ai-competitive"
        if bool(getattr(state, "search_ai_competitive", False))
        else "--no-search-ai-competitive"
    )
    output.extend(("--search-ymyl-mode", str(getattr(state, "search_ymyl_mode", "AUTO") or "AUTO").upper()))
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
                """SELECT status,effective_result_ref,last_error_message
                   FROM audit_fulfillment_work_items
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
    state.search_last_status = (
        "COMPLETE" if status == "SUCCESS" else "COMPLETE_WITH_LIMITATIONS"
    )
    state.search_last_detail = str(row["last_error_message"] or "")
    result_ref = str(row["effective_result_ref"] or "")
    if result_ref and ":" not in result_ref:
        state.search_last_report = str(root / result_ref)
    elif (root / "report" / "search-intelligence.html").is_file():
        state.search_last_report = str(root / "report" / "search-intelligence.html")


def install(console_module: Any) -> None:
    global _INSTALLED
    if _INSTALLED or getattr(console_module, "_rasai_governed_search_runtime", False):
        return

    original_run = console_module.run_audit_from_console

    def run_audit_from_console(state: Any) -> int:
        queries = tuple(getattr(state, "search_queries", ()) or ())
        if not queries:
            return int(original_run(state) or 0)

        from rasai import console_runtime

        original_build = console_runtime.build_command

        def governed_build(current: Any) -> list[str]:
            return _append_search_args(
                list(original_build(current)),
                current,
                queries=queries,
            )

        governed_build._rasai_governed_search = True
        governed_build._rasai_original = original_build

        # The inner historical Search wrapper checks search_queries after the subprocess
        # and would otherwise execute duplicate SERP collection. Keep the terms in this
        # execution closure for command construction while presenting an empty tuple to
        # that obsolete post-AUD branch. Console state classes use slots=True, so runtime
        # orchestration data must not be attached dynamically to the state object.
        state.search_queries = ()
        console_runtime.build_command = governed_build
        try:
            code = int(original_run(state) or 0)
        finally:
            console_runtime.build_command = original_build
            state.search_queries = queries
        _project_result(state)
        return code

    run_audit_from_console._rasai_governed_search = True
    run_audit_from_console._rasai_original = original_run
    console_module.run_audit_from_console = run_audit_from_console
    console_module._rasai_governed_search_runtime = True
    _INSTALLED = True


__all__ = ["install"]
