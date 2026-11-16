"""Read-only execution states for the eleven independent presentation pages.

Use only the persisted audit fulfillment contract and work items. This is
operational observability, not a new collector, score, or prediction of success.
Unknown/unrequested/missing evidence are never converted into success or failure.
Untrusted error text and configuration are deliberately not displayed.
"""
from __future__ import annotations

from collections import Counter

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


def build_execution_context(tables, coverage_receipt):
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
            '<p class="rf">Estados derivados do contrato e dos requisitos registrados '
            'nesta auditoria. Etapa concluída não garante que todos os '
            'provedores ou análises complementares tenham produzido resultados.</p>'
        )
        if page == 'index':
            if contract is None:
                html += '<p class="callout w">Contrato de cumprimento não materializado. O status do banco, isoladamente, não comprova conclusão.</p>'
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
                    html += '<p class="callout w">Consolidação não elegível segundo o contrato persistido. Resultados parciais continuam disponíveis, mas não compõem conclusão consolidada.</p>'
        elif contract is None:
            html += '<p class="callout w">Contrato de execução não disponível. Não inferir conclusão, falha ou solicitação com base apenas em tabelas vazias.</p>'
        if values:
            html += table(
                'Requisitos associados a esta página', values,
                [('component', 'Etapa'), ('state', 'Estado persistido'),
                 ('attempts', 'Tentativas'), ('cause', 'Motivo comprovado')],
            )
        elif page != 'index':
            html += '<p class="rf">Nenhum requisito do contrato foi associado diretamente a esta seção.</p>'
        for note in notes:
            html += '<p class="callout w">' + text(note) + '</p>'
        html += '</section>'
        supplemental[page + ':execution'] = html
    return supplemental, records
