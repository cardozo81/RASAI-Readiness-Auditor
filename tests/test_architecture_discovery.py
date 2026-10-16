"""Pure architecture assessment is shared, conservative and side-effect free."""
from rasai.architecture_discovery import assess_architecture
from rasai.domain import ArchitectureClassification


def test_empty_states_cannot_prove_static_architecture():
    value = assess_architecture(raw_html="<html><title>X</title></html>",
                                rendered_html="<html><title>X</title></html>")
    assert value.architecture is ArchitectureClassification.UNKNOWN
    assert value.limitation == "MAIN_CONTENT_NOT_IDENTIFIED"


def test_raw_and_rendered_content_share_existing_classifier():
    raw = "<html><body><main>Visible content present.</main></body></html>"
    value = assess_architecture(raw_html=raw, rendered_html=raw)
    assert value.architecture is ArchitectureClassification.STATIC_OR_SSR
    assert value.comparison is not None


def test_capture_failure_abstains_without_invoking_analyzer():
    class FailIfCalled:
        def compare(self, *_args):
            raise AssertionError("must not classify failed evidence")
    value = assess_architecture(
        raw_html="<main>raw</main>", rendered_html="<main>rendered</main>",
        quality_reason="RENDER_BLOCKED", analyzer=FailIfCalled())
    assert value.architecture is ArchitectureClassification.UNKNOWN
    assert value.comparison is None


def test_missing_render_abstains():
    value = assess_architecture(raw_html="<main>content</main>", rendered_html=None)
    assert value.architecture is ArchitectureClassification.UNKNOWN


def test_spa_content_materializes_only_after_render():
    raw = "<html><body><main></main></body></html>"
    rendered = "<html><body><main><p>Material client-rendered content visible on this page.</p></main></body></html>"
    result = assess_architecture(raw_html=raw, rendered_html=rendered)
    assert result.architecture is ArchitectureClassification.CSR_SPA
    assert result.comparison is not None


def test_hydrated_content_adds_to_server_content():
    raw = "<html><body><main><p>Material server-delivered product description.</p></main></body></html>"
    rendered = "<html><body><main><p>Material server-delivered product description. Updated by the client.</p></main></body></html>"
    result = assess_architecture(raw_html=raw, rendered_html=rendered)
    assert result.architecture is ArchitectureClassification.HYDRATED


def test_different_material_raw_and_rendered_content_is_mixed():
    raw = "<html><body><main><p>Catalog information in the server document.</p></main></body></html>"
    rendered = "<html><body><main><p>Different information inserted by client rendering.</p></main></body></html>"
    result = assess_architecture(raw_html=raw, rendered_html=rendered)
    assert result.architecture is ArchitectureClassification.MIXED
