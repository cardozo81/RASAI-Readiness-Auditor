"""Read-only, literal-free temporal presentation census for report-catalog #692.

Inspect rendered HTML separately from evidence JSON. This inventory does not
rewrite timestamps or claim that an untyped Unix number is a time instant.
"""
from __future__ import annotations

import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from rasai.catalog_report_contract import CATALOG_REPORT_PAGES
from rasai.time_contract import _AWARE_ISO_TIMESTAMP_RE

CONTRACT = "report-temporal-presentation-inventory-v1"
_LOCAL = re.compile(r"\b\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\s*\([^)]{1,80}\)")
_RFC = re.compile(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+\d{2}\s+[A-Z][a-z]{2}\s+\d{4}\s+\d{2}:\d{2}:\d{2}\s+GMT\b")
_NAIVE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?![\d.Z+-])")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b(?![T ]\d{2}:\d{2})")

# The rendered HTML is untrusted: store ONLY type, tag path and line number.
# Never copy literal timestamps, adjacent text, links, attributes or data-*.
FIELD_CONTRACT = "report-temporal-field-inventory-v1"
_MAX_FIELDS_PER_PAGE = 512
# Tag names are untrusted too: custom elements can contain private identifiers.
# Only structural HTML vocabulary may be emitted in the literal-free inventory.
_STRUCTURAL_TAGS = frozenset(
    "html head body main header footer nav aside section article div span p "
    "h1 h2 h3 h4 h5 h6 table thead tbody tfoot tr th td caption colgroup "
    "ul ol li dl dt dd details summary dialog a button strong b em i small "
    "time label form fieldset legend figure figcaption blockquote pre code "
    "script style title select option textarea output address abbr sup sub".split()
)
_FIELD_PATTERNS = (
    ("LOCAL_PRESENTATION", _LOCAL),
    ("AWARE_ISO_VISIBLE_REVIEW", _AWARE_ISO_TIMESTAMP_RE),
    ("HTTP_DATE_VISIBLE_REVIEW", _RFC),
    ("NAIVE_TIMEZONE_ND", _NAIVE),
    ("DATE_ONLY_UNSHIFTED", _DATE),
)
_FACTORY_BY_PAGE = {
    "index.html": "rasai.catalog_report_governance._overview_body",
    "sari.html": "rasai.catalog_report_governance._sari_body",
    "capture-context.html": "rasai.catalog_report_final_refinements._capture_context_body",
    "execution-evidence.html": "rasai.catalog_report_governance._execution_evidence_body",
    "ai-integrations.html": "rasai.ai_dependency_reporting.install + rasai.catalog_report_final_refinements._ai_integrations_body",
    "directed-analysis.html": "rasai.directed_analysis_reporting.directed_analysis_body",
    "geo.html": "rasai.geo_report.geo_body",
    "geo-content-review.html": "rasai.catalog_report_site.materialize_catalog_report_site + rasai.contextual_advisory_html.contextual_panel",
    "methodology.html": "rasai.catalog_report_site._methodology_body",
    "metrics.html": "rasai.catalog_report_site._metrics_body",
    "network.html": "rasai.network_reporting.network_catalog_sections",
}


def _generator_path(filename: str) -> str:
    if filename.startswith("cat-") and filename.endswith(".html"):
        source = "rasai.catalog_report_page._catalog_body"
    else:
        source = _FACTORY_BY_PAGE.get(filename, "N/D")
    return source + " -> rasai.catalog_report_presentation._shell"



class _Census(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.visible = []
        self.technical = []
        self.fields = []
        self.fields_omitted = 0
        self.field_totals = Counter()

    def handle_starttag(self, tag, attrs):
        if tag not in {"br", "hr", "img", "input", "meta", "link", "source", "wbr"}:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if any(tag in {"script", "style"} for tag in self.stack):
            return
        technical = any(tag in {"code", "pre"} for tag in self.stack)
        (self.technical if technical else self.visible).append(data)
        patterns = (
            (("TECHNICAL_ISO_PRESERVED", _AWARE_ISO_TIMESTAMP_RE),
             ("TECHNICAL_HTTP_DATE_PRESERVED", _RFC))
            if technical else _FIELD_PATTERNS
        )
        for classification, pattern in patterns:
            for match in pattern.finditer(data):
                status = classification
                if classification == "LOCAL_PRESENTATION":
                    declared = match.group(0).rsplit("(", 1)[-1].rstrip(")")
                    # An external source may intentionally use another timezone.
                    if declared != self.zone:
                        status = "OTHER_DECLARED_TIMEZONE_REVIEW"
                self.field_totals[status] += 1
                if len(self.fields) >= _MAX_FIELDS_PER_PAGE:
                    self.fields_omitted += 1
                    continue
                self.fields.append({
                    "classification": status,
                    "line": self.getpos()[0] + data.count("\n", 0, match.start()),
                    "tag_path": "/".join(tag if tag in _STRUCTURAL_TAGS else "unknown"
                                         for tag in self.stack[-8:]) or "N/D",
                    "presentation": "TECHNICAL_PRESERVED" if technical else "RENDERED_TEXT",
                })


def inspect_html(html: str, *, zone: str) -> dict:
    scanner = _Census()
    scanner.zone = zone
    scanner.feed(html)
    visible, technical = " ".join(scanner.visible), " ".join(scanner.technical)
    # Classification counts are observations, not a conversion itself.
    return dict(
        local_presentation=len(_LOCAL.findall(visible)),
        aware_iso_unconverted=len(_AWARE_ISO_TIMESTAMP_RE.findall(visible)),
        rfc7231_visible=len(_RFC.findall(visible)),
        naive_timestamp_nd=len(_NAIVE.findall(visible)),
        date_only_unshifted=len(_DATE.findall(visible)),
        technical_aware_iso=len(_AWARE_ISO_TIMESTAMP_RE.findall(technical)),
        zone_advertised=zone in visible,
        field_inventory_contract=FIELD_CONTRACT,
        fields=scanner.fields,
        fields_omitted=scanner.fields_omitted,
        field_totals=dict(sorted(scanner.field_totals.items())),
    )


def inventory(report_dir: Path, *, zone: str) -> dict:
    if not report_dir.is_dir():
        raise ValueError("report-catalog directory unavailable")
    pages = {}
    for page in CATALOG_REPORT_PAGES:
        path = report_dir / page.filename
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000_000:
            raise ValueError("required report page unavailable or unsafe")
        observed = inspect_html(path.read_text(encoding="utf-8"), zone=zone)
        observed["generator_path"] = _generator_path(page.filename)
        pages[page.filename] = observed
    summary = Counter()
    for row in pages.values():
        summary.update(row["field_totals"])
    return dict(contract=CONTRACT, field_inventory_contract=FIELD_CONTRACT,
                zone=zone, pages=pages, summary=dict(sorted(summary.items())),
                limitations=["NO_LITERAL_OR_ATTRIBUTE_DISCLOSURE",
                             "DOM_TEXT_NODE_BOUNDARY_MAY_HIDE_SPLIT_TIMESTAMPS",
                             "LEGACY_COUNTS_JOIN_TEXT_NODES_FIELDS_SCAN_EACH_NODE",
                             "HTML_ENTITIES_DECODED_WHITESPACE_NOT_SOURCE_BYTE_OFFSETS",
                             "FIELDS_CAPPED_AT_512_TOTALS_NOT_TRUNCATED",
                             "CUSTOM_TAG_NAMES_REDACTED_ATTRIBUTES_NOT_INSPECTED",
                             "VISIBLE_RFC_DATE_REQUIRES_TYPED_RENDERER_REVIEW",
                             "UNTYPED_EPOCH_DURATION_AND_EXTERNAL_TIMES_REMAIN_ND",
                             "GENERATOR_PATH_IS_STATIC_MAPPING_NOT_RUNTIME_PROOF",
                             "NOT_A_CERTIFICATE_OF_COMPLETE_FIELD_COVERAGE"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inventário temporal offline, somente contagens.")
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--timezone", required=True)
    args = parser.parse_args(argv)
    from rasai.time_contract import validate_presentation_timezone
    zone = validate_presentation_timezone(args.timezone)
    print(json.dumps(inventory(args.report_dir, zone=zone), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
