from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DOC_FILES = (ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md")))

# RASAi has not been publicly released. Documentation is a current-state contract,
# not a migration log for discarded development surfaces.
FORBIDDEN_IMPLEMENTATION_HISTORY = (
    re.compile(r"\blegacy\b", re.IGNORECASE),
    re.compile(r"\bbackwards? compatibility\b", re.IGNORECASE),
    re.compile(r"\bcompatibilidade retroativa\b", re.IGNORECASE),
    re.compile(r"\bSUPERSEDED\b", re.IGNORECASE),
    re.compile(r"09_IMPLEMENTATION_PLAN\.md", re.IGNORECASE),
)

STALE_DELIVERY_METADATA = (
    re.compile(r"^\*\*Branch:\*\*\s*`?feat/", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\*\*PR:\*\*\s*#\d+", re.IGNORECASE | re.MULTILINE),
)

FOUR_CATEGORY_LIGHTHOUSE = re.compile(
    r"performance,accessibility,best-practices,seo(?!,agentic-browsing)",
    re.IGNORECASE,
)


def test_documentation_does_not_publish_discarded_implementation_history() -> None:
    violations: list[str] = []
    for path in DOC_FILES:
        text = path.read_text(encoding="utf-8")
        for pattern in (*FORBIDDEN_IMPLEMENTATION_HISTORY, *STALE_DELIVERY_METADATA):
            if pattern.search(text):
                violations.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
    assert not violations, "pre-publication documentation contains implementation-history framing:\n" + "\n".join(violations)


def test_documented_lighthouse_default_includes_agentic_browsing() -> None:
    violations: list[str] = []
    for path in DOC_FILES:
        text = path.read_text(encoding="utf-8")
        if FOUR_CATEGORY_LIGHTHOUSE.search(text):
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "stale four-category Lighthouse contract found in:\n" + "\n".join(violations)