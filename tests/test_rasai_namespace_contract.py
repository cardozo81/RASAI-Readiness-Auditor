from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".py", ".md", ".toml", ".yml", ".yaml", ".json", ".txt", ".cmd",
    ".ps1", ".ini", ".cfg", ".html", ".css", ".js", ".xml", ".csv",
}
EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}


def _legacy_namespace_tokens() -> tuple[str, ...]:
    base = "search" + "geo"
    return (
        base,
        "Search" + "GEO",
        ("SEARCH" + "GEO"),
        "Search/" + "GEO",
        "Search / " + "GEO",
    )


def _old_product_geo_labels() -> tuple[str, ...]:
    return ("GEO" + " Readiness", "Readiness " + "GEO")


def _included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return not any(part in EXCLUDED_DIRS for part in relative.parts)


def test_obsolete_product_namespace_is_absent_from_repository() -> None:
    violations: list[str] = []
    tokens = _legacy_namespace_tokens()
    old_labels = _old_product_geo_labels()

    for path in ROOT.rglob("*"):
        if not _included(path):
            continue
        relative = str(path.relative_to(ROOT))
        if any(token in relative for token in tokens):
            violations.append(relative)
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"README", "LICENSE"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(token in text for token in tokens):
            violations.append(relative)
        folded = text.casefold()
        if any(label.casefold() in folded for label in old_labels):
            violations.append(f"{relative}:old-product-geo-label")

    assert not violations, "obsolete product namespace remains in: " + ", ".join(sorted(set(violations)))


def test_public_documents_use_ascii_hyphen_instead_of_long_dash() -> None:
    en_dash = chr(0x2013)
    em_dash = chr(0x2014)
    violations: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or not _included(path):
            continue
        if path.suffix.lower() not in {".md", ".html"}:
            continue
        text = path.read_text(encoding="utf-8")
        if en_dash in text or em_dash in text:
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "long dash found in public docs/html: " + ", ".join(sorted(violations))


def test_rasai_owned_environment_variable_names_are_canonical() -> None:
    pattern = re.compile(r"(?<!RASAI_)(?:PLAYWRIGHT_CHROMIUM_EXECUTABLE|GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN)")
    violations: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or not _included(path):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"README", "LICENSE"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if pattern.search(text):
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "non-canonical RASAi-owned environment variable remains in: " + ", ".join(sorted(violations))


def test_python_distribution_and_cli_are_rasai_only() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "rasai-readiness-auditor"' in pyproject
    assert 'rasai = "rasai.entrypoint:main"' in pyproject
    assert 'rasai-console = "rasai.console_entrypoint:main"' in pyproject
    assert (ROOT / "src" / "rasai").is_dir()
