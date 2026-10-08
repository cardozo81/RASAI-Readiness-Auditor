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
