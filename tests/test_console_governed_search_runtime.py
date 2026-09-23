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
