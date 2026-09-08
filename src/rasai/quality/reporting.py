"""HTML reporting for RASAi Quality & Verification."""
from __future__ import annotations

from html import escape
import hashlib
from pathlib import Path
from typing import Any

from rasai import report_navigation
from rasai.report_presentation import humanize_report_html
from rasai.report_registry import install as install_report_registry
from .analysis import QualityBundle, analyze_quality
from .content_controls import analyze_content_controls
from .timeline import TimelineBundle
from .verification import VerificationBundle

QUALITY_FILE = "quality.html"
_INACTIVE_FINDING_STATES = frozenset({"RESOLVED", "CLOSED", "DISMISSED"})


def write_quality_report(audit_workspace: str | Path) -> Path:
    install_report_registry()
    workspace = Path(audit_workspace)
    report_dir = workspace / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    bundle = analyze_quality(workspace)
    controls = analyze_content_controls(workspace)
    path = report_dir / QUALITY_FILE
    nav = report_navigation.render_report_navigation(report_dir, QUALITY_FILE)
    confidence_counts = _count(item.evidence_confidence for item in bundle.finding_assessments)
    actionable = _actionable_findings(bundle)
    priority_counts = _count(item.priority_class for item in actionable)
    top_priorities = actionable[:10]
    rec_attention = sum(
        item.status not in {"SUPPORTED_BY_PERSISTED_EVIDENCE", "SUPPORTED_BY_GROUP"}
        for item in bundle.recommendation_assessments
    )
    body = f"""
<header class='hero'>
  <div class='eyebrow'>RASAi Quality · derivado · non-scoring</div>
  <h1>Qualidade da auditoria e decisão</h1>
  <p class='lead'>Avalia a qualidade da própria evidência RASAi, prioriza findings acionáveis e valida a coerência das recomendações sem alterar SARI-001/SCORE-GEO-004.</p>
  <div class='metric-grid'>
    {_metric('Audit health', bundle.health_status)}
    {_metric('Findings', len(bundle.finding_assessments))}
    {_metric('Findings acionáveis', len(actionable))}
    {_metric('Evidence HIGH', confidence_counts.get('HIGH', 0))}
    {_metric('Prioridades P0/P1 acionáveis', priority_counts.get('P0', 0) + priority_counts.get('P1', 0))}
    {_metric('Recomendações a revisar', rec_attention)}
    {_metric('Controles de conteúdo', len(controls))}
  </div>
</header>
<section class='panel notice'><h2>Fronteira metodológica</h2><p><strong>Quality não é um novo score de readiness.</strong> Audit Health descreve a qualidade/completude da coleta; Evidence Confidence descreve a força da evidência de cada finding; Operational Priority é uma heurística de decisão independente; nenhum deles recalcula SARI.</p></section>
<section class='panel'><div class='kicker'>Audit Health</div><h2>Qualidade da própria auditoria</h2><div class='table-wrap'><table><thead><tr><th>Status</th><th>Sev.</th><th>Código</th><th>Verificação</th><th>Detalhe</th></tr></thead><tbody>{''.join(_health_row(x) for x in bundle.health_checks) or '<tr><td colspan=5>Sem verificações.</td></tr>'}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Executive decision</div><h2>Top prioridades operacionais acionáveis</h2><p>Somente findings não resolvidos/fechados/dispensados entram nesta lista. A prioridade combina severidade, abrangência, confiança da evidência e esforço estimado; orienta ordem de trabalho e não altera scoring.</p><div class='table-wrap'><table><thead><tr><th>Prior.</th><th>Score</th><th>Regra</th><th>Sev.</th><th>Confidence</th><th>Escopo</th><th>Esforço</th><th>URL</th><th>Título</th></tr></thead><tbody>{''.join(_finding_row(x) for x in top_priorities) or '<tr><td colspan=9>Nenhum finding acionável.</td></tr>'}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Evidence Confidence</div><h2>Confiança por finding</h2><p>Esta tabela preserva também findings históricos/resolvidos para rastreabilidade.</p><div class='table-wrap'><table><thead><tr><th>Status</th><th>Prior.</th><th>Regra</th><th>Sev.</th><th>Confidence</th><th>Proveniência</th><th>Device</th><th>URL</th><th>Razões</th></tr></thead><tbody>{''.join(_confidence_row(x) for x in sorted(bundle.finding_assessments, key=lambda i: (-i.operational_priority, i.rule_id, i.finding_id))) or '<tr><td colspan=9>Nenhum finding.</td></tr>'}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Coverage Map</div><h2>URL × domínio de evidência</h2><div class='table-wrap'><table><thead><tr><th>URL</th><th>Device</th><th>Technical</th><th>Rendering</th><th>Semantic/entity</th><th>Answer/evidence/intent</th><th>Governance</th></tr></thead><tbody>{''.join(_coverage_row(x) for x in bundle.coverage_map) or '<tr><td colspan=7>Sem cobertura por URL.</td></tr>'}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Search & AI content controls</div><h2>Controles de snippet e uso direto</h2><p>Diretivas restritivas são decisões do publisher e não penalidades. O RASAi apenas registra sua presença para interpretar corretamente Search/GenAI observados.</p><div class='table-wrap'><table><thead><tr><th>URL</th><th>Device</th><th>Meta robots</th><th>X-Robots-Tag</th><th>nosnippet</th><th>max-snippet</th><th>data-nosnippet</th><th>Interpretação</th></tr></thead><tbody>{''.join(_control_row(x) for x in controls) or '<tr><td colspan=8>Sem snapshots para avaliar.</td></tr>'}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Recommendation Validation</div><h2>Coerência das recomendações persistidas</h2><p>Esta validação verifica referência, estado e confiança contra a evidência atual; não substitui revisão humana do conteúdo da recomendação.</p><div class='table-wrap'><table><thead><tr><th>Status</th><th>ID</th><th>Confidence</th><th>Prior.</th><th>Recomendação</th><th>Motivo</th></tr></thead><tbody>{''.join(_rec_row(x) for x in bundle.recommendation_assessments) or '<tr><td colspan=6>Sem recomendações persistidas.</td></tr>'}</tbody></table></div></section>
<footer class='footer'>Métodos: {escape(' · '.join(f'{k}={v}' for k, v in bundle.methodology.items()))}</footer>
"""
    path.write_text(_shell(nav, body), encoding="utf-8", newline="\n")
    report_navigation.normalize_report_navigation(report_dir)
    return path


def write_verification_report(
    audits_root: str | Path,
    bundle: VerificationBundle,
    *,
    report_root: str | Path | None = None,
) -> Path:
    digest = hashlib.sha256(f"{bundle.baseline_audit_id}|{bundle.current_audit_id}".encode()).hexdigest()[:12].upper()
    root = Path(report_root) if report_root else Path(audits_root) / "verification"
    directory = root / f"VER-{digest}"
    directory.mkdir(parents=True, exist_ok=True)
    rows = "".join(
        f"<tr><td>{escape(x.status)}</td><td>{escape(x.severity)}</td><td class='mono'>{escape(x.rule_id)}</td><td>{escape(x.device or '-')}</td><td class='mono'>{escape(x.url or '-')}</td><td>{escape(str(x.before))}</td><td>{escape(str(x.after))}</td><td>{escape(x.reason)}</td></tr>"
        for x in bundle.items
    ) or "<tr><td colspan='8'>Nenhum finding baseline elegível neste escopo.</td></tr>"
    limits = "".join(f"<li>{escape(item)}</li>" for item in bundle.limitations)
    body = f"""<header class='hero'><div class='eyebrow'>RASAi Fix Verification</div><h1>Validação incremental de correções</h1><p>{escape(bundle.baseline_audit_id)} → {escape(bundle.current_audit_id)}</p><div class='metric-grid'>{''.join(_metric(k, v) for k, v in sorted(bundle.counts.items()))}</div></header><section class='panel'><h2>Resultados</h2><div class='table-wrap'><table><thead><tr><th>Status</th><th>Sev.</th><th>Regra</th><th>Device</th><th>URL</th><th>Antes</th><th>Depois</th><th>Interpretação</th></tr></thead><tbody>{rows}</tbody></table></div></section><section class='panel'><h2>Limitações</h2><ul>{limits}</ul></section>"""
    path = directory / "report.html"
    path.write_text(_shell("", body), encoding="utf-8", newline="\n")
    return path


def write_timeline_report(
    audits_root: str | Path,
    bundle: TimelineBundle,
    *,
    report_root: str | Path | None = None,
) -> Path:
    material = f"{bundle.domain_filter or ''}|{bundle.url_filter or ''}"
    digest = hashlib.sha256(material.encode()).hexdigest()[:12].upper()
    root = Path(report_root) if report_root else Path(audits_root) / "quality"
    directory = root / f"TIMELINE-{digest}"
    directory.mkdir(parents=True, exist_ok=True)
    rows = "".join(_timeline_row(x) for x in bundle.points) or "<tr><td colspan='9'>Nenhum AUD compatível com os filtros.</td></tr>"
    skipped = "".join(f"<li>{escape(item)}</li>" for item in bundle.skipped) or "<li>Nenhum workspace ignorado.</li>"
    body = f"""<header class='hero'><div class='eyebrow'>RASAi Evidence Timeline</div><h1>Linha do tempo de evidência</h1><p>Domínio: {escape(bundle.domain_filter or 'todos')} · URL: {escape(bundle.url_filter or 'todas')}</p><div class='metric-grid'>{_metric('AUDs', len(bundle.points))}{_metric('Ignorados', len(bundle.skipped))}</div></header><section class='panel'><h2>Histórico</h2><div class='table-wrap'><table><thead><tr><th>Data</th><th>AUD</th><th>Versão</th><th>Ruleset</th><th>Scoring</th><th>URLs</th><th>FAIL</th><th>WARNING</th><th>Dimensões/estado</th></tr></thead><tbody>{rows}</tbody></table></div></section><section class='panel'><h2>Workspaces ignorados</h2><ul>{skipped}</ul></section>"""
    path = directory / "report.html"
    path.write_text(_shell("", body), encoding="utf-8", newline="\n")
    return path


def _actionable_findings(bundle: QualityBundle) -> tuple[Any, ...]:
    return tuple(
        sorted(
            (
                item
                for item in bundle.finding_assessments
                if str(item.status).upper() not in _INACTIVE_FINDING_STATES
            ),
            key=lambda item: (-item.operational_priority, item.rule_id, item.finding_id),
        )
    )


def _health_row(x: Any) -> str:
    return f"<tr><td>{escape(x.status)}</td><td>{escape(x.severity)}</td><td class='mono'>{escape(x.code)}</td><td>{escape(x.title)}</td><td>{escape(x.detail)}</td></tr>"


def _finding_row(x: Any) -> str:
    return f"<tr><td>{escape(x.priority_class)}</td><td>{x.operational_priority:.2f}</td><td class='mono'>{escape(x.rule_id)}</td><td>{escape(x.severity)}</td><td>{escape(x.evidence_confidence)}</td><td>{x.scope_count}</td><td>{escape(x.effort)}</td><td class='mono'>{escape(x.url or '-')}</td><td>{escape(x.title)}</td></tr>"


def _confidence_row(x: Any) -> str:
    return f"<tr><td>{escape(x.status)}</td><td>{escape(x.priority_class)}</td><td class='mono'>{escape(x.rule_id)}</td><td>{escape(x.severity)}</td><td>{escape(x.evidence_confidence)}</td><td>{escape(x.provenance)}</td><td>{escape(x.device or '-')}</td><td class='mono'>{escape(x.url or '-')}</td><td>{escape(', '.join(x.confidence_reasons))}</td></tr>"


def _coverage_row(x: dict[str, Any]) -> str:
    fields = (
        x.get("url"), x.get("device"), x.get("TECHNICAL_ACCESS"), x.get("CONTENT_RENDERING"),
        x.get("SEMANTIC_ENTITY"), x.get("ANSWER_EVIDENCE_INTENT"), x.get("GOVERNANCE"),
    )
    return "<tr>" + "".join(
        f"<td{(' class=mono' if index == 0 else '')}>{escape(str(value or '-'))}</td>"
        for index, value in enumerate(fields)
    ) + "</tr>"


def _control_row(x: Any) -> str:
    return f"<tr><td class='mono'>{escape(x.url)}</td><td>{escape(x.device)}</td><td>{escape(x.meta_robots or '-')}</td><td>{escape(', '.join(x.x_robots_tag) or '-')}</td><td>{'SIM' if x.nosnippet else 'NÃO'}</td><td>{escape(str(x.max_snippet) if x.max_snippet is not None else '-')}</td><td>{x.data_nosnippet_count}</td><td>{escape(x.interpretation)}</td></tr>"


def _rec_row(x: Any) -> str:
    return f"<tr><td>{escape(x.status)}</td><td class='mono'>{escape(x.recommendation_id)}</td><td>{escape(x.confidence or '-')}</td><td>{escape(x.priority_class or '-')}</td><td>{escape(x.title)}</td><td>{escape(x.reason)}</td></tr>"


def _timeline_row(x: Any) -> str:
    dimensions = "; ".join(f"{key}={value:.1f}" for key, value in sorted(x.dimension_values.items())[:12])
    states = "; ".join(f"{key}={value}" for key, value in sorted(x.page_states.items())[:8])
    detail = " | ".join(value for value in (dimensions, states) if value) or "-"
    return f"<tr><td>{escape(x.event_time)}</td><td class='mono'>{escape(x.audit_id)}</td><td>{escape(x.auditor_version)}</td><td>{escape(x.ruleset_version)}</td><td>{escape(', '.join(x.scoring_versions) or '-')}</td><td>{x.url_count}</td><td>{x.fail_count}</td><td>{x.warning_count}</td><td>{escape(detail)}</td></tr>"


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>"


def _count(values: Any) -> dict[str, int]:
    output: dict[str, int] = {}
    for value in values:
        output[str(value)] = output.get(str(value), 0) + 1
    return output


def _shell(nav: str, body: str) -> str:
    html = f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>RASAi Quality</title><style>{_CSS}</style></head><body>{nav}<main>{body}</main></body></html>"
    return humanize_report_html(html, page_name="quality.html")


_CSS = """body{margin:0;background:#f5f7fa;color:#273449;font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1500px;margin:auto;padding:32px}.hero,.panel{background:#fff;border:1px solid #e1e6ec;border-radius:8px;padding:24px;margin-bottom:16px}.eyebrow,.kicker{font-size:12px;text-transform:uppercase;color:#6d7786;letter-spacing:.08em}.lead{max-width:1000px}.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:18px}.metric{background:#f7f8fb;border-radius:7px;padding:12px}.metric span{display:block;color:#667085}.metric strong{font-size:20px}.table-wrap{overflow:auto;border:1px solid #e1e6ec;border-radius:6px}table{width:100%;border-collapse:collapse;min-width:900px}th,td{padding:9px 10px;border-bottom:1px solid #e1e6ec;text-align:left;vertical-align:top}th{background:#f7f8fb}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px}.notice{background:#fbfcfe}.footer{color:#667085;padding:12px}@media(max-width:700px){main{padding:16px}}"""
