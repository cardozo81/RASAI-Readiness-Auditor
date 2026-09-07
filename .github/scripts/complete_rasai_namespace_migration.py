from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OLD_REPO_SLUG = "cardozo81/SearchGEO-Readiness-Auditor"
NEW_REPO_SLUG = "cardozo81/RASAI-Readiness-Auditor"
TEXT_SUFFIXES = {
    ".py", ".md", ".toml", ".yml", ".yaml", ".json", ".txt", ".cmd",
    ".ps1", ".ini", ".cfg", ".html", ".css", ".js", ".xml", ".csv",
}
EXCLUDED_DIRS = {".git", ".venv", "node_modules", "__pycache__"}


def included(path: Path) -> bool:
    return not any(part in EXCLUDED_DIRS for part in path.parts)


def rename_path(source: Path, destination: Path) -> None:
    if not source.exists() or source == destination:
        return
    if destination.exists():
        raise RuntimeError(f"cannot rename {source} to existing {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.rename(destination)


def migrate_paths() -> None:
    rename_path(ROOT / "src" / "searchgeo", ROOT / "src" / "rasai")

    candidates = [p for p in ROOT.rglob("*") if included(p)]
    for path in sorted(candidates, key=lambda p: len(p.parts), reverse=True):
        if not path.exists():
            continue
        new_name = (
            path.name.replace("SEARCHGEO", "RASAI")
            .replace("SearchGEO", "RASAi")
            .replace("searchgeo", "rasai")
        )
        if new_name != path.name:
            rename_path(path, path.with_name(new_name))

    rename_path(
        ROOT / "src" / "rasai" / "console_config_migration.py",
        ROOT / "src" / "rasai" / "console_config_path.py",
    )
    rename_path(
        ROOT / "tests" / "test_console_config_migration.py",
        ROOT / "tests" / "test_console_config_path.py",
    )
    rename_path(
        ROOT / "docs" / "BRANDING_AND_COMPATIBILITY.md",
        ROOT / "docs" / "BRANDING.md",
    )
    rename_path(
        ROOT / "docs" / "GEO_MINIMUM_REQUIREMENTS.md",
        ROOT / "docs" / "READINESS_MINIMUM_REQUIREMENTS.md",
    )
    rename_path(
        ROOT / "docs" / "specification" / "19_SCORE_APPLICABILITY_GEO_MINIMUMS.md",
        ROOT / "docs" / "specification" / "19_SCORE_APPLICABILITY_READINESS_MINIMUMS.md",
    )


def transform_text(text: str) -> str:
    text = text.replace(OLD_REPO_SLUG, NEW_REPO_SLUG)
    text = text.replace("SEARCHGEO_", "RASAI_")
    text = text.replace("SEARCHGEO", "RASAI")
    text = text.replace("SearchGEO", "RASAi")
    text = text.replace("searchgeo", "rasai")
    text = text.replace("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    text = text.replace("GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN", "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN")
    text = text.replace("console_config_migration", "console_config_path")
    text = text.replace("BRANDING_AND_COMPATIBILITY.md", "BRANDING.md")
    text = text.replace("GEO_MINIMUM_REQUIREMENTS.md", "READINESS_MINIMUM_REQUIREMENTS.md")
    text = text.replace("19_SCORE_APPLICABILITY_GEO_MINIMUMS.md", "19_SCORE_APPLICABILITY_READINESS_MINIMUMS.md")

    text = text.replace("Search/GEO readiness", "Search & AI Readiness")
    text = text.replace("Search/GEO", "Search & AI")
    text = text.replace("Search / GEO", "Search & AI")
    text = text.replace("GEO Readiness", "Search & AI Readiness")
    text = text.replace("Readiness GEO", "Search & AI Readiness")
    text = text.replace("GEO score universal", "score universal de Search & AI Readiness")
    text = text.replace("universal GEO score", "universal Search & AI Readiness score")

    text = text.replace("—", "-").replace("–", "-")
    return text


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
        updated = transform_text(text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def rewrite_runtime_paths() -> None:
    path = ROOT / "src" / "rasai" / "runtime_paths.py"
    path.write_text(
        '''"""Canonical local runtime paths for RASAi."""\nfrom __future__ import annotations\n\nfrom pathlib import Path\n\nCANONICAL_RUNTIME_DIR = ".rasai"\n\n\ndef runtime_directory(root: str | Path) -> Path:\n    """Return the canonical RASAi runtime metadata directory."""\n    return Path(root) / CANONICAL_RUNTIME_DIR\n''',
        encoding="utf-8",
    )


def rewrite_console_config_path() -> None:
    path = ROOT / "src" / "rasai" / "console_config_path.py"
    path.write_text(
        '''"""Canonical interactive-console configuration path for RASAi."""\nfrom __future__ import annotations\n\nimport os\nfrom pathlib import Path\nfrom typing import Mapping, MutableMapping\n\nCONSOLE_INI_ENV = "RASAI_CONSOLE_INI"\nCANONICAL_CONSOLE_INI = "rasai-console.ini"\n\n\ndef prepare_console_config(*, env: MutableMapping[str, str] | None = None, cwd: Path | None = None) -> Path:\n    """Resolve the RASAi console configuration path."""\n    environment = env if env is not None else os.environ\n    base = (cwd if cwd is not None else Path.cwd()).resolve()\n    configured = (environment.get(CONSOLE_INI_ENV) or "").strip()\n    path = Path(configured).expanduser() if configured else Path(CANONICAL_CONSOLE_INI)\n    if not path.is_absolute():\n        path = base / path\n    resolved = path.resolve()\n    environment[CONSOLE_INI_ENV] = str(resolved)\n    return resolved\n\n\ndef canonical_console_config_path(*, env: Mapping[str, str] | None = None, cwd: Path | None = None) -> Path:\n    """Return the effective RASAi console configuration path without filesystem mutation."""\n    environment = env if env is not None else os.environ\n    base = (cwd if cwd is not None else Path.cwd()).resolve()\n    configured = (environment.get(CONSOLE_INI_ENV) or "").strip()\n    path = Path(configured).expanduser() if configured else Path(CANONICAL_CONSOLE_INI)\n    if not path.is_absolute():\n        path = base / path\n    return path.resolve()\n''',
        encoding="utf-8",
    )


def rewrite_tests() -> None:
    (ROOT / "tests" / "test_console_config_path.py").write_text(
        '''from __future__ import annotations\n\nfrom pathlib import Path\nimport tempfile\n\nfrom rasai.console_config_path import CANONICAL_CONSOLE_INI, CONSOLE_INI_ENV, canonical_console_config_path, prepare_console_config\n\n\ndef test_default_console_path_is_rasai() -> None:\n    with tempfile.TemporaryDirectory() as directory:\n        env: dict[str, str] = {}\n        root = Path(directory)\n        path = prepare_console_config(env=env, cwd=root)\n        assert path == (root / CANONICAL_CONSOLE_INI).resolve()\n        assert env[CONSOLE_INI_ENV] == str(path)\n\n\ndef test_explicit_rasai_console_override_is_preserved() -> None:\n    with tempfile.TemporaryDirectory() as directory:\n        root = Path(directory)\n        env = {CONSOLE_INI_ENV: "custom-console.ini"}\n        path = prepare_console_config(env=env, cwd=root)\n        assert path == (root / "custom-console.ini").resolve()\n        assert canonical_console_config_path(env=env, cwd=root) == path\n''',
        encoding="utf-8",
    )

    (ROOT / "tests" / "test_rasai_runtime_branding_and_reports.py").write_text(
        '''from __future__ import annotations\n\nfrom pathlib import Path\nimport sqlite3\nimport tempfile\nimport unittest\n\nfrom rasai.consolidation.index import ConsolidationIndex\nfrom rasai.platform import default_platform_database\nfrom rasai.report_navigation import render_report_navigation\nfrom rasai.report_registry import install\nfrom rasai.runtime_paths import runtime_directory\nfrom rasai.score_geo_003 import resolve_model_path\nfrom rasai.score_geo_003_reporting import _score_reason\n\n\nclass RasaiRuntimeBrandingTests(unittest.TestCase):\n    def test_runtime_directory_is_rasai(self) -> None:\n        with tempfile.TemporaryDirectory() as directory:\n            root = Path(directory)\n            self.assertEqual(runtime_directory(root), root / ".rasai")\n\n    def test_platform_and_consolidation_use_rasai_directory(self) -> None:\n        with tempfile.TemporaryDirectory() as directory:\n            root = Path(directory) / "audits"\n            self.assertEqual(default_platform_database(root), root / ".rasai" / "platform.db")\n            index = ConsolidationIndex(root)\n            self.assertEqual(index.path, root / ".rasai" / "consolidated-index.db")\n\n    def test_score_model_path_uses_rasai_directory(self) -> None:\n        with tempfile.TemporaryDirectory() as directory:\n            project = Path(directory)\n            audit = project / "audits" / "AUD-TEST"\n            audit.mkdir(parents=True)\n            resolved = resolve_model_path(audit)\n            self.assertEqual(resolved, project / ".rasai" / "scoring" / "score-geo-003-model.json")\n\n\nclass RasaiReportConsistencyTests(unittest.TestCase):\n    def test_apdex_navigation_has_one_item_per_html(self) -> None:\n        from rasai import m23_reporting, m25_reporting, report_navigation\n        install()\n        m23_reporting._register_apdex_navigation()\n        m23_reporting._register_apdex_navigation()\n        m25_reporting._register_navigation()\n        m25_reporting._register_navigation()\n        apdex = [item for item in report_navigation.NAV_ITEMS if item[1] == "apdex.html"]\n        experience = [item for item in report_navigation.NAV_ITEMS if item[1] == "apdex-experience.html"]\n        self.assertEqual(apdex, [("Apdex de navegação", "apdex.html")])\n        self.assertEqual(experience, [("Apdex de experiência", "apdex-experience.html")])\n\n    def test_score_reason_explains_missing_validated_model(self) -> None:\n        connection = sqlite3.connect(":memory:")\n        connection.row_factory = sqlite3.Row\n        try:\n            row = connection.execute("SELECT NULL AS value, '[\\"CALIBRATION_MODEL_UNAVAILABLE:SCORE-GEO-003\\"]' AS limitations").fetchone()\n            self.assertIn("VALIDATED", _score_reason(row))\n            self.assertIn("não pode ser consolidado", _score_reason(row))\n        finally:\n            connection.close()\n\n    def test_public_navigation_uses_hyphen_not_long_dash(self) -> None:\n        with tempfile.TemporaryDirectory() as directory:\n            report_dir = Path(directory)\n            (report_dir / "index.html").write_text("x", encoding="utf-8")\n            html = render_report_navigation(report_dir, "index.html")\n            self.assertNotIn("—", html)\n            self.assertNotIn("–", html)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''',
        encoding="utf-8",
    )


def normalize_pyproject() -> None:
    path = ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'^name\s*=\s*"[^"]+"$', 'name = "rasai-readiness-auditor"', text, count=1, flags=re.MULTILINE)
    text = re.sub(
        r'(?ms)^\[project\.scripts\]\n.*?(?=^\[|\Z)',
        '[project.scripts]\nrasai = "rasai.entrypoint:main"\nrasai-console = "rasai.console_entrypoint:main"\n\n',
        text,
    )
    path.write_text(text, encoding="utf-8")


def rewrite_branding_document() -> None:
    path = ROOT / "docs" / "BRANDING.md"
    path.write_text(
        '''# Identidade do produto\n\n## Nome oficial\n\n**RASAi - Search & AI Readiness Auditor**\n\n## Índice público\n\n**SARI-001 - Search & AI Readiness Index**\n\n## Contratos técnicos\n\n- CLI: `rasai`\n- console interativo: `rasai-console`\n- pacote Python: `rasai`\n- distribuição Python: `rasai-readiness-auditor`\n- configuração do console: `rasai-console.ini`\n- configuração geral opcional: `rasai.toml`\n- diretório operacional local: `.rasai`\n- variáveis próprias do produto: prefixo `RASAI_`\n\nVariáveis de credenciais definidas pelos providers mantêm o nome oficial do provider, por exemplo `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` e `GEMINI_API_KEY`.\n\nIDs metodológicos como `BR-GEO-*`, `FR-GEO-*` e `SCORE-GEO-*` permanecem porque identificam contratos de metodologia, não o nome do produto. GEO pode aparecer como conceito técnico quando o texto realmente discute Generative Engine Optimization; não deve ser usado como marca, namespace ou sinônimo de RASAi.\n''',
        encoding="utf-8",
    )


def patch_report_normalizer() -> None:
    path = ROOT / "src" / "rasai" / "report_navigation.py"
    text = path.read_text(encoding="utf-8")
    needle = "        normalized = _move_footer_to_end_of_main(normalized)\n        html_path.write_text(normalized, encoding=\"utf-8\", newline=\"\\n\")"
    replacement = (
        "        normalized = _move_footer_to_end_of_main(normalized)\n"
        "        normalized = normalized.replace(\"—\", \"-\").replace(\"–\", \"-\")\n"
        "        html_path.write_text(normalized, encoding=\"utf-8\", newline=\"\\n\")"
    )
    if needle not in text:
        raise RuntimeError("report navigation normalization insertion point not found")
    path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")


def remove_obsolete_alias_sentences() -> None:
    for path in ROOT.rglob("*.md"):
        if not included(path):
            continue
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"^Aliases legados `rasai` e `rasai-console` permanecem por compatibilidade\.\n+", "", text, flags=re.MULTILINE)
        text = text.replace("menu legado permanece normal", "menu principal permanece normal")
        path.write_text(text, encoding="utf-8")


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


def validate_no_obsolete_namespace() -> None:
    violations: list[str] = []
    legacy_pattern = re.compile(r"SEARCHGEO|SearchGEO|searchgeo|Search/GEO|Search / GEO")
    old_product_geo = re.compile(r"\b(?:Readiness GEO|GEO Readiness)\b", re.IGNORECASE)
    for path in ROOT.rglob("*"):
        if not included(path):
            continue
        relative = str(path.relative_to(ROOT))
        if legacy_pattern.search(relative):
            violations.append(relative)
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"README", "LICENSE"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if legacy_pattern.search(text):
            violations.append(relative)
        if old_product_geo.search(text):
            violations.append(relative + ":old-product-GEO-label")
        if path.suffix.lower() in {".md", ".html"} and ("—" in text or "–" in text):
            violations.append(relative + ":long-dash")
    if (ROOT / "src" / "searchgeo").exists():
        violations.append("src/searchgeo")
    if violations:
        raise RuntimeError("obsolete namespace/public typography remains in: " + ", ".join(sorted(set(violations))))


def main() -> None:
    migrate_paths()
    migrate_text()
    rewrite_runtime_paths()
    rewrite_console_config_path()
    rewrite_tests()
    normalize_pyproject()
    rewrite_branding_document()
    patch_report_normalizer()
    remove_obsolete_alias_sentences()
    remove_one_shot_files()
    validate_no_obsolete_namespace()
    print("RASAi canonical namespace migration completed successfully")


if __name__ == "__main__":
    main()
