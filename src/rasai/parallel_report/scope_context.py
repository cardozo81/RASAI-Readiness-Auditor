"""Human interpretation of persisted observations, with their denominators and limits."""
import sqlite3
from collections import Counter, defaultdict
from types import SimpleNamespace

from rasai.ai_economic_telemetry import known_token_subtotal
from rasai.catalog_report_search_trust import (
    _overview_values, _overview_references, _raw_serp_artifact, _target_hosts, overview_citation,
)
from rasai.network_active_probe import read_authorized_probes
from .components import kv, text
from .presentation_labels import public_value
from .read_model import SEARCH_PAGE
from .sanitization import sanitize


def subsection(title, pairs, note=''):
    return '<details open><summary>' + text(title) + '</summary>' + kv(pairs) + (
        '<p>' + text(note) + '</p>' if note else '') + '</details>'


def search_context(root, tables):
    html = ''
    target_hosts = _target_hosts(SimpleNamespace(targets=[
        r.get('normalized_origin') for r in tables.get('audit_targets', ())]))
    for row in tables.get('serp_observations', ()):
        values = _overview_values(_raw_serp_artifact(root / 'audit.db', row))
        html += subsection('AI Overview na consulta observada', [
            ('Consulta', row.get('query')), ('Marcador do provedor', 'Detectado' if values else 'N/D'),
            ('Referências identificáveis', len(_overview_references(values)) if values else None),
            ('Citação do alvo na lista', overview_citation(values, target_hosts))],
            'Sem lista suficiente, a citação fica indeterminada. Resultados orgânicos representam a profundidade consultada.')
    for row in tables.get('geo_observation_runs', ()):
        projection = row.get('projection_json')
        if not isinstance(projection, dict):
            continue
        overlap = projection.get('descriptive_overlap') or {}
        context = projection.get('comparability') or {}
        target = projection.get('target_observation') or {}
        status = target.get('status')
        html += subsection('Comparação observada por execução de pesquisa', [
            ('Execução Search API', row.get('perplexity_run_id')), ('Consultas', projection.get('queries')),
            ('Fontes devolvidas', projection.get('source_count')),
            ('Alvo nas fontes', 'Ausente nas fontes devolvidas' if status == 'TARGET_NOT_IN_RETURNED_SOURCES' else status),
            ('URLs da SERP', overlap.get('serp_denominator')), ('URLs da Search API', overlap.get('perplexity_denominator')),
            ('URLs em comum', overlap.get('common_urls')), ('Intervalo entre medições (s)', context.get('time_gap_seconds')),
            ('Equivalência de intenção comprovada', {True: 'Sim', False: 'Não'}.get(context.get('intent_equivalence_proven'))),
            ('Equivalência de mercado, idioma, dispositivo e tempo comprovada', {True: 'Sim', False: 'Não'}.get(context.get('geo_language_device_time_equivalence_proven')))],
            'Busca externa não determina citação generativa. A coincidência de termos não estabelece equivalência entre os universos.')
    return html


def editorial_evidence(root, tables):
    from rasai.contextual_advisory import load_projection
    snapshots = tables.get('page_snapshots', ())
    if not any(r.get('rendered_artifact_ref') or r.get('raw_artifact_ref') for r in snapshots):
        return ''
    try:
        projection = load_projection(root, ai='none')
    except (OSError, ValueError, sqlite3.Error):
        return '<p>Qualificação editorial da captura indisponível (N/D).</p>'
    faq = projection.get('faq_aria_v3', {}).get('counts', {})
    semantic = projection.get('semantic_v2', {}).get('counts', {})
    review = projection.get('reverse_review', {}).get('counts', {})
    return subsection('FAQ ARIA e decisão editorial na captura', [
        ('Controles observados', faq.get('controls')), ('Respostas presentes no DOM', faq.get('answer_present')),
        ('Painéis não observados', faq.get('not_observed_nd')), ('Ambíguos', faq.get('ambiguous')),
        ('Contextos qualificados v2', semantic.get('qualified')), ('Verificações editoriais', review.get('verification_tasks')),
        ('Ações qualificadas v2', review.get('actionable_v2')), ('Histórico sem ação', review.get('historical_non_actionable')),
        ('Histórico indeterminado', review.get('historical_undetermined'))],
        'A captura descreve o DOM em um instante. Um painel não observado não prova ausência de resposta após interação. O histórico v1 não autoriza uma intervenção v2.')


def scope_context(root, raw_tables, timezone_name, costs):
    tables = {name: sanitize(rows) for name, rows in raw_tables.items() if name in {
        'audit_targets', 'serp_observations', 'geo_observation_runs', 'perplexity_search_runs',
        'audits', 'audit_fulfillment_contracts', 'page_snapshots', 'synthetic_apdex_summaries',
        'synthetic_ux_apdex_summaries', 'synthetic_apdex_runs', 'synthetic_ux_apdex_runs',
        'passive_security_runs', 'passive_security_findings', 'passive_security_script_observations',
        'web_performance_observations', 'directed_analysis_runs', 'scores',
        'ai_provider_attempts', 'content_remediation_attempts', 'improvement_intelligence_recommendations'}}
    result = defaultdict(str)
    audit = next(iter(tables.get('audits', ())), {})
    local = lambda stamp: public_value(stamp, 'captured_at', timezone_name)
    result[SEARCH_PAGE] = search_context(root, tables)
    result['conteudo'] = editorial_evidence(root, tables)
    if result['conteudo']:
        result['conteudo'] += kv([('Instante da captura · ' + str(row.get('device') or 'N/D'), local(row.get('captured_at')))
                                  for row in tables.get('page_snapshots', ())])
    for contract in tables.get('audit_fulfillment_contracts', ()):
        result['index'] += subsection('Fechamento e pendências', [
            ('Processamento', contract.get('processing_status')), ('Relatório', contract.get('report_status')),
            ('Pontuação', contract.get('score_status')), ('Itens pendentes', contract.get('pending_items'))])
    events = [('Início da auditoria-base', local(audit.get('started_at'))), ('Fim da auditoria-base', local(audit.get('completed_at')))]
    for snap in tables.get('page_snapshots', ()):
        events.append(('Captura · ' + str(snap.get('device') or 'N/D'), local(snap.get('captured_at'))))
    for run in tables.get('perplexity_search_runs', ()):
        events.append(('Consulta Search API', local(run.get('started_at'))))
    probes = read_authorized_probes(root, audit.get('audit_id')) if audit.get('audit_id') else []
    if not probes:
        result['performance'] += '<p>Sonda complementar verificável indisponível (N/D).</p>'
    for probe in probes:
        stamp = local(probe.get('capture_utc'))
        events.append(('Sonda de rede complementar', stamp))
        metrics = probe.get('metrics', {})
        pairs = [('Origem da medição', probe.get('measurement_origin')), ('Instante da sonda', stamp)]
        for field, label in [('dns_elapsed_ms', 'DNS'), ('tcp_handshake_ms', 'TCP'), ('tls_handshake_ms', 'TLS')]:
            pairs.append((label + ' (ms)', public_value((metrics.get(field) or {}).get('value'))))
        result['performance'] += subsection('Sonda complementar de rede', pairs + [('SHA-256', probe.get('sha256'))],
            'A sonda descreve o caminho e o instante observados. Ela não mede a experiência de toda a população.')
    result['index'] += subsection('Cronologia das fontes · ' + timezone_name, events,
        'Os complementos conservam seus próprios instantes. O fim da auditoria-base é o registrado no banco.')
    if tables.get('passive_security_runs'):
        result['performance'] += kv([('Scripts observados na captura passiva', len(tables.get('passive_security_script_observations', ())) if 'passive_security_script_observations' in tables else None)])
    for family, title in [('synthetic_apdex_summaries', 'Navegação'), ('synthetic_ux_apdex_summaries', 'Experiência')]:
        run = next(iter(tables.get(family.replace('_summaries', '_runs'), ())), {})
        configuration = run.get('configuration')
        configuration = configuration if isinstance(configuration, dict) else {}
        boundary = (configuration.get('measurement_contract') or {}).get('version')
        for row in tables.get(family, ()):
            result['performance'] += subsection('Distribuição Apdex · ' + title, [
                ('Dispositivo', 'Agregado dos dispositivos do baseline de experiência' if family == 'synthetic_ux_apdex_summaries' and row.get('device') == 'POPULATION' else row.get('device')), ('Perfil', row.get('profile_id')),
                ('Amostras válidas', row.get('valid_samples')), ('Meta', row.get('target_samples', run.get('target_valid_samples'))),
                ('Satisfeitas', row.get('satisfied_count')), ('Toleráveis', row.get('tolerating_count')),
                ('Frustradas', row.get('frustrated_count')), ('p95 (ms)', row.get('p95_ms')),
                ('Fronteira satisfeita (s)', run.get('satisfied_threshold_seconds', run.get('threshold_seconds'))),
                ('Fronteira frustrada (s)', run.get('frustrated_threshold_seconds', run.get('frustration_seconds'))),
                ('Escopo dos erros', run.get('error_scope')), ('Fronteira temporal declarada', boundary)],
                ' '.join(filter(None, [
                    'Grupo pequeno; o mínimo metodológico normal é 100 amostras válidas.' if row.get('small_group') else '',
                    'A UAD mede o carregamento inicial e XHR/fetch iniciado antes de loadEventEnd. Interações SPA posteriores ficam fora dessa fronteira.' if boundary == 'UAD-BOUNDARY-001' else '',
                ])))
    for row in tables.get('web_performance_observations', ()):
        fields = [('lighthouse_version','Versão Lighthouse'), ('device','Dispositivo'), ('fcp_lab_ms','FCP (ms)'),
                  ('speed_index_lab_ms','Speed Index (ms)'), ('tbt_lab_ms','TBT (ms)'), ('cls_lab','CLS de laboratório')]
        result['performance'] += subsection('Laboratório por observação', [(label, row.get(key)) for key, label in fields])
    for run in tables.get('directed_analysis_runs', ()):
        pairs = [('Inventário de ações', run.get('actions_count')), ('Ações analisadas por IA', run.get('ai_actions_count'))]
        for phase in run.get('roadmap_json') or ():
            if isinstance(phase, dict) and isinstance(phase.get('action_ids'), list):
                pairs.append((phase.get('phase'), len(phase['action_ids'])))
        result['plano'] += subsection('Fases do inventário estratégico', pairs, 'Contagens por fase do roteiro original. A decisão de governança determina a elegibilidade no plano.')
    attempts = tables.get('ai_provider_attempts', []) + tables.get('content_remediation_attempts', [])
    if attempts:
        pairs = []
        for field, label in [('input_tokens','Entrada'), ('cached_input_tokens','Entrada em cache'), ('output_tokens','Saída'), ('reasoning_tokens','Raciocínio'), ('total_tokens','Total')]:
            subtotal, count = known_token_subtotal(attempts, field)
            pairs.append((f'Tokens · {label} ({count}/{len(attempts)} com valor)', subtotal))
        pairs.append(('Tentativas com custo conciliado / total', f"{sum(e.get('amount') is not None for e in costs['entries'])}/{costs['attempt_count']}"))
        result['ia-custos'] += '<p>A duração por tentativa mede uma chamada. Etapas de execução, esperas e requisições HTTP podem se sobrepor; seus intervalos não devem ser somados como duração da auditoria.</p>'
        result['ia-custos'] += subsection('Consumo conhecido e cobertura', pairs, 'Cache integra a entrada. Raciocínio integra a saída. Valores ausentes permanecem desconhecidos.')
    if 'passive_security_findings' in tables and tables.get('passive_security_runs'):
        findings = tables['passive_security_findings']
        counts = Counter(r.get('severity') for r in findings)
        correlated = {r.get('finding_id') for r in tables.get('improvement_intelligence_recommendations', ())
                      if r.get('domain') == 'SECURITY' and r.get('finding_id')}
        if correlated:
            result['seguranca'] += kv([('Achados com recomendação consultiva vinculada / observados',
                                        f"{sum(r.get('finding_id') in correlated for r in findings)}/{len(findings)}")])
        result['seguranca'] += subsection('Severidade dos achados passivos', [(s,counts[s]) for s in ('CRITICAL','HIGH','MEDIUM','LOW','INFO')],
            'A distribuição descreve apenas o escopo observado. A análise consultiva não valida a ausência de vulnerabilidades.')
    versions = sorted({str(r['scoring_version']) for r in tables.get('scores', ()) if r.get('scoring_version')})
    result['indices'] += subsection('Como interpretar os índices', [('Versão da pontuação', ', '.join(versions) or None)],
        'As observações alimentam regras, dimensões e um índice. Cobertura e confiança qualificam a interpretação. O índice não certifica WCAG e não prevê ranking ou indexação.')
    result['descoberta'] += '<p>llms.txt é experimental. A ausência de robots.txt não justifica correção automática. IndexNow exige evidência própria; a decisão de adoção cabe ao responsável.</p>'
    return result
