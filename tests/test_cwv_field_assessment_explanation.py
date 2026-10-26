"""Explain CrUX p75 causality in CAT-04 without new collection or score mutation."""
from rasai.catalog_report_page import _core_web_vitals_explanation_html


def test_cwv_fail_lists_each_out_of_range_field_metric():
    row = {
        "cwv_assessment": "FAIL", "field_scope": "URL",
        "lcp_p75_ms": 2784.0, "inp_p75_ms": 489.0, "cls_p75": 0.9,
    }
    html = _core_web_vitals_explanation_html(row)
    assert "LCP, INP, CLS ultrapassaram" in html
    assert "2.784 ms" in html and "2.500 ms" in html
    assert "489 ms" in html and "200 ms" in html
    assert "0,9" in html and "≤ 0,1" in html
    assert "URL observada pela fonte" in html
    assert "não falha do RASAi" in html
    assert "Ruim" in html and "Precisa melhorar" in html
    assert row["cwv_assessment"] == "FAIL"


def test_cwv_origin_does_not_claim_page_and_missing_metrics_not_failure():
    html = _core_web_vitals_explanation_html({
        "cwv_assessment": "FAIL", "field_scope": "ORIGIN", "lcp_p75_ms": 2900,
    })
    assert "origem agregada (ORIGIN)" in html
    assert "N/D" in html and "Sem medição atribuível" in html
    assert "INP, CLS ultrapassaram" not in html


def test_cwv_diagnostic_does_not_run_without_persisted_assessment():
    assert _core_web_vitals_explanation_html({"field_scope": "URL"}) == ""
    assert "registrou aprovação" in _core_web_vitals_explanation_html({
        "cwv_assessment": "PASS", "field_scope": "URL",
        "lcp_p75_ms": 2000, "cls_p75": 0.05,
    })


def test_cwv_rejects_nan_inf_and_unsafe_unverified_scope():
    html = _core_web_vitals_explanation_html({
        "cwv_assessment": "FAIL", "field_scope": "<script>",
        "lcp_p75_ms": float("nan"), "inp_p75_ms": float("inf"),
        "cls_p75": 0.8,
    })
    assert "<script>" not in html
    assert "escopo não comprovado" in html
    assert "N/D" in html
