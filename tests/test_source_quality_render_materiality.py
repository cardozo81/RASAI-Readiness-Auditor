from __future__ import annotations

from rasai.browser_identity_renderer import BrowserIdentityRenderer
from rasai.render_materiality import (
    CaptureQualityState,
    observe_materiality,
    resolve_capture_quality,
)


class _SequencePage:
    def __init__(self, html_values: list[str]) -> None:
        self._values = list(html_values)
        self.waits: list[int] = []

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)

    def content(self) -> str:
        if len(self._values) > 1:
            return self._values.pop(0)
        return self._values[0]


def test_short_valid_page_is_ready_without_recovery_even_after_bounded_settle_timeout() -> None:
    html = "<html><body><main><h1>Contato</h1><a href='/'>Entrar</a></main></body></html>"
    page = _SequencePage([html])

    final_html, quality = resolve_capture_quality(
        page,
        html,
        settle_outcome="BOUNDED_TIMEOUT",
    )

    assert final_html == html
    assert quality["state"] == CaptureQualityState.READY.value
    assert quality["reason"] == "NO_TRANSIENT_RENDER_SIGNAL"
    assert quality["recovery"]["attempted"] is False
    assert page.waits == []


def test_spa_skeleton_materializes_with_bounded_recovery() -> None:
    initial = (
        "<html><body><div id='app'><main aria-busy='true'>"
        "<div class='skeleton loading-placeholder'></div></main></div></body></html>"
    )
    materialized = (
        "<html><body><div id='app'><main>"
        "<h1>Seguro de Vida</h1><p>Conteúdo principal materializado.</p>"
        "</main></div></body></html>"
    )
    page = _SequencePage([materialized])

    final_html, quality = resolve_capture_quality(
        page,
        initial,
        settle_outcome="BOUNDED_TIMEOUT",
    )

    assert final_html == materialized
    assert quality["state"] == CaptureQualityState.RECOVERED.value
    assert quality["reason"] == "TRANSIENT_RENDER_MATERIALIZED"
    assert quality["recovery"]["attempted"] is True
    assert quality["recovery"]["observation_count"] == 1
    assert quality["recovery"]["bounded_wait_ms"] == 250
    assert quality["growth"]["materialized"] is True
    assert quality["initial"]["transient_markers"] > quality["final"]["transient_markers"]


def test_persistent_skeleton_is_incomplete_after_fixed_bound() -> None:
    skeleton = (
        "<html><body><div id='app'><main aria-busy='true'>"
        "<div class='skeleton shimmer'></div></main></div></body></html>"
    )
    page = _SequencePage([skeleton])

    final_html, quality = resolve_capture_quality(
        page,
        skeleton,
        settle_outcome="BOUNDED_TIMEOUT",
    )

    assert final_html == skeleton
    assert quality["state"] == CaptureQualityState.INCOMPLETE.value
    assert quality["reason"] == "TRANSIENT_RENDER_PERSISTED"
    assert quality["recovery"]["observation_count"] == 4
    assert quality["recovery"]["bounded_wait_ms"] == 1000
    assert quality["recovery"]["max_wait_ms"] == 1000
    assert page.waits == [250, 250, 250, 250]


def test_lazy_marker_plus_settle_timeout_can_recover_after_dom_growth() -> None:
    initial = "<html><body><main><img loading='lazy' data-src='hero.jpg'></main></body></html>"
    materialized = (
        "<html><body><main><img loading='lazy' src='hero.jpg'><article>"
        + ("Conteúdo útil da aplicação. " * 30)
        + "</article></main></body></html>"
    )
    page = _SequencePage([materialized])

    _, quality = resolve_capture_quality(
        page,
        initial,
        settle_outcome="BOUNDED_TIMEOUT",
    )

    assert quality["state"] == CaptureQualityState.RECOVERED.value
    assert quality["growth"]["text_delta"] > 0
    assert quality["growth"]["dom_nodes_delta"] > 0


def test_nested_main_content_is_measured_as_primary_content() -> None:
    observation = observe_materiality(
        "<html><body><main><section><div><p>Texto principal</p></div></section></main></body></html>"
    )
    assert observation.main_present is True
    assert observation.main_text_length == len("Texto principal")


class _FakeResponse:
    status = 200
    headers = {"content-type": "text/html; charset=utf-8"}


class _FakePage:
    url = "https://example.test/"
    main_frame = object()

    def __init__(self) -> None:
        self._content = [
            "<html><body><main aria-busy='true'><div class='skeleton'></div></main></body></html>",
            "<html><body><main><h1>Pronto</h1><p>Conteúdo materializado.</p></main></body></html>",
        ]

    def on(self, *_args) -> None:
        return None

    def goto(self, *_args, **_kwargs):
        return _FakeResponse()

    def wait_for_load_state(self, *_args, **_kwargs) -> None:
        return None

    def wait_for_timeout(self, _milliseconds: int) -> None:
        return None

    def content(self) -> str:
        if len(self._content) > 1:
            return self._content.pop(0)
        return self._content[0]

    def screenshot(self, **_kwargs) -> bytes:
        return b"PNG"

    def close(self) -> None:
        return None


class _FakeContext:
    def __init__(self, page: _FakePage) -> None:
        self.page = page

    def new_page(self) -> _FakePage:
        return self.page

    def close(self) -> None:
        return None


class _FakeBrowser:
    version = "151.0.0.0"

    def __init__(self, page: _FakePage) -> None:
        self.page = page

    def new_context(self, **_kwargs) -> _FakeContext:
        return _FakeContext(self.page)


def test_identity_renderer_projects_capture_quality_in_browser_metadata() -> None:
    page = _FakePage()
    renderer = BrowserIdentityRenderer()
    renderer._browser = _FakeBrowser(page)
    renderer._capture_element_observations = lambda _page: ()

    result = renderer._render_once(
        url="https://example.test/",
        profile=__import__("rasai.rendering", fromlist=["DESKTOP_PROFILE"]).DESKTOP_PROFILE,
        options={},
        identity={"user_agent": "test", "locale": "pt-BR"},
    )

    assert result.succeeded is True
    assert result.browser_metadata["capture_quality"]["state"] == "RECOVERED"
    assert "Conteúdo materializado" in (result.rendered_html or "")
