"""Offline presentation contracts: declared AI confidence and Dynatrace RUM schema labels."""
from pathlib import Path

import pytest

from rasai.catalog_report_presentation import _confidence_label
from rasai.catalog_report_analysis import _synthetic_profile_public_label
from rasai.cat07_architecture_reporting import (
    _dynatrace_rum_kpm_reference_html,
    _preview_source_html,
    _preview_value_html,
)
from rasai.dynatrace_apdex_arch_advisory import KPM_BY_ACTION
from rasai.report_presentation import fractional_confidence_percentage, humanize_report_html


@pytest.mark.parametrize("raw, expected", [
    (0, "0%"), (0.82, "82%"), ("0.82", "82%"), (1, "100%"),
    (0.825, "83%"), (None, "N/D"), (True, "N/D"), (False, "N/D"),
    (float("nan"), "N/D"), (float("inf"), "N/D"),
    (-0.1, "N/D"), (1.01, "N/D"), (82, "N/D"),
    ("abc", "N/D"), ("82%", "N/D"), ({}, "N/D"),
])
def test_fractional_confidence_only_in_unit_interval(raw, expected):
    assert fractional_confidence_percentage(raw) == expected


def test_shared_catalog_confidence_keeps_non_numeric_classes():
    assert _confidence_label(0.82) == "82%"
    assert _confidence_label(0) == "0%"
    assert _confidence_label("HIGH") == "Alta"
    assert _confidence_label("UNAVAILABLE") == "Sem dados para estimar"
    assert _confidence_label(float("inf")) == "N/D"
    assert _confidence_label(82) == "N/D"


def test_geo_competitive_opportunity_is_declared_not_calibrated(monkeypatch):
    from rasai import geo_report
    observation = {
        "observation_id": "SERP-TEST", "query": "insurance", "engine": "google",
        "country": "BR", "region": "RS", "language": "pt-BR",
        "device": "mobile", "collected_at": "2026-10-25T12:00:00Z",
    }
    opportunity = {
        "title": "Revisar cobertura", "category": "EEAT", "priority": "P2",
        "confidence": 0.82, "recommendation": "Revisar material",
        "evidence_ids": ["EV-TEST"],
    }
    monkeypatch.setattr(geo_report, "_serp_baseline", lambda *_: (observation, []))
    monkeypatch.setattr(geo_report, "_prior_competitive_ai", lambda *_: {
        "provider": "offline", "model": "fixture", "evidence_ref": "EV-TEST",
        "summary": None, "opportunities": [opportunity],
    })
    html = geo_report._baseline_serp_section(Path("unopened.db"), "AUD-TEST")
    assert "Confiança estimada pela IA (não verificada)</small>" in html
    assert "<strong>82%</strong>" in html
    assert "0.82</strong>" not in html
    assert opportunity["confidence"] == 0.82
    opportunity["confidence"] = float("nan")
    assert "Confiança estimada pela IA (não verificada)</small><strong>N/D</strong>" in (
        geo_report._baseline_serp_section(Path("unopened.db"), "AUD-TEST")
    )


def test_dynatrace_kpms_have_readable_labels_and_traceable_codes():
    html = _dynatrace_rum_kpm_reference_html("CSR_SPA")
    visible = humanize_report_html(html, page_name="cat-07.html")
    for options in KPM_BY_ACTION.values():
        for code in options:
            assert f"<code>{code}</code>" in visible
    assert "Conclusão visual da ação" in visible
    assert "Índice de velocidade da apresentação visual" in visible
    assert "Deslocamento acumulado de layout (CLS)" in visible
    assert "N/D (tenant não consultado)" in visible
    assert "KPM configurada no tenant: N/D" in visible
    assert "Duração da ação do usuário" in visible


def test_dynatrace_preview_source_is_provenance_not_network_origin():
    raw = "RASAI_EXECUTABLE_DYNATRACE_LOAD_FALLBACK_REFERENCE"
    origin = _preview_source_html(raw)
    assert "Referência de compatibilidade do RASAi" in origin
    assert raw not in origin
    assert "sem consulta ao tenant" in origin
    assert _preview_source_html(None) == "N/D"
    assert "<script>" not in _preview_source_html("<script>")
    assert "Duração da ação de carregamento inicial" in _preview_value_html("USER_ACTION_DURATION")
    assert _preview_value_html("0.2") == "0.2"


def test_synthetic_profile_internal_id_is_replaced_by_observable_preset_labels():
    rendered = str(_synthetic_profile_public_label(
        "RASAI_MOBILE_mobile-balanced-chromium_mobile-balanced_mobile-4g-fast"
    ))
    assert "RASAI_MOBILE" not in rendered
    assert "Rede simulada:" in rendered
    assert "Navegador/cliente:" in rendered
    assert "Capacidade simulada:" in rendered
    assert "RASAI_SECRET_TEST" not in str(_synthetic_profile_public_label("RASAI_SECRET_TEST"))
