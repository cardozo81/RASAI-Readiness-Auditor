from __future__ import annotations

from types import ModuleType

from rasai import console_governed_search_runtime as governed
from rasai import console_runtime
from rasai.console_search_intelligence import SearchConsoleState


def test_governed_search_uses_execution_closure_with_slotted_state(monkeypatch) -> None:
    module = ModuleType("governed_search_test_console")
    observed: dict[str, object] = {}

    def base_build(state) -> list[str]:
        return ["rasai", "audit"]

    def original_run(state) -> int:
        observed["inner_queries"] = state.search_queries
        observed["command"] = console_runtime.build_command(state)
        return 0

    module.run_audit_from_console = original_run
    monkeypatch.setattr(console_runtime, "build_command", base_build)
    monkeypatch.setattr(governed, "_INSTALLED", False)
    governed.install(module)

    state = SearchConsoleState(
        search_queries=("seguro de vida", "previdencia privada"),
        search_depth=30,
        search_region="São Paulo",
        search_device="mobile",
        search_competitive=True,
        search_compare_content=True,
        search_max_content_pages=4,
        search_content_timeout_seconds=12.5,
        search_content_max_bytes=1_500_000,
        search_content_max_redirects=2,
        search_ai_competitive=True,
        search_ymyl_mode="ON",
    )

    assert not hasattr(state, "__dict__")
    assert not hasattr(state, "_governed_search_queries")
    assert module.run_audit_from_console(state) == 0

    assert observed["inner_queries"] == ()
    assert observed["command"] == [
        "rasai",
        "audit",
        "--search-query",
        "seguro de vida",
        "--search-query",
        "previdencia privada",
        "--search-depth",
        "30",
        "--search-region",
        "São Paulo",
        "--search-device",
        "mobile",
        "--search-competitive",
        "--search-compare-content",
        "--search-max-content-pages",
        "4",
        "--search-content-timeout-seconds",
        "12.5",
        "--search-content-max-bytes",
        "1500000",
        "--search-content-max-redirects",
        "2",
        "--search-ai-competitive",
        "--search-ymyl-mode",
        "ON",
    ]
    assert state.search_queries == ("seguro de vida", "previdencia privada")
    assert not hasattr(state, "_governed_search_queries")
    assert console_runtime.build_command is base_build


def test_523_governed_search_result_readonly_and_terminal_distinction(tmp_path):
    import sqlite3
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_governed_search_runtime import _project_result

    state = SearchConsoleState()
    state.audits_root = str(tmp_path)
    state.audit_id = "AUD-SEARCH-523"
    root = tmp_path / state.audit_id
    root.mkdir()
    db = root / "audit.db"
    # No DB may be created merely by reading the post-run status.
    _project_result(state)
    assert not db.exists()

    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE audit_fulfillment_work_items("
            "audit_id TEXT, component TEXT, status TEXT, "
            "updated_at TEXT, last_error_message TEXT)"
        )
        con.executemany(
            "INSERT INTO audit_fulfillment_work_items VALUES (?,?,?,?,?)",
            [
                ("AUD-OTHER", "SEARCH_INTELLIGENCE", "SUCCESS", "2026-10-20", ""),
                (state.audit_id, "SEARCH_INTELLIGENCE", "RUNNING", "2026-10-21",
                 "PRIVATE_TOKEN_SHOULD_NOT_DISPLAY"),
            ],
        )
    before = db.read_bytes()
    _project_result(state)
    assert state.search_last_status == "PENDING"
    assert state.search_last_report == ""
    assert "PRIVATE_TOKEN_SHOULD_NOT_DISPLAY" not in state.search_last_detail
    assert db.read_bytes() == before

    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE audit_fulfillment_work_items SET status='FAILED_RETRYABLE'"
            " WHERE audit_id=?", (state.audit_id,),
        )
    before = db.read_bytes()
    _project_result(state)
    assert state.search_last_status == "COMPLETE_WITH_LIMITATIONS"
    assert db.read_bytes() == before

    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE audit_fulfillment_work_items SET status='SUCCESS'"
            " WHERE audit_id=?", (state.audit_id,),
        )
    _project_result(state)
    assert state.search_last_status == "COMPLETE"
    with sqlite3.connect(db) as con:
        con.execute(
            "DELETE FROM audit_fulfillment_work_items WHERE audit_id=?",
            (state.audit_id,),
        )
    _project_result(state)
    assert state.search_last_status == "NOT_REQUESTED"
    assert "PRIVATE_TOKEN_SHOULD_NOT_DISPLAY" not in state.search_last_detail


def test_523_governed_search_rejects_symlink_schema_error_and_path_traversal(tmp_path):
    import sqlite3
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_governed_search_runtime import _project_result

    state = SearchConsoleState()
    state.audits_root = str(tmp_path)
    state.audit_id = "AUD-SEARCH-523"
    folder = tmp_path / state.audit_id
    folder.mkdir()
    source = tmp_path / "other.db"
    with sqlite3.connect(source) as con:
        con.execute("CREATE TABLE unrelated(value TEXT)")
    linked = folder / "audit.db"
    try:
        linked.symlink_to(source)
    except (OSError, NotImplementedError):
        pass
    else:
        _project_result(state)
        assert state.search_last_status == "NOT_REQUESTED"
        assert source.is_file()
        linked.unlink()
    linked.write_bytes(source.read_bytes())
    _project_result(state)
    assert state.search_last_status == "UNAVAILABLE"
    assert "não verificável" in state.search_last_detail
    assert source.read_bytes() == linked.read_bytes()
    state.audit_id = "../../other"
    _project_result(state)
    assert source.is_file()
