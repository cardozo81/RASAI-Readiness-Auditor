from __future__ import annotations

import json
from pathlib import Path

from rasai.entrypoint import main as rasai_main


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "config" / "properties" / "example.toml"


def test_property_config_public_router_validates_versioned_example(capsys) -> None:
    assert rasai_main(["property-config", "validate", str(EXAMPLE)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["contract"] == "PROPERTY-CONFIG-001"
    assert result["status"] == "VALID"
    assert result["property_id"] == "example"
    assert result["secret_values_persisted"] is False


def test_property_config_show_and_references_never_emit_secret_values(monkeypatch, capsys) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "TEST_ONLY_OPENAI_VALUE")
    monkeypatch.setenv("RASAI_PLATFORM_DATABASE_URL", "postgresql://user:TEST_ONLY_PASSWORD@localhost/test")

    assert rasai_main(["property-config", "show", str(EXAMPLE)]) == 0
    shown = capsys.readouterr().out
    assert "OPENAI_API_KEY" in shown
    assert "RASAI_PLATFORM_DATABASE_URL" in shown
    assert "TEST_ONLY_OPENAI_VALUE" not in shown
    assert "TEST_ONLY_PASSWORD" not in shown

    assert rasai_main(["property-config", "references", str(EXAMPLE)]) == 0
    references = capsys.readouterr().out
    assert "OPENAI_API_KEY" in references
    assert "TEST_ONLY_OPENAI_VALUE" not in references
    assert "TEST_ONLY_PASSWORD" not in references
