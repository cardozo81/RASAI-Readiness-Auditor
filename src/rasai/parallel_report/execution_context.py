"""Read-only execution states for the eleven independent presentation pages.

Use only the persisted audit fulfillment contract and work items. This is
operational observability, not a new collector, score, or prediction of success.
Unknown/unrequested/missing evidence are never converted into success or failure.
Untrusted error text and configuration are deliberately not displayed.
"""
from __future__ import annotations

from collections import Counter
from .annex_payloads import table_annex_filename
import json

from .components import text, kv, table
from .presentation_labels import public_value, STATUS_LABELS
from .read_model import PAGES, SEARCH_PAGE

# A component may contextualize more than one page. This is a small status
# receipt, not a copy of the work-item records (already in index.html).
PAGE_COMPONENTS = {
    'index': (),
    'extracao': ('DISCOVERY_ACQUISITION',),
    'descoberta': ('DISCOVERY_ACQUISITION',),
    'indices': ('CORE_AUDIT',),
    'conteudo': ('DISCOVERY_ACQUISITION', 'CONTENT_REMEDIATION_AI',
                 'IMPROVEMENT_INTELLIGENCE'),
    'performance': ('WEB_PERFORMANCE', 'SYNTHETIC_APDEX', 'EXPERIENCE_APDEX'),
    'rede': ('DISCOVERY_ACQUISITION',),
    SEARCH_PAGE: ('SEARCH_INTELLIGENCE',),
    'seguranca': ('PASSIVE_SECURITY',),
    'plano': ('TECHNICAL_AI', 'CONTENT_REMEDIATION_AI',
              'IMPROVEMENT_INTELLIGENCE'),
    'ia-custos': ('TECHNICAL_AI', 'CONTENT_REMEDIATION_AI',
                  'IMPROVEMENT_INTELLIGENCE'),
}

# Cause is only attributed if the persisted machine code proves the cause.
CAUSES = {
    'PLANNED_WORK_NOT_EXECUTED': 'Execução encerrada antes de uma tentativa efetiva.',
    'AI_NOT_CONFIGURED': 'Nenhum provedor de IA apto configurado nesta execução.',
}
KNOWN_STATES = {
    'SUCCESS', 'COMPLETE', 'COMPLETED', 'PENDING', 'REQUESTED_NOT_EXECUTED',
    'NOT_CONFIGURED', 'NOT_REQUESTED', 'FAILED', 'FAILED_RETRYABLE',
    'FAILED_PERMANENT', 'BLOCKED', 'SKIPPED', 'DISABLED', 'IN_PROGRESS',
    'RUNNING', 'PARTIAL', 'NOT_APPLICABLE',
}
CONTRACT_STATES = {
    'PARTIAL_RETRYABLE': 'Parcial, com requisitos recuperáveis',
    'COMPLETE': 'Concluída',
    'COMPLETE_WITH_LIMITATIONS': 'Concluída com limitações',
    'FAILED': 'Falhou',
    'PENDING': 'Pendente',
    'PRELIMINARY': 'Preliminar',
    'FINAL': 'Final',
    'CONSOLIDATED': 'Consolidado',
    'NOT_CONSOLIDATED': 'Não consolidado',
}


def _state(value):
    token = str(value or '').upper()
    if token in CONTRACT_STATES:
        return CONTRACT_STATES[token]
    if token in KNOWN_STATES:
        return STATUS_LABELS.get(token, 'Estado registrado')
    return 'Estado não classificado' if token else 'Estado não informado'


def _safe_token(value, choices):
    token = str(value or '').upper()
    return token if token in choices else 'UNKNOWN'


def _amount(rows, name):
    return len(rows.get(name) or ())


def _notes(page, rows, network):
    notes = []
    count = lambda name: _amount(rows, name)
    if page == 'index':
        if count('rule_executions') and not count('scores'):
            notes.append(
                f"{count('rule_executions')} execuções de regras persistidas; "
                "nenhum índice agregado registrado. Não calcular score no relatório."
            )
    elif page == 'indices':
        if count('rule_executions') and not count('scores'):
            notes.append(
                f"{count('rule_executions')} regras possuem resultado persistido, "
                "mas a consolidação dos índices não foi registrada."
            )
    elif page == 'conteudo':
        if count('findings') and not count('semantic_coherence_assessments'):
            notes.append(
                f"{count('findings')} achado(s) disponível(is); "
                "isso não substitui avaliação de coerência semântica não materializada."
            )
        if not count('jsonld_remediation_suggestions'):
            notes.append(
                "Nenhuma proposta JSON-LD persistida; isso não comprova ausência "
                "de dados estruturados no conteúdo observado."
            )
    elif page == 'rede':
        passive = network.get('verified_network_observations')
        probes = network.get('verified_network_probes')
        if passive and probes == 0:
            notes.append(
                f"{passive} captura(s) passiva(s) verificável(is); nenhuma sonda "
                "complementar persistida. A captura não autoriza inferir rota ou GeoIP."
            )
        elif probes == 0:
            notes.append(
                "Nenhuma sonda complementar persistida. Não há comprovação da "
                "causa: autorização, despacho e execução não são inferidos."
            )
    elif page == SEARCH_PAGE:
        if count('serp_observations'):
            if not count('perplexity_search_runs'):
                notes.append(
                    "Resultados SERP persistidos; nenhuma execução de pesquisa "
                    "Perplexity registrada nesta AUD. Sucesso do componente Search "
                    "não comprova que todas as integrações tenham sido executadas."
                )
            if not count('geo_observation_runs'):
                notes.append(
                    "Nenhuma projeção GEO contextual persistida nesta AUD; "
                    "resultados SERP não equivalem a citações por IA."
                )
    elif page == 'seguranca':
        if not count('passive_security_runs'):
            notes.append(
                f"{count('passive_security_resources')} recurso(s) e "
                f"{count('passive_security_integrations')} integração(ões) "
                "observado(s) na captura, sem execução formal da análise de "
                "segurança passiva. Esses registros não são vulnerabilidades."
            )
        elif not count('passive_security_findings'):
            notes.append(
                "Nenhum achado formal persistido nesta fonte. Interpretar o "
                "resultado somente com a cobertura e o estado da execução."
            )
    elif page == 'plano':
        if not (count('directed_analysis_actions') or
                count('improvement_intelligence_recommendations') or
                count('content_remediation_suggestions')):
            notes.append(
                "Nenhuma ação ou proposta de remediação persistida. "
                "Não gerar plano, prioridade ou aprovação por inferência."
            )
    elif page == 'ia-custos':
        attempts = count('ai_provider_attempts') + count('content_remediation_attempts')
        if not attempts and count('console_cost_forecast_outcomes'):
            notes.append(
                "Existe previsão financeira persistida, mas não há tentativa de "
                "IA registrada. Previsão não equivale a consumo efetivo ou "
                "cobrança observada."
            )
    return notes


def _decision_summaries(page, rows, timezone_name=None):
    """Concise facts for decisions, not a copy of technical rows or new scores."""
    output = ''
    if page == 'indices':
        results = Counter(
            str(row.get('result') or 'UNKNOWN').upper()
            for row in rows.get('rule_executions', ())
            if isinstance(row, dict)
        )
        if results:
            types = {
                'PASS': 'Regra atendida',
                'WARNING': 'Regra com ressalva',
                'FAIL': 'Regra reprovada',
                'UNKNOWN': 'Resultado da regra não determinado',
            }
            summary = [
                {'result': types.get(kind, 'Outro estado de regra'), 'count': count}
                for kind, count in sorted(results.items())
            ]
            output += (
                '<h2>Resultados das regras, sem recomputar índices</h2>'
                '<p class="rf">Distribuição das execuções persistidas; uma regra '
                'atendida não substitui score consolidado, cobertura ou confiança.</p>'
                + table('Distribuição dos resultados das regras', summary,
                        [('result', 'Estado da regra'), ('count', 'Execuções')])
            )
    if page == 'seguranca':
        resources = [
            r for r in rows.get('passive_security_resources', ())
            if isinstance(r, dict)
        ]
        if resources:
            kinds = Counter(str(r.get('resource_kind') or '').upper() for r in resources)
            parties = Counter(str(r.get('party') or '').upper() for r in resources)
            known_kind = {'IMG':'Imagens', 'STYLESHEET':'Folhas de estilo',
                          'SCRIPT':'Scripts', 'RESOURCE':'Outros recursos'}
            known_party = {'FIRST_PARTY':'Primeira parte',
                           'THIRD_PARTY':'Terceira parte', 'INLINE':'Recurso embutido'}
            summary = [
                {'category': 'Recurso: ' + kind, 'count': sum(
                    amount for name, amount in kinds.items()
                    if known_kind.get(name, 'Não classificado') == kind)}
                for kind in sorted(set(known_kind.get(n, 'Não classificado') for n in kinds))
            ]
            summary.extend([
                {'category': 'Origem: ' + party, 'count': sum(
                    amount for name, amount in parties.items()
                    if known_party.get(name, 'Não classificada') == party)}
                for party in sorted(set(known_party.get(n, 'Não classificada') for n in parties))
            ])
            output += (
                '<h2>Perfil dos recursos da captura</h2>'
                '<p class="rf">As categorias abaixo são contagens independentes por '
                'tipo de recurso e relação com a página: não se somam entre si, '
                'não indicam vulnerabilidade, e não comprovam análise passiva executada.</p>'
                + table('Recursos observados, sem conclusões de segurança',
                        summary, [('category','Categoria'),('count','Registros')])
            )
        integrations = [
            r for r in rows.get('passive_security_integrations', ())
            if isinstance(r, dict)
        ]
        if integrations:
            labels = {
                'TLS_EXTERNAL':'TLS externo',
                'THREAT_REPUTATION':'Reputação de ameaças',
                'OSV':'OSV',
                'MDN_OBSERVATORY':'MDN Observatory',
                'CISA_KEV':'CISA KEV',
            }
            states = []
            for row in integrations:
                token = str(row.get('state') or '').upper()
                states.append({
                    'integration': labels.get(
                        str(row.get('integration_id') or '').upper(),
                        'Integração não classificada'
                    ),
                    'state': _state(token) if token in KNOWN_STATES or
                             token in CONTRACT_STATES else
                             ('Sem dados' if token == 'NO_DATA' else
                              'Estado não classificado'),
                    'attempts': row.get('attempts') if type(row.get('attempts')) is int
                                and row['attempts'] >= 0 else None,
                })
            output += (
                '<h2>Situação das integrações técnicas observadas</h2>'
                '<p class="rf">O sucesso pontual de uma integração não comprova '
                'execução integral de segurança passiva. Estados não solicitados '
                'ou sem dados permanecem distintos.</p>'
                + table('Estados das integrações persistidas',
                        states, [('integration','Integração'),
                                 ('state','Estado'),('attempts','Tentativas')])
            )
    if page == 'ia-custos':
        forecasts = [
            r for r in rows.get('console_cost_forecast_outcomes', ())
            if isinstance(r, dict)
        ]
        if forecasts:
            attempts = [
                r for family in ('ai_provider_attempts', 'content_remediation_attempts')
                for r in rows.get(family, ())
                if isinstance(r, dict)
            ]
            result = []
            for row in forecasts:
                currency = row.get('currency')
                currency = currency if currency in {'BRL', 'USD', 'EUR'} else 'N/D'
                estimate = row.get('expected_cost')
                reconciled = row.get('actual_cost')
                status = str(row.get('status') or '').strip().upper()
                financial_class = {
                    'CRÍTICO': 'Crítico',
                    'CRITICO': 'Crítico',
                    'NOT_COMPARABLE': 'Não comparável',
                    'NÃO COMPARÁVEL': 'Não comparável',
                    'COMPARAVEL': 'Comparável',
                    'COMPARÁVEL': 'Comparável',
                }.get(status, 'Estado não classificado')
                # Attempt telemetry and the forecast's reconciled technical amount
                # are different contracts. Never promote an estimate to billing.
                telemetry = [
                    attempt for attempt in attempts
                    if attempt.get('observed_cost') is not None
                    and type(attempt.get('observed_cost')) in (int, float)
                    and attempt.get('observed_cost_currency') == currency
                ]
                result.append({
                    'cutoff': public_value(row.get('evaluated_at'), 'evaluated_at', timezone_name),
                    'currency': currency,
                    'forecast': public_value(estimate, 'estimated_cost')
                                if type(estimate) in (int, float) else 'N/D',
                    'snapshot': public_value(reconciled, 'amount')
                                  if type(reconciled) in (int, float) else 'N/D',
                    'telemetry': (str(len(telemetry)) + ' tentativa(s) com valor observado'
                                  if telemetry else 'N/D — sem telemetria monetária nesta moeda'),
                    'classification': financial_class,
                    'range': (' a '.join(public_value(row.get(k), 'estimated_cost')
                                        if type(row.get(k)) in (int, float) else 'N/D'
                                        for k in ('likely_low', 'likely_high'))),
                    'basis': 'Histórico local de auditorias' if row.get('source') == 'local-audit-history'
                             else 'Consultar proveniência no registro técnico',
                })
            output += (
                '<h2>Previsão versus execução registrada</h2>'
                '<p class="callout w">O instantâneo do console corresponde exclusivamente '
                'à data de avaliação exibida em cada linha. Não constitui custo final nem '
                'cobrança observada pelo provedor. Comparações antigas podem anteceder '
                'outras tentativas e a conclusão do contrato de execução.</p>'
                + table('Comparação financeira, respeitando a cobertura',
                        result, [('cutoff', 'Avaliado em'), ('currency', 'Moeda'), ('forecast', 'Previsão anterior'),
                                 ('snapshot', 'Instantâneo do console na data indicada'),
                                 ('telemetry', 'Telemetria monetária observada'),
                                 ('classification', 'Classificação financeira persistida'),
                                 ('range', 'Faixa provável na moeda indicada'),
                                 ('basis', 'Origem da previsão')])
                + '<p class="rf">A faixa provável e o cenário P90 são referências históricas, '
                  'não garantias ou limites contratuais. Tentativas posteriores ao instantâneo '
                  'devem ser consultadas no ledger persistido, não inferidas deste valor.</p>'
            )
    return output


def build_execution_context(tables, coverage_receipt, timezone_name=None):
    """Return (HTML by page, structured public operational receipt).

    Both artifacts consume the same immutable source rows; no SQL, HTTP, IA,
    network probes or report-catalog HTML reads.
    """
    contract_rows = tables.get('audit_fulfillment_contracts') or []
    work_items = tables.get('audit_fulfillment_work_items') or []
    contract = next((r for r in contract_rows if isinstance(r, dict)), None)
    items_by_component = {}
    for item in work_items:
        if isinstance(item, dict) and isinstance(item.get('component'), str):
            items_by_component.setdefault(item['component'].upper(), []).append(item)

    records = {
        'source': 'audit_fulfillment_contracts/audit_fulfillment_work_items',
        'certifies_collection_completeness': False,
        'contract_available': contract is not None,
        'pages': {},
    }
    supplemental = {}
    for page, _ in PAGES:
        details = []
        for component in PAGE_COMPONENTS.get(page, ()):
            related = items_by_component.get(component, [])
            if not related:
                details.append({
                    'component': component,
                    'state': 'NOT_RECORDED',
                    'attempts': None,
                    'cause': None,
                    'work_items': 0,
                })
                continue
            counts = Counter(_safe_token(row.get('status'), KNOWN_STATES)
                             for row in related)
            attempts = sum(row.get('attempt_count') for row in related
                           if type(row.get('attempt_count')) is int
                           and row['attempt_count'] >= 0)
            causes = sorted({
                CAUSES[str(row.get('last_error_code'))]
                for row in related
                if str(row.get('last_error_code')) in CAUSES
            })
            details.append({
                'component': component,
                'state': ' / '.join(
                    (key + (f' ({n})' if len(related) > 1 else ''))
                    for key, n in sorted(counts.items())
                ),
                'attempts': attempts,
                'cause': ' '.join(causes) if causes else None,
                'work_items': len(related),
            })

        values = []
        for row in details:
            component_name = public_value(row['component'], 'component')
            if row['state'] == 'NOT_RECORDED':
                status_label = 'Sem requisito registrado'
            else:
                status_label = ' / '.join(
                    _state(part.strip().split(' (')[0])
                    + (' (' + part.split(' (', 1)[1] if ' (' in part else '')
                    for part in row['state'].split(' / ')
                )
            values.append({
                'component': component_name,
                'state': status_label,
                'attempts': row['attempts'],
                'cause': row['cause'],
            })

        network = (coverage_receipt.get('pages', {})
                   .get(page + '.html', {}) if page == 'rede' else {})
        notes = _notes(page, tables, network)
        evidence_status = (coverage_receipt.get('pages', {})
                           .get(page + '.html', {}).get('evidence_state'))
        receipts = {
            'components': details,
            'notes': notes,
            'evidence_state': evidence_status,
        }
        records['pages'][page + '.html'] = receipts
        html = (
            '<section class="execution-context" data-execution-page="' + text(page) + '">'
            '<h2>Situação da execução e limites dos resultados</h2>'
            '<p class="rf">Estados derivados dos critérios de execução e dos requisitos registrados '
            'nesta auditoria. Etapa concluída não garante que todos os '
            'provedores ou análises complementares tenham produzido resultados.</p>'
        )
        if page == 'index':
            if contract is None:
                html += '<p class="callout w">Critérios de conclusão da auditoria não registrados. O status do banco, isoladamente, não comprova conclusão.</p>'
            else:
                html += kv([
                    ('Processamento', _state(contract.get('processing_status'))),
                    ('Pontuação', _state(contract.get('score_status'))),
                    ('Publicação do relatório', _state(contract.get('report_status'))),
                    ('Requisitos obrigatórios atendidos',
                     str(contract.get('successful_items') or 0) + ' / '
                     + str(contract.get('required_items') or 0)),
                    ('Requisitos pendentes', contract.get('pending_items')),
                    ('Requisitos bloqueados', contract.get('blocked_items')),
                ])
                if contract.get('consolidation_eligible') is not True and contract.get('consolidation_eligible') != 1:
                    html += '<p class="callout w">Consolidação não elegível segundo os critérios de conclusão registrados. Resultados parciais continuam disponíveis, mas não compõem conclusão consolidada.</p>'
                reprocess = [
                    run for run in tables.get('audit_reprocess_runs', ())
                    if isinstance(run, dict)
                ]
                if reprocess:
                    history = []
                    for run in reprocess:
                        selected = None
                        configuration = run.get('configuration')
                        if isinstance(configuration, str):
                            try:
                                configuration = json.loads(configuration)
                            except (ValueError, TypeError):
                                configuration = None
                        if isinstance(configuration, dict):
                            selected = configuration.get('selected_items')
                        history.append({
                            **{key: run.get(key) for key in (
                                'reprocess_id', 'status', 'attempted_items', 'successful_items',
                                'remaining_items', 'started_at', 'completed_at', 'note'
                            )},
                            'selected_items': selected,
                        })
                    html += ('<details><summary>Histórico de execução — ' +
                             text(len(history)) + ' reprocessamentos</summary>')
                    html += table(
                        'Execuções AUD/RPR persistidas', history,
                        [('reprocess_id', 'Reprocessamento'), ('status', 'Estado'),
                         ('attempted_items', 'Itens tentados'), ('successful_items', 'Itens bem-sucedidos'),
                         ('remaining_items', 'Itens restantes'), ('started_at', 'Início'),
                         ('completed_at', 'Fim'), ('note', 'Nota'),
                         ('selected_items', 'Itens selecionados')], timezone_name=timezone_name)
                    archived = len(tables.get('audit_reprocess_derived_archive') or ())
                    if 'audit_reprocess_derived_archive' in tables:
                        archive_name = table_annex_filename('audit_reprocess_derived_archive')
                        html += ('<p>Registros derivados arquivados: ' + text(archived) +
                                 ' · <a class="tech-link" href="anexos/' + archive_name +
                                 '">Detalhe integral do histórico arquivado</a></p></details>')
                    else:
                        html += ('<p>Registros derivados arquivados: N/D - fonte de '
                                 'histórico arquivado não presente nesta auditoria.</p></details>')

        elif contract is None:
            html += '<p class="callout w">Critérios de execução não disponíveis. Não inferir conclusão, falha ou solicitação com base apenas em tabelas vazias.</p>'
        if page == 'ia-custos':
            html += _decision_summaries(page, tables, timezone_name)
        if values:
            html += table(
                'Requisitos associados a esta página', values,
                [('component', 'Etapa'), ('state', 'Estado persistido'),
                 ('attempts', 'Tentativas'), ('cause', 'Motivo comprovado')],
            )
        elif page != 'index':
            html += '<p class="rf">Nenhum requisito de execução foi associado diretamente a esta seção.</p>'
        for note in notes:
            html += '<p class="callout w">' + text(note) + '</p>'
        if page != 'ia-custos':
            html += _decision_summaries(page, tables, timezone_name)
        html += '</section>'
        supplemental[page + ':execution'] = html
    return supplemental, records
