from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
DOCS = (ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md")))
_MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")



def test_internal_markdown_links_resolve() -> None:
    failures: list[str] = []
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        for raw_target in _MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith("#"):
                continue
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
                continue
            if target.startswith("mailto:"):
                continue
            relative = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not relative:
                continue
            resolved = (path.parent / relative).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                failures.append(f"{path.relative_to(ROOT)} -> {target} (fora do repositório)")
                continue
            if not resolved.exists():
                failures.append(f"{path.relative_to(ROOT)} -> {target}")

    assert not failures, "links Markdown internos quebrados:\n" + "\n".join(failures)


def test_documentation_uses_hyphen_instead_of_dash_characters() -> None:
    failures: list[str] = []
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        for character, name in (("—", "travessão"), ("–", "meia-risca")):
            if character not in text:
                continue
            lines = [
                str(index)
                for index, line in enumerate(text.splitlines(), 1)
                if character in line
            ]
            failures.append(
                f"{path.relative_to(ROOT)}: {name} em linha(s) {', '.join(lines[:12])}"
            )

    assert not failures, "use hífen '-' na documentação:\n" + "\n".join(failures)
