from __future__ import annotations

from types import SimpleNamespace

import pytest

import rasai.audit_management_console as management
import rasai.console_usability_refinements as usability


class _Console:
    @staticmethod
    def render_header(state) -> None:
        return None


def _item():
    return SimpleNamespace(
        audit_id="AUD-TEST-001",
        size_bytes=1024,
        event_time="2026-09-21T10:00:00+00:00",
        created_at="2026-09-21T10:00:00+00:00",
        fulfillment_processing_status="COMPLETE",
        completion_status="COMPLETE",
        status="COMPLETE",
        domains=("example.com",),
    )


@pytest.mark.parametrize("owner", ["base", "usability"])
def test_management_menu_t_does_not_read_n_selection_buffer(monkeypatch, owner: str) -> None:
    state = SimpleNamespace(
        audits_root="audits",
        operation="",
        status="",
        error="",
    )
    item = _item()
    deleted: list[tuple[tuple[str, ...], bool]] = []

    monkeypatch.setattr(management, "inventory", lambda root: (item,))
    monkeypatch.setattr(management, "filter_inventory", lambda items, filters: items)
    monkeypatch.setattr(management, "_delete", lambda console, state, ids, all_audits=False: deleted.append((tuple(ids), all_audits)))
    monkeypatch.setattr(management, "_domains_label", lambda current: "example.com")
    monkeypatch.setattr(management, "_size_label", lambda value: "1 KB")

    answers = iter(["T", "V"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    if owner == "base":
        management._management_menu(_Console, state)
    else:
        usability._management_menu(_Console, state)

    assert deleted == [(("AUD-TEST-001",), True)]


@pytest.mark.parametrize("owner", ["base", "usability"])
def test_management_menu_n_allows_v_without_changing_selection(monkeypatch, owner: str) -> None:
    state = SimpleNamespace(
        audits_root="audits",
        operation="",
        status="",
        error="",
    )
    item = _item()
    toggles: list[str] = []

    monkeypatch.setattr(management, "inventory", lambda root: (item,))
    monkeypatch.setattr(management, "filter_inventory", lambda items, filters: items)
    monkeypatch.setattr(management, "_toggle_indexes", lambda raw, filtered, selected: toggles.append(raw))
    monkeypatch.setattr(management, "_domains_label", lambda current: "example.com")
    monkeypatch.setattr(management, "_size_label", lambda value: "1 KB")

    answers = iter(["N", "V", "V"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    if owner == "base":
        management._management_menu(_Console, state)
    else:
        usability._management_menu(_Console, state)

    assert toggles == []
