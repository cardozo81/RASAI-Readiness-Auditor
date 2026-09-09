"""Standalone HTML and manifest projection for Search Intelligence History."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import hashlib
import json
from pathlib import Path
from typing import Any

from rasai.report_presentation import humanize_report_html
from rasai.score_geo_004 import SCORING_VERSION

from .history import SearchHistoryComparison, SearchHistoryEvent

FORMAT_VERSION = "RASAI-SEARCH-HISTORY-REPORT-001"


@dataclass(frozen=True, slots=True)
class SearchHistoryReportResult:
    report_dir: Path
    report_path: Path
    manifest_path: Path


def _event_dict(event: SearchHistoryEvent) -> dict[str, Any]:
    return {
        "context_key": event.context_key,
        "query": event.query,
        "status": event.status,
        "label": event.label,
        "before": event.before,
        "after": event.after,
        "delta": event.delta,
        "unit": event.unit,
        "note": event.note,
    }


def write_search_history_report(
    audits_root: str | Path,
    result: SearchHistoryComparison,
    *,
    report_root: str | Path | None = None,
    milestone_id: str | None = None,
    baseline_mode: str | None = None,
) -> SearchHistoryReportResult:
    """Materialize a deterministic standalone report without mutating either AUD."""
    root = Path(audits_root)
    output_root = Path(report_root) if report_root is not None else root / "search-history"
    material_payload = {
        "format": FORMAT_VERSION,
        "method": result.method,
        "baseline": result.baseline_audit_id,
        "current": result.current_audit_id,
        "milestone_id": milestone_id,
        "baseline_mode": baseline_mode,
        "events": [_event_dict(event) for event in result.events],
        "compatibility_notes": list(result.compatibility_notes),
    }
    material = json.dumps(
        material_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()
    report_dir = output_root / f"SH-{digest[:16].upper()}"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "report.html"
    manifest_path = report_dir / "manifest.json"
    generated_at = datetime.now(timezone.utc).isoformat()
    counts = Counter(event.status for event in result.events)
    manifest = {
        "format_version": FORMAT_VERSION,
        "generated_at": generated_at,
        "methodology": result.method,
        "baseline_audit_id": result.baseline_audit_id,
        "current_audit_id": result.current_audit_id,
        "milestone_id": milestone_id,
        "baseline_mode": baseline_mode,
        "comparable_contexts": result.comparable_contexts,
        "non_comparable_contexts": result.non_comparable_contexts,
        "compatibility_notes": list(result.compatibility_notes),
        "event_counts": dict(sorted(counts.items())),
        "events": [_event_dict(event) for event in result.events],
        "source_policy": "AUD-*/audit.db opened read-only; no Search/content/AI provider calls",
        "causality_policy": result.interpretation_policy,
        "scoring_boundary": f"Search History is non-scoring and does not modify SARI-001/{SCORING_VERSION}",
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        _html(result, generated_at, counts, milestone_id=milestone_id, baseline_mode=baseline_mode),
        encoding="utf-8",
        newline="\n",
    )
    return SearchHistoryReportResult(report_dir, report_path, manifest_path)


def _status_label(status: str) -> str:
    return {
        "POSITION_IMPROVED": "Posição melhorou",
        "POSITION_REGRESSED": "Posição piorou",
        "POSITION_UNCHANGED": "Posição estável",
        "ENTERED_OBSERVED_DEPTH": "Entrou na profundidade observada",
        "LEFT_OBSERVED_DEPTH": "Saiu da profundidade observada",
        "OBSERVED_DEPTH_STATE_UNCHANGED": "Estado de profundidade estável",
        "DOMAIN_STATUS_CHANGED": "Estado do domínio mudou",
        "CONTENT_SIGNAL_CHANGED": "Sinal determinístico mudou",
        "CONTENT_VOLUME_CHANGED": "Volume observado mudou",
        "STRUCTURED_DATA_CHANGED": "Dados estruturados mudaram",
        "DETERMINISTIC_GAP_ADDED": "Gap determinístico adicionado",
        "DETERMINISTIC_GAP_RESOLVED": "Gap determinístico resolvido",
        "NEW_CONTEXT": "Novo contexto",
        "MISSING_CURRENT_CONTEXT": "Contexto ausente no atual",
        "NOT_COMPARABLE": "Não comparável",
    }.get(status, status)


def _status_class(status: str) -> str:
    if status in {"POSITION_IMPROVED", "ENTERED_OBSERVED_DEPTH", "DETERMINISTIC_GAP_RESOLVED"}:
        return "good"
    if status in {"POSITION_REGRESSED", "LEFT_OBSERVED_DEPTH", "DETERMINISTIC_GAP_ADDED"}:
        return "bad"
    if status in {"NOT_COMPARABLE", "NEW_CONTEXT", "MISSING_CURRENT_CONTEXT"}:
        return "warn"
    return "neutral"


def _value(value: Any, unit: str | None = None) -> str:
    if value is None:
        return "—"
    if isinstance(value, (tuple, list)):
        text = ", ".join(str(item) for item in value) or "—"
    elif isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    elif isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    if not unit:
        return text
    unit_label = {"positions": "posições", "words": "palavras", "ratio": "proporção"}.get(unit, unit)
    return f"{text} {unit_label}"


def _delta(event: SearchHistoryEvent) -> str:
    if event.delta is None:
        return "—"
    prefix = "+" if event.delta > 0 else ""
    value = f"{event.delta:.4f}".rstrip("0").rstrip(".")
    unit = {"positions": "posições", "words": "palavras", "ratio": "proporção"}.get(event.unit or "", event.unit or "")
    return f"{prefix}{value} {unit}".strip()


def _event_row(event: SearchHistoryEvent) -> str:
    css = _status_class(event.status)
    return "".join((
        "<tr>",
        f"<td><span class='badge {css}'>{escape(_status_label(event.status))}</span></td>",
        f"<td>{escape(event.query)}</td>",
        f"<td>{escape(event.label)}</td>",
        f"<td>{escape(_value(event.before, event.unit))}</td>",
        f"<td>{escape(_value(event.after, event.unit))}</td>",
        f"<td>{escape(_delta(event))}</td>",
        f"<td>{escape(event.note or '—')}</td>",
        f"<td class='mono'>{escape(event.context_key)}</td>",
        "</tr>",
    ))


def _metric(label: str, value: Any, css: str = "") -> str:
    return f"<div class='metric {css}'><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>"


def _html(
    result: SearchHistoryComparison,
    generated_at: str,
    counts: Counter[str],
    *,
    milestone_id: str | None,
    baseline_mode: str | None,
) -> str:
    rows = "".join(_event_row(event) for event in result.events) or "<tr><td colspan='8'>Nenhum evento comparável materializado.</td></tr>"
    notes = "".join(f"<li>{escape(note)}</li>" for note in result.compatibility_notes) or "<li>Nenhuma limitação adicional de comparabilidade detectada.</li>"
    milestone = escape(milestone_id or "não informado")
    selection = escape(baseline_mode or "comparação direta")
    positive = counts.get("POSITION_IMPROVED", 0) + counts.get("ENTERED_OBSERVED_DEPTH", 0)
    negative = counts.get("POSITION_REGRESSED", 0) + counts.get("LEFT_OBSERVED_DEPTH", 0)
    html = f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>RASAi · Histórico de Search Intelligence</title><style>{_CSS}</style></head><body><main>
<header class='hero'>
  <div class='eyebrow'>Search Intelligence History · {escape(result.method)}</div>
  <h1>Evolução observada de Search Intelligence</h1>
  <p>Comparação determinística e read-only entre duas auditorias. Variações de posição, conteúdo e gaps são observações temporais; proximidade com deploy ou alteração de conteúdo não demonstra causalidade.</p>
  <div class='metrics'>
    {_metric('Baseline', result.baseline_audit_id)}
    {_metric('Atual', result.current_audit_id)}
    {_metric('Contextos comparáveis', result.comparable_contexts, 'good' if result.comparable_contexts else 'neutral')}
    {_metric('Não comparáveis', result.non_comparable_contexts, 'warn' if result.non_comparable_contexts else 'neutral')}
    {_metric('Melhoras/entradas', positive, 'good')}
    {_metric('Pioras/saídas', negative, 'bad' if negative else 'neutral')}
  </div>
</header>
<section class='panel'><h2>Contexto da comparação</h2>
  <p><strong>Milestone/deploy:</strong> {milestone} · <strong>modo de seleção:</strong> {selection}</p>
  <p>Delta numérico de posição só existe quando query, engine, país, região, idioma, device, profundidade, domínio, provider, data mode e estado observacional são compatíveis.</p>
</section>
<section class='panel'><h2>Eventos observados</h2><div class='table-wrap'><table><thead><tr>
  <th>Estado</th><th>Query</th><th>Sinal</th><th>Antes</th><th>Depois</th><th>Delta</th><th>Interpretação</th><th>Contexto exato</th>
</tr></thead><tbody>{rows}</tbody></table></div></section>
<section class='panel'><h2>Comparabilidade e limitações</h2><ul>{notes}</ul>
  <ul><li><code>NOT_FOUND_WITHIN_DEPTH</code> nunca vira posição artificial.</li><li>Search é volátil e pode variar por tempo, localização, personalização e provider.</li><li>Word count é volume, não qualidade.</li><li>Mudança de JSON-LD é evidência de diferença, não recomendação automática.</li><li>Gaps determinísticos são correlacionais.</li></ul>
</section>
<section class='panel'><h2>Fronteira metodológica</h2>
  <p><strong>{escape(result.method)}</strong> não altera <strong>SARI-001</strong> nem <strong>{escape(SCORING_VERSION)}</strong>. O relatório não chama Search provider, páginas públicas ou IA e não regrava os <code>audit.db</code> fonte.</p>
  <p>{escape(result.interpretation_policy)}</p>
</section>
<footer>Gerado em {escape(generated_at)} · fonte: dois audit.db abertos read-only · RASAi Search Intelligence.</footer>
</main></body></html>"""
    return humanize_report_html(html, page_name="search-history-report.html")


_CSS = """
:root{--bg:#f5f7fa;--surface:#fff;--ink:#273449;--muted:#6d7786;--line:#e1e6ec;--good:#eaf5ee;--bad:#faecec;--warn:#faf3e7;--neutral:#eef2fb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1500px;margin:auto;padding:34px}.hero,.panel{background:var(--surface);border:1px solid var(--line);border-radius:7px;padding:24px;margin-bottom:16px}.hero{box-shadow:0 8px 24px rgba(39,52,73,.05)}h1{font-size:30px;margin:.2rem 0 1rem}h2{font-size:20px;margin-top:0}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:9px;margin-top:18px}.metric{background:#f7f8fb;border-radius:6px;padding:11px}.metric span{display:block;color:var(--muted);font-size:12px}.metric strong{font-size:16px}.metric.good,.badge.good{background:var(--good)}.metric.bad,.badge.bad{background:var(--bad)}.metric.warn,.badge.warn{background:var(--warn)}.metric.neutral,.badge.neutral{background:var(--neutral)}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:6px}table{width:100%;border-collapse:collapse;min-width:1200px}th,td{padding:9px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}th{background:#f7f8fb;position:sticky;top:0}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;max-width:360px;word-break:break-word}.badge{display:inline-block;border-radius:999px;padding:2px 8px;font-size:11px;font-weight:700}code{background:#f1f3f6;padding:1px 4px;border-radius:4px}footer{color:var(--muted);padding:12px 4px 24px}@media(max-width:700px){main{padding:16px}.hero,.panel{padding:17px}}
"""
