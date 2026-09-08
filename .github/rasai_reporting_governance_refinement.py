from __future__ import annotations

from pathlib import Path
import re

ROOT = Path('.')


def _path(name: str) -> Path:
    return ROOT / name


def replace_once(name: str, old: str, new: str) -> None:
    path = _path(name)
    text = path.read_text(encoding='utf-8')
    if old not in text:
        raise RuntimeError(f'expected text not found in {name}: {old[:120]!r}')
    text = text.replace(old, new, 1)
    path.write_text(text, encoding='utf-8', newline='\n')


def replace_all(name: str, old: str, new: str) -> None:
    path = _path(name)
    text = path.read_text(encoding='utf-8')
    if old not in text:
        return
    path.write_text(text.replace(old, new), encoding='utf-8', newline='\n')


def regex_once(name: str, pattern: str, replacement: str) -> None:
    path = _path(name)
    text = path.read_text(encoding='utf-8')
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f'pattern count={count} for {name}: {pattern[:100]!r}')
    path.write_text(updated, encoding='utf-8', newline='\n')


def append_once(name: str, marker: str, addition: str) -> None:
    path = _path(name)
    text = path.read_text(encoding='utf-8')
    if marker in text:
        return
    path.write_text(text.rstrip() + '\n\n' + addition.strip() + '\n', encoding='utf-8', newline='\n')


# ---------------------------------------------------------------------------
# Public rule catalog / provenance: BR-GEO-055/056 are now real bounded rules.
# ---------------------------------------------------------------------------
replace_once(
    'src/rasai/report_navigation.py',
    '    "BR-GEO-054": "Integridade do auditor · Verifica a reprodutibilidade do SCORE-GEO-004 persistido.",\n}',
    '    "BR-GEO-054": "Integridade do auditor · Verifica a reprodutibilidade do SCORE-GEO-004 persistido.",\n'
    '    "BR-GEO-055": "Severidade dinâmica · Avalia, de forma evidence-bound e opcional por IA, a qualidade técnica do sitemap sem criar peso adicional no grupo SITEMAP.",\n'
    '    "BR-GEO-056": "Severidade dinâmica · Avalia, de forma evidence-bound e opcional por IA, a qualidade técnica de robots.txt sem criar peso adicional no grupo ROBOTS.",\n'
    '}',
)

replace_once(
    'src/rasai/rule_references.py',
    '    "BR-GEO-046", "BR-GEO-047", "BR-GEO-048", "BR-GEO-049",\n})',
    '    "BR-GEO-046", "BR-GEO-047", "BR-GEO-048", "BR-GEO-049",\n'
    '    "BR-GEO-055", "BR-GEO-056",\n})',
)
replace_once(
    'src/rasai/rule_references.py',
    '    elif rule_id == "BR-GEO-018":\n        rows.extend(\n            (\n                (*_RFC_9309, "robots.txt crawler policy protocol"),\n                (*_OPENAI_PUBLISHERS, "OAI-SearchBot search access and GPTBot training controls"),\n            )\n        )\n',
    '    elif rule_id == "BR-GEO-018":\n        rows.extend(\n            (\n                (*_RFC_9309, "robots.txt crawler policy protocol"),\n                (*_OPENAI_PUBLISHERS, "OAI-SearchBot search access and GPTBot training controls"),\n            )\n        )\n'
    '    elif rule_id == "BR-GEO-055":\n        rows.append((*_GOOGLE_SITEMAP, "contexto técnico do recurso sitemap; o verdict bounded continua heurística RASAi"))\n'
    '    elif rule_id == "BR-GEO-056":\n        rows.extend(\n            (\n                (*_RFC_9309, "contexto normativo de robots.txt para a avaliação bounded"),\n                (*_GOOGLE_ROBOTS, "interpretação técnica de robots.txt; o verdict bounded continua heurística RASAi"),\n            )\n        )\n',
)
replace_all('src/rasai/indicator_provenance.py', 'BR-GEO-001..054', 'BR-GEO-001..056')

# ---------------------------------------------------------------------------
# Public report contract: fix tuple bug and align bounded technical AI wording.
# ---------------------------------------------------------------------------
replace_once(
    'src/rasai/report_contract.py',
    '        ai_usage="Nenhum para o cálculo do SCORE-GEO-004.",',
    '        ai_usage="A fórmula e os pesos não dependem de IA. Quando habilitada, a IA técnica pode materializar somente avaliações evidence-bound bounded em BR-GEO-055/056, compartilhando os grupos determinísticos SITEMAP/ROBOTS sem escolher pesos nem criar bônus duplicado.",',
)
replace_once(
    'src/rasai/report_contract.py',
    '        score_impact="Somente regras explicitamente pertencentes ao SARI/SCORE podem contribuir; diagnósticos auxiliares permanecem separados.",',
    '        score_impact="BR-GEO-003/017/018 e, quando houver avaliação técnica evidence-bound válida, BR-GEO-055/056 podem contribuir pelos grupos SITEMAP/ROBOTS; demais diagnósticos desta superfície permanecem advisory/non-scoring.",',
)
replace_once(
    'src/rasai/report_contract.py',
    '        inputs=("fontes metodológicas e referências públicas"),',
    '        inputs=("fontes metodológicas e referências públicas",),',
)

# Generic governance guidance is injected into every canonical report contract.
replace_once(
    'src/rasai/report_registry.py',
    '        f"<div><h3>Fonte de verdade</h3><p>{escape(surface.source_of_truth)}</p></div>"\n        "</div></section>"\n    )',
    '        f"<div><h3>Fonte de verdade</h3><p>{escape(surface.source_of_truth)}</p></div>"\n'
    '        "</div>"\n'
    '        "<div class=\'notice report-reading-governance\' data-report-reading-governance=\'true\'>"\n'
    '        "<strong>Como interpretar e melhorar:</strong> um score alto e uma Confidence baixa não são resultados contraditórios: o score descreve a qualidade do que foi efetivamente avaliado, enquanto Coverage/Confidence descrevem a força e a completude da medição. "\n'
    '        "WARNING/FAIL devem ser tratados pela evidência e pelo critério exibidos na própria página; UNKNOWN/UNAVAILABLE/PARTIAL indicam dado não conclusivo ou cobertura insuficiente, salvo quando a superfície disser explicitamente o contrário. "\n'
    '        "Quando amostra, escopo, max_pages, timeout, integração opcional ou número mínimo de execuções limitarem a medição, o relatório deve sinalizar parametrização/cobertura e não converter isso em falha do website. Aumentar parâmetros amplia a matriz de medição; não corrige o site e não deve ser usado apenas para buscar uma nota melhor. Consulte a Visão geral para configuração × resultado obtido."\n'
    '        "</div></section>"\n    )',
)

# ---------------------------------------------------------------------------
# M24 observability and documentation contract.
# ---------------------------------------------------------------------------
replace_once(
    'src/rasai/m24_crawling_discovery.py',
    '"""M24 - Crawling, Discovery & AI Access diagnostics.\n\nThis module is additive and non-scoring. It reads persisted audit evidence/artifacts,\nadds deterministic technical diagnostics, optionally fetches same-origin /llms.txt,\nand persists a reopenable M24 projection. It never creates RuleExecution, Finding,\nScoreContribution, Score, Coverage, Confidence or Consolidation changes.\n"""',
    '"""M24 - Crawling, Discovery & AI Access diagnostics.\n\nThe deterministic M24 diagnostics are advisory/non-scoring and remain fail-open.\nWhen technical AI is explicitly enabled, a separate bounded bridge may materialize\nevidence-bound BR-GEO-055/056 RuleExecutions for the existing SITEMAP/ROBOTS\nscoring groups. The model never chooses weights, never creates an independent bonus,\nand cannot directly set Score, Coverage, Confidence or Consolidation.\n"""',
)
replace_once(
    'src/rasai/cli_extensions.py',
    'def _parse_extended_args(argv: list[str]):\n    if "audit" not in argv:\n        return None\n    parser = build_parser()\n    return parser, parser.parse_args(argv)\n\n\n',
    'def _parse_extended_args(argv: list[str]):\n    if "audit" not in argv:\n        return None\n    parser = build_parser()\n    return parser, parser.parse_args(argv)\n\n\ndef _m24_scoring_impact(*, audit_id: str, workspace) -> str:\n    result = load_m24_result(audit_id=audit_id, workspace=workspace)\n    return result.scoring_impact if result is not None else "NONE"\n\n\n',
)
replace_once(
    'src/rasai/cli_extensions.py',
    '                        report_path=str(m24_report_path.relative_to(workspace.root)),\n                        scoring_impact="NONE",\n',
    '                        report_path=str(m24_report_path.relative_to(workspace.root)),\n                        scoring_impact=_m24_scoring_impact(audit_id=audit_id, workspace=workspace),\n',
)

# ---------------------------------------------------------------------------
# scoring.html: group contributions by dimension and make each rule explicit.
# ---------------------------------------------------------------------------
replace_once(
    'src/rasai/score_geo_004_reporting.py',
    'LEGACY_REPORT_FILE = "score-geo-004.html"\n',
    'LEGACY_REPORT_FILE = "score-geo-004.html"\n\n_DIMENSION_LABELS = {\n'
    '    "TECHNICAL_ACCESSIBILITY": "Acessibilidade técnica",\n'
    '    "INDEXABILITY": "Capacidade de indexação",\n'
    '    "CONTENT_EXTRACTABILITY": "Extração de conteúdo",\n'
    '    "SEMANTIC_STRUCTURE": "Estrutura semântica",\n'
    '    "ENTITY_CLARITY": "Clareza de entidades",\n'
    '    "STRUCTURED_DATA": "Dados estruturados",\n'
    '    "ANSWERABILITY": "Capacidade de resposta",\n'
    '    "CITATION_READINESS": "Preparação para citação",\n'
    '    "EVIDENCE_TRUST": "Evidências e confiabilidade",\n'
    '    "INTENT_COVERAGE": "Cobertura de intenções",\n'
    '}\n',
)
regex_once(
    'src/rasai/score_geo_004_reporting.py',
    r'def _rule_weights\(audit_id: str, workspace: AuditWorkspace, scoring_version: str\) -> list\[sqlite3\.Row\]:.*?\n\n\ndef _method_section',
    '''def _rule_weights(audit_id: str, workspace: AuditWorkspace, scoring_version: str) -> list[sqlite3.Row]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        return list(connection.execute(
            """SELECT c.dimension,c.rule_id,c.scoring_group,c.weight,c.result,c.result_factor,c.effective_contribution
               FROM score_contributions c
               JOIN scores s ON s.score_id=c.score_id
               WHERE s.audit_id=? AND s.scoring_version=?
               ORDER BY c.dimension,c.scoring_group,c.rule_id,c.weight""",
            (audit_id, scoring_version),
        ).fetchall())
    except sqlite3.OperationalError:
        return []
    finally:
        connection.close()


def _rule_description(rule_id: str) -> str:
    text = report_navigation._RULE_TOOLTIPS.get(rule_id, "")
    if " · " in text:
        return text.split(" · ", 1)[1]
    return text or "Critério versionado do RASAi; consulte Referências e metodologia."


def _method_section''',
)
regex_once(
    'src/rasai/score_geo_004_reporting.py',
    r'def _method_section\(version: str, workspace: AuditWorkspace, audit_id: str\) -> str:.*?\n\n\ndef _dimension_list',
    '''def _method_section(version: str, workspace: AuditWorkspace, audit_id: str) -> str:
    if version == SCORING_VERSION:
        weights = _rule_weights(audit_id, workspace, version)
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in weights:
            grouped.setdefault(str(row["dimension"]), []).append(row)
        blocks: list[str] = []
        for dimension, rows in grouped.items():
            body: list[str] = []
            for row in rows:
                factor = "-" if row["result_factor"] is None else f"{float(row['result_factor']):.2f}"
                effective = "-" if row["effective_contribution"] is None else f"{float(row['effective_contribution']):.3f}"
                group = str(row["scoring_group"] or "regra independente")
                rule_id = str(row["rule_id"])
                body.append(
                    "<tr>"
                    f"<td><strong>{escape(rule_id)}</strong></td>"
                    f"<td>{escape(_rule_description(rule_id))}</td>"
                    f"<td><code>{escape(group)}</code></td>"
                    f"<td>{float(row['weight']):g}</td>"
                    f"<td>{escape(str(row['result']))}</td>"
                    f"<td>{escape(factor)}</td>"
                    f"<td>{escape(effective)}</td>"
                    "</tr>"
                )
            label = _DIMENSION_LABELS.get(dimension, dimension)
            blocks.append(
                f"<article class='ref-card scoring-dimension-group'><h4>{escape(label)}</h4>"
                "<div class='table-wrap'><table><thead><tr>"
                "<th>Regra</th><th>Critério</th><th>Grupo</th><th>Peso</th><th>Resultado</th><th>Fator</th><th>Contribuição efetiva</th>"
                f"</tr></thead><tbody>{''.join(body)}</tbody></table></div></article>"
            )
        materialized = "<div class='grid scoring-weight-groups'>" + "".join(blocks) + "</div>" if blocks else "<p class='intro'>Nenhuma contribuição persistida disponível para detalhar pesos nesta projeção.</p>"
        return f"""<section class='panel'><h2>Fórmula e gates do método vigente</h2><p><strong>Dimensão:</strong> <code>sum(weight × result_factor) / sum(weight evaluated) × 100</code>.</p><p><strong>Overall:</strong> média aritmética de igual peso das dimensões aplicáveis que possuem valor e não estão em <code>NOT_CONSOLIDATED</code>. Uma dimensão legitimamente <code>NOT_APPLICABLE</code> sai do denominador.</p><div class='metric-grid'>{_metric('Agregação Overall', OVERALL_AGGREGATION_VERSION)}{_metric('Coverage mínima para consolidar', f'{MIN_OVERALL_COVERAGE*100:.0f}%')}{_metric('Confidence mínima', 'MEDIUM')}{_metric('Coverage mínima para parcial', f'{MIN_PARTIAL_COVERAGE*100:.0f}%')}</div><h3>Contribuições materializadas neste AUD</h3><p class='intro'>A organização abaixo evita repetir visualmente a dimensão em cada linha e mostra o critério humano da regra, o <code>scoring_group</code>, o peso, o fator efetivamente aplicado e a contribuição persistida. Regras do mesmo grupo não somam bônus: o grupo usa o peso máximo configurado e o resultado representativo mais restritivo avaliado.</p>{materialized}<div class='notice'><strong>Governança da leitura:</strong> pesos de regra atuam somente dentro da dimensão. O Overall continua com peso igual entre dimensões aplicáveis. Um Overall numericamente alto pode permanecer <code>PARTIAL</code> quando Coverage/Confidence não alcançam os gates; isso qualifica a força da medição e não invalida a aritmética do score.</div><div class='notice'><strong>Calibração externa:</strong> não é requisito, input ou gate do Overall {SCORING_VERSION}.</div></section>"""
    if version == "MULTIPLE":
        return "<section class='panel'><h2>Integridade metodológica</h2><div class='notice bad'><strong>Múltiplas scoring_version foram encontradas no mesmo AUD.</strong> A projeção preserva os registros e não escolhe nem converte silenciosamente uma metodologia. Trate o AUD como não comparável até investigar a origem.</div></section>"
    return f"""<section class='panel'><h2>Metodologia histórica preservada</h2><p>Esta auditoria foi persistida com <strong>{escape(version)}</strong>. O RASAi não recalcula nem converte auditorias históricas para {SCORING_VERSION} durante a abertura do relatório.</p><p>{_historical_method_note(version)}</p><div class='notice'><strong>Regra de comparação:</strong> uma série histórica não pode misturar 002/003/004 como se fossem a mesma metodologia. Monitoring deve marcar versões incompatíveis como <code>NOT_COMPARABLE</code>.</div></section>"""


def _dimension_list''',
)
replace_once(
    'src/rasai/score_geo_004_reporting.py',
    "<div class='notice'><strong>IA e scoring:</strong> IA pode produzir evidência semântica para regras elegíveis quando habilitada. O output da IA não substitui a fórmula e não altera diretamente o Overall; o cálculo usa o estado/evidência persistidos conforme o contrato da auditoria.</div>",
    "<div class='notice'><strong>IA e scoring:</strong> IA não escolhe pesos, thresholds ou o Overall. Quando elegível e explicitamente habilitada, uma avaliação evidence-bound pode materializar RuleExecution bounded em regra previamente definida pelo contrato (por exemplo BR-GEO-055/056); essa regra compartilha o scoring_group do sinal determinístico e não cria bônus duplicado. O cálculo final continua determinístico sobre estados/evidências persistidos.</div>",
)

# ---------------------------------------------------------------------------
# readiness/index: explain score-vs-confidence, blockers, actions and parameters.
# ---------------------------------------------------------------------------
replace_once(
    'src/rasai/rasai_readiness_reporting.py',
    '''        discovery_executions = _many(
            connection,
            "SELECT * FROM rule_executions WHERE audit_id=? AND rule_id IN ('BR-GEO-003','BR-GEO-017','BR-GEO-018') ORDER BY rule_id,rule_execution_id",
            (audit_id,),
        )
        return {
            "audit": audit,
            "scores": scores,
            "contributions": contributions,
            "web_run": web_run,
            "web": web,
            "apdex_run": apdex_run,
            "apdex": apdex,
            "ai_session": ai_session,
            "ai_attempts": ai_attempts,
            "discovery_executions": discovery_executions,
        }
''',
    '''        discovery_executions = _many(
            connection,
            "SELECT * FROM rule_executions WHERE audit_id=? AND rule_id IN ('BR-GEO-003','BR-GEO-017','BR-GEO-018') ORDER BY rule_id,rule_execution_id",
            (audit_id,),
        )
        rule_executions = _many(
            connection,
            "SELECT rule_execution_id,rule_id,page_id,device,result,observed_value,expected_condition,error,evidence_ids FROM rule_executions WHERE audit_id=? ORDER BY rule_id,rule_execution_id",
            (audit_id,),
        )
        target = _one(
            connection,
            "SELECT * FROM audit_targets WHERE audit_id=? ORDER BY target_id LIMIT 1",
            (audit_id,),
        )
        return {
            "audit": audit,
            "target": target,
            "scores": scores,
            "contributions": contributions,
            "rule_executions": rule_executions,
            "web_run": web_run,
            "web": web,
            "apdex_run": apdex_run,
            "apdex": apdex,
            "ai_session": ai_session,
            "ai_attempts": ai_attempts,
            "discovery_executions": discovery_executions,
        }
''',
)
replace_once(
    'src/rasai/rasai_readiness_reporting.py',
    '{_audit_limitations_block(audit)}\n{_ai_operational_diagnostic(data)}',
    '{_audit_limitations_block(audit)}\n{_sari_governance_block(data)}\n{_ai_operational_diagnostic(data)}',
)
replace_once(
    'src/rasai/rasai_readiness_reporting.py',
    '''        + "<div class='indicator-tier-label indicator-tier-supporting'>Indicadores complementares - independentes do SARI-001</div>"
        + f"<div class='grid indicator-grid indicator-supporting-grid'>{''.join(cards)}</div></section>"
''',
    '''        + _sari_dashboard_explanation(data)
        + "<div class='indicator-tier-label indicator-tier-supporting'>Indicadores complementares - independentes do SARI-001</div>"
        + f"<div class='grid indicator-grid indicator-supporting-grid'>{''.join(cards)}</div></section>"
''',
)

# Insert governance helpers before the existing AI operational diagnostic.
replace_once(
    'src/rasai/rasai_readiness_reporting.py',
    '\n\ndef _ai_operational_diagnostic(data: dict[str, Any]) -> str:\n',
    r'''

def _governance_rule_description(rule_id: str) -> str:
    text = report_navigation._RULE_TOOLTIPS.get(rule_id, "")
    if " · " in text:
        return text.split(" · ", 1)[1]
    return text or "Critério versionado do RASAi."


def _governance_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _governance_execution(data: dict[str, Any], execution_id: str) -> sqlite3.Row | None:
    return next(
        (row for row in data.get("rule_executions", []) if str(row["rule_execution_id"]) == execution_id),
        None,
    )


def _governance_action(data: dict[str, Any], contribution: sqlite3.Row) -> str:
    execution = _governance_execution(data, str(contribution["rule_execution_id"]))
    if execution is not None:
        expected = str(execution["expected_condition"] or "").strip()
        if expected:
            return expected
    return _governance_rule_description(str(contribution["rule_id"]))


def _governance_observed_reason(data: dict[str, Any], contribution: sqlite3.Row) -> str:
    execution = _governance_execution(data, str(contribution["rule_execution_id"]))
    if execution is None:
        return ""
    observed = _governance_json(execution["observed_value"])
    for key in ("reason", "status", "state", "error"):
        value = observed.get(key)
        if value not in (None, "", [], {}):
            return f"{key}={value}"
    error = str(execution["error"] or "").strip()
    return error


def _sari_dashboard_explanation(data: dict[str, Any]) -> str:
    scores = data.get("scores", [])
    blocks: list[str] = []
    for device in ("MOBILE", "DESKTOP"):
        overall = next(
            (row for row in scores if str(row["device"]).upper() == device and str(row["dimension"]) == "OVERALL_READINESS"),
            None,
        )
        if overall is None or str(overall["consolidation_status"]) == "CONSOLIDATED":
            continue
        blockers = [
            row for row in scores
            if str(row["device"]).upper() == device
            and str(row["dimension"]) != "OVERALL_READINESS"
            and (str(row["confidence"]) in {"LOW", "UNAVAILABLE"} or str(row["consolidation_status"]) != "CONSOLIDATED")
        ]
        blocker_text = ", ".join(
            f"{_DIMENSION_LABELS.get(str(row['dimension']), str(row['dimension']))} ({float(row['coverage'])*100:.0f}% Coverage / {_STATUS_LABELS.get(str(row['confidence']), str(row['confidence']))})"
            for row in blockers
        ) or "uma ou mais dimensões não atingiram os gates de medição"
        label = "Mobile" if device == "MOBILE" else "Desktop"
        blocks.append(
            f"<div class='notice warn sari-governance-summary'><strong>Por que {label} está {escape(_STATUS_LABELS.get(str(overall['consolidation_status']), str(overall['consolidation_status'])))}:</strong> "
            f"o score {float(overall['value']):.1f}/100 descreve a qualidade dos grupos efetivamente avaliados; a Confidence qualifica a força da medição. "
            f"Neste AUD, o bloqueador é {escape(blocker_text)}. Para consolidar, é preciso tornar esses grupos conclusivos; não basta aumentar o score numérico. "
            "<a href='readiness.html#sari-governance'>Ver causa, regra e ação necessária</a>.</div>"
        )
    return "".join(blocks)


def _sari_parameterization_note(data: dict[str, Any]) -> str:
    audit = data.get("audit")
    target = data.get("target")
    if audit is None:
        return ""
    try:
        limits = json.loads(str(audit["limitations"] or "[]"))
    except (json.JSONDecodeError, TypeError, ValueError):
        limits = []
    items = [str(item) for item in limits] if isinstance(limits, list) else []
    rendered_gap = next((item for item in items if item.startswith("RENDERED_DISCOVERY_GAP:")), None)
    if rendered_gap is None:
        return ""
    count = rendered_gap.split(":", 1)[1] if ":" in rendered_gap else "?"
    target_type = str(target["target_type"] or "-") if target is not None and "target_type" in target.keys() else "-"
    max_pages = int(audit["max_pages"] or 0) if "max_pages" in audit.keys() else 0
    specific = ""
    if target_type.upper() == "DOMAIN" and max_pages <= 1:
        specific = (
            f" Neste AUD o target é DOMAIN com max_pages={max_pages}; isso é uma matriz mínima para um domínio. "
            "Se o objetivo for medir o domínio, aumente max_pages de forma conservadora. Se o objetivo for somente uma URL, prefira target de URL única."
        )
    return (
        "<div class='notice' data-parameterization-guidance='true'><strong>Parametrização e escopo:</strong> "
        f"o rendering encontrou {escape(count)} destino(s) same-origin fora do universo efetivamente auditado. "
        "Isso é uma limitação de cobertura do escopo escolhido, não um erro do RASAi e não é convertido automaticamente em FAIL do website."
        + escape(specific)
        + " Alterar parâmetros amplia a matriz de medição; não deve ser usado apenas para buscar uma nota maior.</div>"
    )


def _sari_governance_block(data: dict[str, Any]) -> str:
    scores = data.get("scores", [])
    contributions = data.get("contributions", [])
    sections: list[str] = []
    for device in ("MOBILE", "DESKTOP"):
        overall = next(
            (row for row in scores if str(row["device"]).upper() == device and str(row["dimension"]) == "OVERALL_READINESS"),
            None,
        )
        if overall is None:
            continue
        label = "Mobile" if device == "MOBILE" else "Desktop"
        dimensions = [
            row for row in scores
            if str(row["device"]).upper() == device and str(row["dimension"]) != "OVERALL_READINESS"
        ]
        blockers = [
            row for row in dimensions
            if str(row["confidence"]) in {"LOW", "UNAVAILABLE"} or str(row["consolidation_status"]) != "CONSOLIDATED"
        ]
        blocker_cards: list[str] = []
        for dimension in blockers:
            dim_name = str(dimension["dimension"])
            unresolved = [
                row for row in contributions
                if str(row["device"]).upper() == device
                and str(row["dimension"]) == dim_name
                and (str(row["result"]) in {"UNKNOWN", "ERROR"} or row["result_factor"] is None)
            ]
            details: list[str] = []
            for contribution in unresolved:
                rule_id = str(contribution["rule_id"])
                reason = _governance_observed_reason(data, contribution)
                action = _governance_action(data, contribution)
                details.append(
                    f"<li><strong>{escape(rule_id)}</strong> - {escape(_governance_rule_description(rule_id))}. "
                    + (f"<span class='muted'>Evidência atual: {escape(reason)}.</span> " if reason else "")
                    + f"<strong>Para tornar a medição conclusiva:</strong> {escape(action)}.</li>"
                )
            why = (
                f"Coverage {float(dimension['coverage'])*100:.1f}% · Confidence {_STATUS_LABELS.get(str(dimension['confidence']), str(dimension['confidence']))} · "
                f"Consolidação {_STATUS_LABELS.get(str(dimension['consolidation_status']), str(dimension['consolidation_status']))}"
            )
            blocker_cards.append(
                f"<article class='ref-card'><h4>{escape(_DIMENSION_LABELS.get(dim_name, dim_name))}</h4><p>{escape(why)}</p>"
                + (f"<ul>{''.join(details)}</ul>" if details else "<p>A dimensão não atingiu o gate; consulte suas RuleExecutions/evidências para a causa persistida.</p>")
                + "</article>"
            )

        deductions = [
            row for row in contributions
            if str(row["device"]).upper() == device
            and row["result_factor"] is not None
            and float(row["result_factor"]) < 1.0
        ]
        deduction_rows: list[str] = []
        for contribution in deductions[:16]:
            rule_id = str(contribution["rule_id"])
            dim_name = str(contribution["dimension"])
            deduction_rows.append(
                "<tr>"
                f"<td>{escape(_DIMENSION_LABELS.get(dim_name, dim_name))}</td>"
                f"<td><strong>{escape(rule_id)}</strong><br><small>{escape(_governance_rule_description(rule_id))}</small></td>"
                f"<td>{escape(str(contribution['result']))}</td>"
                f"<td>{float(contribution['weight']):g}</td>"
                f"<td>{float(contribution['result_factor']):.2f}</td>"
                f"<td>{escape(_governance_action(data, contribution))}</td>"
                "</tr>"
            )
        deductions_html = (
            "<h4>O que reduz o score e pode ser melhorado</h4><p class='intro'>Estes itens foram avaliados conclusivamente; portanto afetam a nota, mas não são necessariamente a causa de Confidence baixa. Corrigi-los melhora a qualidade medida. Não altere parâmetros apenas para mascarar esses resultados.</p>"
            "<div class='table-wrap'><table><thead><tr><th>Dimensão</th><th>Regra / critério</th><th>Resultado</th><th>Peso</th><th>Fator</th><th>Condição esperada</th></tr></thead>"
            f"<tbody>{''.join(deduction_rows)}</tbody></table></div>"
            if deduction_rows else "<p class='intro'>Nenhuma dedução conclusiva materializada neste dispositivo.</p>"
        )
        status = str(overall["consolidation_status"])
        confidence = str(overall["confidence"])
        summary_class = "good" if status == "CONSOLIDATED" else "warn"
        summary = (
            f"<div class='notice {summary_class}'><strong>Leitura de governança - {label}:</strong> "
            f"Overall {('-' if overall['value'] is None else f'{float(overall['value']):.1f}/100')} · Coverage {float(overall['coverage'])*100:.1f}% · "
            f"Confidence {_STATUS_LABELS.get(confidence, confidence)} · Consolidação {_STATUS_LABELS.get(status, status)}. "
        )
        if status != "CONSOLIDATED":
            summary += (
                "O gate de consolidação exige Coverage Overall de pelo menos 80% e Confidence mínima MEDIUM. "
                "O Overall herda a menor Confidence entre as dimensões aplicáveis; por isso uma nota relativamente alta pode permanecer parcial sem contradição."
            )
        else:
            summary += "Os gates mínimos de Coverage e Confidence foram atendidos para esta medição."
        summary += "</div>"
        blocker_html = (
            "<h4>Por que Confidence/Consolidação não chegaram ao ideal</h4>"
            + ("<div class='grid'>" + "".join(blocker_cards) + "</div>" if blocker_cards else "<p>Nenhuma dimensão bloqueante.</p>")
        )
        sections.append(f"<section class='sari-governance-device'>{summary}{blocker_html}{deductions_html}</section>")

    if not sections:
        return ""
    return (
        "<section id='sari-governance' class='panel'><div class='kicker'>Governança da medição</div>"
        "<h2>Por que o SARI chegou a este resultado e como melhorar</h2>"
        "<p class='intro'>O RASAi separa três perguntas: <strong>qualidade medida</strong> (Score), <strong>quanto do universo aplicável foi realmente avaliado</strong> (Coverage) e <strong>força da medição</strong> (Confidence). Consolidation aplica gates sobre Coverage/Confidence. Essa separação evita transformar ausência de evidência em falsa qualidade ou falsa falha.</p>"
        + "".join(sections)
        + _sari_parameterization_note(data)
        + "</section>"
    )


def _ai_operational_diagnostic(data: dict[str, Any]) -> str:
''',
)

# Fix nested f-string quoting introduced in the large helper using a safer helper expression.
path = _path('src/rasai/rasai_readiness_reporting.py')
text = path.read_text(encoding='utf-8')
text = text.replace(
    "f\"Overall {('-' if overall['value'] is None else f'{float(overall['value']):.1f}/100')} · Coverage {float(overall['coverage'])*100:.1f}% · \"",
    "f\"Overall {('-' if overall['value'] is None else format(float(overall['value']), '.1f') + '/100')} · Coverage {float(overall['coverage'])*100:.1f}% · \"",
)
path.write_text(text, encoding='utf-8', newline='\n')

# ---------------------------------------------------------------------------
# Documentation / specifications aligned with 055/056 and governance semantics.
# ---------------------------------------------------------------------------
for name in (
    'docs/RULES_GUIDE.md',
    'docs/INDICATOR_PROVENANCE.md',
    'docs/specification/03_BUSINESS_RULES.md',
    'docs/specification/07_FUNCTIONAL_REQUIREMENTS.md',
):
    replace_all(name, 'BR-GEO-001..054', 'BR-GEO-001..056')

replace_once(
    'docs/specification/03_BUSINESS_RULES.md',
    '### BR-GEO-054 - Every score must be reproducible and reliability-aware\n\nTodo score deve ser reconstruível com ruleset e scoring version.\n',
    '### BR-GEO-054 - Every score must be reproducible and reliability-aware\n\nTodo score deve ser reconstruível com ruleset e scoring version.\n\n'
    '### BR-GEO-055 - Evidence-bound sitemap quality assessment may refine the SITEMAP scoring group\n\nRegra opcional, HEURISTIC e dependente de IA técnica explicitamente habilitada. Recebe somente evidence IDs persistidos do recurso sitemap, produz verdict POSITIVE/NEUTRAL/NEGATIVE e nunca escolhe peso numérico. Compartilha o grupo `SITEMAP` e o peso da BR-GEO-003; resultado positivo não soma bônus e baixa confiança do provider não pode produzir PASS/FAIL duro.\n\n'
    '### BR-GEO-056 - Evidence-bound robots quality assessment may refine the ROBOTS scoring group\n\nRegra opcional, HEURISTIC e dependente de IA técnica explicitamente habilitada. Recebe somente evidence IDs persistidos de robots.txt, produz verdict POSITIVE/NEUTRAL/NEGATIVE e nunca escolhe peso numérico. Compartilha o grupo `ROBOTS` e o peso das BR-GEO-017/018; resultado positivo não soma bônus e baixa confiança do provider não pode produzir PASS/FAIL duro.\n',
)

append_once(
    'docs/RULES_GUIDE.md',
    '### BR-GEO-055 / BR-GEO-056 - avaliação técnica bounded por IA',
    '''### BR-GEO-055 / BR-GEO-056 - avaliação técnica bounded por IA

Quando `RASAI_AI_TECHNICAL_REMEDIATION=true`, o RASAi pode usar uma saída evidence-bound para qualificar tecnicamente sitemap e robots.txt. Essas regras são HEURISTIC e opcionais: o provider não escolhe pesos, não altera thresholds e não cria um score paralelo. BR-GEO-055 compartilha `SITEMAP` com BR-GEO-003; BR-GEO-056 compartilha `ROBOTS` com BR-GEO-017/018. O scoring group usa o resultado representativo mais restritivo e impede bônus duplicado. Falha/ausência do provider permanece explícita e não vira FAIL do website.''',
)
append_once(
    'docs/INDICATOR_PROVENANCE.md',
    '### Governança de Score, Coverage e Confidence',
    '''### Governança de Score, Coverage e Confidence

Um score relativamente alto não implica automaticamente Confidence alta. Score mede a qualidade dos grupos efetivamente avaliados; Coverage mede completude; Confidence mede força da medição e o Overall herda a menor Confidence entre as dimensões aplicáveis. Por isso `PARTIAL` deve ser acompanhado da dimensão/regra bloqueante e da condição necessária para tornar a evidência conclusiva. Limitações de escopo ou parametrização (`max_pages`, amostra mínima, timeout, integração opcional) devem ser identificadas como limites da matriz de medição, não como falhas arbitrárias do website ou do auditor.''',
)
append_once(
    'docs/SARI_READINESS_INDEX.md',
    '## Governança explicável do resultado',
    '''## Governança explicável do resultado

A projeção pública deve permitir ao analista distinguir:

- **dedução de qualidade**: PASS/WARNING/FAIL avaliado, com peso/fator e condição esperada;
- **lacuna de medição**: UNKNOWN/ERROR/coverage insuficiente, que afeta Confidence/Consolidation sem ser convertido em FAIL;
- **limitação de parametrização**: escopo, `max_pages`, amostra mínima, timeout ou integração opcional que restringem a matriz coletada.

O relatório deve explicar por que um SARI numericamente alto pode ser `PARTIAL/LOW` e indicar a dimensão/regra que precisa de evidência conclusiva. Ajustar parâmetros amplia a observação e não deve ser usado para fabricar melhora de score.''',
)
append_once(
    'docs/SCORING_GUIDE.md',
    '## Explicabilidade operacional',
    '''## Explicabilidade operacional

`scoring.html` materializa, por dimensão, regra representativa, critério, `scoring_group`, peso, resultado, fator e contribuição efetiva. Regras do mesmo grupo não recebem pesos cumulativos. A leitura operacional deve separar itens que reduzem score de itens que apenas reduzem Coverage/Confidence. O Overall usa peso igual entre dimensões aplicáveis; os pesos exibidos atuam apenas dentro de cada dimensão.''',
)
append_once(
    'docs/SCORE_GEO_004.md',
    '## Regra de explicabilidade da medição',
    '''## Regra de explicabilidade da medição

Toda projeção do SCORE-GEO-004 deve tornar auditável a diferença entre qualidade medida e força da medição. `PARTIAL` com score alto é válido quando o gate de Confidence não foi satisfeito; o relatório deve nomear a dimensão bloqueante, as RuleExecutions UNKNOWN/ERROR relevantes e a condição esperada para tornar a medição conclusiva. Limitações de configuração devem ser apresentadas como limites do escopo/amostra, sem conversão automática em falha do website.''',
)

# M24 specification and decisions: diagnostics remain advisory, bounded rules are explicit.
replace_all('docs/specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md',
            '2. LLM não decide RuleExecution, Finding, Score, Coverage, Confidence ou Consolidation;\n3. diagnósticos próprios persistem `scoring_impact=NONE`;',
            '2. LLM não escolhe pesos, thresholds, Score, Coverage, Confidence ou Consolidation; somente uma saída evidence-bound válida pode ser convertida pelo runtime nas regras bounded BR-GEO-055/056;\n3. diagnósticos próprios permanecem advisory com `scoring_impact=NONE`; quando BR-GEO-055/056 são materializadas, `m24_runs.scoring_impact=BOUNDED_AI_RESOURCE_ASSESSMENT`;')
replace_all('docs/specification/07_FUNCTIONAL_REQUIREMENTS.md',
            'Executar Rastreamento, descoberta e acesso de crawlers como enriquecimento técnico não-scoring de crawling/discovery, preservando `scoring_impact=NONE` e sem alterar retrospectivamente RuleExecution, Finding, Recommendation GEO, Score, Coverage, Confidence, Consolidation, `SCORE-GEO-003` ou `SARI-001`.',
            'Executar Rastreamento, descoberta e acesso de crawlers com diagnósticos determinísticos advisory/non-scoring. Quando IA técnica estiver explicitamente habilitada e produzir saída evidence-bound válida, permitir somente BR-GEO-055/056 bounded nos grupos SITEMAP/ROBOTS, sem escolha de pesos pelo provider, sem bônus duplicado e sem alteração direta de Coverage, Confidence ou Consolidation. O runtime vigente permanece SCORE-GEO-004/SARI-001.')
replace_all('docs/specification/10_DECISIONS.md',
            '1. diagnósticos de rastreamento e descoberta permanecem determinísticos e persistidos com `scoring_impact=NONE`;',
            '1. diagnósticos determinísticos de rastreamento e descoberta permanecem advisory e persistidos com `scoring_impact=NONE`; avaliações técnicas evidence-bound explicitamente habilitadas podem materializar somente BR-GEO-055/056 bounded, registrando `BOUNDED_AI_RESOURCE_ASSESSMENT` no run sem criar peso adicional;')

# ---------------------------------------------------------------------------
# Regression tests for governance and contract adherence.
# ---------------------------------------------------------------------------
test_path = _path('tests/test_reporting_governance_refinement_20260908.py')
test_path.write_text(r'''from __future__ import annotations

from pathlib import Path

from rasai import report_navigation
from rasai.report_contract import surface_by_id
from rasai.rule_references import references_for


def test_bounded_discovery_rules_have_public_titles_and_heuristic_provenance() -> None:
    assert "BR-GEO-055" in report_navigation._RULE_TOOLTIPS
    assert "BR-GEO-056" in report_navigation._RULE_TOOLTIPS
    assert references_for("BR-GEO-055")[0].basis == "HEURISTIC"
    assert references_for("BR-GEO-056")[0].basis == "HEURISTIC"


def test_scoring_contract_explains_bounded_ai_and_reference_inputs_are_tuple() -> None:
    scoring = surface_by_id("scoring")
    refs = surface_by_id("references")
    assert "BR-GEO-055/056" in scoring.ai_usage
    assert refs.inputs == ("fontes metodológicas e referências públicas",)


def test_m24_operational_log_no_longer_hardcodes_none() -> None:
    text = Path("src/rasai/cli_extensions.py").read_text(encoding="utf-8")
    marker = '"M24_REPORT_GENERATED"'
    start = text.index(marker)
    block = text[start:start + 900]
    assert 'scoring_impact="NONE"' not in block
    assert "_m24_scoring_impact" in block


def test_scoring_report_materializes_human_rule_criterion_and_group() -> None:
    text = Path("src/rasai/score_geo_004_reporting.py").read_text(encoding="utf-8")
    assert "<th>Critério</th>" in text
    assert "<th>Grupo</th>" in text
    assert "Contribuição efetiva" in text
    assert "_rule_description" in text


def test_readiness_report_has_explainable_governance_and_parameterization_language() -> None:
    text = Path("src/rasai/rasai_readiness_reporting.py").read_text(encoding="utf-8")
    assert "Por que o SARI chegou a este resultado e como melhorar" in text
    assert "O Overall herda a menor Confidence" in text
    assert "não um erro do RASAi" in text
    assert "O que reduz o score e pode ser melhorado" in text


def test_all_report_contracts_receive_operational_reading_governance() -> None:
    text = Path("src/rasai/report_registry.py").read_text(encoding="utf-8")
    assert "data-report-reading-governance" in text
    assert "Aumentar parâmetros amplia a matriz de medição" in text


def test_ruleset_documentation_includes_055_056() -> None:
    business = Path("docs/specification/03_BUSINESS_RULES.md").read_text(encoding="utf-8")
    guide = Path("docs/RULES_GUIDE.md").read_text(encoding="utf-8")
    assert "BR-GEO-001..056" in business
    assert "BR-GEO-055" in business and "BR-GEO-056" in business
    assert "BR-GEO-055 / BR-GEO-056" in guide
''', encoding='utf-8', newline='\n')

print('RASAi reporting governance refinement applied')
