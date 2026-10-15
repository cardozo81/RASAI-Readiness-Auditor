"""#633 - offline, read-only browser visual-smoke bundle generator.

Use on an *isolated rematerialized report copy*. No new audit or provider call.
Screenshots contain report contents; handle generated output as sensitive.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from typing import Any

from rasai.catalog_report_contract import CATALOG_REPORT_PAGES
from rasai.catalog_report_site import verify_catalog_report_package


class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.row = None
        self.rows: list[str] = []
        self.dialogs = 0
        self.sections: list[str] = []
        self.ids: list[str] = []
        self.local_links: list[str] = []
        self.content_fragments: list[str] = []
        self.in_main = 0
        self.ignored_text = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "main":
            self.in_main += 1
        if self.in_main and tag in {"script", "style"}:
            self.ignored_text += 1
        if self.in_main:
            if attributes.get("id"):
                self.ids.append(str(attributes["id"]))
            for key in ("href", "src"):
                target = attributes.get(key)
                if target and not re.match(r"^(?:https?:|data:|mailto:|tel:)", target, re.I):
                    self.local_links.append(str(target))
        if tag == "section" and attributes.get("id"):
            self.sections.append(str(attributes["id"]))
        if tag == "dialog":
            self.dialogs += 1
        if tag == "table":
            self.depth += 1
        if self.depth and tag == "tr":
            self.row = []

    def handle_endtag(self, tag: str) -> None:
        if self.in_main and tag in {"script", "style"}:
            self.ignored_text = max(0, self.ignored_text - 1)
        if tag == "main":
            self.in_main = max(0, self.in_main - 1)
        if tag == "tr" and self.row is not None:
            self.rows.append(" ".join(" ".join(self.row).split()))
            self.row = None
        if tag == "table":
            self.depth = max(0, self.depth - 1)

    def handle_data(self, data: str) -> None:
        if self.in_main and not self.ignored_text:
            fragment = " ".join(data.split())
            if fragment:
                self.content_fragments.append(fragment)
        if self.row is not None:
            self.row.append(data)


def inventory(directory: Path) -> dict[str, Any]:
    """Keep measurements independent of style/script and section ordering."""
    paths = tuple(page.filename for page in CATALOG_REPORT_PAGES)
    if len(paths) != 19 or len(set(paths)) != 19:
        raise ValueError("canonical page contract is no longer 19 unique paths")
    files = {p.name for p in directory.glob("*.html")}
    if files != set(paths):
        raise ValueError("report pages missing or unexpected duplicate HTML routes")
    report: dict[str, Any] = {}
    for path in paths:
        html = (directory / path).read_text("utf-8")
        table = _Tables()
        table.feed(html)
        report[path] = {
            "table_rows": len(table.rows),
            "table_row_inventory": dict(Counter(table.rows)),
            "section_ids": table.sections,
            "element_ids": table.ids,
            "local_links": dict(Counter(table.local_links)),
            "visible_text": dict(Counter(table.content_fragments)),
            "dialog_count": table.dialogs,
            "menu_count": html.count("data-shared-report-menu="),
        }
    return report


def _check_table_parity(before: dict[str, Any], after: dict[str, Any]) -> None:
    for page in before:
        if before[page]["table_row_inventory"] != after[page]["table_row_inventory"]:
            raise ValueError(f"persisted table row text changed: {page}")
        if not set(before[page]["section_ids"]).issubset(after[page]["section_ids"]):
            raise ValueError(f"preexisting section anchor removed: {page}")
        if before[page]["dialog_count"] != after[page]["dialog_count"]:
            raise ValueError(f"preexisting detail dialog altered: {page}")
        if not set(before[page]["element_ids"]).issubset(after[page]["element_ids"]):
            raise ValueError(f"preexisting evidence anchor or target removed: {page}")
        for field in ("local_links", "visible_text"):
            for fragment, count in before[page][field].items():
                if after[page][field].get(fragment, 0) < count:
                    raise ValueError(
                        f"preexisting {field} fragment or link removed from report: {page}"
                    )


def _physical_report_hashes(directory: Path) -> dict[str, str]:
    """Detect accidental modification of canonical report files during smoke."""
    return {
        str(path.relative_to(directory)): sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _screenshots(report: Path, out: Path, *, pages: tuple[str, ...]) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required only for visual captures") from exc

    captures: dict[str, Any] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for device, width, height in (("desktop", 1440, 900), ("tablet", 820, 1080), ("mobile", 390, 844)):
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                    locale="pt-BR",
                )
                # No outside requests; file CSS and embedded JS continue to work.
                context.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.url.startswith("file://")
                        else route.abort()
                    ),
                )
                for name in pages:
                    page = context.new_page()
                    script_failures: list[str] = []
                    page.on("pageerror", lambda _error: script_failures.append("error"))
                    page.goto((report / name).resolve().as_uri(), wait_until="load")
                    if script_failures:
                        raise ValueError(f"offline report JavaScript failed: {device}/{name}")
                    if page.locator("[data-shared-report-menu]").count() != 1:
                        raise ValueError(f"missing unique canonical navigation: {name}")
                    if page.locator("nav[aria-label='Relatórios'] a").count() != 19:
                        raise ValueError(f"missing canonical menu destination: {name}")
                    if page.locator("nav[aria-label='Relatórios'] a[aria-current='page']").count() != 1:
                        raise ValueError(f"ambiguous selected menu page: {name}")
                    if page.locator("#report-main").count() != 1:
                        raise ValueError(f"missing main landmark: {name}")
                    # Horizontal overflow within dense tables is permitted; the
                    # viewport/document shell itself should never overflow.
                    if page.evaluate("document.documentElement.scrollWidth > innerWidth + 2"):
                        raise ValueError(f"viewport horizontal overflow: {device}/{name}")
                    path = out / "screenshots" / device / (name.removesuffix(".html") + ".png")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(path), full_page=True, animations="disabled")
                    if device == "mobile" and name == "index.html":
                        toggle = page.locator("[data-report-menu-toggle]")
                        toggle.click()
                        if toggle.get_attribute("aria-expanded") != "true":
                            raise ValueError("mobile menu failed to expand")
                        page.screenshot(
                            path=str(out / "screenshots" / "mobile" / "menu-open.png"),
                            full_page=False,
                        )
                        page.keyboard.press("Escape")
                        if toggle.get_attribute("aria-expanded") != "false":
                            raise ValueError("mobile menu did not close via Escape")
                        page.evaluate(
                            """() => {
                                location.hash = '%ZZ';
                                window.dispatchEvent(new Event('hashchange'));
                            }"""
                        )
                        if script_failures:
                            raise ValueError("malformed deep link interrupted the report UI")
                    if device == "desktop" and name in {
                        "index.html", "directed-analysis.html", "cat-07.html",
                    }:
                        pdf = out / "print" / name.replace(".html", ".pdf")
                        pdf.parent.mkdir(parents=True, exist_ok=True)
                        page.pdf(path=str(pdf), format="A4", print_background=True)
                    page.close()
                context.close()
                captures[device] = {"viewport": f"{width}x{height}", "screenshots": len(pages)}

            nojs = browser.new_context(
                viewport={"width": 390, "height": 844},
                java_script_enabled=False,
            )
            nojs.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if route.request.url.startswith("file://")
                    else route.abort()
                ),
            )
            page = nojs.new_page()
            page.goto((report / "index.html").resolve().as_uri(), wait_until="load")
            visible = page.locator("nav[aria-label='Relatórios']").is_visible()
            page.close()
            nojs.close()
            if not visible:
                raise ValueError("canonical navigation hidden with JavaScript disabled")
            captures["javascript_disabled_mobile_navigation"] = True
        finally:
            browser.close()
    return captures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--make-synthetic-fixture", action="store_true")
    parser.add_argument("--baseline-report-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.report_dir) == bool(args.make_synthetic_fixture):
        parser.error("choose exactly one of --report-dir or --make-synthetic-fixture")
    output = args.output_dir.resolve()
    if not args.make_synthetic_fixture:
        source_report = args.report_dir.resolve()
        source_audit = source_report.parent
        if output == source_audit or source_audit in output.parents:
            parser.error("smoke output must be outside the source AUD directory")
    if args.baseline_report_dir:
        baseline = args.baseline_report_dir.resolve()
        if (
            (not args.make_synthetic_fixture and baseline == args.report_dir.resolve())
            or output == baseline or baseline in output.parents
        ):
            parser.error("baseline and candidate must differ; output must not overwrite baseline")
    output.mkdir(parents=True, exist_ok=True)
    if args.make_synthetic_fixture:
        # Fixture uses synthetic test-only data, never real customer material.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_catalog_report_site import AUDIT_ID, _workspace
        from rasai.catalog_report_site import materialize_catalog_report_site
        work = output / "fixture-workspace"
        work.mkdir(parents=True, exist_ok=True)
        workspace, _ = _workspace(work)
        report = materialize_catalog_report_site(audit_id=AUDIT_ID, workspace=workspace).parent
    else:
        report = args.report_dir.resolve()
    immutable_before = _physical_report_hashes(report)
    source_db = report.parent / "audit.db"
    db_before = (
        sha256(source_db.read_bytes()).hexdigest()
        if source_db.is_file() else None
    )
    valid, errors = verify_catalog_report_package(report)
    if not valid:
        raise ValueError("report package not verified: " + "; ".join(errors))
    latest = inventory(report)
    if args.baseline_report_dir:
        original = inventory(args.baseline_report_dir.resolve())
        _check_table_parity(original, latest)
    captures = _screenshots(
        report, output, pages=tuple(p.filename for p in CATALOG_REPORT_PAGES),
    )
    if _physical_report_hashes(report) != immutable_before:
        raise ValueError("source report files changed during offline smoke")
    if db_before is not None and sha256(source_db.read_bytes()).hexdigest() != db_before:
        raise ValueError("source audit.db changed during offline smoke")
    summary = {
        "contract": "RASAI-REPORT-UX-SMOKE-633-001",
        "report_source": "TEST_SYNTHETIC" if args.make_synthetic_fixture else "OPERATOR_ISOLATED_REPORT",
        "manifest_integrity": "VERIFIED",
        "data_row_parity": (
            "VERIFIED_AGAINST_PROVIDED_BASELINE" if args.baseline_report_dir
            else "BASELINE_NOT_PROVIDED"
        ),
        "all_visible_content_parity": (
            "VERIFIED_AGAINST_PROVIDED_BASELINE" if args.baseline_report_dir
            else "BASELINE_NOT_PROVIDED"
        ),
        "source_files_unchanged": True,
        "source_audit_db_sha256_unchanged": db_before is not None,
        "page_count": len(latest),
        "browser_captures": captures,
        "manual_visual_acceptance": "PENDING",
        "score_recomputed": False,
        "collector_or_provider_requests": 0,
        "source_audit_writes": 0,
    }
    (output / "smoke-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
