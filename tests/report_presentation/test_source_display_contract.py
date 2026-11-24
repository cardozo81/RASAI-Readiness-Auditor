"""Surgical source-only presentation assertions for the presentation source contract.

Fixtures simulate persisted rows; they do not assert that a physical AUD was
inspected or that historical data can be regenerated without its audit.db.
"""
import json

from rasai.parallel_report.read_model import build
from rasai.parallel_report.page_views import editorial
from rasai.parallel_report.thresholds import load
from rasai.parallel_report.cost_reconciliation import reconcile
from rasai.parallel_report.execution_context import build_execution_context
from rasai.parallel_report.analytical_views import build_analytical_views
from rasai.parallel_report.action_plan import render_plan, consultative_search_opportunities
from rasai.parallel_report.governance import Governance
from rasai.parallel_report.render import record_html


def model(tables):
    schema = {
        name: {'columns': sorted({k for row in rows for k in row}),
               'primary_key': [], 'foreign_keys': []}
        for name, rows in tables.items()
    }
    return build(tables, schema), schema


def test_costs_keep_estimate_and_dated_snapshot_distinct():
    priced = [
        {'attempt_id': f'AI-{i}', 'provider': 'example', 'model': 'mock',
         'status': 'SUCCESS', 'estimated_cost': 0.02, 'observed_cost': None,
         'cost_currency': 'USD', 'started_at': '2026-11-17T17:30:00'}
        for i in range(6)
    ]
    remediation = [{
        'attempt_id': 'REMED-1', 'provider': 'example', 'model': 'mock',
        'estimated_cost': 0.084055, 'observed_cost': None,
        'cost_currency': 'USD', 'started_at': '2026-11-17T17:31:00'
    }]
    tables = {
        'ai_provider_attempts': priced,
        'content_remediation_attempts': remediation,
        'console_cost_forecast_outcomes': [{
            'evaluated_at': '2026-11-17T16:09:25',
            'actual_cost': 0.005, 'currency': 'USD'
        }],
    }
    records, _ = model(tables)
    result = reconcile(tables)
    html = editorial('ia-custos', records, result, load())
    assert 'USD 0.204055 em 7 tentativas com preço' in html
    assert 'N/D — nenhum custo observado pelo provedor' in html
    assert '17/11/2026 13:09:25 (America/Sao_Paulo)' in html
    assert 'anterior a 7 tentativa(s)' in html
    assert 'Custo técnico conciliado' not in html
    assert html.count('Preço por tentativa') >= 1


def test_forecast_note_is_superseded_only_when_contract_is_newer():
    tables = {
        'console_cost_forecast_outcomes': [{
            'evaluated_at': '2026-11-17T16:09:25',
            'notes': '5 requisitos obrigatórios incompletos', 'status': 'NOT_COMPARABLE',
            'currency': 'USD',
        }],
        'audit_fulfillment_contracts': [{
            'completed_at': '2026-11-17T17:32:04',
        }],
    }
    records, schema = model(tables)
    pages, _ = build_analytical_views(tables, records, schema, 'UTC')
    html = pages['ia-custos']
    assert 'Registrado em 17/11/2026 16:09:25 (UTC)' in html
    assert 'superado pelo contrato de fulfillment concluído em 17/11/2026 17:32:04 (UTC)' in html
    assert '5 requisitos obrigatórios incompletos' in html


def test_reprocessing_history_two_rows_and_archived_receipt():
    tables = {
        'audit_fulfillment_contracts': [{
            'processing_status': 'COMPLETE', 'score_status': 'FINAL',
            'report_status': 'FINAL', 'required_items': 15,
            'successful_items': 15, 'pending_items': 0, 'blocked_items': 0,
            'consolidation_eligible': 1,
        }],
        'audit_reprocess_runs': [
            {'reprocess_id': 'RPR-A', 'status': 'FAILED_RETRYABLE',
             'attempted_items': 0, 'successful_items': 0, 'remaining_items': 4,
             'configuration': '{"selected_items":["A"]}'},
            {'reprocess_id': 'RPR-B', 'status': 'SUCCESS',
             'attempted_items': 4, 'successful_items': 4, 'remaining_items': 0,
             'configuration': '{"selected_items":["B"]}'},
        ],
        'audit_reprocess_derived_archive': [{'archive_id': f'AR-{i}'} for i in range(271)],
    }
    pages, _ = build_execution_context(tables, {'pages': {}})
    panel = pages['index:execution']
    assert 'Histórico de execução — 2 reprocessamentos' in panel
    assert 'RPR-A' in panel and 'RPR-B' in panel
    assert 'Registros derivados arquivados: 271' in panel
    assert 'Itens selecionados' in panel and 'A' in panel and 'B' in panel
    assert 'anexos/' in panel


def test_ai_failures_have_visible_fallback_and_status_aggregation():
    tables = {'ai_provider_attempts': [
        {'attempt_id': 'AI-FAIL', 'provider': 'mock', 'model': 'stub',
         'status': 'TECHNICAL_ERROR', 'error_code': 'TIMEOUT',
         'fallback_reason': 'indisponível temporariamente',
         'request_message_summary': 'diagnóstico técnico'}
    ]}
    records, _ = model(tables)
    html = editorial('ia-custos', records, reconcile(tables), load())
    assert 'Contagens por status persistido' in html
    assert 'Contagens por categoria de erro' in html
    assert 'TECHNICAL_ERROR' in html and 'TIMEOUT' in html
    assert 'indisponível temporariamente' in html
    assert 'diagnóstico técnico' in html


def test_root_groups_and_occurrences_do_not_authorize_client_execution():
    groups = [
        {'group_id': f'RG-{i}', 'rule_id': f'RULE-{i}',
         'root_cause': f'Causa {i}', 'priority_class': 'P1' if i == 0 else 'P2',
         'priority_score': 80 - i, 'severity': 'HIGH', 'impact': 'MEDIUM',
         'effort': 'LOW', 'affected_findings': json.dumps([f'F-{i}'])}
        for i in range(8)
    ]
    actions = [
        {'action_id': f'ACT-{i}', 'title': f'Ação {i % 40}',
         'source_id': 'test', 'source_kind': 'DETERMINISTIC',
         'priority': 'LOW'}
        for i in range(59)
    ]
    tables = {'remediation_groups': groups, 'directed_analysis_actions': actions}
    records, _ = model(tables)
    indexed = {row.table: [] for row in records}
    from rasai.parallel_report.read_model import thaw
    for row in records:
        indexed[row.table].append({**thaw(row.data), '_ref': row.href})
    html = render_plan(lambda names: [item for name in names for item in indexed.get(name, [])],
                       'UTC', Governance([]))
    assert 'Grupos por causa-raiz' in html
    assert 'Causa 0' in html and 'Causa 7' in html
    assert '59 ocorrências / 40 títulos' in html
    assert 'F-0' in html and 'F-7' in html
    assert 'Prioridade do motor' in html
    assert 'Prioridade do plano direcionado' in html
    assert 'Plano aprovado pela governança' in html



def test_consultative_serp_plan_exposes_all_seven_without_dialog_or_approval():
    proposal = {
        'title': 'Oportunidade editorial repetida',
        'priority': 'HIGH',
        'recommendation': 'Publicar conteúdo verificável e específico.',
        'rationale': 'Diferença observada entre páginas, sem causalidade comprovada.',
        'causality_note': 'Não garante posição nem citação.',
        'confidence': 0.91,
        'evidence_ids': ['CE-CUSTOMER', 'CE-COMP-001'],
    }
    row = {
        'observation_id': 'SERP-TEST',
        'state': 'AVAILABLE',
        'opportunity_count': 7,
        'opportunities_json': json.dumps([proposal] * 7),
        '_ref': 'search' '-geo.html#record-test',
    }
    html = consultative_search_opportunities(
        lambda names: [row] if names == ['serp_competitive_ai_analyses'] else [], 'UTC'
    )
    assert 'Propostas materializadas:</strong> 7' in html
    assert html.split('<tbody>', 1)[1].split('</tbody>', 1)[0].count('<tr>') == 7
    assert html.count('Publicar conteúdo verificável e específico.') == 14  # cell and title
    assert 'Não garante posição nem citação.' in html
    assert '0,91' in html and 'Confiança declarada na fonte' in html
    assert 'Prioridade e confiança são declarações da fonte' in html
    assert 'search' '-geo.html#record-test' in html
    assert 'detail-dialog' not in html
    assert 'não ações do plano aprovado' in html
    assert 'Plano aprovado pela governança' not in html


def test_consultative_serp_abstains_and_flags_inconsistent_evidence():
    rows = [
        {'state': 'FAILED', 'opportunity_count': 1,
         'opportunities_json': '[{"title":"Não publicar"}]'},
        {'state': 'AVAILABLE', 'opportunity_count': 1,
         'opportunities_json': 'não é JSON'},
        {'state': 'AVAILABLE', 'opportunity_count': 2,
         'opportunities_json': '[{"title":"Oportunidade presente"}]'},
    ]
    html = consultative_search_opportunities(
        lambda names: rows if names == ['serp_competitive_ai_analyses'] else [], 'UTC'
    )
    assert 'Propostas materializadas:</strong> 1' in html
    assert 'Oportunidade presente' in html and 'Não publicar' not in html
    assert '2 análise(s) indisponível(is) ou ilegível(is)' in html
    assert '1 divergência(s)' in html
    empty = consultative_search_opportunities(lambda _: [], 'UTC')
    assert 'nenhuma proposta competitiva de IA disponível' in empty
    assert 'Propostas materializadas:' not in empty


def test_consultative_serp_survives_absent_directed_plan():
    proposals = [{
        'title': 'Criar página educacional',
        'priority': 'MEDIUM',
        'recommendation': 'Validar fatos antes da publicação.',
    }]
    rows_by_table = {'serp_competitive_ai_analyses': [{
        'state': 'AVAILABLE', 'opportunity_count': 1,
        'opportunities_json': proposals,
        '_ref': 'search' '-geo.html#record-test',
    }]}
    def rows(names):
        return [item for name in names for item in rows_by_table.get(name, [])]
    html = render_plan(rows, 'UTC', Governance([]))
    assert 'Plano de ação não materializado' in html
    assert 'Criar página educacional' in html
    assert 'Plano aprovado pela governança' not in html


def test_crosslinked_records_use_unique_accessible_link_names():
    tables = {'findings': [
        {'finding_id': 'F-1', 'title': 'Título idêntico'},
        {'finding_id': 'F-2', 'title': 'Título idêntico'}]}
    schema = {'findings': {'columns': ['finding_id', 'title'],
                           'primary_key': ['finding_id'], 'foreign_keys': []}}
    records = build(tables, schema)
    source = records[0]
    targets = {r.href: r for r in records}
    html = record_html(source, {source.href: (records[1].href,)}, lookup=targets)
    assert 'relacionado 1' not in html
    assert 'aria-label="Detalhe: Achados da auditoria' in html
    assert records[1].anchor in html


def test_security_platform_text_hides_non_public_raw_identifiers():
    tables = {'passive_security_platforms': [
        {'platform_ref': 'P-1', 'platform_name': 'Example analytics',
         'confidence': 'HIGH',
         'identifiers_json': json.dumps([
             {'identifier_class': 'PUBLIC_IDENTIFIER', 'identifier_display': 'GTM-PUBLIC'},
             {'identifier_class': 'PRIVATE_IDENTIFIER', 'identifier_display': 'SECRET-INNER',
              'identifier_hash': 'hashed-only'},
         ]),
         'evidence_ids_json': '["E-1"]'},
    ]}
    records, _ = model(tables)
    html = editorial('seguranca', records, reconcile(tables), load())
    assert 'GTM-PUBLIC' in html and 'hashed-only' in html
    assert 'SECRET-INNER' not in html
    details = record_html(records[0], {records[0].href: ()})
    assert 'GTM-PUBLIC' in details and 'hashed-only' in details
    assert 'SECRET-INNER' not in details

def test_generated_html_uses_content_hashed_json_for_record_payloads():
    from hashlib import sha256
    from rasai.parallel_report.annex_payloads import collect_payloads
    from rasai.parallel_report.components import table
    from rasai.parallel_report.render import payload

    with collect_payloads() as attached:
        modal = table('Fonte de teste', [{
            'title': 'Registro', 'request_payload': '{"source":"true"}',
            'metadata': {'origin': 'audit.db'}
        }], [('title', 'Título')])
        technical = payload({'source': 'audit.db', 'values': [1, 2]})

    assert '<pre>' not in modal and '<pre>' not in technical
    assert 'href="anexos/' in modal
    assert 'href="anexos/' in technical
    assert attached
    for filename, content in attached.items():
        assert filename == sha256(content).hexdigest() + '.json'
        assert isinstance(json.loads(content), dict)

def test_panel_has_source_links_and_technical_ledgers_remain_in_origin_pages():
    from hashlib import sha256
    from rasai.parallel_report.read_model import destination
    from rasai.parallel_report.render import render

    assert destination('audit_input_urls') == 'extracao'
    assert destination('audit_fulfillment_work_items') == 'ia-custos'
    assert destination('audit_reprocess_derived_archive') == 'ia-custos'
    assert destination('audits') == 'index'

    tables = {
        'audits': [{'audit_id': 'AUD-SYNTHETIC'}],
        'audit_input_urls': [{'position': 1, 'input_url': 'https://example.org'}],
        'audit_reprocess_runs': [{'reprocess_id': 'RPR-X', 'status': 'SUCCESS'}],
    }
    records, _ = model(tables)
    links = {record.href: () for record in records}
    pages = render(records, links, tables, [], [], reconcile(tables),
                   {'status': 'NOT_VERIFIED'}, load(), [])
    for name, rows in tables.items():
        page = destination(name)
        target = (page + '.html#source-' +
                  sha256(name.encode()).hexdigest()[:12])
        assert 'href="' + target + '"' in pages['index.html']
        assert 'id="source-' + sha256(name.encode()).hexdigest()[:12] + '"' in pages[page + '.html']
    assert 'RPR-X' in pages['ia-custos.html']
    assert 'record-' + sha256(json.dumps(['audit_reprocess_runs', 0],
                    sort_keys=True).encode()).hexdigest()[:24] in pages['ia-custos.html']
    assert 'RPR-X' not in pages['index.html'].split('Inventário integral de registros e anexos', 1)[-1]


def test_historical_record_relocation_is_not_data_loss(tmp_path):
    """P9: a migrated audit-ledger record retains its identity on its new page."""
    from scripts.presentation_acceptance import compare_reports

    previous = tmp_path / 'legacy'
    current = tmp_path / 'current'
    (previous / 'anexos').mkdir(parents=True)
    current.mkdir()
    (previous / 'index.html').write_text(
        '<div class="record" id="record-abc">Old location</div>', encoding='utf-8')
    (current / 'index.html').write_text('<h1>Painel</h1>', encoding='utf-8')
    (current / 'ia-custos.html').write_text(
        '<div class="record" id="record-abc">New location</div>', encoding='utf-8')
    (current / '_geracao.json').write_text(
        json.dumps({'table_annexes': {}}), encoding='utf-8')

    result = compare_reports(previous, current)
    assert result['record_identities_lost'] == 0
    assert result['old_records'] == result['new_records'] == 1
    assert result['relocated_record_anchors'] == {
        'record-abc': {'before': 'index.html', 'after': 'ia-custos.html'}}
    assert result['pages']['index.html']['missing_record_anchors'] == []


def test_historical_record_disappearance_remains_blocking(tmp_path):
    """P9: a missing record identity must still refuse publication acceptance."""
    import pytest
    from scripts.presentation_acceptance import compare_reports

    previous = tmp_path / 'legacy'
    current = tmp_path / 'current'
    (previous / 'anexos').mkdir(parents=True)
    current.mkdir()
    (previous / 'index.html').write_text(
        '<div class="record" id="record-lost">Old row</div>', encoding='utf-8')
    (current / 'index.html').write_text('<h1>Painel</h1>', encoding='utf-8')

    with pytest.raises(ValueError, match='record identity regression: 1 missing anchors'):
        compare_reports(previous, current)


def test_persisted_reasoning_profile_matches_each_attempt_and_fallback():
    """No inference from console defaults or grouping across provider attempts."""
    from rasai.parallel_report.presentation_labels import public_value
    attempts = [
        {'attempt_id': 'AI-1', 'provider': 'provedor-A', 'model': 'modelo-alto',
         'reasoning_profile': 'HIGH', 'status': 'TECHNICAL_ERROR',
         'estimated_cost': 0.10, 'cost_currency': 'USD'},
        {'attempt_id': 'AI-2', 'provider': 'provedor-B', 'model': 'modelo-padrao',
         'reasoning_profile': 'PROVIDER_DEFAULT', 'status': 'SUCCESS',
         'fallback_reason': 'tentativa alternativa', 'estimated_cost': 0.20, 'cost_currency': 'USD'},
        {'attempt_id': 'AI-3', 'provider': 'provedor-C', 'model': 'modelo-baixo',
         'reasoning_profile': 'LOW', 'status': 'SUCCESS',
         'estimated_cost': 0.30, 'cost_currency': 'USD'},
        {'attempt_id': 'AI-4', 'provider': 'provedor-D', 'model': 'modelo-ausente',
         'status': 'SUCCESS', 'estimated_cost': 0.40, 'cost_currency': 'USD'},
    ]
    remediation = [{
        'attempt_id': 'REM-1', 'provider': 'provedor-E', 'model': 'modelo-minimo',
        'reasoning_profile': 'MINIMAL', 'status': 'SUCCESS',
        'estimated_cost': 0.05, 'cost_currency': 'USD',
    }]
    source = {'ai_provider_attempts': attempts, 'content_remediation_attempts': remediation}
    records, _ = model(source)
    rendered = editorial('ia-custos', records, reconcile(source), load())
    for caption in ('Custo por chamada', 'Preço por tentativa — sem cobrança inferida'):
        assert f'<caption>{caption}</caption>' in rendered
        section = rendered.split(f'<caption>{caption}</caption>', 1)[1].split('</table>', 1)[0]
        assert 'Esforço solicitado' in section
        for model_name, effort in (
            ('modelo-alto', 'Esforço alto solicitado'),
            ('modelo-padrao', 'Padrão do provedor (nível não comprovado)'),
            ('modelo-baixo', 'Esforço baixo solicitado'),
            ('modelo-ausente', 'N/D'),
            ('modelo-minimo', 'Esforço mínimo solicitado'),
        ):
            matches = [row for row in section.split('<tr>') if f'>{model_name}</td>' in row]
            assert len(matches) == 1, (caption, model_name)
            assert effort in matches[0], (caption, model_name, effort)
    assert public_value('NONE', 'reasoning_profile') == 'Sem esforço adicional solicitado'
    assert public_value('XHIGH', 'reasoning_profile') == 'Esforço muito alto solicitado'
    assert public_value('MAX', 'reasoning_profile') == 'Esforço máximo solicitado'
    assert public_value('', 'reasoning_profile').startswith('N/D')
    assert public_value('HIGH', 'unrelated_evidence') == 'HIGH'
    assert attempts[0]['reasoning_profile'] == 'HIGH'


def test_cost_stacks_explain_each_persisted_attempt_without_cat_classification():
    attempts = [
        {'attempt_id': 'AI-SEM', 'provider': 'Provider A', 'model': 'Model A',
         'reasoning_profile': 'HIGH', 'operation': 'SEMANTIC_M7',
         'estimated_cost': 0.40, 'cost_currency': 'USD', 'status': 'SUCCESS'},
        {'attempt_id': 'AI-FALLBACK', 'provider': 'Provider B', 'model': 'Model B',
         'reasoning_profile': 'PROVIDER_DEFAULT', 'operation': 'DIRECTED_ANALYSIS',
         'fallback_reason': 'primeiro provedor indisponível',
         'estimated_cost': 0.60, 'cost_currency': 'USD', 'status': 'SUCCESS'},
    ]
    original = [dict(item) for item in attempts]
    data = {'ai_provider_attempts': attempts}
    records, _ = model(data)
    index = editorial('index', records, reconcile(data), load())
    costs = editorial('ia-custos', records, reconcile(data), load())
    from rasai.parallel_report.presentation_labels import public_value
    assert public_value('SEMANTIC_M7', 'operation') == 'Análise semântica'
    assert public_value('SEMANTIC_M7', 'observed_value') == 'SEMANTIC_M7'
    for html in (index, costs):
        assert 'role="img"' in html
        assert 'tabindex="0"' in html
        assert 'data-explanation=' in html
        assert 'Catálogo de origem não individualizado nesta tentativa' in html
        assert 'Custo estimado persistido: USD 0,4' in html
        assert 'Custo estimado persistido: USD 0,6' in html
        assert '40,0% do total desta moeda' in html
        assert '60,0% do total desta moeda' in html
        assert 'Provider A' in html and 'Model A' in html
        assert 'Provider B' in html and 'Model B' in html
        assert 'Padrão do provedor (nível não comprovado)' in html
        assert 'motivo do fallback: primeiro provedor indisponível' in html
        assert 'Análise semântica' in html
        assert 'SEMANTIC_M7' not in html.split('data-explanation=', 1)[1].split('>', 1)[0]
        assert 'CAT-01' not in html and 'CAT-02' not in html
    assert attempts == original


def test_crosslinks_humanize_persisted_dimension_without_changing_identity():
    """#728: same source-backed public field name in text and accessible label."""
    tables = {'scores': [
        {'score_id': 'S-1', 'dimension': 'DISCOVERY_ACCESS', 'value': 71},
        {'score_id': 'S-2', 'dimension': 'OVERALL_READINESS', 'value': 83},
    ]}
    records, _ = model(tables)
    source, target = records
    before = json.loads(json.dumps(tables))
    html = record_html(source, {source.href: (target.href,)},
                       lookup={record.href: record for record in records})
    links = html.split('<nav aria-label="Referências bidirecionais">', 1)[1].split('</nav>', 1)[0]
    assert 'Índice de Prontidão Search &amp; IA e dimensões' in links
    assert 'Índice de Prontidão Search &amp; IA (SARI)' in links
    assert 'OVERALL_READINESS' not in links
    assert 'DISCOVERY_ACCESS' not in links
    assert 'href="' + target.href + '"' in links
    assert 'aria-label="Detalhe: ' in links
    assert target.anchor in links
    assert tables == before


def test_crosslinks_keep_unmapped_trace_identifiers_but_label_technical_family():
    """Known public vocabulary does not authorize changing source rule IDs."""
    tables = {'rule_executions': [
        {'execution_id': 'R-1', 'rule_id': 'RULE-TECHNICAL-001', 'dimension': 'DISCOVERY_ACCESS'},
        {'execution_id': 'R-2', 'rule_id': 'RULE-TECHNICAL-002', 'dimension': 'CONTENT_VALUE'},
    ]}
    records, _ = model(tables)
    source, target = records
    html = record_html(source, {source.href: (target.href,)},
                       lookup={record.href: record for record in records})
    links = html.split('<nav aria-label="Referências bidirecionais">', 1)[1].split('</nav>', 1)[0]
    assert 'Resultados das regras' in links
    assert 'RULE-TECHNICAL-002' in links
    assert 'Valor do conteúdo' in links
    assert 'CONTENT_VALUE' not in links
    assert 'href="' + target.href + '"' in links

def test_728_governance_card_contextual_labels_do_not_modify_evidence():
    """Only the public summary is interpreted; the persisted enums remain exact."""
    source = {'recommendation_governance': [
        {'governance_id': 'G-ACCEPT', 'decision': 'ACCEPTED',
         'target_class': 'TARGET_SITE', 'rejection_reason': None},
        {'governance_id': 'G-VERIFY', 'decision': 'VERIFY_DECIDE',
         'target_class': 'EXTERNAL_PROVIDER',
         'rejection_reason': 'CANONICAL_PREFERRED_URL_NOT_PROVEN'},
        {'governance_id': 'G-REJECT', 'decision': 'REJECTED',
         'target_class': 'AUDITOR_INTERNAL',
         'rejection_reason': 'AUDITOR_INTERNAL_NOT_CLIENT_ACTION'},
        {'governance_id': 'G-UNKNOWN', 'decision': 'UNCLASSIFIED_DECISION',
         'target_class': 'UNKNOWN_TARGET',
         'rejection_reason': 'UNKNOWN_REASON_CODE'},
    ]}
    original = json.loads(json.dumps(source))
    records, _ = model(source)
    expected = (
        ('Aceita', 'Site / propriedade auditada', 'N/D'),
        ('Verificar / decidir antes de implementar',
         'Fornecedor / dependência externa',
         'URL canônica preferencial não comprovada — decidir antes de implementar'),
        ('Rejeitada', 'Auditor RASAi',
         'Ação interna do auditor — excluída do plano do cliente'),
        ('Condição técnica não catalogada', 'Condição técnica não catalogada',
         'Condição técnica não catalogada'),
    )
    from rasai.parallel_report.annex_payloads import collect_payloads
    for record, (decision, target, reason) in zip(records, expected):
        with collect_payloads() as annexes:
            html = record_html(record, {record.href: ()})
        assert len(annexes) == 1
        raw_annex = next(iter(annexes.values())).decode('utf-8')
        assert record.data['decision'] in raw_annex
        assert record.data['target_class'] in raw_annex
        summary = html.split('<details>', 1)[0]
        for label, value in (('Decisão', decision), ('Alvo', target),
                             ('Motivo', reason)):
            assert '<dt>' + label + '</dt><dd>' + value + '</dd>' in summary
        assert 'UNKNOWN_REASON_CODE' not in summary
        assert 'CANONICAL_PREFERRED_URL_NOT_PROVEN' not in summary
        assert 'VERIFY_DECIDE' not in summary
        assert record.anchor in html
        assert 'Dados persistidos e proveniência' in html
        assert 'anexos/' in html
    assert source == original


def test_728_public_status_reason_uses_typed_copy_and_keeps_annex():
    """Literal reason codes stay verifiable without leaking into status prose."""
    from rasai.parallel_report.annex_payloads import collect_payloads

    cases = (
        ('scores', {'score_id': 'S-KNOWN', 'status': 'NOT_APPLICABLE',
                    'reason': 'SMALL_GROUP_BELOW_NORMAL_MINIMUM'},
         'Não aplicável — Grupo pequeno, abaixo do mínimo normal de amostras'),
        ('scores', {'score_id': 'S-UNKNOWN', 'status': 'PARTIAL',
                    'reason': 'UNRECOGNIZED_INTERNAL_CONDITION'},
         'Parcial — Motivo técnico não catalogado'),
        ('serp_observations', {'observation_id': 'SERP-UNKNOWN',
                              'observation_status': 'PARTIAL',
                              'reason': 'UNRECOGNIZED_SEARCH_CONDITION'},
         'Parcial — Motivo técnico não catalogado'),
        ('scores', {'score_id': 'S-PROSE', 'status': 'FAILED',
                    'reason': 'Amostra incompleta no contexto consultado'},
         'Falhou — Amostra incompleta no contexto consultado'),
    )
    for family, row, expected_status in cases:
        source = {family: [row]}
        before = json.loads(json.dumps(source))
        records, _ = model(source)
        record = records[0]
        with collect_payloads() as annexes:
            html = record_html(record, {record.href: ()})
        public_card = html.split('<details>', 1)[0]
        assert '<p>' + expected_status + '</p>' in public_card
        if row['reason'].startswith('UNRECOGNIZED_'):
            assert row['reason'] not in public_card
        assert record.anchor in html
        assert len(annexes) == 1
        exact_annex = next(iter(annexes.values())).decode('utf-8')
        assert row['reason'] in exact_annex
        assert source == before
