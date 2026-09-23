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
    "COMPLETE_WITH_LIMITATIONS": "Concluída com limitações",
    "COMPLETED_WITH_LIMITATIONS": "Concluída com limitações",
    "FINAL": "Final",
    "UNAVAILABLE": "Indisponível",
    "NO_DATA": "Sem dados elegíveis",
    "NOT_REQUESTED": "Não solicitada",
}
_ERROR_LABEL = {
    "AUTH_ERROR": "Falha de autenticação",
    "QUOTA_ERROR": "Quota indisponível",
    "CREDIT_ERROR": "Crédito indisponível",
    "RATE_LIMIT_ERROR": "Limite temporário de requisições",
    "MODEL_ERROR": "Modelo indisponível ou inválido",
    "PERMISSION_ERROR": "Permissão insuficiente",
    "NETWORK_ERROR": "Falha de rede",
    "TIMEOUT_ERROR": "Tempo limite excedido",
    "SERVER_ERROR": "Falha temporária do provedor",
    "CONTRACT_ERROR": "Resposta fora do contrato esperado",
    "EMPTY_RESPONSE": "Resposta vazia",
    "INVALID_RESPONSE": "Resposta inválida",
    "UNKNOWN_PROVIDER_ERROR": "Falha não classificada do provedor",
}
_SARI_CONFIDENCE_LABEL = {
    "VERY_HIGH": "Muito alta",
    "HIGH": "Alta",
    "MEDIUM": "Média",
    "LOW": "Baixa",
    "VERY_LOW": "Muito baixa",
    "UNAVAILABLE": "Indisponível",
    "NOT_AVAILABLE": "Indisponível",
    "NOT_APPLICABLE": "Não aplicável",
    "NOT_DETERMINABLE": "Não determinada",
    "UNKNOWN": "Não determinada",
    "NONE": "Não determinada",
    "NOT_SET": "Não determinada",
}

_DECISION_LABEL = {
    "SUCCESS": "Concluído",
    "FALLBACK": "Contingência para próximo provedor",
    "FALLBACK_SUCCESS": "Concluído após contingência",
    "STOP": "Encerrar cadeia",
    "RETRY_ROUND": "Nova rodada",
}
_TOPIC_LABEL = {
    "SEO": "SEO",
    "GEO_AI_READINESS": "Otimização para mecanismos generativos (GEO) / preparação para IA",
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
    """Load the presentation context for both deterministic and AI CONS modes."""
    path = report_dir / "specialist-analysis.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = None

    if not isinstance(payload, dict):
        payload = {}
        try:
            decision = json.loads((report_dir / "decision-context.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            decision = {}
        if isinstance(decision, Mapping) and decision:
            payload["decision_context"] = dict(decision)
            governance = decision.get("source_governance")
            if isinstance(governance, Mapping):
                payload["source_governance"] = dict(governance)

        try:
            evidence_artifact = json.loads(
                (report_dir / "longitudinal-evidence.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            evidence_artifact = {}
        packet = (
            evidence_artifact.get("evidence")
            if isinstance(evidence_artifact, Mapping)
            and isinstance(evidence_artifact.get("evidence"), Mapping)
            else {}
        )
        if isinstance(packet, Mapping):
            scope = packet.get("scope")
            if isinstance(scope, Mapping):
                payload["scope"] = dict(scope)
            refs = packet.get("rule_reference")
            if isinstance(refs, (list, tuple)):
                payload["rule_reference"] = [
                    dict(item) for item in refs if isinstance(item, Mapping)
                ]
            initial = packet.get("initial_to_final")
            if isinstance(initial, Mapping):
                technical = initial.get("current_technical_findings")
                if isinstance(technical, (list, tuple)):
                    payload["current_technical_findings"] = [
                        dict(item) for item in technical if isinstance(item, Mapping)
                    ]
            intervals = packet.get("intervals")
            if isinstance(intervals, (list, tuple)):
                payload["intervals"] = [
                    dict(item) for item in intervals if isinstance(item, Mapping)
                ]

        try:
            manifest = json.loads((report_dir / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        specialist = manifest.get("specialist_ai") if isinstance(manifest, Mapping) else None
        if isinstance(specialist, Mapping):
            payload["ai"] = dict(specialist)

        if not payload:
            return None

    exchanges_path = report_dir / "ai-exchanges.json"
    try:
        exchanges_payload = json.loads(exchanges_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        exchanges_payload = {}
    if isinstance(exchanges_payload, Mapping):
        payload["_exchanges"] = [
            item for item in exchanges_payload.get("exchanges", ())
            if isinstance(item, Mapping)
        ]
    return payload


def specialist_usage_summary(report_dir: str | Path) -> SpecialistUsageSummary | None:
    payload = _load_artifact(Path(report_dir))
    if payload is None:
        return None
    ai = payload.get("ai")
    if not isinstance(ai, Mapping):
        return None
    attempts = [item for item in ai.get("attempts", ()) if isinstance(item, Mapping)]
    exchanges = [item for item in payload.get("_exchanges", ()) if isinstance(item, Mapping)]
    forecast = ai.get("forecast") if isinstance(ai.get("forecast"), Mapping) else {}
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


def _decision_context(payload: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    value = payload.get("decision_context")
    return value if isinstance(value, Mapping) else {}


def _tone_label(tone: str) -> str:
    return {"good": "Concluído", "warn": "Atenção", "bad": "Crítico", "info": "Informativo"}.get(tone, tone)


def _sari_chart(sari: Mapping[str, Any]) -> str:
    series = [item for item in sari.get("series", ()) if isinstance(item, Mapping) and _number(item.get("value")) is not None]
    if len(series) < 2:
        return "<p class='subtle'>Série do Índice de Prontidão Search & IA insuficiente para gráfico longitudinal.</p>"
    width, height, pad = 760.0, 190.0, 34.0
    values = [float(item["value"]) for item in series]
    low = min(values)
    high = max(values)
    span = max(1.0, high - low)
    points = []
    dots = []
    labels = []
    for index, item in enumerate(series):
        x = pad + (width - 2 * pad) * index / max(1, len(series) - 1)
        y = pad + (height - 2 * pad) * (1.0 - (float(item["value"]) - low) / span)
        points.append(f"{x:.1f},{y:.1f}")
        dots.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='4.5' class='decision-dot'><title>{escape(str(item.get('audit_id') or ''))}: {float(item['value']):.2f}</title></circle>")
        labels.append(f"<text x='{x:.1f}' y='{height-8:.1f}' text-anchor='middle' class='decision-axis'>{index+1}</text>")
    return (
        "<div class='decision-chart'><svg viewBox='0 0 760 190' role='img' aria-label='Evolução do Índice de Prontidão Search & IA'>"
        f"<polyline points='{' '.join(points)}' class='decision-line'/>"
        + "".join(dots) + "".join(labels) +
        "</svg><div class='decision-chart-caption'>Cada ponto representa uma AUD em ordem temporal. Passe o cursor sobre os pontos para identificar a auditoria e o valor.</div></div>"
    )


def _sari_confidence_label(value: Any) -> str:
    raw = str(value or "UNKNOWN").strip().upper()
    return _SARI_CONFIDENCE_LABEL.get(raw, "Não determinada")


def _source_limitation_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    code, separator, raw_count = text.partition(":")
    labels = {
        "RENDERED_DISCOVERY_GAP": "Lacuna na descoberta renderizada",
        "RENDER_DISCOVERY_GAP": "Lacuna na descoberta renderizada",
        "DISCOVERY_GAP": "Lacuna de descoberta",
        "PARTIAL_RENDERED_DISCOVERY": "Descoberta renderizada parcial",
        "RENDERED_LINKS_OUTSIDE_AUDIT_UNIVERSE_MAX_PAGES": "Links renderizados fora do universo auditado devido ao limite máximo de páginas",
    }
    label = labels.get(code, code.replace("_", " ").title())
    count = raw_count.strip() if separator else ""
    if count.isdigit():
        suffix = "URL renderizada fora do universo auditado" if count == "1" else "URLs renderizadas fora do universo auditado"
        return f"{label}: {count} {suffix}"
    return label if not count else f"{label}: {count}"


def _render_source_governance(context: Mapping[str, Any]) -> str:
    governance = context.get("source_governance") if isinstance(context.get("source_governance"), Mapping) else {}
    rows = []
    for item in governance.get("audits", ()):
        if not isinstance(item, Mapping):
            continue
        tone = "good" if item.get("conclusive") else ("warn" if item.get("reprocess_recommended") else "bad")
        issues = [
            f"{value.get('component')} / {value.get('status')}"
            for value in item.get("required_issues", ())
            if isinstance(value, Mapping)
        ]
        limitations = [
            _source_limitation_label(value)
            for value in item.get("source_limitations", ())
            if str(value).strip()
        ]
        report_present = item.get("report_catalog_present")
        report_fresh = item.get("report_catalog_fresh")
        if report_fresh is True:
            report_state = "<span class='decision-state good'>Atualizado</span>"
        elif report_present is True:
            report_state = "<span class='decision-state warn'>Desatualizado - navegação suprimida</span>"
        else:
            report_state = "<span class='decision-state info'>Não disponível</span>"
        overlap_state = str(item.get("temporal_revision_overlap_state") or "NONE").upper()
        revision_id = str(item.get("source_revision_id") or "")
        if overlap_state == "REPLAY_SAFE_AFTER_NEXT_OBSERVATION":
            revision_state = "<span class='decision-state info'>Revisão posterior - replay seguro</span>"
        elif overlap_state == "LIVE_RECOLLECTION_AFTER_NEXT_OBSERVATION":
            revision_state = "<span class='decision-state bad'>Recoleta posterior ao próximo marco</span>"
        elif overlap_state == "UNKNOWN_REVISION_AFTER_NEXT_OBSERVATION":
            revision_state = "<span class='decision-state warn'>Revisão posterior não comprovada</span>"
        elif item.get("post_observation_revision") is True:
            revision_state = "<span class='decision-state info'>Revisada após a observação</span>"
        else:
            revision_state = "<span class='decision-state good'>Sem sobreposição temporal</span>"
        if revision_id:
            revision_state += f"<br><small><code>{escape(revision_id)}</code></small>"
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(item.get('audit_id') or '-'))}</code></td>"
            f"<td><span class='decision-state {tone}'>{escape(str(item.get('source_state_label') or '-'))}</span></td>"
            f"<td>{escape(_visible_label(str(item.get('completion_status') or '-')))}</td>"
            f"<td>{escape(_visible_label(str((item.get('fulfillment') or {}).get('processing_status') or '-')))}</td>"
            f"<td>{report_state}</td>"
            f"<td>{revision_state}</td>"
            f"<td>{'Sim' if item.get('reprocess_recommended') else 'Não'}</td>"
            f"<td>{escape('; '.join(limitations) or 'Nenhuma limitação registrada')}</td>"
            f"<td>{escape('; '.join(issues) or 'Nenhuma pendência obrigatória registrada')}</td>"
            "</tr>"
        )
    return (
        "<div class='table-wrap'><table><thead><tr><th>AUD</th><th>Estado da fonte</th><th>Conclusão</th>"
        "<th>Processamento</th><th>Relatório fonte</th><th>Revisão temporal</th><th>Reprocessar</th><th>Limitações registradas</th><th>Pendências obrigatórias</th></tr></thead><tbody>"
        + ("".join(rows) or "<tr><td colspan='9'>Sem dados de governança das fontes.</td></tr>") +
        "</tbody></table></div>"
    )


def _render_structural_matrix(context: Mapping[str, Any]) -> str:
    matrix = context.get("structural_matrix") if isinstance(context.get("structural_matrix"), Mapping) else {}
    cards = []
    for item in matrix.get("axes", ()):
        if not isinstance(item, Mapping):
            continue
        tone = str(item.get("tone") or "info")
        cards.append(
            f"<article class='closure-card {escape(tone)}'><div class='closure-head'>"
            f"<span>{escape(str(item.get('label') or item.get('axis') or '-'))}</span>"
            f"<span class='decision-state {escape(tone)}'>{escape(str(item.get('state') or '-'))}</span></div>"
            f"<p>{escape(str(item.get('detail') or ''))}</p></article>"
        )
    overall = str(matrix.get("overall") or "NÃO DETERMINADO")
    tone = str(matrix.get("tone") or "info")
    return (
        f"<div class='closure-overall {escape(tone)}'><span>Encerramento estrutural do consolidado</span><strong>{escape(overall)}</strong></div>"
        f"<div class='closure-grid'>{''.join(cards)}</div>"
    )


def _render_executive_decision(payload: Mapping[str, Any]) -> str:
    context = _decision_context(payload)
    if not context:
        return ""
    governance = context.get("source_governance") if isinstance(context.get("source_governance"), Mapping) else {}
    sari = context.get("sari") if isinstance(context.get("sari"), Mapping) else {}
    priorities = [item for item in context.get("priorities", ()) if isinstance(item, Mapping)]
    conclusion = str(governance.get("conclusion_state") or "UNKNOWN")
    if conclusion == "CONCLUSIVE":
        state_tone = "good"
        state_label = "Série conclusiva"
    elif conclusion == "CONCLUSIVE_WITH_LIMITATIONS":
        state_tone = "warn"
        state_label = "Série conclusiva com limitações"
    else:
        state_tone = "bad"
        state_label = "Série não conclusiva"
    reprocess_ids = ", ".join(governance.get("reprocess_recommended_audit_ids") or ())
    reliability = context.get("ai_reliability") if isinstance(context.get("ai_reliability"), Mapping) else {}

    sari_cards = ""
    if sari.get("available"):
        initial = sari.get("initial") or {}
        current = sari.get("current") or {}
        peak = sari.get("peak") or {}
        delta = _number(sari.get("delta"))
        sari_cards = (
            "<div class='decision-kpis'>"
            f"<div><small>SARI inicial</small>{_result_value_html(initial.get('value'))}</div>"
            f"<div><small>SARI atual</small>{_result_value_html(current.get('value'))}</div>"
            f"<div><small>Variação inicial → atual</small>{_delta_result_html(delta)}</div>"
            f"<div><small>Pico observado</small>{_result_value_html(peak.get('value'))}<span>{escape(str(peak.get('audit_id') or ''))}</span></div>"
            f"<div><small>Cobertura atual</small><strong>{((_number(current.get('coverage')) or 0)*100):.1f}%</strong></div>"
            f"<div><small>Confiança atual</small><strong>{escape(_sari_confidence_label(current.get('confidence')))}</strong></div>"
            "</div>"
        )

    priority_cards = []
    for item in priorities[:5]:
        priority = str(item.get("priority") or "P3")
        actions = [str(value) for value in item.get("recommended_actions", ()) if str(value).strip()]
        confidence = _number(item.get("confidence"))
        confidence_label = (
            "Muito alta" if confidence is not None and confidence >= 0.95
            else "Alta" if confidence is not None and confidence >= 0.75
            else "Limitada" if confidence is not None
            else "Não determinada"
        )
        confidence_text = f"{confidence * 100:.0f}% · {confidence_label}" if confidence is not None else confidence_label
        priority_cards.append(
            f"<article class='decision-priority priority-{escape(priority.lower())}'>"
            f"<div class='decision-priority-head'><span class='priority-badge priority-{escape(priority.lower())}'>{escape(priority)}</span>"
            f"<strong>{escape(str(item.get('topic_label') or item.get('topic') or 'Prioridade'))}</strong>"
            "<span class='ai-origin compact'>Gerado por IA</span>"
            f"<span class='ai-confidence compact'>Confiabilidade: {escape(confidence_text)}</span></div>"
            f"<p><strong>Diagnóstico / causa provável:</strong> {escape(str(item.get('cause_analysis') or item.get('assessment') or ''))}</p>"
            f"<p><strong>Ação inicial:</strong> {escape(actions[0] if actions else 'Revisar evidências e definir ação humana.')}</p>"
            f"<details><summary>Ver ações e evidências</summary><ul>{''.join(f'<li>{escape(value)}</li>' for value in actions) or '<li>Nenhuma ação adicional.</li>'}</ul>"
            f"<p><strong>Evidências:</strong> <code>{escape(', '.join(item.get('evidence_ids', ())) or '-')}</code></p></details>"
            "</article>"
        )

    source_notice = ""
    if conclusion == "NON_CONCLUSIVE":
        source_notice = (
            "<div class='decision-alert bad'><strong>Análise não conclusiva.</strong> "
            "Uma ou mais AUDs fonte não possuem encerramento final comprovado. "
            + (f"Reprocessamento recomendado: <code>{escape(reprocess_ids)}</code>. " if reprocess_ids else "")
            + "As tendências abaixo permanecem descritivas/contextuais até regularização das fontes.</div>"
        )
    elif conclusion == "CONCLUSIVE_WITH_LIMITATIONS":
        source_notice = (
            "<div class='decision-alert warn'><strong>Série final com limitações.</strong> "
            "As AUDs estão finalizadas e elegíveis para consolidação, sem requisito obrigatório pendente. "
            "As limitações registradas permanecem visíveis e devem ser consideradas na interpretação; "
            "não há recomendação automática de reprocessamento.</div>"
        )

    reliability_label = str(reliability.get("label") or "Não determinada")
    reliability_tone = str(reliability.get("tone") or "info")
    declared = _number(reliability.get("declared_confidence"))
    declared_text = f"{declared * 100:.0f}%" if declared is not None else "não determinada"
    reliability_reasons = "".join(
        f"<li>{escape(str(reason))}</li>"
        for reason in reliability.get("reasons", ())
        if str(reason).strip()
    )
    reliability_html = (
        f"<div class='ai-reliability {escape(reliability_tone)}'>"
        f"<div><small>Confiabilidade da interpretação por IA</small><strong>{escape(reliability_label)}</strong>"
        f"<span>Confiança média declarada pela IA: {escape(declared_text)}</span></div>"
        f"<details><summary>Como interpretar esta confiabilidade</summary>"
        f"<p>{escape(str(reliability.get('interpretation') or ''))}</p><ul>{reliability_reasons}</ul></details></div>"
    )

    return f"""
<section id='decision-overview' class='decision-hero'>
  <div class='decision-eyebrow'>Visão executiva do estudo longitudinal</div>
  <div class='decision-title-row'>
    <div><h2>Como a URL evoluiu e onde agir primeiro</h2>
    <p>{escape(str(context.get('url') or ''))} · {escape(str(context.get('device') or ''))} · {int(context.get('audit_count') or 0)} auditorias · {int(context.get('interval_count') or 0)} intervalos</p></div>
    <span class='decision-state {state_tone}'>{state_label}</span>
  </div>
  {source_notice}
  <div class='managerial-summary'>
    <div class='ai-origin'>Resumo gerencial gerado por IA</div>
    {reliability_html}
    <p>{escape(str(context.get('managerial_summary') or 'Resumo não disponível.'))}</p>
    <p class='subtle'>Síntese interpretativa baseada nas evidências persistidas. Não substitui decisão humana e não prova causalidade.</p>
  </div>
  <h3>Search &amp; AI Readiness Index - Índice de Prontidão Search &amp; IA</h3>
  {sari_cards}
  {_sari_chart(sari)}
  <h3 id='decision-priorities'>Prioridades para decisão</h3>
  <p class='subtle'>Ordenadas pela prioridade atribuída pela análise longitudinal por IA. Evidências e ações completas permanecem rastreáveis nas seções técnicas.</p>
  <div class='decision-priority-grid'>{''.join(priority_cards) or "<p>Nenhuma prioridade estruturada foi retornada.</p>"}</div>
</section>
"""


def _render_governance_section(payload: Mapping[str, Any]) -> str:
    context = _decision_context(payload)
    if not context:
        return ""
    return f"""
<section id='cons-governance' class='panel governance-panel'>
  <div class='kicker'>Inspeção estrutural</div>
  <h2>Governança, integridade e auditabilidade</h2>
  <p>Esta área sustenta inspeção e reprodutibilidade do CONS. Não é a camada principal de decisão sobre a URL.</p>
  {_render_structural_matrix(context)}
  <details class='details'><summary>Saúde das auditorias fonte e necessidade de reprocessamento</summary>{_render_source_governance(context)}</details>
  <details class='details'><summary>Artifacts e integridade do pacote</summary>
    <ul><li><code>manifest.json</code> - contratos, hashes e proveniência.</li>
    <li><code>decision-context.json</code> - contexto decisório derivado.</li>
    <li><code>longitudinal-evidence.json</code> - evidência longitudinal integral.</li>
    <li><code>specialist-analysis.json</code> - interpretação estruturada da IA.</li>
    <li><code>ai-exchanges.json</code> - solicitações/respostas sanitizadas.</li>
    <li><code>execution.json</code> - execução autocontida da consolidação.</li></ul>
  </details>
</section>
"""


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


def _score_tone(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "neutral"
    if number >= 75:
        return "good"
    if number >= 60:
        return "warn"
    if number >= 40:
        return "low"
    return "bad"


def _result_value_html(value: Any, *, tone: str | None = None, digits: int | None = None) -> str:
    number = _number(value)
    rendered = "-" if number is None else (f"{number:.{digits}f}" if digits is not None else _fmt(number))
    safe_tone = tone or _score_tone(number)
    if safe_tone not in {"good", "warn", "low", "bad", "neutral"}:
        safe_tone = "neutral"
    return f"<strong class='result-value {safe_tone}'>{escape(rendered)}</strong>"


def _delta_result_html(value: Any) -> str:
    number = _number(value)
    tone = "good" if number is not None and number > 0 else "bad" if number is not None and number < 0 else "neutral"
    prefix = "+" if number is not None and number > 0 else ""
    rendered = "-" if number is None else prefix + _fmt(number)
    return f"<strong class='result-value {tone}'>{escape(rendered)}</strong>"


def _is_explicit_zero_cost(value: Any) -> bool:
    if value in (None, ""):
        return False
    number = _number(value)
    return number is not None and abs(number) <= 1e-12


def _no_cost_html(value: Any) -> str:
    return f"<span class='no-cost-value'>{escape(str(value))}</span>"


def _money_html(value: Any, currency: str, *, signed: bool = False) -> str:
    number = _number(value)
    if number is None or not currency:
        return escape("Não calculável")
    rendered = f"{currency} {number:+.8f}" if signed else f"{currency} {number:.8f}"
    return _no_cost_html(rendered) if _is_explicit_zero_cost(value) else escape(rendered)


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


def _payload_block(title: str, value: Any, *, truncated: bool = False, digest: Any = None) -> str:
    text = "Não persistido." if value in (None, "") else str(value)
    notice = ""
    if truncated:
        notice = "<div class='notice warn'>Conteúdo truncado pelo limite configurado do RASAi."
        if digest:
            notice += f" SHA-256 integral: <code>{escape(str(digest))}</code>."
        notice += "</div>"
    return (
        f"<h4>{escape(title)}</h4>"
        f"<pre class='ai-exchange-payload'>{escape(text)}</pre>"
        + notice
    )


def _render_usage(
    attempts: list[Mapping[str, Any]],
    *,
    exchanges: list[Mapping[str, Any]] | None = None,
    forecast: Mapping[str, Any] | None = None,
) -> str:
    rows: list[str] = []
    details: list[str] = []
    costs: dict[str, float] = {}
    total_input = total_cached = total_output = total_reasoning = 0
    unpriced = 0
    exchange_rows = exchanges or []
    exchange_by_sequence = {
        int(item.get("sequence_no") or 0): item
        for item in exchange_rows
        if int(item.get("sequence_no") or 0) > 0
    }

    for ordinal, item in enumerate(attempts, 1):
        attempt_no = int(item.get("attempt_no") or ordinal)
        round_no = int(item.get("round_no") or 1)
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
        zero_cost = bool(currency) and _is_explicit_zero_cost(amount)
        rendered_cost_html = _no_cost_html(rendered_cost) if zero_cost else escape(rendered_cost)
        input_html = _no_cost_html(f"{input_tokens:,}") if zero_cost else f"{input_tokens:,}"
        output_html = _no_cost_html(f"{output:,}") if zero_cost else f"{output:,}"

        error_class = str(item.get("error_class") or "")
        error_label = _ERROR_LABEL.get(error_class, error_class or "-")
        decision = str(item.get("decision") or "")
        decision_label = _DECISION_LABEL.get(decision, decision or "-")
        if item.get("retry_eligible"):
            decision_label += " · elegível para nova rodada"

        rows.append(
            "<tr>"
            f"<td>{round_no}</td>"
            f"<td>{attempt_no}</td>"
            f"<td>{escape(str(item.get('provider') or '-'))}</td>"
            f"<td>{escape(str(item.get('model') or '-'))}</td>"
            f"<td>{escape(str(item.get('reasoning') or '-'))}</td>"
            f"<td>{escape(_display_status(item.get('status')))}</td>"
            f"<td>{escape(error_label)}</td>"
            f"<td>{escape(decision_label)}</td>"
            f"<td>{input_html}</td><td>{output_html}</td>"
            f"<td>{rendered_cost_html}</td>"
            f"<td>{int(item.get('duration_ms') or 0):,} ms</td>"
            "</tr>"
        )

        exchange = exchange_by_sequence.get(attempt_no)
        detail = (
            f"<details class='details ai-exchange-detail'><summary>Rodada {round_no} · tentativa {attempt_no} · "
            f"{escape(str(item.get('provider') or 'IA'))} / {escape(str(item.get('model') or '-'))}</summary>"
        )
        detail += "<div class='detail-body'>"
        detail += (
            f"<p><strong>Resultado:</strong> {escape(_display_status(item.get('status')))}"
            f"<br><strong>Decisão:</strong> {escape(decision_label)}"
            f"<br><strong>Erro:</strong> {escape(error_label)}"
            f"<br><strong>HTTP:</strong> {escape(str(item.get('http_status') or '-'))}"
            f"<br><strong>Espera sugerida (Retry-After):</strong> {escape(str(item.get('retry_after_seconds') if item.get('retry_after_seconds') is not None else '-'))}</p>"
        )
        if exchange is not None:
            detail += _payload_block(
                "Solicitação enviada à IA",
                exchange.get("request_payload"),
                truncated=bool(exchange.get("request_truncated")),
                digest=exchange.get("request_sha256"),
            )
            detail += _payload_block(
                "Resposta recebida da IA",
                exchange.get("response_payload"),
                truncated=bool(exchange.get("response_truncated")),
                digest=exchange.get("response_sha256"),
            )
        else:
            detail += "<div class='notice'>Solicitação/resposta não foram encontradas no artifact sanitizado desta tentativa.</div>"
        detail += "</div></details>"
        details.append(detail)

    if not rows:
        return "<p class='subtle'>Nenhuma chamada de IA foi materializada nesta análise.</p>"

    rendered_costs = " · ".join(
        f"{currency} {amount:.8f}" for currency, amount in sorted(costs.items())
    ) or "não calculável"
    zero_total_confirmed = bool(attempts) and all(
        bool(str(item.get("currency") or "").strip()) and _is_explicit_zero_cost(item.get("estimated_cost"))
        for item in attempts
    )
    rendered_costs_html = _no_cost_html(rendered_costs) if zero_total_confirmed else escape(rendered_costs)
    summary_input_html = _no_cost_html(f"{total_input:,}") if zero_total_confirmed else f"{total_input:,}"
    summary_output_html = _no_cost_html(f"{total_output:,}") if zero_total_confirmed else f"{total_output:,}"
    unpriced_note = f" · {unpriced} tentativa(s) sem custo calculável" if unpriced else ""

    forecast = forecast or {}
    forecast_currency = str(forecast.get("currency") or "")
    expected = _number(forecast.get("expected_cost"))
    likely_high = _number(forecast.get("likely_high"))
    potential = _number(forecast.get("potential"))
    observed = costs.get(forecast_currency) if forecast_currency else None
    deviation = observed - expected if observed is not None and expected is not None else None
    deviation_percent = (
        deviation / abs(expected) * 100.0
        if deviation is not None and expected not in (None, 0)
        else None
    )
    observed_html = (
        _no_cost_html(f"{forecast_currency} {observed:.8f}")
        if zero_total_confirmed and forecast_currency and observed is not None
        else escape(f"{forecast_currency} {observed:.8f}" if forecast_currency and observed is not None else rendered_costs)
    )
    forecast_confidence = str(forecast.get("confidence") or "NENHUMA").strip().upper()
    forecast_confidence_label = {
        "ALTA": "Alta",
        "MÉDIA": "Média",
        "MEDIA": "Média",
        "BAIXA": "Baixa",
        "NENHUMA": "Nenhuma",
    }.get(forecast_confidence, forecast_confidence.title() or "Nenhuma")
    pricing_coverage = _number(forecast.get("pricing_coverage"))
    pricing_coverage_label = (
        f"{pricing_coverage * 100:.0f}%"
        if pricing_coverage is not None
        else "Não calculável"
    )
    confidence_basis = str(forecast.get("confidence_basis") or "").strip() or "Não informada."

    forecast_html = (
        "<div class='ai-usage-summary'>"
        f"<div><small>Custo esperado</small><strong>{_money_html(forecast.get('expected_cost'), forecast_currency)}</strong></div>"
        f"<div><small>Máximo estimado da 1ª rodada</small><strong>{_money_html(forecast.get('likely_high'), forecast_currency)}</strong></div>"
        f"<div><small>Cenário potencial com nova tentativa</small><strong>{_money_html(forecast.get('potential'), forecast_currency)}</strong></div>"
        f"<div><small>Custo observado</small><strong>{observed_html}</strong></div>"
        f"<div><small>Desvio monetário</small><strong>{_money_html(deviation, forecast_currency, signed=True) if deviation is not None else escape('Não calculável')}</strong></div>"
        f"<div><small>Desvio percentual</small><strong>{escape(f'{deviation_percent:+.2f}%' if deviation_percent is not None else 'Não calculável')}</strong></div>"
        f"<div><small>Confiança da previsão</small><strong>{escape(forecast_confidence_label)}</strong></div>"
        f"<div><small>Cobertura de preços</small><strong>{escape(pricing_coverage_label)}</strong></div>"
        "</div>"
        f"<p class='subtle'><strong>Base da confiança:</strong> {escape(confidence_basis)}</p>"
    )

    return f"""
    {forecast_html}
    <div class='ai-usage-summary'>
      <div><small>Tentativas</small><strong>{len(rows)}</strong></div>
      <div><small>Rodadas</small><strong>{max(int(item.get('round_no') or 1) for item in attempts)}</strong></div>
      <div><small>Tokens de entrada</small><strong>{summary_input_html}</strong></div>
      <div><small>Tokens de cache</small><strong>{total_cached:,}</strong></div>
      <div><small>Tokens de saída</small><strong>{summary_output_html}</strong></div>
      <div><small>Tokens de raciocínio</small><strong>{total_reasoning:,}</strong></div>
      <div><small>Custo técnico observado</small><strong>{rendered_costs_html}</strong></div>
    </div>
    <div class='table-wrap'><table><thead><tr><th>Rodada</th><th>Tentativa</th><th>Provedor</th><th>Modelo</th><th>Raciocínio</th><th>Resultado</th><th>Erro</th><th>Decisão</th><th>Entrada</th><th>Saída</th><th>Custo</th><th>Duração</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    <h3>Comunicação com as IAs</h3>
    <p class='subtle'>Os payloads abaixo são os envelopes sanitizados efetivamente capturados pelo RASAi. Credenciais e raciocínio privado não são persistidos. Por auditabilidade, campos e enums dentro do payload técnico bruto permanecem na forma canônica de origem, inclusive quando usam en-US; os rótulos da interface são apresentados em pt-BR.</p>
    {''.join(details)}
    <p class='subtle'>Custo técnico calculado a partir do uso reportado pelos adaptadores; não é fatura do provedor{escape(unpriced_note)}.</p>
    """



def _candidate_cost_text(item: Mapping[str, Any]) -> str:
    amount = _number(item.get("estimated_cost"))
    currency = str(item.get("currency") or "").strip()
    if amount is None:
        return "Não calculável"
    return f"{currency + ' ' if currency else ''}{amount:.8f}"


def _candidate_cost_html(item: Mapping[str, Any]) -> str:
    text = _candidate_cost_text(item)
    return _no_cost_html(text) if _is_explicit_zero_cost(item.get("estimated_cost")) else escape(text)


def _render_orchestration(ai: Mapping[str, Any]) -> str:
    candidates = [item for item in ai.get("candidates", ()) if isinstance(item, Mapping)]
    excluded = [str(item) for item in ai.get("excluded_candidates", ()) if str(item)]
    rows = "".join(
        "<tr>"
        f"<td>{index}</td>"
        f"<td>{escape(str(item.get('provider') or '-'))}</td>"
        f"<td>{escape(str(item.get('model') or '-'))}</td>"
        f"<td>{escape(str(item.get('reasoning_profile') or '-'))}</td>"
        f"<td>{_candidate_cost_html(item)}</td>"
        "</tr>"
        for index, item in enumerate(candidates, 1)
    )
    excluded_html = "".join(f"<li>{escape(item)}</li>" for item in excluded) or "<li>Nenhuma exclusão registrada.</li>"
    fallback = "Sim" if len(candidates) > 1 else "Não"
    rounds = int(ai.get("rounds") or 0)
    return f"""
    <div class='ai-usage-summary'>
      <div><small>Candidatos elegíveis</small><strong>{len(candidates)}</strong></div>
      <div><small>Contingência disponível</small><strong>{fallback}</strong></div>
      <div><small>Rodadas executadas</small><strong>{rounds}</strong></div>
      <div><small>Limite de rodadas</small><strong>2</strong></div>
    </div>
    <div class='table-wrap'><table><thead><tr><th>Ordem</th><th>Provedor</th><th>Modelo</th><th>Raciocínio</th><th>Custo estimado</th></tr></thead><tbody>{rows or "<tr><td colspan='5'>Nenhum candidato elegível.</td></tr>"}</tbody></table></div>
    <details class='details'><summary>Provedores/configurações não participantes</summary><ul>{excluded_html}</ul></details>
    """


def _render_ai_section(payload: Mapping[str, Any]) -> str:
    ai = payload.get("ai")
    if not isinstance(ai, Mapping) or not bool(ai.get("requested")):
        return ""
    status = str(ai.get("status") or "UNKNOWN").upper()
    changes = [item for item in payload.get("changes", ()) if isinstance(item, Mapping)]
    attempts = [item for item in ai.get("attempts", ()) if isinstance(item, Mapping)]
    exchanges = [item for item in payload.get("_exchanges", ()) if isinstance(item, Mapping)]
    forecast = ai.get("forecast") if isinstance(ai.get("forecast"), Mapping) else {}
    orchestration = _render_orchestration(ai)
    if str(payload.get("contract") or "") == "CONSOLIDATED-LONGITUDINAL-001":
        projection = ai.get("context_projection") if isinstance(ai.get("context_projection"), Mapping) else {}
        projection_note = (
            f"<p><strong>Contexto IA:</strong> {escape(str(projection.get('level') or '-'))}"
            f" · entrada estimada {escape(str(projection.get('estimated_input_tokens') or '-'))} tokens"
            f" · limite {escape(str(projection.get('max_input_hint_tokens') or '-'))}.</p>"
            if projection else ""
        )
        return f"""
<section id='specialist-ai' class='panel ai-section'>
  <div class='ai-origin'>Rastreabilidade da execução por IA</div>
  <h2>Governança da IA, custos e comunicações</h2>
  <p>Esta seção registra como a análise longitudinal foi executada. A interpretação, os trade-offs e a estratégia permanecem na seção <strong>Análise longitudinal assistida por IA</strong>.</p>
  {projection_note}
  <h3>Orquestração</h3>
  {orchestration}
  <details><summary>Uso, custo e comunicação da IA</summary>{_render_usage(attempts, exchanges=exchanges, forecast=forecast)}</details>
</section>
"""
    if status != "COMPLETE":
        reason = str(ai.get("reason") or _display_status(status))
        return f"""
<section id='specialist-ai' class='panel ai-section'>
  <div class='ai-origin'>Conteúdo assistido por IA · origem explicitamente identificada</div>
  <h2>Análise especialista por IA não concluída</h2>
  <p>A análise determinística permanece válida e independente da IA.</p>
  <p class='notice warning'><strong>Estado:</strong> {escape(_display_status(status))} · {escape(reason)}</p>
  <h3>Orquestração</h3>
  {orchestration}
  <details><summary>Uso, custo e comunicação da IA nesta tentativa</summary>{_render_usage(attempts, exchanges=exchanges, forecast=forecast)}</details>
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
  <h3>Orquestração e custo</h3>
  {orchestration}
  {_render_improvements(changes)}
  <div class='priority-legend' aria-label='Legenda de prioridades'>
    <span class='priority-badge priority-p0'>P0 · Crítica</span><span class='priority-badge priority-p1'>P1 · Alta</span><span class='priority-badge priority-p2'>P2 · Média</span><span class='priority-badge priority-p3'>P3 · Baixa</span>
  </div>
  <div class='ai-card-grid'>{''.join(cards) or "<p class='subtle'>Nenhuma recomendação por tópico foi retornada.</p>"}</div>
  <details class='details'><summary>Uso, custo e comunicação da IA nesta análise</summary>{_render_usage(attempts, exchanges=exchanges, forecast=forecast)}</details>
  <p class='notice info'><strong>Limite:</strong> esta seção interpreta evidências persistidas. Associação temporal não é causalidade; recomendações de IA exigem revisão humana.</p>
</section>
"""


def _presentation_css() -> str:
    return f"""
<style id='{_PRESENTATION_STYLE_ID}'>
.metric-grid>div{{display:flex;flex-direction:column;justify-content:flex-start;min-height:96px;gap:5px}}
.metric-grid>div>small:first-child{{font-size:.76rem;font-weight:600;line-height:1.25;letter-spacing:.01em;margin:0 0 8px;text-transform:none;color:var(--muted)}}
.metric-grid>div>strong{{display:block;font-size:1.28rem;font-weight:750;line-height:1.1;font-variant-numeric:tabular-nums;margin-top:auto;color:var(--ink)}}
.findings-metric-grid>div>strong{{margin-top:auto}}.findings-metric-grid>div{{align-self:stretch}}
body.cons-decision-ready main details{{border:1px solid var(--line);border-radius:8px;background:#fbfcfe;overflow:hidden;padding:0;margin:14px 0}}
body.cons-decision-ready main details>summary{{cursor:pointer;font-weight:700;padding:11px 13px;background:#f3f6fb;list-style:none;display:flex;align-items:center;gap:8px}}
body.cons-decision-ready main details>summary::-webkit-details-marker{{display:none}}
body.cons-decision-ready main details>summary::before{{content:'›';display:inline-block;font-size:1.25rem;line-height:1;transition:transform .15s ease;flex:0 0 auto}}
body.cons-decision-ready main details[open]>summary::before{{transform:rotate(90deg)}}
body.cons-decision-ready main details[open]>summary{{border-bottom:1px solid var(--line)}}
.metric.signal-positive,.signal-positive{{background:var(--green-soft)!important;border-color:rgba(111,159,130,.45)!important;border-left:4px solid var(--green)!important}}
.metric.signal-warning,.signal-warning{{background:var(--amber-soft)!important;border-color:rgba(178,134,79,.42)!important;border-left:4px solid var(--amber)!important}}
.metric.signal-negative,.signal-negative{{background:var(--red-soft)!important;border-color:rgba(185,108,112,.45)!important;border-left:4px solid var(--red)!important}}
.status-pill,.priority-badge,.signal-key,.ai-origin{{display:inline-flex;align-items:center;border-radius:999px;padding:3px 8px;font-size:.76rem;font-weight:750;line-height:1.35}}
.status-positive{{background:var(--green-soft);color:#356b49}}.status-warning{{background:var(--amber-soft);color:#7c5728}}.status-negative{{background:var(--red-soft);color:#8f4248}}
.ai-section{{border-top:4px solid var(--blue)}}.ai-origin{{background:#eaf0fb;color:#3c5e9d;margin-bottom:8px}}.ai-origin.compact{{margin:0 0 6px;padding:2px 7px}}
.ai-summary{{background:var(--soft);border-left:4px solid var(--blue);padding:12px 14px;border-radius:6px;margin:12px 0 16px}}.ai-summary h3{{margin:0 0 6px}}
.priority-legend{{display:flex;gap:7px;flex-wrap:wrap;margin:14px 0}}.priority-p0{{background:var(--red-soft);color:#8f4248}}.priority-p1{{background:var(--amber-soft);color:#7c5728}}.priority-p2{{background:#eaf0fb;color:#3c5e9d}}.priority-p3{{background:var(--green-soft);color:#356b49}}
.ai-card-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}}.ai-card{{background:#fbfcfe;border:1px solid var(--line);border-radius:8px;padding:14px}}.ai-card.priority-p0{{border-left:5px solid var(--red)}}.ai-card.priority-p1{{border-left:5px solid var(--amber)}}.ai-card.priority-p2{{border-left:5px solid var(--blue)}}.ai-card.priority-p3{{border-left:5px solid var(--green)}}
.page-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}}.grid-2{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}.strategy-grid{{align-items:stretch;margin:8px 0 4px}}.strategy-card{{background:#f8fafc;border:1px solid var(--line);border-radius:10px;padding:14px 16px}}.strategy-card h4{{margin:0 0 8px;color:var(--ink)}}.strategy-card ul{{margin:0;padding-left:20px}}.strategy-card li+li{{margin-top:3px}}.page-card{{background:#fbfcfe;border:1px solid var(--line);border-radius:8px;padding:14px}}.page-card h3{{margin-top:4px}}.page-card h4{{margin:12px 0 5px}}
.ai-card-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}}.ai-card h4{{margin:12px 0 5px}}.confidence-line{{font-size:.9rem;color:var(--muted)}}
.improvement-highlight{{margin:16px 0;padding:14px;border:1px solid var(--line);border-radius:8px;background:#fbfcfe}}.improvement-highlight h3{{margin:0 0 5px}}.improvement-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}}.improvement-item{{border-radius:7px;padding:11px}}.improvement-item h4{{margin:8px 0 4px}}.improvement-values{{font-size:1.08rem;font-weight:700;font-variant-numeric:tabular-nums}}.empty-highlight{{background:var(--soft)}}
.ai-usage-summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;margin:12px 0}}.ai-usage-summary>div{{background:#f7f9fc;border:1px solid var(--line);border-radius:7px;padding:10px}}.ai-usage-summary strong{{display:block;font-size:1.08rem;font-variant-numeric:tabular-nums}}.ai-exchange-payload{{max-height:420px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:#111827;color:#e5e7eb;border-radius:7px;padding:12px}}.ai-exchange-detail{{margin:10px 0}}
.decision-hero{{background:linear-gradient(180deg,#fffefd 0%,#f8faff 100%);border:1px solid rgba(99,127,194,.22);box-shadow:0 12px 32px rgba(47,58,78,.06)}}.decision-eyebrow{{font-size:.76rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#5e73a3}}.decision-title-row{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}}.decision-title-row h2{{font-size:1.55rem;margin:3px 0 5px}}.decision-state{{display:inline-flex;border-radius:999px;padding:4px 9px;font-size:.76rem;font-weight:800;white-space:nowrap}}.decision-state.good{{background:var(--green-soft);color:#356b49}}.decision-state.warn{{background:var(--amber-soft);color:#7c5728}}.decision-state.bad{{background:var(--red-soft);color:#8f4248}}.decision-state.info{{background:#eaf0fb;color:#3c5e9d}}.decision-alert{{padding:11px 13px;border-radius:7px;margin:12px 0}}.decision-alert.bad{{background:var(--red-soft);border-left:4px solid var(--red)}}.decision-alert.warn{{background:var(--amber-soft);border-left:4px solid var(--amber)}}.ai-reliability{{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;border-radius:8px;padding:10px 12px;margin:10px 0 12px;border:1px solid var(--line)}}.ai-reliability.good{{background:var(--green-soft)}}.ai-reliability.warn{{background:var(--amber-soft)}}.ai-reliability.bad{{background:var(--red-soft)}}.ai-reliability>div strong{{display:block;font-size:1.08rem}}.ai-reliability>div span{{display:block;color:var(--muted);font-size:.82rem}}.ai-reliability details{{max-width:62%;margin:0}}.ai-confidence{{display:inline-flex;border-radius:999px;padding:3px 7px;font-size:.72rem;font-weight:750;background:#eef2f8;color:#475c82}}.managerial-summary{{background:#eef3fb;border:1px solid rgba(99,127,194,.18);border-radius:8px;padding:14px 16px;margin:14px 0}}.decision-kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:9px;margin:10px 0}}.decision-kpis>div{{background:white;border:1px solid var(--line);border-radius:8px;padding:11px}}.decision-kpis strong{{display:block;font-size:1.35rem}}.decision-kpis span{{display:block;color:var(--muted);font-size:.76rem}}.decision-chart{{background:white;border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin:10px 0 18px}}.decision-line{{fill:none;stroke:var(--blue);stroke-width:3}}.decision-dot{{fill:var(--blue);stroke:white;stroke-width:2}}.decision-axis{{fill:var(--muted);font-size:10px}}.decision-chart-caption{{color:var(--muted);font-size:.82rem}}.decision-priority-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px}}.decision-priority{{background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px}}.decision-priority.priority-p0{{border-left:5px solid var(--red)}}.decision-priority.priority-p1{{border-left:5px solid var(--amber)}}.decision-priority.priority-p2{{border-left:5px solid var(--blue)}}.decision-priority.priority-p3{{border-left:5px solid var(--green)}}.decision-priority-head{{display:flex;gap:7px;align-items:center;flex-wrap:wrap}}.closure-overall{{display:flex;justify-content:space-between;gap:12px;align-items:center;border-radius:8px;padding:12px 14px;margin:12px 0}}.closure-overall.good{{background:var(--green-soft)}}.closure-overall.warn{{background:var(--amber-soft)}}.closure-overall.bad{{background:var(--red-soft)}}.closure-grid{{display:grid;grid-template-columns:1fr;gap:12px}}.closure-card{{background:#fbfcfe;border:1px solid var(--line);border-radius:8px;padding:11px}}.closure-card.good{{border-left:4px solid var(--green)}}.closure-card.warn{{border-left:4px solid var(--amber)}}.closure-card.bad{{border-left:4px solid var(--red)}}.closure-card.info{{border-left:4px solid var(--blue)}}.closure-head{{display:flex;justify-content:space-between;gap:8px;align-items:flex-start;font-weight:700}}.governance-panel{{background:#fafbfc}}body.cons-decision-ready nav a{{font-weight:650}}body.cons-decision-ready #scope{{margin-top:0}}
/* Alinhamento cosmético com report-catalog: cor comunica estado; não cria peso visual por fundo/tag. */
.metric.signal-positive,.metric.signal-warning,.metric.signal-negative,
.signal-positive,.signal-warning,.signal-negative{{background:#fbfcfe!important;border:1px solid var(--line)!important}}
.metric.signal-positive,.signal-positive{{border-left:3px solid var(--green)!important}}
.metric.signal-warning,.signal-warning{{border-left:3px solid var(--amber)!important}}
.metric.signal-negative,.signal-negative{{border-left:3px solid var(--red)!important}}
.metric.signal-positive>strong,.signal-positive .improvement-values{{color:var(--green)}}
.metric.signal-warning>strong{{color:var(--amber)}}
.metric.signal-negative>strong{{color:var(--red)}}
.status-pill,.priority-badge,.signal-key,.decision-state,.rasai-state-chip{{display:inline;padding:0;border:0;border-radius:0;background:transparent!important;font-size:inherit;font-weight:700;line-height:inherit}}
.status-positive,.decision-state.good,.rasai-state-chip.state-good{{color:var(--green)}}
.status-warning,.decision-state.warn,.rasai-state-chip.state-warn{{color:var(--amber)}}
.status-negative,.decision-state.bad,.rasai-state-chip.state-bad{{color:var(--red)}}
.decision-state.info,.rasai-state-chip.state-info{{color:var(--blue)}}
.rasai-state-chip.state-neutral{{color:var(--secondary-ink);font-weight:400}}
.ai-origin{{display:inline-flex;align-items:center;width:max-content;max-width:100%;color:#35568f;background:#eef3fb!important;border:1px solid #d8e2f3;border-radius:999px;padding:3px 8px;margin-bottom:8px;font-size:.72rem;font-weight:700;line-height:1.35}}
.ai-origin.compact{{margin:0 0 6px;padding:2px 7px}}
.priority-p0,.priority-p0 .priority-badge{{background:transparent;color:var(--red)}}
.priority-p1,.priority-p1 .priority-badge{{background:transparent;color:var(--amber)}}
.priority-p2,.priority-p2 .priority-badge{{background:transparent;color:var(--blue)}}
.priority-p3,.priority-p3 .priority-badge{{background:transparent;color:var(--green)}}
.ai-card,.page-card,.decision-priority,.closure-card,.decision-kpis>div,.ai-usage-summary>div{{background:#fbfcfe;border:1px solid var(--line);border-radius:10px;box-shadow:none}}
.ai-card.priority-p0,.decision-priority.priority-p0{{border-left:4px solid var(--red)}}
.ai-card.priority-p1,.decision-priority.priority-p1{{border-left:4px solid var(--amber)}}
.ai-card.priority-p2,.decision-priority.priority-p2{{border-left:4px solid var(--blue)}}
.ai-card.priority-p3,.decision-priority.priority-p3{{border-left:4px solid var(--green)}}
.closure-card.good{{border-left:3px solid var(--green)}}.closure-card.warn{{border-left:3px solid var(--amber)}}.closure-card.bad{{border-left:3px solid var(--red)}}.closure-card.info{{border-left:3px solid var(--blue)}}
.decision-hero{{background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}}
.decision-eyebrow{{font-size:.66rem;font-weight:600;letter-spacing:.09em;color:var(--muted)}}
.ai-reliability,.ai-reliability.good,.ai-reliability.warn,.ai-reliability.bad,
.closure-overall,.closure-overall.good,.closure-overall.warn,.closure-overall.bad{{background:#fbfcfe;border:1px solid var(--line)}}
.ai-reliability.good>div>strong,.closure-overall.good>strong{{color:var(--green)}}
.ai-reliability.warn>div>strong,.closure-overall.warn>strong{{color:var(--amber)}}
.ai-reliability.bad>div>strong,.closure-overall.bad>strong{{color:var(--red)}}
.ai-confidence{{display:inline;color:var(--secondary-ink);background:transparent;border:0;border-radius:0;padding:0;font-size:.78rem;font-weight:400}}
.managerial-summary{{background:#fbfcfe;border:1px solid var(--line);border-radius:10px}}
.decision-kpis strong,.ai-usage-summary strong{{font-size:1rem;font-weight:700}}
.no-cost-value{{color:var(--light-muted);font-weight:400}}
.result-value{{font-weight:700;color:var(--ink)}}.result-value.good{{color:var(--green)}}.result-value.warn{{color:var(--amber)}}.result-value.low{{color:var(--orange)}}.result-value.bad{{color:var(--red)}}.result-value.neutral{{color:var(--ink)}}
.axis-label{{font-size:10px}}
@media(min-width:780px){{.closure-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}\n@media(min-width:1280px){{.closure-grid{{grid-template-columns:repeat(3,minmax(0,1fr))}}}}\n@media(min-width:1920px){{.closure-grid{{grid-template-columns:repeat(4,minmax(0,1fr))}}}}\n@media(max-width:760px){{.ai-card-head{{display:block}}.priority-badge{{margin-top:8px}}.grid-2{{grid-template-columns:1fr}}.decision-title-row{{display:block}}.decision-title-row .decision-state{{margin-top:8px}}}}
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

    decision = _decision_context(artifact)
    if decision and "id='decision-overview'" not in rendered and 'id="decision-overview"' not in rendered:
        executive = _render_executive_decision(artifact)
        if executive:
            rendered = rendered.replace("<main>", "<main>" + executive, 1)
            rendered = rendered.replace("<body>", "<body class='cons-decision-ready'>", 1)
    if decision and "id='cons-governance'" not in rendered and 'id="cons-governance"' not in rendered:
        governance = _render_governance_section(artifact)
        if governance:
            if "<section id='method'>" in rendered:
                rendered = rendered.replace("<section id='method'>", governance + "<section id='method'>", 1)
            else:
                rendered = rendered.replace("<footer", governance + "<footer", 1)
    if decision:
        technical_nav = (
            "<a href='#technical-remediation'>Correções técnicas</a>"
            if "id='technical-remediation'" in rendered or 'id="technical-remediation"' in rendered
            else ""
        )
        ai_nav = (
            "<a href='#longitudinal-ai'>Análise por IA</a>"
            if "id='longitudinal-ai'" in rendered or 'id="longitudinal-ai"' in rendered
            else ""
        )
        modern_nav = (
            "<nav aria-label='Navegação do relatório'>"
            "<a href='#decision-overview'>Visão geral</a>"
            "<a href='#decision-priorities'>Prioridades</a>"
            "<a href='#scores'>Índice de Prontidão e dimensões</a>"
            "<a href='#longitudinal-evolution'>Evolução</a>"
            "<a href='#performance'>Performance</a>"
            "<a href='#apdex'>Experiência</a>"
            + technical_nav
            + ai_nav +
            "<a href='#cons-governance'>Governança</a>"
            "<a href='#method'>Metodologia</a>"
            "</nav>"
        )
        rendered = re.sub(r"<nav aria-label='Navegação do relatório'>.*?</nav>", modern_nav, rendered, count=1, flags=re.DOTALL)

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

    if "longitudinal-evolution" in rendered and "href='#longitudinal-evolution'" not in rendered:
        rendered = rendered.replace("<a href='#evolution'>Evolução</a>", "<a href='#evolution'>Evolução</a><a href='#longitudinal-evolution'>Trajetória</a>", 1)
    if "longitudinal-ai" in rendered and "href='#longitudinal-ai'" not in rendered:
        anchor = "<a href='#longitudinal-evolution'>Trajetória</a>" if "href='#longitudinal-evolution'" in rendered else "<a href='#evolution'>Evolução</a>"
        rendered = rendered.replace(anchor, anchor + "<a href='#longitudinal-ai'>Análise por IA</a>", 1)
    if "specialist-evolution" in rendered and "href='#specialist-evolution'" not in rendered:
        rendered = rendered.replace("<a href='#evolution'>Evolução</a>", "<a href='#evolution'>Evolução</a><a href='#specialist-evolution'>Comparação</a>", 1)
    if "specialist-ai" in rendered and "href='#specialist-ai'" not in rendered:
        rendered = rendered.replace("<a href='#specialist-evolution'>Comparação</a>", "<a href='#specialist-evolution'>Comparação</a><a href='#specialist-ai'>Análise por IA</a>", 1)

    if _PRESENTATION_STYLE_ID not in rendered:
        rendered = rendered.replace("</head>", _presentation_css() + "</head>", 1)
    return rendered



_VISIBLE_TOKEN_LABELS = {
    "MOBILE": "Dispositivo móvel",
    "BALANCED": "Balanceado",
    "COMPACT": "Compacto",
    "FULL": "Completo",
    "NONE": "Nenhum",
    "AUTO": "Automático",
    "RAW": "HTML bruto",
    "RENDERED": "HTML renderizado",
    "PARCIAL": "Parcial",
    "UNRELATED": "Configurações não equivalentes",
    "retryable": "passível de nova tentativa",
    "mobile": "dispositivo móvel",
    "benchmark_index": "índice de referência",
    "BOTH": "Mobile e Desktop",
    "GLOBAL": "Escopo global",
    "WARNING": "Atenção",
    "PASS": "Aprovado",
    "FAIL": "Não aprovado",
    "SUCCESS": "Sucesso",
    "SUCCESS_WITH_LIMITATIONS": "Sucesso com limitações",
    "COMPLETE": "Concluído",
    "COMPLETED": "Concluído",
    "COMPLETE_WITH_LIMITATIONS": "Concluído com limitações",
    "COMPLETED_WITH_LIMITATIONS": "Concluído com limitações",
    "PARTIAL": "Parcial",
    "FINAL": "Final",
    "VALID": "Válido",
    "READY": "Pronto",
    "ERROR": "Erro",
    "LOW": "Baixo",
    "MEDIUM": "Médio",
    "HIGH": "Alto",
    "CRITICAL": "Crítico",
    "INFO": "Informativo",
    "REGRESSED": "Piorou",
    "IMPROVED": "Melhorou",
    "RESOLVED": "Resolvido",
    "CHANGED": "Alterado",
    "NEW": "Novo",
    "DATA_UNAVAILABLE": "Dado indisponível",
    "NOT_FIXED": "Não corrigido",
    "FIXED": "Corrigido",
    "PERSISTING": "Persistente",
    "ABSENT": "Ausente",
    "AVAILABLE": "Disponível",
    "WIDELY_AVAILABLE": "Amplamente disponível",
    "COHERENT": "Coerente",
    "NOT_CONFIGURED": "Não configurado",
    "NOT_REQUESTED": "Não solicitado",
    "NOT_FOUND_WITHIN_DEPTH": "Não encontrado na profundidade analisada",
    "SEM_ESTADO": "Sem estado informado",
    "EVIDENCIA_PERSISTIDA": "Evidência persistida",
    "FONTE_PERSISTIDA": "Fonte persistida",
    "METRICA": "Métrica",
    "NAVIGATION_LOAD": "Carregamento da navegação",
    "USER_ACTION_DURATION": "Duração da ação do usuário",
    "MANUAL_CALIBRATION": "Calibração manual",
    "SYNTHETIC_USER_EXPERIENCE_APDEX": "Apdex sintético de experiência",
    "PAGESPEED_INSIGHTS": "PageSpeed Insights",
    "PAGESPEED_CRUX": "CrUX via PageSpeed",
    "RULE_CONDITION_MISMATCH": "Divergência na condição da regra",
    "SHARED_ACQUISITION": "Aquisição compartilhada",
    "WALL_CLOCK_TIMEOUT": "Tempo limite total excedido",
    "AI_INFERENCE": "Inferência por IA",
    "INFERENCE": "Inferência",
    "DETERMINISTIC": "Determinístico",
    "CORRELATIONAL": "Correlacional",
    "OBSERVED_API": "Observado via API",
    "OBSERVED": "Observado",
    "DEVICE_SNAPSHOT": "Captura por dispositivo",
    "COLD_CONTEXT": "Contexto frio",
    "PERSISTENTE_ATENCAO": "Persistente - requer atenção",
    "CONCLUSIVE_WITH_LIMITATIONS": "Conclusivo com limitações",
    "NON_CONCLUSIVE": "Não conclusivo",
    "EVIDENCIA_DIRETA": "Evidência direta",
    "ASSOCIACAO_FORTE": "Associação forte",
    "GEO_AI_READINESS": "Prontidão para GEO e IA",
    "UX_APDEX": "Apdex de experiência",
    "CONTENT_SEMANTICS": "Conteúdo e semântica",
    "PERFORMANCE": "Desempenho",
    "ACCESSIBILITY": "Acessibilidade",
    "INFRASTRUCTURE": "Infraestrutura",
    "SECURITY": "Segurança",
    "CONTENT": "Conteúdo",
    "COMPETITIVE": "Inteligência competitiva",
    "QUERY_INTENT": "Intenção de busca",
    "RULE": "Regra",
    "SCORE": "Pontuação",
    "FINDINGS": "Ocorrências",
    "REVIEW_AND_CORRECT": "Revisar e corrigir",
    "ADD_FACTUAL_CONTEXT": "Adicionar contexto factual",
    "ADD_QUALIFIERS": "Adicionar qualificadores",
    "ADD_ATTRIBUTION": "Adicionar atribuição",
    "CLOSE_INTENT_GAPS": "Tratar lacunas de intenção",
    "TITLE_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS": "Alinhamento entre título e consulta inferior ao dos líderes observados",
    "INTENT_GAP_EVIDENCE": "Evidência de lacuna de intenção",
    "FACTUAL_CONTEXT_GAP": "Lacuna de contexto factual",
    "ATTRIBUTION_EVIDENCE_GAP": "Lacuna de atribuição ou evidência",
}
_VISIBLE_PHRASE_LABELS = {
    "Canonical declarations must be interpretable and non-conflicting": "Declarações canonical devem ser interpretáveis e não conflitantes",
    "robots.txt must be interpretable when present": "robots.txt deve ser interpretável quando presente",
    "Sitemap resources must be acquired and interpreted when available": "Recursos de sitemap devem ser adquiridos e interpretados quando disponíveis",
    "Comparar RAW e RENDERED": "Comparar HTML bruto e HTML renderizado",
    "findings NEW": "novas ocorrências",
    "findings": "ocorrências",
    "evidence-bound": "baseada em evidências",
    "root cause": "causa raiz",
    "claims": "afirmações",
    "Mobile": "dispositivo móvel",
    "same-session": "mesma sessão",
    "Claims": "Afirmações",
    "claim": "afirmação",
    "freshness": "atualização",
    "fallback": "alternativa genérica",
    "GEO / AI Readiness": "GEO / preparação para IA",
    "main thread": "thread principal",
    "Main thread": "Thread principal",
    "benchmark index": "índice de referência",
    "Benchmark index": "Índice de referência",
    "retryable failed": "falha passível de nova tentativa",
    "Performance mobile": "Desempenho em dispositivo móvel",
}
_VISIBLE_PROTECTED_RE = re.compile(
    r"(?is)<(?:pre|code|script|style)\b.*?</(?:pre|code|script|style)>"
)


def _humanize_visible_text_nodes(html: str) -> str:
    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        token = f"__RASAI_VISIBLE_PROTECTED_{len(protected)}__"
        protected.append(match.group(0))
        return token

    rendered = _VISIBLE_PROTECTED_RE.sub(protect, html)

    def humanize(match: re.Match[str]) -> str:
        text = match.group(1)
        for raw, label in _VISIBLE_PHRASE_LABELS.items():
            text = text.replace(raw, label)
        for raw, label in _VISIBLE_TOKEN_LABELS.items():
            text = re.sub(rf"\b{re.escape(raw)}\b", label, text)
        text = (
            text.replace("os ocorrências", "as ocorrências")
            .replace("Os ocorrências", "As ocorrências")
            .replace("dos ocorrências", "das ocorrências")
            .replace("Dos ocorrências", "Das ocorrências")
            .replace("esses ocorrências", "essas ocorrências")
            .replace("Esses ocorrências", "Essas ocorrências")
            .replace("estes ocorrências", "estas ocorrências")
            .replace("Estes ocorrências", "Estas ocorrências")
            .replace("novos ocorrências", "novas ocorrências")
            .replace("Novos ocorrências", "Novas ocorrências")
        )
        return ">" + text + "<"

    rendered = re.sub(r">([^<>]+)<", humanize, rendered)
    for index, block in enumerate(protected):
        rendered = rendered.replace(f"__RASAI_VISIBLE_PROTECTED_{index}__", block)
    return rendered


_VISIBLE_LABELS = {
    "Answerability": "Capacidade de resposta",
    "Citation Readiness": "Preparação para citação",
    "Structured Data": "Dados estruturados",
    "Evidence & Trust": "Evidências e confiabilidade",
    "Intent Coverage": "Cobertura de intenções",
    "Entity Clarity": "Clareza de entidades",
    "Semantic Structure": "Estrutura semântica",
    "Content Value": "Valor do conteúdo",
    "Discovery & Crawler Access": "Acesso e descoberta",
    "Rendering & Extractability": "Renderização e extração",
    "Indexability": "Indexabilidade e canonicalização",
    "Lighthouse Performance": "Lighthouse Performance",
    "TBT lab": "Total Blocking Time",
    "LCP lab": "LCP de laboratório",
    "FCP lab": "FCP de laboratório",
    "CLS lab": "CLS de laboratório",
    "Mobile": "Dispositivo móvel",
    "COMPLETE": "Completo",
    "COMPLETED": "Concluído",
    "COMPLETE_WITH_LIMITATIONS": "Concluído com limitações",
    "COMPLETED_WITH_LIMITATIONS": "Concluído com limitações",
    "FINAL": "Final",
    "INCOMPLETE": "Incompleto",
    "PARTIAL": "Parcial",
    "CONSOLIDATED": "Consolidado",
    "PASS": "Aprovado",
    "FAIL": "Não aprovado",
    "WARNING": "Atenção",
    "NOT_APPLICABLE": "Não aplicável",
    "UNAVAILABLE": "Indisponível",
    "UNKNOWN": "Desconhecido",
}


def _visible_label(text: str) -> str:
    return _VISIBLE_LABELS.get(text, text)


def _reader_counter_counts(artifact: Mapping[str, Any] | None) -> tuple[int, int, int]:
    if not isinstance(artifact, Mapping):
        return 0, 0, 0
    initial_final = artifact.get("initial_to_final")
    changes = initial_final.get("changes", ()) if isinstance(initial_final, Mapping) else ()
    material = [item for item in changes if isinstance(item, Mapping)]
    improved = sum(1 for item in material if str(item.get("status") or "").upper() in {"IMPROVED", "RESOLVED"})
    regressed = sum(1 for item in material if str(item.get("status") or "").upper() in {"REGRESSED", "NEW"})
    other = len(material) - improved - regressed
    return improved, regressed, max(0, other)


def _reader_ai_chip(artifact: Mapping[str, Any] | None) -> str:
    ai = artifact.get("ai") if isinstance(artifact, Mapping) and isinstance(artifact.get("ai"), Mapping) else None
    requested = bool(ai and ai.get("requested"))
    status = str(ai.get("status") or "UNKNOWN").upper() if ai else "NOT_REQUESTED"
    if requested and status == "COMPLETE":
        return "<span class='rasai-state-chip state-good'>IA especialista concluída</span>"
    if requested:
        return "<span class='rasai-state-chip state-warn'>IA especialista não concluída</span>"
    return "<span class='rasai-state-chip state-neutral'>IA especialista não solicitada</span>"


def _humanize_exact_visible_labels(html: str) -> str:
    rendered = html
    for raw, label in _VISIBLE_LABELS.items():
        rendered = rendered.replace(f">{raw}<", f">{label}<")
    rendered = rendered.replace("Evolução da SARI", "Evolução do SARI")
    rendered = rendered.replace("SARI - Search &amp; AI Readiness Index", "Search &amp; AI Readiness Index - Índice de Prontidão Search &amp; IA")
    rendered = rendered.replace("SARI - Search & AI Readiness Index", "Search & AI Readiness Index - Índice de Prontidão Search & IA")
    rendered = rendered.replace("SARI e dimensões de Search &amp; AI", "Índice de Prontidão Search &amp; IA e dimensões")
    rendered = rendered.replace("SARI e dimensões de Search & AI", "Índice de Prontidão Search & IA e dimensões")
    return _humanize_visible_text_nodes(rendered)


_AUDIT_ID_RE = re.compile(r"\bAUD-[A-Z0-9][A-Z0-9-]*\b")
_AUDIT_LINK_PROTECTED_RE = re.compile(
    r"(?is)<(?:pre|script|style|svg)\b.*?</(?:pre|script|style|svg)>|<a\b.*?</a>"
)


def _audit_report_href(audit_id: str) -> str:
    return f"../../{audit_id}/report-catalog/index.html"


def _canonical_audit_ids(artifact: Mapping[str, Any] | None) -> set[str]:
    """Return navigable AUD IDs; stale source reports are deliberately not linked."""
    if not isinstance(artifact, Mapping):
        return set()

    context = artifact.get("decision_context")
    governance = context.get("source_governance") if isinstance(context, Mapping) else None
    audits = governance.get("audits") if isinstance(governance, Mapping) else None
    if isinstance(audits, (list, tuple)):
        governed = [item for item in audits if isinstance(item, Mapping)]
        if any("report_catalog_fresh" in item for item in governed):
            return {
                str(item.get("audit_id") or "")
                for item in governed
                if str(item.get("audit_id") or "").startswith("AUD-")
                and item.get("report_catalog_fresh") is True
            }

    result: set[str] = set()
    scope = artifact.get("scope")
    if isinstance(scope, Mapping):
        values = scope.get("audit_ids")
        if isinstance(values, (list, tuple)):
            result.update(str(item) for item in values if str(item).startswith("AUD-"))
    if isinstance(audits, (list, tuple)):
        for item in audits:
            if isinstance(item, Mapping):
                audit_id = str(item.get("audit_id") or "")
                if audit_id.startswith("AUD-"):
                    result.add(audit_id)
    return result


def _strip_disallowed_existing_audit_links(
    html: str,
    allowed_audit_ids: set[str] | None,
) -> str:
    """Remove renderer-created AUD links that governance has declared non-navigable."""
    if allowed_audit_ids is None:
        return html
    pattern = re.compile(
        r"(?is)<a\b(?=[^>]*\bhref=['\"]\.\./\.\./(AUD-[A-Z0-9-]+)/report-catalog/index\.html['\"])[^>]*>(.*?)</a>"
    )

    def replace(match: re.Match[str]) -> str:
        audit_id = str(match.group(1) or "")
        return match.group(0) if audit_id in allowed_audit_ids else match.group(2)

    return pattern.sub(replace, html)


def enforce_source_report_navigation(html: str, governance: Mapping[str, Any] | None) -> str:
    """Apply source report freshness to links already emitted by the base renderer."""
    if not isinstance(governance, Mapping):
        return html
    audits = [item for item in governance.get("audits", ()) if isinstance(item, Mapping)]
    if not audits or not any("report_catalog_fresh" in item for item in audits):
        return html
    allowed = {
        str(item.get("audit_id") or "")
        for item in audits
        if str(item.get("audit_id") or "").startswith("AUD-")
        and item.get("report_catalog_fresh") is True
    }
    return _strip_disallowed_existing_audit_links(html, allowed)


def _link_visible_audit_ids(
    html: str,
    allowed_audit_ids: set[str] | None = None,
) -> str:
    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"__RASAI_AUDIT_PROTECTED_{len(protected) - 1}__"

    masked = _AUDIT_LINK_PROTECTED_RE.sub(protect, html)
    parts = re.split(r"(<[^>]+>)", masked)
    for index, part in enumerate(parts):
        if not part or part.startswith("<") or part.startswith("__RASAI_AUDIT_PROTECTED_"):
            continue
        def link(match: re.Match[str]) -> str:
            audit_id = match.group(0)
            if allowed_audit_ids is not None and audit_id not in allowed_audit_ids:
                return audit_id
            return (
                f"<a class='audit-link' href='{escape(_audit_report_href(audit_id), quote=True)}' "
                f"target='_blank' rel='noopener noreferrer'>{escape(audit_id)}</a>"
            )
        parts[index] = _AUDIT_ID_RE.sub(link, part)
    rendered = "".join(parts)
    for index, block in enumerate(protected):
        rendered = rendered.replace(f"__RASAI_AUDIT_PROTECTED_{index}__", block)
    return rendered


def finalize_reader_experience(html: str, artifact: Mapping[str, Any] | None = None) -> str:
    """Finalize only the CONS human-facing layer after shared reader UX injection."""
    rendered = _humanize_exact_visible_labels(html)
    if "class='cons-header-shell'" not in rendered and 'class="cons-header-shell"' not in rendered:
        rendered = re.sub(
            r"<header>(.*?)</header>",
            r"<header><div class='cons-header-shell'>\1</div></header>",
            rendered,
            count=1,
            flags=re.DOTALL,
        )
    if "rasai-cons-header-alignment" not in rendered:
        layout_css = (
            "<style id='rasai-cons-header-alignment'>"
            "header{padding:24px 0}.cons-header-shell{margin:0;padding:0 26px}"
            "nav{padding-left:26px;padding-right:26px}"
            ".rasai-analysis-status[data-rasai-consolidated-experience='true']{padding:16px 0;background:#fff!important;border:1px solid var(--line)!important;border-left:1px solid var(--line)!important;box-shadow:var(--shadow);border-radius:14px}"
            ".rasai-analysis-status-shell{margin:0;padding:0 26px;box-sizing:border-box}"
            ".rasai-analysis-status.state-good,.rasai-analysis-status.state-warn,.rasai-analysis-status.state-bad,.rasai-analysis-status.state-info{background:#fff!important;border-color:var(--line)!important}"
            ".rasai-status-badge,.rasai-state-chip{display:inline;padding:0;border:0!important;border-radius:0;background:transparent!important;font-size:inherit;font-weight:600;line-height:inherit}"
            ".rasai-state-chip.state-good,.state-good.rasai-status-badge{color:var(--green)!important}.rasai-state-chip.state-warn,.state-warn.rasai-status-badge{color:var(--amber)!important}.rasai-state-chip.state-bad,.state-bad.rasai-status-badge{color:var(--red)!important}.rasai-state-chip.state-info,.state-info.rasai-status-badge{color:var(--blue)!important}.rasai-state-chip.state-neutral,.state-neutral.rasai-status-badge{color:var(--secondary-ink)!important;font-weight:400}"
            ".rasai-status-kicker{font-size:.66rem;font-weight:600;color:var(--muted)}"
            ".rasai-help-dialog{border:1px solid var(--line)!important;border-radius:14px!important;background:#fff;color:var(--ink);box-shadow:0 20px 60px rgba(16,24,40,.18)}"
            ".rasai-help-dialog-head{background:#fff!important;border-bottom:1px solid var(--line)!important}.rasai-help-dialog h2,.rasai-help-dialog h3,.rasai-help-dialog strong{color:var(--ink)}"
            ".rasai-help-open,.rasai-help-close{border:1px solid #bdc8da!important;background:#fff!important;color:var(--blue)!important;border-radius:8px!important;font-weight:600!important}"
            "@media(max-width:760px){header{padding:18px 0}.cons-header-shell{padding:0 18px}nav{padding-left:16px;padding-right:16px}.rasai-analysis-status[data-rasai-consolidated-experience='true']{padding:14px 0}.rasai-analysis-status-shell{padding:0 18px}.ai-reliability{display:block}.ai-reliability details{max-width:none;margin-top:8px}}"
            "</style>"
        )
        rendered = rendered.replace("</head>", layout_css + "</head>", 1)

    improved, regressed, other = _reader_counter_counts(artifact)
    chips = (
        _reader_ai_chip(artifact)
        + f"<span class='rasai-state-chip {'state-good' if improved else 'state-neutral'}'>{improved} melhoria(s) ou resolução(ões) entre marco inicial e final</span>"
        + f"<span class='rasai-state-chip {'state-bad' if regressed else 'state-neutral'}'>{regressed} regressão(ões) ou novo(s) sinal(is) entre marco inicial e final</span>"
        + f"<span class='rasai-state-chip {'state-warn' if other else 'state-neutral'}'>{other} alteração(ões) ou indisponibilidade(s) a investigar</span>"
    )
    rendered = re.sub(
        r"(<section class='rasai-analysis-status[^>]*data-rasai-consolidated-experience='true'.*?<div class='rasai-status-meta'>).*?(</div>\s*</section>)",
        lambda match: match.group(1) + chips + match.group(2),
        rendered,
        count=1,
        flags=re.DOTALL,
    )

    if "class='rasai-analysis-status-shell'" not in rendered and 'class="rasai-analysis-status-shell"' not in rendered:
        rendered = re.sub(
            r"(<section class='rasai-analysis-status[^>]*data-rasai-consolidated-experience='true'>)(.*?)(</section>)",
            lambda match: match.group(1) + "<div class='rasai-analysis-status-shell'>" + match.group(2) + "</div>" + match.group(3),
            rendered,
            count=1,
            flags=re.DOTALL,
        )

    refs = artifact.get("rule_reference", ()) if isinstance(artifact, Mapping) else ()
    nav_match = re.search(r"<nav aria-label='Navegação do relatório'>.*?</nav>", rendered, flags=re.DOTALL)
    nav_html = nav_match.group(0) if nav_match else ""
    if refs and "href='rules-reference.html'" not in nav_html:
        nav_link = "<a href='rules-reference.html'>Regras de avaliação</a>"
        rendered = rendered.replace(
            "<a href='#cons-governance'>Governança</a>",
            nav_link + "<a href='#cons-governance'>Governança</a>",
            1,
        )
    canonical_audits = _canonical_audit_ids(artifact)
    allowed = canonical_audits if isinstance(artifact, Mapping) else None
    rendered = _strip_disallowed_existing_audit_links(rendered, allowed)
    return _link_visible_audit_ids(rendered, allowed)


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
