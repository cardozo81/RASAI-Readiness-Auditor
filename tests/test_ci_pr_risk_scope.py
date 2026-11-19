"""Offline contract for #743: no false lightweight classification."""
from scripts.ci_pr_risk_scope import (
    INIT_PATH, PUBLICATION_PATH, classify_checkout, classify_paths, version_only
)


def test_docs_and_editorial_path_selection():
    assert classify_paths(["README.md", "docs/CI_POLICY.md"]) == "docs"
    assert classify_paths(["src/rasai/parallel_report/render.py",
                           "tests/report_presentation/test_source_display_contract.py",
                           "docs/PRESENTATION_EDITORIAL_ACCEPTANCE.md"]) == "presentation"
    # Browser/runtime assets are deliberately outside the lightweight lane.
    assert classify_paths(["src/rasai/parallel_report/assets/app.js"]) == "full"
    assert classify_paths(["src/rasai/parallel_report/assets/site.css"]) == "full"


def test_unrecognized_or_critical_changes_are_full():
    for names in (
        [], ["src/rasai/scoring.py"], ["src/rasai/parallel_report/generator.py"],
        ["src/rasai/parallel_report/sqlite_reader.py"],
        [".github/workflows/full-regression.yml"],
        [".github/workflows/score-geo-validation.yml"],
        ["scripts/ci_pr_risk_scope.py"],
        ["src/rasai/parallel_report/render.py", "src/rasai/m18_ai.py"],
        ["docs/CI_POLICY.md", "src/rasai/score_geo.py"],
        ["docs/../src/rasai/scoring.py"],
        ["docs/config.json"],
    ):
        assert classify_paths(names) == "full", names


def test_version_only_is_mandatory_for_publish_and_init():
    init_before = '__version__ = "0.4.30"\n'
    init_after = '__version__ = "0.4.31"\n'
    assert version_only(INIT_PATH, init_before, init_after)
    before = ("before\n"
              "        versions = (__version__, '0.4.29') if historical_version else (__version__,)\n"
              "after\n")
    after = ("before\n"
             "        versions = (__version__, '0.4.30', '0.4.29') if historical_version else (__version__,)\n"
             "after\n")
    assert version_only(PUBLICATION_PATH, before, after)
    assert not version_only(PUBLICATION_PATH, before, after.replace("after", "new behavior"))
    assert not version_only(INIT_PATH, init_before, 'print("side effect")\n' + init_after)

    sources = {INIT_PATH: (init_before, init_after), PUBLICATION_PATH: (before, after)}
    assert classify_paths(list(sources), sources.__getitem__) == "presentation"
    assert classify_paths([PUBLICATION_PATH]) == "full"


def test_bad_event_and_commit_headers_fail_closed():
    assert classify_checkout("a" * 40, "b" * 40, "push") == "full"
    assert classify_checkout("bad", "b" * 40, "pull_request") == "full"
    assert classify_checkout("", "", "workflow_dispatch") == "full"
