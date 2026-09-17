"""Focused regression for HOME -> Prepare audit after late console composition."""
from __future__ import annotations

import builtins
from types import ModuleType, SimpleNamespace

from rasai import post_smoke_hotfix


def test_preparation_route_guard_reasserts_catalog_owner(monkeypatch) -> None:
    from rasai import (
        console_catalog_ui,
        console_catalog_workflow,
        console_entrypoint,
        console_navigation,
        interactive_console,
    )

    calls: list[object] = []

    def detail_install() -> None:
        calls.append("detail")

    def catalog_install(console: object) -> None:
        calls.append(("catalog", console))

    def canonical_preparation(console: object, state: object, detailed: object = None) -> str:
        del console, state, detailed
        return "R"

    monkeypatch.setattr(console_entrypoint, "install_console_detail_presentation", detail_install)
    monkeypatch.setattr(console_catalog_workflow, "install", catalog_install)
    monkeypatch.setattr(console_catalog_ui, "preparation_menu", canonical_preparation)
    monkeypatch.setattr(console_navigation, "_preparation_menu", lambda *args, **kwargs: "OLD")

    post_smoke_hotfix._install_console_preparation_route_guard()
    console_entrypoint.install_console_detail_presentation()

    assert calls == ["detail", ("catalog", interactive_console)]
    assert console_navigation._preparation_menu is canonical_preparation

    fake = ModuleType("preparation_route_guard_console")
    fake.render_header = lambda state: None
    fake._menu = lambda state: "Q"
    console_navigation.install(fake)
    state = SimpleNamespace(
        project="Projeto",
        target="https://example.com/",
        audit_id="",
        audits_root="audits",
        error="",
    )
    answers = iter(["1"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))

    assert fake._menu(state) == "R"
