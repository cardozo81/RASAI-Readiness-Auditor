from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from rasai.m22_quality_domains import (
    extract_accessibility_issues,
    extract_performance_diagnostics,
)
from rasai.report_navigation import available_navigation


class M22QualityDomainTests(unittest.TestCase):
    def test_accessibility_failure_preserves_lighthouse_selector_and_snippet(self) -> None:
        payload = {
            "lighthouseResult": {
                "categories": {
                    "accessibility": {
                        "auditRefs": [
                            {"id": "button-name", "weight": 10},
                            {"id": "manual-check", "weight": 0},
                        ]
                    }
                },
                "audits": {
                    "button-name": {
                        "title": "Buttons do not have an accessible name",
                        "description": "Buttons need a programmatically determinable name.",
                        "score": 0,
                        "scoreDisplayMode": "binary",
                        "details": {
                            "type": "table",
                            "items": [
                                {
                                    "node": {
                                        "selector": "#header > button.icon",
                                        "snippet": "<button class=\"icon\"><svg></svg></button>",
                                        "nodeLabel": "button.icon",
                                        "explanation": "Fix the accessible name.",
                                    }
                                }
                            ],
                        },
                    },
                    "manual-check": {
                        "title": "Manual check",
                        "score": None,
                        "scoreDisplayMode": "manual",
                    },
                },
            }
        }
        issues, manual = extract_accessibility_issues(payload)
        self.assertEqual(manual, 1)
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue.lighthouse_audit_id, "button-name")
        self.assertEqual(issue.evidence.selector, "#header > button.icon")
        self.assertEqual(issue.evidence.snippet, '<button class="icon"><svg></svg></button>')
        self.assertIn("w3.org", issue.reference_url or "")

    def test_accessibility_never_invents_selector_when_source_has_none(self) -> None:
        payload = {
            "lighthouseResult": {
                "categories": {"accessibility": {"auditRefs": [{"id": "button-name"}]}},
                "audits": {
                    "button-name": {
                        "title": "Buttons do not have an accessible name",
                        "description": "Automated failure without node details.",
                        "score": 0,
                        "scoreDisplayMode": "binary",
                        "explanation": "No node detail returned by this run.",
                    }
                },
            }
        }
        issues, _ = extract_accessibility_issues(payload)
        self.assertEqual(len(issues), 1)
        self.assertIsNone(issues[0].evidence.selector)
        self.assertIsNone(issues[0].evidence.snippet)

    def test_performance_extracts_render_blocking_resource_without_a11y_leakage(self) -> None:
        payload = {
            "lighthouseResult": {
                "categories": {
                    "performance": {"auditRefs": [{"id": "render-blocking-insight"}]},
                    "accessibility": {"auditRefs": [{"id": "button-name"}]},
                },
                "audits": {
                    "render-blocking-insight": {
                        "title": "Render-blocking requests",
                        "description": "Requests block the initial render.",
                        "score": 0.35,
                        "scoreDisplayMode": "numeric",
                        "displayValue": "Potential savings of 420 ms",
                        "details": {
                            "items": [
                                {
                                    "url": "https://example.test/app.css",
                                    "wastedMs": 420,
                                    "totalBytes": 18000,
                                }
                            ]
                        },
                    },
                    "button-name": {
                        "title": "Buttons do not have an accessible name",
                        "score": 0,
                        "scoreDisplayMode": "binary",
                        "details": {"items": [{"node": {"selector": "button.icon"}}]},
                    },
                },
            }
        }
        diagnostics = extract_performance_diagnostics(payload)
        self.assertEqual(len(diagnostics), 1)
        item = diagnostics[0]
        self.assertEqual(item.lighthouse_audit_id, "render-blocking-insight")
        self.assertEqual(item.category, "RENDER_BLOCKING")
        self.assertEqual(item.evidence.url, "https://example.test/app.css")
        self.assertEqual(item.evidence.wasted_ms, 420.0)
        self.assertNotIn("button-name", {row.lighthouse_audit_id for row in diagnostics})

    def test_navigation_keeps_accessibility_as_optional_canonical_domain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory)
            for name in ("index.html", "accessibility.html", "web-performance.html", "references.html"):
                (report / name).write_text("x", encoding="utf-8")
            items = available_navigation(report, "accessibility.html")
            self.assertIn(("Acessibilidade", "accessibility.html"), items)
            self.assertIn(("Web Performance", "web-performance.html"), items)
            self.assertLess(
                items.index(("Acessibilidade", "accessibility.html")),
                items.index(("Web Performance", "web-performance.html")),
            )


if __name__ == "__main__":
    unittest.main()
