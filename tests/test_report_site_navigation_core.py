from __future__ import annotations

import re
from pathlib import Path
import tempfile
import unittest

from rasai import report_site
from rasai.report_navigation import NAV_ITEMS


_LINK_RE = re.compile(r"<a class='([^']*)' href='([^']+)'>([^<]+)</a>")
_NAV_RE = re.compile(r"<nav>(.*?)</nav>", re.DOTALL)


class BaseReportNavigationCoreTests(unittest.TestCase):
    def test_base_report_shell_uses_canonical_navigation_core(self) -> None:
        self.assertFalse(hasattr(report_site, "_navigation"))
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp)
            for _, filename in NAV_ITEMS:
                (report_dir / filename).write_text("<html></html>", encoding="utf-8")

            current = "remediation.html"
            html = report_site._shell("Remediações", current, report_dir, "<section>ok</section>")
            nav_match = _NAV_RE.search(html)
            self.assertIsNotNone(nav_match)
            links = _LINK_RE.findall(nav_match.group(1))
            self.assertEqual(
                [(href, label) for _, href, label in links],
                [(filename, label) for label, filename in NAV_ITEMS],
            )
            self.assertEqual([href for css_class, href, _ in links if css_class == "active"], [current])


if __name__ == "__main__":
    unittest.main()
