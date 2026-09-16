"""Final, contract-preserving refinements for CATALOG-REPORT-002."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from html import escape
import json
import sqlite3
import sys
from typing import Any, Mapping, Sequence


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _money(value: Any, currency: str = "USD") -> str:
    return f"{currency} {_decimal(value):.8f}"


def _assessment_label(value: Any) -> str:
    raw = str(value or "").strip().upper()
    return {
        "PASS": "Aprovado",
        "FAIL": "Não aprovado",
        "GOOD": "Bom",
        "NEEDS_IMPROVEMENT": "Precisa melhorar",
        "POOR": "Ruim",
        "NEEDS_IMPROVEMENT_OR_POOR": "Precisa melhorar / ruim",
        "NOT_APPLICABLE": "Não aplicável",
        "UNAVAILABLE": "Sem dados disponíveis",
    }.get(raw, str(value or "—").replace("_", " ").title())


def _web_metric_rows(database: Any, audit_id: str) -> list[Sequence[Any]]:
    from rasai import catalog_report_metrics as m

    row = m._web_observation(database, audit_id)
    out: list[Sequence[Any]] = []
    for field, label, unit in m._WEB_METRICS:
        if field not in row or row[field] is None:
            continue
        value = row[field]
        if field.endswith("_score"):
            try:
                value = f"{float(value):.0f} / 100"
            except (TypeError, ValueError):
                value = str(value)
        else:
            value = m._fmt_number(value, unit)
        out.append((label, value, "Medição persistida"))
    if row.get("cwv_assessment"):
        out.append(("Core Web Vitals", _assessment_label(row.get("cwv_assessment")), "Dados de campo"))
    return out


def _summary_fields(summary: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in str(summary or "").strip().split(";"):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip().casefold()
        if key:
            out[key] = value.strip()
    return out


def _attempt_input_detail(attempt: Mapping[str, Any]) -> str:
    fields = _summary_fields(attempt.get("request_message_summary"))
    contract = str(attempt.get("contract") or "").upper()
    items: list[str] = []
    if fields.get("rules"):
        items.append(f"{fields['rules']} regras/critérios")
    if fields.get("evidence"):
        items.append(f"{fields['evidence']} evidências")
    if fields.get("findings"):
        items.append(f"{fields['findings']} achados")
    if fields.get("diagnostics"):
        items.append(f"{fields['diagnostics']} diagnósticos")
    if fields.get("snapshot"):
        items.append(f"captura {fields['snapshot']}")
    profile = fields.get("profile")
    if profile and contract == "IMPROVEMENT-INTELLIGENCE-001":
        domains = [part.split("@", 1)[0].replace("_", " ").title() for part in profile.split(",") if part.strip()]
        if domains:
            items.append("domínios: " + ", ".join(domains))
    return "; ".join(items) or "O resumo quantitativo da entrada não foi persistido para esta tentativa."


def _ai_totals(attempts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    from rasai import catalog_report_integrations as i

    return {
        "attempts": len(attempts),
        "success": sum(1 for a in attempts if i._norm(a.get("status")) in i._STATUS_SUCCESS),
        "input": sum(int(a.get("input_tokens") or 0) for a in attempts),
        "cached": sum(int(a.get("cached_input_tokens") or 0) for a in attempts),
        "output": sum(int(a.get("output_tokens") or 0) for a in attempts),
        "reasoning": sum(int(a.get("reasoning_tokens") or 0) for a in attempts),
        "total": sum(i._attempt_total_tokens(a) for a in attempts),
        "cost": sum((_decimal(a.get("estimated_cost") or a.get("estimated_cost_usd")) for a in attempts), Decimal("0")),
    }


def _ai_integrations_body(database: Any, data: Any) -> str:
    from rasai import catalog_report_integrations as i

    attempts = i._ai_attempts(database, data.audit_id)
    exchanges = i._ai_exchange_rows(database, data.audit_id)
    external = i._external_integrations(database, data.audit_id)
    totals = _ai_totals(attempts)
    rows: list[Sequence[Any]] = []
    modals: list[str] = []
    used: set[str] = set()

    for index, attempt in enumerate(attempts, 1):
        exchange = i._match_exchange(attempt, exchanges, used)
        modal_id = f"ai-attempt-{index}"
        cost = _decimal(attempt.get("estimated_cost") or attempt.get("estimated_cost_usd"))
        usage_context, inputs, role = i._ai_usage_detail(attempt)
        currency = str(attempt.get("cost_currency") or "USD")
        rows.append((
            attempt.get("purpose"), usage_context, attempt.get("provider") or "—", attempt.get("model") or "—",
            i._status_label(attempt.get("status")),
            f"{int(attempt.get('input_tokens') or 0):,} / {int(attempt.get('output_tokens') or 0):,}".replace(",", " "),
            _money(cost, currency), i._modal_button(modal_id, "Ver requisição"),
        ))
        body = i._kv((
            ("Finalidade", attempt.get("purpose")),
            ("Aplicado em", usage_context),
            ("Provedor", attempt.get("provider")),
            ("Modelo", attempt.get("model")),
            ("Resultado da tentativa", i._status_label(attempt.get("status"))),
            ("Tentativa", attempt.get("attempt_index") or "—"),
            ("Início", attempt.get("started_at") or "—"),
            ("Fim", attempt.get("finished_at") or "—"),
            ("Duração", i._fmt_number(attempt.get("duration_ms"), "ms")),
            ("Tokens de entrada", attempt.get("input_tokens") or 0),
            ("Entrada em cache", attempt.get("cached_input_tokens") or 0),
            ("Tokens de saída", attempt.get("output_tokens") or 0),
            ("Tokens de raciocínio", attempt.get("reasoning_tokens") or 0),
            ("Tokens totais", i._attempt_total_tokens(attempt)),
            ("Custo individual", _money(cost, currency)),
            ("Roteamento / contingência", attempt.get("decision") or attempt.get("fallback_reason") or "—"),
            ("Fallback de", attempt.get("fallback_from_provider") or "—"),
            ("Erro", attempt.get("error_detail") or attempt.get("error_code") or "—"),
        ))
        body += "<h3>Entrada utilizada</h3><p>" + escape(_attempt_input_detail(attempt)) + "</p>"
        body += "<h3>Dados envolvidos</h3><p>" + escape(inputs) + "</p>"
        body += "<h3>Resultado funcional esperado</h3><p>" + escape(role) + "</p>"
        if exchange:
            body += "<h3>Comunicação persistida · solicitação</h3><div class='pre'>" + escape(i._safe_payload_text(exchange.get("request_payload"))) + "</div>"
            body += "<h3>Comunicação persistida · resposta</h3><div class='pre'>" + escape(i._safe_payload_text(exchange.get("response_payload"))) + "</div>"
            if exchange.get("request_truncated") or exchange.get("response_truncated"):
                body += "<div class='notice warn'>O log persistido sinaliza truncamento; o relatório não reconstrói conteúdo ausente.</div>"
        else:
            body += "<div class='notice'><strong>Solicitação/resposta bruta não persistida.</strong> A telemetria disponível é exibida acima; o relatório não reconstrói nem inventa o payload.</div>"
        body += "<details><summary>Ver contrato técnico da chamada</summary><div class='detail-body'>" + i._kv((("Contrato", attempt.get("contract") or "—"), ("Hash do payload", attempt.get("request_payload_hash") or "—"))) + "</div></details>"
        modals.append(i._modal(modal_id, f"{attempt.get('purpose')} · tentativa {attempt.get('attempt_index') or index}", f"{attempt.get('provider') or 'IA'} / {attempt.get('model') or 'modelo não informado'}", body))

    int_rows: list[Sequence[Any]] = []
    int_modals: list[str] = []
    for index, row in enumerate(external, 1):
        modal_id = f"integration-{index}"
        int_rows.append((row["name"], i._status_label(row["status"]), row["attempts"], row["successes"], i._fmt_number(row["duration_ms"], "ms") if row["duration_ms"] is not None else "—", i._modal_button(modal_id, "Ver integração")))
        raw = row["raw"]
        details = raw.get("details_json")
        detail_body = i._kv((("Serviço", row["name"]), ("Resultado", i._status_label(row["status"])), ("Tentativas / alvos", row["attempts"]), ("Sucessos", row["successes"]), ("HTTP", row["http_status"] or "—"), ("Duração", i._fmt_number(row["duration_ms"], "ms") if row["duration_ms"] is not None else "—"), ("URL", row["url"] or "—"), ("Erro", row["error"] or "—"), ("Artefato", row["reference"] or "—")))
        if details:
            detail_body += "<h3>Detalhes persistidos</h3><div class='pre'>" + escape(i._safe_payload_text(details)) + "</div>"
        int_modals.append(i._modal(modal_id, row["name"], "Comunicação/serviço externo persistido", detail_body))

    forecast = i._cost_forecast(database, data.audit_id)
    currency = str(forecast.get("currency") or "USD") if forecast else "USD"
    expected = _decimal(forecast.get("expected_cost")) if forecast else Decimal("0")
    observed = totals["cost"]
    persisted_observed = _decimal(forecast.get("actual_cost")) if forecast else observed
    deviation = observed - expected if forecast else Decimal("0")
    deviation_percent = (deviation / expected * Decimal("100")) if forecast and expected else None
    persisted_deviation = _decimal(forecast.get("deviation_amount")) if forecast else deviation
    persisted_percent = _decimal(forecast.get("deviation_percent")) if forecast and forecast.get("deviation_percent") is not None else deviation_percent
    reconciled = abs(persisted_observed - observed) <= Decimal("0.00000001")
    arithmetic_ok = (not forecast) or (
        abs(persisted_deviation - deviation) <= Decimal("0.00000001")
        and (deviation_percent is None or (persisted_percent is not None and abs(persisted_percent - deviation_percent) <= Decimal("0.0001")))
    )

    body = i._audit_hero(data, "IA e integrações", "Auditoria das comunicações externas: finalidade, dados envolvidos, tentativas, volume, custo, resultado e solicitações/respostas persistidas, com credenciais removidas.")
    body += i._outline((("summary", "Resumo"), ("ai", "Requisições de IA"), ("integrations", "Outras integrações"), ("cost", "Previsão × consumo"), ("principles", "Leitura")))
    success_note = f"{totals['success']} concluída(s)"
    input_text = f"{totals['input']:,}".replace(",", " ")
    cached_text = f"{totals['cached']:,}".replace(",", " ")
    output_text = f"{totals['output']:,}".replace(",", " ")
    reasoning_text = f"{totals['reasoning']:,}".replace(",", " ")
    total_text = f"{totals['total']:,}".replace(",", " ")
    summary_html = "<div class='metric-grid'>"
    summary_html += i._metric("Tentativas de IA", totals["attempts"], success_note)
    summary_html += i._metric("Tokens de entrada", input_text)
    summary_html += i._metric("Entrada em cache", cached_text)
    summary_html += i._metric("Tokens de saída", output_text)
    summary_html += i._metric("Tokens de raciocínio", reasoning_text, "subconjunto informativo; não somado novamente")
    summary_html += i._metric("Tokens totais", total_text, "total canônico persistido por tentativa")
    summary_html += i._metric("Custo técnico observado", _money(observed, currency), "soma única das tentativas com preço persistido")
    summary_html += "</div>"
    body += i._section("summary", "Resumo do consumo", summary_html)
    body += i._section("ai", "Requisições de IA", i._table(("Finalidade", "Aplicação no relatório", "Provedor", "Modelo", "Resultado", "Tokens entrada / saída", "Custo", "Detalhe"), rows, empty="Nenhuma tentativa de IA persistida.", sortable=bool(rows), page_size=10 if len(rows) > 10 else None) + "".join(modals))
    body += i._section("integrations", "Outras integrações", i._table(("Serviço", "Resultado", "Tentativas", "Sucessos", "Duração", "Detalhe"), int_rows, empty="Nenhuma integração externa reconhecida foi persistida.", sortable=bool(int_rows), page_size=10 if len(int_rows) > 10 else None) + "".join(int_modals))

    if forecast:
        cost_html = "<div class='metric-grid'>"
        cost_html += i._metric("Custo esperado", _money(expected, currency))
        cost_html += i._metric("Custo observado", _money(observed, currency), "soma das tentativas com preço persistido")
        cost_html += i._metric("Desvio monetário", f"{currency} {deviation:+.8f}")
        cost_html += i._metric("Desvio percentual", f"{deviation_percent:+.2f}%" if deviation_percent is not None else "Não calculável")
        cost_html += i._metric("Faixa provável", f"{_money(forecast.get('likely_low'), currency)} – {_money(forecast.get('likely_high'), currency)}")
        cost_html += i._metric("Cenário potencial (P90)", _money(forecast.get("potential"), currency))
        cost_html += i._metric("Confiança da previsão", i._level_label(forecast.get("confidence")))
        cost_html += i._metric("Classificação", i._level_label(forecast.get("status")))
        cost_html += "</div>"
        tone = "good" if reconciled and arithmetic_ok else "bad"
        text = "Os totalizadores estão conciliados entre tentativas, custo observado e desvio da previsão." if reconciled and arithmetic_ok else "Há divergência entre os totalizadores persistidos e a agregação canônica desta projeção."
        cost_html += f"<div class='notice {tone}'><strong>Conciliação:</strong> {escape(text)}</div>"
        if forecast.get("relation"):
            cost_html += f"<div class='notice'><strong>Posição:</strong> {escape(str(forecast.get('relation')))}</div>"
        cost_html += f"<p class='muted'>Previsão avaliada em {escape(str(forecast.get('evaluated_at') or '—'))}. O custo é uma estimativa monetária técnica do RASAi; não representa invoice/fatura do provedor.</p>"
        if int(forecast.get("unpriced_ai_attempts") or 0):
            cost_html += f"<div class='notice warn'>{int(forecast.get('unpriced_ai_attempts') or 0)} tentativa(s) de IA não possuem preço monetário conhecido e permanecem fora do total.</div>"
    else:
        cost_html = "<div class='metric-grid'>" + i._metric("Custo observado", _money(observed, currency)) + i._metric("Previsão pré-execução", "Não persistida") + "</div><div class='notice'>Sem previsão persistida, o relatório não inventa custo esperado, desvio ou faixa histórica.</div>"
    body += i._section("cost", "Previsão × consumo observado", cost_html)
    body += i._section("principles", "Como ler esta página", "<div class='grid'><div class='card'><h3>CATs</h3><p>Mostram o resultado funcional produzido. Não repetem tokens, solicitações/respostas e custos.</p></div><div class='card'><h3>IA e integrações</h3><p>Centraliza a telemetria e a comunicação externa de cada tentativa e explica quais dados funcionais participaram de cada chamada.</p></div><div class='card'><h3>Segurança</h3><p>Segredos, tokens de autenticação e credenciais são removidos antes da projeção. Conteúdo ausente no log não é reconstruído.</p></div></div>")
    return body


def _apdex_samples_html(database: Any, data: Any, *, experience: bool) -> str:
    from rasai import catalog_report_analysis as a

    table = "synthetic_ux_apdex_samples" if experience else "synthetic_apdex_samples"
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        samples = a._audit_rows(con, table, data.audit_id)
        run = a._last(con, "synthetic_ux_apdex_runs" if experience else "synthetic_apdex_runs", data.audit_id)
    finally:
        con.close()
    summary = a._apdex_summary(database, data.audit_id, experience=experience)
    samples = sorted(samples, key=lambda item: (str(item.get("captured_at") or ""), int(item.get("run_index") or 0)))
    rows: list[Sequence[Any]] = []
    modals: list[str] = []
    for index, sample in enumerate(samples, 1):
        modal_id = ("ux" if experience else "nav") + f"-sample-{index}"
        captured = sample.get("captured_at") or "—"
        if experience:
            duration = sample.get("kpm_value_ms") if sample.get("kpm_value_ms") is not None else sample.get("user_action_duration_ms")
            rows.append((sample.get("run_index", index), captured, a._device_label(sample.get("device")), a._classification_label(sample.get("classification")), a._fmt_number(duration, "ms"), a._fmt_number(sample.get("lcp_ms"), "ms"), sample.get("request_failed_count") or 0, a._status_label(sample.get("status")), a._modal_button(modal_id, "Ver amostra")))
            fields = (
                ("Amostra", sample.get("sample_id")), ("Capturada em", captured), ("URL", sample.get("url")), ("URL final", sample.get("final_url")),
                ("Classificação", a._classification_label(sample.get("classification"))), ("Duração da ação", a._fmt_number(sample.get("user_action_duration_ms"), "ms")),
                ("Navegação", a._fmt_number(sample.get("navigation_duration_ms"), "ms")), ("LCP", a._fmt_number(sample.get("lcp_ms"), "ms")), ("CLS", sample.get("cls")),
                ("Requisições XHR/fetch", sample.get("xhr_fetch_count")), ("Recursos dinâmicos", sample.get("dynamic_resource_count")), ("Erros JavaScript", sample.get("javascript_error_count")),
                ("Erros de console", sample.get("console_error_count")), ("Requisições com falha", sample.get("request_failed_count")), ("Falhas em recursos próprios", sample.get("first_party_request_failed_count")),
                ("Respostas HTTP com erro", sample.get("http_error_count")), ("Rede estabilizada", "Sim" if sample.get("network_settled") else "Não"), ("Frustração forçada por erro", "Sim" if sample.get("error_forced_frustrated") else "Não"),
                ("Erro", sample.get("error_message") or sample.get("error_code") or "—"),
            )
            note = "<div class='notice'>O horário representa o <strong>momento persistido da captura da amostra</strong>; não é apresentado como horário de início da navegação. A amostra persiste contagens de falhas por requisição; quando a lista individual de URLs não foi persistida, o relatório não a inventa.</div>"
        else:
            duration = sample.get("duration_ms")
            rows.append((sample.get("run_index", index), captured, a._device_label(sample.get("device")), a._classification_label(sample.get("classification")), a._fmt_number(duration, "ms"), a._status_label(sample.get("status")), a._modal_button(modal_id, "Ver amostra")))
            fields = (("Amostra", sample.get("sample_id")), ("Capturada em", captured), ("URL", sample.get("url")), ("URL final", sample.get("final_url")), ("Classificação", a._classification_label(sample.get("classification"))), ("Duração", a._fmt_number(duration, "ms")), ("HTTP", sample.get("http_status")), ("Perfil técnico", sample.get("profile_id")), ("Política de cache", a._session_label(sample.get("cache_policy"))), ("Erro", sample.get("error_message") or sample.get("error_code") or "—"))
            diagnostics = a._safe_json(sample.get("browser_diagnostics"), {})
            note = "<h3>Diagnóstico de navegador</h3><div class='pre'>" + escape(json.dumps(diagnostics, ensure_ascii=False, indent=2)) + "</div>" if diagnostics else ""
        modals.append(a._modal(modal_id, f"Amostra {sample.get('run_index', index)}", f"{'Apdex de experiência' if experience else 'Apdex de navegação'} · {sample.get('url') or '—'}", a._kv(fields) + note))

    lead = ""
    if experience and run and bool(run.get("errors_affect_apdex")):
        forced = int(summary.get("error_forced_frustrated_count") or 0)
        valid = int(summary.get("valid_samples") or 0)
        scope = a._error_scope_label(run.get("error_scope"))
        lead = f"<div class='notice warn'><strong>Política de erro do Apdex:</strong> erros participam da classificação ({escape(scope)}). {forced} de {valid} amostra(s) válida(s) foram forçadas para Frustrada por essa regra. A duração, isoladamente, não explica essas classificações.</div>"
    headers = ("Amostra", "Data/hora", "Dispositivo", "Classificação", "Duração", "LCP", "Falhas de requisição", "Medição", "Detalhe") if experience else ("Amostra", "Data/hora", "Dispositivo", "Classificação", "Duração", "Medição", "Detalhe")
    return lead + a._table(headers, rows, empty="Nenhuma amostra foi persistida para este Apdex.", sortable=bool(rows), page_size=10 if experience and len(rows) > 10 else None) + "".join(modals)


def _attempt_trace(database: Any, audit_id: str) -> str:
    from rasai import catalog_report_analysis as a

    attempts = [item for item in a._ai_attempts(database, audit_id) if str(item.get("contract") or "").upper() == "IMPROVEMENT-INTELLIGENCE-001"]
    rows = [(item.get("provider") or "—", item.get("model") or "—", a._status_label(item.get("status")), item.get("attempt_index") or "—", item.get("error_detail") or item.get("error_code") or "—") for item in attempts]
    return a._table(("Provedor", "Modelo", "Resultado da tentativa", "Tentativa", "Erro"), rows, empty="Nenhuma tentativa de IA foi persistida para esta etapa.")


def _improvement_html(database: Any, data: Any) -> str:
    from rasai import catalog_report_analysis as a

    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        run = a._last(con, "improvement_intelligence_runs", data.audit_id)
        findings = a._audit_rows(con, "improvement_intelligence_findings", data.audit_id)
        recs = a._audit_rows(con, "improvement_intelligence_recommendations", data.audit_id)
    finally:
        con.close()
    if not run:
        return "<div class='notice bad'><strong>Resultado funcional ausente:</strong> a análise profunda foi solicitada, mas o resultado consolidado não está persistido. Consulte a rastreabilidade abaixo e IA e integrações; isso não é tratado como 'nenhuma análise realizada'.</div>" + _attempt_trace(database, data.audit_id)

    status = a._norm(run.get("status"))
    if status not in a._STATUS_SUCCESS and not findings:
        metrics = "<div class='metric-grid'>" + a._metric("Estado da análise", a._status_label(run.get("status"))) + a._metric("Problemas persistidos", 0) + a._metric("Recomendações persistidas", 0) + "</div>"
        return metrics + "<div class='notice bad'><strong>Análise profunda sem resultado funcional:</strong> a etapa possui estado persistido, mas não materializou findings. A tabela abaixo mostra tentativas, fallback e erro para permitir correção/reprocessamento.</div>" + _attempt_trace(database, data.audit_id)

    rec_by_finding = {str(r.get("finding_id")): r for r in recs if r.get("finding_id")}
    rows: list[Sequence[Any]] = []
    modals: list[str] = []
    distribution: Counter[str] = Counter()
    for index, finding in enumerate(findings, 1):
        rec = rec_by_finding.get(str(finding.get("finding_id")))
        domain = a._norm(finding.get("domain"))
        distribution[domain] += 1
        source_cat = a._DOMAIN_CATALOG.get(domain)
        modal_id = f"improvement-{index}"
        reference = a._Html(f"<a class='ref' href='{a.CATALOG_PAGE_BY_ID[source_cat].filename}'>Origem: {source_cat}</a>") if source_cat in a.CATALOG_PAGE_BY_ID else "—"
        rows.append((finding.get("title") or "Problema identificado", a._domain_label(domain), a._level_label(finding.get("severity")), "Sim" if rec else "Não", reference, a._modal_button(modal_id, "Ver análise")))
        body = a._kv((("Problema", finding.get("observation") or finding.get("title") or "—"), ("Domínio", a._domain_label(domain)), ("Severidade", a._level_label(finding.get("severity"))), ("Fonte", finding.get("source") or "—"), ("Catálogo de origem", source_cat or "—"), ("Seletor / path", finding.get("selector") or "Não se aplica / não identificado")))
        if finding.get("original_html"):
            body += "<h3>Trecho observado</h3><div class='pre'>" + escape(str(finding.get("original_html"))) + "</div>"
        evidence = a._safe_json(finding.get("evidence_ids_json"), [])
        if isinstance(evidence, list) and evidence:
            body += "<h3>Evidências vinculadas</h3><p>" + escape(" · ".join(str(v) for v in evidence)) + "</p>"
        if rec:
            body += "<h3>Melhoria recomendada</h3><p>" + escape(str(rec.get("recommendation") or rec.get("title") or "—")) + "</p><p><a href='cat-09.html'>Ver implementação no CAT-09</a></p>"
        else:
            body += "<div class='notice'>Este finding não possui remediação individual da análise profunda persistida nesta execução. O relatório não inventa uma correção.</div>"
        modals.append(a._modal(modal_id, finding.get("title") or "Análise", f"Análise profunda · {source_cat or 'evidência transversal'}", body))

    unique_recs = len({str(r.get("finding_id")) for r in recs if r.get("finding_id")})
    without = max(0, len(findings) - unique_recs)
    intro = "<div class='metric-grid'>"
    intro += a._metric("Problemas correlacionados", len(findings))
    intro += a._metric("Melhorias recomendadas", len(recs))
    intro += a._metric("Achados sem remediação individual", without)
    intro += a._metric("Estado", a._status_label(run.get("status")))
    intro += a._metric("Idioma da análise", run.get("analysis_language") or run.get("language") or "—")
    intro += "</div>"
    maximum = run.get("max_recommendations")
    if maximum and len(findings) > len(recs):
        intro += f"<div class='notice'><strong>Cobertura das remediações:</strong> a execução analisou {len(findings)} problema(s) e foi configurada para no máximo {int(maximum)} recomendações. Por isso nem todo finding precisa ter uma correção individual gerada pela IA.</div>"
    if distribution:
        dist_rows = [(a._domain_label(key), value) for key, value in sorted(distribution.items())]
        intro += "<details><summary>Distribuição dos problemas por domínio</summary><div class='detail-body'>" + a._table(("Domínio", "Problemas"), dist_rows) + "</div></details>"
    summary = run.get("ai_summary") or run.get("summary")
    if summary:
        intro += f"<div class='notice'><strong>Síntese da análise:</strong> {escape(str(summary))}</div>"
    return intro + a._table(("Problema", "Domínio", "Severidade", "Tem remediação", "Referência", "Detalhe"), rows, empty="A análise foi concluída sem materializar problemas correlacionados.", sortable=bool(rows), page_size=10 if len(rows) > 10 else None) + "".join(modals)


def _discovery_title(action: Mapping[str, Any]) -> tuple[str, str]:
    code = str(action.get("diagnostic_code") or "").upper()
    if "ROBOTS-ABSENT" in code:
        return "Considerar publicar robots.txt explícito", "Oportunidade"
    if "SITEMAP-ABSENT" in code:
        return "Avaliar publicação e localização do sitemap", "Oportunidade"
    if "LLMS" in code and "ABSENT" in code:
        return "Avaliar llms.txt apenas como recurso opcional", "Oportunidade"
    return str(action.get("objective_pt") or "Orientação técnica de descoberta"), "Informativa"


def _jsonld_title(row: Mapping[str, Any]) -> str:
    existing = row.get("existing_types")
    try:
        parsed = json.loads(existing) if isinstance(existing, str) else existing
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = []
    return "Aprimorar dados estruturados existentes" if isinstance(parsed, list) and parsed else "Considerar implementar dados estruturados aplicáveis"


def _friendly_deterministic_title(row: Mapping[str, Any], root: Mapping[str, Any]) -> str:
    title = str(row.get("title") or "Correção")
    text = (title + " " + str(row.get("description") or "") + " " + str(root.get("cause_summary") or "") + " " + str(root.get("rule_id") or "")).casefold()
    if "robots.txt" in text and ("aus" in text or "br-geo-017" in text or "br-geo-056" in text):
        return "Considerar publicar robots.txt explícito"
    if "sitemap" in text and ("aus" in text or "br-geo-003" in text or "br-geo-055" in text):
        return "Avaliar publicação e localização do sitemap"
    if ("dados estruturados" in text or "json-ld" in text) and ("aus" in text or "nenhum" in text):
        return "Considerar implementar dados estruturados aplicáveis"
    return title


def _remediation_html(database: Any, data: Any) -> str:
    from rasai import catalog_report_analysis as a

    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        roots = a._audit_rows(con, "root_cause_analyses", data.audit_id)
        deterministic = a._audit_rows(con, "recommendations", data.audit_id)
        content = a._audit_rows(con, "content_remediation_suggestions", data.audit_id)
        jsonld = a._audit_rows(con, "jsonld_remediation_suggestions", data.audit_id)
        deep = a._audit_rows(con, "improvement_intelligence_recommendations", data.audit_id)
        deep_findings = a._audit_rows(con, "improvement_intelligence_findings", data.audit_id)
        deep_run = a._last(con, "improvement_intelligence_runs", data.audit_id)
    finally:
        con.close()
    ai_discovery, policy_note = a._m24_ai_guidance(database, data.audit_id)
    rows: list[Sequence[Any]] = []
    modals: list[str] = []
    index = 0
    root_by_find = {str(row.get("finding_id")): row for row in roots}
    finding_by_id = {str(row.get("finding_id")): row for row in deep_findings}
    covered = {str(row.get("finding_id")) for row in deep if row.get("finding_id")}

    ai_codes = {str(item.get("diagnostic_code") or "") for item in ai_discovery}
    suppressed_rules: set[str] = set()
    if "M24-ROBOTS-ABSENT" in ai_codes:
        suppressed_rules.update({"BR-GEO-017", "BR-GEO-056"})
    if "M24-SITEMAP-ABSENT" in ai_codes:
        suppressed_rules.update({"BR-GEO-003", "BR-GEO-055"})

    for action in ai_discovery:
        index += 1
        modal_id = f"rem-discovery-{index}"
        code = str(action.get("diagnostic_code") or "")
        title, priority = _discovery_title(action)
        rows.append((title, a._domain_label("FILES_DISCOVERY"), priority, "CAT-01 → CAT-09 · IA técnica", a._modal_button(modal_id, "Ver orientação")))
        body = a._kv((("Situação / objetivo", title), ("Como proceder", action.get("recommended_change_pt") or "—"), ("Validação humana necessária", "Sim" if action.get("human_validation_required") else "Não"), ("Evidências", ", ".join(str(v) for v in action.get("evidence_ids", []) if str(v)) or "—")))
        if "ROBOTS-ABSENT" in code.upper():
            body += "<div class='notice'><strong>Classificação:</strong> robots.txt ausente não é erro de crawling por si só. Esta é uma oportunidade de explicitar política quando houver necessidade operacional; o relatório não fabrica bloqueios.</div>"
        if "SITEMAP-ABSENT" in code.upper():
            body += "<div class='notice'><strong>Classificação:</strong> a ausência no caminho convencional é uma lacuna de descoberta/readiness, não prova falha fatal. URLs não descobertas não são inventadas.</div>"
        modals.append(a._modal(modal_id, title, f"Orientação assistida por IA · {code or 'evidência persistida'}", body))

    for rec in deep:
        index += 1
        modal_id = f"rem-deep-{index}"
        title = rec.get("title") or "Melhoria da análise profunda"
        domain = a._norm(rec.get("domain"))
        source_cat = a._DOMAIN_CATALOG.get(domain)
        finding = finding_by_id.get(str(rec.get("finding_id")), {})
        rows.append((title, a._domain_label(domain), a._level_label(rec.get("priority")), f"CAT-08 → {source_cat or 'evidência transversal'}", a._modal_button(modal_id, "Ver implementação")))
        rationale = a._rationale_parts(rec.get("rationale"))
        problem = finding.get("observation") or finding.get("title") or "—"
        body = a._kv((("Problema observado", problem), ("Catálogo de origem", source_cat or "—"), ("Domínio", a._domain_label(domain)), ("Severidade", a._level_label(rec.get("severity"))), ("Prioridade", a._level_label(rec.get("priority"))), ("Seletor / path", rec.get("selector") or finding.get("selector") or "Não se aplica / não identificado"), ("Como corrigir", rec.get("recommendation") or "—"), ("Risco de manter como está", rationale.get("risk") or rec.get("rationale") or "—"), ("Benefício esperado da correção", rationale.get("benefit") or "—"), ("Justificativa técnica", rationale.get("technical") or "—"), ("Impactos relacionados", a._impact_summary(rec.get("impacts_json"))), ("Esforço", a._level_label(rec.get("effort"))), ("Confiança", a._confidence_label(rec.get("confidence"))), ("Problema de origem", rec.get("finding_id") or "—")))
        original = rec.get("original_html") or finding.get("original_html")
        if original:
            body += "<h3>Situação atual</h3><div class='pre'>" + escape(str(original)) + "</div>"
        if rec.get("suggested_html"):
            body += "<h3>Proposta corrigida</h3><div class='pre'>" + escape(str(rec.get("suggested_html"))) + "</div>"
        if rec.get("suggested_text"):
            body += "<h3>Texto sugerido</h3><div class='pre'>" + escape(str(rec.get("suggested_text"))) + "</div>"
        if rec.get("verification"):
            body += "<h3>Critério de validação / como revalidar</h3><p>" + escape(str(rec.get("verification"))) + "</p>"
        evidence = a._safe_json(rec.get("evidence_ids_json"), [])
        if isinstance(evidence, list) and evidence:
            body += "<details><summary>Ver referências de evidência</summary><div class='detail-body'><p>" + escape(" · ".join(str(v) for v in evidence)) + "</p></div></details>"
        modals.append(a._modal(modal_id, title, f"Remediação da análise CAT-08 · origem {source_cat or 'transversal'}", body))

    for rec in deterministic:
        if rec.get("finding_id") and str(rec.get("finding_id")) in covered:
            continue
        root = root_by_find.get(str(rec.get("finding_id")), {})
        if str(root.get("rule_id") or "") in suppressed_rules:
            continue
        index += 1
        modal_id = f"rem-det-{index}"
        title = _friendly_deterministic_title(rec, root)
        rows.append((title, "Técnico / determinístico", a._level_label(rec.get("priority_class")), "Diagnóstico persistido", a._modal_button(modal_id, "Ver correção")))
        body = a._kv((("Problema / objetivo", rec.get("description") or root.get("cause_summary") or "—"), ("Impacto", a._level_label(rec.get("impact"))), ("Esforço", a._level_label(rec.get("effort"))), ("Confiança", a._confidence_label(rec.get("confidence"))), ("Problema de origem", rec.get("finding_id") or "—")))
        if root:
            body += "<h3>Implementação sugerida</h3>" + a._kv((("Mudança exata", root.get("exact_change") or "—"), ("Exemplo após correção", root.get("example_after") or "—"), ("Decisão humana necessária", root.get("human_decision_required") or "Não indicada"), ("Critério de aceite", root.get("acceptance_criteria") or "—"), ("Como revalidar", root.get("revalidation_steps") or "—")))
        modals.append(a._modal(modal_id, title, "Remediação determinística derivada de problema persistido", body))

    for rec in content:
        if rec.get("finding_id") and str(rec.get("finding_id")) in covered:
            continue
        index += 1
        modal_id = f"rem-content-{index}"
        title = rec.get("objective") or "Melhoria de conteúdo"
        rows.append((title, a._domain_label("CONTENT"), "—", "IA · conteúdo", a._modal_button(modal_id, "Ver sugestão")))
        body = a._kv((("Objetivo", title), ("Onde aplicar", rec.get("target_location")), ("Texto proposto", rec.get("proposed_text")), ("Confiança", a._confidence_label(rec.get("confidence"))), ("Problema de origem", rec.get("finding_id"))))
        modals.append(a._modal(modal_id, title, "Conteúdo assistido por IA", body))

    for rec in jsonld:
        if rec.get("finding_id") and str(rec.get("finding_id")) in covered:
            continue
        index += 1
        modal_id = f"rem-jsonld-{index}"
        title = _jsonld_title(rec)
        rows.append((title, "Dados estruturados", "—", "CAT-03 → CAT-09", a._modal_button(modal_id, "Ver JSON-LD")))
        proposed = a._safe_json(rec.get("proposed_json"), rec.get("proposed_json"))
        existing = a._safe_json(rec.get("existing_types"), [])
        body = a._kv((("Situação", a._status_label(rec.get("status"))), ("Tipos existentes", ", ".join(existing) if isinstance(existing, list) and existing else "Nenhum"), ("Melhorias", rec.get("improvements") or "—")))
        body += "<div class='notice'>Quando nenhum bloco estruturado foi observado, esta sugestão é uma oportunidade de implementação aplicável ao conteúdo; não é descrita como 'correção de sintaxe'.</div>"
        body += "<h3>JSON-LD sugerido</h3><div class='pre'>" + escape(json.dumps(proposed, ensure_ascii=False, indent=2) if isinstance(proposed, (dict, list)) else str(proposed or "—")) + "</div>"
        modals.append(a._modal(modal_id, "Dados estruturados", "Sugestão persistida; exige revisão humana", body))

    lead = ""
    if policy_note:
        lead = "<div class='notice'><strong>Política para arquivos de descoberta:</strong> " + escape(policy_note) + "</div>"
    unique_findings = len({str(row.get("finding_id")) for row in deep_findings if row.get("finding_id")})
    unique_deep = len(covered)
    without = max(0, unique_findings - unique_deep)
    if deep_run and deep_run.get("max_recommendations") and without:
        lead += f"<div class='notice'><strong>Cobertura da análise profunda:</strong> {unique_findings} problema(s) foram correlacionados; {unique_deep} possuem remediação individual persistida. O limite configurado foi {int(deep_run.get('max_recommendations'))} recomendações. Itens sem remediação individual permanecem visíveis no CAT-08, sem correção inventada.</div>"
    if rows:
        lead += "<div class='metric-grid'>"
        lead += a._metric("Correções e melhorias apresentadas", len(rows))
        lead += a._metric("Remediações da análise profunda", len(deep))
        lead += a._metric("Achados sem remediação IA individual", without)
        lead += a._metric("Orientações técnicas de descoberta", len(ai_discovery))
        lead += "</div>"
    return lead + a._table(("Correção / melhoria", "Domínio", "Prioridade", "Origem", "Detalhe"), rows, empty="Nenhuma remediação persistida para esta auditoria.", sortable=bool(rows), page_size=10 if len(rows) > 10 else None) + "".join(modals)


def _capture_context_body(database: Any, data: Any) -> str:
    from rasai import catalog_report_governance as g

    snaps = g._capture_snapshots(database, data.audit_id)
    rows: list[Sequence[Any]] = []
    detail_modals: list[str] = []
    shot_modals: list[str] = []
    gallery: list[str] = []
    for index, snap in enumerate(snaps, 1):
        meta = g._safe_json(snap.get("browser_metadata"), {})
        profile = meta.get("profile") if isinstance(meta, Mapping) and isinstance(meta.get("profile"), Mapping) else {}
        browser = meta.get("browser_identity") if isinstance(meta, Mapping) and isinstance(meta.get("browser_identity"), Mapping) else {}
        viewport = profile.get("viewport") if isinstance(profile, Mapping) and isinstance(profile.get("viewport"), Mapping) else {}
        visual_state = meta.get("visual_snapshot") if isinstance(meta, Mapping) and isinstance(meta.get("visual_snapshot"), Mapping) else {}
        runtime = g._runtime_items(snap)
        detail_id = f"capture-{index}"
        shot_id = f"capture-image-{index}"
        visual_ref = meta.get("visual_artifact_ref") if isinstance(meta, Mapping) else None
        visual_path = g._artifact_path(database.parent, visual_ref)
        shot_action = g._modal_button(shot_id, "Ver imagem") if visual_path is not None and visual_ref else "—"
        rows.append((g._device_label(snap.get("device")), snap.get("requested_url") or snap.get("page_url") or "—", snap.get("final_url") or "—", snap.get("captured_at") or "—", snap.get("http_status") or "—", len(runtime), shot_action, g._modal_button(detail_id, "Ver contexto")))
        artifact_rows = (("Resposta HTTP", snap.get("raw_artifact_ref") or "—"), ("HTML renderizado", snap.get("rendered_artifact_ref") or "—"), ("Conteúdo principal", snap.get("main_content_ref") or "—"), ("Dados estruturados", snap.get("structured_data_ref") or "—"), ("Captura visual", visual_ref or "—"))
        viewport_width = viewport.get("width", visual_state.get("viewport_width", "—"))
        viewport_height = viewport.get("height", visual_state.get("viewport_height", "—"))
        detail = g._kv((("Identificador da página", snap.get("page_id")), ("Identificador da captura", snap.get("snapshot_id")), ("URL solicitada", snap.get("requested_url") or snap.get("page_url")), ("URL final", snap.get("final_url")), ("Capturada em", snap.get("captured_at")), ("HTTP", snap.get("http_status")), ("Tipo de conteúdo", snap.get("content_type")), ("Renderização", snap.get("rendering_mode")), ("Arquitetura", snap.get("architecture_classification")), ("Dispositivo", g._device_label(snap.get("device"))), ("Perfil", browser.get("descriptor") or profile.get("device") or "—"), ("Área visível (viewport)", f"{viewport_width} × {viewport_height}"), ("Escala de pixels (DPR)", profile.get("device_scale_factor") or "—"), ("Navegador", f"{browser.get('channel', 'Chrome')} {browser.get('browser_version') or meta.get('browser_version', '—')}"), ("Idioma", browser.get("locale") or profile.get("locale") or "—"), ("Diagnósticos da execução do navegador", len(runtime))))
        detail += "<h3>Arquivos e evidências</h3>" + g._table(("Arquivo / evidência", "Referência"), artifact_rows)
        if visual_path is not None and visual_ref:
            detail += "<p>" + str(g._modal_button(shot_id, "Abrir captura visual")) + "</p>"
        elif visual_ref:
            detail += "<div class='notice warn'>A referência da captura visual foi persistida, mas o arquivo não está disponível junto aos artefatos desta cópia da auditoria.</div>"
        detail_modals.append(g._modal(detail_id, "Contexto da captura", f"{g._device_label(snap.get('device'))} · {snap.get('final_url') or snap.get('requested_url') or '—'}", detail))
        if visual_path is not None and visual_ref:
            href = "../" + str(visual_ref).replace("\\", "/")
            alt = f"Captura visual da página auditada em {g._device_label(snap.get('device'))}"
            gallery.append(f"<div class='card'><h3>{escape(g._device_label(snap.get('device')))}</h3><p class='muted'>{escape(str(snap.get('captured_at') or '—'))} · viewport {escape(str(viewport_width))} × {escape(str(viewport_height))}</p><button type='button' class='action' data-modal-open='{escape(shot_id)}'><img class='capture-preview' src='{escape(href)}' alt='{escape(alt)}'></button><p class='muted mono'>{escape(str(visual_ref))}</p></div>")
            shot_body = f"<img class='capture-preview' src='{escape(href)}' alt='{escape(alt)}'><p class='muted mono'>{escape(str(visual_ref))}</p>"
            shot_modals.append(g._modal(shot_id, "Captura visual", f"{g._device_label(snap.get('device'))} · {snap.get('captured_at') or '—'}", shot_body))

    capture_html = g._table(("Dispositivo", "URL solicitada", "URL final", "Data/hora", "HTTP", "Diagnósticos", "Imagem", "Detalhe"), rows, empty="Nenhuma captura de navegador persistida.", sortable=bool(rows))
    if gallery:
        capture_html += "<div class='subsection'><h3>Prévia visual</h3><div class='grid'>" + "".join(gallery) + "</div></div>"
    capture_html += "".join(detail_modals) + "".join(shot_modals)
    body = g._audit_hero(data, "Captura e contexto", "Como a página foi capturada: URL, dispositivo, navegador, renderização e artefatos. Diagnósticos funcionais permanecem no catálogo responsável.")
    body += g._outline((("capture", "Capturas"), ("boundaries", "Responsabilidades"), ("technical", "Detalhes técnicos")))
    body += g._section("capture", "Capturas da auditoria", capture_html)
    body += g._section("boundaries", "Responsabilidades", "<div class='grid'><div class='card'><h3>Captura e contexto</h3><p>Identifica a captura, navegador, dispositivo, área visível, URL e arquivos de evidência.</p></div><div class='card'><h3>CAT-01</h3><p>Exibe erros/alertas do navegador e problemas técnicos observados.</p><p><a href='cat-01.html'>Abrir CAT-01</a></p></div><div class='card'><h3>CAT-06 / CAT-07</h3><p>Exibem suas próprias amostras sintéticas; não duplicam a captura base.</p></div></div>")
    body += g._section("technical", "Detalhes técnicos", "<details><summary>Como interpretar os identificadores</summary><div class='detail-body'><p>O identificador da página localiza o alvo auditado; o identificador da captura localiza uma execução específica por dispositivo/contexto. Os CATs referenciam esses identificadores sem criar cópias dos artefatos.</p></div></details>")
    return body


def install_catalog_report_refinements() -> None:
    from rasai import catalog_report_analysis as analysis
    from rasai import catalog_report_governance as governance
    from rasai import catalog_report_integrations as integrations
    from rasai import catalog_report_metrics as metrics
    from rasai import catalog_report_page as page

    metrics._web_metric_rows = _web_metric_rows
    analysis._apdex_samples_html = _apdex_samples_html
    page._apdex_samples_html = _apdex_samples_html
    analysis._improvement_html = _improvement_html
    page._improvement_html = _improvement_html
    analysis._remediation_html = _remediation_html
    page._remediation_html = _remediation_html
    analysis._friendly_deterministic_title = _friendly_deterministic_title
    governance._capture_context_body = _capture_context_body
    integrations._ai_integrations_body = _ai_integrations_body
    integrations._ai_totals = _ai_totals

    site = sys.modules.get("rasai.catalog_report_site")
    if site is not None:
        setattr(site, "_capture_context_body", _capture_context_body)
        setattr(site, "_ai_integrations_body", _ai_integrations_body)


__all__ = [
    "_ai_totals", "_assessment_label", "_attempt_input_detail", "_capture_context_body",
    "_discovery_title", "_friendly_deterministic_title", "_jsonld_title", "_money",
    "_web_metric_rows", "install_catalog_report_refinements",
]
