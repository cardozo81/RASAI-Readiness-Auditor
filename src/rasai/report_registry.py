"""Install the stable public report contract into legacy/current generators.

Report generators remain responsible for their domain content. This module owns
cross-cutting presentation invariants that must be identical on every page:
canonical navigation, dependency metadata, SARI method projection, version-neutral
filenames, manifest projection and defensive normalization of stale wording.
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re
import sqlite3

from rasai.report_contract import (
    CANONICAL_NAV_ITEMS,
    REPORT_ALIASES,
    REPORT_SURFACES,
    surface_by_filename,
)
from rasai.score_geo_004 import (
    DIMENSION_WEIGHTS,
    MACRO_COMPONENTS,
    OVERALL_AGGREGATION_VERSION,
    SCORING_VERSION,
)


_DIMENSION_PUBLIC_LABELS = {
    "DISCOVERY_ACCESS": "Discovery & Crawler Access",
    "INDEXABILITY": "Indexability & Canonicalization",
    "CONTENT_EXTRACTABILITY": "Rendering & Extractability",
    "SEMANTIC_STRUCTURE": "Semantic Structure",
    "ENTITY_CLARITY": "Entity Clarity",
    "STRUCTURED_DATA": "Structured Data",
    "ANSWERABILITY": "Answerability",
    "CITATION_READINESS": "Citation Readiness",
    "EVIDENCE_TRUST": "Evidence & Trust",
    "INTENT_COVERAGE": "Intent Coverage",
    "CONTENT_VALUE": "Content Value",
}

_MACRO_PUBLIC_LABELS = {
    "DISCOVERY_AND_CRAWLER_ACCESS": "Discovery & Crawler Access",
    "INDEXABILITY_AND_CANONICALIZATION": "Indexability & Canonicalization",
    "RENDERING_AND_EXTRACTABILITY": "Rendering & Extractability",
    "SEMANTIC_UNDERSTANDABILITY": "Semantic Understandability",
    "CONTENT_UTILITY_AND_INTENT": "Content Utility & Intent",
    "EVIDENCE_TRUST_AND_CITATION": "Evidence, Trust & Citation",
    "STRUCTURED_DATA": "Structured Data",
}


def _ensure_single_filename(label: str, filename: str) -> None:
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
    from rasai import rasai_readiness_reporting
    rasai_readiness_reporting.COMPATIBLE_ENGINE_VERSION = SCORING_VERSION


def _normalize_known_legacy_wording(html: str, *, page_name: str) -> str:
    del page_name
    updated = re.sub(r"SCORE-GEO-(?!004)\d{3}", SCORING_VERSION, html, flags=re.I)
    replacements = (
        ("TECHNICAL_ACCESSIBILITY", "DISCOVERY_ACCESS"),
        ("Acessibilidade Técnica", "Discovery & Crawler Access"),
        ("Acessibilidade técnica", "Discovery & Crawler Access"),
        ("EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1", OVERALL_AGGREGATION_VERSION),
        ("Peso igual entre dimensões aplicáveis", "Agregação hierárquica ponderada"),
        ("peso igual entre dimensões aplicáveis", "agregação hierárquica ponderada"),
        ("Média simples das dimensões aplicáveis suficientemente consolidadas.", "Média ponderada das dimensões aplicáveis e efetivamente medidas."),
        ("Média de igual peso das dimensões aplicáveis com medição suficiente.", "Média ponderada das dimensões aplicáveis com medição suficiente."),
        ("contratos históricos", "contrato vigente"),
        ("contrato histórico", "contrato vigente"),
        ("histórico metodológico", "contrato metodológico vigente"),
        ("metodologia histórica", "metodologia vigente"),
    )
    for old, replacement in replacements:
        updated = updated.replace(old, replacement)
    # Raw fallback labels must not leak when a legacy generator does not know the
    # newly introduced dimension yet.
    updated = updated.replace(">DISCOVERY_ACCESS<", ">Discovery & Crawler Access<")
    updated = updated.replace(">CONTENT_VALUE<", ">Content Value<")
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
        "<div class='report-contract-grid'>"
        f"<div class='report-contract-item'><h3>Inputs</h3><p>{escape(list_text(surface.inputs))}</p></div>"
        f"<div class='report-contract-item'><h3>Outputs</h3><p>{escape(list_text(surface.outputs))}</p></div>"
        f"<div class='report-contract-item'><h3>Dependências obrigatórias</h3><p>{escape(list_text(surface.required_dependencies))}</p></div>"
        f"<div class='report-contract-item'><h3>Dependências opcionais</h3><p>{escape(list_text(surface.optional_dependencies))}</p></div>"
        f"<div class='report-contract-item'><h3>Uso de IA</h3><p>{escape(surface.ai_usage)}</p></div>"
        f"<div class='report-contract-item'><h3>Impacto no SARI/SCORE</h3><p>{escape(surface.score_impact)}</p></div>"
        f"<div class='report-contract-item'><h3>Fonte de verdade</h3><p>{escape(surface.source_of_truth)}</p></div>"
        "</div>"
        "<div class='notice report-reading-governance' data-report-reading-governance='true'>"
        "<strong>Como interpretar:</strong> score mede a qualidade do universo avaliado; Coverage e Confidence medem força/completude da medição; Critical Gates informam bloqueios fundamentais de readiness. Um gate BLOCKED não é escondido por uma média alta, e UNKNOWN não é convertido em FAIL."
        "</div></section>"
    )


def _dependency_map() -> str:
    return (
        "<section id='report-dependency-map' class='panel' data-report-dependency-map='true'>"
        "<div class='kicker'>Arquitetura da auditoria</div><h2>Como as evidências alimentam as superfícies</h2>"
        "<p class='intro'>As setas representam fluxo de evidência/projeção, não causalidade entre métricas.</p>"
        "<div class='notice'><strong>Audit Evidence</strong><br>"
        "├-&gt; <strong>SARI / SCORE-GEO-004</strong> <span class='badge'>regras contratadas</span><br>"
        "├-&gt; Web Performance / Accessibility <span class='badge'>métricas externas</span><br>"
        "├-&gt; Search Intelligence / AI Visibility <span class='badge'>outcomes observados</span><br>"
        "├-&gt; Synthetic Apdex <span class='badge'>complementar</span><br>"
        "└-&gt; AI Usage <span class='badge'>telemetria</span></div>"
        "<p class='intro'>Scores Lighthouse, Core Web Vitals, Apdex, SERP e telemetria não entram diretamente no SARI. Audit-level evidence externa só pode corroborar regra equivalente por mapeamento explícito e sem dupla pontuação.</p></section>"
    )


def _macro_weight_rows() -> str:
    rows: list[str] = []
    for macro, dimensions in MACRO_COMPONENTS.items():
        weight = sum(DIMENSION_WEIGHTS[item] for item in dimensions)
        detail = ", ".join(
            f"{_DIMENSION_PUBLIC_LABELS[item]} {DIMENSION_WEIGHTS[item] * 100:.0f}%"
            for item in dimensions
        )
        rows.append(
            f"<tr><td><strong>{escape(_MACRO_PUBLIC_LABELS[macro])}</strong></td>"
            f"<td>{weight * 100:.0f}%</td><td>{escape(detail)}</td></tr>"
        )
    return "".join(rows)


def _latest_sari_states(report_dir: Path) -> list[dict[str, str]]:
    database = report_dir.parent / "audit.db"
    if not database.is_file():
        return []
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            rows = connection.execute(
                """SELECT device,value,limitations,calculated_at
                   FROM scores
                   WHERE dimension='OVERALL_READINESS' AND scoring_version=?
                   ORDER BY calculated_at""",
                (SCORING_VERSION,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    finally:
        connection.close()

    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        device = str(row["device"])
        raw = row["limitations"]
        try:
            limitations = json.loads(raw) if isinstance(raw, str) else list(raw or ())
        except (TypeError, ValueError, json.JSONDecodeError):
            limitations = []
        gates = {"DISCOVERY": "-", "INDEXABILITY": "-", "EXTRACTION": "-"}
        status = "-"
        for item in limitations:
            text = str(item)
            if text.startswith("CRITICAL_GATE:"):
                parts = text.split(":", 2)
                if len(parts) == 3 and parts[1] in gates:
                    gates[parts[1]] = parts[2]
            elif text.startswith("READINESS_STATUS:"):
                status = text.split(":", 1)[1]
        latest[device] = {
            "device": device,
            "value": "-" if row["value"] is None else f"{float(row['value']):.1f}",
            "status": status,
            **gates,
        }
    return list(latest.values())


def _sari_method_panel(report_dir: Path, page_name: str) -> str:
    if page_name not in {"readiness.html", "scoring.html"}:
        return ""
    state_rows = _latest_sari_states(report_dir)
    state_table = ""
    if state_rows:
        body = "".join(
            "<tr>"
            f"<td>{escape(item['device'])}</td><td>{escape(item['value'])}</td>"
            f"<td><strong>{escape(item['status'])}</strong></td>"
            f"<td>{escape(item['DISCOVERY'])}</td><td>{escape(item['INDEXABILITY'])}</td><td>{escape(item['EXTRACTION'])}</td>"
            "</tr>"
            for item in state_rows
        )
        state_table = (
            "<h3>Critical readiness gates desta auditoria</h3>"
            "<div class='table-wrap'><table><thead><tr><th>Device</th><th>SARI</th><th>Status</th><th>Discovery</th><th>Indexability</th><th>Extraction</th></tr></thead>"
            f"<tbody>{body}</tbody></table></div>"
            "<p class='intro'>O status é separado do número: uma medição pode ser CONSOLIDATED e ainda estar BLOCKED por uma condição crítica do website.</p>"
        )
    return (
        "<section id='sari-hierarchical-contract' class='panel' data-sari-hierarchical-contract='true'>"
        "<div class='kicker'>SARI-001 - contrato vigente</div>"
        f"<h2>{escape(OVERALL_AGGREGATION_VERSION)}</h2>"
        "<p class='intro'>O Overall deixou de ser uma média 10 x 10. RuleExecutions são resolvidas por página/escopo, agregadas em scoring groups de peso fixo e só então nas dimensões. A quantidade de páginas não multiplica o peso de um grupo global como robots.txt ou sitemap.</p>"
        "<div class='table-wrap'><table><thead><tr><th>Macrocomponente</th><th>Peso no SARI</th><th>Dimensões</th></tr></thead>"
        f"<tbody>{_macro_weight_rows()}</tbody></table></div>"
        "<div class='notice'><strong>Precedência de evidência:</strong> fato determinístico conclusivo prevalece sobre avaliação IA corroborativa no mesmo scoring_group. IA pode aprofundar ou resolver um estado sem evidência suficiente, mas não sobrescrever um hard fact avaliado.</div>"
        "<div class='notice'><strong>Lighthouse:</strong> Performance, Accessibility, Best Practices e SEO continuam métricas externas. Os category scores não entram na aritmética SARI; apenas audit-level evidence explicitamente mapeada pode corroborar a mesma condição técnica, sem bônus duplicado.</div>"
        f"{state_table}</section>"
    )


def _inject_shared_contract(html: str, *, page_name: str, report_dir: Path) -> str:
    if page_name == "index.html" and "data-report-dependency-map='true'" not in html:
        html = html.replace("</main>", _dependency_map() + "</main>", 1)
    if "data-sari-hierarchical-contract='true'" not in html:
        panel = _sari_method_panel(report_dir, page_name)
        if panel:
            html = html.replace("</main>", panel + "</main>", 1)
    if "data-report-contract='true'" not in html:
        section = _contract_section(page_name)
        if section:
            html = html.replace("</main>", section + "</main>", 1)
    return html


def _patch_final_branding_normalization() -> None:
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
            updated = updated.replace("Compatibilidade metodológica:", "Contrato metodológico:")
            updated = _inject_shared_contract(updated, page_name=path.name, report_dir=root)
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
    report_navigation._RULE_TOOLTIPS["BR-GEO-057"] = (
        "Content Value - avalia sinais evidence-bound de utilidade e especificidade; heurística RASAi."
    )
    report_navigation._RULE_TOOLTIPS["BR-GEO-058"] = (
        "Content Value - diferenciação/experiência própria só é concluída com sinal explícito; ausência de prova fica UNKNOWN."
    )
    report_navigation._RULE_TOOLTIPS["BR-GEO-059"] = (
        "Content Value - avalia profundidade/contexto por baseline conservadora; heurística RASAi."
    )
    _patch_apdex_navigation()
    _patch_lighthouse_traceability_message()
    _patch_current_scoring_projection()
    _patch_final_branding_normalization()
