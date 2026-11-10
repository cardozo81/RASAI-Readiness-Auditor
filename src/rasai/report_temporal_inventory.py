"""Read-only, literal-free temporal presentation census for report-catalog #692.

Inspect rendered HTML separately from evidence JSON. This inventory does not
rewrite timestamps or claim that an untyped Unix number is a time instant.
"""
from __future__ import annotations

import argparse
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


class _Census(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.visible = []
        self.technical = []

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
        (self.technical if any(tag in {"code", "pre"} for tag in self.stack)
         else self.visible).append(data)


def inspect_html(html: str, *, zone: str) -> dict:
    scanner = _Census()
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
    )


def inventory(report_dir: Path, *, zone: str) -> dict:
    if not report_dir.is_dir():
        raise ValueError("report-catalog directory unavailable")
    pages = {}
    for page in CATALOG_REPORT_PAGES:
        path = report_dir / page.filename
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000_000:
            raise ValueError("required report page unavailable or unsafe")
        pages[page.filename] = inspect_html(path.read_text(encoding="utf-8"), zone=zone)
    return dict(contract=CONTRACT, zone=zone, pages=pages,
                limitations=["COUNTS_ONLY_NO_LITERAL_DISCLOSURE",
                             "UNOBSERVED_OR_UNTYPED_TEMPORAL_FIELDS_REMAIN_ND"])


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
