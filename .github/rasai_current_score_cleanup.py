from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OLD_SCORE_RE = re.compile(r"SCORE-GEO-00[123]", re.I)
CURRENT = "SCORE-GEO-004"


def read(path: str | Path) -> str:
    p = ROOT / path if not isinstance(path, Path) or not path.is_absolute() else path
    return p.read_text(encoding="utf-8")


def write(path: str | Path, text: str) -> None:
    p = ROOT / path if not isinstance(path, Path) or not path.is_absolute() else path
    p.write_text(text, encoding="utf-8", newline="\n")


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise RuntimeError(f"{label}: start marker not found")
    b = text.find(end, a)
    if b < 0:
        raise RuntimeError(f"{label}: end marker not found")
    return text[:a] + replacement + text[b:]


def clean_markdown(path: Path) -> None:
    """Remove unpublished scoring-history blocks while preserving current documentation.

    The product has not shipped a previous scoring method, so documentation must not
    present development iterations as a supported public history. Blocks containing
    obsolete SCORE-GEO identifiers are removed rather than blindly renumbered.
    """
    text = path.read_text(encoding="utf-8")
    if not OLD_SCORE_RE.search(text):
        return

    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            block = [line]
            i += 1
            while i < len(lines):
                block.append(lines[i])
                if lines[i].lstrip().startswith("```"):
                    i += 1
                    break
                i += 1
            if not OLD_SCORE_RE.search("\n".join(block)):
                out.extend(block)
            continue

        if not line.strip():
            out.append(line)
            i += 1
            continue

        block: list[str] = []
        while i < len(lines) and lines[i].strip() and not lines[i].lstrip().startswith("```"):
            block.append(lines[i])
            i += 1
        joined = "\n".join(block)
        if not OLD_SCORE_RE.search(joined):
            out.extend(block)
            continue

        # Tables and lists can safely retain unaffected rows/items.
        if all((not value.strip()) or value.lstrip().startswith("|") for value in block):
            out.extend(value for value in block if not OLD_SCORE_RE.search(value))
            continue
        if all(
            (not value.strip())
            or value.lstrip().startswith(("- ", "* ", "+ "))
            for value in block
        ):
            out.extend(value for value in block if not OLD_SCORE_RE.search(value))
            continue
        # Prose/headings mentioning unpublished methods are intentionally dropped.

    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).rstrip() + "\n"
    path.write_text(cleaned, encoding="utf-8", newline="\n")


def clean_readme() -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    replacements = {
        "- relatórios consolidados/históricos read-only;": "- relatórios consolidados read-only;",
        "Ele não duplica score, findings ou evidence. É produzido a partir de `audit.db` em modo read-only e facilita debugging, completude, API/SaaS e abertura de auditorias históricas.": "Ele não duplica score, findings ou evidence. É produzido a partir de `audit.db` em modo read-only e facilita debugging, completude e evolução para API/SaaS.",
        "A comparação longitudinal deve respeitar essas fronteiras. Uma série não pode misturar 002/003/004 como se fossem a mesma metodologia.": "A comparação longitudinal deve manter `scoring_version` compatível entre baseline e current. Nesta fase de desenvolvimento, a única metodologia de scoring suportada é `SCORE-GEO-004`.",
        "- relatórios históricos preservam `scoring_version` e diferenças metodológicas.": "- relatórios preservam `scoring_version`; nesta fase de desenvolvimento, a única metodologia suportada é `SCORE-GEO-004`.",
        "A documentação está organizada em [`docs/README.md`](docs/README.md). O projeto está em desenvolvimento e validação; referências a métodos anteriores significam propostas/baselines de desenvolvimento preservados para rastreabilidade, não releases públicas anteriores.": "A documentação está organizada em [`docs/README.md`](docs/README.md). O projeto está em desenvolvimento e validação; `SCORE-GEO-004` é a única metodologia de scoring vigente e reconhecida nesta fase.",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8", newline="\n")
    clean_markdown(path)


def patch_report_registry() -> None:
    path = ROOT / "src/rasai/report_registry.py"
    text = path.read_text(encoding="utf-8")
    if "import re\n" not in text:
        text = text.replace("from pathlib import Path\nimport sqlite3\n", "from pathlib import Path\nimport re\nimport sqlite3\n", 1)
    old_start = "def _normalize_known_legacy_wording(html: str, *, page_name: str) -> str:\n"
    end = "def _contract_section(page_name: str) -> str:\n"
    new = '''def _normalize_known_legacy_wording(html: str, *, page_name: str) -> str:\n    """Enforce the single pre-publication scoring contract on every HTML surface."""\n    del page_name\n    from rasai.score_geo_004 import SCORING_VERSION\n\n    # Development iterations were never public releases. A final report must never\n    # expose them as a supported history or competing methodological truth.\n    updated = re.sub(r"SCORE-GEO-(?!004)\\d{3}", SCORING_VERSION, html, flags=re.I)\n    replacements = (\n        ("contratos históricos", "contrato vigente"),\n        ("contrato histórico", "contrato vigente"),\n        ("histórico metodológico", "contrato metodológico vigente"),\n        ("metodologia histórica", "metodologia vigente"),\n        ("referências de desenvolvimento anteriores", "contrato vigente"),\n        ("referência de desenvolvimento anterior", "contrato vigente"),\n        ("auditorias históricas", "auditorias da versão vigente"),\n        ("comparabilidade histórica", "comparabilidade entre auditorias da versão vigente"),\n    )\n    for old, replacement in replacements:\n        updated = updated.replace(old, replacement)\n    updated = re.sub(\n        rf"(?:{re.escape(SCORING_VERSION)}[;, ]+)+{re.escape(SCORING_VERSION)}",\n        SCORING_VERSION,\n        updated,\n    )\n    return updated\n\n\n'''
    text = replace_between(text, old_start, end, new, "report registry scoring normalizer")
    text = text.replace(
        "The gate validates public/runtime invariants without rewriting files. References\nto earlier development proposals remain allowed when clearly qualified; current\nsurfaces may not present an earlier proposal as the active runtime.",
        "The gate validates the single pre-publication scoring/runtime contract without rewriting files.",
    )
    text = text.replace("comparabilidade histórica", "comparabilidade entre auditorias da versão vigente")
    text = text.replace("auditorias históricas", "auditorias da versão vigente")
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_m26() -> None:
    path = ROOT / "src/rasai/m26_reporting.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "Esta página é deliberadamente separada de SARI-001 e do {SCORING_VERSION} vigente. SCORE-GEO-003 e SCORE-GEO-002 permanecem históricos. Ausência de dados observados não reduz readiness.",
        "Esta página é deliberadamente separada de SARI-001 e do {SCORING_VERSION} vigente. Ausência de dados observados não reduz readiness.",
    )
    text = text.replace(
        "Estes dados <strong>não compõem SARI-001/{SCORING_VERSION}</strong>; SCORE-GEO-003 e SCORE-GEO-002 são contratos históricos e também não recebem estes dados retroativamente. Os valores não são convertidos em um “GEO Score”.",
        "Estes dados <strong>não compõem SARI-001/{SCORING_VERSION}</strong>. Os valores não são convertidos em um “GEO Score”.",
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_m15() -> None:
    path = ROOT / "src/rasai/m15_reporting.py"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    text = OLD_SCORE_RE.sub(CURRENT, text)
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_scoring_report() -> None:
    path = ROOT / "src/rasai/score_geo_004_reporting.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace('LEGACY_REPORT_FILE = "score-geo-004.html"\n', "")

    start = "def register_navigation() -> None:\n"
    end = "def write_score_geo_004_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:\n"
    replacement = '''def register_navigation() -> None:\n    # Pre-publication contract: there is one version-neutral scoring surface only.\n    items = [\n        item\n        for item in report_navigation.NAV_ITEMS\n        if item[1] == REPORT_FILE or not item[1].startswith("score-geo-")\n    ]\n    items = [item for item in items if item[1] != REPORT_FILE]\n    pos = next((i + 1 for i, item in enumerate(items) if item[1] == "readiness.html"), 2)\n    items.insert(pos, ("Metodologia de scoring", REPORT_FILE))\n    report_navigation.NAV_ITEMS = tuple(items)\n\n\n'''
    text = replace_between(text, start, end, replacement, "scoring report navigation")

    text = text.replace(
        '    """Render the stable scoring surface without rewriting historical methodology."""',
        '    """Render the single scoring surface supported by this pre-publication build."""',
    )
    old = '''    versions = _scoring_versions(audit_id, workspace)\n    effective_version = versions[0] if len(versions) == 1 else (SCORING_VERSION if not versions else "MULTIPLE")\n    scores = _scores(audit_id, workspace, effective_version if effective_version != "MULTIPLE" else None)\n    score_rows = "".join(_score_row(row) for row in scores) or "<tr><td colspan='7'>Overall não persistido para esta versão.</td></tr>"\n    status_label = "VIGENTE" if effective_version == SCORING_VERSION else "HISTÓRICA"\n    if effective_version == "MULTIPLE":\n        status_label = "INCONSISTENTE"\n'''
    new = '''    versions = _scoring_versions(audit_id, workspace)\n    effective_version = SCORING_VERSION\n    scores = _scores(audit_id, workspace, SCORING_VERSION)\n    score_rows = "".join(_score_row(row) for row in scores) or "<tr><td colspan='7'>Overall vigente não persistido para esta auditoria.</td></tr>"\n    status_label = "VIGENTE"\n'''
    if old not in text:
        raise RuntimeError("scoring report effective version block not found")
    text = text.replace(old, new, 1)

    text = text.replace(
        "    # Pre-publication development contract: keep only the canonical version-neutral surface.\n    (report_dir / LEGACY_REPORT_FILE).unlink(missing_ok=True)\n",
        "    # Pre-publication development contract: remove any obsolete version-named surface.\n    for obsolete in report_dir.glob('score-geo-*.html'):\n        obsolete.unlink(missing_ok=True)\n",
    )

    # The method section can only render the current contract in this build.
    marker = "    if version == \"MULTIPLE\":\n"
    a = text.find(marker, text.find("def _method_section"))
    if a < 0:
        raise RuntimeError("historical method branch not found")
    b = text.find("\n\ndef _dimension_list", a)
    if b < 0:
        raise RuntimeError("dimension list marker not found")
    text = text[:a] + text[b:]

    dim_start = "def _dimension_list(version: str) -> str:\n"
    intro_start = "def _version_intro(version: str) -> str:\n"
    new_dim = '''def _dimension_list(version: str) -> str:\n    del version\n    items = "".join(f"<li><code>{escape(name)}</code></li>" for name in FEATURE_ORDER)\n    return f"<ul>{items}</ul><p class='intro'>No Overall 004, cada dimensão aplicável consolidável recebe peso igual; pesos internos de regras são os persistidos nas contribuições da respectiva dimensão.</p>"\n\n\n'''
    text = replace_between(text, dim_start, intro_start, new_dim, "dimension list")

    integrity_start = "def _version_integrity_notice(versions: list[str]) -> str:\n"
    score_row_start = "def _score_row(row: sqlite3.Row) -> str:\n"
    current_helpers = '''def _version_intro(version: str) -> str:\n    del version\n    return "Método operacional vigente do SARI-001. O Overall é determinístico, reproduzível e baseado nas evidências persistidas da auditoria; não depende de model artifact externo."\n\n\ndef _version_integrity_notice(versions: list[str]) -> str:\n    unsupported = [version for version in versions if version != SCORING_VERSION]\n    if not unsupported:\n        return ""\n    return (\n        "<section class='notice bad'><strong>Integridade metodológica:</strong> esta auditoria contém "\n        "uma scoring_version que não pertence ao contrato suportado por esta build pré-publicação. "\n        f"Somente <code>{SCORING_VERSION}</code> é reconhecido e nenhuma versão descontinuada é projetada ou convertida.</section>"\n    )\n\n\n'''
    text = replace_between(text, intro_start, score_row_start, current_helpers, "current-only scoring helpers")

    if OLD_SCORE_RE.search(text):
        raise RuntimeError("obsolete SCORE-GEO literal remains in score_geo_004_reporting.py")
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_public_gate() -> None:
    path = ROOT / "src/rasai/public_contract_gate.py"
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r'The gate validates public/runtime invariants without rewriting files\. References\n.*?active runtime\.\n',
        'The gate validates the single pre-publication public/runtime scoring contract without rewriting files.\n',
        text,
        flags=re.S,
    )
    definitions_start = '_OLD_VERSION_RE = re.compile(r"SCORE-GEO-00[123]", re.I)\n'
    root_start = 'def _root(root: str | Path | None) -> Path:\n'
    definitions = '''_OLD_VERSION_RE = re.compile(r"SCORE-GEO-(?!004)\\d{3}", re.I)\n_MILESTONE_PUBLIC_RE = re.compile(r"(?<![A-Za-z0-9_])M\\d{1,3}(?![A-Za-z0-9_])")\n_MILESTONE_EVENT_RE = re.compile(r"\\bM\\d{1,3}_[A-Z][A-Z0-9_]*\\b")\n_VERSIONED_CANONICAL_RE = re.compile(r"report/score-geo-\\d+\\.html")\n\n\n'''
    text = replace_between(text, definitions_start, root_start, definitions, "public gate regex definitions")

    stale_start = "def _stale_current_lines(text: str) -> list[str]:\n"
    runtime_start = "def _check_runtime(errors: list[str]) -> None:\n"
    if stale_start in text:
        text = replace_between(text, stale_start, runtime_start, "", "remove stale-line historical allowance")

    docs_start = "def _check_docs(root: Path, errors: list[str]) -> None:\n"
    cli_start = "def _check_cli_docs(root: Path, errors: list[str]) -> None:\n"
    docs_fn = '''def _check_docs(root: Path, errors: list[str]) -> None:\n    for relative in CURRENT_METHOD_DOCS:\n        text = _read(root, relative)\n        if not text:\n            errors.append(f"documento corrente ausente: {relative}")\n            continue\n        if EXPECTED_SCORING_VERSION not in text:\n            errors.append(f"documento corrente não menciona {EXPECTED_SCORING_VERSION}: {relative}")\n        if _OLD_VERSION_RE.search(text):\n            errors.append(f"documento corrente expõe scoring descontinuado: {relative}")\n        if _VERSIONED_CANONICAL_RE.search(text):\n            errors.append(f"documento corrente expõe filename versionado de scoring: {relative}")\n\n    readme = _read(root, "README.md")\n    nav_apdex = re.findall(r"(?m)^apdex\\.html\\s+", readme)\n    nav_ux_apdex = re.findall(r"(?m)^apdex-experience\\.html\\s+", readme)\n    if len(nav_apdex) != 1:\n        errors.append("README deve listar apdex.html uma única vez no inventário canônico")\n    if len(nav_ux_apdex) != 1:\n        errors.append("README deve listar apdex-experience.html uma única vez no inventário canônico")\n    if "report-manifest.json" not in readme:\n        errors.append("README não documenta report/report-manifest.json")\n\n    docs = [root / "README.md", *(root / "docs").rglob("*.md")]\n    for path in docs:\n        if not path.is_file():\n            continue\n        text = path.read_text(encoding="utf-8")\n        if _OLD_VERSION_RE.search(text):\n            errors.append(f"scoring descontinuado exposto na documentação: {path.relative_to(root)}")\n        if _MILESTONE_PUBLIC_RE.search(text) or _MILESTONE_EVENT_RE.search(text):\n            errors.append(f"marco interno M* exposto na documentação: {path.relative_to(root)}")\n\n\n'''
    text = replace_between(text, docs_start, cli_start, docs_fn, "public gate docs")

    generators_start = "def _check_generators(root: Path, errors: list[str]) -> None:\n"
    validate_start = "def validate_public_contract(root: str | Path | None = None) -> tuple[str, ...]:\n"
    generators_fn = '''def _check_generators(root: Path, errors: list[str]) -> None:\n    for relative in PUBLIC_GENERATOR_FILES:\n        text = _read(root, relative)\n        if not text:\n            errors.append(f"gerador público ausente: {relative}")\n            continue\n        if _OLD_VERSION_RE.search(text):\n            errors.append(f"gerador público expõe scoring descontinuado: {relative}")\n\n\n'''
    text = replace_between(text, generators_start, validate_start, generators_fn, "public gate generators")
    path.write_text(text, encoding="utf-8", newline="\n")


def patch_tests() -> None:
    # Tests may retain obsolete identifiers only when asserting that they are rejected;
    # fixtures that model the active runtime must use the sole supported version.
    fixture_files = (
        "tests/test_consolidation_reporting_ux.py",
        "tests/test_m26_observed_generative_visibility.py",
    )
    for relative in fixture_files:
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        text = OLD_SCORE_RE.sub(CURRENT, text)
        # Avoid contradictory assertions created by fixture normalization.
        text = re.sub(r'^\s*self\.assertNotIn\("SCORE-GEO-004", html\)\s*\n', '', text, flags=re.M)
        path.write_text(text, encoding="utf-8", newline="\n")


def remove_unpublished_method_docs() -> None:
    for name in ("SCORE_GEO_001.md", "SCORE_GEO_002.md", "SCORE_GEO_003.md"):
        (ROOT / "docs" / name).unlink(missing_ok=True)


def main() -> None:
    clean_readme()
    for path in sorted((ROOT / "docs").rglob("*.md")):
        clean_markdown(path)
    remove_unpublished_method_docs()
    patch_report_registry()
    patch_m26()
    patch_m15()
    patch_scoring_report()
    patch_public_gate()
    patch_tests()

    public_paths = [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]
    public_generators = (
        ROOT / "src/rasai/m15_reporting.py",
        ROOT / "src/rasai/m26_reporting.py",
        ROOT / "src/rasai/report_registry.py",
        ROOT / "src/rasai/score_geo_004_reporting.py",
    )
    remaining: list[str] = []
    for path in [*public_paths, *public_generators]:
        if path.is_file() and OLD_SCORE_RE.search(path.read_text(encoding="utf-8")):
            remaining.append(str(path.relative_to(ROOT)))
    if remaining:
        raise RuntimeError("obsolete public SCORE-GEO references remain: " + ", ".join(remaining))


if __name__ == "__main__":
    main()
