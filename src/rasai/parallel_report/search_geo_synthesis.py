"""Read-only Search/GEO synthesis over persisted audit and observability evidence.

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
        datasets = [dict(row) for row in connection.execute(
            'SELECT dataset_id, source_type, metadata, artifact_path FROM datasets')]
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
                     if counts is not None else 'N/D — sem inventário legível')
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


def _competitive_summary(tables):
    analyses = [r for r in tables.get('serp_competitive_analyses', ())
                if isinstance(r, dict)]
    def reported_total(field):
        values = [_nonnegative_integer(a.get(field)) for a in analyses]
        return sum(values) if values and all(v is not None for v in values) else 'N/D'
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
         'value': reported_total('observed_competitor_pages'),
         'basis': 'serp_competitive_analyses.observed_competitor_pages'},
        {'indicator': 'Diferenças competitivas determinísticas',
         'value': reported_total('gap_count'),
         'basis': 'serp_competitive_analyses.gap_count'},
    ]


def render_search_geo_synthesis(root, tables):
    """Contextual sections only; full source records remain in technical inventory."""
    html = (
        '<section class="search-geo-synthesis">'
        '<h2>Fontes Search/GEO e seus estados registrados</h2>'
        '<p class="rf">Habilitação, solicitação, execução, resultado e '
        'disponibilidade de observabilidade são dimensões diferentes. '
        'Falha externa não é ausência de configuração; ausência de sidecar '
        'não comprova execução, falha ou resultado zero.</p>'
    )
    html += table('Estados das integrações', _source_rows(root, tables),
                  [('source', 'Integração'), ('enabled', 'Habilitação'),
                   ('request', 'Solicitação'), ('execution', 'Execução'),
                   ('data', 'Dados'), ('origin', 'Proveniência')])
    source_status = []
    for name, family in [('SERP', 'serp_observations'),
                         ('Perplexity / Search API', 'perplexity_search_runs'),
                         ('Inteligência competitiva', 'serp_competitive_analyses'),
                         ('Competitive AI', 'serp_competitive_ai_analyses')]:
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
    for row in tables.get('serp_competitive_ai_analyses', ()):
        if not isinstance(row, dict):
            continue
        ai.append({
            'observation': row.get('observation_id'),
            'status': row.get('state'),
            'provider': row.get('provider'), 'model': row.get('model'),
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
            '<h2>Propostas semânticas de Competitive AI</h2>'
            '<p class="rf">Análise persistida produzida por IA, de caráter consultivo; '
            'não constitui ação aprovada pela governança ou prova causal.</p>'
        )
        html += table('Sínteses de IA já materializadas', sanitize(ai),
                      [('observation', 'Observação SERP'), ('status', 'Estado'),
                       ('provider', 'Provedor'), ('model', 'Modelo'),
                       ('summary', 'Síntese consultiva'),
                       ('opportunity_count', 'Propostas declaradas'),
                       ('reference', 'Artefato'), ('sha', 'SHA-256')], full_text=True)
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
