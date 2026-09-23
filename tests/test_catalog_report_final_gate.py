from __future__ import annotations

from rasai.catalog_report_style import _JS
from rasai.entrypoint import _blocking_catalog_report_errors


def test_catalog_renderer_or_freshness_error_blocks_final_report_completion() -> None:
    errors = (
        "web-performance:ValueError:optional enrichment",
        "catalog-report:RuntimeError:renderer failed",
        "catalog-report-freshness:RuntimeError:source mismatch",
    )
    assert _blocking_catalog_report_errors(errors) == (
        "catalog-report:RuntimeError:renderer failed",
        "catalog-report-freshness:RuntimeError:source mismatch",
    )
    assert _blocking_catalog_report_errors(("web-performance:ValueError:optional",)) == ()


def test_interactive_table_normalizes_visible_dates_and_formatted_metrics_before_sort() -> None:
    # Visible timestamps are localized to dd/mm/yyyy by the presentation timezone
    # contract. The client-side sorter normalizes that display value back to a
    # lexicographically sortable yyyy-mm-dd key, and strips grouping from milliseconds.
    assert "const normalizeSortValue=" in _JS
    assert "localized=value.match" in _JS
    assert "milliseconds=value.match" in _JS
    assert "rows.sort((a,b)=>valueFor(a,index).localeCompare" in _JS
    # Sorting mutates the complete row dataset before render() slices it into pages.
    sort_at = _JS.index("rows.sort((a,b)=>valueFor(a,index).localeCompare")
    render_at = _JS.index("render();};", sort_at)
    assert sort_at < render_at
