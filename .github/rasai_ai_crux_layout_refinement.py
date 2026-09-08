from __future__ import annotations

from pathlib import Path
import re


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, repl: str, *, label: str) -> str:
    result, count = re.subn(pattern, repl, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return result


# ---------------------------------------------------------------------------
# 1) Extended providers: classify HTTP 400 invalid request as request/contract
#    integration failure and send only the JSON-Schema subset supported by the
#    Gemini Interactions API. Local validation remains canonical and strict.
# ---------------------------------------------------------------------------
path = "src/rasai/provider_extensions.py"
text = read(path)
text = replace_once(
    text,
    '    if status == 404 or "model" in token:\n        return ProviderErrorClass.MODEL_ERROR\n    if status >= 500:\n',
    '    if status == 404 or "model" in token:\n        return ProviderErrorClass.MODEL_ERROR\n    if status == 400 or "invalid_request" in token or "invalid argument" in token:\n        return ProviderErrorClass.CONTRACT_ERROR\n    if status >= 500:\n',
    label="provider HTTP 400 classification",
)

helper = r'''

_GEMINI_SCHEMA_KEYWORDS = frozenset({
    "$id", "$defs", "$ref", "$anchor", "type", "format", "title", "description",
    "enum", "items", "prefixItems", "minItems", "maxItems", "minimum", "maximum",
    "anyOf", "oneOf", "properties", "additionalProperties", "required", "propertyOrdering",
})


def gemini_wire_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Project the canonical local schema to Gemini's documented JSON-Schema subset.

    The RASAi local validator remains the source of truth. Unsupported wire-only
    keywords are removed rather than weakening post-response validation.
    """
    def walk(value: Any, parent: str | None = None) -> Any:
        if isinstance(value, list):
            return [walk(item) for item in value]
        if not isinstance(value, Mapping):
            return value
        if parent in {"properties", "$defs"}:
            return {str(key): walk(item) for key, item in value.items()}
        output: dict[str, Any] = {}
        for key, item in value.items():
            if key not in _GEMINI_SCHEMA_KEYWORDS:
                continue
            output[str(key)] = walk(item, str(key))
        return output

    projected = walk(schema)
    if not isinstance(projected, dict):
        raise TypeError("Gemini wire schema must remain an object")
    return projected
'''
marker = "\n\nclass GeminiProvider(IsolatedStructuredSemanticProvider):\n"
if "def gemini_wire_schema(" not in text:
    text = replace_once(text, marker, helper + marker, label="Gemini schema helper")
text = replace_once(
    text,
    '                "schema": hardened_semantic_output_schema(semantic_input.allowed_evidence_ids),\n',
    '                "schema": gemini_wire_schema(hardened_semantic_output_schema(semantic_input.allowed_evidence_ids)),\n',
    label="Gemini semantic wire schema",
)
write(path, text)


# ---------------------------------------------------------------------------
# 2) M24 technical AI: extension providers are real configured providers too.
#    Gemini/XAI/Qwen/Anthropic now get provider-specific wire payloads. A provider
#    quarantined by the semantic stage is UNAVAILABLE, never mislabeled as
#    NOT_CONFIGURED/UNSUPPORTED.
# ---------------------------------------------------------------------------
path = "src/rasai/m24_ai.py"
text = read(path)
text = replace_once(
    text,
    'from rasai.persistence import AuditWorkspace\nfrom rasai.semantic import _extract_json_payload\n',
    'from rasai.persistence import AuditWorkspace\nfrom rasai.provider_extensions import IsolatedStructuredSemanticProvider, gemini_wire_schema\nfrom rasai.semantic import _extract_json_payload\n',
    label="M24 extension imports",
)
text = replace_once(
    text,
    '''    candidates = _candidates(provider)\n    if not candidates:\n        result = M24AiResult(\n            state=ProviderState.NOT_CONFIGURED,\n            reason="AI_NOT_CONFIGURED_OR_UNSUPPORTED_FOR_M24",\n        )\n        _persist_result(workspace, audit_id, result)\n        return result\n''',
    '''    candidates = _candidates(provider)\n    if not candidates:\n        configured_state = _configured_provider_state(provider)\n        if configured_state is not None:\n            result = M24AiResult(\n                state=ProviderState.UNAVAILABLE,\n                reason=f"M24_AI_PROVIDER_{configured_state}",\n            )\n        else:\n            result = M24AiResult(\n                state=ProviderState.NOT_CONFIGURED,\n                reason="AI_NOT_CONFIGURED_FOR_M24",\n            )\n        _persist_result(workspace, audit_id, result)\n        return result\n''',
    label="M24 configured vs unavailable state",
)

new_candidates = r'''def _candidate_items(provider: Any) -> tuple[Any, ...]:
    routed = getattr(provider, "providers", None)
    if isinstance(routed, tuple):
        return tuple(routed)
    return (provider,) if provider is not None else ()


def _supported_candidate(candidate: Any) -> bool:
    return isinstance(candidate, (ResponsesSemanticProvider, IsolatedStructuredSemanticProvider))


def _configured_provider_state(provider: Any) -> str | None:
    configured = [
        item for item in _candidate_items(provider)
        if _supported_candidate(item) and bool(getattr(item, "api_key", None))
    ]
    if not configured:
        return None
    if any(getattr(item, "_runtime_state", RuntimeProviderState.ACTIVE) is RuntimeProviderState.QUARANTINED_FOR_AUDIT for item in configured):
        return "QUARANTINED_FOR_AUDIT"
    return "UNAVAILABLE"


def _candidates(provider: Any) -> tuple[Any, ...]:
    output: list[Any] = []
    for item in _candidate_items(provider):
        if not _supported_candidate(item):
            continue
        if not bool(getattr(item, "api_key", None)):
            continue
        state = getattr(item, "_runtime_state", RuntimeProviderState.ACTIVE)
        if state is RuntimeProviderState.QUARANTINED_FOR_AUDIT:
            continue
        output.append(item)
    return tuple(output)
'''
text = regex_once(
    text,
    r"def _candidates\(provider: Any\).*?\n\ndef _schema\(\) -> dict\[str, Any\]:",
    new_candidates + "\n\ndef _schema() -> dict[str, Any]:",
    label="M24 candidate routing",
)

wire_helpers = r'''

def _candidate_payload(candidate: Any, *, schema: dict[str, Any], instructions: str, facts: list[dict[str, Any]]) -> dict[str, Any]:
    facts_json = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
    name = str(getattr(candidate, "name", "")).upper()
    if isinstance(candidate, IsolatedStructuredSemanticProvider):
        if name == "GEMINI":
            return {
                "model": candidate.model,
                "input": instructions + "\n\nDiagnósticos técnicos persistidos:\n" + facts_json,
                "response_format": {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": gemini_wire_schema(schema),
                },
            }
        if name == "QWEN":
            return {
                "model": candidate.model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": "Diagnósticos técnicos persistidos:\n" + facts_json},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "rasai_m24_technical_remediation", "schema": schema, "strict": True},
                },
            }
        if name == "ANTHROPIC":
            return {
                "model": candidate.model,
                "max_tokens": 8192,
                "system": instructions,
                "messages": [{"role": "user", "content": "Diagnósticos técnicos persistidos:\n" + facts_json}],
                "output_config": {"format": {"type": "json_schema", "schema": schema}},
            }
        # XAI uses the Responses-style contract.
        return {
            "model": candidate.model,
            "instructions": instructions,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "Diagnósticos técnicos persistidos:\n" + facts_json}]}],
            "reasoning": {"effort": str(getattr(candidate, "reasoning_profile", "HIGH")).casefold()},
            "text": {"format": {"type": "json_schema", "name": "rasai_m24_technical_remediation", "schema": schema, "strict": True}},
        }

    if candidate.structured_mode == "json_object":
        local_instructions = instructions + "\nSchema local obrigatório:\n" + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        fmt: dict[str, Any] = {"type": "json_object"}
    else:
        local_instructions = instructions
        fmt = {"type": "json_schema", "name": "rasai_m24_technical_remediation", "schema": schema}
        if candidate.name == "OPENAI":
            fmt["strict"] = True
    return {
        "model": candidate.model,
        "instructions": local_instructions,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Diagnósticos técnicos persistidos:\n" + facts_json}]}],
        "reasoning": {"effort": candidate.requested_reasoning_effort.casefold()},
        "text": {"format": fmt},
    }


def _candidate_usage(candidate: Any, raw: Mapping[str, Any]):
    if isinstance(candidate, IsolatedStructuredSemanticProvider):
        return candidate._usage(raw)
    return _usage_from_native(raw)


def _candidate_native_error(candidate: Any, raw: Mapping[str, Any]):
    if isinstance(candidate, IsolatedStructuredSemanticProvider):
        return candidate._native_error(raw)
    return _response_error(raw)


def _candidate_extract_payload(candidate: Any, raw: Mapping[str, Any]) -> Any:
    if isinstance(candidate, IsolatedStructuredSemanticProvider):
        return candidate._extract_payload(raw)
    return _extract_json_payload(dict(raw))
'''
call_marker = "\n\ndef _call(\n"
if "def _candidate_payload(" not in text:
    text = replace_once(text, call_marker, wire_helpers + call_marker, label="M24 wire helpers")

# Replace the provider-specific payload construction inside _call.
text = regex_once(
    text,
    r'''    schema = _schema\(\)\n    instructions = \(.*?\n    body = json\.dumps\(payload, ensure_ascii=False, separators=\(\",\", \":\"\)\)\.encode\(\"utf-8\"\)''',
    '''    schema = _schema()\n    instructions = (\n        "Você é um especialista técnico em crawling, robots.txt, sitemap e controles de crawlers. "\n        "Responda em português do Brasil e somente em JSON. Use exclusivamente os diagnósticos "\n        "determinísticos fornecidos. Não invente pesos numéricos nem altere a fórmula do SCORE-GEO-004/SARI-001. "\n        "Além das ações, classifique ROBOTS e/ou SITEMAP somente quando houver evidência fornecida, "\n        "usando POSITIVE, NEUTRAL ou NEGATIVE. O runtime converte essa classe por fatores estáticos/versionados. "\n        "Não invente URL, status HTTP, configuração, crawler, evidência, causa raiz, política ou fato. "\n        "Cada ação deve referenciar um diagnostic_code fornecido e somente evidence_ids fornecidos. "\n        "OAI-SearchBot está relacionado à descoberta no ChatGPT Search; GPTBot está relacionado a "\n        "potencial uso para treinamento. Google-Extended é um token de controle de usos específicos "\n        "Google/Gemini e não requisito de inclusão/ranking no Google Search. Nunca recomende liberar "\n        "GPTBot ou Google-Extended como técnica de SEO/Search. Mudanças nesses controles exigem decisão "\n        "de política humana. llms.txt é proposta comunitária experimental, não web standard obrigatório. "\n        "Não apresente sua ausência como defeito nem como requisito GEO. "\n        "Quando a evidência não permitir uma mudança exata e segura, recomende validação humana."\n    )\n    payload = _candidate_payload(candidate, schema=schema, instructions=instructions, facts=facts)\n    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")''',
    label="M24 payload construction",
)
text = replace_once(text, "        usage = _usage_from_native(raw)\n        native_error = _response_error(raw)\n", "        usage = _candidate_usage(candidate, raw)\n        native_error = _candidate_native_error(candidate, raw)\n", label="M24 provider usage/error")
text = replace_once(text, "                _extract_json_payload(dict(raw)),\n", "                _candidate_extract_payload(candidate, raw),\n", label="M24 provider payload extraction")
text = text.replace("    candidate: ResponsesSemanticProvider,\n", "    candidate: Any,\n", 1)
write(path, text)


# ---------------------------------------------------------------------------
# 3) Web Performance/CrUX: distinguish field data carried by PageSpeed from a
#    direct CrUX API fallback. "Not executed" must say why.
# ---------------------------------------------------------------------------
path = "src/rasai/report_consistency_v2.py"
text = read(path)
old_success = '''            reason = "Coleta PageSpeed/CrUX desabilitada por configuração." if not enabled else (\n                "Todos os contextos configurados obtiveram evidência utilizável." if status == "SUCCESS"\n                else str(web["reason"] or "Uma ou mais fontes não produziram evidência utilizável; consulte as tentativas de Web Performance.")\n            )\n'''
new_success = '''            if not enabled:\n                reason = "Coleta PageSpeed/CrUX desabilitada por configuração."\n            elif status == "SUCCESS":\n                observations = _many(db, "SELECT field_source FROM web_performance_observations WHERE audit_id=?", audit_id)\n                attempts = _many(db, "SELECT service,status FROM web_performance_attempts WHERE audit_id=?", audit_id)\n                embedded = sum(str(row["field_source"] or "").upper() == "PAGESPEED_CRUX" for row in observations)\n                direct_attempts = sum(str(row["service"] or "").upper() == "CRUX_API" for row in attempts)\n                direct_successes = sum(str(row["service"] or "").upper() == "CRUX_API" and str(row["status"] or "") == "SUCCESS" for row in attempts)\n                reason = (\n                    f"Todos os contextos configurados obtiveram evidência utilizável. Field data CrUX via resposta PageSpeed: {embedded}; "\n                    f"CrUX API direta (fallback): {direct_successes}/{direct_attempts} sucesso(s)/tentativa(s)."\n                )\n            else:\n                reason = str(web["reason"] or "Uma ou mais fontes não produziram evidência utilizável; consulte as tentativas de Web Performance.")\n'''
text = replace_once(text, old_success, new_success, label="Web Performance coverage reason")
text = replace_once(
    text,
    '        categories = _json_list(run["categories"]) if run is not None else []\n',
    '        categories = _json_list(run["categories"]) if run is not None else []\n        configured_field_source = str(run["field_source"] or "auto").casefold() if run is not None else "auto"\n',
    label="CrUX configured field source",
)
old_crux = '''            if crux is None:\n                crux_status = "NÃO EXECUTADO"\n                crux_reason = (\n                    "Dados de campo vieram do PageSpeed."\n                    if str(observation["field_source"] or "") == "PAGESPEED_CRUX"\n                    else "CrUX direto não foi necessário/configurado ou não havia credencial elegível."\n                )\n            else:\n                crux_status, crux_reason = str(crux["status"]), _attempt_reason(crux)\n'''
new_crux = '''            if crux is None:\n                effective_field_source = str(observation["field_source"] or "").upper()\n                if effective_field_source == "PAGESPEED_CRUX":\n                    crux_status = "NÃO NECESSÁRIO"\n                    crux_reason = "Field data CrUX foi obtido na própria resposta PageSpeed; a CrUX API direta é fallback e por isso não foi chamada."\n                elif configured_field_source == "none":\n                    crux_status = "DESABILITADO POR CONFIGURAÇÃO"\n                    crux_reason = "Field data foi explicitamente desabilitado; somente Lighthouse lab era elegível."\n                elif configured_field_source == "pagespeed":\n                    crux_status = "NÃO SOLICITADO POR CONFIGURAÇÃO"\n                    crux_reason = "A configuração restringiu field data ao PageSpeed e não habilitou fallback direto CrUX."\n                elif configured_field_source == "crux":\n                    crux_status = "NÃO MATERIALIZADO"\n                    crux_reason = "A configuração solicitou CrUX direto, mas nenhuma tentativa CRUX_API foi persistida; revisar elegibilidade da credencial e o fluxo de coleta."\n                else:\n                    crux_status = "NÃO MATERIALIZADO"\n                    crux_reason = "Modo auto não obteve field data via PageSpeed e nenhuma tentativa direta CrUX foi persistida; revisar credencial/elegibilidade ou fluxo."\n            else:\n                crux_status, crux_reason = str(crux["status"]), _attempt_reason(crux)\n'''
text = replace_once(text, old_crux, new_crux, label="CrUX direct fallback semantics")
text = text.replace("<th>CrUX direto</th><th>Motivo CrUX</th>", "<th>CrUX API direta (fallback)</th><th>Motivo / origem do field data</th>")
write(path, text)


# ---------------------------------------------------------------------------
# 4) AI reporting: explain origin and remediation of provider errors. HTTP 400
#    invalid_request is explicitly an integration/request-contract problem, not
#    missing key and not a website finding.
# ---------------------------------------------------------------------------
path = "src/rasai/m18_reporting.py"
text = read(path)
helpers = r'''

def _failure_origin(row: Any) -> tuple[str, str]:
    status = str(_row_value(row, "status", "") or "").upper()
    error_class = str(_row_value(row, "error_class", "") or "").upper()
    error_code = str(_row_value(row, "error_code", "") or "").casefold()
    http_status = _row_value(row, "http_status")
    if status == "NOT_CONFIGURED" or error_class in {"AUTH_ERROR", "PERMISSION_ERROR", "MODEL_ERROR"}:
        return "CONFIGURAÇÃO", "Revisar credencial, permissão, modelo e endpoint selecionados."
    if error_class in {"CONTRACT_ERROR", "INVALID_RESPONSE", "EMPTY_RESPONSE"} or http_status == 400 or "invalid_request" in error_code:
        return "CONTRATO / INTEGRAÇÃO", "A chamada chegou ao provider, mas request/response não satisfez o contrato esperado. Revisar adapter/schema/modelo; não atribuir ao website."
    if error_class in {"QUOTA_ERROR", "CREDIT_ERROR", "RATE_LIMIT_ERROR", "SERVER_ERROR", "TIMEOUT_ERROR", "NETWORK_ERROR"}:
        return "SERVIÇO EXTERNO", "Revisar quota/saldo, disponibilidade, rede e timeout conforme a classe persistida."
    if status in {"QUARANTINED", "QUARANTINED_FOR_AUDIT"}:
        return "DERIVADO DE FALHA ANTERIOR", "O provider foi isolado para evitar repetição de uma falha já observada neste AUD."
    return "OPERACIONAL / NÃO CLASSIFICADO", "Consultar HTTP, error class/code e logs sanitizados; não inferir falha do website."


def _failure_origin_summary(failures: list[sqlite3.Row]) -> str:
    if not failures:
        return ""
    rows = []
    for row in failures[:8]:
        origin, guidance = _failure_origin(row)
        provider = f"{_row_value(row, 'provider', '-')}/{_row_value(row, 'model', '-')}"
        detail = " · ".join(
            item for item in (
                f"HTTP {_row_value(row, 'http_status')}" if _row_value(row, "http_status") is not None else "",
                str(_row_value(row, "error_class", "") or ""),
                f"code={_row_value(row, 'error_code')}" if _row_value(row, "error_code") else "",
            ) if item
        ) or str(_row_value(row, "status", "-") or "-")
        rows.append(
            f"<tr><td>{escape(provider)}</td><td><strong>{escape(origin)}</strong></td><td>{escape(detail)}</td><td>{escape(guidance)}</td></tr>"
        )
    return (
        "<div class='notice warn ai-failure-origin'><strong>Diagnóstico operacional das falhas de IA</strong>"
        "<p>Esta classificação explica onde investigar. Falha de provider/adapter não é finding do website e não recebe peso negativo no SARI.</p>"
        "<div class='table-wrap'><table><thead><tr><th>Provider</th><th>Origem</th><th>Evidência persistida</th><th>O que revisar</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></div>"
    )
'''
marker = "\n\ndef _report_section(session: sqlite3.Row, attempts: list[sqlite3.Row], snapshot_count: int) -> str:\n"
if "def _failure_origin(" not in text:
    text = replace_once(text, marker, helpers + marker, label="AI error origin helpers")
text = replace_once(text, "    failure_detail = _failure_detail(attempts)\n", "    failure_detail = _failure_detail(attempts)\n    failure_origin = _failure_origin_summary(failures)\n", label="AI failure origin calculation")
text = replace_once(text, '        f"{failure_detail}"\n        "<h3>Relatório detalhado de uso da IA</h3>', '        f"{failure_detail}"\n        f"{failure_origin}"\n        "<h3>Relatório detalhado de uso da IA</h3>', label="AI failure origin rendering")
write(path, text)


# ---------------------------------------------------------------------------
# 5) Readiness reporting must be null-safe when semantic AI fails. An unavailable
#    score is not numeric zero and must never crash report generation.
# ---------------------------------------------------------------------------
path = "src/rasai/rasai_readiness_reporting.py"
text = read(path)
old = '            f"o score {float(overall[\'value\']):.1f}/100 descreve a qualidade dos grupos efetivamente avaliados; a Confidence qualifica a força da medição. "\n'
new = '            f"{(\'o score \' + format(float(overall[\'value\']), \'.1f\') + \'/100 descreve a qualidade dos grupos efetivamente avaliados\' if overall[\'value\'] is not None else \'o score numérico não foi consolidado porque a evidência aplicável ficou insuficiente\')}; a Confidence qualifica a força da medição. "\n'
text = replace_once(text, old, new, label="null-safe SARI dashboard explanation")
write(path, text)


# ---------------------------------------------------------------------------
# 6) Shared visual contract: configuration-heavy card grids become vertical
#    accordions (closed by default), and nested gray/white blocks get breathing
#    room. The transformer is conservative and only touches configuration panels
#    with multiple recognized configuration card headings.
# ---------------------------------------------------------------------------
path = "src/rasai/report_navigation.py"
text = read(path)
css_anchor = ".page-card+.page-card{margin-top:16px}.ref-card{box-shadow:0 2px 9px rgba(47,58,78,.025)}\n"
css_add = r'''.page-card+.page-card{margin-top:16px}.ref-card{box-shadow:0 2px 9px rgba(47,58,78,.025)}
.panel>.metric-grid,.panel>.grid,.panel>.score-grid,.panel>.table-wrap,.panel>.notice,.panel>.page-card,.panel>details{margin-block:14px}
.panel>:is(.metric-grid,.grid,.score-grid,.table-wrap,.notice,.page-card,details)+:is(.metric-grid,.grid,.score-grid,.table-wrap,.notice,.page-card,details){margin-top:16px}
.metric,.score-meta div,.page-summary div,.remediation-grid>div,.confidence-explain>div,.ref-card{overflow-wrap:anywhere;word-break:normal}
.config-accordion-stack{display:grid;grid-template-columns:1fr;gap:10px;margin:14px 0 18px}
.config-accordion{display:block;width:100%;min-width:0;margin:0!important;border:1px solid var(--line);border-radius:7px;background:#fbfbfc;overflow:hidden}
.config-accordion>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 15px;cursor:pointer;background:#f5f6f8;font-size:.9rem;font-weight:680;list-style:none}
.config-accordion>summary::-webkit-details-marker{display:none}.config-accordion>summary::after{content:'+';font-size:1.05rem;color:var(--muted);font-weight:500}.config-accordion[open]>summary::after{content:'−'}
.config-accordion-body{padding:14px 15px 16px;background:#fff}.config-accordion-body>:first-child{margin-top:0}.config-accordion-body>:last-child{margin-bottom:0}
.config-accordion-body .metric-grid,.config-accordion-body .grid{margin-block:10px;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr))}
.config-accordion-body code,.config-accordion-body strong,.config-accordion-body span{overflow-wrap:anywhere}
'''
text = replace_once(text, css_anchor, css_add, label="shared report spacing and accordion CSS")

transformer = r'''

_CONFIG_PANEL_RE = re.compile(
    r"<section(?P<attrs>[^>]*\bclass=(?P<q>['\"])[^'\"]*\bpanel\b[^'\"]*(?P=q)[^>]*)>(?P<body>.*?)</section>",
    flags=re.IGNORECASE | re.DOTALL,
)
_CONFIG_CARD_RE = re.compile(
    r"<article(?P<attrs>[^>]*\bclass=(?P<q>['\"])[^'\"]*\bref-card\b[^'\"]*(?P=q)[^>]*)>(?P<body>.*?)</article>",
    flags=re.IGNORECASE | re.DOTALL,
)
_CONFIG_TITLE_RE = re.compile(r"<h3[^>]*>(?P<title>.*?)</h3>", flags=re.IGNORECASE | re.DOTALL)
_CONFIG_HEADING_HINTS = (
    "auditoria", "ia semântica", "ia semantica", "remediação", "remediacao",
    "web performance", "apdex", "contexto editorial", "pagespeed", "crux",
)


def _plain_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value).replace("&nbsp;", " ").strip()


def _enhance_configuration_accordions(html: str) -> str:
    def replace_panel(match: re.Match[str]) -> str:
        body = match.group("body")
        cards = list(_CONFIG_CARD_RE.finditer(body))
        if len(cards) < 3:
            return match.group(0)
        titles: list[str] = []
        for card in cards:
            title_match = _CONFIG_TITLE_RE.search(card.group("body"))
            titles.append(_plain_html(title_match.group("title")) if title_match else "")
        recognized = sum(any(hint in title.casefold() for hint in _CONFIG_HEADING_HINTS) for title in titles)
        panel_text = _plain_html(body).casefold()
        if recognized < 2 or "configura" not in panel_text:
            return match.group(0)

        def replace_card(card_match: re.Match[str]) -> str:
            card_body = card_match.group("body")
            title_match = _CONFIG_TITLE_RE.search(card_body)
            if title_match is None:
                return card_match.group(0)
            title_html = title_match.group("title")
            remainder = card_body[:title_match.start()] + card_body[title_match.end():]
            return (
                "<details class='config-accordion'>"
                f"<summary>{title_html}</summary>"
                f"<div class='config-accordion-body'>{remainder}</div></details>"
            )

        converted = _CONFIG_CARD_RE.sub(replace_card, body)
        converted = re.sub(
            r"<div\s+class=(['\"])grid\1>",
            "<div class='config-accordion-stack'>",
            converted,
            count=1,
            flags=re.IGNORECASE,
        )
        return f"<section{match.group('attrs')}>{converted}</section>"

    return _CONFIG_PANEL_RE.sub(replace_panel, html)
'''
marker = "\n\ndef available_navigation(report_dir: Path, current: str | None = None) -> tuple[tuple[str, str], ...]:\n"
if "def _enhance_configuration_accordions(" not in text:
    text = replace_once(text, marker, transformer + marker, label="configuration accordion transformer")
text = replace_once(
    text,
    "        normalized = enhance_report_html(normalized, page_name=html_path.name, report_dir=report_dir)\n        normalized = _enhance_rule_tooltips(normalized)\n",
    "        normalized = enhance_report_html(normalized, page_name=html_path.name, report_dir=report_dir)\n        normalized = _enhance_configuration_accordions(normalized)\n        normalized = _enhance_rule_tooltips(normalized)\n",
    label="configuration accordion application",
)
write(path, text)


# ---------------------------------------------------------------------------
# 7) Documentation: explicitly describe Gemini failure diagnostics and CrUX
#    direct-fallback semantics so UI and docs tell the same story.
# ---------------------------------------------------------------------------
path = "docs/AI_PROVIDER_EXTENSIONS.md"
text = read(path)
append = r'''

## Diagnóstico operacional de providers estendidos

Uma chave configurada e uma tentativa HTTP persistida provam que o provider foi chamado; não provam que o request foi aceito. HTTP 400/`invalid_request` é classificado como erro de contrato/integração do request, não como ausência de credencial e nunca como finding do website. O provider pode ser isolado (`QUARANTINED_FOR_AUDIT`) para evitar repetição da mesma falha no AUD.

As finalidades técnicas de crawling/discovery aceitam os providers estendidos explícitos quando o adapter possui contrato wire compatível. Se um provider já foi isolado pela análise semântica, a finalidade técnica o apresenta como indisponível/quarantined, não como `NOT_CONFIGURED`.

Para Gemini, o schema enviado pela Interactions API é projetado para o subconjunto JSON Schema aceito no wire; a validação local completa do RASAi continua obrigatória após a resposta.
'''
if "## Diagnóstico operacional de providers estendidos" not in text:
    text = text.rstrip() + append + "\n"
write(path, text)

path = "docs/GOOGLE_API_KEYS.md"
text = read(path)
append = r'''

## CrUX via PageSpeed versus CrUX API direta

Em `field_source=auto`, `CrUX` pode ser materializado sem uma chamada `CRUX_API`: o PageSpeed Insights pode retornar field data CrUX no mesmo payload usado pelo Lighthouse. Nesse caso o report deve apresentar `PAGESPEED_CRUX` como fonte efetiva e `CrUX API direta: NÃO NECESSÁRIO`, porque a chamada direta é apenas fallback. `crux_attempts=0` sozinho, portanto, não significa que Core Web Vitals não foram coletados.

Quando não houver field data no PageSpeed, o report diferencia explicitamente: desabilitado por configuração, não solicitado pelo modo escolhido, tentativa direta com erro/quota/HTTP, ou ausência inesperada de tentativa que requer revisão do fluxo/configuração. Ausência de field data permanece indisponibilidade de medição e não é transformada em falha do website.
'''
if "## CrUX via PageSpeed versus CrUX API direta" not in text:
    text = text.rstrip() + append + "\n"
write(path, text)


# ---------------------------------------------------------------------------
# 8) Regression tests for this exact smoke backlog.
# ---------------------------------------------------------------------------
test_path = Path("tests/test_ai_crux_layout_refinement.py")
test_path.write_text(r'''from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
from urllib.error import HTTPError
import io

from rasai.m18_ai import ProviderErrorClass, ProviderState, RuntimeProviderState
from rasai.m24_ai import _candidates, _configured_provider_state
from rasai.provider_extensions import GeminiProvider, _diagnostic_from_http, gemini_wire_schema
from rasai.report_navigation import _enhance_configuration_accordions
from rasai.report_consistency_v2 import _contexts
from rasai.persistence import AuditWorkspace


def test_gemini_http_400_invalid_request_is_contract_integration_error() -> None:
    body = io.BytesIO(json.dumps({"error": {"code": "invalid_request", "type": "invalid_request"}}).encode())
    exc = HTTPError("https://example.invalid", 400, "bad", {}, body)
    diagnostic = _diagnostic_from_http(exc)
    assert diagnostic.error_class is ProviderErrorClass.CONTRACT_ERROR
    assert diagnostic.http_status == 400
    assert diagnostic.error_code == "invalid_request"


def test_gemini_wire_schema_removes_unsupported_keywords_but_preserves_properties() -> None:
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 50},
            "items": {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
        },
        "required": ["name", "items"],
        "additionalProperties": False,
    }
    projected = gemini_wire_schema(schema)
    assert set(projected["properties"]) == {"name", "items"}
    assert "minLength" not in projected["properties"]["name"]
    assert "uniqueItems" not in projected["properties"]["items"]
    assert projected["required"] == ["name", "items"]


def test_m24_recognizes_configured_gemini_and_distinguishes_quarantine() -> None:
    provider = GeminiProvider(model="gemini-3.8-flash", api_key="test-key", transport=lambda *_: {})
    assert _candidates(provider) == (provider,)
    provider._runtime_state = RuntimeProviderState.QUARANTINED_FOR_AUDIT
    assert _candidates(provider) == ()
    assert _configured_provider_state(provider) == "QUARANTINED_FOR_AUDIT"


def test_configuration_panels_become_closed_vertical_accordions() -> None:
    html = """<section class='panel'><h2>Configuração utilizada neste AUD</h2><div class='grid'>
    <article class='ref-card'><h3>Auditoria</h3><p>Max pages 1</p></article>
    <article class='ref-card'><h3>IA semântica</h3><p>Gemini</p></article>
    <article class='ref-card'><h3>Web Performance</h3><p>auto</p></article>
    </div></section>"""
    result = _enhance_configuration_accordions(html)
    assert "config-accordion-stack" in result
    assert result.count("<details class='config-accordion'>") == 3
    assert "<details class='config-accordion' open" not in result


def test_crux_embedded_in_pagespeed_is_reported_as_direct_api_not_needed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = AuditWorkspace(Path(tmp) / "AUD-X")
        workspace.root.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(workspace.database)
        db.executescript("""
        CREATE TABLE web_performance_runs(audit_id TEXT, enabled INTEGER, status TEXT, field_source TEXT, categories TEXT);
        CREATE TABLE pages(page_id TEXT, audit_id TEXT, normalized_url TEXT);
        CREATE TABLE web_performance_observations(
          audit_id TEXT,page_id TEXT,snapshot_id TEXT,device TEXT,normalized_url TEXT,
          accessibility_score REAL,pagespeed_artifact_reference TEXT,error_summary TEXT,field_source TEXT
        );
        CREATE TABLE web_performance_attempts(
          audit_id TEXT,page_id TEXT,snapshot_id TEXT,service TEXT,status TEXT,http_status INTEGER,error_code TEXT,error_message TEXT,created_at TEXT,attempt_id TEXT
        );
        """)
        db.execute("INSERT INTO web_performance_runs VALUES (?,?,?,?,?)", ("AUD-X",1,"SUCCESS","auto",json.dumps(["accessibility"])))
        db.execute("INSERT INTO pages VALUES (?,?,?)", ("P1","AUD-X","https://example.com/"))
        db.execute("INSERT INTO web_performance_observations VALUES (?,?,?,?,?,?,?,?,?)", ("AUD-X","P1","S1","MOBILE","https://example.com/",90,"artifact.json",None,"PAGESPEED_CRUX"))
        db.execute("INSERT INTO web_performance_attempts VALUES (?,?,?,?,?,?,?,?,?,?)", ("AUD-X","P1","S1","PAGESPEED_INSIGHTS","SUCCESS",200,None,None,"2026-01-01","A1"))
        db.commit(); db.close()
        contexts = _contexts("AUD-X", workspace)
        assert len(contexts) == 1
        assert contexts[0].crux_status == "NÃO NECESSÁRIO"
        assert "própria resposta PageSpeed" in contexts[0].crux_reason
''', encoding="utf-8", newline="\n")

print("RASAi AI/CrUX/layout refinement patch applied")
