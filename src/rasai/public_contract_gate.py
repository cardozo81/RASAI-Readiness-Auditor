"""Automated consistency gate for RASAi public contracts.

The gate validates the single current public/runtime scoring contract without rewriting files.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re

from rasai.indicator_provenance import enrich_indicator_provenance_html
from rasai.report_contract import (
    CANONICAL_FILENAMES,
    CANONICAL_NAV_ITEMS,
    OBSERVABILITY_CONTRACT_VERSION,
    REPORT_ALIASES,
    REPORT_CONTRACT_VERSION,
    REPORT_SURFACES,
    SARI_VERSION,
)
from rasai.score_geo_004 import SCORING_VERSION
from rasai.score_geo_004_cli import main as scoring_cli_main
from rasai.score_geo_004_reporting import REPORT_FILE

EXPECTED_SCORING_VERSION = "SCORE-GEO-004"
EXPECTED_SARI_VERSION = "SARI-001"
EXPECTED_REPORT_FILE = "scoring.html"
EXPECTED_CANONICAL_FILENAMES = (
    "index.html",
    "readiness.html",
    "scoring.html",
    "context.html",
    "crawling-discovery.html",
    "mobile.html",
    "desktop.html",
    "accessibility.html",
    "web-performance.html",
    "standards.html",
    "apdex.html",
    "apdex-experience.html",
    "search-intelligence.html",
    "ai-visibility.html",
    "observability.html",
    "ai-usage.html",
    "improvement-intelligence.html",
    "content-suggestions.html",
    "remediation.html",
    "quality.html",
    "references.html",
)

CURRENT_METHOD_DOCS = (
    "README.md",
    "docs/REPORT_GUIDE.md",
    "docs/CAPTURE_CONTEXT_MODEL.md",
    "docs/OUTPUTS_AND_ARTIFACTS.md",
    "docs/SCORING_GUIDE.md",
    "docs/SCORE_GEO_004.md",
    "docs/SARI_READINESS_INDEX.md",
    "docs/CLI_REFERENCE.md",
    "docs/CONSOLIDATED_REPORTING.md",
    "docs/COMPETITIVE_AI_INTELLIGENCE.md",
    "docs/COMPETITIVE_SEARCH_INTELLIGENCE.md",
    "docs/SERP_OBSERVATION.md",
    "docs/ENVIRONMENT_VARIABLES.md",
    "docs/IMPROVEMENT_INTELLIGENCE.md",
    "docs/INDICATOR_PROVENANCE.md",
    "docs/ACCESSIBILITY_PERFORMANCE_DOMAINS.md",
    "docs/MONITORING_OBSERVABILITY.md",
    "docs/SEARCH_INTELLIGENCE_REPORT.md",
    "docs/SEARCH_INTELLIGENCE_HISTORY.md",
    "docs/SEARCH_INTELLIGENCE_MONITORING.md",
    "docs/POSTGRESQL_MIGRATION_STRATEGY.md",
    "docs/SECURE_REDIRECT_RECOVERY.md",
    "docs/specification/00_SPEC_INDEX.md",
    "docs/specification/05_SCORING_MODEL.md",
    "docs/specification/07_FUNCTIONAL_REQUIREMENTS.md",
    "docs/specification/08_TECHNICAL_ARCHITECTURE.md",
    "docs/specification/12_AI_HANDOFF.md",
    "docs/specification/21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md",
    "docs/specification/22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md",
    "docs/specification/26_OBSERVED_GENERATIVE_VISIBILITY.md",
    "docs/specification/27_MONITORING_OBSERVABILITY.md",
    "docs/specification/28_AUDIT_QUALITY_VERIFICATION.md",
)

PUBLIC_GENERATOR_FILES = (
    "src/rasai/context_reporting.py",
    "src/rasai/improvement_intelligence.py",
    "src/rasai/m20_reporting.py",
    "src/rasai/m21_reporting.py",
    "src/rasai/m22_quality_domains.py",
    "src/rasai/m23_reporting.py",
    "src/rasai/m24_reporting.py",
    "src/rasai/m25_reporting.py",
    "src/rasai/m26_reporting.py",
    "src/rasai/rasai_readiness_reporting.py",
    "src/rasai/score_geo_004_reporting.py",
    "src/rasai/search_intelligence/reporting.py",
    "src/rasai/search_intelligence/history_reporting.py",
    "src/rasai/standards_metrics.py",
    "src/rasai/observability/reporting.py",
    "src/rasai/quality/reporting.py",
    "src/rasai/monitoring/reporting.py",
)

SURFACE_IMPLEMENTATION_HINTS = {
    "index.html": "src/rasai/reporting.py",
    "readiness.html": "src/rasai/rasai_readiness_reporting.py",
    "scoring.html": "src/rasai/score_geo_004_reporting.py",
    "context.html": "src/rasai/context_reporting.py",
    "mobile.html": "src/rasai/reporting.py",
    "desktop.html": "src/rasai/reporting.py",
    "remediation.html": "src/rasai/reporting.py",
    "content-suggestions.html": "src/rasai/m20_reporting.py",
    "crawling-discovery.html": "src/rasai/m24_reporting.py",
    "accessibility.html": "src/rasai/m22_quality_domains.py",
    "web-performance.html": "src/rasai/m21_reporting.py",
    "standards.html": "src/rasai/standards_metrics.py",
    "search-intelligence.html": "src/rasai/search_intelligence/reporting.py",
    "apdex.html": "src/rasai/m23_reporting.py",
    "apdex-experience.html": "src/rasai/m25_reporting.py",
    "ai-visibility.html": "src/rasai/m26_reporting.py",
    "observability.html": "src/rasai/observability/reporting.py",
    "quality.html": "src/rasai/quality/reporting.py",
    "ai-usage.html": "src/rasai/reporting.py",
    "improvement-intelligence.html": "src/rasai/improvement_intelligence.py",
    "references.html": "src/rasai/reporting.py",
}

_OLD_VERSION_RE = re.compile(r"SCORE-GEO-(?!004)\d{3}", re.I)
_MILESTONE_PUBLIC_RE = re.compile(r"(?i)(?<![A-Za-z0-9])m\d{1,3}")
_VERSIONED_CANONICAL_RE = re.compile(r"report/score-geo-\d+\.html")
_STALE_EQUAL_WEIGHT_RE = re.compile(r"m[eé]dia\s+de\s+igual\s+peso", re.I)

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

_SCORING_SCAN_SUFFIXES = frozenset({
    ".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".json", ".ini", ".cmd", ".ps1"
})


def _root(root: str | Path | None) -> Path:
    return Path(root).resolve() if root is not None else Path(__file__).resolve().parents[2]


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _check_runtime(errors: list[str]) -> None:
    if SCORING_VERSION != EXPECTED_SCORING_VERSION:
        errors.append(f"runtime SCORING_VERSION={SCORING_VERSION!r}; esperado {EXPECTED_SCORING_VERSION}")
    if SARI_VERSION != EXPECTED_SARI_VERSION:
        errors.append(f"SARI_VERSION={SARI_VERSION!r}; esperado {EXPECTED_SARI_VERSION}")
    if REPORT_FILE != EXPECTED_REPORT_FILE:
        errors.append(f"REPORT_FILE={REPORT_FILE!r}; esperado {EXPECTED_REPORT_FILE}")
    if tuple(CANONICAL_FILENAMES) != EXPECTED_CANONICAL_FILENAMES:
        errors.append("lista canônica de report surfaces diverge do contrato público")
    labels_by_filename = {filename: label for label, filename in CANONICAL_NAV_ITEMS}
    if labels_by_filename.get("context.html") != "Contexto de captura":
        errors.append("context.html não usa o rótulo canônico Contexto de captura")
    if labels_by_filename.get("crawling-discovery.html") != "Domínio e descoberta":
        errors.append("crawling-discovery.html não usa o rótulo canônico Domínio e descoberta")
    if labels_by_filename.get("standards.html") != "Métricas e padrões":
        errors.append("standards.html não usa o rótulo canônico Métricas e padrões")
    if labels_by_filename.get("improvement-intelligence.html") != "Análise profunda e melhorias":
        errors.append("improvement-intelligence.html não usa o rótulo canônico Análise profunda e melhorias")
    if REPORT_ALIASES:
        errors.append("contrato atual não deve expor aliases de report")
    if not REPORT_CONTRACT_VERSION or not OBSERVABILITY_CONTRACT_VERSION:
        errors.append("versões de contrato de report/observability não estão definidas")

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
        if EXPECTED_SCORING_VERSION not in text:
            errors.append(f"documento corrente não menciona {EXPECTED_SCORING_VERSION}: {relative}")
        if _OLD_VERSION_RE.search(text):
            errors.append(f"documento corrente expõe scoring inválido: {relative}")
        if _VERSIONED_CANONICAL_RE.search(text):
            errors.append(f"documento corrente expõe filename versionado de scoring: {relative}")
        if _STALE_EQUAL_WEIGHT_RE.search(text):
            errors.append(f"documento corrente descreve Overall com peso igual inválido: {relative}")

    readme = _read(root, "README.md")
    nav_apdex = re.findall(r"(?m)^apdex\.html\s+", readme)
    nav_ux_apdex = re.findall(r"(?m)^apdex-experience\.html\s+", readme)
    if len(nav_apdex) != 1:
        errors.append("README deve listar apdex.html uma única vez no inventário canônico")
    if len(nav_ux_apdex) != 1:
        errors.append("README deve listar apdex-experience.html uma única vez no inventário canônico")
    if "report-manifest.json" not in readme:
        errors.append("README não documenta report/report-manifest.json")

    docs = [root / "README.md", *(root / "docs").rglob("*.md")]
    for path in docs:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if _OLD_VERSION_RE.search(text):
            errors.append(f"scoring inválido exposto na documentação: {path.relative_to(root)}")
        if _MILESTONE_PUBLIC_RE.search(text):
            errors.append(f"identificador interno de entrega exposto na documentação: {path.relative_to(root)}")
        if EXPECTED_SCORING_VERSION in text and _STALE_EQUAL_WEIGHT_RE.search(text):
            errors.append(f"fórmula de peso igual inválida exposta na documentação: {path.relative_to(root)}")


def _check_cli_docs(root: Path, errors: list[str]) -> None:
    cli_doc = _read(root, "docs/CLI_REFERENCE.md")
    required = (
        "rasai audit",
        "rasai search",
        "rasai search-history",
        "rasai search-monitor",
        "rasai scoring inspect",
        "rasai visibility import",
        "rasai visibility report",
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
    for obsolete in ("rasai scoring dataset", "rasai scoring calibrate"):
        if obsolete in cli_doc:
            errors.append(f"CLI de scoring não suportada exposta na documentação: {obsolete}")


def _check_surfaces(root: Path, errors: list[str]) -> None:
    ids = [surface.id for surface in REPORT_SURFACES]
    filenames = [surface.filename for surface in REPORT_SURFACES]
    if len(ids) != len(set(ids)):
        errors.append("ReportSurface.id duplicado")
    if len(filenames) != len(set(filenames)):
        errors.append("ReportSurface.filename duplicado")
    if tuple((surface.label, surface.filename) for surface in REPORT_SURFACES) != CANONICAL_NAV_ITEMS:
        errors.append("navegação não deriva integralmente de REPORT_SURFACES")
    for filename, implementation in SURFACE_IMPLEMENTATION_HINTS.items():
        if filename not in filenames:
            errors.append(f"surface ausente do registry: {filename}")
        if not (root / implementation).is_file():
            errors.append(f"implementação esperada não existe para {filename}: {implementation}")
    if any(re.fullmatch(r"score-geo-\d+\.html", filename) for filename in filenames):
        errors.append("filename canônico versionado presente no registry")


def _check_generators(root: Path, errors: list[str]) -> None:
    for relative in PUBLIC_GENERATOR_FILES:
        text = _read(root, relative)
        if not text:
            errors.append(f"gerador público ausente: {relative}")
            continue
        if _OLD_VERSION_RE.search(text):
            errors.append(f"gerador público expõe scoring inválido: {relative}")


def _check_public_html_normalization(errors: list[str]) -> None:
    fixture = "<html><body>" + " | ".join(_PUBLIC_HTML_MILESTONE_FIXTURES) + "</body></html>"
    normalized = enrich_indicator_provenance_html(fixture, page_name="index.html")
    if _MILESTONE_PUBLIC_RE.search(normalized):
        errors.append("normalizador público mantém identificadores internos de entrega no HTML")

    # Never solve the public milestone problem with a generic replacement over audited
    # content: a product/model can legitimately contain the same token shape.
    evidence = "<html><body><p>Produto M25 industrial observado na página.</p></body></html>"
    preserved = enrich_indicator_provenance_html(evidence, page_name="other.html")
    if "Produto M25 industrial observado na página." not in preserved:
        errors.append("normalizador público altera conteúdo auditado legítimo")


def _check_single_scoring_contract(root: Path, errors: list[str]) -> None:
    """Reject concrete scoring versions other than the single current contract."""
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

    stale_reporting_claims = (
        "No Search Intelligence-specific HTML report is introduced yet",
        "no Search Intelligence-specific HTML report yet",
        "não há Search Intelligence HTML específico",
        "no dedicated historical HTML report is generated yet",
    )
    for relative in (
        "docs/SERP_OBSERVATION.md",
        "docs/COMPETITIVE_SEARCH_INTELLIGENCE.md",
        "docs/COMPETITIVE_AI_INTELLIGENCE.md",
        "docs/SEARCH_INTELLIGENCE_HISTORY.md",
    ):
        text = _read(root, relative)
        for claim in stale_reporting_claims:
            if claim in text:
                errors.append(f"documentação anuncia limitação já implementada em {relative}: {claim}")


def validate_public_contract(root: str | Path | None = None) -> tuple[str, ...]:
    errors: list[str] = []
    base = _root(root)
    _check_runtime(errors)
    _check_docs(base, errors)
    _check_cli_docs(base, errors)
    _check_surfaces(base, errors)
    _check_generators(base, errors)
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
    print(f"runtime={SCORING_VERSION}; sari={SARI_VERSION}; report={REPORT_FILE}; surfaces={len(REPORT_SURFACES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
