from __future__ import annotations

from pathlib import Path
import re


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTATION_ROOTS = (REPOSITORY_ROOT / "README.md", REPOSITORY_ROOT / "docs")
_INTERNAL_MILESTONE_REFERENCE = re.compile(r"(?i)(?<![A-Za-z0-9])m\d+")


def _documentation_files() -> tuple[Path, ...]:
    from runpy import run_path
    _public_documentation_paths = run_path(str(REPOSITORY_ROOT / "tests/test_user_facing_language_contract.py"))["_public_documentation_paths"]
    return _public_documentation_paths()

def test_documentation_does_not_expose_internal_milestone_identifiers() -> None:
    violations: list[str] = []
    for path in _documentation_files():
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            if _INTERNAL_MILESTONE_REFERENCE.search(line):
                relative = path.relative_to(REPOSITORY_ROOT).as_posix()
                violations.append(f"{relative}:{line_number}: {line.strip()}")

    assert not violations, (
        "Documentation must use functional/product capability names instead of internal milestone identifiers:\n"
        + "\n".join(violations)
    )
