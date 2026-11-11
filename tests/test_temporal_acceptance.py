"""Minimum synthetic gates for private 21-page Windows temporal acceptance."""
import json
import pytest

from rasai.document_advisory import _inventory
from rasai.temporal_acceptance import _NonTemporalTokens, _preflight, verify_copy
from tests.test_contextual_report_integration import _captured_workspace


def test_private_copy_generates_21_pages_and_does_not_modify_aud(tmp_path):
    workspace = _captured_workspace(tmp_path)
    before = _inventory(workspace.root)
    output = tmp_path / "private" / "validation"
    output.parent.mkdir(mode=0o700)
    result = verify_copy(workspace.root, output)
    assert result["status"] == "PASS_TECHNICAL"
    assert result["source_unchanged"] is True
    assert result["page_count"] == 21
    assert result["non_temporal_21_pages"] == "PASS_FOCAL_LOCALIZER_PARITY"
    assert result["temporal_21_pages"] == "REVIEW_REQUIRED"
    assert result["human_review"] == "N/D"
    assert result["network_attempts_blocked"] == 0
    assert _inventory(workspace.root) == before
    assert (output / workspace.root.name / "report-catalog" / "geo-content-review.html").is_file()
    assert len(json.loads((output / "temporal-inventory.json").read_text())["pages"]) == 21
    assert json.loads((output / "temporal-acceptance.json").read_text())["status"] == "PASS_TECHNICAL"


def test_preflight_rejects_original_or_existing_target(tmp_path):
    workspace = _captured_workspace(tmp_path)
    with pytest.raises(ValueError):
        _preflight(workspace.root, workspace.root / "derived")
    with pytest.raises(ValueError):
        _preflight(workspace.root, workspace.root)


def test_non_temporal_comparison_keeps_attributes_and_technical_code():
    a = "<p data-sensitive='a'>2026-09-11T00:00:00Z</p><code>2026-09-11T00:00:00Z</code>"
    b = "<p data-sensitive='a'>10/09/2026 21:00:00 (America/Sao_Paulo)</p><code>2026-09-11T00:00:00Z</code>"
    c = b.replace("data-sensitive='a'", "data-sensitive='b'")
    assert _NonTemporalTokens(a).tokens == _NonTemporalTokens(b).tokens
    assert _NonTemporalTokens(a).tokens != _NonTemporalTokens(c).tokens
