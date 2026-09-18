"""AI and external-integration telemetry, payload safety and cost projection."""
from rasai.catalog_report_governance import *  # noqa: F401,F403


_AI_USAGE_DETAILS: dict[str, tuple[str,str,str]] = {
    "M18-SEMANTIC-22-V1": (
        "CAT-03 · Conteúdo, semântica e dados estruturados",
        "Conteúdo principal, título e headings, entidades e contexto semântico, além das evidências de dados estruturados/JSON-LD disponibilizadas no payload desta análise.",
        "Produzir avaliações semânticas vinculadas às evidências. Esta chamada pertence ao CAT-03; dados estruturados/JSON-LD não são tratados como CAT-01 apenas por estarem no HTML.",
    ),
    "M24-TECHNICAL-REMEDIATION-V2": (
        "CAT-01 → CAT-09 · descoberta técnica e remediação",
        "Diagnósticos persistidos de robots.txt, sitemap, llms.txt, IndexNow e evidências de descoberta técnica aplicáveis.",
        "Interpretar o estado técnico sem transformar ausência válida em erro e produzir orientação de remediação no CAT-09.",
    ),
    "M20-CONTENT-REMEDIATION-V3": (
        "CAT-03 → CAT-09 · conteúdo e remediação",
        "Achados de conteúdo/semântica e evidências editoriais persistidas para a URL auditada.",
        "Sugerir texto ou ajuste editorial para achados existentes, sem alterar a medição ou a pontuação determinística.",
    ),
    "IMPROVEMENT-INTELLIGENCE-001": (
        "CAT-08 · análise profunda; remediações relacionadas no CAT-09",
        "Evidências persistidas dos domínios selecionados, podendo incluir performance, acessibilidade, semântica, conteúdo, descoberta, boas práticas e segurança passiva.",
        "Correlacionar problemas, explicar impacto, priorizar melhorias e produzir recomendações evidence-bound. A implementação detalhada é projetada no CAT-09.",
    ),
}


def _sanitize_obj(value: Any) -> Any:
    if isinstance(value,Mapping):
        out={}
        for k,v in value.items():
            out[str(k)]="[REDACTED]" if _SECRET_KEY_RE.search(str(k)) else _sanitize_obj(v)
        return out
    if isinstance(value,list):return [_sanitize_obj(v) for v in value]
    if isinstance(value,str):
        return _APIKEY_RE.sub("[REDACTED]",_BEARER_RE.sub("Bearer [REDACTED]",value))
    return value


def _safe_payload_text(value: Any) -> str:
    if value in (None,""):return "Não persistido."
    parsed=_safe_json(value,None)
    sanitized=_sanitize_obj(parsed if parsed is not None else str(value))
    if isinstance(sanitized,(dict,list)):
        return json.dumps(sanitized,ensure_ascii=False,indent=2)
    return str(sanitized)


def _ai_attempts(database: Path, audit_id: str) -> list[dict[str,Any]]:
    con=sqlite3.connect(database);con.row_factory=sqlite3.Row
    try:
        attempts=[]
        for table,contract_field in (("ai_provider_attempts","semantic_contract_version"),("content_remediation_attempts","contract_version")):
            for r in _audit_rows(con,table,audit_id):
                d=dict(r); contract=str(d.get(contract_field) or "")
                purpose,catalog=_AI_PURPOSE_LABELS.get(contract.upper(),(contract or "Chamada de IA",""))
                d["_source_table"]=table;d["purpose"]=purpose;d["catalog_id"]=catalog;d["contract"]=contract
                attempts.append(d)
        attempts.sort(key=lambda r:str(r.get("started_at") or ""))
        return attempts
    finally:con.close()


def _ai_exchange_rows(database: Path, audit_id: str) -> list[dict[str,Any]]:
    con=sqlite3.connect(database);con.row_factory=sqlite3.Row
    try:return _audit_rows(con,"ai_exchange_log",audit_id)
    finally:con.close()


def _match_exchange(attempt: Mapping[str,Any], exchanges: Sequence[Mapping[str,Any]], used: set[str]) -> Mapping[str,Any]|None:
    ap=str(attempt.get("provider") or "").upper(); model=str(attempt.get("model") or "")
    purpose=str(attempt.get("purpose") or "").casefold()
    for ex in exchanges:
        eid=str(ex.get("exchange_id") or "")
        if eid in used:continue
        if str(ex.get("provider") or "").upper()!=ap:continue
        if model and str(ex.get("model") or "")!=model:continue
        ex_label=_AI_EXCHANGE_PURPOSES.get(_norm(ex.get("purpose")),str(ex.get("purpose") or "")).casefold()
        if ex_label and (ex_label in purpose or purpose in ex_label):
            used.add(eid);return ex
    return None


def _external_integrations(database: Path, audit_id: str) -> list[dict[str,Any]]:
    con=sqlite3.connect(database);con.row_factory=sqlite3.Row
    try:
        out=[]
        for r in _audit_rows(con,"web_performance_attempts",audit_id):
            out.append({"name":_friendly_service(r.get("service")),"status":r.get("status"),"attempts":1,"successes":1 if _norm(r.get("status")) in _STATUS_SUCCESS else 0,"duration_ms":r.get("duration_ms"),"http_status":r.get("http_status"),"error":r.get("error_message") or r.get("error_code"),"url":r.get("url"),"reference":r.get("artifact_reference"),"raw":r})
        direct_external={"w3c-validator","w3c-css-validator","mdn-observatory","web-platform-baseline"}
        for r in _audit_rows(con,"standards_service_runs",audit_id):
            service=str(r.get("service_id") or "")
            if not r.get("requested") or service not in direct_external:continue
            details=_safe_json(r.get("details_json"),{})
            errors=details.get("errors",[]) if isinstance(details,Mapping) else []
            out.append({"name":_friendly_service(service),"status":r.get("state"),"attempts":r.get("targets_attempted",0),"successes":r.get("targets_succeeded",0),"duration_ms":None,"http_status":None,"error":"; ".join(str(v) for v in errors) if isinstance(errors,list) else errors,"url":details.get("endpoint") if isinstance(details,Mapping) else None,"reference":details.get("observations_artifact") if isinstance(details,Mapping) else None,"raw":r})
        return out
    finally:con.close()


def _ai_usage_detail(attempt: Mapping[str,Any]) -> tuple[str,str,str]:
    contract=str(attempt.get("contract") or "").upper()
    return _AI_USAGE_DETAILS.get(contract,(attempt.get("catalog_id") or "Transversal","Contexto específico não descrito no contrato desta projeção.","Finalidade registrada pela própria tentativa de IA."))


def _cost_forecast(database: Path, audit_id: str) -> dict[str,Any]:
    con=sqlite3.connect(database);con.row_factory=sqlite3.Row
    try:return _last(con,"console_cost_forecast_outcomes",audit_id)
    finally:con.close()


def _attempt_total_tokens(attempt: Mapping[str,Any]) -> int:
    """Return canonical total tokens without double-counting reasoning tokens.

    Provider accounting defines total as input + output. Reasoning tokens, when exposed,
    are a subset of output tokens and therefore remain a diagnostic breakdown only.
    """
    persisted=attempt.get("total_tokens")
    if persisted not in (None,""):
        return int(persisted or 0)
    return int(attempt.get("input_tokens") or 0)+int(attempt.get("output_tokens") or 0)


def _ai_integrations_body(database: Path, data: _ReportData) -> str:
    attempts=_ai_attempts(database,data.audit_id)
    exchanges=_ai_exchange_rows(database,data.audit_id)
    external=_external_integrations(database,data.audit_id)
    success=sum(1 for a in attempts if _norm(a.get("status")) in _STATUS_SUCCESS)
    input_tokens=sum(int(a.get("input_tokens") or 0) for a in attempts)
    cached_tokens=sum(int(a.get("cached_input_tokens") or 0) for a in attempts)
    output_tokens=sum(int(a.get("output_tokens") or 0) for a in attempts)
    reasoning_tokens=sum(int(a.get("reasoning_tokens") or 0) for a in attempts)
    total_tokens=sum(_attempt_total_tokens(a) for a in attempts)
    total_cost=sum(float(a.get("estimated_cost") or a.get("estimated_cost_usd") or 0) for a in attempts)
    rows=[];modals=[];used=set()
    for i,a in enumerate(attempts,1):
        ex=_match_exchange(a,exchanges,used)
        mid=f"ai-attempt-{i}"
        cost=float(a.get("estimated_cost") or a.get("estimated_cost_usd") or 0)
        usage_context,inputs,role=_ai_usage_detail(a)
        rows.append((a.get("purpose"),usage_context,a.get("provider") or "-",a.get("model") or "-",_status_label(a.get("status")),f"{int(a.get('input_tokens') or 0):,} / {int(a.get('output_tokens') or 0):,}".replace(","," "),f"{a.get('cost_currency') or 'USD'} {cost:.8f}",_modal_button(mid,"Ver requisição")))
        body=_kv((("Finalidade",a.get("purpose")),("Aplicação no relatório",usage_context),("Provedor",a.get("provider")),("Modelo",a.get("model")),("Resultado da tentativa",_status_label(a.get("status"))),("Tentativa",a.get("attempt_index") or "-"),("Início",a.get("started_at") or "-"),("Fim",a.get("finished_at") or "-"),("Duração",_fmt_number(a.get("duration_ms"),"ms")),("Tokens de entrada",a.get("input_tokens") or 0),("Entrada em cache",a.get("cached_input_tokens") or 0),("Tokens de saída",a.get("output_tokens") or 0),("Tokens de raciocínio",a.get("reasoning_tokens") or 0),("Tokens totais",_attempt_total_tokens(a)),("Custo individual",f"{a.get('cost_currency') or 'USD'} {cost:.8f}"),("Roteamento / contingência",a.get("decision") or a.get("fallback_reason") or "-"),("Erro",a.get("error_detail") or a.get("error_code") or "-")))
        body+="<h3>Dados envolvidos</h3><p>"+escape(inputs)+"</p>"
        body+="<h3>Papel da IA nesta chamada</h3><p>"+escape(role)+"</p>"
        body+="<h3>O que foi solicitado</h3><p>"+escape(str(a.get("request_message_summary") or "Resumo textual da solicitação não persistido."))+"</p>"
        if ex:
            body+="<h3>Comunicação persistida · solicitação</h3><div class='pre'>"+escape(_safe_payload_text(ex.get("request_payload")))+"</div>"
            body+="<h3>Comunicação persistida · resposta</h3><div class='pre'>"+escape(_safe_payload_text(ex.get("response_payload")))+"</div>"
            if ex.get("request_truncated") or ex.get("response_truncated"):
                body+="<div class='notice warn'>O log persistido sinaliza truncamento; o relatório não reconstrói conteúdo ausente.</div>"
        else:
            body+="<div class='notice'>O conteúdo bruto da solicitação/resposta não foi persistido para esta tentativa. O relatório exibe somente a telemetria disponível e não inventa a comunicação.</div>"
        body+="<details><summary>Ver contrato técnico da chamada</summary><div class='detail-body'>"+_kv((("Contrato",a.get("contract") or "-"),))+"</div></details>"
        modals.append(_modal(mid,f"{a.get('purpose')} · tentativa {a.get('attempt_index') or i}",f"{a.get('provider') or 'IA'} / {a.get('model') or 'modelo não informado'}",body))
    int_rows=[];int_modals=[]
    for i,r in enumerate(external,1):
        mid=f"integration-{i}"
        int_rows.append((r["name"],_status_label(r["status"]),r["attempts"],r["successes"],_fmt_number(r["duration_ms"],"ms") if r["duration_ms"] is not None else "-",_modal_button(mid,"Ver integração")))
        raw=r["raw"];details=raw.get("details_json")
        body=_kv((("Serviço",r["name"]),("Resultado",_status_label(r["status"])),("Tentativas / alvos",r["attempts"]),("Sucessos",r["successes"]),("HTTP",r["http_status"] or "-"),("Duração",_fmt_number(r["duration_ms"],"ms") if r["duration_ms"] is not None else "-"),("URL",r["url"] or "-"),("Erro",r["error"] or "-"),("Artefato",r["reference"] or "-")))
        if details:
            body+="<h3>Detalhes persistidos</h3><div class='pre'>"+escape(_safe_payload_text(details))+"</div>"
        int_modals.append(_modal(mid,r["name"],"Comunicação/serviço externo persistido",body))

    forecast=_cost_forecast(database,data.audit_id)
    currency=str(forecast.get("currency") or "USD") if forecast else "USD"
    expected=float(forecast.get("expected_cost") or 0) if forecast else 0.0
    observed_persisted=float(forecast.get("actual_cost") or total_cost) if forecast else total_cost
    computed_deviation=total_cost-expected if forecast else 0.0
    computed_percent=(computed_deviation/expected*100.0) if forecast and expected else None
    reconciled=abs(observed_persisted-total_cost)<=0.00000001
    stored_deviation=float(forecast.get("deviation_amount") or computed_deviation) if forecast else computed_deviation
    stored_percent=float(forecast.get("deviation_percent") or (computed_percent or 0)) if forecast else None
    arithmetic_ok=(not forecast) or (abs(stored_deviation-computed_deviation)<=0.00000001 and (computed_percent is None or abs(stored_percent-computed_percent)<=0.0001))

    body=_audit_hero(data,"IA e integrações","Auditoria das comunicações externas: finalidade, dados envolvidos, tentativas, volume, custo, resultado e solicitações/respostas persistidas, com credenciais removidas.")
    body+=_outline((("summary","Resumo"),("ai","Requisições de IA"),("integrations","Outras integrações"),("cost","Custos"),("principles","Leitura")))
    body+=_section("summary","Resumo do consumo",f"<div class='metric-grid'>{_metric('Tentativas de IA',len(attempts),f'{success} concluída(s)')}{_metric('Tokens de entrada',f'{input_tokens:,}'.replace(',',' '))}{_metric('Entrada em cache',f'{cached_tokens:,}'.replace(',',' '))}{_metric('Tokens de saída',f'{output_tokens:,}'.replace(',',' '))}{_metric('Tokens de raciocínio',f'{reasoning_tokens:,}'.replace(',',' '), 'incluídos nos tokens de saída; não somados novamente')}{_metric('Tokens totais',f'{total_tokens:,}'.replace(',',' '),'entrada + saída')}{_metric('Custo técnico observado',f'{currency} {total_cost:.8f}','soma dos custos individuais persistidos')}</div>")
    body+=_section("ai","Requisições de IA",_table(("Finalidade","Aplicação no relatório","Provedor","Modelo","Resultado","Tokens entrada / saída","Custo","Detalhe"),rows,empty="Nenhuma tentativa de IA persistida.",sortable=bool(rows),page_size=10 if len(rows)>10 else None)+"".join(modals))
    body+=_section("integrations","Outras integrações",_table(("Serviço","Resultado","Tentativas","Sucessos","Duração","Detalhe"),int_rows,empty="Nenhuma integração externa reconhecida foi persistida.",sortable=bool(int_rows),page_size=10 if len(int_rows)>10 else None)+"".join(int_modals))

    if forecast:
        cost_html=(
            "<div class='metric-grid'>"
            +_metric("Custo esperado",f"{currency} {expected:.8f}")
            +_metric("Custo observado",f"{currency} {total_cost:.8f}","soma das tentativas com preço persistido")
            +_metric("Desvio monetário",f"{currency} {computed_deviation:+.8f}")
            +_metric("Desvio percentual",f"{computed_percent:+.2f}%" if computed_percent is not None else "Não calculável")
            +_metric("Faixa provável",f"{currency} {float(forecast.get('likely_low') or 0):.8f} – {currency} {float(forecast.get('likely_high') or 0):.8f}")
            +_metric("Cenário potencial (P90)",f"{currency} {float(forecast.get('potential') or 0):.8f}")
            +_metric("Confiança da previsão",_level_label(forecast.get("confidence")))
            +_metric("Classificação",forecast.get("status") or "-")
            +"</div>"
        )
        reconcile_tone="good" if reconciled and arithmetic_ok else "bad"
        reconcile_text="Os totalizadores estão conciliados: custo observado = soma dos custos individuais e o desvio foi recalculado a partir do custo esperado e do custo observado." if reconciled and arithmetic_ok else "Há divergência entre os totalizadores persistidos e a soma/recomputação desta projeção. Revise a telemetria financeira antes de usar esses valores."
        cost_html+=f"<div class='notice {reconcile_tone}'><strong>Conciliação:</strong> {escape(reconcile_text)}</div>"
        if forecast.get("relation"):
            cost_html+=f"<div class='notice'>{escape(str(forecast.get('relation')))}</div>"
        if int(forecast.get("unpriced_ai_attempts") or 0):
            cost_html+=f"<div class='notice warn'>{int(forecast.get('unpriced_ai_attempts') or 0)} tentativa(s) de IA não possuem preço monetário conhecido e permanecem fora do total.</div>"
    else:
        cost_html=f"<div class='metric-grid'>{_metric('Custo observado',f'{currency} {total_cost:.8f}')}{_metric('Previsão pré-execução','Não persistida')}</div><div class='notice'>Sem previsão persistida, o relatório não inventa custo esperado, desvio ou faixa histórica.</div>"
    body+=_section("cost","Custos e aderência à estimativa",cost_html)
    body+=_section("principles","Como ler esta página","<div class='grid'><div class='card'><h3>CATs</h3><p>Mostram o resultado funcional produzido. Não repetem tokens, solicitações/respostas e custos.</p></div><div class='card'><h3>IA e integrações</h3><p>Centraliza a telemetria e a comunicação externa de cada tentativa e explica quais dados funcionais participaram de cada chamada.</p></div><div class='card'><h3>Segurança</h3><p>Segredos, tokens de autenticação e credenciais são removidos antes da projeção. Conteúdo ausente no log não é reconstruído.</p></div></div>")
    return body


__all__ = [name for name in globals() if not name.startswith("__")]
