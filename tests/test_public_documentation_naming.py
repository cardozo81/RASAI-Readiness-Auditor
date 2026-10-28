from __future__ import annotations

from pathlib import Path
import re


_INTERNAL_MILESTONE = re.compile(r"(?<![A-Za-z0-9_])M\d{1,2}(?![A-Za-z0-9_])")


def test_user_facing_markdown_does_not_expose_internal_milestone_labels() -> None:
    root = Path(__file__).resolve().parents[1]
    from runpy import run_path
    _public_documentation_paths = run_path(str(root / "tests/test_user_facing_language_contract.py"))["_public_documentation_paths"]
    candidates = _public_documentation_paths()
    violations: list[str] = []

    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if _INTERNAL_MILESTONE.search(line):
                violations.append(f"{path.relative_to(root).as_posix()}:{number}: {line.strip()}")

    assert not violations, (
        "Documentação voltada ao usuário não deve expor identificadores internos M*. "
        "Use o nome funcional da capacidade.\n" + "\n".join(violations)
    )
