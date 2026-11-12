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


def test_temporal_inventory_covers_all_21_real_materializer_pages_without_extra_io(tmp_path, monkeypatch):
    from html.parser import HTMLParser
    from rasai import catalog_report_presentation as presentation, catalog_report_site as site
    from rasai.time_contract import _AWARE_ISO_TIMESTAMP_RE
    from rasai.report_temporal_inventory import _LOCAL

    class NonTemporal(HTMLParser):
        def __init__(self, html):
            super().__init__(convert_charrefs=False)
            self.tokens, self.stack = [], []
            self.feed(html)

        def handle_starttag(self, tag, attrs):
            self.tokens.append(self.get_starttag_text())  # attributes stay exact
            self.stack.append(tag)

        def handle_endtag(self, tag):
            self.tokens.append(('end', tag))
            if tag in self.stack:
                del self.stack[len(self.stack) - 1 - self.stack[::-1].index(tag):]

        def handle_data(self, data):
            if not any(tag in {'code', 'pre', 'script', 'style'} for tag in self.stack):
                data = _LOCAL.sub('INSTANT', _AWARE_ISO_TIMESTAMP_RE.sub('INSTANT', data))
            self.tokens.append(('text', data))

        def handle_entityref(self, name):
            self.tokens.append(('entity', name))

    original = presentation.localize_html_timestamps
    compared = []
    runtime = {}

    def checked(html, **kwargs):
        result = original(html, **kwargs)
        assert NonTemporal(html).tokens == NonTemporal(result).tokens
        compared.append(html)
        for name in ('_overview_body', '_capture_context_body', '_ai_integrations_body'):
            function = getattr(site, name)
            chain = []
            seen = set()
            while function is not None:
                assert callable(function) and id(function) not in seen
                seen.add(id(function))
                chain.append(function.__module__)
                function = getattr(function, '_rasai_original', None)
            runtime[name] = chain
        return result

    monkeypatch.setattr(presentation, 'localize_html_timestamps', checked)
    workspace = _captured_workspace(tmp_path)
    report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    actual = inventory(report, zone="America/Sao_Paulo")
    assert set(actual["pages"]) == {p.filename for p in CATALOG_REPORT_PAGES}
    assert len(actual["pages"]) == 21
    assert all(row["zone_advertised"] for row in actual["pages"].values())
    assert "source_sha256" not in str(actual)
    assert len(compared) == 21
    assert runtime['_overview_body'][-1] == 'rasai.catalog_report_governance'
    assert runtime['_capture_context_body'][-1] == 'rasai.catalog_report_final_refinements'
    assert runtime['_ai_integrations_body'][-1] == 'rasai.catalog_report_final_refinements'
    assert set(runtime['_ai_integrations_body']) <= {
        'rasai.catalog_report_final_refinements', 'rasai.ai_dependency_reporting',
        'rasai.execution_consistency_runtime',
    }


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


def test_field_inventory_classification_codes_have_public_pt_br_labels():
    from rasai.catalog_report_public_labels import public_label
    from rasai.report_temporal_inventory import _FIELD_PATTERNS
    classes = {code for code, _regex in _FIELD_PATTERNS}
    classes.update({
        "OTHER_DECLARED_TIMEZONE_REVIEW",
        "TECHNICAL_ISO_PRESERVED",
        "TECHNICAL_HTTP_DATE_PRESERVED",
    })
    for code in classes:
        label = public_label(code)
        assert label and label != code
        assert "_" not in label


def test_field_inventory_redacts_custom_tag_names_and_attributes():
    from json import dumps
    html = ("<client-secret-abc data-private='token-secret'><p>2026-09-11T00:00:00Z</p>"
            "</client-secret-abc><script>2026-09-11T00:00:00Z</script>")
    row = inspect_html(html, zone="UTC")
    assert row["fields"][0]["tag_path"] == "unknown/p"
    assert row["field_totals"] == {"AWARE_ISO_VISIBLE_REVIEW": 1}
    assert "secret" not in dumps(row)


def test_field_inventory_bounds_records_without_losing_totals_or_raw_evidence():
    html = "<p>2026-09-11T00:00:00Z</p>" * 520
    row = inspect_html(html, zone="UTC")
    assert len(row["fields"]) == 512
    assert row["fields_omitted"] == 8
    assert row["field_totals"] == {"AWARE_ISO_VISIBLE_REVIEW": 520}
    split = inspect_html("<p>2026-09-11T<span>00:00:00Z</span></p>", zone="UTC")
    assert "AWARE_ISO_VISIBLE_REVIEW" not in split["field_totals"]



def test_date_only_census_recognizes_presentation_without_double_counting_instants():
    html = ("<p>CrUX 21/08/2026, fonte 2026-08-22.</p>"
            "<p>Evento 22/08/2026 11:00:00 (America/Sao_Paulo)</p>")
    result = inspect_html(html, zone="America/Sao_Paulo")
    assert result["field_totals"].get("DATE_ONLY_UNSHIFTED") == 2
    assert result["field_totals"].get("LOCAL_PRESENTATION") == 1
