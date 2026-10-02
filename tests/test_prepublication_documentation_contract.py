from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DOC_FILES = (ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md")))

# Documentation is a current-state contract after the public v0.5.0 release,
# not a migration log for discarded development surfaces. Historical/future
# documents must be explicitly classified instead of redefining the live contract.
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

FIVE_CATEGORY_PAGESPEED_DEFAULT = "performance,accessibility,best-practices,seo,agentic-browsing"
STALE_AGENTIC_TRANSPORT_WORDING = (
    re.compile(r"agentic-browsing[^\n]{0,160}não (?:é|deve ser) enviado[^\n]{0,80}PageSpeed", re.IGNORECASE),
    re.compile(r"Agentic Browsing[^\n]{0,160}(?:fonte|adapter) Lighthouse diret[oa] separad[oa]", re.IGNORECASE),
)

RELEASE_STATE_DOCUMENTS = (
    "README.md",
    "docs/README.md",
    "docs/specification/01_PROJECT_CHARTER_SCOPE.md",
    "docs/specification/10_DECISIONS.md",
    "docs/ENVIRONMENT_VARIABLES.md",
    "docs/INTERACTIVE_CONSOLE.md",
    "docs/AUDIT_REPROCESSING.md",
    "docs/AUDIT_CATALOG_WORKFLOW.md",
    "docs/EXECUTION_SCHEDULING.md",
    "docs/CONSOLE_VISUAL_SEMANTICS.md",
    "docs/WINDOWS_SECRET_PERSISTENCE.md",
    "docs/PARTIAL_DIAGNOSTIC_EXECUTION.md",
    "docs/AI_FAILURE_FULFILLMENT_CONTRACT.md",
)

FORBIDDEN_GENERIC_PREPUBLICATION = (
    re.compile(r"RASAi ainda não foi publicado", re.IGNORECASE),
    re.compile(r"produto ainda não foi publicado", re.IGNORECASE),
    re.compile(r"desenvolvimento e validação pré-publicação", re.IGNORECASE),
    re.compile(r"\*\*Estado do produto:\*\*\s*pré-publicação", re.IGNORECASE),
)



def test_documentation_does_not_publish_discarded_implementation_history() -> None:
    violations: list[str] = []
    for path in DOC_FILES:
        text = path.read_text(encoding="utf-8")
        for pattern in (*FORBIDDEN_IMPLEMENTATION_HISTORY, *STALE_DELIVERY_METADATA):
            if pattern.search(text):
                violations.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
    assert not violations, "documentation contains implementation-history framing:\n" + "\n".join(violations)


def test_canonical_pagespeed_documents_publish_current_five_category_default() -> None:
    for relative in (
        "docs/LIGHTHOUSE_CATEGORIES.md",
        "docs/LIGHTHOUSE_PAGESPEED_TRANSPORT.md",
        "docs/specification/21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert FIVE_CATEGORY_PAGESPEED_DEFAULT in text, f"missing current PageSpeed category contract in {relative}"
        assert "Agentic" in text and "experiment" in text.casefold(), f"missing Agentic experimental qualification in {relative}"


def test_canonical_pagespeed_documents_do_not_publish_stale_agentic_transport_separation() -> None:
    violations: list[str] = []
    for relative in (
        "docs/LIGHTHOUSE_CATEGORIES.md",
        "docs/LIGHTHOUSE_PAGESPEED_TRANSPORT.md",
        "docs/specification/21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md",
        "docs/CLI_REFERENCE.md",
        "docs/ENVIRONMENT_VARIABLES.md",
        "docs/AI_RUNTIME_ORCHESTRATION.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for pattern in STALE_AGENTIC_TRANSPORT_WORDING:
            if pattern.search(text):
                violations.append(f"{relative}: {pattern.pattern}")
    assert not violations, "PageSpeed documentation contains stale Agentic transport separation:\n" + "\n".join(violations)


def test_current_normative_documents_do_not_claim_product_is_prepublication() -> None:
    violations: list[str] = []
    for relative in RELEASE_STATE_DOCUMENTS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for pattern in FORBIDDEN_GENERIC_PREPUBLICATION:
            if pattern.search(text):
                violations.append(f"{relative}: {pattern.pattern}")
    assert not violations, "published product is described as generically pre-publication:\n" + "\n".join(violations)


def test_runner_future_assessment_tracks_live_issue_1_not_unrelated_163() -> None:
    for relative in (
        "README.md",
        "docs/README.md",
        "docs/SAAS_RUNNER_ARTIFACTS_FUTURE_ASSESSMENT.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "Issue #163" not in text
        assert "issues/163" not in text
        assert ("Issue #1" in text) or ("issues/1" in text)


def test_aud_rpr_parity_matrix_is_historical_not_an_open_release_gate() -> None:
    text = (ROOT / "docs/AUD_RPR_PARITY_MATRIX_110.md").read_text(encoding="utf-8")
    folded = text.casefold()
    assert "registro histórico" in folded
    assert "#110 permanece aberta" not in text
    assert "não equivale a homologação ponta a ponta" not in folded
    for issue in ("#15", "#92", "#109", "#110"):
        assert issue in text
    assert "fechadas/completed" in folded
