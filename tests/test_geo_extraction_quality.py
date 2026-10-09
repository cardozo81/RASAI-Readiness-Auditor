"""Regression tests for non-destructive navigation-dominated extraction advisory."""
import json
from pathlib import Path

from rasai.geo_extraction_quality import (
    classify_extracted_text, inspect_workspace_extractions, materialize_extraction_quality,
)


def test_navigation_shell_is_flagged_without_claiming_crawler_failure():
    text = "Produtos Dental Residencial Vida Viagem Capitalização Atendimento Acessibilidade Menu Buscar"
    observed = classify_extracted_text(text)
    assert observed["state"] == "NAVIGATION_DOMINATED_SUSPECTED"
    assert observed["classification"] == "HEURISTIC_ADVISORY_ONLY"


def test_factual_content_and_long_form_are_not_falsely_flagged():
    assert classify_extracted_text(
        "Seguro de vida possui coberturas e condições específicas. A proposta "
        "apresenta informações sobre contratação, carências, assistência e beneficiários."
    )["state"] == "NOT_FLAGGED"


def test_sidecar_is_deterministic_and_preserves_original_text(tmp_path: Path):
    original = tmp_path / "artifacts" / "extraction" / "SNP-1" / "main_content.txt"
    original.parent.mkdir(parents=True)
    original.write_text(
        "Produtos Dental Residencial Vida Viagem Capitalização Atendimento Acessibilidade Menu Buscar",
        encoding="utf-8",
    )
    original_before = original.read_bytes()
    output = materialize_extraction_quality(tmp_path)
    assert output == "artifacts/geo-extraction-quality.json"
    sidecar = tmp_path / output
    first = sidecar.read_bytes()
    assert materialize_extraction_quality(tmp_path) == output
    assert sidecar.read_bytes() == first
    assert original.read_bytes() == original_before
    rows = inspect_workspace_extractions(tmp_path)
    assert len(rows) == 1
    payload = json.loads(first)
    assert payload["scoring_effect"] == "NONE"


def test_regenerated_main_text_retires_stale_advisory(tmp_path: Path):
    original = tmp_path / "artifacts" / "extraction" / "SNP-1" / "main_content.txt"
    original.parent.mkdir(parents=True)
    original.write_text("Produtos Dental Residencial Vida Viagem Capitalização Atendimento Acessibilidade Menu Buscar", encoding="utf-8")
    materialize_extraction_quality(tmp_path)
    original.write_text(
        "Coberturas contratuais, benefícios e critérios de elegibilidade da proteção de vida "
        "são apresentados nesta página para a análise das condições da oferta.",
        encoding="utf-8",
    )
    materialize_extraction_quality(tmp_path)
    payload = json.loads((tmp_path / "artifacts" / "geo-extraction-quality.json").read_text(encoding="utf-8"))
    assert payload["observations"] == []


def test_rendered_main_empty_correlates_by_snapshot_without_altering_html(tmp_path: Path):
    snapshot = "SNP-EXAMPLE"
    original = tmp_path / "artifacts" / "extraction" / "PAGE-1" / "mobile" / snapshot / "main_content.txt"
    original.parent.mkdir(parents=True)
    original.write_text(
        "Produtos Dental Residencial Vida Viagem Capitalização Atendimento Acessibilidade Menu Buscar",
        encoding="utf-8",
    )
    rendered = tmp_path / "artifacts" / "rendered" / "PAGE-1" / "mobile" / (snapshot + ".html")
    rendered.parent.mkdir(parents=True)
    rendered.write_text(
        "<html><body><nav>Produtos Menu Buscar</nav><main></main><h1></h1></body></html>",
        encoding="utf-8",
    )
    screenshot = tmp_path / "artifacts" / "visual" / "PAGE-1" / "mobile" / (snapshot + ".png")
    screenshot.parent.mkdir(parents=True)
    screenshot.write_bytes(b"fake-png-fixture")
    source_sha = rendered.read_bytes()
    rows = inspect_workspace_extractions(tmp_path)
    assert len(rows) == 1
    assert rows[0]["rendered_dom"]["main_empty_in_captured_html"] is True
    assert rows[0]["rendered_dom"]["main_element_count"] == 1
    assert rows[0]["rendered_dom"]["h1_text_characters"] == 0
    assert rows[0]["visual"]["screenshot_ref"].endswith(snapshot + ".png")
    assert len(rows[0]["visual"]["screenshot_sha256"]) == 64
    assert rendered.read_bytes() == source_sha
