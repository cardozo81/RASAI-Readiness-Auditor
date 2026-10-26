"""#665: captured-state hidden DOM does not become asserted visible content."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from rasai.extraction import ContentExtractor
from rasai.m4 import _attested_hidden_markers
from rasai.rendering import BrowserRenderer


def _hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


_HTML = """<html><head><meta charset="utf-8"><title>Wikipedia</title></head>
<body><main><h1>Knowledge base</h1><p>Article is visible.</p>
<div class="overlay-banner-main"><p>Hidden fundraising modal</p></div>
<div hidden><h2>Invisible heading</h2></div>
<div aria-hidden="true">Invisible ARIA text</div>
<div style="opacity: 0">Invisible opacity text</div>
<div style="display: none">Invisible display text</div>
</main><svg><title>Wikimedia Foundation</title></svg></body></html>"""


def test_explicit_hidden_elements_and_svg_titles_never_pollute_content():
    page = ContentExtractor().extract(_HTML)
    assert page.title == "Wikipedia"
    assert "Article is visible." in page.main_content
    for marker in ("Invisible heading", "Invisible ARIA text",
                   "Invisible opacity text", "Invisible display text"):
        assert marker not in page.main_content
    assert [item.text for item in page.headings] == ["Knowledge base"]
    assert "Wikimedia Foundation" not in page.title


def test_captured_css_hidden_class_removed_only_when_attested():
    parser = ContentExtractor()
    old_capture = parser.extract(_HTML)
    assert "Hidden fundraising modal" in old_capture.main_content
    measured = parser.extract(_HTML, hidden_markers={
        "id": frozenset(),
        "class": frozenset({_hash("overlay-banner-main")}),
    })
    assert "Hidden fundraising modal" not in measured.main_content
    assert "Article is visible." in measured.main_content
    assert measured.title == old_capture.title


def test_cross_snapshot_or_tampered_rendered_dom_cannot_reuse_visibility(tmp_path: Path):
    rendered = tmp_path / "artifacts" / "snapshot.html"
    rendered.parent.mkdir()
    rendered.write_text(_HTML, encoding="utf-8")
    digest = sha256(rendered.read_bytes()).hexdigest()
    snapshot = SimpleNamespace(
        rendered_artifact_ref="artifacts/snapshot.html",
        browser_metadata={
            "architecture_artifact_binding": {"rendered_sha256": digest},
            "dom_visibility": {
                "version": "dom-visibility-v1", "source": "CHROMIUM_COMPUTED_STYLE",
                "status": "OBSERVED", "rendered_sha256": digest,
                "hidden_ids_sha256": [],
                "hidden_classes_sha256": [_hash("overlay-banner-main")],
            }
        }
    )
    workspace = SimpleNamespace(root=tmp_path)
    selectors = _attested_hidden_markers(snapshot, workspace, "RENDERED_DOM", "artifacts/snapshot.html")
    assert selectors is not None
    assert _hash("overlay-banner-main") in selectors["class"]
    assert _attested_hidden_markers(snapshot, workspace, "RAW_HTML_FALLBACK", "artifacts/snapshot.html") is None
    rendered.write_text(_HTML + "<div>CHANGED</div>", encoding="utf-8")
    assert _attested_hidden_markers(snapshot, workspace, "RENDERED_DOM", "artifacts/snapshot.html") is None


def test_live_browser_identifier_values_are_hashed_before_persistence():
    class FakePage:
        def evaluate(self, _code):
            return {
                "status": "OBSERVED", "inspected": 20,
                "markers": [{"kind": "class", "value": "overlay-banner-main"},
                            {"kind": "id", "value": "fundraising-modal"}],
            }
    observed = BrowserRenderer._capture_dom_visibility(FakePage())
    assert observed["status"] == "OBSERVED"
    assert _hash("overlay-banner-main") in observed["hidden_classes_sha256"]
    assert _hash("fundraising-modal") in observed["hidden_ids_sha256"]
    assert "overlay-banner-main" not in str(observed)
    assert "fundraising-modal" not in str(observed)

def test_device_scoped_renderer_persists_visibility_only_for_frozen_dom() -> None:
    """#665 R02: the device capture path must not silently omit CSS markers."""
    from rasai.device_context_capture import _capture_bound_dom_visibility

    html = "<html><main><div class='overlay-banner-main'>hidden</div></main></html>"

    class Page:
        def __init__(self, values: list[str]) -> None:
            self.values = iter(values)

        def content(self) -> str:
            return next(self.values)

    class Renderer:
        def __init__(self) -> None:
            self.calls = 0

        def _capture_dom_visibility(self, _page: object) -> dict[str, object]:
            self.calls += 1
            return {
                "version": "dom-visibility-v1",
                "source": "CHROMIUM_COMPUTED_STYLE",
                "status": "OBSERVED",
                "hidden_ids_sha256": [],
                "hidden_classes_sha256": [_hash("overlay-banner-main")],
                "inspected": 1,
            }

    renderer = Renderer()
    stable = _capture_bound_dom_visibility(renderer, Page([html, html]), html)
    assert stable["status"] == "OBSERVED"
    assert _hash("overlay-banner-main") in stable["hidden_classes_sha256"]
    assert renderer.calls == 1
    assert "rendered_sha256" not in stable  # SHA identity is owned by M3

    changed_before = _capture_bound_dom_visibility(
        renderer, Page([html + " changed"]), html,
    )
    assert changed_before["status"] == "UNAVAILABLE"
    assert changed_before["hidden_classes_sha256"] == []
    assert renderer.calls == 1

    changed_after = _capture_bound_dom_visibility(
        renderer, Page([html, html + " changed"]), html,
    )
    assert changed_after["status"] == "UNAVAILABLE"
    assert changed_after["hidden_classes_sha256"] == []
    assert renderer.calls == 2


def test_device_scoped_installer_uses_bound_visibility_observation() -> None:
    """Guard the overridden production renderer, not just the helper."""
    import inspect
    from rasai import device_context_capture
    source = inspect.getsource(device_context_capture._install_browser_capture)
    assert 'metadata["dom_visibility"] = _capture_bound_dom_visibility(' in source

