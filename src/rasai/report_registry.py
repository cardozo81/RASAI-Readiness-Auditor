"""Install the stable public report contract into legacy/current generators.

Report generators remain responsible for their domain content. This module owns
cross-cutting presentation invariants that must be identical on every page:
canonical navigation, public dependency metadata, version-neutral filenames,
manifest projection and defensive normalization of known stale wording.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
import sqlite3

from rasai.report_contract import (
    CANONICAL_NAV_ITEMS,
    REPORT_ALIASES,
    REPORT_SURFACES,
    surface_by_filename,
)


def _ensure_single_filename(label: str, filename: str) -> None:
    """Keep exactly one navigation entry for a report filename."""
    from rasai import report_navigation

    items: list[tuple[str, str]] = []
    inserted = False
    for current_label, current_filename in report_navigation.NAV_ITEMS:
        if current_filename == filename:
            if not inserted:
                items.append((label, filename))
                inserted = True
            continue
        items.append((current_label, current_filename))
    if not inserted:
        canonical_index = next(
            (index for index, item in enumerate(CANONICAL_NAV_ITEMS) if item[1] == filename),
            len(items),
        )
        before = {item[1] for item in CANONICAL_NAV_ITEMS[:canonical_index]}
        insertion = 0
        for index, item in enumerate(items):
            if item[1] in before:
                insertion = index + 1
        items.insert(insertion, (label, filename))
    report_navigation.NAV_ITEMS = tuple(items)


def _patch_apdex_navigation() -> None:
    from rasai import m23_reporting, m25_reporting

    def register_navigation_apdex() -> None:
        _ensure_single_filename("Apdex de navegação", "apdex.html")

    def register_navigation_experience() -> None:
        _ensure_single_filename("Apdex de experiência", "apdex-experience.html")

    m23_reporting._register_apdex_navigation = register_navigation_apdex
    m25_reporting._register_navigation = register_navigation_experience


def _patch_lighthouse_traceability_message() -> None:
    from rasai import m23_reporting
    from rasai.report_presentation import public_label

    if getattr(m23_reporting, "_rasai_lighthouse_state_patch", False):
        return

    original_load = m23_reporting._load
    original_page = m23_reporting._page

    def load_with_web_run(audit_id, workspace):
        data = original_load(audit_id, workspace)
        connection = sqlite3.connect(workspace.database)
        connection.row_factory = sqlite3.Row
        try:
            try:
                web_run = connection.execute(
                    "SELECT * FROM web_performance_runs WHERE audit_id=?",
                    (audit_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                web_run = None
        finally:
            connection.close()
        data["web_run"] = web_run
        return data

    def lighthouse_message(data) -> str:
        if data.get("profiles"):
            return ""
        run = data.get("web_run")
        if run is None:
            return "Não disponível nesta execução: não existe estado persistido de Web Performance/Lighthouse."
        if not bool(run["enabled"]):
            return (
                "Não aplicável nesta execução: Web Performance externo estava desabilitado, "
                "portanto nenhum lighthouseResult.configSettings foi coletado."
            )
        status = public_label(str(run["status"] or "INDEFINIDO"))
        reason = str(run["reason"] or "").strip()
        suffix = f" Motivo persistido: {reason}." if reason else ""
        return (
            f"Nenhum configSettings Lighthouse utilizável foi persistido. Estado Web Performance: {status}."
            f"{suffix} Consulte Web Performance e o log operacional para a tentativa PageSpeed/Lighthouse."
        )

    def page_with_lighthouse_state(data, report_dir):
        html = original_page(data, report_dir)
        message = lighthouse_message(data)
        if message:
            html = html.replace(
                "Nenhum configSettings Lighthouse disponível.",
                escape(message),
                1,
            )
        return html

    m23_reporting._load = load_with_web_run
    m23_reporting._page = page_with_lighthouse_state
    m23_reporting._rasai_lighthouse_state_patch = True


def _patch_current_scoring_projection() -> None:
    """Keep public SARI projection aligned with the current runtime version."""
    from rasai import rasai_readiness_reporting
    from rasai.score_geo_004 import SCORING_VERSION

    rasai_readiness_reporting.COMPATIBLE_ENGINE_VERSION = SCORING_VERSION


def _normalize_known_legacy_wording(html: str, *, page_name: str) -> str:
    """Defensively repair stale current-method copy without rewriting history."""
    replacements = (
        ("não é convertido em SCORE-GEO-003", "não é convertido em SCORE-GEO-004"),
        ("SCORE-GEO-003 continua disponível normalmente", "SCORE-GEO-004 continua disponível normalmente"),
        ("não reduz SCORE-GEO-003", "não reduz SCORE-GEO-004"),
        ("Overall Readiness do SCORE-GEO-003", "Overall Readiness do SCORE-GEO-004"),
        ("separadamente do SCORE-GEO-003", "separadamente do SCORE-GEO-004"),
        ("threshold do SCORE-GEO-003", "threshold do SCORE-GEO-004"),
        ("SCORE-GEO-003 permanece índice heurístico independente e reprodutível", "SCORE-GEO-004 permanece índice heurístico independente e reprodutível"),
        ("SARI-001/SCORE-GEO-003", "SARI-001/SCORE-GEO-004"),
        ("SARI-001 nem SCORE-GEO-003", "SARI-001 nem SCORE-GEO-004"),
    )
    updated = html
    for old, new in replacements:
        updated = updated.replace(old, new)

    if page_name == "ai-visibility.html":
        updated = updated.replace(
            "do SCORE-GEO-003 vigente. SCORE-GEO-002 permanece histórico.",
            "do SCORE-GEO-004 vigente. SCORE-GEO-003 e SCORE-GEO-002 permanecem históricos.",
        )
        updated = updated.replace(
            "não compõem SARI-001/SCORE-GEO-002 histórico e tampouco SCORE-GEO-003 vigente",
            "não compõem SARI-001/SCORE-GEO-004 vigente; SCORE-GEO-003 e SCORE-GEO-002 permanecem contratos históricos",
        )
    return updated


def _contract_section(page_name: str) -> str:
    if page_name in REPORT_ALIASES:
        return ""
    try:
        surface = surface_by_filename(page_name)
    except KeyError:
        return ""

    def list_text(values: tuple[str, ...], fallback: str = "Nenhuma") -> str:
        return "; ".join(values) if values else fallback

    return (
        "<section id='public-report-contract' class='panel' data-report-contract='true'>"
        "<div class='kicker'>Contrato desta superfície</div>"
        f"<h2>{escape(surface.label)}: inputs, outputs e dependências</h2>"
        "<div class='grid'>"
        f"<div><h3>Inputs</h3><p>{escape(list_text(surface.inputs))}</p></div>"
        f"<div><h3>Outputs</h3><p>{escape(list_text(surface.outputs))}</p></div>"
        f"<div><h3>Dependências obrigatórias</h3><p>{escape(list_text(surface.required_dependencies))}</p></div>"
        f"<div><h3>Dependências opcionais</h3><p>{escape(list_text(surface.optional_dependencies))}</p></div>"
        f"<div><h3>Uso de IA</h3><p>{escape(surface.ai_usage)}</p></div>"
        f"<div><h3>Impacto no SARI/SCORE</h3><p>{escape(surface.score_impact)}</p></div>"
        f"<div><h3>Fonte de verdade</h3><p>{escape(surface.source_of_truth)}</p></div>"
        "</div>"
        "<div class='notice report-reading-governance' data-report-reading-governance='true'>"
        "<strong>Como interpretar e melhorar:</strong> um score alto e uma Confidence baixa não são resultados contraditórios: o score descreve a qualidade do que foi efetivamente avaliado, enquanto Coverage/Confidence descrevem a força e a completude da medição. "
        "WARNING/FAIL devem ser tratados pela evidência e pelo critério exibidos na própria página; UNKNOWN/UNAVAILABLE/PARTIAL indicam dado não conclusivo ou cobertura insuficiente, salvo quando a superfície disser explicitamente o contrário. "
        "Quando amostra, escopo, max_pages, timeout, integração opcional ou número mínimo de execuções limitarem a medição, o relatório deve sinalizar parametrização/cobertura e não converter isso em falha do website. Aumentar parâmetros amplia a matriz de medição; não corrige o site e não deve ser usado apenas para buscar uma nota melhor. Consulte a Visão geral para configuração × resultado obtido."
        "</div></section>"
    )


def _dependency_map() -> str:
    return (
        "<section id='report-dependency-map' class='panel' data-report-dependency-map='true'>"
        "<div class='kicker'>Arquitetura da auditoria</div><h2>Como as evidências alimentam as superfícies</h2>"
        "<p class='intro'>As setas abaixo representam fluxo de evidência/projeção, não causalidade entre métricas. "
        "Somente regras pertencentes ao contrato SARI/SCORE entram no readiness.</p>"
        "<div class='notice'><strong>Audit Evidence</strong><br>"
        "├─&gt; <strong>SARI / SCORE-GEO-004</strong> <span class='badge'>participa do score</span><br>"
        "├─&gt; Remediação <span class='badge'>read-only derivado</span><br>"
        "├─&gt; Web Performance ─&gt; Acessibilidade <span class='badge'>integração externa / complementar</span><br>"
        "├─&gt; Synthetic Apdex <span class='badge'>complementar</span><br>"
        "├─&gt; Observability <span class='badge'>observacional / integração externa</span><br>"
        "├─&gt; Quality <span class='badge'>read-only derivado</span><br>"
        "└─&gt; AI Usage <span class='badge'>telemetria de IA</span></div>"
        "<p class='intro'>Resultados gerados por IA devem ser identificados no próprio output e vinculados aos inputs/evidências usados; "
        "custos/tokens e telemetria de IA não entram no SCORE-GEO-004.</p></section>"
    )


def _inject_shared_contract(html: str, *, page_name: str) -> str:
    if page_name == "index.html" and "data-report-dependency-map='true'" not in html:
        html = html.replace("</main>", _dependency_map() + "</main>", 1)
    if "data-report-contract='true'" not in html:
        section = _contract_section(page_name)
        if section:
            html = html.replace("</main>", section + "</main>", 1)
    return html


def _patch_final_branding_normalization() -> None:
    """Apply shared public contract and keep a defensive final consistency pass."""
    from rasai import report_navigation
    from rasai.report_manifest import write_report_manifest
    from rasai.report_presentation import humanize_report_html

    if getattr(report_navigation, "_rasai_public_wording_patch", False):
        return
    original = report_navigation.normalize_report_navigation

    def normalize_with_current_wording(report_dir, *args, **kwargs):
        result = original(report_dir, *args, **kwargs)
        root = Path(report_dir)
        for path in root.glob("*.html"):
            try:
                html = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            updated = html.replace("Search/AI", "Search & AI")
            updated = _normalize_known_legacy_wording(updated, page_name=path.name)
            updated = updated.replace(
                "Média simples das dimensões aplicáveis suficientemente consolidadas. Dimensão legitimamente NOT_APPLICABLE não recebe zero.",
                "Média de igual peso das dimensões aplicáveis com medição suficiente. Dimensão legitimamente NOT_APPLICABLE sai do denominador e não recebe zero.",
            )
            updated = updated.replace("Compatibilidade metodológica:", "Contrato metodológico:")
            updated = updated.replace(
                "esta mudança de relatório não recalcula auditorias, não altera pesos e não quebra comparabilidade histórica.",
                "o resultado é calculado e persistido pelo contrato vigente desta auditoria.",
            )
            updated = _inject_shared_contract(updated, page_name=path.name)
            updated = updated.replace("—", "-").replace("–", "-")
            updated = humanize_report_html(updated, page_name=path.name)
            if updated != html:
                try:
                    path.write_text(updated, encoding="utf-8", newline="\n")
                except OSError:
                    continue
        write_report_manifest(root)
        return result

    report_navigation.normalize_report_navigation = normalize_with_current_wording
    report_navigation._rasai_public_wording_patch = True


def install() -> None:
    """Install the canonical public report contract idempotently."""
    from rasai import report_navigation

    report_navigation.NAV_ITEMS = CANONICAL_NAV_ITEMS
    report_navigation._RULE_TOOLTIPS["BR-GEO-054"] = (
        "Integridade do auditor - verifica a reprodutibilidade do scoring persistido; "
        "SCORE-GEO-004 é o método vigente e não depende de artifact de calibração."
    )
    _patch_apdex_navigation()
    _patch_lighthouse_traceability_message()
    _patch_current_scoring_projection()
    _patch_final_branding_normalization()
