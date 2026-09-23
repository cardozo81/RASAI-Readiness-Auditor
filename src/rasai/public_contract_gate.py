"""Automated consistency gate for the current public runtime contract."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re

from rasai.catalog_report_contract import (
    CATALOG_REPORT_CONTRACT_VERSION,
    CATALOG_REPORT_DIR,
    CATALOG_REPORT_FILENAMES,
    CATALOG_REPORT_NAV_ITEMS,
    CATALOG_REPORT_PAGES,
)
from rasai.indicator_provenance import enrich_indicator_provenance_html
from rasai.score_geo_004 import SCORING_VERSION
from rasai.score_geo_004_cli import main as scoring_cli_main


EXPECTED_SCORING_VERSION = "SCORE-GEO-004"
EXPECTED_CATALOG_REPORT_CONTRACT = "CATALOG-REPORT-002"
EXPECTED_CATALOG_REPORT_DIR = "report-catalog"

CURRENT_METHOD_DOCS = (
    "README.md",
    "docs/OUTPUTS_AND_ARTIFACTS.md",
    "docs/REPORT_GUIDE.md",
    "docs/SCORING_GUIDE.md",
    "docs/SCORE_GEO_004.md",
    "docs/SARI_READINESS_INDEX.md",
    "docs/CLI_REFERENCE.md",
    "docs/specification/00_SPEC_INDEX.md",
    "docs/specification/05_SCORING_MODEL.md",
    "docs/specification/07_FUNCTIONAL_REQUIREMENTS.md",
    "docs/specification/08_TECHNICAL_ARCHITECTURE.md",
)

_OLD_VERSION_RE = re.compile(r"SCORE-GEO-(?!004)\d{3}", re.I)
_MILESTONE_PUBLIC_RE = re.compile(r"(?i)(?<![A-Za-z0-9])m\d{1,3}")
_STALE_EQUAL_WEIGHT_RE = re.compile(r"m[eé]dia\s+de\s+igual\s+peso", re.I)
_SCORING_SCAN_SUFFIXES = frozenset({
    ".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".json", ".ini", ".cmd", ".ps1"
})

_PUBLIC_HTML_MILESTONE_FIXTURES = (
    "M18/M20",
    "M21/M22",
    "M21 + M22 · domínio Web Performance",
    "M23 · domínio Web Performance",
    "Web Performance · M23",
    "M23 · metodologia",
    "Estado M23",
    "M24-CD-001",
    "Rastreamento e descoberta M24",
)


def _root(root: str | Path | None) -> Path:
    return Path(root).resolve() if root is not None else Path(__file__).resolve().parents[2]


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _check_runtime(errors: list[str]) -> None:
    if SCORING_VERSION != EXPECTED_SCORING_VERSION:
        errors.append(
            f"runtime SCORING_VERSION={SCORING_VERSION!r}; esperado {EXPECTED_SCORING_VERSION}"
        )
    if CATALOG_REPORT_CONTRACT_VERSION != EXPECTED_CATALOG_REPORT_CONTRACT:
        errors.append(
            "contrato de report-catalog divergente: "
            f"{CATALOG_REPORT_CONTRACT_VERSION!r}"
        )
    if CATALOG_REPORT_DIR != EXPECTED_CATALOG_REPORT_DIR:
        errors.append(
            f"diretório de report-catalog divergente: {CATALOG_REPORT_DIR!r}"
        )

    ids = [page.id for page in CATALOG_REPORT_PAGES]
    filenames = [page.filename for page in CATALOG_REPORT_PAGES]
    if len(ids) != len(set(ids)):
        errors.append("CatalogReportPage.id duplicado")
    if len(filenames) != len(set(filenames)):
        errors.append("CatalogReportPage.filename duplicado")
    if tuple(filenames) != tuple(CATALOG_REPORT_FILENAMES):
        errors.append("filenames do report-catalog divergem do contrato")
    if tuple((page.label, page.filename) for page in CATALOG_REPORT_PAGES) != tuple(
        CATALOG_REPORT_NAV_ITEMS
    ):
        errors.append("navegação do report-catalog diverge do contrato")

    required = {
        "index.html",
        "sari.html",
        "capture-context.html",
        "execution-evidence.html",
        "ai-integrations.html",
        "methodology.html",
        "metrics.html",
    }
    missing = sorted(required.difference(filenames))
    if missing:
        errors.append("superfícies obrigatórias ausentes do report-catalog: " + ", ".join(missing))

    output = StringIO()
    try:
        with redirect_stdout(output):
            code = scoring_cli_main(["inspect"])
    except SystemExit as exc:
        errors.append(f"rasai scoring inspect abortou: {exc}")
        return
    text = output.getvalue()
    if code != 0 or EXPECTED_SCORING_VERSION not in text:
        errors.append("rasai scoring inspect não expõe SCORE-GEO-004 corretamente")


def _check_docs(root: Path, errors: list[str]) -> None:
    for relative in CURRENT_METHOD_DOCS:
        text = _read(root, relative)
        if not text:
            errors.append(f"documento corrente ausente: {relative}")
            continue
        if _OLD_VERSION_RE.search(text):
            errors.append(f"documento corrente expõe scoring inválido: {relative}")
        if EXPECTED_SCORING_VERSION in text and _STALE_EQUAL_WEIGHT_RE.search(text):
            errors.append(f"documento corrente descreve Overall com peso igual inválido: {relative}")

    readme = _read(root, "README.md")
    if "report-catalog/index.html" not in readme:
        errors.append("README não documenta report-catalog/index.html")
    if "report-catalog/" not in readme:
        errors.append("README não documenta a raiz report-catalog/")


def _check_cli_docs(root: Path, errors: list[str]) -> None:
    cli_doc = _read(root, "docs/CLI_REFERENCE.md")
    required = (
        "rasai audit",
        "rasai search",
        "rasai search-history",
        "rasai search-monitor",
        "rasai scoring inspect",
        "rasai visibility import",
        "rasai monitor compare",
        "rasai monitor impact",
        "rasai monitor gate",
        "rasai observe",
        "rasai quality report",
        "rasai quality verify",
        "rasai quality timeline",
        "rasai platform",
    )
    for command in required:
        if command not in cli_doc:
            errors.append(f"CLI pública sem documentação: {command}")


def _check_public_html_normalization(errors: list[str]) -> None:
    fixture = "<html><body>" + " | ".join(_PUBLIC_HTML_MILESTONE_FIXTURES) + "</body></html>"
    normalized = enrich_indicator_provenance_html(fixture, page_name="index.html")
    if _MILESTONE_PUBLIC_RE.search(normalized):
        errors.append("normalizador público mantém identificadores internos de entrega no HTML")

    evidence = "<html><body><p>Produto M25 industrial observado na página.</p></body></html>"
    preserved = enrich_indicator_provenance_html(evidence, page_name="other.html")
    if "Produto M25 industrial observado na página." not in preserved:
        errors.append("normalizador público altera conteúdo auditado legítimo")


def _check_single_scoring_contract(root: Path, errors: list[str]) -> None:
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _SCORING_SCAN_SUFFIXES:
            continue
        if any(part in {".git", ".venv", "venv", "__pycache__"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        match = _OLD_VERSION_RE.search(text)
        if match:
            errors.append(
                f"contrato de scoring inválido {match.group(0)!r}: {path.relative_to(root)}; "
                f"somente {EXPECTED_SCORING_VERSION} é válido"
            )


def validate_public_contract(root: str | Path | None = None) -> tuple[str, ...]:
    errors: list[str] = []
    base = _root(root)
    _check_runtime(errors)
    _check_docs(base, errors)
    _check_cli_docs(base, errors)
    _check_public_html_normalization(errors)
    _check_single_scoring_contract(base, errors)
    return tuple(dict.fromkeys(errors))


def main() -> int:
    errors = validate_public_contract()
    if errors:
        print("PUBLIC CONTRACT CONSISTENCY GATE: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PUBLIC CONTRACT CONSISTENCY GATE: PASS")
    print(
        f"runtime={SCORING_VERSION}; "
        f"report={CATALOG_REPORT_DIR}; "
        f"surfaces={len(CATALOG_REPORT_PAGES)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
