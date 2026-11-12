"""Focused read-only report UX contracts; no network, paid IA, or AUD mutation."""
from __future__ import annotations

from datetime import datetime, timezone

from rasai.architecture_audit_facts import _tls_validity_presentation
from rasai.catalog_report_assurance import assurance_matrix_html, catalog_assurance_html


def test_tls_unix_seconds_use_utc_and_configured_timezone_without_mutation(monkeypatch) -> None:
    monkeypatch.setenv("RASAI_PRESENTATION_TIMEZONE", "America/Sao_Paulo")
    source = 1789084800
    utc_label, local_label = _tls_validity_presentation(source)
    assert utc_label == "11/09/2026 00:00:00 (UTC)"
    assert local_label == "10/09/2026 21:00:00 (America/Sao_Paulo)"
    assert source == 1789084800
    assert _tls_validity_presentation("1806191999") == (
        "27/03/2027 23:59:59 (UTC)",
        "27/03/2027 20:59:59 (America/Sao_Paulo)",
    )


def test_tls_unix_seconds_reject_invalid_without_inventing_dates(monkeypatch) -> None:
    monkeypatch.setenv("RASAI_PRESENTATION_TIMEZONE", "UTC")
    for value in (None, True, "abc", "-1", "1.5", "", "9999999999999999999999"):
        assert _tls_validity_presentation(value) == ("N/D", "N/D")
    assert _tls_validity_presentation("0") == (
        "01/01/1970 00:00:00 (UTC)",
        "01/01/1970 00:00:00 (UTC)",
    )


def test_assurance_does_not_reinterpret_partial_catalog_as_completed() -> None:
    row = {
        "catalog_id": "CAT-05", "selected": True, "functional_status": "PARCIAL",
        "configurability": 100, "governance": 100, "exposure": 100,
        "reliability": 100, "integrity": 100, "security": 100,
        "maturity": 100, "closure_eligible": True, "checks": [],
    }
    catalog_html = catalog_assurance_html(row)
    assert "Um catálogo PARCIAL pode ter maturidade estrutural de 100%" in catalog_html
    result = {
        "catalogs": [row], "global": {"maturity": 100},
        "closure_eligible": True, "package_integrity": {"final_source_snapshot_match": True},
    }
    html = assurance_matrix_html(result)
    assert "PARCIAL" in html
    assert "100.00%" in html
    assert "não promove o CAT a CONCLUÍDO" in html



def test_external_geo_source_dates_keep_ambiguous_literals():
    from rasai.geo_report import _source_date_display
    assert _source_date_display("2026-09-11") == "11/09/2026"
    assert _source_date_display("2026-02-30") == "N/D (data civil inválida)"
    assert _source_date_display("2026-09-11T00:00:00Z") == "2026-09-11T00:00:00Z"
    assert _source_date_display("Sep 11, 2026") == "Sep 11, 2026"
    assert _source_date_display(None) == "N/D"
