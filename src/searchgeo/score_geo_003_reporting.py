"""Concise HTML projection for SCORE-GEO-003 methodology and calibration state."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sqlite3

from searchgeo import report_navigation
from searchgeo.persistence import AuditWorkspace
from searchgeo.score_geo_003 import load_model_for_workspace, resolve_model_path
from searchgeo.score_geo_003_calibration import (
    MIN_DISTINCT_DAYS, MIN_DOMAINS, MIN_ENGINES, MIN_OBSERVATIONS,
    MIN_QUERIES_PER_DOMAIN, MIN_REPETITIONS, MIN_VALIDATION_AUC,
    MIN_VALIDATION_DOMAINS,
)

REPORT_FILE = "score-geo-003.html"


def register_navigation() -> None:
    if any(filename == REPORT_FILE for _label, filename in report_navigation.NAV_ITEMS):
        return
    items = list(report_navigation.NAV_ITEMS)
    pos = next((i + 1 for i, item in enumerate(items) if item[1] == "readiness.html"), 2)
    items.insert(pos, ("SCORE-GEO-003", REPORT_FILE))
    report_navigation.NAV_ITEMS = tuple(items)


def write_score_geo_003_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    register_navigation()
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    model = load_model_for_workspace(workspace.root, require_validated=False)
    nav = report_navigation.render_report_navigation(report_dir, REPORT_FILE)
    model_path = resolve_model_path(workspace.root)
    if model is None:
        model_html = (
            "<div class='notice warn'><strong>Modelo calibrado VALIDATED não disponível.</strong> "
            "SCORE-GEO-003 permanece o método padrão, porém o Overall fica não consolidado por contrato. "
            "Isso não depende da ordem de geração dos demais relatórios: a consolidação exige um artifact de calibração VALIDATED.</div>"
            + _metric("Artifact esperado", str(model_path))
        )
    else:
        model_html = "".join((
            _metric("Modelo", model.model_version), _metric("Dataset", model.dataset_version),
            _metric("Estado", model.status), _metric("Confidence da calibração", model.calibration_confidence),
            _metric("Engines", ", ".join(model.engines)), _metric("AUC validação", _num(model.validation.get("auc"))),
            _metric("Brier validação", _num(model.validation.get("brier"))),
        ))
        if not model.validated:
            model_html += "<div class='notice warn'>Artifact EXPERIMENTAL: não consolida o Overall até promoção para VALIDATED.</div>"
    scores = _scores(audit_id, workspace)
    score_rows = "".join(_score_row(row) for row in scores) or "<tr><td colspan='6'>Overall não persistido.</td></tr>"
    gates = (
        f"{MIN_DOMAINS} domínios; {MIN_VALIDATION_DOMAINS} no holdout; {MIN_ENGINES} engines; "
        f"{MIN_QUERIES_PER_DOMAIN} queries/domínio; {MIN_REPETITIONS} repetições/query/engine; "
        f"{MIN_DISTINCT_DAYS} dias distintos de observação por domínio; {MIN_OBSERVATIONS} observações; "
        f"AUC ≥ {MIN_VALIDATION_AUC:.2f}; Brier melhor que baseline."
    )
    html = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>SCORE-GEO-003</title><link rel='stylesheet' href='css/site.css'></head><body>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>RASAi · método de pontuação</div><h1>SCORE-GEO-003</h1><p class='lead'>Método padrão do SARI-001. As dimensões permanecem determinísticas; o Overall usa regressão logística regularizada calibrada contra presença observada de citação. Sem calibração validada, nenhum Overall é fabricado.</p></header>
<section class='panel'><h2>Estado da calibração</h2><div class='metric-grid'>{model_html}</div><div class='table-wrap'><table><thead><tr><th>Device</th><th>Overall</th><th>Coverage</th><th>Confidence</th><th>Consolidação</th><th>Motivo / rastreabilidade</th></tr></thead><tbody>{score_rows}</tbody></table></div></section>
<section class='panel'><h2>Contrato</h2><p><strong>Dimensão:</strong> <code>Σ(weight × result_factor) / Σ(weight evaluated) × 100</code>. <strong>Overall:</strong> <code>100 × sigmoid(β0 + Σ βi × feature_i)</code>. Coeficientes, imputações, features e gates não são configuráveis por auditoria.</p><p><strong>Promotion gate mínimo:</strong> {escape(gates)}</p><p>O split de validação é por domínio, evitando leakage entre queries do mesmo site. A cobertura temporal mínima impede promover um artifact sustentado apenas por repetições concentradas em um único dia. Auditorias SCORE-GEO-002 históricas não são recalculadas.</p><p><strong>Ordem de execução:</strong> o cálculo SCORE-GEO-003 é persistido na etapa de scoring, antes das recomendações. Esta página HTML é materializada no fechamento do site de relatório, depois dos demais enriquecimentos, para refletir o estado final persistido sem alterar a matemática do score.</p></section>
<section class='panel'><h2>Operação</h2><p><code>rasai scoring calibrate --dataset-version GEO-CAL-001</code></p><p><code>rasai scoring inspect</code></p></section>
<footer class='footer'>SCORE-GEO-003 mede associação observacional; não prova causalidade nem garante citação futura.</footer></main></body></html>\n"""
    path = report_dir / REPORT_FILE
    path.write_text(html, encoding="utf-8", newline="\n")
    return path


def _scores(audit_id: str, workspace: AuditWorkspace) -> list[sqlite3.Row]:
    con = sqlite3.connect(workspace.database); con.row_factory = sqlite3.Row
    try:
        return list(con.execute("SELECT device,value,coverage,confidence,consolidation_status,limitations FROM scores WHERE audit_id=? AND dimension='OVERALL_READINESS' ORDER BY device,calculated_at", (audit_id,)).fetchall())
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def _score_row(row: sqlite3.Row) -> str:
    value = "Não consolidado" if row["value"] is None else f"{float(row['value']):.1f}"
    reason = _score_reason(row)
    return f"<tr><td>{escape(str(row['device']))}</td><td>{escape(value)}</td><td>{float(row['coverage'])*100:.1f}%</td><td>{escape(str(row['confidence']))}</td><td>{escape(str(row['consolidation_status']))}</td><td>{escape(reason)}</td></tr>"


def _score_reason(row: sqlite3.Row) -> str:
    try:
        raw = json.loads(str(row["limitations"] or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        raw = []
    limitations = [str(item) for item in raw if item]
    if any(item == "CALIBRATION_MODEL_UNAVAILABLE:SCORE-GEO-003" for item in limitations):
        return "Modelo de calibração VALIDATED não disponível; Overall não pode ser consolidado."
    missing = [item.split(":", 1)[1] for item in limitations if item.startswith("DIMENSION_NOT_CONSOLIDATED:")]
    if missing:
        return "Dimensão(ões) não consolidada(s): " + ", ".join(missing)
    if row["value"] is not None:
        model = next((item.split(":", 1)[1] for item in limitations if item.startswith("CALIBRATION_MODEL:")), None)
        dataset = next((item.split(":", 1)[1] for item in limitations if item.startswith("CALIBRATION_DATASET:")), None)
        if model or dataset:
            return "Overall calculado com " + "; ".join(item for item in (f"modelo {model}" if model else "", f"dataset {dataset}" if dataset else "") if item)
        return "Overall consolidado a partir do estado persistido."
    return "Overall não consolidado; consulte limitações das dimensões e estado da calibração."


def _metric(label: str, value: str) -> str:
    return f"<div class='metric'><small>{escape(label)}</small><strong>{escape(value)}</strong></div>"


def _num(value: object) -> str:
    try: return f"{float(value):.4f}"
    except (TypeError, ValueError): return "—"
