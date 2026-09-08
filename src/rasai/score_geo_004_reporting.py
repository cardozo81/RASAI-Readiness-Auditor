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
# in the rendered content. The versioned 004 path is compatibility-only.
REPORT_FILE = "scoring.html"
LEGACY_REPORT_FILE = "score-geo-004.html"


def register_navigation() -> None:
    legacy_files = {"score-geo-003.html", LEGACY_REPORT_FILE, REPORT_FILE}
    items = [item for item in report_navigation.NAV_ITEMS if item[1] not in legacy_files]
    pos = next((i + 1 for i, item in enumerate(items) if item[1] == "readiness.html"), 2)
    items.insert(pos, ("Metodologia de scoring", REPORT_FILE))
    report_navigation.NAV_ITEMS = tuple(items)


def write_score_geo_004_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    """Render the stable scoring surface without rewriting historical methodology."""
    register_navigation()
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    nav = report_navigation.render_report_navigation(report_dir, REPORT_FILE)
    versions = _scoring_versions(audit_id, workspace)
    effective_version = versions[0] if len(versions) == 1 else (SCORING_VERSION if not versions else "MULTIPLE")
    scores = _scores(audit_id, workspace, effective_version if effective_version != "MULTIPLE" else None)
    score_rows = "".join(_score_row(row) for row in scores) or "<tr><td colspan='7'>Overall não persistido para esta versão.</td></tr>"
    status_label = "VIGENTE" if effective_version == SCORING_VERSION else "HISTÓRICA"
    if effective_version == "MULTIPLE":
        status_label = "INCONSISTENTE"

    html = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Metodologia de scoring - {escape(effective_version)}</title><link rel='stylesheet' href='css/site.css'></head><body>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>RASAi - metodologia de pontuação da auditoria</div><h1>{escape(effective_version)}</h1><p class='lead'>{_version_intro(effective_version)}</p><div class='metric-grid'>{_metric('Índice público', SARI_VERSION)}{_metric('scoring_version', effective_version)}{_metric('Estado da metodologia', status_label)}{_metric('Contrato de relatório', REPORT_CONTRACT_VERSION)}</div></header>
{_version_integrity_notice(versions)}
<section class='panel'><h2>Resultado Overall persistido</h2><p class='intro'>Esta tabela é projeção read-only de <code>audit.db</code>. Renderizar o HTML não recalcula nem troca a <code>scoring_version</code>.</p><div class='table-wrap'><table><thead><tr><th>Device</th><th>Overall</th><th>Coverage</th><th>Confidence</th><th>Consolidação</th><th>scoring_version</th><th>Motivo / rastreabilidade</th></tr></thead><tbody>{score_rows}</tbody></table></div></section>
{_method_section(effective_version, workspace, audit_id)}
<section class='panel'><h2>O que entra no score</h2><p class='intro'>Entram somente <strong>RuleExecutions aplicáveis</strong> mapeadas às dimensões do contrato e suas evidências persistidas. Para {SCORING_VERSION}, cada dimensão usa os pesos de regra persistidos em <code>score_contributions</code>; o Overall usa peso igual entre dimensões aplicáveis que tenham medição suficiente.</p>{_dimension_list(effective_version)}</section>
<section class='panel'><h2>O que não entra automaticamente no score</h2><ul><li>Lighthouse Performance;</li><li>Core Web Vitals / CrUX;</li><li>Lighthouse Accessibility;</li><li>Synthetic Navigation Apdex;</li><li>Synthetic User Experience Apdex;</li><li>Observed Generative Visibility;</li><li>Search Console e demais outcomes de Observability;</li><li>custos, tokens ou quantidade de chamadas de IA;</li><li>Monitoring, Quality, Fix Verification e Evidence Timeline.</li></ul><div class='notice'><strong>IA e scoring:</strong> IA pode produzir evidência semântica para regras elegíveis quando habilitada. O output da IA não substitui a fórmula e não altera diretamente o Overall; o cálculo usa o estado/evidência persistidos conforme o contrato da auditoria.</div></section>
<section class='panel'><h2>Dependências e reprodutibilidade</h2><div class='grid'><div><h3>Inputs</h3><p>RuleExecutions, Evidences, applicability, pesos/fatores persistidos, Coverage e Confidence.</p></div><div><h3>Outputs</h3><p>Scores por dimensão, Overall, Coverage, Confidence e Consolidation.</p></div><div><h3>Dependências obrigatórias</h3><p><code>audit.db</code> íntegro e <code>scoring_version</code> preservada.</p></div><div><h3>IA obrigatória</h3><p>Não para a fórmula. A ausência de IA pode deixar regras semânticas sem evidência suficiente quando aplicável.</p></div><div><h3>Fonte de verdade</h3><p><code>audit.db</code>; HTML é somente projeção.</p></div><div><h3>Comparabilidade histórica</h3><p>Somente séries com metodologia compatível. 002, 003 e 004 não são misturados como se fossem o mesmo método.</p></div></div></section>
<section class='panel'><h2>Estados de medição</h2><p><code>UNKNOWN</code> não significa FAIL. <code>NOT_APPLICABLE</code> não recebe zero. <code>NOT_CONSOLIDATED</code> indica que a evidência não sustenta consolidação. <code>UNAVAILABLE</code> indica ausência técnica do dado esperado para aquela superfície.</p></section>
<section class='panel'><h2>Contrato do arquivo</h2><p><code>{REPORT_FILE}</code> é o endereço canônico e estável. A versão metodológica pertence a <code>scoring_version</code>, banco, manifests, metadados e conteúdo. {_alias_explanation(effective_version)}</p></section>
<footer class='footer'>{escape(effective_version)} é uma metodologia versionada e auditável do RASAi. O índice não garante ranking, tráfego, conversão ou citação futura.</footer></main></body></html>\n"""
    path = report_dir / REPORT_FILE
    path.write_text(html, encoding="utf-8", newline="\n")
    if effective_version == SCORING_VERSION:
        _write_legacy_alias(report_dir)
    else:
        # A versioned 004 alias on a historical AUD would falsely imply that
        # the historical audit was scored with 004. Report files are projections,
        # so removing only this compatibility alias does not mutate audit evidence.
        (report_dir / LEGACY_REPORT_FILE).unlink(missing_ok=True)
    return path


def _write_legacy_alias(report_dir: Path) -> Path:
    """Keep old 004 links working without making the versioned path canonical."""
    alias = report_dir / LEGACY_REPORT_FILE
    html = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta http-equiv='refresh' content='0; url={REPORT_FILE}'><link rel='canonical' href='{REPORT_FILE}'><title>Metodologia de scoring - compatibilidade</title></head><body><main><p>Este endereço é um alias de compatibilidade do SCORE-GEO-004. O contrato público canônico é <a href='{REPORT_FILE}'>{REPORT_FILE}</a>; a versão efetivamente usada é lida do <code>audit.db</code>.</p></main></body></html>\n"""
    alias.write_text(html, encoding="utf-8", newline="\n")
    return alias


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
            """SELECT DISTINCT c.dimension,c.rule_id,c.weight
               FROM score_contributions c
               JOIN scores s ON s.score_id=c.score_id
               WHERE s.audit_id=? AND s.scoring_version=?
               ORDER BY c.dimension,c.rule_id,c.weight""",
            (audit_id, scoring_version),
        ).fetchall())
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()


def _method_section(version: str, workspace: AuditWorkspace, audit_id: str) -> str:
    if version == SCORING_VERSION:
        weights = _rule_weights(audit_id, workspace, version)
        rows = "".join(
            f"<tr><td>{escape(str(row['dimension']))}</td><td>{escape(str(row['rule_id']))}</td><td>{float(row['weight']):g}</td></tr>"
            for row in weights
        ) or "<tr><td colspan='3'>Nenhuma contribuição persistida disponível para detalhar pesos nesta projeção.</td></tr>"
        return f"""<section class='panel'><h2>Fórmula e gates do método vigente</h2><p><strong>Dimensão:</strong> <code>sum(weight × result_factor) / sum(weight evaluated) × 100</code>.</p><p><strong>Overall:</strong> média aritmética de igual peso das dimensões aplicáveis que possuem valor e não estão em <code>NOT_CONSOLIDATED</code>. Uma dimensão legitimamente <code>NOT_APPLICABLE</code> sai do denominador.</p><div class='metric-grid'>{_metric('Agregação Overall', OVERALL_AGGREGATION_VERSION)}{_metric('Coverage mínima para consolidar', f'{MIN_OVERALL_COVERAGE*100:.0f}%')}{_metric('Confidence mínima', 'MEDIUM')}{_metric('Coverage mínima para parcial', f'{MIN_PARTIAL_COVERAGE*100:.0f}%')}</div><h3>Pesos de regra materializados neste AUD</h3><div class='table-wrap'><table><thead><tr><th>Dimensão</th><th>Regra</th><th>Peso</th></tr></thead><tbody>{rows}</tbody></table></div><div class='notice'><strong>Calibração externa:</strong> não é requisito, input ou gate do Overall {SCORING_VERSION}.</div></section>"""
    if version == "MULTIPLE":
        return "<section class='panel'><h2>Integridade metodológica</h2><div class='notice bad'><strong>Múltiplas scoring_version foram encontradas no mesmo AUD.</strong> A projeção preserva os registros e não escolhe nem converte silenciosamente uma metodologia. Trate o AUD como não comparável até investigar a origem.</div></section>"
    return f"""<section class='panel'><h2>Metodologia histórica preservada</h2><p>Esta auditoria foi persistida com <strong>{escape(version)}</strong>. O RASAi não recalcula nem converte auditorias históricas para {SCORING_VERSION} durante a abertura do relatório.</p><p>{_historical_method_note(version)}</p><div class='notice'><strong>Regra de comparação:</strong> uma série histórica não pode misturar 002/003/004 como se fossem a mesma metodologia. Monitoring deve marcar versões incompatíveis como <code>NOT_COMPARABLE</code>.</div></section>"""


def _dimension_list(version: str) -> str:
    if version != SCORING_VERSION:
        return "<p class='intro'>As dimensões e valores exibidos permanecem exatamente os persistidos pelo método histórico; esta projeção não aplica a lista 004 retroativamente.</p>"
    items = "".join(f"<li><code>{escape(name)}</code></li>" for name in FEATURE_ORDER)
    return f"<ul>{items}</ul><p class='intro'>No Overall 004, cada dimensão aplicável consolidável recebe peso igual; pesos internos de regras são os persistidos nas contribuições da respectiva dimensão.</p>"


def _version_intro(version: str) -> str:
    if version == SCORING_VERSION:
        return "Método operacional vigente do SARI-001. O Overall é determinístico, reproduzível e baseado nas evidências persistidas da auditoria; não depende de model artifact externo."
    if version == "MULTIPLE":
        return "Foram encontradas múltiplas versões de scoring no mesmo AUD. O relatório não mistura nem converte essas metodologias e expõe o estado para investigação."
    return f"Este AUD preserva a metodologia histórica {escape(version)}. O relatório é read-only em relação ao score e não promove essa versão a runtime vigente."


def _historical_method_note(version: str) -> str:
    if version == "SCORE-GEO-003":
        return "SCORE-GEO-003 pertence ao histórico metodológico e usava fluxo de dataset/calibração/model artifact para o Overall. Esses requisitos não pertencem ao runtime 004."
    if version == "SCORE-GEO-002":
        return "SCORE-GEO-002 pertence ao histórico metodológico anterior. Seus resultados continuam identificados pela scoring_version original e não são reinterpretados pela fórmula 004."
    return "A versão não é o runtime atual. Consulte a documentação histórica correspondente antes de interpretar fórmula, pesos ou comparabilidade."


def _version_integrity_notice(versions: list[str]) -> str:
    if len(versions) <= 1:
        return ""
    joined = ", ".join(escape(item) for item in versions)
    return f"<section class='notice bad'><strong>Atenção:</strong> o AUD contém mais de uma <code>scoring_version</code>: {joined}. Nenhuma delas foi sobrescrita pelo relatório.</section>"


def _alias_explanation(version: str) -> str:
    if version == SCORING_VERSION:
        return f"<code>{LEGACY_REPORT_FILE}</code> pode existir apenas como alias de compatibilidade e não aparece no menu."
    return f"Como este AUD usa {escape(version)}, o alias <code>{LEGACY_REPORT_FILE}</code> não é materializado para evitar falsa atribuição metodológica."


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
        return "Overall consolidado pelos gates da metodologia persistida."
    if status == "PARTIAL":
        return "Overall calculado, mas a força da medição não alcançou o gate de consolidação da metodologia persistida."
    return "Overall não consolidado; consulte Coverage, Confidence e limitações das dimensões."


def _metric(label: str, value: str) -> str:
    return f"<div class='metric'><small>{escape(label)}</small><strong>{escape(value)}</strong></div>"
