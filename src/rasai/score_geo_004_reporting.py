"""HTML projection for the current SCORE-GEO-004 contract."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sqlite3

from rasai import report_navigation
from rasai.persistence import AuditWorkspace
from rasai.score_geo_004 import (
    MIN_OVERALL_COVERAGE,
    MIN_PARTIAL_COVERAGE,
    OVERALL_AGGREGATION_VERSION,
    SCORING_VERSION,
)

# The public report path is intentionally version-neutral. The scoring version is
# persisted in audit.db and rendered inside the page. This keeps bookmarks,
# automations and future SaaS routes stable across SCORE-GEO revisions.
REPORT_FILE = "scoring.html"
LEGACY_REPORT_FILE = "score-geo-004.html"


def register_navigation() -> None:
    legacy_files = {"score-geo-003.html", LEGACY_REPORT_FILE, REPORT_FILE}
    items = [item for item in report_navigation.NAV_ITEMS if item[1] not in legacy_files]
    pos = next((i + 1 for i, item in enumerate(items) if item[1] == "readiness.html"), 2)
    items.insert(pos, ("Metodologia de scoring", REPORT_FILE))
    report_navigation.NAV_ITEMS = tuple(items)


def write_score_geo_004_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    register_navigation()
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    nav = report_navigation.render_report_navigation(report_dir, REPORT_FILE)
    scores = _scores(audit_id, workspace)
    score_rows = "".join(_score_row(row) for row in scores) or "<tr><td colspan='6'>Overall não persistido.</td></tr>"
    html = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Metodologia de scoring - {SCORING_VERSION}</title><link rel='stylesheet' href='css/site.css'></head><body>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>RASAi - metodologia de pontuação vigente</div><h1>{SCORING_VERSION}</h1><p class='lead'>Método operacional padrão do SARI-001. As dimensões e o Overall são determinísticos, reproduzíveis e baseados apenas nas evidências persistidas da auditoria. O Overall não representa probabilidade de ranking ou citação.</p></header>
<section class='panel'><h2>Resultado Overall persistido</h2><div class='table-wrap'><table><thead><tr><th>Device</th><th>Overall</th><th>Coverage</th><th>Confidence</th><th>Consolidação</th><th>Motivo / rastreabilidade</th></tr></thead><tbody>{score_rows}</tbody></table></div></section>
<section class='panel'><h2>Contrato determinístico</h2><p><strong>Dimensão:</strong> <code>sum(weight x result_factor) / sum(weight evaluated) x 100</code>.</p><p><strong>Overall:</strong> média aritmética de igual peso das dimensões aplicáveis que possuem valor e não estão em <code>NOT_CONSOLIDATED</code>. Uma dimensão legitimamente <code>NOT_APPLICABLE</code> sai do denominador e não recebe zero.</p><div class='metric-grid'>{_metric('Versão do scoring', SCORING_VERSION)}{_metric('Agregação', OVERALL_AGGREGATION_VERSION)}{_metric('Coverage mínima para consolidar', f'{MIN_OVERALL_COVERAGE*100:.0f}%')}{_metric('Confidence para consolidar', 'HIGH ou MEDIUM')}{_metric('Coverage mínima para parcial', f'{MIN_PARTIAL_COVERAGE*100:.0f}%')}</div><div class='notice'><strong>Separação metodológica:</strong> Lighthouse, Core Web Vitals, Accessibility e Synthetic Apdex não entram no SARI-001. Falhas ou indisponibilidade dessas medições externas não reduzem o Overall.</div></section>
<section class='panel'><h2>Relação com SCORE-GEO-003</h2><p>O SCORE-GEO-003 permanece um método histórico calibrado e uma ferramenta de validação empírica. Seu Overall dependia de um model artifact <code>VALIDATED</code>, o que exigia um dataset multi-domínio e tornava uma auditoria individual incapaz de produzir Overall consolidado sem infraestrutura de calibração prévia.</p><p>O SCORE-GEO-004 remove essa dependência operacional sem afirmar validação estatística inexistente. A calibração empírica pode continuar sendo executada separadamente para pesquisa, benchmarking e futuras revisões metodológicas; ela não altera silenciosamente o score 004.</p></section>
<section class='panel'><h2>Quando o Overall fica consolidado</h2><p>O estado <code>CONSOLIDATED</code> exige todas as dimensões aplicáveis materializadas, nenhuma dimensão aplicável em <code>NOT_CONSOLIDATED</code>, Coverage média de pelo menos {MIN_OVERALL_COVERAGE*100:.0f}% e menor Confidence entre as dimensões igual a <code>MEDIUM</code> ou <code>HIGH</code>.</p><p>Se existe valor calculável, mas a evidência não alcança esse gate, o resultado pode ser <code>PARTIAL</code>. Estados insuficientes nunca são convertidos em zero.</p></section>
<section class='panel'><h2>Contrato do arquivo</h2><p><code>{REPORT_FILE}</code> é o endereço canônico estável desta página. A versão metodológica pertence aos dados persistidos e ao conteúdo, não ao nome do arquivo. <code>{LEGACY_REPORT_FILE}</code> é mantido apenas como alias de compatibilidade para links gerados durante a vigência inicial do SCORE-GEO-004.</p></section>
<footer class='footer'>{SCORING_VERSION} é uma metodologia proprietária, versionada e auditável do RASAi. Não garante ranking, tráfego, conversão ou citação futura.</footer></main></body></html>\n"""
    path = report_dir / REPORT_FILE
    path.write_text(html, encoding="utf-8", newline="\n")
    _write_legacy_alias(report_dir)
    return path


def _write_legacy_alias(report_dir: Path) -> Path:
    """Keep old external links working without making the versioned path canonical."""
    alias = report_dir / LEGACY_REPORT_FILE
    html = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta http-equiv='refresh' content='0; url={REPORT_FILE}'><link rel='canonical' href='{REPORT_FILE}'><title>Metodologia de scoring - compatibilidade</title></head><body><main><p>Este endereço foi substituído por <a href='{REPORT_FILE}'>{REPORT_FILE}</a>. A versão vigente é exibida na página canônica e persistida em audit.db.</p></main></body></html>\n"""
    alias.write_text(html, encoding="utf-8", newline="\n")
    return alias


def _scores(audit_id: str, workspace: AuditWorkspace) -> list[sqlite3.Row]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        return list(
            connection.execute(
                "SELECT device,value,coverage,confidence,consolidation_status,limitations FROM scores WHERE audit_id=? AND dimension='OVERALL_READINESS' AND scoring_version=? ORDER BY device,calculated_at",
                (audit_id, SCORING_VERSION),
            ).fetchall()
        )
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()


def _score_row(row: sqlite3.Row) -> str:
    value = "Indisponível" if row["value"] is None else f"{float(row['value']):.1f}/100"
    return (
        "<tr>"
        f"<td>{escape(str(row['device']))}</td>"
        f"<td>{escape(value)}</td>"
        f"<td>{float(row['coverage'])*100:.1f}%</td>"
        f"<td>{escape(str(row['confidence']))}</td>"
        f"<td>{escape(str(row['consolidation_status']))}</td>"
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
        return "Overall determinístico consolidado pelos gates de Coverage e Confidence."
    if status == "PARTIAL":
        return "Overall calculado, mas a força da medição ainda não alcança o gate de consolidação."
    return "Overall não consolidado; consulte Coverage, Confidence e limitações das dimensões."


def _metric(label: str, value: str) -> str:
    return f"<div class='metric'><small>{escape(label)}</small><strong>{escape(value)}</strong></div>"
