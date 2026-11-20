"""Read-only Search e GEO synthesis over persisted audit and observability evidence.

A missing observability sidecar never becomes evidence that a provider failed,
was disabled, or returned zero results. No provider calls, scores or inferences.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from rasai.observability.store import observability_database_path

from .components import table, text
from .sanitization import sanitize

_EXTERNAL_SOURCES = {
    'Google Search Console': ('GOOGLE_SEARCH_CONSOLE_', 'RASAI_GSC_ENABLED'),
    'Microsoft Clarity': ('MICROSOFT_CLARITY_LIVE_INSIGHTS', 'RASAI_CLARITY_ENABLED'),
    'Common Crawl': ('COMMON_CRAWL_CDX_HISTORY', 'RASAI_COMMON_CRAWL_ENABLED'),
}


def _json(value):
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return None


def _configured_value(source, key):
    if isinstance(source, dict):
        for name, value in source.items():
            if str(name).casefold() == key.casefold():
                return value
        for value in source.values():
            found = _configured_value(value, key)
            if found is not None:
                return found
    elif isinstance(source, (tuple, list)):
        for value in source:
            found = _configured_value(value, key)
            if found is not None:
                return found
    return None


def _flag(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().casefold()
    if normalized in {'1', 'true', 'yes', 'on', 'sim'}:
        return True
    if normalized in {'0', 'false', 'no', 'off', 'não', 'nao', 'disabled'}:
        return False
    return None


def _configuration(tables):
    configurations = tables.get('audit_execution_configurations', ())
    if len(configurations) != 1:
        return None
    return _json(configurations[0].get('configuration_json'))


def _sidecar(root):
    """Read existing indexed datasets in read-only mode; never initialize a DB."""
    path = observability_database_path(Path(root))
    if not path.is_file():
        return None, None
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        tables = {r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if 'datasets' not in tables:
            return None, 'Banco de observabilidade sem inventário de datasets'
        dataset_columns = {column[1] for column in connection.execute('PRAGMA table_info(datasets)')}
        fields = ['dataset_id', 'source_type', 'metadata', 'artifact_path']
        if 'artifact_sha256' in dataset_columns:
            fields.append('artifact_sha256')
        datasets = [dict(row) for row in connection.execute(
            'SELECT ' + ', '.join(fields) + ' FROM datasets')]
        counts = {}
        for source, (prefix, _) in _EXTERNAL_SOURCES.items():
            ids = [row['dataset_id'] for row in datasets
                   if str(row.get('source_type') or '').startswith(prefix)]
            lookup = {'Google Search Console': ('search_performance', 'index_observations'),
                      'Microsoft Clarity': ('behavioral_observations',),
                      'Common Crawl': ('web_archive_observations',)}[source]
            counted = 0
            for family in lookup:
                if family not in tables or not ids:
                    continue
                values = ','.join('?' for _ in ids)
                columns = {col[1] for col in connection.execute(
                    'PRAGMA table_info("' + family + '")')}
                if 'dataset_id' in columns:
                    counted += connection.execute(
                        'SELECT COUNT(*) FROM "' + family + '" WHERE dataset_id IN ('
                        + values + ')', ids).fetchone()[0]
            counts[source] = counted
        return datasets, counts


def _source_rows(root, tables):
    config = _configuration(tables)
    try:
        datasets, counts = _sidecar(root)
        sidecar_error = None
    except (OSError, sqlite3.Error, ValueError) as error:
        datasets, counts = None, None
        sidecar_error = type(error).__name__
    output = []
    services = [
        r for r in tables.get('standards_service_runs', ())
        if isinstance(r, dict) and
        'google-search-console' in str(r.get('service_id') or '').lower()
    ]
    for name, (prefix, flag_key) in _EXTERNAL_SOURCES.items():
        flag = _flag(_configured_value(config, flag_key))
        source = ([d for d in datasets
                   if str(d.get('source_type') or '').startswith(prefix)]
                  if datasets is not None else [])
        work = services if name == 'Google Search Console' else []
        requested = bool(source or work or flag is True)
        errors = sum(str(w.get('state') or w.get('status') or '').upper() in
                     {'FAILED', 'ERROR', 'UNAVAILABLE'} for w in work)
        for d in source:
            metadata = _json(d.get('metadata'))
            if isinstance(metadata, dict):
                try:
                    errors += max(0, int(metadata.get('errors') or 0))
                except (ValueError, TypeError):
                    pass
        executed = bool(source or work)
        if executed:
            execution = 'Executada com erro registrado' if errors else 'Execução registrada'
        elif requested:
            execution = 'Não comprovada pelos registros disponíveis'
        elif flag is False:
            execution = 'Desabilitada'
        else:
            execution = 'N/D — solicitação não comprovada'
        available = (str(counts[name]) + ' registro(s) de observabilidade'
                     if counts is not None and counts[name]
                     else 'Sem registros de resultado'
                     if counts is not None else 'N/D — inventário externo indisponível')
        output.append({
            'source': name,
            'enabled': 'Habilitada' if flag is True else
                       'Desabilitada' if flag is False else 'Não documentada',
            'request': 'Solicitada' if requested else
                       'Não solicitada' if flag is False
                       else 'N/D — solicitação não comprovada',
            'execution': execution,
            'data': available,
            'origin': (str(len(source)) + ' dataset(s) persistido(s)'
                       + ('; ' + str(len(work)) + ' serviço(s)' if work else '')
                       if source or work else 'Sem dataset/serviço verificável'),
            'dataset_id': source[-1].get('dataset_id') if source else None,
            'artifact_ref': source[-1].get('artifact_path') if source else None,
            'artifact_sha256': source[-1].get('artifact_sha256') if source else None,
        })
    if sidecar_error:
        output.append({
            'source': 'Integridade do inventário externo',
            'enabled': 'N/D', 'request': 'N/D',
            'execution': 'Leitura indisponível: ' + sidecar_error,
            'data': 'N/D', 'origin': 'Revisão técnica necessária',
        })
    return output


def _nonnegative_integer(value):
    return value if type(value) is int and value >= 0 else None


def _competitive_evidence_assessment(tables):
    """Source-only comparison gate: no market, ranking or causal conclusion.

    Match by observation AND selected requested URL, not by number of
    harvested pages. A persisted count of zero is not proof of comparability.
    """
    analyses = {
        str(row['observation_id']): row
        for row in tables.get('serp_competitive_analyses', ())
        if isinstance(row, dict) and row.get('observation_id')
    }
    pages = {}
    for row in tables.get('serp_competitive_pages', ()):
        if isinstance(row, dict) and row.get('observation_id'):
            pages.setdefault(str(row['observation_id']), []).append(row)
    selected = {}
    for row in tables.get('serp_competitive_results', ()):
        if (isinstance(row, dict) and row.get('observation_id')
                and row.get('selected_for_content_comparison') in (1, True)
                and row.get('url')):
            selected.setdefault(str(row['observation_id']), set()).add(str(row['url']))

    identifiers = sorted(set(analyses) | set(pages) | set(selected))
    gap_labels = {
        'QUERY_BODY_COVERAGE_LOWER_THAN_OBSERVED_LEADERS':
            'Menor cobertura dos termos da consulta no conteúdo',
        'TITLE_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS':
            'Menor correspondência dos termos da consulta no título',
        'HEADING_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS':
            'Menor correspondência dos termos da consulta nos cabeçalhos',
        'CONTENT_WORD_COUNT_LOWER_THAN_OBSERVED_LEADERS':
            'Menor volume de texto observado na página',
        'STRUCTURED_DATA_TYPES_DIFFER_FROM_OBSERVED_LEADERS':
            'Diferença nos tipos de dados estruturados observados',
    }
    reasons = {
        'SERP_OBSERVATION_UNAVAILABLE': 'Observação SERP indisponível nesta coleta.',
        'CONTENT_COMPARISON_DISABLED': 'Comparação de conteúdo não solicitada.',
        'CUSTOMER_URL_REQUIRED': 'URL do alvo não estava disponível para comparação.',
        'CUSTOMER_CONTENT_UNAVAILABLE': 'Conteúdo do alvo indisponível.',
        'CUSTOMER_CONTENT_NOT_COMPARABLE': 'Conteúdo do alvo não comparável.',
        'NO_ELIGIBLE_COMPETITOR_CANDIDATES': 'Nenhum candidato elegível foi selecionado.',
        'COMPETITOR_CONTENT_UNAVAILABLE': 'Conteúdo dos candidatos não foi observado de forma comparável.',
    }
    output = []
    for identifier in identifiers:
        analysis = analyses.get(identifier) or {}
        state = str(analysis.get('comparison_status') or '').upper()
        observed = pages.get(identifier, [])
        customer = any(
            row.get('role') == 'CUSTOMER' and row.get('fetch_status') == 'OBSERVED'
            for row in observed
        )
        selected_urls = selected.get(identifier, set())
        candidate_count = sum(
            row.get('role') == 'COMPETITOR_CANDIDATE'
            and row.get('fetch_status') == 'OBSERVED'
            and str(row.get('requested_url') or '') in selected_urls
            for row in observed
        )
        gaps = analysis.get('gap_count')
        comparable = bool(
            state == 'CONSOLIDATED'
            and customer and selected_urls and candidate_count > 0
            and type(gaps) is int and gaps >= 0
        )
        if not state:
            reason = 'Análise comparativa não persistida para esta observação.'
        elif state != 'CONSOLIDATED':
            reason = reasons.get(state, 'Estado persistido sem comparabilidade suficiente.')
        elif not customer:
            reason = 'Sem captura observada do conteúdo do alvo nesta evidência.'
        elif not selected_urls:
            reason = 'Sem seleção persistida dos candidatos comparáveis.'
        elif not candidate_count:
            reason = 'Sem conteúdo observado correspondente aos candidatos selecionados.'
        elif not comparable:
            reason = 'Quantidade de diferenças não verificável na análise persistida.'
        else:
            reason = 'Há comparação técnica descritiva registrada; a captura HTTP não comprova conteúdo principal substantivo ou equivalência editorial e não demonstra ranking, mercado ou causalidade.'
        # Detail text is eligible only if the canonical persisted gap ledger
        # reconciles to its count. Never invent a description from a number.
        details = []
        detail_state = 'NOT_APPLICABLE' if comparable and gaps == 0 else 'NOT_VERIFIABLE'
        raw_gaps = _json(analysis.get('gaps_json')) if comparable and gaps else None
        if (comparable and type(gaps) is int and 0 < gaps <= 20
                and isinstance(raw_gaps, list) and len(raw_gaps) == gaps
                and all(isinstance(item, dict) and
                        isinstance(item.get('message'), str) and
                        item['message'].strip() for item in raw_gaps)):
            # Gap references use a final URL if available, as recorded by the
            # content comparator; URLs from other observations are not proof.
            verified_urls = {
                str(row.get('final_url') or row.get('requested_url') or '')
                for row in observed
                if row.get('role') == 'COMPETITOR_CANDIDATE'
                and row.get('fetch_status') == 'OBSERVED'
                and str(row.get('requested_url') or '') in selected_urls
            }
            for gap in raw_gaps:
                references = gap.get('evidence_urls')
                refs = (references if isinstance(references, list) else [])
                trusted = [
                    str(url) for url in refs
                    if isinstance(url, str) and url in verified_urls
                ]
                details.append({
                    'observation': identifier,
                    'kind': gap_labels.get(
                        str(gap.get('code') or ''), 'Diferença de conteúdo registrada'),
                    'code': str(gap.get('code') or 'N/D')[:120],
                    'difference': gap['message'][:700],
                    'customer': gap.get('customer_value'),
                    'reference': gap.get('leader_reference'),
                    'evidence': ', '.join(trusted[:5]) if trusted else 'N/D — referência não conciliada',
                    'receipt': analysis.get('evidence_ref') or 'N/D',
                })
            detail_state = 'PERSISTED_GAPS_RECONCILED'
        output.append({
            'observation_id': identifier,
            'comparison_status': state or 'N/D',
            'content_comparison_verified': comparable,
            'content_comparison': 'Comparação técnica registrada' if comparable else 'N/D — não comprovada',
            'reason': reason,
            'selected_candidate_count': len(selected_urls),
            'observed_selected_candidate_pages': candidate_count,
            'observed_page_records': len(observed),
            'observed_gap_count': gaps if comparable else None,
            'difference_detail_state': detail_state,
            'observed_differences': details,
            'competitive_conclusion': 'INDETERMINATE',
            'evidence_ref': analysis.get('evidence_ref') or None,
            'source_families': ('serp_competitive_analyses', 'serp_competitive_pages',
                                'serp_competitive_results'),
        })
    return output


def _competitive_summary(tables):
    analyses = [r for r in tables.get('serp_competitive_analyses', ())
                if isinstance(r, dict)]
    assessed = _competitive_evidence_assessment(tables)
    comparable = [item for item in assessed if item['content_comparison_verified']]

    def observed_pages_total():
        # Observed competitor content is a source fact even if the customer's
        # content cannot be compared. Do not erase valid collection coverage.
        values = [_nonnegative_integer(a.get('observed_competitor_pages'))
                  for a in analyses]
        return sum(values) if values and all(v is not None for v in values) else 'N/D'

    def verified_gaps_total():
        # A zero is meaningful only for comparable observations. In a mixed
        # cohort, label the numerator as partial instead of inventing a total.
        if not comparable:
            return 'N/D'
        total = sum(item['observed_gap_count'] for item in comparable)
        if len(comparable) != len(assessed):
            return f'{total} (parcial: {len(comparable)} de {len(assessed)} observações)'
        return total
    results = tables.get('serp_results')
    selected = [r for r in tables.get('serp_competitive_results', ())
                if isinstance(r, dict) and
                r.get('selected_for_content_comparison') in (1, True)]
    return [
        {'indicator': 'Resultados SERP normalizados',
         'value': len(results) if results is not None else 'N/D',
         'basis': 'serp_results'},
        {'indicator': 'Candidatos selecionados para comparação',
         'value': len(selected) if tables.get('serp_competitive_results') is not None else 'N/D',
         'basis': 'serp_competitive_results'},
        {'indicator': 'Páginas externas com conteúdo observado',
         'value': observed_pages_total(),
         'basis': 'serp_competitive_analyses.observed_competitor_pages'},
        {'indicator': 'Diferenças competitivas determinísticas',
         'value': verified_gaps_total(),
         'basis': 'serp_competitive_analyses.gap_count'},
    ]


def _competitive_ai_reasoning_profile(row, attempts):
    """Use a source-owned profile or a unique exact request-ID match only.

    Provider/model coincidence and current configuration never prove the
    effort used, especially after retries or fallback.
    """
    value = row.get('reasoning_profile')
    if isinstance(value, str) and value.strip():
        return value.strip()
    request_id = str(row.get('provider_request_id') or '').strip()
    if not request_id:
        return None
    matches = [
        attempt for attempt in attempts
        if isinstance(attempt, dict)
        and str(attempt.get('request_id') or '').strip() == request_id
        and str(attempt.get('operation') or '').upper() == 'COMPETITIVE_INTELLIGENCE'
        and str(attempt.get('semantic_contract_version') or '').upper() == 'COMPETITIVE-AI-001'
        and str(attempt.get('status') or '').upper() == 'SUCCESS'
        and str(attempt.get('provider') or '').casefold() ==
            str(row.get('provider') or '').casefold()
        and str(attempt.get('model') or '') == str(row.get('model') or '')
    ]
    if len(matches) != 1:
        return None
    profile = matches[0].get('reasoning_profile')
    return str(profile).strip() if isinstance(profile, str) and profile.strip() else None


def render_search_visibility_synthesis(root, tables):
    """Contextual sections only; full source records remain in technical inventory."""
    html = (
        '<section class="search-visibility-synthesis">'
        '<h2>Fontes Search e GEO e seus estados registrados</h2>'
        '<p class="rf">Habilitação, solicitação, execução, resultado e '
        'disponibilidade de observabilidade são dimensões diferentes. '
        'Falha externa não é ausência de configuração; ausência de sidecar '
        'não comprova execução, falha ou resultado zero.</p>'
    )
    html += table('Estados das integrações', sanitize(_source_rows(root, tables)),
                  [('source', 'Integração'), ('enabled', 'Habilitação'),
                   ('request', 'Solicitação'), ('execution', 'Execução'),
                   ('data', 'Dados'), ('origin', 'Proveniência'),
                   ('dataset_id', 'Dataset da última evidência'),
                   ('artifact_ref', 'Arquivo de origem'),
                   ('artifact_sha256', 'SHA-256 da origem')])
    source_status = []
    for name, family in [('SERP', 'serp_observations'),
                         ('Perplexity / Search API', 'perplexity_search_runs'),
                         ('Inteligência competitiva', 'serp_competitive_analyses'),
                         ('Análises competitivas por IA', 'serp_competitive_ai_analyses')]:
        records = tables.get(family)
        source_status.append({'source': name,
                              'count': len(records) if records is not None else 'N/D',
                              'basis': family})
    html += table('Disponibilidade dos resultados persistidos de Search',
                  source_status, [('source', 'Fonte'), ('count', 'Registros'),
                                  ('basis', 'Tabela de origem')])
    html += (
        '<h2>Comparação competitiva e GEO — universos independentes</h2>'
        '<p class="rf">Contagens por contexto de observação, sem deduplicação '
        'transversal entre consultas. A sobreposição de URLs não demonstra '
        'citação generativa ou preferência de uma IA. Diferenças de conteúdo '
        'não são causas comprovadas de posicionamento.</p>'
    )
    html += table('Indicadores competitivos materializados',
                  _competitive_summary(tables),
                  [('indicator', 'Indicador'), ('value', 'Valor'),
                   ('basis', 'Fonte / campo')])
    comparable_rows = _competitive_evidence_assessment(tables)
    html += (
        '<h3>Verificação da comparabilidade por observação</h3>'
        '<p class="rf">A presença de candidatos SERP não prova concorrência comercial. '
        'Somente uma análise consolidada, com conteúdo do alvo observado e '
        'conteúdo observado de candidato selecionado na mesma observação, '
        'permite apresentar diferenças descritivas. A captura HTTP não comprova '
        'conteúdo principal substantivo ou equivalência editorial; conclusões '
        'sobre ranking, mercado e causalidade permanecem indeterminadas.</p>'
    )
    if comparable_rows:
        html += table('Condições verificadas da comparação de conteúdo',
                      sanitize([
                          {'observation': row['observation_id'],
                           'status': row['comparison_status'],
                           'comparison': row['content_comparison'],
                           'reason': row['reason'],
                           'observed_pages': row['observed_page_records'],
                           'selected_pages': row['observed_selected_candidate_pages'],
                           'gaps': (row['observed_gap_count']
                                    if row['content_comparison_verified'] else 'N/D'),
                           'reference': row['evidence_ref'] or 'N/D'}
                          for row in comparable_rows
                      ]),
                      [('observation', 'Observação SERP'),
                       ('status', 'Estado da análise'),
                       ('comparison', 'Comparabilidade do conteúdo'),
                       ('reason', 'Limitação e interpretação'),
                       ('observed_pages', 'Registros de páginas'),
                       ('selected_pages', 'Candidatos selecionados com conteúdo'),
                       ('gaps', 'Diferenças observadas'),
                       ('reference', 'Evidência persistida')], full_text=True)
    else:
        html += '<p class="rf">N/D — nenhuma análise ou página comparativa persistida; conclusão competitiva indeterminada.</p>'
    if any(row['content_comparison_verified'] and row['observed_gap_count'] == 0
           for row in comparable_rows):
        html += ('<p class="rf">Zero diferenças determinísticas foram registradas '
                 'em uma ou mais comparações técnicas. Isso não comprova '
                 'equivalência substantiva das páginas, ausência de lacunas '
                 'editoriais, qualidade do conteúdo principal ou vantagem '
                 'competitiva. Recomendações de IA são consultivas e independentes '
                 'desse resultado.</p>')
    explained = [gap for row in comparable_rows for gap in row['observed_differences']]
    if explained:
        html += (
            '<h3>Diferenças descritivas registradas por observação</h3>'
            '<p class="rf">Apenas diferenças do registro persistido conciliadas '
            'com a mesma observação e páginas selecionadas. Não representam '
            'vantagem competitiva, relação causal, resultado de mercado ou '
            'recomendação aprovada.</p>'
        )
        html += table('Diferenças observadas e rastreáveis',
                      sanitize(explained),
                      [('observation', 'Observação SERP'),
                       ('kind', 'Diferença registrada'),
                       ('difference', 'Descrição persistida'),
                       ('customer', 'Valor do alvo'),
                       ('reference', 'Referência observada'),
                       ('evidence', 'URL de evidência conciliada'),
                       ('receipt', 'Artefato persistido')], full_text=True)
    if any(row['content_comparison_verified'] and
           row['difference_detail_state'] == 'NOT_VERIFIABLE'
           for row in comparable_rows):
        html += '<p class="rf">N/D — há contagens de diferenças, mas o detalhamento persistido não pôde ser conciliado integralmente; não se inferem descrições.</p>'
    comparisons = []
    for item in tables.get('geo_observation_runs', ()):
        projection = _json(item.get('projection_json'))
        if not isinstance(projection, dict):
            continue
        overlap = projection.get('descriptive_overlap') or {}
        if not isinstance(overlap, dict):
            overlap = {}
        comparisons.append({
            'run': item.get('perplexity_run_id'),
            'perplexity': _nonnegative_integer(projection.get('source_count')),
            'serp': _nonnegative_integer(overlap.get('serp_denominator')),
            'common': _nonnegative_integer(overlap.get('common_urls')),
            'origin': 'geo_observation_runs.projection_json',
        })
    if comparisons:
        html += table('Sobreposição descritiva por execução persistida', comparisons,
                      [('run', 'Execução Search API'), ('perplexity', 'Fontes externas'),
                       ('serp', 'URLs SERP'), ('common', 'URLs em comum'),
                       ('origin', 'Proveniência')])
    else:
        html += '<p class="rf">N/D — nenhuma projeção de sobreposição disponível.</p>'
    context = [
        {'observation': a.get('observation_id'),
         'status': a.get('comparison_status'), 'gaps': a.get('gap_count'),
         'reference': a.get('evidence_ref'), 'sha': a.get('evidence_sha256')}
        for a in tables.get('serp_competitive_analyses', ())
        if isinstance(a, dict)
    ]
    if context:
        html += table('Proveniência das comparações determinísticas',
                      sanitize(context),
                      [('observation', 'Observação SERP'), ('status', 'Comparabilidade'),
                       ('gaps', 'Diferenças'), ('reference', 'Arquivo de evidência'),
                       ('sha', 'SHA-256')])
    ai, opportunities = [], []
    attempts = tables.get('ai_provider_attempts', ())
    for row in tables.get('serp_competitive_ai_analyses', ()):
        if not isinstance(row, dict):
            continue
        ai.append({
            'observation': row.get('observation_id'),
            'status': row.get('state'),
            'provider': row.get('provider'), 'model': row.get('model'),
            'reasoning_profile': _competitive_ai_reasoning_profile(row, attempts),
            'summary': row.get('summary'),
            'opportunity_count': row.get('opportunity_count'),
            'reference': row.get('evidence_ref'),
            'sha': row.get('evidence_sha256'),
        })
        proposals = _json(row.get('opportunities_json'))
        if isinstance(proposals, list):
            for proposal in proposals:
                if not isinstance(proposal, dict):
                    continue
                evidence_ids = proposal.get('evidence_ids')
                opportunities.append({
                    'observation': row.get('observation_id'),
                    'title': proposal.get('title'),
                    'priority': proposal.get('priority'),
                    'proposal': proposal.get('recommendation'),
                    'evidence': ', '.join(str(i) for i in evidence_ids)
                                if isinstance(evidence_ids, list) else 'N/D',
                    'reference': row.get('evidence_ref'),
                })
    if ai:
        html += (
            '<h2>Propostas consultivas de análise competitiva por IA</h2>'
            '<p class="rf">Análise persistida produzida por IA, de caráter consultivo; '
            'não constitui ação aprovada pela governança ou prova causal.</p>'
        )
        html += table('Sínteses de IA já materializadas', sanitize(ai),
                      [('observation', 'Observação SERP'), ('status', 'Estado'),
                       ('provider', 'Provedor'), ('model', 'Modelo'),
                       ('reasoning_profile', 'Esforço solicitado'),
                       ('summary', 'Síntese consultiva'),
                       ('opportunity_count', 'Propostas declaradas'),
                       ('reference', 'Artefato'), ('sha', 'SHA-256')], full_text=True)
        html += ('<p class="rf">O esforço indica a configuração registrada da tentativa, '
                 'não a profundidade efetivamente observada. N/D quando esta síntese '
                 'não possui vínculo inequívoco com uma tentativa de IA.</p>')
    if opportunities:
        # The full list is still available in the canonical row and annex;
        # this is an editorial preview in persisted order, not a new ranking.
        html += '<p class="rf">Amostra das primeiras até cinco propostas, na ordem persistida; ' \
                'não é uma seleção de prioridades aprovadas.</p>'
        html += table('Propostas consultivas e seus vínculos de evidência',
                      sanitize(opportunities[:5]),
                      [('observation', 'Observação'), ('title', 'Proposta'),
                       ('priority', 'Prioridade declarada pela fonte'),
                       ('proposal', 'Recomendação consultiva'),
                       ('evidence', 'IDs de evidência'), ('reference', 'Artefato')], full_text=True)
    html += (
        '<p class="rf">Registros completos, limitações metodológicas, IDs '
        'e anexos permanecem no inventário técnico desta própria página. '
        'Não há dependência do relatório de catálogo.</p></section>'
    )
    return html
