"""Final HTML-only projection of AI routing, exchanges and AUTO editorial context."""
from __future__ import annotations

from html import escape
import re
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

from rasai.persistence import AuditWorkspace

_CONTEXT_LABELS = {
    "risk_profile": "Perfil de risco do conteúdo",
    "ymyl_category": "Classificação YMYL",
    "page_purpose": "Propósito da página",
    "intended_audience": "Público pretendido",
    "experience_requirement": "Relevância de experiência (E-E-A-T)",
    "freshness_sensitivity": "Sensibilidade a atualização",
    "content_origin": "Origem do conteúdo",
}
_VALUE_LABELS = {
    "standard": "Padrão", "ymyl": "YMYL", "none": "Não YMYL",
    "health-safety": "Saúde e segurança", "financial-security": "Finanças e segurança econômica",
    "civic-societal": "Cívico e societal", "other-significant-welfare": "Outro impacto relevante no bem-estar",
    "informational": "Informacional", "transactional": "Transacional", "product-service": "Produto ou serviço",
    "review-comparison": "Avaliação ou comparação", "news-editorial": "Notícia ou editorial",
    "support-documentation": "Suporte ou documentação", "forum-ugc": "Fórum / conteúdo de usuário", "other": "Outro",
    "general": "Público geral", "professional": "Profissional", "mixed": "Misto",
    "required": "Experiência relevante é requerida", "beneficial": "Experiência relevante é benéfica",
    "not-expected": "Experiência direta não é esperada", "low": "Baixa", "medium": "Média", "high": "Alta",
    "first-party": "Primeira parte", "third-party": "Terceiros", "user-generated": "Gerado por usuários",
}
_RUNTIME_STYLE = """
<style id='rasai-ai-runtime-style'>
.ai-exchange-log details{margin:.8rem 0;border:1px solid var(--border,#d9dde3);border-radius:8px;padding:.65rem .8rem}
.ai-exchange-log summary{cursor:pointer;font-weight:650}
.ai-exchange-log pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:34rem;overflow:auto;background:var(--code-bg,#f6f7f9);padding:.75rem;border-radius:6px}
.ai-exchange-meta{display:flex;gap:.75rem;flex-wrap:wrap;margin:.35rem 0 .7rem}
.ai-exchange-meta code{font-size:.86em}.ai-context-table td:nth-child(4){min-width:18rem}
</style>
"""


def enrich_ai_runtime_report(*, audit_id: str, workspace: AuditWorkspace, context_interpretations: Sequence[Any] = (), routing_snapshot: Mapping[str, Any] | None = None) -> None:
    report_dir = workspace.root / "report"
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        _rewrite_readiness(report_dir / "readiness.html", connection, audit_id, context_interpretations)
        _rewrite_ai_usage(report_dir / "ai-usage.html", connection, audit_id, routing_snapshot)
    finally:
        connection.close()


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except (OSError, UnicodeError):
        return None


def _write(path: Path, html: str) -> None:
    path.write_text(html, encoding="utf-8", newline="\n")


def _auto_context_row(connection: sqlite3.Connection, audit_id: str) -> sqlite3.Row | None:
    try:
        return connection.execute("""SELECT risk_profile,ymyl_category,page_purpose,intended_audience,experience_requirement,freshness_sensitivity,content_origin FROM content_analysis_contexts WHERE audit_id=? LIMIT 1""", (audit_id,)).fetchone()
    except sqlite3.OperationalError:
        return None


def _snapshot_meta(connection: sqlite3.Connection, audit_id: str) -> dict[str, tuple[str, str]]:
    try:
        rows = connection.execute("""SELECT ps.snapshot_id,ps.device,COALESCE(ps.final_url,p.normalized_url) AS url FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=?""", (audit_id,)).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {str(row["snapshot_id"]): (str(row["device"] or "-"), str(row["url"] or "-")) for row in rows}


def _record_value(record: Any, name: str, default: Any = None) -> Any:
    return record.get(name, default) if isinstance(record, Mapping) else getattr(record, name, default)


def _render_auto_context(connection: sqlite3.Connection, audit_id: str, records: Sequence[Any]) -> str:
    configured = _auto_context_row(connection, audit_id)
    if configured is None:
        return ""
    auto_fields = tuple(field for field in _CONTEXT_LABELS if str(configured[field] or "").casefold() == "auto")
    if not auto_fields:
        return ""
    snapshot_meta = _snapshot_meta(connection, audit_id)
    rows: list[str] = []
    for record in records:
        fields = _record_value(record, "fields", {})
        if not isinstance(fields, Mapping):
            continue
        snapshot_id = str(_record_value(record, "snapshot_id", "") or "")
        fallback_url = str(_record_value(record, "page_url", "") or "-")
        device, page_url = snapshot_meta.get(snapshot_id, ("-", fallback_url))
        provider = str(_record_value(record, "provider", "-") or "-")
        model = str(_record_value(record, "model", "-") or "-")
        for field in auto_fields:
            item = fields.get(field)
            if not isinstance(item, Mapping):
                continue
            status = str(item.get("status") or "").upper()
            if status == "NOT_REQUESTED":
                continue
            if status == "INTERPRETED":
                raw_value = str(item.get("value") or "")
                interpretation = _VALUE_LABELS.get(raw_value, raw_value or "Não determinável")
            else:
                interpretation = "Não determinável"
            try:
                confidence_text = f"{float(item.get('confidence', 0.0)) * 100:.0f}%"
            except (TypeError, ValueError):
                confidence_text = "-"
            rationale = str(item.get("rationale") or "").strip() or "A resposta não trouxe justificativa suficiente."
            evidence_ids = item.get("evidence_ids") or ()
            evidence_text = ", ".join(str(value) for value in evidence_ids) or "-"
            rows.append("<tr>" f"<td>{escape(page_url)}<br><small>{escape(device)} · <code>{escape(snapshot_id or '-')}</code></small></td>" f"<td>{escape(_CONTEXT_LABELS[field])}</td><td><code>AUTO</code></td>" f"<td><strong>{escape(interpretation)}</strong><br><small>confiança {escape(confidence_text)}</small></td>" f"<td>{escape(rationale)}<br><small>Evidências: {escape(evidence_text)}</small></td>" f"<td>{escape(provider)}<br><small>{escape(model)}</small></td></tr>")
    fields_text = ", ".join(_CONTEXT_LABELS[field] for field in auto_fields)
    intro = "<div class='notice auto-editorial-context' data-auto-editorial-context='true'><strong>Contexto editorial em modo automático:</strong> " + escape(fields_text) + ". A configuração oficial permanece <code>AUTO</code>. A leitura abaixo é uma interpretação contextual da IA baseada somente no conteúdo/evidências fornecidos nesta execução; não sobrescreve <code>content_analysis_contexts</code>, não entra no SCORE-GEO-004/SARI-001 e não é tratada como verdade canônica.</div>"
    if not rows:
        return intro + "<div class='notice ai-auto-interpretation-unavailable'><strong>Interpretação da IA:</strong> não disponível nesta execução. O relatório não infere nem reconstrói classificações YMYL/E-E-A-T a partir do banco.</div>"
    return intro + "<section class='ai-context-interpretation' data-ai-context-interpretation='true'><h2>Como a IA interpretou os campos AUTO nesta execução</h2><p class='intro'>Esta seção permite comparar a intenção/configuração humana com a leitura do conteúdo pela IA. <strong>Não determinável</strong> é o resultado correto quando a evidência visível não sustenta uma classificação segura.</p><div class='table-wrap'><table class='ai-context-table'><thead><tr><th>Página / contexto</th><th>Campo</th><th>Configuração</th><th>Interpretação IA</th><th>Justificativa</th><th>Provider / modelo</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></section>"


def _rewrite_readiness(path: Path, connection: sqlite3.Connection, audit_id: str, records: Sequence[Any]) -> None:
    html = _read(path)
    if html is None:
        return
    html = re.sub(r"<div class='notice auto-editorial-context' data-auto-editorial-context='true'>.*?</div>", "", html, count=1, flags=re.DOTALL)
    html = re.sub(r"<section class='ai-context-interpretation' data-ai-context-interpretation='true'>.*?</section>", "", html, count=1, flags=re.DOTALL)
    block = _render_auto_context(connection, audit_id, records)
    if block:
        anchor = "<p><a href='content-suggestions.html'>"
        html = html.replace(anchor, block + anchor, 1) if anchor in html else html.replace("</main>", block + "</main>", 1)
    _write(path, html)


def _exchange_rows(connection: sqlite3.Connection, audit_id: str) -> list[sqlite3.Row]:
    try:
        return list(connection.execute("""SELECT sequence_no,provider,model,purpose,snapshot_id,page_url,endpoint,started_at,duration_ms,outcome,http_status,exception_type,request_payload,request_sha256,request_truncated,response_payload,response_sha256,response_truncated FROM ai_exchange_log WHERE audit_id=? ORDER BY sequence_no,started_at""", (audit_id,)).fetchall())
    except sqlite3.OperationalError:
        return []


def _routing_summary(snapshot: Mapping[str, Any] | None) -> str:
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("provider_health"), Mapping):
        return ""
    rows: list[str] = []
    for provider, raw in snapshot["provider_health"].items():
        if not isinstance(raw, Mapping):
            continue
        final_state = "Elegível" if bool(raw.get("eligible")) else "Removido da execução"
        reason = str(raw.get("exclusion_reason") or "-")
        rows.append("<tr>" f"<td><strong>{escape(str(provider))}</strong></td>" f"<td>{int(raw.get('attempts') or 0)}</td><td>{int(raw.get('successes') or 0)}</td>" f"<td>{int(raw.get('temporary_failures') or 0)}</td><td>{int(raw.get('terminal_failures') or 0)}</td>" f"<td>{escape(final_state)}</td><td><code>{escape(reason)}</code></td></tr>")
    if not rows:
        return ""
    return "<section class='ai-routing-runtime' data-ai-routing-runtime='true'><h2>Elegibilidade e rotação de providers nesta execução</h2><p class='intro'>Em <code>AI=auto</code>, cada necessidade começa no próximo provider elegível. Uma mesma necessidade tenta cada provider no máximo uma vez. Falhas de credencial/crédito/quota/permissão/modelo ou HTTP 404/410 removem o provider imediatamente. Demais falhas abrem o circuit breaker quando somam 3 falhas nas últimas 5 tentativas daquele provider.</p><div class='table-wrap'><table><thead><tr><th>Provider</th><th>Tentativas</th><th>Sucessos</th><th>Falhas temporárias</th><th>Falhas terminais</th><th>Estado final</th><th>Motivo</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div></section>"


def _exchange_section(rows: Sequence[sqlite3.Row]) -> str:
    if not rows:
        return "<section class='ai-exchange-log' data-ai-exchange-log='true'><h2>Log de comunicação com IA</h2><p class='intro'>Nenhum envelope de comunicação foi persistido para esta execução.</p></section>"
    items: list[str] = []
    for row in rows:
        status = str(row["outcome"] or "-")
        http = f"HTTP {row['http_status']}" if row["http_status"] is not None else "-"
        request_note = " · truncado" if bool(row["request_truncated"]) else ""
        response_note = " · truncado" if bool(row["response_truncated"]) else ""
        response = str(row["response_payload"]) if row["response_payload"] is not None else "[sem envelope de resposta]"
        response_hash = "sha256:" + escape(str(row["response_sha256"])) if row["response_sha256"] else "-"
        items.append("<details>" f"<summary>#{int(row['sequence_no'])} · {escape(str(row['purpose']))} · {escape(str(row['provider']))} · {escape(status)}</summary>" "<div class='ai-exchange-meta'>" f"<span>Modelo: <code>{escape(str(row['model'] or '-'))}</code></span><span>HTTP: <code>{escape(http)}</code></span>" f"<span>Duração: <code>{int(row['duration_ms'])} ms</code></span><span>Página: <code>{escape(str(row['page_url'] or '-'))}</code></span>" f"<span>Snapshot: <code>{escape(str(row['snapshot_id'] or '-'))}</code></span></div>" f"<p><strong>Endpoint:</strong> <code>{escape(str(row['endpoint']))}</code></p>" f"<p><strong>Requisição enviada{escape(request_note)}:</strong> <code>sha256:{escape(str(row['request_sha256']))}</code></p><pre>{escape(str(row['request_payload']))}</pre>" f"<p><strong>Envelope/resposta recebida{escape(response_note)}:</strong> <code>{response_hash}</code></p><pre>{escape(response)}</pre></details>")
    return "<section class='ai-exchange-log' data-ai-exchange-log='true'><h2>Log de comunicação com IA</h2><div class='notice'><strong>Escopo do log:</strong> registra o corpo encaminhado ao transport e o envelope retornado ao adapter. Headers de autenticação, API keys, tokens de acesso e segredos são excluídos. Conteúdo de raciocínio privado não é persistido. A interpretação editorial transitória dos campos AUTO é redigida do log do banco e aparece apenas na seção interpretativa do relatório. Payloads acima do limite de captura são truncados e mantêm SHA-256 do conteúdo integral observado.</div>" + "".join(items) + "</section>"


def _rewrite_ai_usage(path: Path, connection: sqlite3.Connection, audit_id: str, routing_snapshot: Mapping[str, Any] | None) -> None:
    html = _read(path)
    if html is None:
        return
    if "rasai-ai-runtime-style" not in html:
        html = html.replace("</head>", _RUNTIME_STYLE + "</head>", 1)
    html = re.sub(r"<section class='ai-routing-runtime' data-ai-routing-runtime='true'>.*?</section>", "", html, flags=re.DOTALL)
    html = re.sub(r"<section class='ai-exchange-log' data-ai-exchange-log='true'>.*?</section>", "", html, flags=re.DOTALL)
    block = _routing_summary(routing_snapshot) + _exchange_section(_exchange_rows(connection, audit_id))
    anchor = "<section id='public-report-contract'"
    html = html.replace(anchor, block + anchor, 1) if anchor in html else html.replace("</main>", block + "</main>", 1)
    _write(path, html)
