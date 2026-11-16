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
    assert 'Contrato de cumprimento não materializado' in html['index:execution']
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
