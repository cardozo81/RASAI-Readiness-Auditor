from __future__ import annotations

from pathlib import Path
import re
from tempfile import TemporaryDirectory

from rasai.acquisition import HttpClient
from rasai.m24_crawling_discovery import execute_m24
from rasai.m24_reporting import enrich_m24_report_site
from tests.test_m24_crawling_discovery import _fixture, _server


_MILESTONE_PUBLIC_RE = re.compile(r"(?i)(?<![A-Za-z0-9])m\d{1,3}")


def _context(text: str, match: re.Match[str] | None) -> str:
    if match is None:
        return ""
    start = max(0, match.start() - 180)
    end = min(len(text), match.end() + 180)
    return text[start:end]


def test_crawling_discovery_public_html_contains_no_internal_delivery_identifier() -> None:
    with _server() as origin, TemporaryDirectory() as directory:
        audit, _, workspace, _ = _fixture(origin, directory)
        execute_m24(
            audit_id=audit.audit_id,
            workspace=workspace,
            technical_ai=False,
            http_client=HttpClient(timeout=1),
        )
        report_dir = workspace.root / "report"
        (report_dir / "css").mkdir(parents=True)
        (report_dir / "css" / "site.css").write_text("body{}\n", encoding="utf-8")
        shell = (
            "<!doctype html><html><body>"
            "<aside><nav><a href='index.html'>Visão geral</a></nav></aside>"
            "<main></main><footer class='footer'>x</footer></body></html>"
        )
        for name in ("index.html", "ai-usage.html", "references.html"):
            (report_dir / name).write_text(shell, encoding="utf-8")

        page = enrich_m24_report_site(audit_id=audit.audit_id, workspace=workspace)
        for path in (page, report_dir / "ai-usage.html", report_dir / "references.html"):
            html = Path(path).read_text(encoding="utf-8")
            match = _MILESTONE_PUBLIC_RE.search(html)
            assert match is None, f"{Path(path).name}: {_context(html, match)!r}"
