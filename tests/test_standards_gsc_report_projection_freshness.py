from __future__ import annotations

from rasai.standards_gsc_observability_runtime import _clear_gsc_report_panels, _remove_marked_panel


def _block(marker: str, body: str) -> str:
    return f"<!-- {marker}:START -->{body}<!-- {marker}:END -->"


def test_clear_gsc_report_panels_removes_only_gsc_projection_blocks(tmp_path) -> None:
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    path = report_dir / "observability.html"
    path.write_text(
        "<html><body><main>"
        + _block("RASAI_GSC_OBSERVATIONAL_METRICS", "<section>old inspection</section>")
        + _block("RASAI_GSC_CRAWL_FRESHNESS_METRICS", "<section>old crawl</section>")
        + _block("RASAI_GSC_SITEMAP_METRICS", "<section>old sitemaps</section>")
        + _block("RASAI_GSC_RETURNED_VISIBILITY_COUNTS", "<section>old visibility</section>")
        + _block("RASAI_UNRELATED_PANEL", "<section>keep me</section>")
        + "</main></body></html>",
        encoding="utf-8",
    )

    assert _clear_gsc_report_panels(report_dir) is True
    html = path.read_text(encoding="utf-8")

    assert "RASAI_GSC_OBSERVATIONAL_METRICS" not in html
    assert "RASAI_GSC_CRAWL_FRESHNESS_METRICS" not in html
    assert "RASAI_GSC_SITEMAP_METRICS" not in html
    assert "RASAI_GSC_RETURNED_VISIBILITY_COUNTS" not in html
    assert "RASAI_UNRELATED_PANEL" in html
    assert "keep me" in html
    assert html.endswith("</main></body></html>")


def test_clear_gsc_report_panels_is_idempotent(tmp_path) -> None:
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    path = report_dir / "observability.html"
    path.write_text(
        "<main>" + _block("RASAI_GSC_OBSERVATIONAL_METRICS", "old") + "</main>",
        encoding="utf-8",
    )

    assert _clear_gsc_report_panels(report_dir) is True
    once = path.read_text(encoding="utf-8")
    assert _clear_gsc_report_panels(report_dir) is False
    assert path.read_text(encoding="utf-8") == once


def test_remove_marked_panel_does_not_truncate_malformed_unclosed_block(tmp_path) -> None:
    path = tmp_path / "observability.html"
    original = "<main><!-- RASAI_GSC_OBSERVATIONAL_METRICS:START --><section>partial</section></main>"
    path.write_text(original, encoding="utf-8")

    assert _remove_marked_panel(path, "RASAI_GSC_OBSERVATIONAL_METRICS") is False
    assert path.read_text(encoding="utf-8") == original
