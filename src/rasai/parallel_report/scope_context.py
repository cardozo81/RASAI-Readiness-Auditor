"""Human interpretation of persisted observations, with their denominators and limits."""
import json
import sqlite3
from collections import Counter, defaultdict
from types import SimpleNamespace

from rasai.ai_economic_telemetry import known_token_subtotal
from rasai.catalog_report_search_trust import (
    _overview_values, _overview_references, _raw_serp_artifact, _target_hosts, overview_citation,
)
from rasai.network_intelligence import build_network_assessment
from rasai.network_map import network_geographic_panel
from rasai.network_active_probe import read_authorized_probes
from rasai.network_observation import snapshots_from_audit
from rasai.network_observation_store import read_network_observations, sidecar_path
from .components import kv, table, text
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
            ('Alvo nas fontes', 'Ausente nas fontes devolvidas' if status == 'TARGET_NOT_IN_RETURNED_SOURCES' else public_value(status, 'domain_status')),
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
    overview = subsection('FAQ ARIA e decisão editorial na captura', [
        ('Controles observados', faq.get('controls')), ('Respostas presentes no DOM', faq.get('answer_present')),
        ('Painéis não observados', faq.get('not_observed_nd')), ('Ambíguos', faq.get('ambiguous')),
        ('Contextos qualificados v2', semantic.get('qualified')), ('Verificações editoriais', review.get('verification_tasks')),
        ('Ações qualificadas v2', review.get('actionable_v2')), ('Histórico sem ação', review.get('historical_non_actionable')),
        ('Histórico indeterminado', review.get('historical_undetermined'))],
        'A captura descreve o DOM em um instante. Um painel não observado não prova ausência de resposta após interação. O histórico v1 não autoriza uma intervenção v2.')
    tasks = (projection.get('reverse_review') or {}).get('tasks') or []
    html = '<section id="editorial-verification"><h2>Verificações editoriais condicionais</h2>'
    html += '<p>Tarefas de validação sustentadas pelo material de captura, não defeitos SEO/GEO comprovados. SPA, FAQ pós-interação, visibilidade e intenção permanecem condicionais.</p>'
    if not isinstance(tasks, list) or not tasks:
        return overview + html + '<p>N/D — nenhuma tarefa de verificação sustentada nesta captura.</p></section>'
    html += '<p>' + text(len(tasks)) + ' tarefa(s) no contrato de revisão da captura.</p>'
    for item in tasks[:64]:
        if not isinstance(item, dict):
            continue
        task = sanitize(item)
        refs = task.get('evidence_refs') or []
        html += '<details><summary>' + text(task.get('title')) + '</summary>'
        html += kv([
            ('Identificação', task.get('task_id')),
            ('Estado', public_value(task.get('status'), 'status')),
            ('Suficiência da evidência', public_value(task.get('evidence_sufficiency'), 'status')),
            ('Motivo observado', task.get('rationale')),
            ('Como validar', task.get('validation')),
            ('Referências total', task.get('evidence_refs_total')),
            ('Referências omitidas na origem', task.get('evidence_refs_omitted')),
        ])
        for ref in refs[:16]:
            if not isinstance(ref, dict):
                continue
            html += kv([
                ('Elemento / trecho observado', ref.get('label')),
                ('Texto observado', ref.get('text')),
                ('Snapshot', ref.get('snapshot_id')),
                ('Ocorrência / heading', ref.get('occurrence_id') or ref.get('heading_id')),
                ('Arquivo fonte', ref.get('source_ref')),
                ('SHA-256 da fonte', ref.get('source_sha256')),
            ])
        html += '</details>'
    if len(tasks) > 64:
        html += '<p>Exibidas 64 verificações de ' + text(len(tasks)) + '; restante permanece no contrato técnico.</p>'
    return overview + html + '</section>'



_NETWORK_METRICS = (
    ('connected_public_ip', 'Endereço público da conexão'),
    ('http_protocol', 'Protocolo HTTP'),
    ('http_status', 'Status HTTP'),
    ('redirect_count', 'Redirecionamentos HTTP'),
    ('dns_resolution', 'Resolução DNS'),
    ('dns_elapsed_ms', 'Consulta DNS (ms)'),
    ('tcp_handshake_ms', 'Conexão TCP (ms)'),
    ('tls_handshake_ms', 'Negociação TLS (ms)'),
    ('tls_protocol', 'Versão TLS'),
    ('traceroute', 'Traceroute'),
    ('asn', 'ASN / operador de rede'),
    ('geoip', 'GeoIP aproximado'),
)
_NETWORK_ERRORS = {
    'DNS_LOOKUP_FAILED': 'Falha DNS registrada no pacote histórico.',
    'DNS_TEMPORARY_FAILURE': 'O resolvedor registrou indisponibilidade temporária.',
    'DNS_NAME_RESOLUTION_FAILED': 'O resolvedor não conseguiu resolver o hostname.',
    'DNS_RESOLVER_OS_ERROR': 'O resolvedor registrou erro de sistema.',
    'TRACE_TIME_BUDGET_EXCEEDED': 'O rastreamento excedeu o limite de tempo; saltos anteriores podem estar preservados.',
    'TRACE_COMMAND_NOT_AVAILABLE': 'Ferramenta local de rastreamento indisponível.',
    'TRACE_COMMAND_FAILED': 'O processo de rastreamento terminou com erro.',
    'TRACE_COLLECTION_FAILED': 'Falha técnica na coleta do rastreamento.',
    'ROUTE_NOT_CONFIRMED': 'Não foi possível confirmar o percurso até o destino.',
}
_NETWORK_ABSENCE = {
    'NO_DNS_CAPTURE': 'A captura passiva não mede a resolução DNS separadamente.',
    'NO_TCP_TIMING_CAPTURE': 'A captura passiva não mede o handshake TCP separadamente.',
    'NO_TLS_TIMING_CAPTURE': 'A captura passiva não mede o handshake TLS separadamente.',
    'NO_ACTIVE_PROBE': 'Não houve sonda ativa vinculada a esta observação.',
    'NO_ENRICHMENT': 'Não houve enriquecimento ASN/GeoIP nesta observação.',
}
_HOP_STATES = {
    'PUBLIC_HOP': 'Resposta pública',
    'PRIVATE_HOP_REDACTED': 'Endereço reservado/oculto',
    'NO_REPLY': 'Sem resposta',
}


def _network_value(key, metric):
    if not isinstance(metric, dict) or metric.get('state') != 'OBSERVED':
        return None
    value = metric.get('value')
    if key == 'asn' and isinstance(value, dict):
        number = value.get('number')
        label = ('AS' + str(number)) if number is not None else 'ASN N/D'
        if value.get('organization'):
            label += ' · ' + str(value['organization'])
        return label
    if key == 'geoip' and isinstance(value, dict):
        parts = []
        if value.get('latitude') is not None and value.get('longitude') is not None:
            parts.append(str(value['latitude']) + '°, ' + str(value['longitude']) + '°')
        if value.get('accuracy_radius_km') is not None:
            parts.append('precisão ±' + str(value['accuracy_radius_km']) + ' km')
        if value.get('source'):
            parts.append('fonte ' + str(value['source']))
        return ' · '.join(parts) or None
    if key == 'traceroute' and isinstance(value, dict):
        hops = value.get('hops') if isinstance(value.get('hops'), list) else []
        reached = 'destino alcançado' if value.get('target_reached') is True else 'caminho completo não confirmado'
        parts = [str(len(hops)) + ' salto(s) registrado(s)', reached]
        if value.get('method'):
            parts.append('método ' + str(value['method']))
        if value.get('probe_protocol'):
            parts.append('protocolo ' + str(value['probe_protocol']))
        if type(value.get('max_hops')) is int:
            parts.append('limite ' + str(value['max_hops']) + ' saltos')
        return ' · '.join(parts)
    if isinstance(value, list):
        return ', '.join(str(item) for item in value[:32])
    return value


def _network_reason(metric):
    if not isinstance(metric, dict):
        return None
    error = metric.get('error')
    if isinstance(error, str) and error:
        return _NETWORK_ERRORS.get(error, 'Falha técnica registrada; código interno não publicado nesta camada.')
    source = metric.get('source')
    if metric.get('state') != 'OBSERVED' and isinstance(source, str):
        return _NETWORK_ABSENCE.get(source)
    return None


def _network_metric_rows(observations, probes, timezone_name):
    rows = []
    for index, item in enumerate(observations, 1):
        metrics = item.get('metrics') if isinstance(item, dict) else None
        if not isinstance(metrics, dict):
            continue
        context = str(item.get('device') or ('Captura ' + str(index)))
        stamp = public_value(item.get('capture_utc'), 'captured_at', timezone_name)
        for key, label in _NETWORK_METRICS:
            metric = metrics.get(key)
            if not isinstance(metric, dict):
                continue
            rows.append({
                'origin': 'Captura persistida da AUD',
                'context': context,
                'target': item.get('target_host'),
                'captured_at': stamp,
                'indicator': label,
                'state': metric.get('state') or 'INCONCLUSIVE',
                'value': _network_value(key, metric),
                'provenance': metric.get('source') or item.get('measurement_origin'),
                'reason': _network_reason(metric),
            })
    for index, item in enumerate(probes, 1):
        metrics = item.get('metrics') if isinstance(item, dict) else None
        if not isinstance(metrics, dict):
            continue
        context = item.get('series_id') or ('Probe ' + str(index))
        if item.get('port') is not None:
            context = str(context) + ' · porta ' + str(item.get('port'))
        stamp = public_value(item.get('capture_utc'), 'captured_at', timezone_name)
        for key, label in _NETWORK_METRICS:
            metric = metrics.get(key)
            if not isinstance(metric, dict):
                continue
            rows.append({
                'origin': 'Sonda complementar autorizada',
                'context': context,
                'target': item.get('hostname'),
                'captured_at': stamp,
                'indicator': label,
                'state': metric.get('state') or 'INCONCLUSIVE',
                'value': _network_value(key, metric),
                'provenance': metric.get('source') or item.get('measurement_origin'),
                'reason': _network_reason(metric),
            })
    return sanitize(rows)


def _network_hop_rows(probes, timezone_name):
    rows = []
    for item in probes:
        metrics = item.get('metrics') if isinstance(item, dict) else None
        trace = metrics.get('traceroute') if isinstance(metrics, dict) else None
        value = trace.get('value') if isinstance(trace, dict) and trace.get('state') == 'OBSERVED' else None
        hops = value.get('hops') if isinstance(value, dict) else None
        if not isinstance(hops, list):
            continue
        stamp = public_value(item.get('capture_utc'), 'captured_at', timezone_name)
        for hop in hops[:16]:
            if not isinstance(hop, dict) or type(hop.get('hop')) is not int:
                continue
            enrichment = hop.get('enrichment') if isinstance(hop.get('enrichment'), dict) else {}
            rows.append({
                'captured_at': stamp,
                'target': item.get('hostname'),
                'hop': hop.get('hop'),
                'hop_state': _HOP_STATES.get(hop.get('state'), 'Estado não determinado'),
                'public_ip': hop.get('public_ip') if hop.get('state') == 'PUBLIC_HOP' else None,
                'rtt_ms': hop.get('rtt_ms'),
                'rtt_samples': hop.get('rtt_samples_ms'),
                'asn': _network_value('asn', enrichment.get('asn')),
                'geoip': _network_value('geoip', enrichment.get('geoip')),
            })
    return sanitize(rows)


def network_context(root, audit_id, timezone_name):
    if not audit_id:
        return ('<p class="callout">Identidade da AUD indisponível; dados de rede permanecem N/D.</p>',
                [], '<p class="callout">Sem Audit ID verificável; inventário de rede indisponível.</p>')
    packet = sidecar_path(root)
    packet_present = packet.exists() or packet.is_symlink()
    observations = read_network_observations(root, audit_id)
    if not observations and not packet_present:
        database = root / 'audit.db'
        if database.is_file() and not database.is_symlink():
            try:
                observations = snapshots_from_audit(database, audit_id)
            except (OSError, ValueError, TypeError, sqlite3.Error):
                observations = []
    probes = read_authorized_probes(root, audit_id)
    events = [('Sonda de rede complementar',
               public_value(item.get('capture_utc'), 'captured_at', timezone_name))
              for item in probes]

    html = '<h2>Escopo e proveniência de rede</h2>' + kv([
        ('Capturas passivas verificadas', len(observations)),
        ('Sondas complementares autorizadas', len(probes)),
        ('Regra de interpretação', 'ausência de medição não é falha de conectividade'),
        ('Mapa e rota visual', 'detalhe técnico no report-catalog quando materializado'),
    ])
    html += ('<p class="callout w">Captura do navegador e sonda complementar são observações independentes, '
             'potencialmente feitas em instantes e ambientes diferentes. IP, rota e tempos não são inferidos entre elas.</p>')
    if packet_present and not observations:
        html += ('<p class="callout w">Existe pacote de observação passiva, mas ele não foi validado para esta AUD. '
                 'Nenhum valor desse pacote é apresentado.</p>')
    if not observations:
        html += '<p>Captura passiva de rede verificável indisponível (N/D).</p>'
    if not probes:
        html += '<p>Sonda complementar verificável indisponível (N/D). Isso não demonstra falha de conectividade.</p>'

    metric_rows = _network_metric_rows(observations, probes, timezone_name)
    html += '<h2>Indicadores observados</h2>' + table(
        'Rede · fatos persistidos por origem', metric_rows,
        [('origin', 'Origem'), ('context', 'Contexto'), ('target', 'Destino'),
         ('captured_at', 'Instante'), ('indicator', 'Indicador'), ('state', 'Estado'),
         ('value', 'Valor'), ('provenance', 'Fonte'), ('reason', 'Motivo / limite')])
    hop_rows = _network_hop_rows(probes, timezone_name)
    if hop_rows:
        html += '<h2>Etapas conhecidas do caminho</h2>' + table(
            'Traceroute · saltos persistidos', hop_rows,
            [('captured_at', 'Instante'), ('target', 'Destino'), ('hop', 'Salto'),
             ('hop_state', 'Situação'), ('public_ip', 'Endereço público'),
             ('rtt_ms', 'RTT (ms)'), ('rtt_samples', 'Amostras RTT'),
             ('asn', 'ASN'), ('geoip', 'GeoIP aproximado')])
    # Reuse the established offline map with exactly the verified probe objects.
    # Missing coordinates produce an explicit explanation, never a synthetic route.
    map_html = network_geographic_panel(probes)
    has_map = '<h2>Mapa geográfico consultivo</h2>' in map_html
    map_html = map_html.replace("<section class='panel'>",
                                "<section class='panel' id='network-map'>", 1)
    html += map_html
    html += '<h2>Diagnóstico consultivo determinístico</h2>'
    # Use the *same* pure evidence-bound assessor as the technical network report.
    # No new probe, geocoding, AI call, scoring or inferred causal relationship.
    try:
        assessment = sanitize(build_network_assessment(root, audit_id))
    except (ValueError, OSError, TypeError, KeyError, sqlite3.Error):
        assessment = None
    if assessment is None:
        html += '<p>N/D — evidências de rede insuficientes ou não verificáveis para diagnóstico.</p>'
    else:
        coverage = assessment.get('coverage') or {}
        html += kv([
            ('Método', public_value(assessment.get('analysis_method'), 'analysis_method')),
            ('Escopo da confiança', public_value(assessment.get('confidence_scope'), 'confidence_scope')),
            ('Justificativa da confiança', assessment.get('confidence_explanation')),
            ('Capturas verificadas', coverage.get('audit_captures')),
            ('Sondas autorizadas', coverage.get('authorized_probes')),
            ('Amostras DNS / TCP / TLS',
             ' / '.join(str(coverage.get(k, 'N/D')) for k in ('dns_samples', 'tcp_samples', 'tls_samples'))),
        ])
        conclusions = assessment.get('findings') or []
        html += table('Conclusões, evidências e validação', conclusions,
                      [('title', 'Tema'), ('conclusion', 'Conclusão'),
                       ('confidence', 'Confiança pontual'), ('evidence_refs', 'IDs da evidência'),
                       ('limitation', 'Limitação causal'), ('recommendation', 'Próxima ação'),
                       ('validation', 'Como validar')])
        html += '<p class="rf">Conclusões são limitadas às sessões e ao ambiente medido; não demonstram rota física, causa de lentidão, disponibilidade global nem efeito em SEO/GEO.</p>'
    html += ('<p class="rf">O mapa acima usa somente coordenadas documentadas em sondas '
             'autorizadas. Não há dependência do catálogo técnico, nem inferência de '
             'topologia ou localização física dos equipamentos.</p>')
    map_status = ('Mapa geográfico aproximado disponível com coordenadas verificadas'
                  if has_map else 'Mapa indisponível: nenhuma coordenada verificável persistida')
    hop_status = ('Etapas de rede registradas em sondas autorizadas'
                  if hop_rows else 'Nenhum salto de rede verificável registrado')
    modal = (
        '<dialog class="detail-dialog" id="network-context-modal" aria-labelledby="network-context-title">'
        '<div class="modal-head"><div><span class="modal-kicker">Rede e conectividade</span>'
        '<h2 id="network-context-title">Detalhes da medição de rede</h2></div>'
        '<button type="button" class="modal-close" data-modal-close aria-label="Fechar detalhes">×</button></div>'
        '<div class="modal-body"><p>Esta explicação resume o alcance das evidências de rede '
        'registradas. Valores por medição, fontes e limitações permanecem nas tabelas e '
        'no inventário desta apresentação, sem repetição integral aqui.</p>'
        + kv([
            ('Capturas passivas verificadas', len(observations)),
            ('Sondas autorizadas', len(probes)),
            ('Rastreamento do caminho', hop_status),
            ('Representação geográfica', map_status),
            ('Limite', 'Coordenadas de IP são estimativas; não comprovam rota física.'),
        ]) +
        '<p><a class="tech-link" href="#network-map">Consultar mapa e sua disponibilidade</a></p>'
        '<p><a class="tech-link" href="#network-evidence-inventory">Consultar fontes e registros locais</a></p>'
        '</div><div class="modal-foot">'
        '<button type="button" class="modal-dismiss" data-modal-close>Fechar</button>'
        '</div></dialog>'
    )
    html += modal
    inventory = (
        '<p class="rf">Fontes locais verificadas: capturas passivas persistidas '
        '(sidecar validado ou projeção do audit.db histórico) e sondas complementares '
        'autorizadas. Os registros abaixo são sanitizados para apresentação; '
        'não representam novas medições nem substituem os artefatos originais.</p>'
    )
    for label, entries in (
        ('Captura passiva verificada', observations),
        ('Sonda complementar autorizada', probes),
    ):
        for position, row in enumerate(entries, 1):
            inventory += (
                '<details><summary>' + text(label) + ' ' + str(position)
                + ' de ' + str(len(entries)) + '</summary><pre>'
                + text(json.dumps(sanitize(row), ensure_ascii=False, indent=2, default=str))
                + '</pre></details>'
            )
    if not observations and not probes:
        inventory += (
            '<p class="callout">Nenhuma captura passiva ou sonda de rede verificável '
            'foi materializada para esta AUD. Ausência de evidência não demonstra '
            'falha de conectividade.</p>'
        )
    return html, events, inventory


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
    review_html = editorial_evidence(root, tables)
    result['conteudo'] = review_html
    if review_html:
        result[SEARCH_PAGE] += ('<h2>Conteúdo observado e condições GEO/SEO</h2>'
                                '<p>As mesmas tarefas de validação editorial estão disponíveis na superfície de conteúdo, '
                                'sem equivaler a medição de ranking ou citação generativa.</p>'
                                + review_html)
    if result['conteudo']:
        result['conteudo'] += kv([('Instante da captura · ' + str(row.get('device') or 'N/D'), local(row.get('captured_at')))
                                  for row in tables.get('page_snapshots', ())])
    for contract in tables.get('audit_fulfillment_contracts', ()):
        result['index'] += subsection('Fechamento e pendências', [
            ('Processamento', public_value(contract.get('processing_status'), 'status')),
            ('Relatório', public_value(contract.get('report_status'), 'status')),
            ('Pontuação', public_value(contract.get('score_status'), 'status')), ('Itens pendentes', contract.get('pending_items'))])
    events = [('Início da auditoria-base', local(audit.get('started_at'))), ('Fim da auditoria-base', local(audit.get('completed_at')))]
    for snap in tables.get('page_snapshots', ()):
        events.append(('Captura · ' + str(snap.get('device') or 'N/D'), local(snap.get('captured_at'))))
    for run in tables.get('perplexity_search_runs', ()):
        events.append(('Consulta Search API', local(run.get('started_at'))))
    network_html, network_events, network_inventory = network_context(root, audit.get('audit_id'), timezone_name)
    result['rede'] += network_html
    result['rede:inventory'] = network_inventory
    events.extend(network_events)
    result['index'] += subsection('Cronologia das fontes · ' + timezone_name, events,
        'Os complementos conservam seus próprios instantes. O fim da auditoria-base é o registrado no banco.')
    if tables.get('passive_security_runs'):
        result['seguranca'] += kv([('Scripts observados na captura passiva', len(tables.get('passive_security_script_observations', ())) if 'passive_security_script_observations' in tables else None)])
    for family, title in [('synthetic_apdex_summaries', 'Navegação'), ('synthetic_ux_apdex_summaries', 'Experiência')]:
        run = next(iter(tables.get(family.replace('_summaries', '_runs'), ())), {})
        configuration = run.get('configuration')
        configuration = configuration if isinstance(configuration, dict) else {}
        boundary = (configuration.get('measurement_contract') or {}).get('version')
        for row in tables.get(family, ()):
            result['performance'] += subsection('Distribuição Apdex · ' + title, [
                ('Dispositivo', 'Agregado dos dispositivos do baseline de experiência' if family == 'synthetic_ux_apdex_summaries' and row.get('device') == 'POPULATION' else public_value(row.get('device'), 'device')), ('Perfil', row.get('profile_id')),
                ('Amostras válidas', row.get('valid_samples')), ('Meta', row.get('target_samples', run.get('target_valid_samples'))),
                ('Satisfeitas', row.get('satisfied_count')), ('Toleráveis', row.get('tolerating_count')),
                ('Frustradas', row.get('frustrated_count')), ('p95 (ms)', row.get('p95_ms')),
                ('Fronteira satisfeita (s)', run.get('satisfied_threshold_seconds', run.get('threshold_seconds'))),
                ('Fronteira frustrada (s)', run.get('frustrated_threshold_seconds', run.get('frustration_seconds'))),
                ('Escopo dos erros', public_value(run.get('error_scope'), 'error_scope')), ('Fronteira temporal declarada', boundary)],
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
        result['seguranca'] += subsection('Severidade dos achados passivos', [(public_value(s,'severity'),counts[s]) for s in ('CRITICAL','HIGH','MEDIUM','LOW','INFO')],
            'A distribuição descreve apenas o escopo observado. A análise consultiva não valida a ausência de vulnerabilidades.')
    versions = sorted({str(r['scoring_version']) for r in tables.get('scores', ()) if r.get('scoring_version')})
    result['indices'] += subsection('Como interpretar os índices', [('Versão da pontuação', ', '.join(versions) or None)],
        'As observações alimentam regras, dimensões e um índice. Cobertura e confiança qualificam a interpretação. O índice não certifica WCAG e não prevê ranking ou indexação.')
    result['descoberta'] += '<p>llms.txt é experimental. A ausência de robots.txt não justifica correção automática. IndexNow exige evidência própria; a decisão de adoção cabe ao responsável.</p>'
    return result
