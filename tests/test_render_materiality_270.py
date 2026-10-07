from __future__ import annotations

import json

from rasai.render_materiality import (
    CaptureQualityState,
    observe_materiality,
    resolve_capture_quality,
)


class _FakePage:
    def __init__(self, candidates: list[str]) -> None:
        self._candidates = list(candidates)
        self.waits: list[int] = []

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)

    def content(self) -> str:
        if len(self._candidates) > 1:
            return self._candidates.pop(0)
        return self._candidates[0]


def _material_content(*, include_main: bool = False) -> str:
    body = (
        "<section><h1>Seguro de vida com proteção completa</h1>"
        "<p>" + ("Cobertura, assistência, benefícios e orientação para contratação. " * 5) + "</p>"
        "</section>"
    )
    if include_main:
        return "<html><body><main></main>" + body + "</body></html>"
    return "<html><body>" + body + "</body></html>"


def test_chrome_only_without_main_is_not_material_even_above_220_characters() -> None:
    chrome = "Navegação institucional e links auxiliares. " * 10
    html = f"<html><body><nav>{chrome}</nav><footer>{chrome}</footer></body></html>"

    observation = observe_materiality(html)
    _, quality = resolve_capture_quality(
        _FakePage([html]),
        html,
        settle_outcome="NETWORK_IDLE",
    )

    assert observation.text_length > 220
    assert observation.primary_text_length < 80
    assert quality["state"] == CaptureQualityState.INCOMPLETE.value
    assert quality["reason"] == "CHROME_ONLY"
    assert quality["recovery"]["attempted"] is False


def test_real_content_without_main_is_material() -> None:
    html = _material_content()

    observation = observe_materiality(html)
    _, quality = resolve_capture_quality(
        _FakePage([html]),
        html,
        settle_outcome="NETWORK_IDLE",
    )

    assert observation.main_present is False
    assert observation.heading_nodes >= 1
    assert observation.content_nodes >= 2
    assert observation.primary_text_length >= 160
    assert quality["state"] == CaptureQualityState.READY.value
    assert quality["reason"] == "PRIMARY_CONTENT_MATERIAL"


def test_empty_main_with_external_primary_content_is_material() -> None:
    html = _material_content(include_main=True)

    observation = observe_materiality(html)
    _, quality = resolve_capture_quality(
        _FakePage([html]),
        html,
        settle_outcome="NETWORK_IDLE",
    )

    assert observation.main_present is True
    assert observation.main_text_length == 0
    assert quality["state"] == CaptureQualityState.READY.value
    assert quality["reason"] == "EMPTY_MAIN_WITH_EXTERNAL_PRIMARY_CONTENT"


def test_empty_main_with_chrome_and_transient_shell_remains_incomplete() -> None:
    chrome = "Política de cookies, navegação e contatos institucionais. " * 8
    html = (
        "<html><body><div id='root'><main></main>"
        "<div class='skeleton'>Carregando</div>"
        f"<nav>{chrome}</nav><footer>{chrome}</footer>"
        "</div></body></html>"
    )
    page = _FakePage([html, html, html, html])

    _, quality = resolve_capture_quality(
        page,
        html,
        settle_outcome="BOUNDED_TIMEOUT",
    )

    assert quality["state"] == CaptureQualityState.INCOMPLETE.value
    assert quality["recovery"]["attempted"] is True
    assert quality["recovery"]["observation_count"] == 4
    assert quality["recovery"]["bounded_wait_ms"] == 1000
    assert quality["reason"] in {"CHROME_ONLY", "TRANSIENT_SHELL"}


def test_skeleton_that_materializes_within_bound_is_recovered() -> None:
    initial = (
        "<html><body><div id='root'><div class='skeleton'>Carregando</div>"
        "</div></body></html>"
    )
    hydrated = _material_content()
    page = _FakePage([initial, hydrated])

    final_html, quality = resolve_capture_quality(
        page,
        initial,
        settle_outcome="BOUNDED_TIMEOUT",
    )

    assert final_html == hydrated
    assert quality["state"] == CaptureQualityState.RECOVERED.value
    assert quality["reason"] == "SLOW_HYDRATION"
    assert quality["recovery"]["outcome"] == "MATERIALIZED"
    assert quality["recovery"]["observation_count"] == 2
    assert quality["growth"]["primary_text_delta"] > 0


def test_transient_shell_without_evolution_exhausts_only_the_existing_bound() -> None:
    html = (
        "<html><body><div id='root'><div class='skeleton'>Carregando</div>"
        "</div></body></html>"
    )
    page = _FakePage([html, html, html, html])

    _, quality = resolve_capture_quality(
        page,
        html,
        settle_outcome="BOUNDED_TIMEOUT",
    )

    assert quality["state"] == CaptureQualityState.INCOMPLETE.value
    assert page.waits == [250, 250, 250, 250]
    assert quality["recovery"]["outcome"] == "BOUND_EXHAUSTED"
    assert quality["recovery"]["bounded_wait_ms"] == 1000
    assert quality["growth"]["materialized"] is False


def test_materiality_diagnostics_persist_counts_not_page_text_or_secrets() -> None:
    secret = "SECRET-TOKEN-DO-NOT-PERSIST"
    html = (
        "<html><body><nav>" + secret * 20 + "</nav>"
        "<div id='root' class='skeleton'>Carregando</div></body></html>"
    )

    _, quality = resolve_capture_quality(
        _FakePage([html, html, html, html]),
        html,
        settle_outcome="BOUNDED_TIMEOUT",
    )

    serialized = json.dumps(quality, ensure_ascii=False)
    assert secret not in serialized
    assert "text_length" in serialized
    assert "primary_text_length" in serialized
    assert "heading_nodes" in serialized
    assert "content_nodes" in serialized
