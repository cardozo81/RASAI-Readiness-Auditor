from __future__ import annotations

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    ".github/workflows/rasai-sari-migration.yml",
    ".github/workflows/rasai-sari-migration-v2.yml",
    ".github/workflows/rasai-sari-migration-v3.yml",
    "tools/rasai_sari_migrate.py",
}
TEXT_SUFFIXES = {".py", ".md", ".cmd", ".toml", ".yml", ".yaml", ".txt", ".html"}


def _tracked_files() -> list[str]:
    return subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()


def _public_surface_replacements() -> None:
    for name in _tracked_files():
        if name in EXCLUDED:
            continue
        path = ROOT / name
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != "README.md":
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        original = text

        text = text.replace("SearchGEO Readiness Auditor", "RASAI — Search & AI Readiness Auditor")
        text = text.replace("SearchGEO Readiness Index", "Search & AI Readiness Index")
        text = text.replace("SearchGEO Readiness", "Search & AI Readiness")
        text = text.replace("SearchGEO", "RASAI")
        text = text.replace("SGRI-001", "SARI-001")
        text = re.sub(r"\bSGRI\b", "SARI", text)
        text = text.replace("searchgeo.html", "readiness.html")
        text = text.replace("Compatibilidade GEO", "Readiness Search & AI")
        text = text.replace("compatibilidade GEO", "readiness Search & AI")

        if path.suffix.lower() in {".md", ".cmd"} or path.name == "README.md":
            text = text.replace("searchgeo-console", "rasai-console")
            text = re.sub(
                r"(?<![\w./-])searchgeo(?=\s+(?:audit|visibility|scoring|--version))",
                "rasai",
                text,
            )

        if path.suffix.lower() == ".py":
            text = text.replace('prog="searchgeo visibility"', 'prog="rasai visibility"')
            text = text.replace('prog="searchgeo scoring"', 'prog="rasai scoring"')
            text = text.replace('prog="searchgeo"', 'prog="rasai"')
            text = text.replace("prog='searchgeo visibility'", "prog='rasai visibility'")
            text = text.replace("prog='searchgeo scoring'", "prog='rasai scoring'")
            text = text.replace("prog='searchgeo'", "prog='rasai'")

        if text != original:
            path.write_bytes(text.encode("utf-8"))


def _pyproject() -> None:
    path = ROOT / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    if 'rasai = "searchgeo.entrypoint:main"' not in text:
        text = text.replace(
            "[project.scripts]\n",
            '[project.scripts]\nrasai = "searchgeo.entrypoint:main"\nrasai-console = "searchgeo.console_entrypoint:main"\n',
            1,
        )
    text = re.sub(
        r"^description = .*?$",
        'description = "RASAI — Search & AI readiness auditor. Legacy Python namespace retained for compatibility."',
        text,
        flags=re.MULTILINE,
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def _branding_module() -> None:
    (ROOT / "src/searchgeo/branding.py").write_text(
        '''"""Public RASAI/SARI identity and compatibility contract."""

PRODUCT_NAME = "RASAI"
PRODUCT_EXPANSION = "Readiness Assessment for Search & AI"
PRODUCT_DESCRIPTOR = "Search & AI Readiness Auditor"
PRODUCT_DISPLAY_NAME = f"{PRODUCT_NAME} — {PRODUCT_DESCRIPTOR}"
FRAMEWORK_NAME = "RASAI Framework"

PUBLIC_INDEX_NAME = "Search & AI Readiness Index"
PUBLIC_INDEX_VERSION = "SARI-001"
LEGACY_PUBLIC_INDEX_VERSION = "SGRI-001"

CANONICAL_READINESS_REPORT = "readiness.html"
LEGACY_READINESS_REPORT = "searchgeo.html"

PRIMARY_CLI = "rasai"
PRIMARY_CONSOLE_CLI = "rasai-console"
LEGACY_CLI = "searchgeo"
LEGACY_CONSOLE_CLI = "searchgeo-console"
''',
        encoding="utf-8",
        newline="\n",
    )


def _readiness_reporting() -> None:
    path = ROOT / "src/searchgeo/searchgeo_readiness_reporting.py"
    text = path.read_text(encoding="utf-8")

    if "from searchgeo.branding import (" not in text:
        text = text.replace(
            "from searchgeo import report_navigation\n",
            '''from searchgeo import report_navigation
from searchgeo.branding import (
    CANONICAL_READINESS_REPORT,
    LEGACY_PUBLIC_INDEX_VERSION,
    LEGACY_READINESS_REPORT,
    PUBLIC_INDEX_VERSION,
)
''',
            1,
        )

    text = text.replace(
        'SEARCHGEO_FILE = "readiness.html"\nPUBLIC_METHOD_VERSION = "SARI-001"\n',
        "SEARCHGEO_FILE = CANONICAL_READINESS_REPORT\n"
        "PUBLIC_METHOD_VERSION = PUBLIC_INDEX_VERSION\n"
        "LEGACY_SEARCHGEO_FILE = LEGACY_READINESS_REPORT\n"
        "LEGACY_PUBLIC_METHOD_VERSION = LEGACY_PUBLIC_INDEX_VERSION\n",
        1,
    )
    text = text.replace('(\"RASAI Readiness\", SEARCHGEO_FILE)', '(\"SARI Readiness\", SEARCHGEO_FILE)')

    mkdir_anchor = '    report_dir.mkdir(parents=True, exist_ok=True)\n    _register_navigation()\n'
    if "legacy_readiness_path = report_dir / LEGACY_SEARCHGEO_FILE" not in text:
        text = text.replace(
            mkdir_anchor,
            '    report_dir.mkdir(parents=True, exist_ok=True)\n'
            '    legacy_readiness_path = report_dir / LEGACY_SEARCHGEO_FILE\n'
            '    if legacy_readiness_path.is_file():\n'
            '        legacy_readiness_path.unlink()\n'
            '    _register_navigation()\n',
            1,
        )

    old_tail = '''    report_navigation.normalize_report_navigation(report_dir)
    _post_normalize_language(report_dir)
    return searchgeo_path
'''
    if "legacy_path = report_dir / LEGACY_SEARCHGEO_FILE" not in text:
        text = text.replace(
            old_tail,
            '''    report_navigation.normalize_report_navigation(report_dir)
    _post_normalize_language(report_dir)

    legacy_path = report_dir / LEGACY_SEARCHGEO_FILE
    legacy_path.write_text(
        _legacy_readiness_redirect(),
        encoding="utf-8",
        newline="\\n",
    )
    return searchgeo_path
''',
            1,
        )

    if "def _legacy_readiness_redirect()" not in text:
        helper = '''

def _legacy_readiness_redirect() -> str:
    """Keep old report bookmarks functional without duplicating analytics."""
    return f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'>
<meta http-equiv='refresh' content='0; url={SEARCHGEO_FILE}'>
<link rel='canonical' href='{SEARCHGEO_FILE}'>
<title>RASAI — relatório legado</title></head>
<body><p>Este endereço é legado. Abra <a href='{SEARCHGEO_FILE}'>{SEARCHGEO_FILE}</a>.</p></body></html>\\n"""
'''
        text = text.replace("\ndef _register_navigation() -> None:\n", helper + "\ndef _register_navigation() -> None:\n", 1)

    path.write_text(text, encoding="utf-8", newline="\n")


def _console_branding() -> None:
    path = ROOT / "src/searchgeo/console_runtime.py"
    text = path.read_text(encoding="utf-8")
    if "from searchgeo.branding import PRODUCT_DISPLAY_NAME" not in text:
        text = text.replace(
            "from searchgeo import __version__\n",
            "from searchgeo import __version__\nfrom searchgeo.branding import PRODUCT_DISPLAY_NAME\n",
            1,
        )
    text = text.replace(
        'print(f"RASAI — Search & AI Readiness Auditor | versão {__version__}")',
        'print(f"{PRODUCT_DISPLAY_NAME} | versão {__version__}")',
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def _docs() -> None:
    old_index = ROOT / "docs/SEARCHGEO_READINESS_INDEX.md"
    new_index = ROOT / "docs/SARI_READINESS_INDEX.md"
    new_index.write_text(old_index.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    old_index.write_text(
        '''# Documento legado — SearchGEO / SGRI-001

Este caminho é mantido exclusivamente para compatibilidade de links e histórico.

A identidade pública atual é **RASAI — Search & AI Readiness Auditor** e o índice público é **Search & AI Readiness Index `SARI-001`**.

Consulte [SARI_READINESS_INDEX.md](SARI_READINESS_INDEX.md).

`SGRI-001` permanece como alias público histórico. IDs persistidos como `SCORE-GEO-002`, `SCORE-GEO-003` e `BR-GEO-*`, além do namespace Python `searchgeo`, variáveis `SEARCHGEO_*` e artifacts históricos, não são reescritos por esta migração.
''',
        encoding="utf-8",
        newline="\n",
    )

    (ROOT / "docs/BRANDING_AND_COMPATIBILITY.md").write_text(
        '''# RASAI / SARI — identidade e compatibilidade

## Identidade pública

- **Produto:** RASAI
- **Expansão:** Readiness Assessment for Search & AI
- **Descriptor:** Search & AI Readiness Auditor
- **Framework:** RASAI Framework
- **Índice público:** Search & AI Readiness Index — `SARI-001`
- **Índice público legado:** `SGRI-001`

## Mudança pública

A apresentação, documentação, console, user-agent e relatórios usam RASAI/SARI. A página canônica do índice é `report/readiness.html`. `report/searchgeo.html` permanece como redirect de compatibilidade.

Os comandos preferenciais são `rasai`, `rasai-console`, `rasai audit`, `rasai visibility` e `rasai scoring`.

## Compatibilidade preservada

- `searchgeo` e `searchgeo-console` permanecem aliases funcionais;
- `src/searchgeo/` permanece como namespace Python;
- `SEARCHGEO_*` permanece como família de variáveis de ambiente;
- `searchgeo.toml`, `searchgeo-console.ini` e marcadores locais continuam válidos;
- `searchgeo-readiness-auditor` permanece como nome da distribuição Python nesta etapa;
- `BR-GEO-*`, `SCORE-GEO-002`, `SCORE-GEO-003` e outros IDs versionados não são renomeados;
- auditorias e artifacts históricos não são regravados.

## SARI versus scoring engine

`SARI-001` identifica publicamente o Search & AI Readiness Index. Ele não substitui a versão do motor persistido. A troca `SGRI-001` → `SARI-001` é nominal e não altera pesos, fatores, thresholds, fórmula ou calibração.

Lighthouse, Core Web Vitals, Acessibilidade, Synthetic Navigation Apdex, Synthetic User Experience Apdex e Observed AI Visibility continuam metodologias independentes e não são combinadas silenciosamente no SARI.
''',
        encoding="utf-8",
        newline="\n",
    )

    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    banner = (
        "\n> **Identidade atual:** **RASAI — Search & AI Readiness Auditor**. "
        "O índice público é **SARI-001 — Search & AI Readiness Index**. "
        "`searchgeo`, `searchgeo-console`, `SEARCHGEO_*`, o namespace Python `searchgeo` "
        "e IDs `SCORE-GEO-*`/`BR-GEO-*` permanecem compatíveis. "
        "Veja [docs/BRANDING_AND_COMPATIBILITY.md](docs/BRANDING_AND_COMPATIBILITY.md).\n"
    )
    if "docs/BRANDING_AND_COMPATIBILITY.md" not in text:
        pos = text.find("\n")
        text = text[: pos + 1] + banner + text[pos + 1 :]
    readme.write_text(text, encoding="utf-8", newline="\n")


def _tests() -> None:
    # Existing tests render HTML through html.escape; the visible '&' is encoded in source HTML.
    for rel in (
        "tests/test_searchgeo_readiness_reporting.py",
        "tests/test_indicator_provenance.py",
    ):
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        text = text.replace("Search & AI Readiness · Mobile", "Search &amp; AI Readiness · Mobile")
        text = text.replace(
            "Search & AI Readiness Index (SARI-001)",
            "Search &amp; AI Readiness Index (SARI-001)",
        )
        path.write_text(text, encoding="utf-8", newline="\n")

    (ROOT / "tests/test_rasai_sari_branding.py").write_text(
        '''from pathlib import Path
import tempfile
import tomllib

from searchgeo.branding import (
    CANONICAL_READINESS_REPORT,
    LEGACY_PUBLIC_INDEX_VERSION,
    LEGACY_READINESS_REPORT,
    PRODUCT_DISPLAY_NAME,
    PUBLIC_INDEX_VERSION,
)
from searchgeo.searchgeo_readiness_reporting import (
    PUBLIC_METHOD_VERSION,
    SEARCHGEO_FILE,
    _legacy_readiness_redirect,
)


def test_public_branding_contract() -> None:
    assert PRODUCT_DISPLAY_NAME == "RASAI — Search & AI Readiness Auditor"
    assert PUBLIC_INDEX_VERSION == "SARI-001"
    assert LEGACY_PUBLIC_INDEX_VERSION == "SGRI-001"
    assert CANONICAL_READINESS_REPORT == "readiness.html"
    assert LEGACY_READINESS_REPORT == "searchgeo.html"
    assert PUBLIC_METHOD_VERSION == "SARI-001"
    assert SEARCHGEO_FILE == "readiness.html"


def test_legacy_report_alias_redirects_to_canonical_readiness() -> None:
    html = _legacy_readiness_redirect()
    assert "url=readiness.html" in html
    assert "href='readiness.html'" in html


def test_primary_and_legacy_cli_entrypoints_coexist() -> None:
    scripts = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts["rasai"] == scripts["searchgeo"] == "searchgeo.entrypoint:main"
    assert scripts["rasai-console"] == scripts["searchgeo-console"] == "searchgeo.console_entrypoint:main"


def test_public_documentation_and_legacy_document_coexist() -> None:
    assert Path("docs/SARI_READINESS_INDEX.md").is_file()
    assert Path("docs/SEARCHGEO_READINESS_INDEX.md").is_file()
    assert Path("docs/BRANDING_AND_COMPATIBILITY.md").is_file()
''',
        encoding="utf-8",
        newline="\n",
    )


def _validate_static_contract() -> None:
    import tomllib

    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert {"rasai", "rasai-console", "searchgeo", "searchgeo-console"} <= set(scripts)
    assert scripts["rasai"] == scripts["searchgeo"]
    assert scripts["rasai-console"] == scripts["searchgeo-console"]

    reporting = (ROOT / "src/searchgeo/searchgeo_readiness_reporting.py").read_text(encoding="utf-8")
    for marker in (
        "CANONICAL_READINESS_REPORT",
        "LEGACY_READINESS_REPORT",
        "_legacy_readiness_redirect",
        "legacy_path = report_dir",
        "legacy_readiness_path = report_dir",
    ):
        assert marker in reporting, marker

    assert "SCORE-GEO-003" in (ROOT / "docs/SCORE_GEO_003.md").read_text(encoding="utf-8")
    assert "SEARCHGEO_" in "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in (ROOT / "src/searchgeo").glob("*.py")
    )


def main() -> None:
    _public_surface_replacements()
    _pyproject()
    _branding_module()
    _readiness_reporting()
    _console_branding()
    _docs()
    _tests()
    _validate_static_contract()


if __name__ == "__main__":
    main()
