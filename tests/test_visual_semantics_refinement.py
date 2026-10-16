from pathlib import Path

from rasai.report_semantics import enhance_report_html
from rasai.report_contract import REPORT_ALIASES, surface_by_id
from rasai.report_observation_reconciliation import install as install_report_observation_reconciliation
from rasai.m23_reporting import _apdex_class_badge


def test_structured_data_note_matches_current_scoring_contract(tmp_path: Path) -> None:
    html = "<h2>Dimensões Mobile</h2><table><tbody><tr><td>Dados estruturados</td><td>80.0</td><td>100%</td><td>Alta</td><td>Consolidado</td></tr></tbody></table>"
    rendered = enhance_report_html(html, page_name="mobile.html", report_dir=tmp_path)
    assert "BR-GEO-034" in rendered
    assert "lacuna leve" in rendered
    assert "não reduz o Overall" not in rendered


def test_apdex_class_badges_preserve_apdex_classes() -> None:
    assert "apdex-class-satisfied" in _apdex_class_badge("SATISFIED")
    assert "apdex-class-tolerating" in _apdex_class_badge("TOLERATING")
    assert "apdex-class-frustrated" in _apdex_class_badge("FRUSTRATED")
    assert "apdex-class-excluded" in _apdex_class_badge(None)


def test_prepublication_report_contract_is_canonical_only() -> None:
    assert REPORT_ALIASES == {}
    assert "scorecard de contexto read-only" in surface_by_id("mobile").outputs
