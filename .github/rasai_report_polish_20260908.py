from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def replace(path: str, old: str, new: str, *, count: int | None = None) -> None:
    text = read(path)
    occurrences = text.count(old)
    if occurrences == 0:
        raise RuntimeError(f"replacement anchor not found in {path}: {old[:120]!r}")
    if count is not None and occurrences != count:
        raise RuntimeError(f"unexpected occurrence count in {path}: {occurrences} != {count} for {old[:120]!r}")
    write(path, text.replace(old, new))


def append_once(path: str, marker: str, block: str) -> None:
    text = read(path)
    if marker in text:
        return
    write(path, text.rstrip() + "\n\n" + block.strip() + "\n")


# ---------------------------------------------------------------------------
# 1. Functional fix: canonical readiness/M24 projection must match live schema.
# ---------------------------------------------------------------------------
replace(
    "src/rasai/rasai_readiness_reporting.py",
    '"SELECT * FROM m24_runs WHERE audit_id=? ORDER BY completed_at DESC LIMIT 1",',
    '"SELECT * FROM m24_runs WHERE audit_id=? LIMIT 1",',
    count=1,
)

# Make the canonical readiness vocabulary user-facing while preserving method
# terms in explanatory prose when they add technical value.
replace(
    "src/rasai/rasai_readiness_reporting.py",
    "Score, Coverage, Confidence e Consolidation ficam centralizados nesta página.",
    "Pontuação, Cobertura, Confiança e Consolidação ficam centralizadas nesta página.",
    count=1,
)
replace(
    "src/rasai/rasai_readiness_reporting.py",
    "<th>Dimensão</th><th>Score</th><th>Coverage</th><th>Confidence</th><th>Consolidação</th>",
    "<th>Dimensão</th><th>Pontuação</th><th>Cobertura</th><th>Confiança</th><th>Consolidação</th>",
    count=1,
)
replace(
    "src/rasai/rasai_readiness_reporting.py",
    "<small>Coverage</small><strong>{coverage}</strong></div><div><small>Confidence</small>",
    "<small>Cobertura</small><strong>{coverage}</strong></div><div><small>Confiança</small>",
    count=1,
)

# ---------------------------------------------------------------------------
# 2. Public labels: persisted enums stay unchanged; HTML becomes readable.
# ---------------------------------------------------------------------------
presentation = read("src/rasai/report_presentation.py")
anchor = '    "WARM": "Aquecida (warm)",\n}'
extra_labels = '''    "WARM": "Aquecida (warm)",
    # AI routing and provider states.
    "SINGLE_PROVIDER": "Provedor único",
    "AUTO": "Automática",
    "NONE": "Nenhuma",
    "CHAIN_EXHAUSTED": "Cadeia de provedores esgotada",
    "PROVIDER_UNAVAILABLE": "Provedor indisponível",
    "CONTRACT_ERROR": "Erro no contrato de evidências",
    "QUARANTINED_FOR_AUDIT": "Indisponível nesta auditoria",
    # Crawling/discovery and content-remediation machine values.
    "ABSENT": "Ausente",
    "PRESENT": "Presente",
    "AVAILABLE": "Disponível",
    "AI_ACCESS": "Acesso por sistemas de IA",
    "BOUNDED_AI_RESOURCE_ASSESSMENT": "Avaliação por IA com escopo limitado",
    "MISSING_PROPOSED": "Proposta não gerada",
    "INTERNAL_BASELINE": "Referência interna",
    "RULES_GUIDE": "Guia de regras",
    "SCORING_GUIDE": "Guia de pontuação",
    "ADD_ATTRIBUTION": "Adicionar atribuição",
    "ADD_FACTUAL_CONTEXT": "Adicionar contexto factual",
    "ADD_OR_CORRECT": "Adicionar ou corrigir",
    "ADD_OR_RESTRUCTURE_ANSWER": "Adicionar ou reestruturar resposta",
    "ADD_QUALIFIERS": "Adicionar qualificadores",
    "CANONICAL_ABSENT": "Canonical ausente",
    "CLOSE_INTENT_GAPS": "Fechar lacunas de intenção",
    "CONTENT_REGION": "Região de conteúdo",
    "CORRECT_RESOURCE": "Corrigir recurso",
    "CORRECT_STRUCTURED_DATA": "Corrigir dados estruturados",
    "DOCUMENT_OR_CONTENT": "Documento ou conteúdo",
    "DOMAIN_RESOURCE": "Recurso do domínio",
    "REVIEW_AND_CORRECT": "Revisar e corrigir",
    "ROBOTS_ABSENT": "robots.txt ausente",
    "SITEMAP_ABSENT": "Sitemap ausente",
    "VERY_HIGH": "Muito alta",
    # Rule groups/dimensions that may appear in technical tables.
    "CONTENT_EXTRACTION": "Extração de conteúdo",
    "DUPLICATE_CONTENT": "Conteúdo duplicado",
    "ENTITY_AMBIGUITY": "Ambiguidade de entidade",
    "ENTITY_CONTEXT": "Contexto de entidade",
    "ENTITY_PRIMARY": "Entidade principal",
    "EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1": "Peso igual entre dimensões aplicáveis",
    "FACTUAL_CLAIMS": "Afirmações factuais",
    "FACTUAL_CONTEXT": "Contexto factual",
    "INDEX_DIRECTIVES": "Diretivas de indexação",
    "INFERENCE_LOAD": "Carga de inferência",
    "INTENT_GAPS": "Lacunas de intenção",
    "INTENT_SET": "Conjunto de intenções",
    "INTERNAL_LINKS": "Links internos",
    "JS_CONTENT": "Conteúdo por JavaScript",
    "PAGE_ACCESS": "Acesso à página",
    "PRIMARY_ANSWERS": "Respostas principais",
    "PRIMARY_INTENT": "Intenção principal",
    "REDIRECT": "Redirecionamentos",
    "RENDER_ACCESS": "Acesso após renderização",
    "ROBOTS": "robots.txt",
    "SEMANTIC_HIERARCHY": "Hierarquia semântica",
    "SEMANTIC_TITLE": "Título semântico",
    "SEMANTIC_TOPIC": "Tópico semântico",
    "SITEMAP": "Sitemap",
    "SOFT_ERROR": "Erro aparente",
    "SPA_NAVIGATION": "Navegação SPA",
    "SPA_ROUTE": "Rota SPA",
    "STRUCTURED_DATA_SYNTAX": "Sintaxe de dados estruturados",
    # Web Performance diagnostic categories.
    "CRITICAL_PATH": "Caminho crítico",
    "JAVASCRIPT_MAIN_THREAD": "Thread principal de JavaScript",
    "LAYOUT_STABILITY": "Estabilidade de layout",
    "PAGESPEED_CRUX": "PageSpeed / CrUX",
    "PAGESPEED_INSIGHTS": "PageSpeed Insights",
    "RENDER_BLOCKING": "Bloqueio de renderização",
    "SERVER_DOCUMENT": "Documento do servidor",
    "THIRD_PARTY": "Terceiros",
}'''
if anchor not in presentation:
    raise RuntimeError("report_presentation label anchor not found")
presentation = presentation.replace(anchor, extra_labels, 1)

old_humanize = '''def humanize_report_html(html: str, *, page_name: str | None = None) -> str:
    """Humanize only isolated primary values in generated HTML.

    ``page_name`` is accepted for future domain-specific refinements, but the
    current contract intentionally uses only conservative cross-report states.
    """
    del page_name

    def replace(match: re.Match[str]) -> str:
        value = match.group("value")
        label = _PUBLIC_LABELS.get(value)
        if label is None:
            return match.group(0)
        return f"{match.group(1)}{label}{match.group(4)}"

    return _VISIBLE_VALUE_RE.sub(replace, html)
'''
new_humanize = '''_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)", flags=re.DOTALL)
_PUBLIC_TOKEN_RE = re.compile(
    r"(?<![A-Z0-9_])(" + "|".join(
        re.escape(value) for value in sorted(_PUBLIC_LABELS, key=len, reverse=True)
    ) + r")(?![A-Z0-9_])"
)


def humanize_report_html(html: str, *, page_name: str | None = None) -> str:
    """Humanize known machine values without mutating persisted or code content.

    Values are translated both when isolated in primary cells and when embedded
    in normal visible prose. ``code``, ``pre``, ``script`` and ``style`` remain
    untouched so technical identifiers, environment variables and examples keep
    their canonical representation.
    """
    del page_name

    def isolated(match: re.Match[str]) -> str:
        value = match.group("value")
        label = _PUBLIC_LABELS.get(value)
        if label is None:
            return match.group(0)
        return f"{match.group(1)}{label}{match.group(4)}"

    html = _VISIBLE_VALUE_RE.sub(isolated, html)
    parts = _TAG_SPLIT_RE.split(html)
    blocked_depth = 0
    output: list[str] = []
    for part in parts:
        if part.startswith("<"):
            lowered = part.lower()
            if re.match(r"<(script|style|pre|code)\\b", lowered):
                blocked_depth += 1
            elif re.match(r"</(script|style|pre|code)\\b", lowered):
                blocked_depth = max(0, blocked_depth - 1)
            output.append(part)
            continue
        if blocked_depth:
            output.append(part)
            continue
        output.append(_PUBLIC_TOKEN_RE.sub(lambda match: _PUBLIC_LABELS[match.group(1)], part))
    return "".join(output)
'''
if old_humanize not in presentation:
    raise RuntimeError("humanize_report_html anchor not found")
presentation = presentation.replace(old_humanize, new_humanize, 1)
write("src/rasai/report_presentation.py", presentation)

# ---------------------------------------------------------------------------
# 3. Global actionable-result visual contract for report tables/lists.
# ---------------------------------------------------------------------------
semantics = read("src/rasai/report_semantics.py")
css_anchor = ".semantic-legend{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 2px;color:var(--muted);font-size:.76rem}.semantic-legend .result-tag{margin:0}\n"
css_add = css_anchor + ".result-cell{font-weight:650}.result-cell .result-tag{margin-top:0}.result-cell.good{background:rgba(95,150,116,.08)}.result-cell.warn{background:rgba(182,138,80,.10)}.result-cell.bad{background:rgba(191,111,112,.10)}\n"
if css_anchor not in semantics:
    raise RuntimeError("semantic CSS anchor not found")
semantics = semantics.replace(css_anchor, css_add, 1)

regex_anchor = "_PROFILE_RE = re.compile(r\"<p class=['\\\"]intro['\\\"]><strong>Perfil sintético:</strong>.*?</p>\", flags=re.IGNORECASE | re.DOTALL)\n"
regex_add = regex_anchor + '''_TABLE_ROW_RE = re.compile(r"<tr(?P<attrs>[^>]*)>(?P<body>.*?)</tr>", flags=re.IGNORECASE | re.DOTALL)
_TABLE_CELL_RE = re.compile(r"<td(?P<attrs>[^>]*)>(?P<body>.*?)</td>", flags=re.IGNORECASE | re.DOTALL)
_ACTIONABLE_GOOD = {"pass", "aprovado", "success", "concluído", "consolidado"}
_ACTIONABLE_WARN = {"warning", "alerta", "partial", "parcial", "degraded", "degradado", "not_consolidated", "não consolidado", "concluído com limitações", "complete_with_limitations"}
_ACTIONABLE_BAD = {"fail", "failed", "não aprovado", "reprovado", "error", "erro", "falhou", "blocked", "bloqueado"}
'''
if regex_anchor not in semantics:
    raise RuntimeError("semantic regex anchor not found")
semantics = semantics.replace(regex_anchor, regex_add, 1)

old_pipeline = '''    html = _decorate_metrics(html, page_name)
    if page_name in {"mobile.html", "desktop.html"}:
'''
new_pipeline = '''    html = _decorate_metrics(html, page_name)
    html = _decorate_actionable_rows(html)
    html = _translate_readiness_table_headers(html)
    if page_name in {"mobile.html", "desktop.html"}:
'''
if old_pipeline not in semantics:
    raise RuntimeError("semantic pipeline anchor not found")
semantics = semantics.replace(old_pipeline, new_pipeline, 1)

helper_anchor = "\ndef _plain(value: str) -> str:\n"
helpers = r'''
def _merge_class_attr(attrs: str, class_name: str) -> str:
    match = re.search(r"\sclass=(?P<q>['\"])(?P<classes>[^'\"]*)(?P=q)", attrs, flags=re.IGNORECASE)
    if match is None:
        return attrs.rstrip() + f" class='{class_name}'"
    classes = match.group("classes").split()
    if class_name not in classes:
        classes.append(class_name)
    replacement = f" class={match.group('q')}{' '.join(classes)}{match.group('q')}"
    return attrs[: match.start()] + replacement + attrs[match.end() :]


def _decorate_actionable_rows(html: str) -> str:
    """Give actionable result cells a consistent semantic state across reports."""
    def replace_row(match: re.Match[str]) -> str:
        body = match.group("body")
        cells = list(_TABLE_CELL_RE.finditer(body))
        if not cells:
            return match.group(0)
        selected: tuple[re.Match[str], str] | None = None
        rank = {"good": 1, "warn": 2, "bad": 3}
        current_rank = 0
        for cell in cells:
            value = _plain(cell.group("body")).casefold().strip()
            state = None
            if value in _ACTIONABLE_BAD:
                state = "bad"
            elif value in _ACTIONABLE_WARN:
                state = "warn"
            elif value in _ACTIONABLE_GOOD:
                state = "good"
            if state is not None and rank[state] > current_rank:
                selected = (cell, state)
                current_rank = rank[state]
        if selected is None:
            return match.group(0)
        cell, state = selected
        cell_body = cell.group("body")
        cell_attrs = _merge_class_attr(cell.group("attrs"), f"result-cell {state}")
        if "result-tag" not in cell_body:
            cell_body = f"<span class='result-tag {state}'>{cell_body}</span>"
        replacement = f"<td{cell_attrs}>{cell_body}</td>"
        body = body[: cell.start()] + replacement + body[cell.end() :]
        row_attrs = _strip_result_state(match.group("attrs"))
        row_attrs = _merge_class_attr(row_attrs, f"result-state-{state}")
        return f"<tr{row_attrs}>{body}</tr>"

    return _TABLE_ROW_RE.sub(replace_row, html)


def _translate_readiness_table_headers(html: str) -> str:
    return html.replace(
        "<th>Dimensão</th><th>Score</th><th>Coverage</th><th>Confidence</th><th>Consolidação</th>",
        "<th>Dimensão</th><th>Pontuação</th><th>Cobertura</th><th>Confiança</th><th>Consolidação</th>",
    )

'''
if helper_anchor not in semantics:
    raise RuntimeError("semantic helper anchor not found")
semantics = semantics.replace(helper_anchor, "\n" + helpers + "def _plain(value: str) -> str:\n", 1)

# CV is descriptive. Keep the existing attention threshold, but label it explicitly
# as a RASAi presentation signal rather than a universal statistical standard.
semantics = semantics.replace(
    'return "warn", "Alta variabilidade", False',
    'return "warn", "Variabilidade elevada no teste", False',
    1,
)
write("src/rasai/report_semantics.py", semantics)

# ---------------------------------------------------------------------------
# 4. Report menu: comprehension first, action after evidence/diagnostics.
# ---------------------------------------------------------------------------
contract_path = "src/rasai/report_contract.py"
contract = read(contract_path)
start = contract.index("REPORT_SURFACES: tuple[ReportSurface, ...] = (")
body_start = contract.index("\n", start) + 1
end_marker = "\n)\n\n\nCANONICAL_NAV_ITEMS"
body_end = contract.index(end_marker, body_start)
body = contract[body_start:body_end]
blocks: list[str] = []
pos = 0
while True:
    idx = body.find("    ReportSurface(", pos)
    if idx < 0:
        break
    depth = 0
    i = idx
    in_string = False
    quote = ""
    escaped = False
    while i < len(body):
        ch = body[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                in_string = False
        else:
            if ch in {"'", '"'}:
                in_string = True
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    j = i + 1
                    while j < len(body) and body[j] in ",\r\n":
                        j += 1
                    blocks.append(body[idx:j].rstrip() + "\n")
                    pos = j
                    break
        i += 1
    else:
        raise RuntimeError("unterminated ReportSurface block")

by_id: dict[str, str] = {}
for block in blocks:
    match = re.search(r'id="([^"]+)"', block)
    if not match:
        raise RuntimeError("ReportSurface without id")
    by_id[match.group(1)] = block

order = [
    "index", "readiness", "scoring", "mobile", "desktop",
    "crawling-discovery", "accessibility", "web-performance", "apdex",
    "apdex-experience", "content-suggestions", "remediation", "ai-usage",
    "ai-visibility", "observability", "quality", "references",
]
if set(order) != set(by_id):
    raise RuntimeError(f"report surface set changed: expected {order}, actual {sorted(by_id)}")
new_body = "".join(by_id[item] for item in order).rstrip()
contract = contract[:body_start] + new_body + contract[body_end:]
write(contract_path, contract)

# ---------------------------------------------------------------------------
# 5. Consolidated report: same-snapshot decisions, clearer state, useful rates.
# ---------------------------------------------------------------------------
consolidated_path = "src/rasai/consolidation/reporting.py"
cons = read(consolidated_path)
cons = cons.replace('REPORT_FORMAT_VERSION = "CONS-2"', 'REPORT_FORMAT_VERSION = "CONS-3"', 1)

# Executive SARI must state consolidation state and never mix dimensions from
# different audits when identifying the weakest current dimension.
old = '''        if overall and _number(overall.get("value")) is not None:
            bullets.append(
                f"<li><strong>{escape(_device(device))}:</strong> Readiness Search & AI {_fmt(_number(overall.get('value')))} / 100, "
                f"cobertura {_pct(_number(overall.get('coverage')))} e confiança {escape(_confidence(overall.get('confidence')))}.</li>"
            )
        dimensions = [
            row for row in data.score_history
            if str(row.get("device") or "").upper() == device.upper()
            and str(row.get("dimension") or "") != "OVERALL_READINESS"
            and _number(row.get("value")) is not None
        ]
'''
new = '''        if overall and _number(overall.get("value")) is not None:
            state = _consolidation(overall.get("consolidation_status"))
            score_label = "Readiness Search & AI" if str(overall.get("consolidation_status") or "").upper() == "CONSOLIDATED" else "pontuação parcial de readiness"
            bullets.append(
                f"<li><strong>{escape(_device(device))}:</strong> {escape(score_label)} {_fmt(_number(overall.get('value')))} / 100, "
                f"cobertura {_pct(_number(overall.get('coverage')))}, confiança {escape(_confidence(overall.get('confidence')))} e estado {escape(state)}.</li>"
            )
        latest_audit_id = str(overall.get("audit_id") or "") if overall else ""
        dimensions = [
            row for row in data.score_history
            if overall is not None
            and str(row.get("audit_id") or "") == latest_audit_id
            and str(row.get("device") or "").upper() == device.upper()
            and str(row.get("dimension") or "") != "OVERALL_READINESS"
            and _number(row.get("value")) is not None
        ]
'''
if old not in cons:
    raise RuntimeError("consolidated executive score anchor not found")
cons = cons.replace(old, new, 1)

old_apdex_exec = '''    for apdex in data.apdex:
        if apdex.small_groups and not apdex.final_groups:
            bullets.append(
                f"<li><strong>Apdex {escape(_device(apdex.device))}:</strong> {_fmt(apdex.weighted_apdex, 3)} com {apdex.valid_samples} amostras válidas, "
                "mas somente grupos classificados como amostra pequena; resultado diagnóstico, não conclusão robusta.</li>"
            )
'''
new_apdex_exec = '''    for apdex in data.apdex:
        if apdex.small_groups and not apdex.final_groups:
            bullets.append(
                f"<li><strong>Apdex {escape(_device(apdex.device))}:</strong> {_fmt(apdex.weighted_apdex, 3)} com {apdex.valid_samples} amostras válidas, "
                "mas somente grupos classificados como amostra pequena; resultado diagnóstico, não conclusão robusta.</li>"
            )
        elif apdex.final_groups:
            bullets.append(
                f"<li><strong>Apdex {escape(_device(apdex.device))}:</strong> {_fmt(apdex.weighted_apdex, 3)} com {apdex.valid_samples} amostras válidas em grupo(s) final(is); "
                "a leitura permanece condicionada ao mesmo perfil sintético e ao mesmo limiar T.</li>"
            )
'''
if old_apdex_exec not in cons:
    raise RuntimeError("consolidated apdex executive anchor not found")
cons = cons.replace(old_apdex_exec, new_apdex_exec, 1)

# Findings evolution should be normalized by audited URL count; raw counts remain
# visible as scope telemetry but are not used as a behavioral trend by themselves.
cons = cons.replace(
    '            "affected": len({str(row.get("page_id")) for row in rows if row.get("page_id")}),\n',
    '            "affected": len({str(row.get("page_id")) for row in rows if row.get("page_id")}),\n            "per_url": (len(rows) / int(audit.get("url_count") or 0)) if int(audit.get("url_count") or 0) > 0 else None,\n',
    1,
)
cons = cons.replace(
    '        title="Evolução do volume de ocorrências",\n        rows=trend,\n        primary_field="value",\n        primary_label="Ocorrências",\n',
    '        title="Evolução de ocorrências por URL auditada",\n        rows=trend,\n        primary_field="per_url",\n        primary_label="Ocorrências por URL",\n',
    1,
)
cons = cons.replace(
    'O volume bruto de ocorrências deve ser interpretado junto com a quantidade de URLs auditadas; escopos maiores podem produzir mais ocorrências sem representar piora proporcional.',
    'A série usa ocorrências por URL auditada para reduzir o viés de mudança de escopo. O volume bruto continua disponível como contexto e não deve ser comparado isoladamente entre auditorias com universos diferentes.',
    1,
)
cons = cons.replace("Confiança da medição GEO", "Confiança da readiness", 1)

# Remove release/legacy framing from consolidated methodology. Older scoring
# values, if present in development datasets, remain traceable but incompatible.
method_start = cons.index('    score002 = "SCORE-GEO-002" in methods')
method_end = cons.index('    return f"""\n    <section id=\'method\'>', method_start)
method_logic = '''    current_method = "SCORE-GEO-004" in methods
    prior_development_methods = [method for method in methods if method not in {"SCORE-GEO-004", "UNKNOWN"}]
    if current_method:
        score_explanation = """
        <h3>Como o SCORE-GEO-004 é interpretado</h3>
        <ol>
          <li>Regras aplicáveis produzem resultados persistidos e fatores versionados; ausência de evidência não é convertida silenciosamente em falha.</li>
          <li>A pontuação de cada dimensão usa <code>soma(peso × fator) / soma dos pesos efetivamente avaliados × 100</code>.</li>
          <li>Cobertura mede a fração aplicável efetivamente avaliada; Confiança qualifica a força/completude da medição.</li>
          <li>Dimensão legitimamente não aplicável sai do denominador. Dimensão aplicável sem medição suficiente pode bloquear a consolidação do Overall.</li>
          <li>O Overall usa igual peso entre dimensões aplicáveis com medição suficiente e não incorpora Lighthouse, Core Web Vitals, Acessibilidade ou Apdex.</li>
        </ol>
        """
        if prior_development_methods:
            score_explanation += (
                "<p class='notice warning'><strong>Dados de desenvolvimento não comparáveis:</strong> o universo selecionado também contém "
                + escape(", ".join(prior_development_methods))
                + ". Esses contratos anteriores de desenvolvimento são preservados por rastreabilidade e não são tratados como série equivalente ao SCORE-GEO-004.</p>"
            )
    else:
        score_explanation = (
            f"<p>Versão(ões) persistida(s) encontrada(s): <strong>{escape(method_value)}</strong>. "
            "O consolidado preserva esses dados de desenvolvimento sem recalcular e sem presumir equivalência com o contrato vigente SCORE-GEO-004.</p>"
        )
'''
cons = cons[:method_start] + method_logic + cons[method_end:]

# Make the consolidated reading order match decision flow.
cons = cons.replace(
    "<nav aria-label='Navegação do relatório'><a href='#summary'>Resumo</a><a href='#evolution'>Evolução</a><a href='#scores'>Readiness Search & AI</a><a href='#performance'>Desempenho</a><a href='#apdex'>Apdex</a><a href='#findings'>Ocorrências</a><a href='#reliability'>Confiabilidade</a><a href='#sources'>Auditorias</a><a href='#method'>Metodologia</a></nav>",
    "<nav aria-label='Navegação do relatório'><a href='#summary'>Resumo</a><a href='#scores'>Readiness Search & AI</a><a href='#evolution'>Evolução</a><a href='#performance'>Desempenho</a><a href='#apdex'>Apdex</a><a href='#findings'>Ocorrências</a><a href='#reliability'>Confiabilidade</a><a href='#sources'>Auditorias</a><a href='#method'>Metodologia</a></nav>",
    1,
)
cons = cons.replace(
    "{_render_executive(data)}\n{_render_score_trends(data)}\n{_render_scores(data)}\n{_render_dimension_matrix(data)}",
    "{_render_executive(data)}\n{_render_scores(data)}\n{_render_score_trends(data)}\n{_render_dimension_matrix(data)}",
    1,
)
# Inline CSS for the same result-state vocabulary used by the per-audit reports.
css_token = ".heat.na{{color:var(--muted);background:#f7f8fa}}"
css_replacement = css_token + ".result-tag{{display:inline-flex;align-items:center;padding:2px 7px;border-radius:999px;font-size:.72rem;font-weight:700}}.result-tag.good{{background:var(--green-soft);color:#3f7452}}.result-tag.warn{{background:var(--amber-soft);color:#855f2c}}.result-tag.bad{{background:var(--red-soft);color:#98494c}}tr.result-state-warn{{background:var(--amber-soft)}}tr.result-state-bad{{background:var(--red-soft)}}tr.result-state-good>td:first-child{{box-shadow:inset 3px 0 0 var(--green)}}tr.result-state-warn>td:first-child{{box-shadow:inset 3px 0 0 var(--amber)}}tr.result-state-bad>td:first-child{{box-shadow:inset 3px 0 0 var(--red)}}"
if css_token not in cons:
    raise RuntimeError("consolidated CSS anchor not found")
cons = cons.replace(css_token, css_replacement, 1)

# Apply central semantic/humanization pass to the standalone consolidated HTML.
cons = cons.replace(
    "from .models import ConsolidatedData, GenerationResult, NumericSummary, RefreshResult\n",
    "from .models import ConsolidatedData, GenerationResult, NumericSummary, RefreshResult\nfrom rasai.report_presentation import humanize_report_html\nfrom rasai.report_semantics import enhance_report_html\n",
    1,
)
cons = cons.replace(
    '    report_path.write_text(_render_html(data, generated_at, fingerprint), encoding="utf-8")\n',
    '    rendered = _render_html(data, generated_at, fingerprint)\n    rendered = enhance_report_html(rendered, page_name="consolidated.html", report_dir=output)\n    rendered = humanize_report_html(rendered, page_name="consolidated.html")\n    report_path.write_text(rendered, encoding="utf-8")\n',
    1,
)
write(consolidated_path, cons)

# ---------------------------------------------------------------------------
# 6. Remove release-history framing from current development documentation/code.
# ---------------------------------------------------------------------------
release_replacements = {
    "`SCORE-GEO-003` permanece histórico": "`SCORE-GEO-003` é uma proposta anterior de desenvolvimento preservada apenas para rastreabilidade técnica",
    "SCORE-GEO-003 permanece histórico": "SCORE-GEO-003 é uma proposta anterior de desenvolvimento preservada apenas para rastreabilidade técnica",
    "SCORE-GEO-002 permanece histórico": "SCORE-GEO-002 é uma proposta anterior de desenvolvimento preservada apenas para rastreabilidade técnica",
    "metodologias históricas": "propostas metodológicas anteriores de desenvolvimento",
    "método histórico 003": "método anterior de desenvolvimento 003",
    "contratos históricos": "contratos anteriores de desenvolvimento",
    "versões históricas": "versões anteriores de desenvolvimento",
    "compatibilidade histórica": "compatibilidade entre dados de desenvolvimento",
    "links antigos": "links produzidos durante o desenvolvimento",
    "adoção inicial": "fase atual de desenvolvimento",
    "## Methodological limit": "## Limite metodológico",
}
for md in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
    text = md.read_text(encoding="utf-8")
    original = text
    for old, new in release_replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"\*\*Status:\*\*", "**Estado no baseline de desenvolvimento:**", text)
    text = text.replace("LEGACY", "REFERÊNCIA DE DESENVOLVIMENTO ANTERIOR")
    text = text.replace("DEPRECATED", "FORA DO BASELINE DE EXECUÇÃO ATUAL")
    text = text.replace("OBSOLETO", "FORA DO BASELINE DE EXECUÇÃO ATUAL")
    if text != original:
        md.write_text(text, encoding="utf-8", newline="\n")

# User-facing defensive wording in the report registry follows the same policy.
registry = read("src/rasai/report_registry.py")
registry = registry.replace("without rewriting history", "without presenting development iterations as public releases")
registry = registry.replace("permanece histórico", "é preservado como referência de desenvolvimento anterior")
registry = registry.replace("permanecem históricos", "são preservados como referências de desenvolvimento anteriores")
write("src/rasai/report_registry.py", registry)

# ---------------------------------------------------------------------------
# 7. Documentation contract and detailed cross-document updates.
# ---------------------------------------------------------------------------
docs_index = r'''# Documentação do RASAi

## Estado do produto

O RASAi está em **desenvolvimento e validação**. Nenhuma combinação anterior de `SARI`, `SCORE-GEO`, relatório ou contrato interno deve ser descrita como uma versão pública legada, obsoleta ou anteriormente lançada. Quando dados de testes anteriores precisam ser preservados para reprodutibilidade, eles são tratados como **referências de desenvolvimento anteriores** e permanecem identificados pela versão persistida que efetivamente os produziu.

O baseline funcional vigente usa:

- índice público `SARI-001`;
- método de scoring `SCORE-GEO-004` para novas auditorias;
- `report/readiness.html` como superfície canônica do índice;
- `report/scoring.html` como superfície canônica da metodologia;
- `report/score-geo-004.html` somente como alias interno de compatibilidade durante o desenvolvimento;
- HTML em português do Brasil, mantendo em inglês apenas nomes técnicos consolidados, identificadores, APIs, formatos e termos cujo uso técnico melhora a precisão.

## Ordem de leitura recomendada

1. [`REPORT_GUIDE.md`](REPORT_GUIDE.md) - contrato dos relatórios e como interpretar os indicadores.
2. [`SARI_READINESS_INDEX.md`](SARI_READINESS_INDEX.md) - identidade pública e limites do SARI.
3. [`SCORING_GUIDE.md`](SCORING_GUIDE.md) e [`SCORE_GEO_004.md`](SCORE_GEO_004.md) - fórmula, Coverage/Cobertura, Confidence/Confiança e gates.
4. [`RULES_GUIDE.md`](RULES_GUIDE.md) - regras BR-GEO, evidências e aplicabilidade.
5. [`SYNTHETIC_APDEX.md`](SYNTHETIC_APDEX.md) e [`SYNTHETIC_USER_EXPERIENCE_APDEX.md`](SYNTHETIC_USER_EXPERIENCE_APDEX.md) - experiência sintética independente do SARI.
6. [`ACCESSIBILITY_PERFORMANCE_DOMAINS.md`](ACCESSIBILITY_PERFORMANCE_DOMAINS.md) - fronteiras entre performance, acessibilidade e readiness.
7. [`CONSOLIDATED_REPORTING.md`](CONSOLIDATED_REPORTING.md) e [`CONSOLIDATED_REPORTING_VALIDATION.md`](CONSOLIDATED_REPORTING_VALIDATION.md) - séries, comparabilidade e relatório histórico.
8. [`AI_GUIDE.md`](AI_GUIDE.md), [`AI_PROVIDER_EXTENSIONS.md`](AI_PROVIDER_EXTENSIONS.md) e [`CONTENT_ANALYSIS_CONTEXT.md`](CONTENT_ANALYSIS_CONTEXT.md) - uso de IA, contexto e limites.
9. [`TECHNICAL_GUIDE.md`](TECHNICAL_GUIDE.md), [`CONFIGURATION.md`](CONFIGURATION.md), [`ENVIRONMENT_VARIABLES.md`](ENVIRONMENT_VARIABLES.md) e [`CLI_REFERENCE.md`](CLI_REFERENCE.md) - operação e implantação.
10. [`specification/00_SPEC_INDEX.md`](specification/00_SPEC_INDEX.md) - especificação técnica detalhada.

## Convenção de linguagem de relatório

Enums e estados persistidos continuam em sua forma canônica no banco e em interfaces técnicas. Na interface HTML, valores de máquina conhecidos são apresentados com rótulos amigáveis. Exemplos:

| Valor persistido | Exibição no HTML |
|---|---|
| `SINGLE_PROVIDER` | Provedor único |
| `PASS` | Aprovado |
| `WARNING` | Alerta |
| `NOT_CONSOLIDATED` | Não consolidado |
| `NOT_APPLICABLE` | Não aplicável |
| `BOUNDED_AI_RESOURCE_ASSESSMENT` | Avaliação por IA com escopo limitado |

Blocos `code`/`pre`, nomes de variáveis, IDs de regras, versões e contratos técnicos não são traduzidos, porque fazem parte da rastreabilidade.

## Semântica visual

Relatórios usam um contrato global de estados:

- **verde**: resultado conclusivo e aprovado/consolidado;
- **amarelo/laranja**: alerta, resultado parcial, degradação ou condição que exige observação;
- **vermelho**: reprovação, falha ou erro que exige ação;
- **azul/neutro**: indisponibilidade, não aplicabilidade ou informação que não deve ser interpretada como falha do website.

A cor é apoio de leitura. O valor persistido, a evidência, o critério e a explicação textual prevalecem.

## Referências públicas primárias

As referências abaixo sustentam domínios específicos; nenhuma delas homologa o índice proprietário SARI/SCORE-GEO:

- Google Search Central: https://developers.google.com/search/docs
- Google Search - dados estruturados: https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data
- RFC 9309 - Robots Exclusion Protocol: https://www.rfc-editor.org/rfc/rfc9309
- Sitemap protocol: https://www.sitemaps.org/protocol.html
- Schema.org: https://schema.org/
- Chrome Lighthouse: https://developer.chrome.com/docs/lighthouse/
- Web Vitals: https://web.dev/vitals/
- W3C WCAG 2.2: https://www.w3.org/TR/WCAG22/
- Apdex: https://www.apdex.org/

Consulte também `report/references.html` de cada auditoria: ele deve materializar a proveniência aplicável à execução, enquanto estes documentos descrevem o contrato do produto.
'''
write("docs/README.md", docs_index)

append_once(
    "README.md",
    "<!-- rasai-doc-index-20260908 -->",
    '''<!-- rasai-doc-index-20260908 -->
## Contrato da documentação

A documentação está organizada em [`docs/README.md`](docs/README.md). O projeto está em desenvolvimento e validação; referências a métodos anteriores significam propostas/baselines de desenvolvimento preservados para rastreabilidade, não releases públicas anteriores.''',
)

append_once(
    "docs/REPORT_GUIDE.md",
    "<!-- rasai-global-result-semantics-20260908 -->",
    r'''<!-- rasai-global-result-semantics-20260908 -->
## Semântica visual e linguagem pública

A normalização final dos relatórios aplica o mesmo contrato a todas as superfícies HTML. Estados conclusivos que aparecem em tabelas/listas recebem uma tag na célula e uma indicação discreta na linha: aprovado/consolidado em verde, alerta/parcial em amarelo, falha/erro em vermelho. Estados neutros não são promovidos artificialmente a erro.

Enums persistidos não são alterados no banco. A camada de apresentação traduz valores de máquina conhecidos para PT-BR e preserva identificadores dentro de `code`/`pre`. Isso evita expor ao usuário termos como `SINGLE_PROVIDER` ou `NOT_DETERMINABLE` sem perder rastreabilidade técnica.

A ordem canônica do menu segue a sequência de leitura: visão geral → SARI → metodologia → evidências por dispositivo → crawling/acessibilidade/performance/Apdex → conteúdo/remediação → telemetria e outcomes de IA → quality → referências.

Correlação: veja [`README.md`](README.md), [`SCORING_GUIDE.md`](SCORING_GUIDE.md), [`CONSOLIDATED_REPORTING.md`](CONSOLIDATED_REPORTING.md) e [`docs/README.md`](README.md).''',
)

append_once(
    "docs/SYNTHETIC_APDEX.md",
    "<!-- rasai-apdex-cv-20260908 -->",
    r'''<!-- rasai-apdex-cv-20260908 -->
## Coeficiente de variação e estabilidade das amostras

O relatório apresenta o **coeficiente de variação (CV)** das durações válidas:

```text
CV (%) = desvio padrão das durações / média das durações × 100
```

O CV mede a dispersão relativa das navegações sintéticas. Em um mesmo perfil, origem e alvo, valor menor indica tempos mais consistentes; valor maior indica maior oscilação. Ele pode refletir, em conjunto, máquina executora, rede local, rota, DNS/TCP/TLS, CDN, servidor, terceiros e comportamento da própria aplicação. O CV **não identifica sozinho a causa** e um CV baixo não significa página rápida: uma página pode ser lenta e estável.

A UI pode marcar CV elevado como **sinal de atenção do RASAi**. Esse destaque é heurística de apresentação, não limiar universal do Apdex nem norma estatística externa. O CV não entra na fórmula do Apdex. Para diagnóstico, deve ser lido junto com média/mediana, percentis/cauda, erros, perfil, `T` e quantidade de amostras.

Uma futura execução distribuída por regiões não deve misturar indiscriminadamente todas as origens em um único CV: estabilidade **intrarregional** e dispersão **entre regiões** respondem perguntas diferentes e devem permanecer separadas.''',
)

append_once(
    "docs/CONSOLIDATED_REPORTING.md",
    "<!-- rasai-consolidated-cons3-20260908 -->",
    r'''<!-- rasai-consolidated-cons3-20260908 -->
## Leitura comportamental do formato CONS-3

O consolidado prioriza dados úteis para decisão e evita criar tendência artificial:

- o resumo de SARI informa pontuação, Cobertura, Confiança **e estado de consolidação**; pontuação parcial não é apresentada como SARI consolidado;
- a dimensão de menor pontuação no estado atual é obtida do **mesmo AUD** do Overall atual, evitando misturar snapshots de datas diferentes;
- séries de score continuam restritas à mesma `scoring_version` e ao mesmo universo de URLs comparável;
- evolução de findings usa **ocorrências por URL auditada** para reduzir o viés de mudanças de escopo; volume bruto permanece apenas como contexto;
- Apdex só é agregado entre mesmo perfil e mesmo `T`, ponderado por amostras válidas e com indicação explícita de grupos pequenos/finais;
- Lighthouse/lab e Core Web Vitals/field permanecem separados;
- estados acionáveis usam o mesmo padrão visual dos relatórios individuais;
- métodos anteriores encontrados em bases de teste são preservados como dados de desenvolvimento não comparáveis ao `SCORE-GEO-004`, sem narrativa de release legado.

O formato não recalcula auditorias e não transforma ausência de dado em zero. Veja também [`CONSOLIDATED_REPORTING_VALIDATION.md`](CONSOLIDATED_REPORTING_VALIDATION.md), [`SCORING_GUIDE.md`](SCORING_GUIDE.md), [`SYNTHETIC_APDEX.md`](SYNTHETIC_APDEX.md) e [`REPORT_GUIDE.md`](REPORT_GUIDE.md).''',
)

append_once(
    "docs/SCORING_GUIDE.md",
    "<!-- rasai-readiness-canonical-fix-20260908 -->",
    r'''<!-- rasai-readiness-canonical-fix-20260908 -->
## Projeção canônica do readiness

`readiness.html` é a superfície que centraliza SARI, pontuação por dimensão, Cobertura, Confiança e Consolidação. `mobile.html` e `desktop.html` preservam evidências/findings por dispositivo e não devem duplicar a função de página canônica do índice.

A projeção deve consultar o schema efetivamente persistido de cada módulo. Em particular, `m24_runs` possui uma linha por `audit_id` e usa `updated_at`; a geração do SARI não depende de uma coluna `completed_at` inexistente. Uma falha de projeção não pode ser confundida com falha de scoring: o score já persistido continua sendo a fonte de verdade, mas a auditoria deve sinalizar a falha operacional até que o HTML seja materializado corretamente.''',
)

# ---------------------------------------------------------------------------
# 8. Regression tests for the exact gaps found in the supplied audit.
# ---------------------------------------------------------------------------
test_file = r'''from __future__ import annotations

from pathlib import Path

from rasai.report_contract import CANONICAL_NAV_ITEMS
from rasai.report_presentation import humanize_report_html
from rasai.report_semantics import enhance_report_html

ROOT = Path(__file__).resolve().parents[1]


def test_m24_readiness_projection_uses_live_schema_contract() -> None:
    source = (ROOT / "src/rasai/rasai_readiness_reporting.py").read_text(encoding="utf-8")
    assert "SELECT * FROM m24_runs WHERE audit_id=? LIMIT 1" in source
    assert "m24_runs WHERE audit_id=? ORDER BY completed_at" not in source


def test_public_html_humanizes_provider_strategy_and_inline_machine_state() -> None:
    html = "<div><span>SINGLE_PROVIDER</span><p>Sitemap em estado ABSENT.</p><code>SINGLE_PROVIDER ABSENT</code></div>"
    rendered = humanize_report_html(html)
    assert "Provedor único" in rendered
    assert "Sitemap em estado Ausente" in rendered
    assert "<code>SINGLE_PROVIDER ABSENT</code>" in rendered


def test_actionable_table_rows_use_global_result_state_contract() -> None:
    html = "<table><tbody><tr><td>BR-GEO-017</td><td>Alerta</td></tr><tr><td>BR-GEO-005</td><td>Aprovado</td></tr><tr><td>x</td><td>Erro</td></tr></tbody></table>"
    rendered = enhance_report_html(html, page_name="scoring.html", report_dir=ROOT)
    assert "result-state-warn" in rendered
    assert "result-state-good" in rendered
    assert "result-state-bad" in rendered
    assert "result-tag warn" in rendered


def test_canonical_report_order_follows_reading_flow() -> None:
    filenames = [filename for _label, filename in CANONICAL_NAV_ITEMS]
    expected = [
        "index.html", "readiness.html", "scoring.html", "mobile.html", "desktop.html",
        "crawling-discovery.html", "accessibility.html", "web-performance.html", "apdex.html",
        "apdex-experience.html", "content-suggestions.html", "remediation.html", "ai-usage.html",
        "ai-visibility.html", "observability.html", "quality.html", "references.html",
    ]
    assert filenames == expected


def test_documentation_declares_development_not_prior_public_releases() -> None:
    docs_index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    assert "desenvolvimento e validação" in docs_index
    assert "não corresponde" not in docs_index.lower() or "release" not in docs_index.lower()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/README.md" in readme


def test_consolidated_report_uses_normalized_findings_series_and_cons3() -> None:
    source = (ROOT / "src/rasai/consolidation/reporting.py").read_text(encoding="utf-8")
    assert 'REPORT_FORMAT_VERSION = "CONS-3"' in source
    assert 'primary_field="per_url"' in source
    assert "latest_audit_id" in source
    assert "Confiança da readiness" in source
'''
write("tests/test_report_polish_20260908.py", test_file)

# Strengthen the existing language contract against the specific raw enum that
# escaped in the supplied report.
append_once(
    "tests/test_user_facing_language_contract.py",
    "test_single_provider_strategy_is_not_exposed_as_raw_enum",
    '''def test_single_provider_strategy_is_not_exposed_as_raw_enum() -> None:
    from rasai.report_presentation import humanize_report_html
    rendered = humanize_report_html("<div><span>SINGLE_PROVIDER</span></div>")
    assert "Provedor único" in rendered
    assert ">SINGLE_PROVIDER<" not in rendered
''',
)

# ---------------------------------------------------------------------------
# 9. Self-checks before CI takes over.
# ---------------------------------------------------------------------------
assert "ORDER BY completed_at" not in read("src/rasai/rasai_readiness_reporting.py").split("m24_runs", 1)[1].split("rule_executions", 1)[0]
assert "SINGLE_PROVIDER\": \"Provedor único" in read("src/rasai/report_presentation.py")
assert "CONS-3" in read("src/rasai/consolidation/reporting.py")
assert (ROOT / "docs/README.md").is_file()

print("RASAi report/documentation patch applied successfully")
