from __future__ import annotations

from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
OLD_REPO_SLUG = "cardozo81/SearchGEO-Readiness-Auditor"
REPO_SENTINEL = "__RASAI_REPO_SLUG_SENTINEL__"
TEXT_SUFFIXES = {
    ".py", ".md", ".toml", ".yml", ".yaml", ".json", ".txt", ".cmd",
    ".ps1", ".ini", ".cfg", ".html", ".css", ".js", ".xml", ".csv",
}
EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__"}


def included(path: Path) -> bool:
    return not any(part in EXCLUDED_DIRS for part in path.parts)


def migrate_paths() -> None:
    old_package = ROOT / "src" / "searchgeo"
    new_package = ROOT / "src" / "rasai"
    if old_package.exists():
        if new_package.exists():
            raise RuntimeError("src/rasai already exists while src/searchgeo is still present")
        old_package.rename(new_package)

    candidates = [p for p in ROOT.rglob("*") if included(p)]
    for path in sorted(candidates, key=lambda p: len(p.parts), reverse=True):
        if not path.exists():
            continue
        name = path.name
        new_name = (
            name.replace("SEARCHGEO", "RASAI")
            .replace("SearchGEO", "RASAi")
            .replace("searchgeo", "rasai")
        )
        if new_name == name:
            continue
        target = path.with_name(new_name)
        if target.exists():
            raise RuntimeError(f"cannot rename {path} to existing {target}")
        path.rename(target)


def migrate_text() -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or not included(path):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"README", "LICENSE"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        original = text
        # Keep the current GitHub repository slug valid until the repository itself is renamed.
        text = text.replace(OLD_REPO_SLUG, REPO_SENTINEL)
        text = text.replace("SEARCHGEO_", "RASAI_")
        text = text.replace("SEARCHGEO", "RASAI")
        text = text.replace("SearchGEO", "RASAi")
        text = text.replace("searchgeo", "rasai")
        # These are RASAi-owned environment-variable contracts, not upstream standards.
        text = text.replace("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        text = text.replace("GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN", "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN")
        text = text.replace(REPO_SENTINEL, OLD_REPO_SLUG)
        if text != original:
            path.write_text(text, encoding="utf-8")


def normalize_pyproject() -> None:
    path = ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'^name\s*=\s*"rasai-readiness-auditor"$', 'name = "rasai-readiness-auditor"', text, flags=re.MULTILINE)
    lines = text.splitlines()
    output: list[str] = []
    in_scripts = False
    seen_scripts: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if stripped == "[project.scripts]":
            in_scripts = True
            output.append(line)
            continue
        if in_scripts and stripped.startswith("[") and stripped.endswith("]"):
            in_scripts = False
        if in_scripts and "=" in line and not stripped.startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in {"rasai", "rasai-console"}:
                if key in seen_scripts:
                    continue
                seen_scripts.add(key)
        output.append(line)
    text = "\n".join(output) + "\n"
    path.write_text(text, encoding="utf-8")


def remove_legacy_compatibility_language() -> None:
    branding = ROOT / "docs" / "BRANDING_AND_COMPATIBILITY.md"
    if branding.exists():
        text = branding.read_text(encoding="utf-8")
        text = re.sub(
            r"\nPor compatibilidade operacional, também são aceitos:.*?\nEsses elementos são contratos técnicos e não definem a marca exibida ao usuário\.\n",
            "\nNão há aliases públicos da identidade anterior. O runtime, a documentação e a configuração usam exclusivamente RASAi/RASAI. IDs metodológicos como `BR-GEO-*` e `SCORE-GEO-*` permanecem por serem contratos de metodologia, não nomes do produto.\n",
            text,
            flags=re.DOTALL,
        )
        branding.write_text(text, encoding="utf-8")


def remove_one_shot_files() -> None:
    for relative in (
        ".github/scripts/complete_rasai_namespace_migration.py",
        ".github/workflows/rasai-namespace-migration.yml",
    ):
        target = ROOT / relative
        if target.exists():
            target.unlink()
    scripts_dir = ROOT / ".github" / "scripts"
    if scripts_dir.exists() and not any(scripts_dir.iterdir()):
        scripts_dir.rmdir()


def validate_no_legacy_namespace() -> None:
    violations: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or not included(path):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"README", "LICENSE"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        scrubbed = text.replace(OLD_REPO_SLUG, "")
        if re.search(r"SEARCHGEO|SearchGEO|searchgeo", scrubbed):
            violations.append(str(path.relative_to(ROOT)))
    if (ROOT / "src" / "searchgeo").exists():
        violations.append("src/searchgeo")
    if violations:
        raise RuntimeError("legacy SearchGEO namespace remains in: " + ", ".join(sorted(set(violations))))


def main() -> None:
    migrate_paths()
    migrate_text()
    normalize_pyproject()
    remove_legacy_compatibility_language()
    remove_one_shot_files()
    validate_no_legacy_namespace()
    print("RASAi namespace migration completed successfully")


if __name__ == "__main__":
    main()
