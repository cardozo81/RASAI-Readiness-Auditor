"""Presentation refinements for consolidated HTML and specialist AI usage.

This layer is derivative only. It never recalculates persisted metrics, SARI/SCORE-GEO,
Monitoring deltas, or Fix Verification. It improves visible language, hierarchy and
provenance after the canonical CONS materialization/enrichment has completed.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .models import GenerationResult

_PRESENTATION_STYLE_ID = "rasai-consolidated-presentation-v1"
_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_PRIORITY_LABEL = {
    "P0": "Crítica · ação imediata",
    "P1": "Alta · próxima ação",
    "P2": "Média · planejar",
    "P3": "Baixa · oportunidade",
}
_STATUS_LABEL = {
    "IMPROVED": "Melhorou",
    "RESOLVED": "Resolvido",
    "REGRESSED": "Piorou",
    "NEW": "Novo sinal",
    "CHANGED": "Alterado",
    "NOT_COMPARABLE": "Não comparável",
    "DATA_UNAVAILABLE": "Dado indisponível",
    "FIXED": "Corrigido",
    "PARTIALLY_FIXED": "Parcialmente corrigido",
    "NOT_FIXED": "Não corrigido",
    "NOT_VERIFIABLE": "Não verificável",
    "SUCCESS": "Sucesso",
    "COMPLETE": "Concluída",
    "UNAVAILABLE": "Indisponível",
    "NO_DATA": "Sem dados elegíveis",
    "NOT_REQUESTED": "Não solicitada",
}
_TOPIC_LABEL = {
    "SEO": "SEO",
    "GEO_AI_READINESS": "GEO / preparação para IA",
    "PERFORMANCE": "Desempenho",
    "UX_APDEX": "UX / Apdex",
    "ACCESSIBILITY": "Acessibilidade",
    "INFRASTRUCTURE": "Infraestrutura",
    "SECURITY": "Segurança",
    "CONTENT_SEMANTICS": "Conteúdo e semântica",
}


@dataclass(frozen=True, slots=True)
class SpecialistUsageSummary:
    requested: bool
    status: str
    attempts: int
    successes: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    costs: tuple[tuple[str, float], ...]
    unpriced_attempts: int


def _load_artifact(report_dir: Path) -> dict[str, Any] | None:
    path = report_dir / "specialist-analysis.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def specialist_usage_summary(report_dir: str | Path) -> SpecialistUsageSummary | None:
    payload = _load_artifact(Path(report_dir))
    if payload is None:
        return None
    ai = payload.get("ai")
    if not isinstance(ai, Mapping):
        return None
    attempts = [item for item in ai.get("attempts", ()) if isinstance(item, Mapping)]
    input_tokens = sum(int(item.get("input_tokens") or 0) for item in attempts)
    cached = sum(int(item.get("cached_input_tokens") or 0) for item in attempts)
    output = sum(int(item.get("output_tokens") or 0) for item in attempts)
    reasoning = sum(int(item.get("reasoning_tokens") or 0) for item in attempts)
    costs: dict[str, float] = {}
    unpriced = 0
    successes = 0
    for item in attempts:
        status = str(item.get("status") or "").upper()
        if status == "SUCCESS":
            successes += 1
        amount = item.get("estimated_cost")
        currency = str(item.get("currency") or "").strip()
        if amount is not None and currency:
            try:
                costs[currency] = costs.get(currency, 0.0) + float(amount)
            except (TypeError, ValueError):
                unpriced += 1
        elif any(item.get(key) is not None for key in ("input_tokens", "output_tokens", "reasoning_tokens")):
            unpriced += 1
    return SpecialistUsageSummary(
        requested=bool(ai.get("requested")),
        status=str(ai.get("status") or "UNKNOWN"),
        attempts=len(attempts),
        successes=successes,
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        output_tokens=output,
        reasoning_tokens=reasoning,
        total_tokens=input_tokens + output,
        costs=tuple(sorted((currency, round(amount, 10)) for currency, amount in costs.items())),
        unpriced_attempts=unpriced,
    )


def _display_status(value: Any) -> str:
    text = str(value or "-").upper()
    return _STATUS_LABEL.get(text, str(value or "-"))


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "-" if value is None else str(value)
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _change_rank(item: Mapping[str, Any]) -> tuple[int, int, float, float]:
    status = str(item.get("status") or "").upper()
    status_rank = 0 if status == "RESOLVED" else 1
    severity = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}.get(
        str(item.get("severity") or "").upper(), 0
    )
    delta_percent = abs(_number(item.get("delta_percent")) or 0.0)
    delta = abs(_number(item.get("delta")) or 0.0)
    return status_rank, -severity, -delta_percent, -delta


def _render_improvements(changes: list[Mapping[str, Any]]) -> str:
    improved = [item for item in changes if str(item.get("status") or "").upper() in {"IMPROVED", "RESOLVED"}]
    improved.sort(key=_change_rank)
    if not improved:
        return (
            "<div class='improvement-highlight empty-highlight'>"
            "<h3>Destaques de melhora observada</h3>"
            "<p>Nenhuma melhora ou resolução material comparável foi registrada no par selecionado.</p>"
            "</div>"
        )
    cards: list[str] = []
    for item in improved[:3]:
        status = _display_status(item.get("status"))
        scope = item.get("url") or "escopo global"
        context = " / ".join(
            str(value) for value in (item.get("device"), item.get("rule_id")) if value
        )
        delta = _number(item.get("delta"))
        delta_text = f" · Δ {_fmt(delta)} {escape(str(item.get('unit') or ''))}" if delta is not None else ""
        cards.append(
            "<article class='improvement-item signal-positive'>"
            f"<div><span class='status-pill status-positive'>{escape(status)}</span> "
            f"<code>{escape(str(item.get('evidence_id') or '-'))}</code></div>"
            f"<h4>{escape(str(item.get('label') or 'Sinal observado'))}</h4>"
            f"<p class='improvement-values'>{escape(_fmt(item.get('before')))} → {escape(_fmt(item.get('after')))}{delta_text}</p>"
            f"<p class='subtle'>{escape(str(scope))}{('<br>' + escape(context)) if context else ''}</p>"
            "</article>"
        )
    return (
        "<div class='improvement-highlight'>"
        "<div class='section-title'><div><h3>Destaques de melhora observada</h3>"
        "<p>Priorizados por resolução, severidade e magnitude disponível. São mudanças observadas; não provam causalidade.</p>"
        "</div><span class='signal-key signal-positive'>Melhora</span></div>"
        f"<div class='improvement-grid'>{''.join(cards)}</div></div>"
    )


def _render_usage(attempts: list[Mapping[str, Any]]) -> str:
    rows: list[str] = []
    costs: dict[str, float] = {}
    total_input = total_cached = total_output = total_reasoning = 0
    unpriced = 0
    for item in attempts:
        input_tokens = int(item.get("input_tokens") or 0)
        cached = int(item.get("cached_input_tokens") or 0)
        output = int(item.get("output_tokens") or 0)
        reasoning = int(item.get("reasoning_tokens") or 0)
        total_input += input_tokens
        total_cached += cached
        total_output += output
        total_reasoning += reasoning
        amount = item.get("estimated_cost")
        currency = str(item.get("currency") or "").strip()
        if amount is not None and currency:
            try:
                costs[currency] = costs.get(currency, 0.0) + float(amount)
            except (TypeError, ValueError):
                unpriced += 1
        elif any(item.get(key) is not None for key in ("input_tokens", "output_tokens", "reasoning_tokens")):
            unpriced += 1
        rendered_cost = "-"
        if amount is not None and currency:
            try:
                rendered_cost = f"{currency} {float(amount):.8f}"
            except (TypeError, ValueError):
                rendered_cost = "não calculado"
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('provider') or '-'))}</td>"
            f"<td>{escape(str(item.get('model') or '-'))}</td>"
            f"<td>{escape(str(item.get('reasoning') or '-'))}</td>"
            f"<td>{escape(_display_status(item.get('status')))}</td>"
            f"<td>{input_tokens:,}</td><td>{cached:,}</td><td>{output:,}</td><td>{reasoning:,}</td>"
            f"<td>{escape(rendered_cost)}</td>"
            "</tr>"
        )
    if not rows:
        return "<p class='subtle'>Nenhuma chamada de IA foi materializada nesta análise.</p>"
    rendered_costs = " · ".join(f"{currency} {amount:.8f}" for currency, amount in sorted(costs.items())) or "não calculável"
    unpriced_note = f" · {unpriced} tentativa(s) sem custo calculável" if unpriced else ""
    return f"""
    <div class='ai-usage-summary'>
      <div><small>Tentativas</small><strong>{len(rows)}</strong></div>
      <div><small>Tokens de entrada</small><strong>{total_input:,}</strong></div>
      <div><small>Tokens de cache</small><strong>{total_cached:,}</strong></div>
      <div><small>Tokens de saída</small><strong>{total_output:,}</strong></div>
      <div><small>Tokens de raciocínio</small><strong>{total_reasoning:,}</strong></div>
      <div><small>Custo técnico estimado</small><strong>{escape(rendered_costs)}</strong></div>
    </div>
    <div class='table-wrap'><table><thead><tr><th>Provedor</th><th>Modelo</th><th>Perfil de raciocínio</th><th>Resultado</th><th>Entrada</th><th>Cache</th><th>Saída</th><th>Raciocínio</th><th>Custo estimado</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    <p class='subtle'>Custo técnico calculado a partir do uso reportado pelos adaptadores; não é fatura do provedor{escape(unpriced_note)}.</p>
    """


def _render_ai_section(payload: Mapping[str, Any]) -> str:
    ai = payload.get("ai")
    if not isinstance(ai, Mapping) or not bool(ai.get("requested")):
        return ""
    status = str(ai.get("status") or "UNKNOWN").upper()
    changes = [item for item in payload.get("changes", ()) if isinstance(item, Mapping)]
    attempts = [item for item in ai.get("attempts", ()) if isinstance(item, Mapping)]
    if status != "COMPLETE":
        reason = str(ai.get("reason") or _display_status(status))
        return f"""
<section id='specialist-ai' class='panel ai-section'>
  <div class='ai-origin'>Conteúdo assistido por IA · origem explicitamente identificada</div>
  <h2>Análise especialista por IA não concluída</h2>
  <p>A análise determinística permanece válida e independente da IA.</p>
  <p class='notice warning'><strong>Estado:</strong> {escape(_display_status(status))} · {escape(reason)}</p>
  <details><summary>Uso e custo da IA nesta tentativa</summary>{_render_usage(attempts)}</details>
</section>
"""
    analyses = [item for item in ai.get("topic_analyses", ()) if isinstance(item, Mapping)]
    analyses.sort(key=lambda item: (_PRIORITY_RANK.get(str(item.get("priority") or "P3").upper(), 9), str(item.get("topic") or "")))
    cards: list[str] = []
    for item in analyses:
        priority = str(item.get("priority") or "P3").upper()
        topic = _TOPIC_LABEL.get(str(item.get("topic") or ""), str(item.get("topic") or "Tópico"))
        confidence = _number(item.get("confidence"))
        confidence_text = f"{confidence * 100:.0f}%" if confidence is not None else "-"
        actions = "".join(f"<li>{escape(str(action))}</li>" for action in item.get("recommended_actions", ()) if str(action).strip())
        evidence = ", ".join(str(value) for value in item.get("evidence_ids", ()) if str(value)) or "-"
        cards.append(
            f"<article class='ai-card priority-{priority.lower()}'>"
            "<div class='ai-card-head'>"
            f"<div><span class='ai-origin compact'>Gerado por IA</span><div class='kicker'>{escape(topic)}</div></div>"
            f"<span class='priority-badge priority-{priority.lower()}'>{escape(priority)} · {escape(_PRIORITY_LABEL.get(priority, 'Prioridade'))}</span>"
            "</div>"
            f"<p>{escape(str(item.get('assessment') or ''))}</p>"
            f"<p class='confidence-line'><strong>Confiança da análise:</strong> {escape(confidence_text)}</p>"
            f"<h4>Ações recomendadas</h4><ul>{actions or '<li>Nenhuma ação adicional informada.</li>'}</ul>"
            f"<p><strong>Evidências usadas:</strong> <code>{escape(evidence)}</code></p>"
            "</article>"
        )
    summary = escape(str(ai.get("summary") or ""))
    return f"""
<section id='specialist-ai' class='panel ai-section'>
  <div class='ai-origin'>Conteúdo gerado por IA · orientativo · não altera SARI/SCORE-GEO</div>
  <h2>Análise especialista por IA e plano priorizado</h2>
  <div class='ai-summary'><h3>Síntese gerada por IA</h3><p>{summary or 'Nenhuma síntese textual foi retornada.'}</p></div>
  {_render_improvements(changes)}
  <div class='priority-legend' aria-label='Legenda de prioridades'>
    <span class='priority-badge priority-p0'>P0 · Crítica</span><span class='priority-badge priority-p1'>P1 · Alta</span><span class='priority-badge priority-p2'>P2 · Média</span><span class='priority-badge priority-p3'>P3 · Baixa</span>
  </div>
  <div class='ai-card-grid'>{''.join(cards) or "<p class='subtle'>Nenhuma recomendação por tópico foi retornada.</p>"}</div>
  <details class='details'><summary>Uso e custo da IA nesta análise</summary>{_render_usage(attempts)}</details>
  <p class='notice info'><strong>Limite:</strong> esta seção interpreta evidências persistidas. Associação temporal não é causalidade; recomendações de IA exigem revisão humana.</p>
</section>
"""


def _presentation_css() -> str:
    return f"""
<style id='{_PRESENTATION_STYLE_ID}'>
.metric-grid>div{{display:flex;flex-direction:column;justify-content:flex-start;min-height:92px;gap:4px}}
.metric-grid>div>small:first-child{{font-size:.78rem;font-weight:700;line-height:1.25;letter-spacing:.015em;margin:0 0 7px;text-transform:none}}
.metric-grid>div>strong{{display:block;font-size:1.35rem;line-height:1.15;font-variant-numeric:tabular-nums;margin-top:auto}}
.metric.signal-positive,.signal-positive{{background:var(--green-soft)!important;border-color:rgba(111,159,130,.45)!important;border-left:4px solid var(--green)!important}}
.metric.signal-warning,.signal-warning{{background:var(--amber-soft)!important;border-color:rgba(178,134,79,.42)!important;border-left:4px solid var(--amber)!important}}
.metric.signal-negative,.signal-negative{{background:var(--red-soft)!important;border-color:rgba(185,108,112,.45)!important;border-left:4px solid var(--red)!important}}
.status-pill,.priority-badge,.signal-key,.ai-origin{{display:inline-flex;align-items:center;border-radius:999px;padding:3px 8px;font-size:.76rem;font-weight:750;line-height:1.35}}
.status-positive{{background:var(--green-soft);color:#356b49}}.status-warning{{background:var(--amber-soft);color:#7c5728}}.status-negative{{background:var(--red-soft);color:#8f4248}}
.ai-section{{border-top:4px solid var(--blue)}}.ai-origin{{background:#eaf0fb;color:#3c5e9d;margin-bottom:8px}}.ai-origin.compact{{margin:0 0 6px;padding:2px 7px}}
.ai-summary{{background:var(--soft);border-left:4px solid var(--blue);padding:12px 14px;border-radius:6px;margin:12px 0 16px}}.ai-summary h3{{margin:0 0 6px}}
.priority-legend{{display:flex;gap:7px;flex-wrap:wrap;margin:14px 0}}.priority-p0{{background:var(--red-soft);color:#8f4248}}.priority-p1{{background:var(--amber-soft);color:#7c5728}}.priority-p2{{background:#eaf0fb;color:#3c5e9d}}.priority-p3{{background:var(--green-soft);color:#356b49}}
.ai-card-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}}.ai-card{{background:#fbfcfe;border:1px solid var(--line);border-radius:8px;padding:14px}}.ai-card.priority-p0{{border-left:5px solid var(--red)}}.ai-card.priority-p1{{border-left:5px solid var(--amber)}}.ai-card.priority-p2{{border-left:5px solid var(--blue)}}.ai-card.priority-p3{{border-left:5px solid var(--green)}}
.ai-card-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}}.ai-card h4{{margin:12px 0 5px}}.confidence-line{{font-size:.9rem;color:var(--muted)}}
.improvement-highlight{{margin:16px 0;padding:14px;border:1px solid var(--line);border-radius:8px;background:#fbfcfe}}.improvement-highlight h3{{margin:0 0 5px}}.improvement-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}}.improvement-item{{border-radius:7px;padding:11px}}.improvement-item h4{{margin:8px 0 4px}}.improvement-values{{font-size:1.08rem;font-weight:700;font-variant-numeric:tabular-nums}}.empty-highlight{{background:var(--soft)}}
.ai-usage-summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;margin:12px 0}}.ai-usage-summary>div{{background:#f7f9fc;border:1px solid var(--line);border-radius:7px;padding:10px}}.ai-usage-summary strong{{display:block;font-size:1.08rem;font-variant-numeric:tabular-nums}}
@media(max-width:760px){{.ai-card-head{{display:block}}.priority-badge{{margin-top:8px}}}}
</style>
"""


def refine_html(html: str, artifact: Mapping[str, Any] | None = None) -> str:
    rendered = html
    replacements = {
        "Snapshot": "Leitura pontual",
        "Fix Verification": "Verificação de correções",
        "advisory/non-scoring": "orientativa · não altera a pontuação",
    }
    for old, new in replacements.items():
        rendered = rendered.replace(old, new)

    metric_classes = {
        "<div class='metric'><span>Melhorias</span>": "<div class='metric signal-positive'><span>Melhorias</span>",
        "<div class='metric'><span>Resolvidos</span>": "<div class='metric signal-positive'><span>Resolvidos</span>",
        "<div class='metric'><span>Regressões</span>": "<div class='metric signal-negative'><span>Regressões</span>",
        "<div class='metric'><span>Novos sinais</span>": "<div class='metric signal-warning'><span>Novos sinais</span>",
    }
    for old, new in metric_classes.items():
        rendered = rendered.replace(old, new)

    cell_statuses = {
        "IMPROVED": ("Melhorou", "status-positive"),
        "RESOLVED": ("Resolvido", "status-positive"),
        "REGRESSED": ("Piorou", "status-negative"),
        "NEW": ("Novo sinal", "status-warning"),
        "CHANGED": ("Alterado", "status-warning"),
        "NOT_COMPARABLE": ("Não comparável", "status-warning"),
        "DATA_UNAVAILABLE": ("Dado indisponível", "status-warning"),
        "FIXED": ("Corrigido", "status-positive"),
        "PARTIALLY_FIXED": ("Parcialmente corrigido", "status-warning"),
        "NOT_FIXED": ("Não corrigido", "status-negative"),
        "NOT_VERIFIABLE": ("Não verificável", "status-warning"),
    }
    for raw, (label, css) in cell_statuses.items():
        rendered = rendered.replace(f"<td>{raw}</td>", f"<td><span class='status-pill {css}'>{label}</span></td>")

    rendered = rendered.replace(
        "<p><code>FIXED</code> significa que uma condição FAIL/WARNING persistida atingiu PASS na auditoria atual. Isso não prova impacto downstream em Search/IA.</p>",
        "<p><strong>Corrigido (<code>FIXED</code>)</strong> significa que uma condição de falha/alerta persistida atingiu aprovação na auditoria atual. Isso não prova impacto posterior em Search/IA.</p>",
    )

    ai = artifact.get("ai") if isinstance(artifact, Mapping) else None
    ai_requested = isinstance(ai, Mapping) and bool(ai.get("requested"))
    if ai_requested:
        rendered = rendered.replace(
            "<div><small>Chamadas externas</small><strong>Nenhuma</strong><p>O consolidado não chama IA, PageSpeed, CrUX ou qualquer API.</p></div>",
            "<div><small>Chamadas externas</small><strong>Somente IA especialista, quando autorizada</strong><p>A consolidação dos AUDs é local e somente leitura. Apenas a análise especialista identificada como IA pode efetuar chamada externa autorizada; PageSpeed/CrUX não são reexecutados pelo consolidado.</p></div>",
        )
        ai_section = _render_ai_section(artifact)
        if ai_section:
            rendered, count = re.subn(
                r"<section id=['\"]specialist-ai['\"][^>]*>.*?</section>",
                ai_section,
                rendered,
                count=1,
                flags=re.DOTALL,
            )
            if count == 0:
                rendered = rendered.replace("<footer", ai_section + "<footer", 1)

    if "specialist-evolution" in rendered and "href='#specialist-evolution'" not in rendered:
        rendered = rendered.replace("<a href='#evolution'>Evolução</a>", "<a href='#evolution'>Evolução</a><a href='#specialist-evolution'>Comparação</a>", 1)
    if "specialist-ai" in rendered and "href='#specialist-ai'" not in rendered:
        rendered = rendered.replace("<a href='#specialist-evolution'>Comparação</a>", "<a href='#specialist-evolution'>Comparação</a><a href='#specialist-ai'>Análise por IA</a>", 1)

    if _PRESENTATION_STYLE_ID not in rendered:
        rendered = rendered.replace("</head>", _presentation_css() + "</head>", 1)
    return rendered


def refine_result(result: GenerationResult) -> GenerationResult:
    """Refine a materialized CONS report without changing its factual payload."""
    try:
        html = result.report_path.read_text(encoding="utf-8")
    except OSError:
        return result
    artifact = _load_artifact(result.report_dir)
    rendered = refine_html(html, artifact)
    if rendered != html:
        try:
            result.report_path.write_text(rendered, encoding="utf-8", newline="\n")
        except OSError:
            return result
    return result
