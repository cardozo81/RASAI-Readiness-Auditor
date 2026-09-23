from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from rasai.console_environment import EnvironmentSpec
from rasai.console_search_intelligence import SearchConsoleState
from rasai import console_configuration_presentation as presentation
from rasai import console_provider_environment as environment


@pytest.fixture(autouse=True)
def _restore_environment():
    before = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(before)


def _spec(name: str):
    return next(spec for spec in environment.refresh_specs() if spec.name == name)


def test_every_published_configuration_has_a_human_label() -> None:
    specs = environment.refresh_specs()
    assert specs
    for spec in specs:
        label = presentation.friendly_label(spec)
        assert label.strip(), spec.name
        assert label != spec.name, spec.name
        assert "RASAI_" not in label, spec.name


def test_apdex_labels_use_operator_language() -> None:
    assert presentation.friendly_label(_spec("RASAI_APDEX_ACQUISITION_MODE")) == "Modo de aquisição do Apdex"
    assert presentation.friendly_label(_spec("RASAI_APDEX_SAMPLES_PER_CONTEXT")) == "Amostras por contexto"
    assert presentation.friendly_label(_spec("RASAI_APDEX_THRESHOLD_SECONDS")) == "Limite de experiência satisfatória"


def test_effective_value_formats_seconds_for_humans(monkeypatch) -> None:
    spec = _spec("RASAI_APDEX_THRESHOLD_SECONDS")
    monkeypatch.setenv(spec.name, "3")
    assert presentation.friendly_value(spec) == "3 s"


def test_secret_value_is_never_exposed(monkeypatch) -> None:
    spec = EnvironmentSpec(
        "OPENAI_API_KEY",
        "IA - credenciais",
        "Chave da OpenAI.",
        "segredo/API key",
        sensitive=True,
    )
    secret = "unit-test-secret-value"
    monkeypatch.setenv(spec.name, secret)
    rendered = presentation.friendly_value(spec)
    assert rendered == "CONFIGURADO"
    assert secret not in rendered


def test_public_row_has_label_value_origin_and_secondary_technical_name(monkeypatch) -> None:
    spec = _spec("RASAI_APDEX_THRESHOLD_SECONDS")
    monkeypatch.setenv(spec.name, "3")
    state = SearchConsoleState()
    row = presentation.format_configuration_row(state, spec)
    assert presentation.friendly_label(spec) in row
    assert "3 s" in row
    assert "Variável técnica: RASAI_APDEX_THRESHOLD_SECONDS" in row
    assert "[" in row and "]" in row


def test_rewrite_of_raw_row_does_not_duplicate_origin_or_technical_reference(monkeypatch) -> None:
    spec = _spec("RASAI_APDEX_THRESHOLD_SECONDS")
    monkeypatch.setenv(spec.name, "3")
    state = SearchConsoleState()
    raw_row = f"12345678  {spec.name:<46} [SESSÃO]"
    rewritten = presentation._rewrite_line(raw_row, state, {spec.name: spec}, (spec.name,))
    assert presentation.friendly_label(spec) in rewritten
    assert rewritten.count(spec.name) == 1
    assert rewritten.count("[SESSÃO]") == 1


def test_technical_details_exposes_raw_value_and_identifier(monkeypatch) -> None:
    spec = _spec("RASAI_APDEX_THRESHOLD_SECONDS")
    monkeypatch.setenv(spec.name, "3")
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    state = SearchConsoleState()
    output = StringIO()
    with redirect_stdout(output):
        presentation._technical_details(state, spec)
    rendered = output.getvalue()
    assert "DETALHES TÉCNICOS" in rendered
    assert spec.name in rendered
    assert "Valor bruto" in rendered


def test_fallback_label_uses_purpose_instead_of_internal_key() -> None:
    spec = SimpleNamespace(
        name="RASAI_EXAMPLE_INTERNAL_FLAG",
        purpose="Habilita coleta complementar de exemplo.",
    )
    label = presentation.friendly_label(spec)
    assert label == "Coleta complementar de exemplo"
    assert "RASAI_" not in label


def test_public_technical_variable_line_uses_gray(monkeypatch) -> None:
    spec = _spec("RASAI_APDEX_THRESHOLD_SECONDS")
    monkeypatch.setenv(spec.name, "3")
    calls: list[tuple[str, str, bool]] = []

    def fake_paint(text: object, color: str, *, bold: bool = False) -> str:
        calls.append((str(text), color, bold))
        return str(text)

    monkeypatch.setattr(presentation, "paint", fake_paint)
    presentation.format_configuration_row(SearchConsoleState(), spec)

    assert any(
        "Variável técnica: RASAI_APDEX_THRESHOLD_SECONDS" in text
        and color == presentation.GRAY
        for text, color, _ in calls
    )


def test_all_rendered_technical_variable_references_use_gray() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "rasai"
    paths = (
        root / "console_configuration_presentation.py",
        root / "console_catalog_configuration_refinements.py",
        root / "console_provider_environment.py",
        root / "integration_diagnostics_console.py",
        root / "console_environment_reset.py",
    )
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "Variável técnica:" not in line:
                continue
            if "if " in line:
                continue
            assert "GRAY" in line, f"{path}: {line.strip()}"


def test_raw_technical_variable_line_is_forced_to_gray(monkeypatch) -> None:
    calls: list[tuple[str, str, bool]] = []

    def fake_paint(text: object, color: str, *, bold: bool = False) -> str:
        calls.append((str(text), color, bold))
        return f"<gray>{text}</gray>"

    monkeypatch.setattr(presentation, "paint", fake_paint)
    rendered = presentation._rewrite_line(
        "    Variável técnica: RASAI_TEST_VALUE",
        SearchConsoleState(),
        {},
        (),
    )

    assert rendered == "<gray>    Variável técnica: RASAI_TEST_VALUE</gray>"
    assert calls == [
        ("    Variável técnica: RASAI_TEST_VALUE", presentation.GRAY, False)
    ]


def test_gray_uses_actual_ansi_gray_code() -> None:
    from rasai.console_ui import GRAY

    assert GRAY == "\033[90m"
