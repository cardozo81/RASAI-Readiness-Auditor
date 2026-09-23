from __future__ import annotations

import unittest

from rasai.m16_root_cause import _EXACT_TAGS, _SEMANTIC_CONTEXT_RULES


class M16StructuredDataPolicyTests(unittest.TestCase):
    def test_structured_data_rules_use_script_elements_not_main_context(self) -> None:
        for rule_id in ("BR-GEO-034", "BR-GEO-035", "BR-GEO-036", "BR-GEO-037"):
            self.assertEqual(_EXACT_TAGS[rule_id], ("script",))
            self.assertNotIn(rule_id, _SEMANTIC_CONTEXT_RULES)

    def test_semantic_content_rules_keep_main_as_context_region(self) -> None:
        for rule_id in ("BR-GEO-031", "BR-GEO-033", "BR-GEO-038", "BR-GEO-039", "BR-GEO-049"):
            self.assertIn(rule_id, _SEMANTIC_CONTEXT_RULES)


if __name__ == "__main__":
    unittest.main()
