from __future__ import annotations

from pathlib import Path
import tempfile

from rasai.score_geo_004 import FEATURE_ORDER, SCORING_VERSION
from rasai.score_geo_004_reporting import _dimension_list


def _page(body: str) -> str:
    return (
        "<html><body><aside class='app-nav'><nav></nav></aside>"
        f"<main>{body}</main></body></html>"
    )


def test_scoring_dimension_list_never_exposes_raw_dimension_enums() -> None:
    html = _dimension_list(SCORING_VERSION)
    for dimension in FEATURE_ORDER:
        assert f">{dimension}<" not in html
        assert f"<code>{dimension}</code>" not in html
    assert "Acesso e descoberta" in html
    assert "Indexabilidade e canonicalização" in html
    assert "Renderização e extração" in html
    assert "Estrutura semântica" in html
    assert "Clareza de entidades" in html
    assert "Dados estruturados" in html
    assert "Capacidade de resposta" in html
    assert "Preparação para citação" in html
    assert "Evidências e confiabilidade" in html
    assert "Cobertura de intenções" in html
    assert "Valor do conteúdo" in html


def test_sari_methodology_uses_human_title_and_keeps_contract_id_technical() -> None:
    from rasai.report_registry import _sari_method_panel

    with tempfile.TemporaryDirectory() as tmp:
        html = _sari_method_panel(Path(tmp), "scoring.html")
    assert "<h2>Hierarchical Weighted Readiness</h2>" in html
    assert "<code>HIERARCHICAL_WEIGHTED_READINESS_V1</code>" in html
    assert "<h2>HIERARCHICAL_WEIGHTED_READINESS_V1</h2>" not in html
