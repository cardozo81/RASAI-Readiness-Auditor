"""Version-aware HTML projection for the stable scoring report surface."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sqlite3

from rasai import report_navigation
from rasai.persistence import AuditWorkspace
from rasai.report_contract import REPORT_CONTRACT_VERSION, SARI_VERSION
from rasai.score_geo_004 import (
    FEATURE_ORDER,
    MIN_OVERALL_COVERAGE,
    MIN_PARTIAL_COVERAGE,
    OVERALL_AGGREGATION_VERSION,
    SCORING_VERSION,
)

# Public URLs are version-neutral. Method versions live in persisted metadata and
# in the rendered content. This pre-publication build exposes only the canonical path.
REPORT_FILE = "scoring.html"

_DIMENSION_LABELS = {
    "TECHNICAL_ACCESSIBILITY": "Acessibilidade técnica",
    "INDEXABILITY": "Capacidade de indexação",
    "CONTENT_EXTRACTABILITY": "Extração de conteúdo",
    "SEMANTIC_STRUCTURE": "Estrutura semântica",
    "ENTITY_CLARITY": "Clareza de entidades",
    "STRUCTURED_DATA": "Dados estruturados",
    "ANSWERABILITY": "Capacidade de resposta",
    "CITATION_READINESS": "Preparação para citação",
    "EVIDENCE_TRUST": "Evidências e confiabilidade",
    "INTENT_COVERAGE": "Cobertura de intenções",
}

# Page-scoped layout: scoring contribution tables need substantially more horizontal
# space than generic report cards. Keeping this CSS local prevents a scoring-specific
# readability requirement from changing the layout contract of the other reports.
_SCORING_LAYOUT_CSS = r"""
.scoring-weight-groups{display:flex;flex-direction:column;gap:16px;margin-top:16px}
.scoring-dimension-panel{width:100%;min-width:0;border:1px solid var(--line);background:var(--surface);border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(47,58,78,.025)}
.scoring-dimension-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 16px;background:#f7f8fb;border-bottom:1px solid var(--line)}
.scoring-dimension-heading h4{margin:0;font-size:1rem;line-height:1.3}
.scoring-dimension-meta{color:var(--muted);font-size:.76rem;white-space:nowrap}
.scoring-dimension-table{margin:0!important;border:0!important;border-radius:0!important;overflow-x:auto;overflow-y:visible;max-height:none!important}
.scoring-dimension-table table{width:100%;min-width:940px;table-layout:fixed}
.scoring-dimension-table th,.scoring-dimension-table td{padding:11px 12px;line-height:1.45}
.scoring-dimension-table th:nth-child(1),.scoring-dimension-table td:nth-child(1){width:112px}
.scoring-dimension-table th:nth-child(2),.scoring-dimension-table td:nth-child(2){width:auto;min-width:300px}
.scoring-dimension-table th:nth-child(3),.scoring-dimension-table td:nth-child(3){width:190px}
.scoring-dimension-table th:nth-child(4),.scoring-dimension-table td:nth-child(4){width:72px;text-align:center}
.scoring-dimension-table th:nth-child(5),.scoring-dimension-table td:nth-child(5){width:110px}
.scoring-dimension-table th:nth-child(6),.scoring-dimension-table td:nth-child(6){width:72px;text-align:center}
.scoring-dimension-table th:nth-child(7),.scoring-dimension-table td:nth-child(7){width:142px;text-align:right}
.scoring-dimension-table td:nth-child(2){color:#3f4c60}
.scoring-dimension-table td:nth-child(3) code{white-space:normal;overflow-wrap:anywhere;word-break:break-word}
.scoring-dimension-table td:nth-child(4),.scoring-dimension-table td:nth-child(5),.scoring-dimension-table td:nth-child(6),.scoring-dimension-table td:nth-child(7){white-space:nowrap}
.scoring-dimension-table tbody tr:hover{background:#fafbfc}
@media(max-width:900px){.scoring-dimension-heading{align-items:flex-start;flex-direction:column;gap:4px}.scoring-dimension-meta{white-space:normal}.scoring-dimension-table table{min-width:900px}}
@media print{.scoring-dimension-panel{break-inside:avoid;box-shadow:none}.scoring-dimension-table{overflow:visible}.scoring-dimension-table table{min-width:0;table-layout:auto;font-size:.72rem}.scoring-dimension-table th,.scoring-dimension-table td{width:auto!important;min-width:0!important;padding:6px 7px}}
"""


def register_navigation() -> None:
    # Pre-publication contract: there is one version-neutral scoring surface only.
    items = [
        item
        for item in report_navigation.NAV_ITEMS
        if item[1] == REPORT_FILE or not item[1].startswith("score-geo-")
    ]
    items = [item for item in items if item[1] != REPORT_FILE]
    pos = next((i + 1 for i, item in enumerate(items) if item[1] == "readiness.html"), 2)
    items.insert(pos, ("Metodologia de scoring", REPORT_FILE))
    report_navigation.NAV_ITEMS = tuple(items)


def write_score_geo_004_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    """Render the single scoring surface supported by this pre-publication build."""
    register_navigation()
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    nav = report_navigation.render_report_navigation(report_dir, REPORT_FILE)
    versions = _scoring_versions(audit_id, workspace)
    effective_version = SCORING_VERSION
    scores = _scores(audit_id, workspace, SCORING_VERSION)
    score_rows = "".join(_score_row(row) for row in scores) or "<tr><td colspan='7'>Overall vigente não persistido para esta auditoria.</td></tr>"
    status_label = "VIGENTE"

    html = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Metodologia de scoring - {escape(effective_version)}</title><link rel='stylesheet' href='css/site.css'><style>{_SCORING_LAYOUT_CSS}</style></head><body>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>RASAi - metodologia de pontuação da auditoria</div><h1>{escape(effective_version)}</h1><p class='lead'>{_version_intro(effective_version)}</p><div class='metric-grid'>{_metric('Índice público', SARI_VERSION)}{_metric('scoring_version', effective_version)}{_metric('Estado da metodologia', status_label)}{_metric('Contrato de relatório', REPORT_CONTRACT_VERSION)}</div></header>
{_version_integrity_notice(versions)}
<section class='panel'><h2>Resultado Overall persistido</h2><p class='intro'>Esta tabela é projeção read-only de <code>audit.db</code>. Renderizar o HTML não recalcula nem troca a <code>scoring_version</code>.</p><div class='table-wrap'><table><thead><tr><th>Device</th><th>Overall</th><th>Coverage</th><th>Confidence</th><th>Consolidação</th><th>scoring_version</th><th>Motivo / rastreabilidade</th></tr></thead><tbody>{score_rows}</tbody></table></div></section>
{_method_section(effective_version, workspace, audit_id)}
<section class='panel'><h2>O que entra no score</h2><p class='intro'>Entram somente <strong>RuleExecutions aplicáveis</strong> mapeadas às dimensões do contrato e suas evidências persistidas. Para {SCORING_VERSION}, cada dimensão usa pesos e fatores estáticos/versionados persistidos em <code>score_contributions</code>; o Overall usa peso igual entre dimensões aplicáveis que tenham medição suficiente. Sitemap e robots usam peso interno pequeno/moderado e compartilham grupos com eventual avaliação técnica por IA, impedindo bônus duplicado. JSON-LD ausente é uma lacuna leve mensurável; JSON-LD inválido é desfavorável; consistência semântica pode usar IA evidence-bound quando disponível.</p>{_dimension_list(effective_version)}</section>
<section class='panel'><h2>O que não entra automaticamente no score</h2><ul><li>Lighthouse Performance;</li><li>Core Web Vitals / CrUX;</li><li>Lighthouse Accessibility;</li><li>Synthetic Navigation Apdex;</li><li>Synthetic User Experience Apdex;</li><li>Observed Generative Visibility;</li><li>Search Console e demais outcomes de Observability;</li><li>custos, tokens ou quantidade de chamadas de IA;</li><li>Monitoring, Quality, Fix Verification e Evidence Timeline.</li></ul><div class='notice'><strong>IA e scoring:</strong> IA não escolhe pesos, thresholds ou o Overall. Quando elegível e explicitamente habilitada, uma avaliação evidence-bound pode materializar RuleExecution bounded em regra previamente definida pelo contrato (por exemplo BR-GEO-055/056); essa regra compartilha o scoring_group do sinal determinístico e não cria bônus duplicado. O cálculo final continua determinístico sobre estados/evidências persistidos.</div></section>
<section class='panel'><h2>Dependências e reprodutibilidade</h2><div class='grid'><div><h3>Inputs</h3><p>RuleExecutions, Evidences, applicability, pesos/fatores persistidos, Coverage e Confidence.</p></div><div><h3>Outputs</h3><p>Scores por dimensão, Overall, Coverage, Confidence e Consolidation.</p></div><div><h3>Dependências obrigatórias</h3><p><code>audit.db</code> íntegro e <code>scoring_version</code> preservada.</p></div><div><h3>IA obrigatória</h3><p>Não para a fórmula. A ausência de IA pode deixar regras semânticas sem evidência suficiente quando aplicável.</p></div><div><h3>Fonte de verdade</h3><p><code>audit.db</code>; HTML é somente projeção.</p></div><div><h3>Contrato vigente</h3><p>Esta build de desenvolvimento publica somente o contrato vigente da auditoria. A versão continua persistida em <code>scoring_version</code>.</p></div></div></section>
<section class='panel'><h2>Estados de medição</h2><p><code>UNKNOWN</code> não significa FAIL. <code>NOT_APPLICABLE</code> não recebe zero. Ausência de um recurso que o método considera uma melhoria de readiness pode ser <code>WARNING</code> com fator reduzido em vez de PASS ou zero. <code>NOT_CONSOLIDATED</code> indica que a evidência não sustenta consolidação. <code>UNAVAILABLE</code> indica ausência técnica do dado esperado para aquela superfície.</p></section>
<section class='panel'><h2>Contrato do arquivo</h2><p><code>{REPORT_FILE}</code> é o único endereço canônico desta build de desenvolvimento. A versão metodológica pertence a <code>scoring_version</code>, banco, manifests, metadados e conteúdo.</p></section>
<footer class='footer'>{escape(effective_version)} é uma metodologia versionada e auditável do RASAi. O índice não garante ranking, tráfego, conversão ou citação futura.</footer></main></body></html>\n"""
    path = report_dir / REPORT_FILE
    path.write_text(html, encoding="utf-8", newline="\n")
    # Pre-publication development contract: remove any obsolete version-named surface.
    for obsolete in report_dir.glob('score-geo-*.html'):
        obsolete.unlink(missing_ok=True)
    return path


def _scoring_versions(audit_id: str, workspace: AuditWorkspace) -> list[str]:
    connection = sqlite3.connect(workspace.database)
    try:
        try:
            rows = connection.execute(
                "SELECT DISTINCT scoring_version FROM scores WHERE audit_id=? AND scoring_version IS NOT NULL ORDER BY scoring_version",
                (audit_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [str(row[0]) for row in rows if row[0]]
    finally:
        connection.close()


def _scores(audit_id: str, workspace: AuditWorkspace, scoring_version: str | None) -> list[sqlite3.Row]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if scoring_version is None:
            sql = "SELECT device,value,coverage,confidence,consolidation_status,limitations,scoring_version FROM scores WHERE audit_id=? AND dimension='OVERALL_READINESS' ORDER BY scoring_version,device,calculated_at"
            params = (audit_id,)
        else:
            sql = "SELECT device,value,coverage,confidence,consolidation_status,limitations,scoring_version FROM scores WHERE audit_id=? AND dimension='OVERALL_READINESS' AND scoring_version=? ORDER BY device,calculated_at"
            params = (audit_id, scoring_version)
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()


def _rule_weights(audit_id: str, workspace: AuditWorkspace, scoring_version: str) -> list[sqlite3.Row]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        return list(connection.execute(
            """SELECT c.dimension,c.rule_id,c.scoring_group,c.weight,c.result,c.result_factor,c.effective_contribution
               FROM score_contributions c
               JOIN scores s ON s.score_id=c.score_id
               WHERE s.audit_id=? AND s.scoring_version=?
               ORDER BY c.dimension,c.scoring_group,c.rule_id,c.weight""",
            (audit_id, scoring_version),
        ).fetchall())
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()


def _rule_description(rule_id: str) -> str:
    text = report_navigation._RULE_TOOLTIPS.get(rule_id, "")
    if " · " in text:
        return text.split(" · ", 1)[1]
    return text or "Critério versionado do RASAi; consulte Referências e metodologia."


def _method_section(version: str, workspace: AuditWorkspace, audit_id: str) -> str:
    if version == SCORING_VERSION:
        weights = _rule_weights(audit_id, workspace, version)
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in weights:
            grouped.setdefault(str(row["dimension"]), []).append(row)
        blocks: list[str] = []
        ordered_dimensions = [dimension for dimension in FEATURE_ORDER if dimension in grouped]
        ordered_dimensions.extend(dimension for dimension in grouped if dimension not in ordered_dimensions)
        for dimension in ordered_dimensions:
            rows = grouped[dimension]
            body: list[str] = []
            scoring_groups: set[str] = set()
            for row in rows:
                factor = "-" if row["result_factor"] is None else f"{float(row['result_factor']):.2f}"
                effective = "-" if row["effective_contribution"] is None else f"{float(row['effective_contribution']):.3f}"
                group = str(row["scoring_group"] or "regra independente")
                scoring_groups.add(group)
                rule_id = str(row["rule_id"])
                body.append(
                    "<tr>"
                    f"<td><strong>{escape(rule_id)}</strong></td>"
                    f"<td>{escape(_rule_description(rule_id))}</td>"
                    f"<td><code>{escape(group)}</code></td>"
                    f"<td>{float(row['weight']):g}</td>"
                    f"<td>{escape(str(row['result']))}</td>"
                    f"<td>{escape(factor)}</td>"
                    f"<td>{escape(effective)}</td>"
                    "</tr>"
                )
            label = _DIMENSION_LABELS.get(dimension, dimension)
            rule_label = "regra" if len(rows) == 1 else "regras"
            group_label = "grupo" if len(scoring_groups) == 1 else "grupos"
            blocks.append(
                "<article class='scoring-dimension-panel'>"
                f"<div class='scoring-dimension-heading'><h4>{escape(label)}</h4>"
                f"<span class='scoring-dimension-meta'>{len(rows)} {rule_label} · {len(scoring_groups)} {group_label}</span></div>"
                "<div class='table-wrap scoring-dimension-table'><table><thead><tr>"
                "<th>Regra</th><th>Critério</th><th>Grupo</th><th>Peso</th><th>Resultado</th><th>Fator</th><th>Contribuição efetiva</th>"
                f"</tr></thead><tbody>{''.join(body)}</tbody></table></div></article>"
            )
        materialized = "<div class='scoring-weight-groups'>" + "".join(blocks) + "</div>" if blocks else "<p class='intro'>Nenhuma contribuição persistida disponível para detalhar pesos nesta projeção.</p>"
        return f"""<section class='panel'><h2>Fórmula e gates do método vigente</h2><p><strong>Dimensão:</strong> <code>sum(weight × result_factor) / sum(weight evaluated) × 100</code>.</p><p><strong>Overall:</strong> média aritmética de igual peso das dimensões aplicáveis que possuem valor e não estão em <code>NOT_CONSOLIDATED</code>. Uma dimensão legitimamente <code>NOT_APPLICABLE</code> sai do denominador.</p><div class='metric-grid'>{_metric('Agregação Overall', OVERALL_AGGREGATION_VERSION)}{_metric('Coverage mínima para consolidar', f'{MIN_OVERALL_COVERAGE*100:.0f}%')}{_metric('Confidence mínima', 'MEDIUM')}{_metric('Coverage mínima para parcial', f'{MIN_PARTIAL_COVERAGE*100:.0f}%')}</div><h3>Contribuições materializadas neste AUD</h3><p class='intro'>Cada dimensão ocupa um painel de largura total, mantendo regra, critério humano, <code>scoring_group</code>, peso, fator aplicado e contribuição persistida na mesma linha de leitura. Regras do mesmo grupo não somam bônus: o grupo usa o peso máximo configurado e o resultado representativo mais restritivo avaliado.</p>{materialized}<div class='notice'><strong>Governança da leitura:</strong> pesos de regra atuam somente dentro da dimensão. O Overall continua com peso igual entre dimensões aplicáveis. Um Overall numericamente alto pode permanecer <code>PARTIAL</code> quando Coverage/Confidence não alcançam os gates; isso qualifica a força da medição e não invalida a aritmética do score.</div><div class='notice'><strong>Calibração externa:</strong> não é requisito, input ou gate do Overall {SCORING_VERSION}.</div></section>"""


def _dimension_list(version: str) -> str:
    del version
    items = "".join(f"<li><code>{escape(name)}</code></li>" for name in FEATURE_ORDER)
    return f"<ul>{items}</ul><p class='intro'>No Overall 004, cada dimensão aplicável consolidável recebe peso igual; pesos internos de regras são os persistidos nas contribuições da respectiva dimensão.</p>"


def _version_intro(version: str) -> str:
    del version
    return "Método operacional vigente do SARI-001. O Overall é determinístico, reproduzível e baseado nas evidências persistidas da auditoria; não depende de model artifact externo."


def _version_integrity_notice(versions: list[str]) -> str:
    unsupported = [version for version in versions if version != SCORING_VERSION]
    if not unsupported:
        return ""
    return (
        "<section class='notice bad'><strong>Integridade metodológica:</strong> esta auditoria contém "
        "uma scoring_version que não pertence ao contrato suportado por esta build pré-publicação. "
        f"Somente <code>{SCORING_VERSION}</code> é reconhecido e nenhuma versão descontinuada é projetada ou convertida.</section>"
    )


def _score_row(row: sqlite3.Row) -> str:
    value = "Indisponível" if row["value"] is None else f"{float(row['value']):.1f}/100"
    return (
        "<tr>"
        f"<td>{escape(str(row['device']))}</td>"
        f"<td>{escape(value)}</td>"
        f"<td>{float(row['coverage'])*100:.1f}%</td>"
        f"<td>{escape(str(row['confidence']))}</td>"
        f"<td>{escape(str(row['consolidation_status']))}</td>"
        f"<td>{escape(str(row['scoring_version']))}</td>"
        f"<td>{escape(_score_reason(row))}</td>"
        "</tr>"
    )


def _score_reason(row: sqlite3.Row) -> str:
    try:
        raw = json.loads(str(row["limitations"] or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        raw = []
    limitations = [str(item) for item in raw if item]
    missing = [item.split(":", 1)[1] for item in limitations if item.startswith("DIMENSION_NOT_CONSOLIDATED:")]
    if missing:
        return "Dimensão(ões) ainda não consolidada(s): " + ", ".join(missing)
    status = str(row["consolidation_status"])
    if status == "CONSOLIDATED":
        return "Overall determinístico consolidado pelos gates da metodologia persistida."
    if status == "PARTIAL":
        return "Overall calculado, mas a força da medição não alcançou o gate de consolidação da metodologia persistida."
    return "Overall não consolidado; consulte Coverage, Confidence e limitações das dimensões."


def _metric(label: str, value: str) -> str:
    return f"<div class='metric'><small>{escape(label)}</small><strong>{escape(value)}</strong></div>"
