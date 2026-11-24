"""Page-specific deterministic summaries and receipts of what was projected."""
from collections import Counter, defaultdict
import json
from urllib.parse import urlsplit

from .capture_projection import object_value, public_data, read_source, state_label
from .components import kv, table, text
from .governance import Governance
from .history_projection import crux_history
from .read_model import PAGES, SEARCH_PAGE, destination, thaw
from .presentation_labels import public_value
from .templates import label as public_label


def summaries(root, tables, inventory, records, capture, timezone_name=None):
    html, topics = defaultdict(str), defaultdict(list)
    by_table = defaultdict(list)
    for record in records:
        by_table[record.table].append(record)

    def emit(page, topic, families, body, state=None, sources=(), limitation=None):
        refs = [dict(table=name, record_id=dict(r.identity), href=r.href)
                for name in families for r in by_table[name]]
        quantity = sum(len(tables.get(n, ())) for n in families)
        state = state or ('PRESENT_SUMMARIZED' if quantity else 'SOURCE_ABSENT')
        topics[page].append(dict(topic=topic, state=state, families=list(families),
            records=quantity, sources=refs + list(sources), limitation=limitation))
        html[page] += '<section><h2>' + text(topic) + '</h2>' + body
        links = [by_table[n][0] for n in families if by_table[n]]
        if links:
            html[page] += '<p class="rf">Fontes: ' + ' · '.join(
                '<a class="tech-link" href="' + text(r.href) + '">' + text(public_label(r.table)) + '</a>'
                for r in links) + '.</p>'
        html[page] += '</section>'

    safe = public_data(tables)
    findings = safe.get('findings', ())
    actions = tables.get('directed_analysis_actions', ())
    governance = Governance(tables.get('recommendation_governance', ()))
    approved = sum(governance.disposition('directed_analysis_actions', r) == 'Aceita pela governança'
                   for r in actions)
    categories = Counter(str(r.get('category') or 'N/D') for r in findings)
    finding_body = (kv([('Achados técnicos persistidos', len(findings)),
                       ('Ações dirigidas propostas', len(actions)), ('Ações dirigidas aprovadas', approved)])
        + '<p>Achados, riscos classificados e ações são registros distintos. '
          'A contagem de achados não estabelece prioridade ou aprovação. '
          'Não há classificação adicional de risco produzida nesta apresentação.</p>'
        + (table('Classificação persistida dos achados',
                 [dict(category=k, quantity=v) for k, v in sorted(categories.items())],
                 [('category', 'Categoria de origem'), ('quantity', 'Achados')]) if categories else ''))
    for page in ('index', 'plano'):
        body = finding_body
        if page == 'plano' and findings:
            material = [{**r, '_ref': by_table['findings'][i].href}
                        for i, r in enumerate(findings)]
            body += '<p>Material de análise disponível; nenhuma recomendação, prioridade ou aprovação é criada a partir destes achados.</p>'
            body += table('Achados técnicos informativos — não constituem plano de ação', material,
                          [('title','Título registrado'), ('category','Categoria'), ('status','Estado'),
                           ('source','Origem'), ('evidence_ids','Evidências persistidas'),
                           ('_ref','Registro e limitações da fonte')], inline_details=True)
        emit(page, 'Achados e decisões registradas',
             ('findings', 'directed_analysis_actions', 'recommendation_governance'), body,
             limitation='FINDINGS_DO_NOT_AUTHORIZE_ACTIONS')

    elements = safe.get('element_observations', ())
    evidence = list(safe.get('evidence', ()))
    refs = {r.get('artifact_reference') for r in evidence + list(elements) if r.get('artifact_reference')}
    verified = {r for r in refs if r in inventory}
    tags = Counter(str(r.get('tag_name') or 'N/D').lower() for r in elements)
    body = kv([('Capturas registradas', len(safe.get('page_snapshots', ()))),
               ('Observações de elementos DOM', len(elements)), ('Registros de evidência', len(evidence)),
               ('Arquivos distintos referenciados por elementos/evidências', len(refs)),
               ('Arquivos dessas referências presentes no inventário', len(verified))])
    body += '<p>Elementos DOM são observações estruturais, sem classificação automática como entidades semânticas.</p>'
    if tags:
        body += table('Estrutura DOM observada', [dict(tag=k, quantity=v) for k, v in sorted(tags.items())],
                      [('tag','Elemento'), ('quantity','Observações')])
        body += table('Trechos persistidos dos elementos', [
            dict(tag=r.get('tag_name'), selector=r.get('selector'), excerpt=r.get('text_excerpt'),
                 snapshot=r.get('snapshot_id')) for r in elements],
            [('tag','Elemento'), ('selector','Seletor persistido'), ('excerpt','Texto observado'), ('snapshot','Captura')])
    emit('extracao', 'Síntese factual da extração',
         ('page_snapshots', 'element_observations', 'evidence'), body)

    # Worker structural map, shared by all three pages without recomputation.
    for page in ('extracao', 'conteudo', SEARCH_PAGE):
        body = kv([('Estado da projeção estrutural offline', state_label(capture['state']))])
        for surface in capture.get('content_structure_v3', {}).get('captures', ()):
            title = surface.get('title') or {}
            body += kv([('Título observado no DOM', title.get('text')),
                        ('Headings observados', surface.get('heading_count')),
                        ('Headings omitidos pelo limite', surface.get('headings_omitted')),
                        ('Captura', surface.get('snapshot_id')),
                        ('Fonte', surface.get('source_ref')), ('SHA-256', surface.get('source_sha256'))])
            if surface.get('headings'):
                body += table('Headings capturados · ' + str(surface.get('snapshot_id')), surface['headings'],
                              [('tag','Nível'), ('text','Texto capturado'), ('scope','Escopo estrutural')])
        for snapshot in safe.get('page_snapshots', ()):
            meta = object_value(snapshot.get('browser_metadata'))
            quality = object_value(meta.get('capture_quality'))
            final = object_value(quality.get('final'))
            body += kv([('Canonical persistida', snapshot.get('canonical')),
                        ('Qualidade da captura persistida', state_label(quality.get('state'))),
                        ('Condição do conteúdo capturado', public_value(quality.get('materiality_reason'), 'materiality_reason')),
                        ('Texto no main (caracteres observados)', final.get('main_text_length')),
                        ('Texto primário (caracteres observados)', final.get('primary_text_length'))])
        for sidecar in capture.get('sources', ()):
            if sidecar.get('field') not in {'main_content_ref', 'structured_data_ref'}:
                continue
            body += kv([('Fonte complementar', {'main_content_ref':'Texto principal extraído',
                                               'structured_data_ref':'Dados estruturados extraídos'}.get(sidecar.get('field'))),
                        ('Estado do sidecar', state_label(sidecar.get('state'))),
                        ('Fonte do sidecar', sidecar.get('reference')), ('SHA-256 do sidecar', sidecar.get('sha256')),
                        ('Caracteres no texto extraído', sidecar.get('characters')),
                        ('Trecho do texto extraído (até 600 caracteres)', sidecar.get('excerpt')),
                        ('Tipos declarados no sidecar JSON', sidecar.get('observed_types'))])
        body += ('<p>Extração estrutural determinística da captura, sem execução de análise semântica, '
                 'interpretação de intenção, ranking ou autoridade. FAQ/ARIA descrevem somente o DOM '
                 'capturado; visibilidade e conteúdo após interação permanecem condicionais.</p>')
        emit(page, 'Estrutura editorial verificável da captura', ('page_snapshots',), body,
             state={'AVAILABLE':'PRESENT_SUMMARIZED', 'PARTIAL':'PROCESSING_PARTIAL'}.get(capture['state'], capture['state']),
             sources=capture['sources'], limitation='STRUCTURAL_EXTRACTION_ONLY')

    metrics = safe.get('standards_metric_observations', ())
    grouped = Counter((str(r.get('source') or 'N/D'), str(r.get('scope') or 'N/D'),
                       str(r.get('state') or 'N/D')) for r in metrics)
    body = table('Cobertura das métricas por origem e escopo', [
        dict(tool=a, scope=b, execution=public_value(c, 'status'), quantity=n) for (a,b,c),n in sorted(grouped.items())],
        [('tool','Ferramenta/origem'), ('scope','Escopo'), ('execution','Estado persistido'), ('quantity','Métricas')])
    occurrences = Counter()
    for row in metrics:
        details = object_value(row.get('details_json'))
        for field in ('messages', 'error_details', 'warning_details'):
            for item in details.get(field, ()) if isinstance(details.get(field), list) else ():
                if isinstance(item, dict):
                    # Tool type/subtype/message are persisted, not inferred severities.
                    key = (row.get('source'), field, item.get('type'), item.get('subtype'), item.get('message'))
                    occurrences[key] += 1
    if occurrences:
        body += table('Ocorrências de validação agrupadas', [
            dict(tool=a, collection={'messages':'Mensagens','error_details':'Erros','warning_details':'Avisos'}.get(b,b),
                 kind=c, subtype=d, message=e, quantity=n)
            for (a,b,c,d,e),n in sorted(occurrences.items(), key=lambda x:str(x[0]))],
            [('tool','Ferramenta'), ('collection','Coleção de origem'), ('kind','Tipo persistido'),
             ('subtype','Subtipo persistido'), ('message','Mensagem registrada'), ('quantity','Ocorrências')])
    body += '<p>Tipos e contagens dos validadores não comprovam impacto SEO/GEO. Severidades não persistidas permanecem N/D.</p>'
    emit('descoberta', 'Síntese das validações técnicas',
         ('standards_metric_observations', 'standards_service_runs'), body)

    analyses = safe.get('serp_competitive_analyses', ())
    body = ''
    for row in analyses:
        status = row.get('comparison_status')
        body += kv([('Estado persistido da comparação', public_value(status, 'comparison_status')), ('Candidatos', row.get('candidate_count')),
                    ('Páginas de concorrentes comparadas em conteúdo', row.get('observed_competitor_pages'))])
        if status == 'CUSTOMER_CONTENT_NOT_COMPARABLE':
            body += ('<p class="callout w">O conteúdo capturado do alvo não permitiu comparação. '
                     'Candidatos observados na SERP não comprovam comparação de conteúdo executada '
                     'nem lacunas competitivas demonstradas.</p>')
    emit(SEARCH_PAGE, 'Elegibilidade da comparação competitiva', ('serp_competitive_analyses',),
         body or '<p>Comparação de conteúdo não materializada nesta fonte.</p>')

    from rasai.catalog_report_search_trust import _overview_values, _overview_references
    overview_sources, overview_rows = [], []
    for row in tables.get('serp_observations', ()):
        ref = row.get('raw_evidence_ref')
        raw, state = read_source(root, ref, inventory, expected=row.get('raw_evidence_sha256'), limit=8_000_000)
        source = dict(table='serp_observations', observation_id=row.get('observation_id'),
                      reference=ref if ref in inventory else None, sha256=inventory.get(ref), state=state)
        overview_sources.append(source)
        if raw is None:
            continue
        try:
            values = _overview_references(_overview_values(json.loads(raw)))
            for item in values[:100]:
                url = urlsplit(item['link'])
                if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
                    continue
                overview_rows.append(dict(query=row.get('query'), reference_index=item['index'],
                    reference_title=item['title'], reference_url=item['link']))
            if len(values) > 100:
                source['state'] = 'PARTIAL'
        except (ValueError, TypeError, RecursionError):
            source['state'] = 'PROJECTION_ERROR'
    overview_state = ('SOURCE_INTEGRITY_MISMATCH' if any(s['state'] == 'SOURCE_INTEGRITY_MISMATCH' for s in overview_sources) else
                      'PROCESSING_PARTIAL' if overview_rows and any(s['state'] != 'AVAILABLE' for s in overview_sources) else
                      'PRESENT_SUMMARIZED' if overview_rows else
                      'PROJECTION_ERROR' if any(s['state'] == 'PROJECTION_ERROR' for s in overview_sources) else
                      'RESOURCE_LIMIT' if any(s['state'] == 'RESOURCE_LIMIT' for s in overview_sources) else 'SOURCE_ABSENT')
    emit(SEARCH_PAGE, 'Referências identificáveis do AI Overview', ('serp_observations',),
        table('Referências declaradas pelo provedor no recorte observado', public_data(overview_rows),
              [('query','Consulta'), ('reference_index','Índice da referência no provedor'),
               ('reference_title','Título observado'), ('reference_url','URL observada (sem parâmetros privados)')])
        + '<p>Referência do AI Overview, resultado orgânico e citação generativa do alvo são evidências distintas. '
          'A lista não demonstra comparação competitiva executada.</p>',
        state=overview_state,
        sources=overview_sources, limitation='PROVIDER_REFERENCES_ONLY_NOT_ORGANIC_POSITIONS')

    history = crux_history(root, tables, inventory)
    body = kv([('Estado da projeção histórica CrUX', state_label(history['state']))])
    if history['groups']:
        body += table('CrUX de campo: janelas comparáveis por métrica e dispositivo', history['groups'],
            [('target','Alvo'), ('scope','Escopo'), ('form_factor','Dispositivo'), ('metric','Métrica'),
             ('unit','Unidade'), ('periods','Janelas'), ('first_start','Início da primeira janela'),
             ('first_end','Fim da primeira janela'), ('first_p75','Primeiro p75'),
             ('last_start','Início da última janela'), ('last_end','Fim da última janela'), ('last_p75','Último p75')],
             timezone_name=timezone_name)
    else:
        body += '<p>Sem série temporal comparável comprovada nos sidecars disponíveis.</p>'
    for index, group in enumerate(history['groups'],1):
        body += '<details><summary>'+text('Janelas de campo · '+str(group['metric'])+' · '+str(group['form_factor'] or 'Sem filtro de dispositivo'))+'</summary>'
        body += table('CrUX · série '+str(index), group['series'],
                      [('period_start','Início da janela'),('period_end','Fim da janela'),('p75','p75 ('+group['unit']+')')],
                      timezone_name=timezone_name, full_text=True)
        body += '</details>'
    body += ('<p>Janelas CrUX podem se sobrepor; diferenças não demonstram tendência ou causalidade. '
             'Campo, laboratório e simulação são medições independentes. Não são combinados em score.</p>')
    emit('performance', 'Histórico de campo com proveniência', (), body,
         state='PRESENT_SUMMARIZED' if history['state'] == 'AVAILABLE' else history['state'],
         sources=history['sources'], limitation=history['limitations'])

    # Include existing, actually populated page-specific field projections.
    from .page_views import SECTIONS
    from .catalog_context import STRUCTURED
    for page, _ in PAGES:
        projected = set(n for t in topics[page] if t['state'] == 'PRESENT_SUMMARIZED' for n in t['families'])
        specs = [(title, names, fields) for title,names,fields in SECTIONS.get(page, ()) if page != 'plano']
        for title, families, fields in specs:
            actual = [n for n in families if any(any(r.get(k) is not None for k,_ in fields)
                       for r in tables.get(n, ()))]
            if actual:
                topics[page].append(dict(topic=title, families=actual, state='PRESENT_FIELD_PROJECTION',
                    displayed_fields=[k for k,_ in fields],
                    sources=[dict(table=n, href=r.href, record_id=dict(r.identity)) for n in actual for r in by_table[n]],
                    limitation='FIELD_PROJECTION_NOT_EXECUTIVE_COMPLETENESS'))
                projected.update(actual)
        for title,name,fields,limit,_ in STRUCTURED.get(page, ()):
            if tables.get(name):
                topics[page].append(dict(topic=title, families=[name], state='PRESENT_PREVIEW',
                    available_records=len(tables[name]), preview_records=min(limit,len(tables[name])),
                    displayed_fields=[k for k,_ in fields], adequate_representation_certified=False,
                    sources=[dict(table=name, href=r.href, record_id=dict(r.identity)) for r in by_table[name][:limit]]))
        # Explicitly account for already-present aggregate summaries, with source-backed applicability.
        aggregate = {'indices': ('rule_executions', 'scores'), 'seguranca': ('passive_security_resources', 'passive_security_integrations'),
                     'ia-custos': ('console_cost_forecast_outcomes',)}.get(page, ())
        for name in aggregate:
            if tables.get(name):
                topics[page].append(dict(topic='Síntese de registros persistidos', families=[name],
                    state='PRESENT_SUMMARIZED', sources=[dict(table=name, href=r.href, record_id=dict(r.identity)) for r in by_table[name]]))
                projected.add(name)
        for name, rows in tables.items():
            if destination(name) == page and rows and name not in projected:
                topics[page].append(dict(topic=name, families=[name], state='PRESENT_TECHNICAL_ONLY',
                    sources=[dict(table=name, href=r.href, record_id=dict(r.identity)) for r in by_table[name]],
                    limitation='NO_ADDITIONAL_EXECUTIVE_PROJECTION_CLAIMED'))
    # Missing analysis has an explicit execution state, separate from capture availability.
    for page, family, component in (
        ('conteudo', 'semantic_coherence_assessments', 'CORE_AUDIT'),
        ('indices', 'scores', 'CORE_AUDIT'),
        ('seguranca', 'passive_security_runs', 'PASSIVE_SECURITY'),
        ('plano', 'directed_analysis_actions', 'TECHNICAL_AI'),
    ):
        if not tables.get(family):
            work = next((r for r in tables.get('audit_fulfillment_work_items', ())
                         if r.get('component') == component), {})
            state = work.get('status')
            topics[page].append(dict(topic=family, families=[family],
                state='PROCESSING_NOT_EXECUTED' if state in {'PENDING','REQUESTED_NOT_EXECUTED', 'NOT_REQUESTED'}
                      else 'SOURCE_ABSENT', component=component, persisted_execution_state=state,
                limitation='ABSENCE_IS_NOT_A_NEGATIVE_FINDING'))
    receipt = dict(contract='RASAI-PRESENTATION-EDITORIAL-COVERAGE-001',
        certifies_editorial_completeness=False, capture_state=capture['state'], history_state=history['state'],
        overview_state=overview_state,
        pages={p + '.html': topics[p] for p,_ in PAGES})
    return html, public_data(receipt)
