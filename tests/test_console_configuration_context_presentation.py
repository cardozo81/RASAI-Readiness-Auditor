from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO

from rasai import console_configuration_context_presentation as context_ui
from rasai import console_configuration_presentation as presentation
from rasai import console_provider_environment as environment
from rasai import console_ui_catalog as catalog
from rasai.console_search_intelligence import SearchConsoleState


def _spec(name: str):
    return next(spec for spec in environment.refresh_specs() if spec.name == name)


def test_all_public_configuration_labels_are_unique_and_human() -> None:
    context_ui.install()
    specs = tuple(environment.refresh_specs())
    labels = [presentation.friendly_label(spec) for spec in specs]
    assert len(labels) == len({label.casefold() for label in labels})
    assert all("RASAI_" not in label for label in labels)
    assert all(not label.casefold().startswith("variável reconhecida pelo rasai") for label in labels)


def test_search_sources_have_distinct_functional_groups() -> None:
    context_ui.install()
    serp = _spec("RASAI_SERP_TIMEOUT_SECONDS")
    gsc = _spec("RASAI_GSC_ENABLED")
    crux = _spec("RASAI_CRUX_API_KEY")

    assert context_ui._functional_group(serp)[0].startswith("SERP")
    assert context_ui._functional_group(gsc)[0].startswith("Google Search Console")
    assert context_ui._functional_group(crux)[0].startswith("Chrome UX Report")


def test_all_configuration_rows_render_group_headers_and_secondary_technical_names() -> None:
    context_ui.install()
    state = SearchConsoleState()
    specs = (
        _spec("RASAI_SERP_TIMEOUT_SECONDS"),
        _spec("RASAI_GSC_ENABLED"),
        _spec("RASAI_CRUX_API_KEY"),
    )
    output = StringIO()
    with redirect_stdout(output):
        catalog._rows(state, specs, True)
    rendered = output.getvalue()

    assert "SERP — resultados públicos por termo" in rendered
    assert "Google Search Console — dados da property autenticada" in rendered
    assert "Chrome UX Report (CrUX)" in rendered
    assert "Variável técnica: RASAI_SERP_TIMEOUT_SECONDS" in rendered
    assert "Variável técnica: RASAI_GSC_ENABLED" in rendered
    assert "Variável técnica: RASAI_CRUX_API_KEY" in rendered


def test_generic_registry_purpose_uses_specific_human_fallback() -> None:
    class Spec:
        name = "RASAI_SAMPLE_MAX_PAGES"
        purpose = "Variável reconhecida pelo RASAi."

    label = context_ui._build_label_map((Spec(),), lambda spec: spec.purpose)[Spec.name]
    assert label != "Variável reconhecida pelo RASAi."
    assert "Máximo de páginas" in label
    assert "RASAI_" not in label
