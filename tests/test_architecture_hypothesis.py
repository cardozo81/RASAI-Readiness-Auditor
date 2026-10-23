"""Domain-agnostic, advisory-only hypotheses when physical rendering is absent."""
from rasai.architecture_discovery import assess_architecture
from rasai.console_architecture_discovery import describe_architecture_assessment
from rasai.domain import ArchitectureClassification as Classification


LONG_MAIN = (
    "A complete visible server-delivered page introduces substantive information "
    "that may later remain stable or be replaced and extended by client JavaScript."
)


def test_embedded_frame_topology_is_not_mistaken_for_spa_or_server_rendering():
    raw = ('<html><body><div id="app"></div>'
           '<iframe src="/process/flow" title="Process"></iframe>'
           '<script src="/shell.js"></script></body></html>')
    value = assess_architecture(
        raw_html=raw, rendered_html=None, quality_reason="OCI_ASSET_UNAVAILABLE",
    )
    assert value.architecture is Classification.UNKNOWN
    assert value.hypothesis is not None
    assert value.hypothesis.likely is None
    assert value.hypothesis.structure == "EMBEDDED_FRAME_COMPOSITION"
    assert value.hypothesis.confidence == "LOW"
    assert value.raw_signals.iframe_tags == 1
    assert value.raw_signals.iframe_src_tags == 1
    assert value.raw_signals.iframe_srcdoc_tags == 0
    output = "\n".join(describe_architecture_assessment(value))
    assert "página composta com iframe" in output
    assert "arquitetura do conteúdo embarcado não observada" in output
    assert "Arquitetura observada: UNKNOWN" in output


def test_embedded_srcdoc_is_also_a_distinct_unverified_document():
    raw = '<main><iframe srcdoc="<main>nested</main>"></iframe></main>'
    value = assess_architecture(raw_html=raw, rendered_html=None)
    assert value.raw_signals.iframe_tags == 1
    assert value.raw_signals.iframe_srcdoc_tags == 1
    assert value.hypothesis.structure == "EMBEDDED_FRAME_COMPOSITION"


def test_js_shell_is_an_uncertain_candidate_not_an_observed_spa():
    raw = '<html><div id="root"></div><script src="/app.js"></script></html>'
    value = assess_architecture(raw_html=raw, rendered_html=None)
    assert value.architecture is Classification.UNKNOWN
    assert value.hypothesis.likely is Classification.CSR_SPA
    assert Classification.MIXED in value.hypothesis.alternatives
    assert "NÃO comprovada" in "\n".join(describe_architecture_assessment(value))


def test_server_content_and_framework_markers_do_not_prove_hydration():
    raw = f'<main data-hydrate="true"><h1>Title</h1>{LONG_MAIN}</main><script src="/app.js"></script>'
    value = assess_architecture(raw_html=raw, rendered_html=None)
    assert value.architecture is Classification.UNKNOWN
    assert value.hypothesis.likely is Classification.HYDRATED
    assert Classification.STATIC_OR_SSR in value.hypothesis.alternatives
    assert value.hypothesis.confidence == "LOW"


def test_server_content_without_framework_can_only_suggest_static_or_ssr():
    raw = f'<main><h1>Title</h1>{LONG_MAIN}</main>'
    value = assess_architecture(raw_html=raw, rendered_html=None)
    assert value.architecture is Classification.UNKNOWN
    assert value.hypothesis.likely is Classification.STATIC_OR_SSR
    assert Classification.MIXED in value.hypothesis.alternatives


def test_no_raw_evidence_means_no_hypothesis_even_if_tls_or_network_fails():
    for reason in ("PUBLIC_TLS_FAILURE", "PUBLIC_TIMEOUT", "OCI_NETWORK_ISOLATION_NOT_ATTESTED"):
        value = assess_architecture(raw_html=None, rendered_html=None, quality_reason=reason)
        assert value.architecture is Classification.UNKNOWN
        assert value.hypothesis is None
        output = "\n".join(describe_architecture_assessment(value))
        assert "Hipótese de arquitetura" not in output
        assert "Padrão estrutural provável" not in output


def test_missing_material_positive_signals_does_not_invent_a_hypothesis():
    value = assess_architecture(
        raw_html='<html><head><title>Page</title></head><body><div>Small</div></body></html>',
        rendered_html=None,
    )
    assert value.hypothesis is None


def test_successfully_observed_dom_uses_canonical_classifier_without_hypothesis():
    raw = f'<main><h1>Title</h1>{LONG_MAIN}</main>'
    value = assess_architecture(raw_html=raw, rendered_html=raw)
    assert value.architecture is Classification.STATIC_OR_SSR
    assert value.hypothesis is None


def test_hypothesis_has_no_hostname_specific_rules_or_network_side_effects():
    from rasai.architecture_hypothesis import suggest_architecture_from_raw
    from rasai.architecture_raw_signals import inspect_raw_html_signals
    assert suggest_architecture_from_raw(
        inspect_raw_html_signals('<div id="root"></div><script src="/bundle.js"></script>')
    ).likely is Classification.CSR_SPA
