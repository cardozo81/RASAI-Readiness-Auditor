"""Static HTML report for RASAi audit-to-audit monitoring."""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import hashlib
import json
from pathlib import Path
from typing import Any

from rasai.report_presentation import humanize_report_html

from .compare import evaluate_release_gate
from .models import ChangeEvent, ComparisonResult, MonitoringReportResult

FORMAT_VERSION = "RASAI-MONITOR-001"


def write_monitoring_report(
    audits_root: str | Path,
    result: ComparisonResult,
    *,
    report_root: str | Path | None = None,
) -> MonitoringReportResult:
    root = Path(audits_root)
    output_root = Path(report_root) if report_root is not None else root / "monitoring"
    material = json.dumps(
        {
            "format": FORMAT_VERSION,
            "baseline": result.baseline.audit_id,
            "current": result.current.audit_id,
            "events": [_event_dict(event) for event in result.events],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    report_dir = output_root / f"MON-{digest[:16].upper()}"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "report.html"
    manifest_path = report_dir / "manifest.json"
    gate = evaluate_release_gate(result)
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "format_version": FORMAT_VERSION,
        "generated_at": generated_at,
        "baseline_audit_id": result.baseline.audit_id,
        "current_audit_id": result.current.audit_id,
        "comparable": result.comparable,
        "compatibility_notes": list(result.compatibility_notes),
        "counts": result.counts,
        "material_counts": result.material_counts,
        "release_gate": {
            "passed": gate.passed,
            "reason": gate.reason,
            "deterministic_only": gate.policy.deterministic_only,
            "blocking_keys": [event.key for event in gate.blocking_events],
        },
        "events": [_event_dict(event) for event in result.events],
        "source_policy": "AUD-*/audit.db opened read-only; no source database migration or mutation",
        "causality_policy": "temporal/change association only; causality is not inferred from sequence alone",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(_html(result, gate.passed, gate.reason, generated_at), encoding="utf-8", newline="\n")
    return MonitoringReportResult(report_dir, report_path, manifest_path)


def _event_dict(event: ChangeEvent) -> dict[str, Any]:
    return {
        "key": event.key,
        "domain": event.domain,
        "label": event.label,
        "status": event.status,
        "before": event.before,
        "after": event.after,
        "severity": event.severity,
        "material": event.material,
        "device": event.device,
        "url": event.url,
        "rule_id": event.rule_id,
        "unit": event.unit,
        "delta": event.delta,
        "delta_percent": event.delta_percent,
        "reason": event.reason,
    }


def _html(result: ComparisonResult, gate_passed: bool, gate_reason: str, generated_at: str) -> str:
    regressions = sorted(
        result.regressions,
        key=lambda event: (-_severity(event.severity), event.domain, event.url or "", event.label),
    )
    improvements = sorted(result.improvements, key=lambda event: (event.domain, event.url or "", event.label))
    changes = [event for event in result.events if event.status in {"CHANGED", "NEW", "DATA_UNAVAILABLE", "NOT_COMPARABLE"} and event.material]
    compatibility = "".join(f"<li>{escape(note)}</li>" for note in result.compatibility_notes) or "<li>Nenhuma limitação adicional de comparabilidade detectada.</li>"
    regression_rows = "".join(_event_row(event) for event in regressions) or "<tr><td colspan='9'>Nenhuma regressão material detectada.</td></tr>"
    improvement_rows = "".join(_event_row(event) for event in improvements) or "<tr><td colspan='9'>Nenhuma melhoria material detectada.</td></tr>"
    change_rows = "".join(_event_row(event) for event in changes) or "<tr><td colspan='9'>Nenhuma mudança material não-direcional.</td></tr>"
    material_total = sum(result.material_counts.values())
    status_class = "good" if gate_passed else "bad"
    html = f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>RASAi Monitor · {escape(result.baseline.audit_id)} → {escape(result.current.audit_id)}</title>
<style>{_CSS}</style></head><body>
<main>
<header class='hero'>
  <div class='eyebrow'>RASAi Monitor · {FORMAT_VERSION}</div>
  <h1>Regressão e mudança entre auditorias</h1>
  <p>Comparação derivada e read-only. O relatório detecta mudanças observáveis; não atribui causalidade a deploys, conteúdo ou mecanismos externos sem evidência adicional.</p>
  <div class='metrics'>
    {_metric('Baseline', result.baseline.audit_id)}
    {_metric('Atual', result.current.audit_id)}
    {_metric('Mudanças materiais', material_total)}
    {_metric('Regressões', len(regressions))}
    {_metric('Melhorias', len(improvements))}
    {_metric('Release gate', 'PASS' if gate_passed else 'FAIL', status_class)}
  </div>
</header>
<section class='panel {status_class}'><h2>Release gate determinístico</h2><p><strong>{escape(gate_reason)}</strong>. Por padrão, regras semânticas dependentes de IA não bloqueiam release. Performance e sinais técnicos continuam observáveis separadamente.</p></section>
<section class='panel'><h2>Comparabilidade</h2><ul>{compatibility}</ul><p><strong>Baseline:</strong> {escape(result.baseline.event_time)} · ruleset {escape(result.baseline.ruleset_version)} · scoring {escape(', '.join(result.baseline.scoring_versions) or '-')}</p><p><strong>Atual:</strong> {escape(result.current.event_time)} · ruleset {escape(result.current.ruleset_version)} · scoring {escape(', '.join(result.current.scoring_versions) or '-')}</p></section>
<section class='panel'><h2>Regressões materiais</h2>{_table(regression_rows)}</section>
<section class='panel'><h2>Melhorias / resoluções</h2>{_table(improvement_rows)}</section>
<section class='panel'><h2>Mudanças materiais sem direção comprovada</h2><p>Ex.: canonical alterado é mudança relevante, mas não é chamado de regressão sem regra/evidência que demonstre piora.</p>{_table(change_rows)}</section>
<section class='panel'><h2>Metodologia</h2><ul><li><code>UNKNOWN</code>, <code>ERROR</code> e <code>NOT_APPLICABLE</code> não viram FAIL.</li><li>SCOREs de versões metodológicas sem sobreposição ficam <code>NOT_COMPARABLE</code>.</li><li>URL universes muito diferentes geram limitação explícita.</li><li>Dados ausentes no audit atual ficam <code>DATA_UNAVAILABLE</code>, não <code>RESOLVED</code>.</li><li>Thresholds numéricos apenas filtram materialidade; não redefinem métricas oficiais.</li></ul></section>
<footer>Gerado em {escape(generated_at)} · RASAi Monitor · fonte: audit.db read-only.</footer>
</main></body></html>"""
    return humanize_report_html(html, page_name="monitoring-report.html")


def _table(rows: str) -> str:
    return f"<div class='table-wrap'><table><thead><tr><th>Status</th><th>Severidade</th><th>Domínio</th><th>Regra/Métrica</th><th>Device</th><th>URL</th><th>Antes</th><th>Depois</th><th>Razão</th></tr></thead><tbody>{rows}</tbody></table></div>"


def _event_row(event: ChangeEvent) -> str:
    return "".join((
        "<tr>",
        f"<td><span class='badge {escape(event.status.casefold())}'>{escape(event.status)}</span></td>",
        f"<td>{escape(event.severity)}</td>",
        f"<td>{escape(event.domain)}</td>",
        f"<td>{escape(event.rule_id or event.label)}</td>",
        f"<td>{escape(event.device or '-')}</td>",
        f"<td class='mono'>{escape(event.url or '-')}</td>",
        f"<td>{escape(_value(event.before, event.unit))}</td>",
        f"<td>{escape(_value(event.after, event.unit))}</td>",
        f"<td>{escape(event.reason or '-')}</td>",
        "</tr>",
    ))


def _value(value: Any, unit: str | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    return f"{text} {unit}" if unit else text


def _metric(label: str, value: Any, css: str = "") -> str:
    return f"<div class='metric {css}'><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>"


def _severity(value: str) -> int:
    return {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}.get(value.upper(), 0)


_CSS = """
:root{--bg:#f5f7fa;--surface:#fff;--ink:#273449;--muted:#6d7786;--line:#e1e6ec;--good:#eaf5ee;--bad:#faecec;--warn:#faf3e7;--blue:#eef2fb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1500px;margin:auto;padding:34px}.hero,.panel{background:var(--surface);border:1px solid var(--line);border-radius:7px;padding:24px;margin-bottom:16px}.hero{box-shadow:0 8px 24px rgba(39,52,73,.05)}h1{font-size:30px;margin:.2rem 0 1rem}h2{font-size:20px;margin-top:0}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:9px;margin-top:18px}.metric{background:#f7f8fb;border-radius:6px;padding:11px}.metric span{display:block;color:var(--muted);font-size:12px}.metric strong{font-size:16px}.metric.good,.panel.good{background:var(--good)}.metric.bad,.panel.bad{background:var(--bad)}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:6px}table{width:100%;border-collapse:collapse;min-width:980px}th,td{padding:9px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{background:#f7f8fb;position:sticky;top:0}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px}.badge{display:inline-block;border-radius:999px;padding:2px 8px;background:var(--blue);font-size:11px;font-weight:700}.badge.regressed{background:var(--bad)}.badge.improved,.badge.resolved{background:var(--good)}.badge.data_unavailable,.badge.not_comparable{background:var(--warn)}code{background:#f1f3f6;padding:1px 4px;border-radius:4px}footer{color:var(--muted);padding:12px 4px 24px}@media(max-width:700px){main{padding:16px}.hero,.panel{padding:17px}}
"""
