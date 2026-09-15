from __future__ import annotations

from rasai import console_environment as base
from rasai.console_configuration_detail_refinements import install
from rasai.m25_cli import DYNATRACE_APPLICATION_ID_ENV, DYNATRACE_CONFIG_JSON_ENV


def test_dynatrace_open_values_publish_format_example_and_activation_criteria() -> None:
    install()
    app = base.SPEC_BY_NAME[DYNATRACE_APPLICATION_ID_ENV]
    path = base.SPEC_BY_NAME[DYNATRACE_CONFIG_JSON_ENV]

    assert "Web Application" in app.value_type
    assert app.example == "APPLICATION-XXXXXXXXXXXX"
    assert "modo live" in app.required_when
    assert "Alternativa ao modo live" in path.required_when
    assert path.example.endswith("dynatrace-web-application.json")
