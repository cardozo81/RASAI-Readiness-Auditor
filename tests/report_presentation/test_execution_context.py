"""Regressions for operational limitations on all 11 independent HTML pages.

Only the persisted fulfillment contract and work-item states may establish a
cause. Missing analytical data is not an affirmative, executed result.
"""
from rasai.parallel_report.execution_context import build_execution_context
from rasai.parallel_report.read_model import PAGES, SEARCH_PAGE


def sample_partial_contract():
    return {
        'audits': [{'audit_id': 'AUD-TEST', 'status': 'FAILED'}],
        'audit_fulfillment_contracts': [{
            'processing_status': 'PARTIAL_RETRYABLE', 'score_status': 'PENDING',
            'report_status': 'PRELIMINARY', 'consolidation_eligible': 0,
            'successful_items': 5, 'required_items': 10, 'pending_items': 5,
            'blocked_items': 0,
        }],
        'audit_fulfillment_work_items': [
            {'component': 'CORE_AUDIT', 'status': 'PENDING', 'attempt_count': 0},
            {'component': 'DISCOVERY_ACQUISITION', 'status': 'SUCCESS', 'attempt_count': 1},
            {'component': 'WEB_PERFORMANCE', 'status': 'SUCCESS', 'attempt_count': 1},
            {'component': 'SYNTHETIC_APDEX', 'status': 'SUCCESS', 'attempt_count': 1},
            {'component': 'EXPERIENCE_APDEX', 'status': 'SUCCESS', 'attempt_count': 1},
            {'component': 'SEARCH_INTELLIGENCE', 'status': 'SUCCESS', 'attempt_count': 1},
            {'component': 'PASSIVE_SECURITY', 'status': 'REQUESTED_NOT_EXECUTED',
             'attempt_count': 0, 'last_error_code': 'PLANNED_WORK_NOT_EXECUTED',
             'last_error_message': 'internal diagnostic text that must not appear'},
            {'component': 'TECHNICAL_AI', 'status': 'REQUESTED_NOT_EXECUTED',
             'attempt_count': 0, 'last_error_code': 'PLANNED_WORK_NOT_EXECUTED'},
            {'component': 'CONTENT_REMEDIATION_AI', 'status': 'REQUESTED_NOT_EXECUTED',
             'attempt_count': 0, 'last_error_code': 'PLANNED_WORK_NOT_EXECUTED'},
            {'component': 'IMPROVEMENT_INTELLIGENCE', 'status': 'NOT_CONFIGURED',
             'attempt_count': 0, 'last_error_code': 'AI_NOT_CONFIGURED',
             'last_error_message': 'password: secret-not-to-print'},
        ],
        'rule_executions': [{} for _ in range(27)],
        'findings': [{} for _ in range(2)],
        'passive_security_resources': [{} for _ in range(87)],
        'passive_security_integrations': [{} for _ in range(5)],
        'serp_observations': [{}],
        'console_cost_forecast_outcomes': [{}],
    }


def receipt_with_network():
    return {'pages': {
        page + '.html': {
            'evidence_state': 'COM_REGISTROS_PERSISTIDOS',
            **({'verified_network_observations': 1, 'verified_network_probes': 0}
               if page == 'rede' else {}),
        } for page, _ in PAGES
    }}


def test_partial_audit_explains_proven_pending_execution_on_each_relevant_page():
    html, receipt = build_execution_context(sample_partial_contract(), receipt_with_network())
    assert len(receipt['pages']) == len(PAGES) == 11
    assert len(html) == 11
    assert receipt['certifies_collection_completeness'] is False
    for page, _ in PAGES:
        body = html[page + ':execution']
        assert body.count('data-execution-page="' + page + '"') == 1
        assert 'Situação da execução e limites dos resultados' in body
        assert 'report-catalog/' not in body
        assert 'secret-that-must-not-appear' not in body
        assert 'secret-not-to-print' not in body
        assert 'last_error_message' not in body

    index = html['index:execution']
    assert 'Parcial, com requisitos recuperáveis' in index
    assert '5 / 10' in index
    assert 'Preliminar' in index
    assert 'Consolidação não elegível' in index

    indices = html['indices:execution']
    assert '27 regras possuem resultado persistido' in indices
    assert 'consolidação dos índices não foi registrada' in indices
    assert 'Pendente' in indices

    security = html['seguranca:execution']
    assert 'Solicitado, não executado' in security
    assert 'Execução encerrada antes de uma tentativa efetiva' in security
    assert '87 recurso(s) e 5 integração(ões)' in security
    assert 'não são vulnerabilidades' in security
    assert '0</td>' in security

    search = html[SEARCH_PAGE + ':execution']
    assert 'Concluído' in search
    assert 'nenhuma execução de pesquisa Perplexity registrada' in search
    assert 'Nenhuma projeção GEO contextual persistida' in search

    plan = html['plano:execution']
    assert 'Solicitado, não executado' in plan
    assert 'Não configurado' in plan
    assert 'Nenhum provedor de IA apto configurado' in plan
    assert 'Nenhuma ação ou proposta de remediação persistida' in plan

    ai = html['ia-custos:execution']
    assert 'Existe previsão financeira persistida' in ai
    assert 'não há tentativa de IA registrada' in ai

    network = html['rede:execution']
    assert '1 captura(s) passiva(s)' in network
    assert 'nenhuma sonda complementar persistida' in network

    content = html['conteudo:execution']
    assert '2 achado(s) disponível(is)' in content
    assert 'Nenhuma proposta JSON-LD persistida' in content


def test_absent_contract_never_implies_complete_or_failure():
    rows = {'audits': [{'status':'FAILED'}]}
    html, receipt = build_execution_context(rows, receipt_with_network())
    assert receipt['contract_available'] is False
    assert 'Critérios de conclusão da auditoria não registrados' in html['index:execution']
    assert 'Contrato de cumprimento' not in html['index:execution']
    assert 'Sem requisito registrado' in html['seguranca:execution']
    assert 'Não inferir conclusão, falha ou solicitação' in html['seguranca:execution']
    assert 'Solicitado, não executado' not in html['seguranca:execution']
    assert 'Concluída' not in html['index:execution']


def test_status_reason_must_be_canonical_and_never_leak_raw_error():
    rows = sample_partial_contract()
    for task in rows['audit_fulfillment_work_items']:
        if task['component'] == 'PASSIVE_SECURITY':
            task['last_error_code'] = 'ANY_SECRET_CODE_NOT_WHITELISTED'
            task['last_error_message'] = 'sk-unsafe-token-that-must-not-be-published'
            task['status'] = '<script>alert(1)</script>'
    html, receipt = build_execution_context(rows, receipt_with_network())
    body = html['seguranca:execution']
    assert '<script>' not in body and 'alert(1)' not in body
    assert 'ANY_SECRET_CODE_NOT_WHITELISTED' not in body
    assert 'sk-unsafe-token' not in body
    assert 'Execução encerrada antes de uma tentativa efetiva' not in body
    assert 'Estado não classificado' in body
    assert receipt['pages']['seguranca.html']['components'][0]['state'] == 'UNKNOWN'


def test_multiple_work_items_for_one_component_are_counted_without_discarding_state():
    rows = sample_partial_contract()
    rows['audit_fulfillment_work_items'].append({
        'component':'PASSIVE_SECURITY',
        'status':'SUCCESS', 'attempt_count':1,
        'last_error_code':None,
    })
    html, receipt = build_execution_context(rows, receipt_with_network())
    statuses=receipt['pages']['seguranca.html']['components'][0]
    assert statuses['work_items'] == 2
    assert statuses['attempts'] == 1
    assert 'SUCCESS (1)' in statuses['state']
    assert 'REQUESTED_NOT_EXECUTED (1)' in statuses['state']
    assert 'Concluído (1)' in html['seguranca:execution']
    assert 'Solicitado, não executado (1)' in html['seguranca:execution']


def test_only_persisted_rule_result_distribution_is_displayed_not_a_new_score():
    rows = sample_partial_contract()
    rows['rule_executions'] = (
        [{'result':'PASS'} for _ in range(16)]
        + [{'result':'UNKNOWN'} for _ in range(9)]
        + [{'result':'WARNING'} for _ in range(2)]
    )
    body, _ = build_execution_context(rows, receipt_with_network())
    html = body['indices:execution']
    assert 'Resultados das regras, sem recomputar índices' in html
    assert 'Regra atendida' in html
    assert 'Regra com ressalva' in html
    assert 'Resultado da regra não determinado' in html
    assert 'score consolidado' in html
    assert '>16</td>' in html and '>9</td>' in html and '>2</td>' in html
    assert '>89,8<' not in html


def test_passive_resources_and_integrations_are_not_security_findings():
    rows = sample_partial_contract()
    rows['passive_security_resources'] = (
        [{'resource_kind':'IMG','party':'FIRST_PARTY'} for _ in range(46)]
        + [{'resource_kind':'STYLESHEET','party':'FIRST_PARTY'} for _ in range(18)]
        + [{'resource_kind':'SCRIPT','party':'FIRST_PARTY'} for _ in range(6)]
        + [{'resource_kind':'SCRIPT','party':'THIRD_PARTY'} for _ in range(10)]
        + [{'resource_kind':'SCRIPT','party':'INLINE'} for _ in range(2)]
        + [{'resource_kind':'RESOURCE','party':'INLINE'} for _ in range(5)]
    )
    rows['passive_security_integrations']=[
        {'integration_id':'TLS_EXTERNAL','state':'SUCCESS','attempts':1},
        {'integration_id':'THREAT_REPUTATION','state':'NO_DATA','attempts':0},
        {'integration_id':'MDN_OBSERVATORY','state':'NOT_REQUESTED','attempts':0},
    ]
    html, _ = build_execution_context(rows, receipt_with_network())
    body=html['seguranca:execution']
    assert 'Perfil dos recursos da captura' in body
    assert 'Folhas de estilo' in body and 'Imagens' in body
    assert 'Primeira parte' in body and 'Terceira parte' in body
    assert 'Situação das integrações técnicas observadas' in body
    assert 'TLS externo' in body and 'Reputação de ameaças' in body
    assert 'Sem dados' in body and 'Não solicitado' in body
    assert 'não comprovam análise passiva executada' in body


def test_forecast_with_incomplete_execution_does_not_claim_final_spend():
    rows=sample_partial_contract()
    rows['console_cost_forecast_outcomes']=[{
        'currency':'USD', 'expected_cost':0.0411926,
        'actual_cost':0.0, 'status':'NÃO COMPARÁVEL',
        'relation':'unsafe source text should not appear in output',
    }]
    html, _ = build_execution_context(rows, receipt_with_network())
    ai=html['ia-custos:execution']
    assert 'Previsão versus execução registrada' in ai
    assert 'NÃO COMPARÁVEL' in ai
    assert '0,041193' in ai
    assert 'Valor realizado registrado na previsão' in ai
    assert 'Telemetria monetária observada' in ai
    assert 'Não constitui custo final' in ai
    assert 'unsafe source text' not in ai



def test_final_contract_states_are_read_without_promoting_partial_status():
    rows = sample_partial_contract()
    rows['audit_fulfillment_contracts'] = [{
        'processing_status': 'COMPLETE', 'score_status': 'FINAL',
        'report_status': 'FINAL', 'consolidation_eligible': 1,
        'successful_items': 15, 'required_items': 15,
        'pending_items': 0, 'blocked_items': 0,
    }]
    body, _ = build_execution_context(rows, receipt_with_network())
    panel = body['index:execution']
    assert 'Concluída' in panel
    assert panel.count('Final') >= 2
    assert 'Estado não classificado' not in panel
    assert 'Consolidação não elegível' not in panel
    partial, _ = build_execution_context(sample_partial_contract(), receipt_with_network())
    assert 'Preliminar' in partial['index:execution']
    assert 'Pendente' in partial['index:execution']
    assert 'Final' not in partial['index:execution']


def test_financial_forecast_critical_classification_keeps_estimates_distinct():
    rows = sample_partial_contract()
    rows['audit_fulfillment_contracts'][0].update({
        'processing_status': 'COMPLETE', 'score_status': 'FINAL',
        'report_status': 'FINAL', 'consolidation_eligible': 1,
    })
    rows['console_cost_forecast_outcomes'] = [{
        'currency': 'USD', 'expected_cost': 0.0411926,
        'actual_cost': 0.68212442, 'status': 'CRÍTICO',
        'likely_low': 0.03, 'likely_high': 0.09,
        'source': 'local-audit-history',
    }]
    rows['ai_provider_attempts'] = [
        {'attempt_id': 'a1', 'estimated_cost': 0.68212442,
         'observed_cost': None, 'cost_currency': 'USD'},
    ]
    html, _ = build_execution_context(rows, receipt_with_network())
    body = html['ia-custos:execution']
    assert '0,041193' in body
    assert '0,682124' in body
    assert 'CRÍTICO' in body
    assert 'Valor realizado registrado na previsão' in body
    assert 'N/D — sem telemetria monetária nesta moeda' in body
    assert 'Observado até o momento' not in body
    assert 'Não constitui custo final nem cobrança observada pelo provedor' in body
    rows['ai_provider_attempts'][0]['observed_cost'] = 0
    rows['ai_provider_attempts'][0]['observed_cost_currency'] = 'USD'
    with_telemetry, _ = build_execution_context(rows, receipt_with_network())
    assert '1 tentativa(s) com valor observado' in with_telemetry['ia-custos:execution']

def test_financial_snapshot_timestamp_uses_report_timezone_without_mutating_source():
    stamp = '2026-11-17T16:09:25.783348+00:00'
    rows = sample_partial_contract()
    rows['console_cost_forecast_outcomes'] = [{
        'currency': 'USD', 'evaluated_at': stamp, 'expected_cost': 0.1,
        'actual_cost': 0.2, 'status': 'NOT_COMPARABLE',
    }]
    panels, _ = build_execution_context(rows, receipt_with_network(), 'America/Sao_Paulo')
    assert '17/11/2026 13:09:25 (America/Sao_Paulo)' in panels['ia-custos:execution']
    assert stamp not in panels['ia-custos:execution']
    assert rows['console_cost_forecast_outcomes'][0]['evaluated_at'] == stamp
