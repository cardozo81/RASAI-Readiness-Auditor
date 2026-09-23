from __future__ import annotations

from rasai.console_observability_capability_refinements import (
    _overall_status,
    _source_names,
)


def _clear(monkeypatch) -> None:
    names = {name for values in _source_names().values() for name in values}
    for name in names:
        monkeypatch.delenv(name, raising=False)


def test_observability_sources_match_runtime_and_exclude_dynatrace(monkeypatch) -> None:
    _clear(monkeypatch)
    names = {name for values in _source_names().values() for name in values}
    assert "RASAI_CLARITY_ENABLED" in names
    assert "RASAI_COMMON_CRAWL_ENABLED" in names
    assert "RASAI_CRUX_HISTORY_ENABLED" in names
    assert all("DYNATRACE" not in name for name in names)


def test_observability_default_is_apto_because_common_crawl_is_bounded_on(monkeypatch) -> None:
    _clear(monkeypatch)
    status, detail = _overall_status()
    assert status == "APTO"
    assert "apta" in detail


def test_requested_clarity_without_token_is_configurar(monkeypatch) -> None:
    _clear(monkeypatch)
    monkeypatch.setenv("RASAI_CLARITY_ENABLED", "true")
    status, detail = _overall_status()
    assert status == "CONFIGURAR"
    assert "pendente" in detail
