"""Gate for newly introduced versioned filenames; historical paths are not rescanned.

Run in CI against the event's base and checked-out HEAD. This script reads Git
metadata only and does not rename or edit files.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


# Public/externally versioned contract IDs require a separately documented,
# explicit review before an exception is added here. There are no exceptions
# for new paths in this initial policy gate.
PUBLIC_CONTRACT_EXCEPTIONS: frozenset[str] = frozenset()

_TRACKING_TOKENS = (
    # Short issue / PR prefixes must not bypass the numeric-length rule.
    re.compile(r"(?:^|[-_])(?:issue|pr|ticket|task|bug)[-_]?\d+(?=$|[-_.])", re.I),
    # Implementation dates (YYYYMMDD).
    re.compile(r"(?:^|[-_])(?:19|20)\d{6}(?=$|[-_.])"),
    # Standalone issue numbers and opaque numeric tracking suffixes.
    re.compile(r"(?:^|[-_])\d{3,}(?=$|[-_.])"),
)


def prohibited_filename(path: str) -> bool:
    """Inspect the filename only, not directory names or its contents."""
    filename = PurePosixPath(path).name
    return bool(filename) and any(pattern.search(filename) for pattern in _TRACKING_TOKENS)


def parse_added_or_renamed(raw: bytes) -> list[str]:
    """Parse NUL-delimited 'git diff --name-status -z' including rename pairs."""
    tokens = raw.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        status = tokens[index].decode("ascii")
        index += 1
        if not status or status[0] not in "ACDMRTUXB":
            raise ValueError(f"Unexpected git diff status: {status!r}")
        if status.startswith(("R", "C")):
            if index + 1 >= len(tokens):
                raise ValueError("Malformed rename/copy record")
            # The first pathname is the source; the destination is the new name.
            destination = tokens[index + 1]
            index += 2
            paths.append(destination.decode("utf-8", "surrogateescape"))
        else:
            if index >= len(tokens):
                raise ValueError("Malformed diff record")
            destination = tokens[index]
            index += 1
            if status == "A":
                paths.append(destination.decode("utf-8", "surrogateescape"))
    return paths


def git_new_paths(base: str, head: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-status", "-z", "--find-renames", base, head, "--"],
        check=True,
        capture_output=True,
    )
    return parse_added_or_renamed(proc.stdout)


def git_all_paths(head: str) -> list[str]:
    """Enumerate the complete committed Git tree, without index search."""
    proc = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "-z", head],
        check=True,
        capture_output=True,
    )
    return [
        path.decode("utf-8", "surrogateescape")
        for path in proc.stdout.split(b"\0") if path
    ]


def check(paths: list[str]) -> list[str]:
    return sorted(
        path for path in paths
        if prohibited_filename(path) and path not in PUBLIC_CONTRACT_EXCEPTIONS
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Verified Git base commit for incremental checks")
    parser.add_argument("--full-tree", action="store_true", help="Scan every path in the committed HEAD tree")
    parser.add_argument("--head", default="HEAD", help="Commit to validate")
    args = parser.parse_args(argv)
    try:
        if not args.full_tree and not args.base:
            parser.error("--base is required unless --full-tree is set")
        paths = git_all_paths(args.head) if args.full_tree else git_new_paths(args.base, args.head)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Cannot evaluate filenames: {exc}", file=sys.stderr)
        return 2
    invalid = check(paths)
    if invalid:
        print(
            "New or renamed filenames contain internal tracking IDs. "
            "Use stable functional names instead:",
            file=sys.stderr,
        )
        for path in invalid:
            print(f"  {path}", file=sys.stderr)
        return 1
    print(f"Filename policy PASS: {len(paths)} {'committed' if args.full_tree else 'newly introduced/renamed'} paths checked.")
    return 0


def test_flags_tracking_identifiers() -> None:
    names = [
        "tests/test_issue_164_ai_evidence.py",
        "src/rasai/faq_observation_601.py",
        ".github/workflows/geo-304-targeted.yml",
        "docs/REVIEW_20261015.md",
        "docs/plan-pr-7.md",
        "docs/task_02.md",
    ]
    assert check(names) == sorted(names)


def test_preserves_functional_names_and_short_catalog_ids() -> None:
    assert not check([
        "docs/REPOSITORY_FILENAME_POLICY.md",
        "src/rasai/faq_observation.py",
        "tests/test_repository_filename_policy.py",
        ".github/workflows/public-contract-consistency.yml",
        "src/rasai/m25.py",
        "report-catalog/cat-01.html",
    ])


def test_git_name_status_includes_additions_and_rename_destinations() -> None:
    raw = (
        b"A\0docs/added_601.md\0"
        b"M\0docs/unchanged_602.md\0"
        b"D\0docs/deleted_603.md\0"
        b"R100\0docs/old.md\0docs/renamed_604.md\0"
        b"C095\0docs/base.md\0docs/copied_605.md\0"
    )
    assert parse_added_or_renamed(raw) == [
        "docs/added_601.md",
        "docs/renamed_604.md",
        "docs/copied_605.md",
    ]


def test_unusual_pathnames_are_not_shell_interpreted() -> None:
    assert check(parse_added_or_renamed(
        "A\0docs/name $(echo unsafe)_602.md\0".encode()
    )) == ["docs/name $(echo unsafe)_602.md"]


def test_malformed_diff_fails_closed() -> None:
    try:
        parse_added_or_renamed(b"R100\0docs/only-old.md\0")
    except ValueError:
        pass
    else:
        raise AssertionError("Incomplete rename must fail closed")


def test_complete_tree_parser_is_safe_and_returns_all_paths(monkeypatch) -> None:
    class Result:
        stdout = b"src/rasai/safe.py\0docs/historical_639.md\0"
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        assert kwargs["check"] and kwargs["capture_output"]
        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    paths = git_all_paths("HEAD")
    assert seen["command"] == ["git", "ls-tree", "-r", "--name-only", "-z", "HEAD"]
    assert check(paths) == ["docs/historical_639.md"]



def test_entire_committed_tree_has_zero_unapproved_tracking_filename_ids() -> None:
    """A green incremental diff does not excuse regressions in the whole tree."""
    paths = git_all_paths("HEAD")
    assert paths, "The committed checkout must contain repository files"
    assert not PUBLIC_CONTRACT_EXCEPTIONS, (
        "Any new public-name exemption requires its own reviewed contract"
    )
    violations = check(paths)
    assert not violations, (
        f"Tracking IDs in {len(violations)} of {len(paths)} versioned paths:\n"
        + "\n".join(violations[:40])
    )

def missing_workflow_python_paths(root: Path) -> list[str]:
    """Audit positive references across both Actions YAML extensions."""
    workflows = root / ".github" / "workflows"
    missing: list[str] = []
    for workflow in sorted(set(workflows.glob("*.yml")) | set(workflows.glob("*.yaml"))):
        content = workflow.read_text(encoding="utf-8")
        paths = set(re.findall(r"(?:src/rasai|tests)/[A-Za-z0-9_./*-]+\\.py\\b", content))
        for path in sorted(paths):
            if "*" in path or (root / path).is_file():
                continue
            lines = [line.strip() for line in content.splitlines() if path in line]
            absent_guard = re.compile(
                r"\\btest\\s+-[fe]\\s+" + re.escape(path) + r"(?:[;\\s]|$)"
            )
            if lines and all(absent_guard.search(line) for line in lines):
                continue
            missing.append(f"{workflow.name}: {path}")
    return missing


def test_all_ci_workflows_reference_existing_literal_python_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    missing = missing_workflow_python_paths(root)
    assert not missing, "\\n".join(missing)


def test_workflow_reference_inventory_checks_yaml_and_yml(tmp_path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "one.yml").write_text(
        "run: pytest tests/nonexistent_one.py\\n", encoding="utf-8"
    )
    (workflows / "two.yaml").write_text(
        "run: python src/rasai/nonexistent_two.py\\n", encoding="utf-8"
    )
    assert missing_workflow_python_paths(tmp_path) == [
        "one.yml: tests/nonexistent_one.py",
        "two.yaml: src/rasai/nonexistent_two.py",
    ]
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "nonexistent_one.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "rasai").mkdir(parents=True)
    (tmp_path / "src" / "rasai" / "nonexistent_two.py").write_text("", encoding="utf-8")
    assert missing_workflow_python_paths(tmp_path) == []


def test_workflow_reference_inventory_ignores_explicit_negative_guards(tmp_path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "negative.yaml").write_text(
        "run: if test -f src/rasai/removed.py; then exit 1; fi\\n",
        encoding="utf-8",
    )
    assert missing_workflow_python_paths(tmp_path) == []



def test_repository_filename_policy_preserves_external_public_contract_names():
    """Do not confuse short method/catalog IDs with tracking numbers."""
    assert not check([
        "src/rasai/m23.py", "src/rasai/m25.py",
        "docs/REPORT_DESIGN_SYSTEM.md",
        ".github/workflows/report-catalog-visual-smoke.yaml",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
