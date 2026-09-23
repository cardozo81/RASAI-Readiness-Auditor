from __future__ import annotations

import unittest

from rasai.m16_root_cause import _scope_status


class M16ResourceScopeTests(unittest.TestCase):
    def test_http_page_failure_is_page_resource(self) -> None:
        self.assertEqual(
            _scope_status("BR-GEO-005", ()),
            ("PAGE_RESOURCE", "NOT_APPLICABLE", "HIGH"),
        )

    def test_robots_rules_are_domain_resources(self) -> None:
        for rule_id in ("BR-GEO-017", "BR-GEO-018"):
            self.assertEqual(
                _scope_status(rule_id, ()),
                ("DOMAIN_RESOURCE", "NOT_APPLICABLE", "HIGH"),
            )


if __name__ == "__main__":
    unittest.main()
