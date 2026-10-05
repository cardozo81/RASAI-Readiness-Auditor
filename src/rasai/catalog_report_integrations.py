"""AI and external-integration telemetry, payload safety and cost projection."""
from rasai.catalog_report_governance import *  # noqa: F401,F403
from rasai.ai_native_usage import humanize_native_usage_unit
from rasai.ai_economic_telemetry import aggregate_attempt_costs, attempt_monetary_cost, canonical_total_tokens
from rasai.secret_safety import redact_value
from rasai.time_contract import parse_timestamp


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
    "COMPETITIVE-AI-001": (
        "CAT-05 · Inteligência competitiva",
        "SERP persistida, classificação competitiva, páginas públicas observadas, comparação determinística e lacunas vinculadas ao snapshot de evidências.",
        "Interpretar oportunidades competitivas somente sobre evidência selada. O resultado é advisory, não altera score e não declara causalidade de ranking.",
    ),
    "DIRECTED-ANALYSIS-001": (
        "Análise Direcionada · camada estratégica",
        "Contexto estratégico estruturado derivado exclusivamente de catálogos, findings, métricas, recomendações, evidências, remediações e limitações já persistidos nesta auditoria.",
        "Correlacionar ações existentes, impactos multidimensionais, esforço, confiança, dependências, ordem e validação. A IA não cria fatos técnicos, ações, evidências ou links de catálogo.",
    ),
    "RASAI-PERPLEXITY-SEARCH-1": (
        "CAT-05 · Pesquisa externa / Search Intelligence",
        "Queries e fontes retornadas pela Perplexity Search API com provenance externa explícita.",
        "Descobrir fontes externas e preservar citações/metadata. Esta pesquisa é advisory, não substitui SERP observada, não vira evidência determinística e não altera scoring.",
    ),
}


def _sanitize_obj(value: Any) -> Any:
    return redact_value(value)


def _safe_payload_text(value: Any) -> str:
    if value in (None,""):return "Não persistido."
    parsed=_safe_json(value,None)
    sanitized=_sanitize_obj(parsed if parsed is not None else str(value))
    if isinstance(sanitized,(dict,list)):
        return json.dumps(sanitized,ensure_ascii=False,indent=2)
    return str(sanitized)


def _provider_identity(value: Any) -> _Html:
    """Preserve canonical provider identity without weakening generic enum fallback."""
    raw=str(value or "-").strip() or "-"
    return _Html("<code class='provider-id'>"+escape(raw)+"</code>")


def _persisted_payload_text(value: Any) -> str:
    """Return the persisted exchange evidence without semantic humanization."""
    if value in (None, ""):
        return "Não persistido."
    return str(value)


def _raw_payload_block(value: Any) -> str:
    # humanize_report_html intentionally treats <pre> as an immutable evidence zone.
    return "<pre class='pre'>"+escape(_persisted_payload_text(value))+"</pre>"


def _external_details_public_text(value: Any) -> str:
    """Display only recognized external-source metadata after secret redaction.

    Source JSON is immutable: this creates a separate, valid JSON projection,
    keeping keys distinct and leaving arbitrary vendor payloads untouched.
    """
    safe = _safe_payload_text(value)
    payload = _safe_json(safe, None)
    if not isinstance(payload, Mapping):
        return safe
    displayed = dict(payload)
    dataset = displayed.get("dataset")
    if isinstance(dataset, Mapping) and dataset.get("source") == "NPM_WEB_FEATURES":
        dataset = dict(dataset)
        dataset["source"] = "Pacote npm web-features"
        displayed["dataset"] = dataset
        boundary = str(displayed.get("boundary") or "")
        if boundary.startswith("SUCCESS means deterministic classification of directly observable"):
            displayed["boundary"] = (
                "Concluído significa que o detector determinístico classificou "
                "somente sinais diretamente observáveis dentro do escopo delimitado; "
                "não representa inventário exaustivo de código oculto em recursos "
                "externos nem dos caminhos dinâmicos não executados."
            )
    if displayed.get("source_type") == "CHROME_UX_REPORT_HISTORY":
        displayed["source_type"] = "Histórico do Chrome UX Report"
        if displayed.get("capture_method") == "DIRECT_OFFICIAL_API":
            displayed["capture_method"] = "Consulta direta à API oficial"
        metadata = displayed.get("metadata")
        if isinstance(metadata, Mapping):
            metadata = dict(metadata)
            if metadata.get("scope_policy") == "AUDITED_ORIGIN_ONLY":
                metadata["scope_policy"] = "Somente a origem auditada"
            displayed["metadata"] = metadata
    return json.dumps(displayed, ensure_ascii=False, indent=2)


def _ai_attempts(database: Path, audit_id: str) -> list[dict[str,Any]]:
    con=sqlite3.connect(database);con.row_factory=sqlite3.Row
    try:
        attempts=[]
        security_only_improvement=False
        improvement=_last(con,"improvement_intelligence_runs",audit_id)
        if improvement:
            domains=_safe_json(improvement.get("domains_json"),[])
            normalized={_norm(v) for v in domains} if isinstance(domains,list) else set()
            security_only_improvement=normalized=={"SECURITY"} and bool(_audit_rows(con,"passive_security_runs",audit_id))
        for table,contract_field,native_table in (
            ("ai_provider_attempts","semantic_contract_version","ai_provider_native_usage"),
            ("content_remediation_attempts","contract_version","content_remediation_native_usage"),
        ):
            for r in _audit_rows(con,table,audit_id):
                d=dict(r); contract=str(d.get(contract_field) or "")
                try:
                    d["_native_usage"] = [
                        dict(item)
                        for item in con.execute(
                            f"SELECT * FROM {native_table} WHERE attempt_id=? ORDER BY component_index",
                            (d.get("attempt_id"),),
                        ).fetchall()
                    ]
                except sqlite3.OperationalError:
                    d["_native_usage"] = []
                purpose,catalog=_AI_PURPOSE_LABELS.get(contract.upper(),(contract or "Chamada de IA",""))
                if contract.upper()=="IMPROVEMENT-INTELLIGENCE-001" and security_only_improvement:
                    purpose,catalog="Análise advisory de segurança passiva","CAT-10"
                d["_source_table"]=table;d["purpose"]=purpose;d["catalog_id"]=catalog;d["contract"]=contract
                attempts.append(d)
        attempts.sort(key=lambda r:str(r.get("started_at") or ""))
        return attempts
    finally:con.close()


def _reprocess_runs(database: Path, audit_id: str) -> list[dict[str,Any]]:
    con=sqlite3.connect(database);con.row_factory=sqlite3.Row
    try:
        return _audit_rows(con,"audit_reprocess_runs",audit_id)
    finally:
        con.close()


def _execution_origin(
    occurred_at: Any,
    reprocess_runs: Sequence[Mapping[str,Any]],
) -> tuple[str,str|None]:
    raw=str(occurred_at or "").strip()
    if not raw:
        return "Não determinado",None
    try:
        instant=parse_timestamp(raw)
    except (TypeError,ValueError):
        return "Não determinado",None
    for run in reprocess_runs:
        started=str(run.get("started_at") or "").strip()
        completed=str(run.get("completed_at") or "").strip()
        if not started:
            continue
        try:
            start=parse_timestamp(started)
            end=parse_timestamp(completed) if completed else None
        except (TypeError,ValueError):
            continue
        if instant >= start and (end is None or instant <= end):
            return "Reprocessamento",str(run.get("reprocess_id") or "") or None
    return "Processamento",None


def _external_event_time(raw: Mapping[str,Any]) -> Any:
    for key in ("created_at","updated_at","observed_at","captured_at","started_at","finished_at","completed_at"):
        value=raw.get(key)
        if value not in (None,""):
            return value
    return None


def _no_cost_value(value: Any) -> _Html:
    return _Html(f"<span class='no-cost-value'>{escape(str(value))}</span>")


def _is_explicit_zero_cost(value: Any) -> bool:
    if value in (None, ""):
        return False
    try:
        return abs(float(value)) <= 0.000000000001
    except (TypeError, ValueError):
        return False


def _money_display(value: Any, currency: str="USD") -> _Html|str:
    if value in (None, ""):
        return _state_text("NOT_DETERMINABLE","Não precificado")
    try:
        amount=float(value)
    except (TypeError,ValueError):
        return _state_text("NOT_DETERMINABLE","Não precificado")
    text=f"{currency} {amount:.8f}"
    return _no_cost_value(text) if _is_explicit_zero_cost(value) else text


def _signed_money_display(value: Any, currency: str="USD") -> _Html|str:
    if value in (None, ""):
        return _state_text("NOT_DETERMINABLE","Não calculável")
    try:
        amount=float(value)
    except (TypeError,ValueError):
        return _state_text("NOT_DETERMINABLE","Não calculável")
    text=f"{currency} {amount:+.8f}"
    return _no_cost_value(text) if _is_explicit_zero_cost(value) else text


def _money_range_display(low: Any, high: Any, currency: str="USD") -> _Html:
    if low in (None, "") and high in (None, ""):
        return _state_text("NOT_DETERMINABLE","Não precificada")
    low_rendered=_money_display(low,currency)
    high_rendered=_money_display(high,currency)
    low_html=str(low_rendered) if isinstance(low_rendered,_Html) else escape(str(low_rendered))
    high_html=str(high_rendered) if isinstance(high_rendered,_Html) else escape(str(high_rendered))
    return _Html(f"{low_html} - {high_html}")


def _token_pair_display(input_tokens: Any, output_tokens: Any, *, cost: Any) -> _Html|str:
    text=f"{int(input_tokens or 0):,} / {int(output_tokens or 0):,}".replace(","," ")
    try:
        amount=float(cost or 0)
    except (TypeError,ValueError):
        amount=0.0
    return _no_cost_value(text) if _is_explicit_zero_cost(cost) else text


def _token_value_display(value: Any, *, cost: Any) -> _Html|int:
    number=int(value or 0)
    try:
        amount=float(cost or 0)
    except (TypeError,ValueError):
        amount=0.0
    return _no_cost_value(f"{number:,}".replace(","," ")) if _is_explicit_zero_cost(cost) else number


def _ai_exchange_rows(database: Path, audit_id: str) -> list[dict[str,Any]]:
    con=sqlite3.connect(database);con.row_factory=sqlite3.Row
    try:return _audit_rows(con,"ai_exchange_log",audit_id)
    finally:con.close()


def _match_exchange(attempt: Mapping[str,Any], exchanges: Sequence[Mapping[str,Any]], used: set[str]) -> Mapping[str,Any]|None:
    attempt_id=str(attempt.get("attempt_id") or "")
    if attempt_id:
        for ex in exchanges:
            eid=str(ex.get("exchange_id") or "")
            if eid in used:continue
            if str(ex.get("attempt_id") or "")==attempt_id:
                used.add(eid);return ex

    # Backward-compatible fallback for historical databases created before stable
    # attempt correlation existed. New exchanges must match by attempt_id above.
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
            out.append({"name":_friendly_service(r.get("service")),"status":r.get("status"),"attempts":1,"successes":1 if _norm(r.get("status")) in _STATUS_SUCCESS else 0,"duration_ms":r.get("duration_ms"),"http_status":r.get("http_status"),"error":r.get("error_message") or r.get("error_code"),"url":r.get("url"),"reference":r.get("artifact_reference"),"occurred_at":_external_event_time(r),"raw":r})
        direct_external={"w3c-validator","w3c-css-validator","mdn-observatory","web-platform-baseline"}
        for r in _audit_rows(con,"standards_service_runs",audit_id):
            service=str(r.get("service_id") or "")
            if not r.get("requested") or service not in direct_external:continue
            details=_safe_json(r.get("details_json"),{})
            errors=details.get("errors",[]) if isinstance(details,Mapping) else []
            out.append({"name":_friendly_service(service),"status":r.get("state"),"attempts":r.get("targets_attempted",0),"successes":r.get("targets_succeeded",0),"duration_ms":None,"http_status":None,"error":"; ".join(str(v) for v in errors) if isinstance(errors,list) else errors,"url":details.get("endpoint") if isinstance(details,Mapping) else None,"reference":details.get("observations_artifact") if isinstance(details,Mapping) else None,"occurred_at":_external_event_time(r),"raw":r})
        for r in _audit_rows(con,"passive_security_integrations",audit_id):
            integration=str(r.get("integration_id") or "")
            if integration=="MDN_OBSERVATORY":
                continue
            details=_safe_json(r.get("details_json"),{})
            out.append({
                "name":_friendly_service(integration),
                "status":r.get("state"),
                "attempts":r.get("attempts",0),
                "successes":r.get("successes",0),
                "duration_ms":None,
                "http_status":None,
                "error":r.get("error_message") or r.get("error_type"),
                "url":None,
                "reference":r.get("artifact_reference"),
                "occurred_at":_external_event_time(r),
                "raw":{**r,"details_json":details},
            })
        return out
    finally:con.close()


def _ai_usage_detail(attempt: Mapping[str,Any]) -> tuple[str,str,str]:
    contract=str(attempt.get("contract") or "").upper()
    if contract=="IMPROVEMENT-INTELLIGENCE-001" and str(attempt.get("catalog_id") or "")=="CAT-10":
        return (
            "CAT-10 · Segurança passiva",
            "Findings determinísticos/externos de segurança já persistidos, limitados ao domínio SECURITY; a IA não decide presença de headers, versão de componente ou CVE.",
            "Interpretar impacto, priorizar e enriquecer remediação. O resultado é advisory, não executa exploração e não altera scores determinísticos.",
        )
    return _AI_USAGE_DETAILS.get(contract,(attempt.get("catalog_id") or "Transversal","Contexto específico não descrito no contrato desta projeção.","Finalidade registrada pela própria tentativa de IA."))


def _cost_forecast(database: Path, audit_id: str) -> dict[str,Any]:
    con=sqlite3.connect(database);con.row_factory=sqlite3.Row
    try:return _last(con,"console_cost_forecast_outcomes",audit_id)
    finally:con.close()


def _attempt_cost_value(attempt: Mapping[str,Any]) -> Any:
    amount,_currency,_basis=attempt_monetary_cost(attempt)
    if amount is not None:
        return amount
    native = attempt.get("_native_usage")
    if isinstance(native, Sequence):
        priced = [
            row.get("observed_cost")
            if row.get("observed_cost") not in (None, "")
            else row.get("estimated_cost")
            for row in native
            if isinstance(row, Mapping)
            and str(row.get("component_type") or "").upper() in {"REQUEST","CONSUMPTION"}
        ]
        known = [float(value) for value in priced if value not in (None, "")]
        if known:
            return sum(known)
    return None


def _native_usage_display(attempt: Mapping[str,Any], *, include_trace: bool=False) -> str:
    rows = attempt.get("_native_usage")
    if not isinstance(rows, Sequence) or not rows:
        return "Não aplicável"
    rendered = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        quantity = float(row.get("native_usage_quantity") or 0.0)
        unit = str(row.get("native_usage_unit") or "")
        component_type = str(row.get("component_type") or "").upper()
        label = humanize_native_usage_unit(unit, quantity)
        prefix = {
            "REQUEST": "Consumo",
            "CONSUMPTION": "Consumo",
            "RECONCILIATION": "Reconciliação",
            "REFUND": "Reembolso",
            "GRANT": "Crédito concedido",
        }.get(component_type, component_type or "Uso")
        text = f"{quantity:g} {label}"
        if include_trace:
            text = f"{prefix}: {text} · fonte {row.get('source_metric') or 'não informada'}"
        rendered.append(text)
    return "; ".join(rendered) or "Não aplicável"


def _native_usage_summary(attempts: Sequence[Mapping[str,Any]]) -> tuple[str,int]:
    totals: dict[str,float] = {}
    unpriced = 0
    for attempt in attempts:
        rows = attempt.get("_native_usage")
        if not isinstance(rows, Sequence):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            if str(row.get("component_type") or "").upper() not in {"REQUEST","CONSUMPTION"}:
                continue
            unit = str(row.get("native_usage_unit") or "")
            quantity = float(row.get("native_usage_quantity") or 0.0)
            totals[unit] = totals.get(unit, 0.0) + quantity
            if row.get("estimated_cost") in (None, "") and row.get("observed_cost") in (None, ""):
                unpriced += 1
    rendered = "; ".join(
        f"{quantity:g} {humanize_native_usage_unit(unit, quantity)}"
        for unit, quantity in sorted(totals.items())
    )
    return rendered, unpriced


def _attempt_total_tokens(attempt: Mapping[str,Any]) -> int:
    """Return canonical total tokens without double-counting reasoning tokens."""
    return canonical_total_tokens(attempt) or 0


def _pricing_trace_rows(attempt: Mapping[str,Any]) -> tuple[tuple[str,Any], ...]:
    """Human-facing pricing trace for a persisted AI attempt.

    Technical identifiers remain secondary traceability fields. Runtime matching
    conditions are rendered as readable key/value text and never include credentials.
    """
    raw_conditions = _safe_json(attempt.get("pricing_runtime_conditions"), {})
    conditions = raw_conditions if isinstance(raw_conditions, Mapping) else {}
    condition_labels = {
        "commercial_mode": "Modalidade comercial",
        "operation_mode": "Modo de operação",
        "region": "Região",
        "service_tier": "Nível de serviço",
    }
    condition_values = {
        "TRIAL": "Avaliação gratuita (TRIAL)",
        "PRODUCTION": "Produção (PRODUCTION)",
        "REALTIME": "Tempo real (REALTIME)",
        "GLOBAL": "Global (GLOBAL)",
        "STANDARD": "Padrão (STANDARD)",
        "STANDARD_ONLY": "Somente padrão (STANDARD_ONLY)",
        "DEFAULT": "Padrão do provedor (DEFAULT)",
        "PAYG": "Pagamento por uso (PAYG)",
    }
    rendered_conditions = "; ".join(
        f"{condition_labels.get(str(key), str(key))}: "
        f"{condition_values.get(str(value).upper(), str(value))}"
        for key, value in sorted(conditions.items())
    ) or "Não determinadas"

    return (
        ("Regra de preço", attempt.get("pricing_rule_id") or "Não determinada"),
        ("Contexto tarifário", attempt.get("pricing_context") or "Não determinado"),
        ("Versão do catálogo de preços", attempt.get("pricing_version") or "Não determinada"),
        ("Modelo de precificação", attempt.get("pricing_model") or "Token-based / não persistido"),
        ("Superfície comercial", attempt.get("surface") or "Não determinada"),
        ("Fonte oficial de preço", attempt.get("pricing_source_reference") or "Não determinada"),
        ("Condições tarifárias efetivas", rendered_conditions),
    )


def _ai_integrations_body(database: Path, data: _ReportData) -> str:
    attempts=_ai_attempts(database,data.audit_id)
    exchanges=_ai_exchange_rows(database,data.audit_id)
    external=_external_integrations(database,data.audit_id)
    reprocess_runs=_reprocess_runs(database,data.audit_id)
    success=sum(1 for a in attempts if _norm(a.get("status")) in _STATUS_SUCCESS)
    input_tokens=sum(int(a.get("input_tokens") or 0) for a in attempts)
    cached_tokens=sum(int(a.get("cached_input_tokens") or 0) for a in attempts)
    output_tokens=sum(int(a.get("output_tokens") or 0) for a in attempts)
    reasoning_tokens=sum(int(a.get("reasoning_tokens") or 0) for a in attempts)
    total_tokens=sum(_attempt_total_tokens(a) for a in attempts)
    attempt_costs=[_attempt_cost_value(a) for a in attempts]
    total_cost=sum(float(value or 0) for value in attempt_costs)
    native_usage_text,native_unpriced=_native_usage_summary(attempts)
    zero_cost_confirmed=(not attempts) or (
        all(value not in (None,"") for value in attempt_costs)
        and _is_explicit_zero_cost(total_cost)
    )
    rows=[];modals=[];used=set()
    for i,a in enumerate(attempts,1):
        ex=_match_exchange(a,exchanges,used)
        mid=f"ai-attempt-{i}"
        raw_cost=_attempt_cost_value(a)
        cost=float(raw_cost or 0)
        usage_context,inputs,role=_ai_usage_detail(a)
        currency_code=str(a.get("cost_currency") or "USD")
        occurred_at=a.get("started_at") or a.get("finished_at")
        origin,reprocess_id=_execution_origin(occurred_at,reprocess_runs)
        rows.append((
            a.get("purpose"),usage_context,_provider_identity(a.get("provider")),a.get("model") or "-",
            occurred_at or "-",origin,_status_label(a.get("status")),
            _token_pair_display(a.get("input_tokens"),a.get("output_tokens"),cost=raw_cost),
            _native_usage_display(a),
            _money_display(raw_cost,currency_code),_modal_button(mid,"Ver requisição"),
        ))
        body=_kv((
            ("Finalidade",a.get("purpose")),
            ("Aplicação no relatório",usage_context),
            ("Provedor",_provider_identity(a.get("provider"))),
            ("Modelo",a.get("model")),
            ("Data/hora",occurred_at or "-"),
            ("Origem da execução",origin),
            ("Identificador do reprocessamento",reprocess_id or "Não aplicável"),
            ("Resultado da tentativa",_status_label(a.get("status"))),
            ("Tentativa",a.get("attempt_index") or "-"),
            ("Início",a.get("started_at") or "-"),
            ("Fim",a.get("finished_at") or "-"),
            ("Duração",_fmt_number(a.get("duration_ms"),"ms")),
            ("Uso nativo",_native_usage_display(a,include_trace=True)),
            ("Tokens de entrada",_token_value_display(a.get("input_tokens"),cost=raw_cost) if a.get("input_tokens") is not None else "Não informado"),
            ("Entrada em cache",a.get("cached_input_tokens") or 0),
            ("Tokens de saída",_token_value_display(a.get("output_tokens"),cost=raw_cost) if a.get("output_tokens") is not None else "Não informado"),
            ("Tokens de raciocínio",a.get("reasoning_tokens") or 0),
            ("Tokens totais",_attempt_total_tokens(a)),
            ("Custo individual",_money_display(raw_cost,currency_code)),
            *_pricing_trace_rows(a),
            ("Roteamento / contingência",a.get("decision") or a.get("fallback_reason") or "-"),
            ("Erro",a.get("error_detail") or a.get("error_code") or "-"),
        ))
        body+="<h3>Dados envolvidos</h3><p>"+escape(inputs)+"</p>"
        body+="<h3>Papel da IA nesta chamada</h3><p>"+escape(role)+"</p>"
        body+="<h3>O que foi solicitado</h3><p>"+escape(str(a.get("request_message_summary") or "Resumo textual da solicitação não persistido."))+"</p>"
        if ex:
            body+="<h3>Comunicação persistida · solicitação</h3>"+_raw_payload_block(ex.get("request_payload"))
            body+="<h3>Comunicação persistida · resposta</h3>"+_raw_payload_block(ex.get("response_payload"))
            if ex.get("request_truncated") or ex.get("response_truncated"):
                body+="<div class='notice warn'>O log persistido sinaliza truncamento; o relatório não reconstrói conteúdo ausente.</div>"
        else:
            body+="<div class='notice'>O conteúdo bruto da solicitação/resposta não foi persistido para esta tentativa. O relatório exibe somente a telemetria disponível e não inventa a comunicação.</div>"
        body+="<details><summary>Ver contrato técnico da chamada</summary><div class='detail-body'>"+_kv((("Contrato",a.get("contract") or "-"),))+"</div></details>"
        modals.append(_modal(mid,f"{a.get('purpose')} · tentativa {a.get('attempt_index') or i}","Detalhes técnicos da tentativa persistida",body))
    int_rows=[];int_modals=[]
    for i,r in enumerate(external,1):
        mid=f"integration-{i}"
        raw=r["raw"];details=raw.get("details_json")
        occurred_at=r.get("occurred_at") or _external_event_time(raw)
        origin,reprocess_id=_execution_origin(occurred_at,reprocess_runs)
        int_rows.append((
            r["name"],occurred_at or "-",origin,_status_label(r["status"]),
            r["attempts"],r["successes"],
            _fmt_number(r["duration_ms"],"ms") if r["duration_ms"] is not None else "-",
            _modal_button(mid,"Ver integração"),
        ))
        body=_kv((
            ("Serviço",r["name"]),
            ("Data/hora",occurred_at or "-"),
            ("Origem da execução",origin),
            ("Identificador do reprocessamento",reprocess_id or "Não aplicável"),
            ("Resultado",_status_label(r["status"])),
            ("Tentativas / alvos",r["attempts"]),
            ("Sucessos",r["successes"]),
            ("HTTP",r["http_status"] or "-"),
            ("Duração",_fmt_number(r["duration_ms"],"ms") if r["duration_ms"] is not None else "-"),
            ("URL",r["url"] or "-"),
            ("Erro",r["error"] or "-"),
            ("Artefato",r["reference"] or "-"),
        ))
        if details:
            body+="<h3>Detalhes persistidos</h3><div class='pre'>"+escape(_external_details_public_text(details))+"</div>"
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
    input_display=_no_cost_value(f"{input_tokens:,}".replace(","," ")) if zero_cost_confirmed else f"{input_tokens:,}".replace(","," ")
    output_display=_no_cost_value(f"{output_tokens:,}".replace(","," ")) if zero_cost_confirmed else f"{output_tokens:,}".replace(","," ")
    native_metric=_metric('Uso nativo',native_usage_text,'unidades comerciais do provedor; não convertidas em tokens') if native_usage_text else ""
    body+=_section("summary","Resumo do consumo",f"<div class='metric-grid'>{_metric('Tentativas de IA',len(attempts),f'{success} concluída(s)')}{_metric('Tokens de entrada',input_display)}{_metric('Entrada em cache',f'{cached_tokens:,}'.replace(',',' '))}{_metric('Tokens de saída',output_display)}{_metric('Tokens de raciocínio',f'{reasoning_tokens:,}'.replace(',',' '), 'incluídos nos tokens de saída; não somados novamente')}{_metric('Tokens totais',f'{total_tokens:,}'.replace(',',' '),'entrada + saída')}{native_metric}{_metric('Custo técnico observado',_money_display(total_cost,currency),'soma dos custos individuais persistidos')}</div>")
    body+=_section("ai","Requisições de IA",_table(("Finalidade","Aplicação no relatório","Provedor","Modelo","Data/hora","Origem da execução","Resultado","Tokens entrada / saída","Uso nativo","Custo","Detalhe"),rows,empty="Nenhuma tentativa de IA persistida.",sortable=bool(rows),page_size=10 if len(rows)>10 else None)+"".join(modals))
    body+=_section("integrations","Outras integrações",_table(("Serviço","Data/hora","Origem da execução","Resultado","Tentativas","Sucessos","Duração","Detalhe"),int_rows,empty="Nenhuma integração externa reconhecida foi persistida.",sortable=bool(int_rows),page_size=10 if len(int_rows)>10 else None)+"".join(int_modals))

    if forecast:
        cost_html=(
            "<div class='metric-grid'>"
            +_metric("Custo esperado",_money_display(expected,currency))
            +_metric("Custo observado",_money_display(total_cost,currency),"soma das tentativas com preço persistido")
            +_metric("Desvio monetário",_signed_money_display(computed_deviation,currency))
            +_metric("Desvio percentual",f"{computed_percent:+.2f}%" if computed_percent is not None else "Não calculável")
            +_metric("Faixa provável",_money_range_display(forecast.get("likely_low"),forecast.get("likely_high"),currency))
            +_metric("Cenário potencial (P90)",_money_display(forecast.get("potential"),currency))
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
        cost_html=f"<div class='metric-grid'>{_metric('Custo observado',_money_display(total_cost,currency))}{_metric('Previsão pré-execução','Não persistida')}</div><div class='notice'>Sem previsão persistida, o relatório não inventa custo esperado, desvio ou faixa histórica.</div>"
    if native_unpriced:
        cost_html+=f"<div class='notice warn'>{native_unpriced} componente(s) de uso nativo não possuem conversão monetária aplicável; o relatório preserva a unidade observada e não inventa custo zero.</div>"
    body+=_section("cost","Custos e aderência à estimativa",cost_html)
    body+=_section("principles","Como ler esta página","<div class='grid'><div class='card'><h3>CATs</h3><p>Mostram o resultado funcional produzido. Não repetem tokens, solicitações/respostas e custos.</p></div><div class='card'><h3>IA e integrações</h3><p>Centraliza a telemetria e a comunicação externa de cada tentativa e explica quais dados funcionais participaram de cada chamada.</p></div><div class='card'><h3>Segurança</h3><p>Segredos, tokens de autenticação e credenciais são removidos antes da projeção. Conteúdo ausente no log não é reconstruído.</p></div></div>")
    return body


__all__ = [name for name in globals() if not name.startswith("__")]
