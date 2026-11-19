"""Fail-closed risk scope for PR-only CI; never mutates project sources.

Only proven derived presentation files and version-list-only metadata qualify
for a directed test run. Unknown files, absent Git data and manual events
always select full regression. Used by existing checks, not a new workflow.
"""
from __future__ import annotations

import os
from pathlib import PurePosixPath
import re
import subprocess


PUBLIC_PRESENTATION_FILES = frozenset({
    "src/rasai/parallel_report/presentation_labels.py",
    "src/rasai/parallel_report/templates.py",
    "src/rasai/parallel_report/render.py",
    "src/rasai/parallel_report/components.py",
    "src/rasai/parallel_report/page_views.py",
})
INIT_PATH = "src/rasai/parallel_report/__init__.py"
PUBLICATION_PATH = "src/rasai/parallel_report/publication.py"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_VERSION = re.compile(r'^__version__ = "[0-9][a-zA-Z0-9.+-]*"$')
_HISTORICAL_VERSIONS = re.compile(
    r"^        versions = \(__version__,.*\) if historical_version else \(__version__,\)$"
)


def version_only(path: str, before: str, after: str) -> bool:
    """Whitelisted metadata changes must not conceal behavior modifications."""
    old, new = before.splitlines(), after.splitlines()
    if len(old) != len(new):
        return False
    changed = [(a, b) for a, b in zip(old, new) if a != b]
    if len(changed) != 1:
        return False
    a, b = changed[0]
    if path == INIT_PATH:
        return bool(_VERSION.fullmatch(a) and _VERSION.fullmatch(b))
    if path == PUBLICATION_PATH:
        return bool(_HISTORICAL_VERSIONS.fullmatch(a) and
                    _HISTORICAL_VERSIONS.fullmatch(b))
    return False


def classify_paths(paths: list[str], content=None) -> str:
    """docs, presentation or full (default); filenames are Git paths."""
    if not paths:
        return "full"
    scope = "docs"
    for path in paths:
        if not path or path.startswith("/") or "\\" in path or ".." in PurePosixPath(path).parts:
            return "full"
        if path == "README.md" or (
            path.startswith("docs/") and path.endswith(".md")
        ):
            continue
        # Asset JavaScript/CSS can affect cross-page interaction, browser and
        # accessibility semantics: keep full+Chromium for those changes.
        if (path in PUBLIC_PRESENTATION_FILES
                or (path.startswith("tests/report_presentation/")
                    and path.endswith(".py"))):
            scope = "presentation"
            continue
        if path in {INIT_PATH, PUBLICATION_PATH}:
            if content is None:
                return "full"
            before, after = content(path)
            if not version_only(path, before, after):
                return "full"
            scope = "presentation"
            continue
        return "full"
    return scope


def _git(*arguments: str) -> bytes:
    return subprocess.check_output(
        ["git", *arguments], stderr=subprocess.DEVNULL, timeout=10
    )


def classify_checkout(base: str, head: str, event: str) -> str:
    """Never trust a name-only comparison without merge-base and both trees."""
    if event != "pull_request" or not _SHA.fullmatch(base) or not _SHA.fullmatch(head):
        return "full"
    try:
        ancestor = _git("merge-base", base, head).decode("ascii").strip()
        if not _SHA.fullmatch(ancestor):
            return "full"
        paths = [
            raw.decode("utf-8")
            for raw in _git("diff", "--no-renames", "--name-only", "-z",
                            ancestor, head).split(b"\0") if raw
        ]
        def content(path: str) -> tuple[str, str]:
            return (
                _git("show", f"{ancestor}:{path}").decode("utf-8"),
                _git("show", f"{head}:{path}").decode("utf-8"),
            )
        return classify_paths(paths, content)
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
        return "full"


def main() -> int:
    mode = classify_checkout(
        os.getenv("CI_PR_BASE_SHA", ""),
        os.getenv("CI_PR_HEAD_SHA", ""),
        os.getenv("GITHUB_EVENT_NAME", ""),
    )
    if mode not in {"docs", "presentation", "full"}:
        mode = "full"
    print("CI_RISK_SCOPE=" + mode)
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write("mode=" + mode + "\n")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("Risk-scoped PR checks: **" + mode + "**. "
                         "Full regression remains available and fail-closed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
