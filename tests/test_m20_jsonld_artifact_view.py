from __future__ import annotations

import json
from pathlib import Path

from rasai.m20_reporting import _structured_data_artifact_html


def test_structured_data_artifact_is_visible_in_html_and_keeps_full_file_link(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts/extraction/P1/mobile/S1/structured_data.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(
        json.dumps(
            {
                "blocks": [
                    {
                        "index": 0,
                        "raw": '{"@context":"https://schema.org","@type":"Product","name":"Seguro"}',
                        "parsed": {"@context": "https://schema.org", "@type": "Product", "name": "Seguro"},
                        "parse_error": None,
                        "types": ["Product"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ref = artifact.relative_to(tmp_path).as_posix()
    rendered = _structured_data_artifact_html(tmp_path, ref)
    assert "Visualizar JSON-LD observado nesta auditoria" in rendered
    assert "Seguro" in rendered
    assert "Product" in rendered
    assert f"../{ref}" in rendered
    assert "não é uma reconstrução feita pelo relatório" in rendered


def test_structured_data_artifact_preview_blocks_path_traversal(tmp_path: Path) -> None:
    rendered = _structured_data_artifact_html(tmp_path, "../outside.json")
    assert "bloqueada por segurança" in rendered
