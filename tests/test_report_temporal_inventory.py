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


def test_field_census_is_line_traceable_without_disclosing_source_literals():
    from json import dumps
    html = (
        "<main><p>11/09/2026 00:00:00 (UTC)</p>\n"
        "<p>10/09/2026 21:00:00 (America/Sao_Paulo)</p>\n"
        "<p>Fri, 11 Sep 2026 00:00:00 GMT</p>\n"
        "<p>2026-09-11T00:00:00Z</p>\n"
        "<p>2026-09-11T00:00:00</p>\n"
        "<p>2026-09-11</p>\n"
        "<pre>2026-09-11T00:00:00Z</pre>"
        "<script>2026-09-11T00:00:00Z</script></main>"
    )
    row = inspect_html(html, zone="America/Sao_Paulo")
    assert row["field_totals"] == {
        "AWARE_ISO_VISIBLE_REVIEW": 1,
        "DATE_ONLY_UNSHIFTED": 1,
        "HTTP_DATE_VISIBLE_REVIEW": 1,
        "LOCAL_PRESENTATION": 1,
        "NAIVE_TIMEZONE_ND": 1,
        "OTHER_DECLARED_TIMEZONE_REVIEW": 1,
        "TECHNICAL_ISO_PRESERVED": 1,
    }
    assert all(item["line"] >= 1 and item["tag_path"] for item in row["fields"])
    assert all("source" not in item and "value" not in item for item in row["fields"])
    serialized = dumps(row["fields"])
    assert "2026-09-11" not in serialized
    assert "21:00:00" not in serialized


def test_field_inventory_generator_mapping_covers_current_canonical_pages():
    from rasai.report_temporal_inventory import _generator_path, FIELD_CONTRACT
    assert FIELD_CONTRACT == "report-temporal-field-inventory-v1"
    for page in CATALOG_REPORT_PAGES:
        mapping = _generator_path(page.filename)
        assert "N/D" not in mapping
        assert mapping.endswith("rasai.catalog_report_presentation._shell")
    assert "_catalog_body" in _generator_path("cat-01.html")
