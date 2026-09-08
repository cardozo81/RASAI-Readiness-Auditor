from __future__ import annotations

from pathlib import Path
import re

ROOT = Path('.')
REPORT = ROOT / 'src/rasai/rasai_readiness_reporting.py'
DECISIONS = ROOT / 'docs/specification/10_DECISIONS.md'
REPORT_GUIDE = ROOT / 'docs/REPORT_GUIDE.md'
TEST = ROOT / 'tests/test_sari_input_traceability_20260908.py'


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(f'expected target not found: {old[:160]!r}')
    return text.replace(old, new, 1)


text = REPORT.read_text(encoding='utf-8')

text = replace_once(
    text,
    '''        discovery_executions = _many(
            connection,
            "SELECT * FROM rule_executions WHERE audit_id=? AND rule_id IN ('BR-GEO-003','BR-GEO-017','BR-GEO-018') ORDER BY rule_id,rule_execution_id",
            (audit_id,),
        )
''',
    '''        discovery_executions = _many(
            connection,
            "SELECT * FROM rule_executions WHERE audit_id=? AND rule_id IN ('BR-GEO-003','BR-GEO-017','BR-GEO-018','BR-GEO-055','BR-GEO-056') ORDER BY rule_id,rule_execution_id",
            (audit_id,),
        )
        m24_run = _one(
            connection,
            "SELECT * FROM m24_runs WHERE audit_id=? ORDER BY completed_at DESC LIMIT 1",
            (audit_id,),
        )
''',
)

text = replace_once(
    text,
    '''            "ai_attempts": ai_attempts,
            "discovery_executions": discovery_executions,
        }
''',
    '''            "ai_attempts": ai_attempts,
            "discovery_executions": discovery_executions,
            "m24_run": m24_run,
        }
''',
)

text = replace_once(
    text,
    '''{_discovery_scoring_block(data)}
{_content_context_block(workspace, audit_id)}
''',
    '''{_discovery_scoring_block(data)}
{_structured_data_scoring_block(data)}
{_content_context_block(workspace, audit_id)}
''',
)

pattern = re.compile(r"def _discovery_scoring_block\(data: dict\[str, Any\]\) -> str:\n.*?\n\ndef _provenance_block", re.DOTALL)
if not pattern.search(text):
    raise RuntimeError('discovery scoring block not found')

replacement = r'''def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _state_pt(value: Any) -> str:
    raw = str(value or "UNAVAILABLE").upper()
    return {
        "OBTAINED": "OBTIDO",
        "ABSENT": "AUSENTE",
        "INVALID": "INVÁLIDO",
        "HTTP_ERROR": "ERRO HTTP",
        "NETWORK_ERROR": "ERRO DE REDE",
        "UNAVAILABLE": "INDISPONÍVEL",
        "NOT_REQUESTED": "NÃO SOLICITADO",
        "SKIPPED_SOURCE_BLOCKER": "NÃO CONSULTADO - BLOQUEIO DE FONTE",
    }.get(raw, raw)


def _rule_results(executions: list[sqlite3.Row], rule_id: str) -> str:
    values = sorted({str(_row_get(row, "result", "NÃO EXECUTADO")) for row in executions if str(_row_get(row, "rule_id", "")) == rule_id})
    return ", ".join(values) if values else "NÃO EXECUTADO"


def _group_trace(contributions: list[sqlite3.Row], group: str) -> str:
    rows = [row for row in contributions if str(_row_get(row, "scoring_group", "") or "") == group]
    if not rows:
        return "<p class='intro'>Nenhuma contribuição representativa persistida para este grupo.</p>"
    items: list[str] = []
    for row in sorted(rows, key=lambda item: (str(_row_get(item, "device", "")), str(_row_get(item, "rule_id", "")))):
        factor_raw = _row_get(row, "result_factor")
        effective_raw = _row_get(row, "effective_contribution")
        weight = float(_row_get(row, "weight", 0.0) or 0.0)
        factor = "-" if factor_raw is None else f"{float(factor_raw):.2f}"
        effective = "-" if effective_raw is None else f"{float(effective_raw):.3f}"
        items.append(
            "<li>"
            f"<strong>{escape(str(_row_get(row, 'device', '-')).title())}</strong>: "
            f"representante <code>{escape(str(_row_get(row, 'rule_id', '-')))}</code> = {escape(str(_row_get(row, 'result', '-')))}; "
            f"peso {weight:g} × fator {factor} = contribuição {effective}."
            "</li>"
        )
    return "<ul class='compact-list'>" + "".join(items) + "</ul>"


def _sitemap_state(executions: list[sqlite3.Row]) -> str:
    states: list[str] = []
    for row in executions:
        if str(_row_get(row, "rule_id", "")) != "BR-GEO-003":
            continue
        observed = _json_object(_row_get(row, "observed_value", ""))
        for item in observed.get("sitemaps", []):
            if isinstance(item, dict) and item.get("state"):
                states.append(_state_pt(item.get("state")))
    return ", ".join(dict.fromkeys(states)) if states else "NÃO OBSERVADO"


def _robots_state(executions: list[sqlite3.Row]) -> str:
    for row in executions:
        if str(_row_get(row, "rule_id", "")) == "BR-GEO-017":
            observed = _json_object(_row_get(row, "observed_value", ""))
            return _state_pt(observed.get("state"))
    return "NÃO OBSERVADO"


def _crawler_state(executions: list[sqlite3.Row], robots_state: str) -> str:
    rows = [row for row in executions if str(_row_get(row, "rule_id", "")) == "BR-GEO-018"]
    if not rows:
        return "NÃO OBSERVADO"
    unresolved = 0
    blocked = 0
    for row in rows:
        observed = _json_object(_row_get(row, "observed_value", ""))
        unresolved += len(observed.get("unresolved", []) if isinstance(observed.get("unresolved"), list) else [])
        blocked += len(observed.get("blocked_search_crawlers", []) if isinstance(observed.get("blocked_search_crawlers"), list) else [])
    if unresolved:
        return f"NÃO RESOLVIDO ({unresolved} combinação(ões))"
    if blocked:
        return f"BLOQUEIO SEARCH DETECTADO ({blocked})"
    if robots_state == "AUSENTE":
        return "RESOLVIDO POR DEFAULT ALLOW (robots.txt ausente)"
    return "RESOLVIDO - SEM BLOQUEIO SEARCH"


def _discovery_scoring_block(data: dict[str, Any]) -> str:
    executions = data.get("discovery_executions", [])
    contributions = data.get("contributions", [])
    sitemap_state = _sitemap_state(executions)
    robots_state = _robots_state(executions)
    crawler_state = _crawler_state(executions, robots_state)
    llms_state = _state_pt(_row_get(data.get("m24_run"), "llms_state", "UNAVAILABLE"))
    sitemap_result = _rule_results(executions, "BR-GEO-003")
    robots_result = _rule_results(executions, "BR-GEO-017")
    crawler_result = _rule_results(executions, "BR-GEO-018")
    ai_sitemap = _rule_results(executions, "BR-GEO-055")
    ai_robots = _rule_results(executions, "BR-GEO-056")
    return (
        "<section class='panel' id='discovery-scoring-inputs'><div class='kicker'>SARI - inputs técnicos de descoberta</div>"
        "<h2>O que foi realmente encontrado e como entrou no SARI</h2>"
        "<p class='intro'>O estado observado é mostrado separadamente do resultado da regra. <strong>AUSENTE não significa encontrado</strong>: sitemap e robots ausentes recebem WARNING com fatores reduzidos. Acesso de crawler pode ser resolvido como default allow quando robots.txt não existe; BR-GEO-017/018/056 compartilham o grupo ROBOTS, portanto o resultado mais restritivo representa o grupo sem bônus duplicado.</p>"
        "<div class='grid'>"
        "<article class='ref-card'><h3>Sitemap</h3>"
        f"<p><strong>Estado observado:</strong> {escape(sitemap_state)}</p>"
        f"<p><strong>Regra base:</strong> <code>BR-GEO-003</code> = {escape(sitemap_result)}</p>"
        f"<p><strong>IA técnica bounded:</strong> <code>BR-GEO-055</code> = {escape(ai_sitemap)}</p>"
        "<p><strong>Grupo:</strong> <code>SITEMAP</code> · peso máximo versionado 0,25.</p>"
        + _group_trace(contributions, "SITEMAP")
        + "</article>"
        "<article class='ref-card'><h3>robots.txt e acesso de crawlers</h3>"
        f"<p><strong>robots.txt observado:</strong> {escape(robots_state)}</p>"
        f"<p><strong>BR-GEO-017:</strong> {escape(robots_result)}</p>"
        f"<p><strong>Acesso efetivo:</strong> {escape(crawler_state)} · <code>BR-GEO-018</code> = {escape(crawler_result)}</p>"
        f"<p><strong>IA técnica bounded:</strong> <code>BR-GEO-056</code> = {escape(ai_robots)}</p>"
        "<p><strong>Grupo:</strong> <code>ROBOTS</code> · peso máximo versionado 0,60.</p>"
        + _group_trace(contributions, "ROBOTS")
        + "</article></div>"
        "<div class='notice'><strong>llms.txt:</strong> estado observado nesta camada: "
        + escape(llms_state)
        + ". O arquivo é tratado como proposta comunitária experimental e pode enriquecer o diagnóstico de descoberta, mas <strong>peso SARI = 0</strong>. Presença, ausência ou erro de llms.txt não aumenta nem reduz o SCORE-GEO-004.</div>"
        "<p><a href='crawling-discovery.html'>Abrir diagnóstico aprofundado de rastreamento e descoberta →</a></p></section>"
    )


def _structured_data_state(executions: list[sqlite3.Row]) -> tuple[str, int, int, tuple[str, ...]]:
    rows = [row for row in executions if str(_row_get(row, "rule_id", "")) == "BR-GEO-034"]
    if not rows:
        return "NÃO OBSERVADO", 0, 0, ()
    present = 0
    blocks = 0
    invalid = 0
    types: list[str] = []
    for row in rows:
        observed = _json_object(_row_get(row, "observed_value", ""))
        if bool(observed.get("present")):
            present += 1
        blocks += int(observed.get("blocks") or 0)
        invalid += int(observed.get("invalid_blocks") or 0)
        for item in observed.get("types", []) if isinstance(observed.get("types"), list) else []:
            if isinstance(item, str):
                types.append(item)
    if invalid:
        state = "PRESENTE COM BLOCO(S) INVÁLIDO(S)"
    elif present:
        state = "PRESENTE E SINTATICAMENTE INTERPRETÁVEL"
    else:
        state = "AUSENTE NO HTML ANALISADO"
    return state, blocks, invalid, tuple(dict.fromkeys(types))


def _structured_score_summary(scores: list[sqlite3.Row]) -> str:
    rows = [row for row in scores if str(_row_get(row, "dimension", "")) == "STRUCTURED_DATA"]
    if not rows:
        return "Não persistido"
    parts: list[str] = []
    for row in rows:
        device = str(_row_get(row, "device", "-")).title()
        value = _row_get(row, "value")
        rendered = "N/A" if value is None else f"{float(value):.1f}/100"
        parts.append(f"{device}: {rendered}")
    return " · ".join(parts)


def _structured_data_scoring_block(data: dict[str, Any]) -> str:
    executions = data.get("rule_executions", [])
    contributions = data.get("contributions", [])
    state, blocks, invalid, types = _structured_data_state(executions)
    type_text = ", ".join(types) if types else "nenhum @type observado"
    rule_results = {rule_id: _rule_results(executions, rule_id) for rule_id in ("BR-GEO-034", "BR-GEO-035", "BR-GEO-036", "BR-GEO-037")}
    absence_note = (
        "Na ausência de JSON-LD, BR-GEO-034 permanece aplicável como WARNING com fator 0,80; BR-GEO-035..037 ficam NOT_APPLICABLE. Assim a ausência é uma lacuna leve e rastreável, não zero e não N/A para toda a dimensão."
        if state == "AUSENTE NO HTML ANALISADO"
        else "Quando JSON-LD existe, sintaxe/tipos e consistência com conteúdo/entidades são avaliados pelos grupos versionados do Structured Data."
    )
    return (
        "<section class='panel' id='structured-data-scoring-inputs'><div class='kicker'>SARI - dados estruturados</div>"
        "<h2>JSON-LD no cálculo do SCORE-GEO-004</h2>"
        "<p class='intro'>O RASAi procura blocos <code>script[type=&quot;application/ld+json&quot;]</code> no HTML preservado. A tabela de dimensões mostra o score agregado; este bloco expõe a origem da contribuição para que seja possível verificar se JSON-LD entrou ou não na aritmética.</p>"
        f"<div class='metric-grid'>{_metric('Estado JSON-LD', state)}{_metric('Blocos observados', blocks)}{_metric('Blocos inválidos', invalid)}{_metric('Tipos', type_text)}{_metric('Structured Data', _structured_score_summary(data.get('scores', [])))}</div>"
        "<div class='grid'>"
        "<article class='ref-card'><h3>Presença, sintaxe e tipos</h3>"
        f"<p><code>BR-GEO-034</code> = {escape(rule_results['BR-GEO-034'])} · <code>BR-GEO-035</code> = {escape(rule_results['BR-GEO-035'])}</p>"
        "<p><strong>Grupo:</strong> <code>STRUCTURED_DATA_SYNTAX</code>.</p>"
        + _group_trace(contributions, "STRUCTURED_DATA_SYNTAX")
        + "</article>"
        "<article class='ref-card'><h3>Consistência semântica</h3>"
        f"<p><code>BR-GEO-036</code> = {escape(rule_results['BR-GEO-036'])} · <code>BR-GEO-037</code> = {escape(rule_results['BR-GEO-037'])}</p>"
        "<p><strong>Grupo:</strong> <code>STRUCTURED_DATA_CONSISTENCY</code>. Quando aplicável, a análise pode usar evidência semântica/IA evidence-bound; o modelo não escolhe pesos.</p>"
        + _group_trace(contributions, "STRUCTURED_DATA_CONSISTENCY")
        + "</article></div>"
        f"<div class='notice'>{escape(absence_note)}</div>"
        "<p><a href='structured-data.html'>Abrir evidências detalhadas de conteúdo e JSON-LD →</a></p></section>"
    )


def _provenance_block'''

text = pattern.sub(replacement, text, count=1)
REPORT.write_text(text, encoding='utf-8', newline='\n')

# Current decision clarification: preserve the optional nature of JSON-LD while
# reflecting the SCORE-GEO-004 behavior that makes absence a small measurable gap.
decisions = DECISIONS.read_text(encoding='utf-8')
needle = '''JSON-LD/Structured Data é classificado como **OPCIONAL / REFORÇO**, não como requisito universal para GEO funcional. Sua ausência legítima, isoladamente, não é FAIL nem impedimento para Readiness Search & AI mensurável. Quando presente, deve ser interpretável e coerente com o conteúdo visível; markup inválido ou contraditório pode reduzir o score.
'''
replacement_decision = needle + '''
**Refinamento vigente no SCORE-GEO-004:** a ausência de JSON-LD é materializada por `BR-GEO-034` como `WARNING` de baixo impacto (fator 0,80) para tornar a lacuna visível e comparável; `BR-GEO-035..037` permanecem `NOT_APPLICABLE` enquanto não houver JSON-LD. Isso não transforma JSON-LD em requisito universal nem converte ausência em `FAIL`.
'''
if replacement_decision not in decisions:
    decisions = replace_once(decisions, needle, replacement_decision)
DECISIONS.write_text(decisions, encoding='utf-8', newline='\n')

guide = REPORT_GUIDE.read_text(encoding='utf-8')
addition = '''
## Rastreabilidade dos inputs do SARI

A página **Search & AI Readiness** deve distinguir o **estado observado** do nome/objetivo da regra. Um critério como “interpretar sitemap quando disponível” não pode ser apresentado como se o recurso tivesse sido encontrado. Para sitemap, `robots.txt` e JSON-LD o report expõe estado observado, RuleExecution, `scoring_group`, peso, fator e contribuição efetiva persistida.

`llms.txt` continua sendo inspecionado em **Rastreamento e descoberta** como sinal experimental/advisory. Seu peso direto no `SARI-001` é `0`: presença, ausência ou erro não alteram `SCORE-GEO-004`.

JSON-LD é extraído de `script[type="application/ld+json"]`. No SCORE-GEO-004, ausência gera uma lacuna leve via `BR-GEO-034=WARNING`; markup inválido pode ser desfavorável; consistência semântica só é avaliada quando aplicável.
'''
if '## Rastreabilidade dos inputs do SARI' not in guide:
    guide = guide.rstrip() + '\n' + addition
REPORT_GUIDE.write_text(guide, encoding='utf-8', newline='\n')

TEST.write_text(
    '''from pathlib import Path\n\n\ndef test_readiness_exposes_observed_discovery_state_not_presence_claim() -> None:\n    source = Path("src/rasai/rasai_readiness_reporting.py").read_text(encoding="utf-8")\n    assert "Sitemap disponível: aquisição e interpretação" not in source\n    assert "robots.txt presente: interpretabilidade" not in source\n    assert "AUSENTE não significa encontrado" in source\n    assert "peso SARI = 0" in source\n    assert "m24_runs" in source\n    assert "BR-GEO-055" in source and "BR-GEO-056" in source\n\n\ndef test_readiness_exposes_jsonld_scoring_trace() -> None:\n    source = Path("src/rasai/rasai_readiness_reporting.py").read_text(encoding="utf-8")\n    assert "_structured_data_scoring_block(data)" in source\n    assert "JSON-LD no cálculo do SCORE-GEO-004" in source\n    assert "script[type=&quot;application/ld+json&quot;]" in source\n    assert "STRUCTURED_DATA_SYNTAX" in source\n    assert "STRUCTURED_DATA_CONSISTENCY" in source\n    assert "BR-GEO-034" in source and "BR-GEO-037" in source\n\n\ndef test_method_docs_keep_llms_non_scoring_and_jsonld_absence_traceable() -> None:\n    decisions = Path("docs/specification/10_DECISIONS.md").read_text(encoding="utf-8")\n    guide = Path("docs/REPORT_GUIDE.md").read_text(encoding="utf-8")\n    assert "ausência de JSON-LD é materializada" in decisions\n    assert "llms.txt" in guide and "peso direto" in guide and "`0`" in guide\n''',
    encoding='utf-8', newline='\n'
)

print('SARI traceability refinement applied')
