"""Offline temporal inventory and parity with the canonical 21-page renderer."""
from rasai.report_temporal_inventory import inspect_html, inventory
from rasai.catalog_report_site import materialize_catalog_report_site
from rasai.catalog_report_contract import CATALOG_REPORT_PAGES
from tests.test_contextual_report_integration import _captured_workspace, AUDIT_ID


def test_temporal_scanner_separates_local_primary_from_immutable_technical_source():
    text = ("<p>Validade 10/09/2026 21:00:00 (America/Sao_Paulo)</p>"
            "<p>Referência apenas de data 2026-09-11</p>"
            "<code>2026-09-11T00:00:00Z</code>")
    result = inspect_html(text, zone="America/Sao_Paulo")
    assert result["local_presentation"] == 1
    assert result["aware_iso_unconverted"] == 0
    assert result["technical_aware_iso"] == 1
    assert result["zone_advertised"] is True


def test_temporal_scanner_refuses_silent_claim_of_rfc_and_naive_conversion():
    text = ("<p>Fri, 11 Sep 2026 00:00:00 GMT</p>"
            "<p>Data N/D 2026-09-11T00:00:00</p>")
    result = inspect_html(text, zone="UTC")
    assert result["rfc7231_visible"] == 1
    assert result["naive_timestamp_nd"] == 1
    assert result["local_presentation"] == 0


def test_temporal_inventory_covers_all_21_real_materializer_pages_without_extra_io(tmp_path):
    workspace = _captured_workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    actual = inventory(report, zone="America/Sao_Paulo")
    assert set(actual["pages"]) == {p.filename for p in CATALOG_REPORT_PAGES}
    assert len(actual["pages"]) == 21
    assert all(row["zone_advertised"] for row in actual["pages"].values())
    assert "source_sha256" not in str(actual)
