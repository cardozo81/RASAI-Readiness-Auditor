"""#728/A: verify every persisted analytical field has a human-facing title.

Only labels on HTML tables change. Evidence, source IDs, currencies, values,
annexes, and historical SQLite are never translated or rewritten.
"""
from rasai.parallel_report.analytical_views import FIELDS
from rasai.parallel_report.components import table
from rasai.parallel_report.presentation_labels import FIELD_LABELS


def test_728_every_selected_analytical_field_has_explicit_pt_br_header():
    columns = {field for selected in FIELDS.values() for field in selected.split()}
    missing = sorted(columns.difference(FIELD_LABELS))
    # Reason has two distinct, already-humanized caller contexts: the
    # classification explanation and the analytical-projection motive.
    # A global label would erase the classification-specific public contract.
    assert missing == ["reason"], "Uncovered fields: " + ", ".join(missing)
    for field in columns.difference({"reason"}):
        assert FIELD_LABELS[field].strip(), field
        assert FIELD_LABELS[field] != field.replace("_", " "), field


def test_728_humanized_column_names_preserve_literal_source_evidence():
    source = {
        "observation_id": "OBS-728-EXACT",
        "fetch_status": "OBSERVED",
        "requested_url": "https://example.test/path",
        "error_code": "SOURCE_SYSTEM_ERROR",
        "cost_currency": "USD",
    }
    before = source.copy()
    columns = [(name, name.replace("_", " ")) for name in source]
    html = table("Evidência preservada", [source], columns, full_text=True)
    for name in source:
        assert FIELD_LABELS[name] in html
    assert 'fetch status' not in html
    assert 'observation id' not in html
    assert 'requested url' not in html
    assert 'OBS-728-EXACT' in html
    assert 'SOURCE_SYSTEM_ERROR' in html
    assert 'https://example.test/path' in html
    assert source == before
