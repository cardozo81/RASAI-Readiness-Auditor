"""Focused offline tests for the #728 presentation surface triage receipt."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from scripts.presentation_surface_inventory import EXPECTED_PAGES, inspect_presentation, main


def _package(tmp_path, first_html):
    root = tmp_path / "report-presentation"
    root.mkdir()
    for name in EXPECTED_PAGES:
        (root / name).write_text(
            first_html if name == "index.html" else "<html><body><p>Sem sinais.</p></body></html>",
            encoding="utf-8")
    return root


def test_728_all_eleven_surfaces_flag_context_without_copying_private_values(tmp_path):
    text = (
        '<html><body><section data-analytical-family="m24_runs">'
        '<h2>SEMANTIC_M7</h2><button aria-label="M23">Detalhes</button>'
        '<p>Consultar CAT-03</p><table><tr>'
        '<td title="SOURCE_UNAVAILABLE">SOURCE_UNAVAILABLE</td></tr></table>'
        '<pre>PRIVATE_API_KEY</pre><code>CAT-05</code>'
        '<blockquote>PRIVATE_USER_CONTENT</blockquote>'
        '<a href="CAT-06" data-raw="CAT-07">Link seguro</a>'
        '</section></body></html>'
    )
    root = _package(tmp_path, text)
    original = {p.name: sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    report = inspect_presentation(root)

    assert report["pages_reviewed"] == 11
    assert report["candidate_count"] == 5
    assert report["candidates_by_context"]["EDITORIAL_COPY_REVIEW"] == 3
    assert report["candidates_by_context"]["PERSISTED_VALUE_REVIEW"] == 2
    assert report["candidates_by_context"]["LITERAL_OR_TECHNICAL"] == 3
    assert report["certifies_humanization"] is False
    assert report["automatic_replacement_performed"] is False
    assert report["raw_snippets_included"] is False
    assert not report["samples_truncated"]
    assert {item["known_reference"] for item in report["candidates"]
            if "known_reference" in item} == {"SEMANTIC_M7", "M23", "CAT-03"}
    assert not any("SOURCE_UNAVAILABLE" in json.dumps(item)
                   for item in report["candidates"])
    assert {item["surface"] for item in report["candidates"]} == {
        "text", "aria-label", "title",
    }
    assert {item["analytical_family"] for item in report["candidates"]} == {"m24_runs"}
    assert original == {p.name: sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}


def test_728_cli_refuses_receipt_inside_source_and_never_overwrites(tmp_path):
    root = _package(tmp_path, "<html><body><p>M7</p></body></html>")
    original = (root / "index.html").read_bytes()
    receipt = tmp_path / "review" / "editorial-surface-inventory.json"
    assert main(["--presentation", str(root), "--output", str(receipt)]) == 0
    content = json.loads(receipt.read_text(encoding="utf-8"))
    assert content["candidate_count"] == 1
    assert (root / "index.html").read_bytes() == original
    with pytest.raises(SystemExit):
        main(["--presentation", str(root), "--output", str(receipt)])
    with pytest.raises(SystemExit):
        main(["--presentation", str(root), "--output", str(root / "unsafe.json")])


def test_728_incomplete_html_package_is_never_reported_as_all_eleven(tmp_path):
    root = tmp_path / "partial"
    root.mkdir()
    (root / "index.html").write_text("<p>CAT-03</p>", encoding="utf-8")
    with pytest.raises(ValueError, match="eleven expected"):
        inspect_presentation(root)
