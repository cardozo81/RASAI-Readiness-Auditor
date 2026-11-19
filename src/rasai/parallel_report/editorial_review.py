"""Deterministic issue-722 source inventory; never certifies editorial completeness.

This policy catalogs persisted evidence and explicit presentation projections.
Decision relevance is an editorial triage rule, not a finding, score, approval,
or an assertion that a collector or AI provider completed successfully.
"""
from collections import Counter, defaultdict
from hashlib import sha256

from .components import kv, text
from .read_model import PAGES, destination
from .search_visibility_synthesis import _competitive_evidence_assessment
from .templates import label as public_label


# Explicit decision-oriented triage, independent of the existence of rows.
# A missing executive interpretation cannot be satisfied by a technical link.
EXECUTIVE_REVIEW = frozenset("""
audit_fulfillment_contracts audit_fulfillment_work_items audit_reprocess_runs
audits directed_analysis_runs remediation_groups recommendations
improvement_intelligence_recommendations passive_security_remediations
semantic_assessments property_semantic_summaries
content_context_interpretations serp_competitive_pages
web_performance_runs synthetic_ux_apdex_runs
""".split())
ANALYTICAL_REVIEW = frozenset("""
ai_provider_native_usage ai_request_rounds ai_task_profile_attempts
perplexity_search_sources root_cause_analyses root_cause_precision
score_contributions passive_security_relationships
""".split())

# Operational evidence that is intentionally not turned into a recommendation.
# Listed explicitly to prevent a newly introduced family from being silently
# dismissed as "not decision relevant" without review.
TECHNICAL_BY_DESIGN = frozenset("""
ai_audit_sessions ai_dependency_snapshots ai_evidence_versions
ai_task_dependency_specs audit_execution_configurations
audit_execution_sessions audit_fulfillment_attempts audit_input_summary
audit_input_urls audit_reprocess_derived_archive audit_targets
console_execution_projections content_remediation_runs
content_remediation_suggestions improvement_intelligence_runs
lighthouse_execution_profiles m24_ai_results m24_runs pages
passive_security_cookie_attribution passive_security_platforms
passive_security_script_observations
perplexity_search_request_scopes provider_native_pricing_catalog
provider_pricing_catalog request_remediation_ai request_remediation_evidence
request_remediation_groups semantic_corpus_manifests
serp_evidence_provenance synthetic_apdex_acquisition_runs
synthetic_apdex_acquisitions synthetic_apdex_runs synthetic_apdex_samples
synthetic_ux_apdex_samples web_performance_attempts
content_remediation_native_usage passive_security_advisories
passive_security_components finding_element_observations
semantic_property_signals synthetic_acquisition_replay_links
""".split())

# Proof is a specific existing rendering path, not a generic family prefix.
# These representations remain subject to human editorial acceptance.
CONTEXTUAL_RENDERERS = {
    'audits': 'Painel e situação de execução',
    'audit_fulfillment_contracts': 'Painel e situação de execução',
    'audit_fulfillment_work_items': 'Painel e situação de execução',
    'audit_reprocess_runs': 'Histórico de execução no Painel',
    'directed_analysis_runs': 'Contexto estratégico do Plano',
    'remediation_groups': 'Grupos de causa-raiz do Plano',
    'recommendations': 'Recomendações consultivas do Plano',
    'improvement_intelligence_recommendations': 'Correções consultivas do Plano',
}

# Only source-field statuses are exposed. No inferential execution status.
STATUS_TOKENS = frozenset("""
SUCCESS COMPLETE COMPLETED PARTIAL FAILED ERROR BLOCKED PENDING
NOT_REQUESTED NOT_EXECUTED REQUESTED_NOT_EXECUTED SKIPPED
NOT_APPLICABLE UNKNOWN RUNNING IN_PROGRESS FAILED_RETRYABLE
FAILED_PERMANENT TECHNICAL_ERROR CONTRACT_ERROR
PASS WARNING FAIL FINAL PRELIMINARY NOT_COMPARABLE
CONSOLIDATED NOT_CONSOLIDATED
""".split())

CLASS_LABELS = {
    'PRESENT_EXECUTIVE': 'Síntese registrada',
    'PRESENT_ANALYTICAL': 'Campos analíticos registrados',
    'PRESENT_CONTEXTUAL': 'Projeção contextual existente',
    'REQUIRES_EXECUTIVE_REVIEW': 'Síntese decisória a validar',
    'REQUIRES_ANALYTICAL_REVIEW': 'Projeção analítica a validar',
    'TECHNICAL_BY_DESIGN': 'Detalhe técnico por finalidade',
    'POLICY_REVIEW_REQUIRED': 'Relevância a classificar',
    'SOURCE_EMPTY': 'Fonte presente, sem registros',
}
REASONS = {
    'PRESENT_EXECUTIVE': 'Há uma síntese com fonte registrada; correção semântica e suficiência ainda dependem de aceite.',
    'PRESENT_ANALYTICAL': 'Campos persistidos foram projetados; isso não certifica interpretação executiva.',
    'PRESENT_CONTEXTUAL': 'Existe projeção contextual identificada no gerador; sua suficiência não está certificada.',
    'REQUIRES_EXECUTIVE_REVIEW': 'Família relevante a decisões sem síntese comprovada no recibo desta geração.',
    'REQUIRES_ANALYTICAL_REVIEW': 'Família relevante a análise sem campos analíticos comprovados no recibo desta geração.',
    'TECHNICAL_BY_DESIGN': 'Fonte operacional de rastreabilidade; uso como conclusão exigiria outra evidência.',
    'POLICY_REVIEW_REQUIRED': 'Família sem política explícita: não presumir irrelevância ou conclusão.',
    'SOURCE_EMPTY': 'Zero registros persistidos nesta tabela; não equivale a ausência de problema ou execução bem-sucedida.',
}


def _row_statuses(rows):
    fields = ('status', 'state', 'processing_status')
    counts = Counter()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for field in fields:
            raw = row.get(field)
            if isinstance(raw, str):
                token = raw.strip().upper()
                counts[token if token in STATUS_TOKENS else 'OTHER_RECORDED_STATE'] += 1
                break
    return dict(sorted(counts.items()))


def _reference(name, table_annexes):
    page = destination(name)
    if page is not None:
        anchor = sha256(name.encode('utf-8')).hexdigest()[:12]
        return page + '.html#source-' + anchor
    return 'anexos/' + table_annexes[name]


def _summaries(editorial_receipt, name):
    return [
        {'page': page, 'topic': topic.get('topic'), 'state': topic.get('state')}
        for page, topics in editorial_receipt.get('pages', {}).items()
        for topic in topics if name in topic.get('families', ())
    ]


def _classification(name, rows, editorial_states, analytical_fields):
    if not rows:
        return 'SOURCE_EMPTY'
    if 'PRESENT_SUMMARIZED' in editorial_states:
        return 'PRESENT_EXECUTIVE'
    if name == 'serp_competitive_pages':
        # Field-level visibility is not a competitive decision or executive
        # synthesis. Keep the explicit high-priority editorial gap open.
        return 'REQUIRES_EXECUTIVE_REVIEW'
    if analytical_fields or 'PRESENT_FIELD_PROJECTION' in editorial_states:
        # Existing SECTIONS are source-backed field projections even when the
        # separate analytical-views renderer did not register direct fields.
        return 'PRESENT_ANALYTICAL'
    if name in CONTEXTUAL_RENDERERS:
        return 'PRESENT_CONTEXTUAL'
    if name in EXECUTIVE_REVIEW:
        return 'REQUIRES_EXECUTIVE_REVIEW'
    if name in ANALYTICAL_REVIEW:
        return 'REQUIRES_ANALYTICAL_REVIEW'
    if name in TECHNICAL_BY_DESIGN:
        return 'TECHNICAL_BY_DESIGN'
    return 'POLICY_REVIEW_REQUIRED'


def _simple_table(rows):
    headers = ('Fonte', 'Registros', 'Representação e próxima revisão', 'Evidência')
    head = ''.join('<th scope="col">' + text(name) + '</th>' for name in headers)
    body = []
    for item in rows:
        cells = [
            text(public_label(item['family'])),
            text(item['row_count']),
            text(CLASS_LABELS[item['classification']]),
            '<a class="tech-link" href="' + text(item['href']) + '">Abrir fonte</a>',
        ]
        body.append('<tr>' + ''.join('<td>' + cell + '</td>' for cell in cells) + '</tr>')
    return '<div class="tw"><table><caption>Classificação de fontes persistidas</caption><thead><tr>' + head + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div>'


def build_editorial_review(tables, editorial_receipt, analytical_receipt,
                           table_annexes, coverage_receipt):
    """Return per-page HTML and complete source-by-source review receipt.

    All SQLite families are accounted for, including zero-row families and
    technical-only sources. No score, recommendation or observation is created.
    """
    families = {}
    for name, rows in sorted(tables.items()):
        topics = _summaries(editorial_receipt, name)
        page = destination(name)
        analytical = analytical_receipt.get(page + '.html', {}).get(name, {}) if page else {}
        direct = list(analytical.get('direct_fields') or ())
        classification = _classification(name, rows,
                                         {topic['state'] for topic in topics}, direct)
        families[name] = {
            'family': name,
            'source': 'audit.db',
            'row_count': len(rows),
            'page': page + '.html' if page is not None else None,
            'href': _reference(name, table_annexes),
            'annex': 'anexos/' + table_annexes[name],
            'status_field_observations': _row_statuses(rows),
            'materialization': [{'page': entry['page'], 'state': entry['state'],
                                 'topic': entry['topic']} for entry in topics],
            'analytical_direct_fields': direct,
            'classification': classification,
            'decision_relevance': ('HIGH' if name in EXECUTIVE_REVIEW
                                   else 'MEDIUM' if name in ANALYTICAL_REVIEW else
                                   'TECHNICAL' if name in TECHNICAL_BY_DESIGN else 'UNASSESSED'),
            'rationale': REASONS[classification],
            'existing_contextual_renderer': CONTEXTUAL_RENDERERS.get(name),
            'human_editorial_acceptance': 'PENDING',
        }

    topic_review = []
    for page, topics in editorial_receipt.get('pages', {}).items():
        for topic in topics:
            if topic.get('state') != 'PRESENT_TECHNICAL_ONLY':
                continue
            for name in topic.get('families', ()):
                if name not in families:
                    raise RuntimeError('Editorial topic without persisted family: ' + name)
                topic_review.append({
                    'page': page, 'topic': topic.get('topic'), 'family': name,
                    'classification': families[name]['classification'],
                    'href': families[name]['href'],
                    'human_editorial_acceptance': 'PENDING',
                })
    # An expected but absent analysis is not a zero-valued measurement.
    # These projections originate from the existing execution/editorial receipt,
    # and are separate from the physical inventory of SQLite tables.
    absent_topics = []
    for page, topics in editorial_receipt.get('pages', {}).items():
        for topic in topics:
            if topic.get('state') not in {'SOURCE_ABSENT', 'PROCESSING_NOT_EXECUTED'}:
                continue
            for family in topic.get('families', ()):
                absent_topics.append({
                    'page': page, 'family': family,
                    'table_present': family in tables,
                    'persisted_rows': len(tables.get(family, ())),
                    'state': topic['state'],
                    'source_component': topic.get('component'),
                    'persisted_execution_state': topic.get('persisted_execution_state'),
                    'limitation': topic.get('limitation'),
                })
    counts = dict(sorted(Counter(f['classification'] for f in families.values()).items()))
    open_gaps = sorted(
        (f for f in families.values() if f['classification'] in {
            'REQUIRES_EXECUTIVE_REVIEW', 'REQUIRES_ANALYTICAL_REVIEW', 'POLICY_REVIEW_REQUIRED'}),
        key=lambda f: (0 if f['decision_relevance'] == 'HIGH'
                       else 1 if f['decision_relevance'] == 'MEDIUM' else 2,
                       f['family'])
    )
    network_receipt = coverage_receipt.get('pages', {}).get('rede.html', {})
    sidecars = [
        {'source': 'rede:network_passive', 'source_kind': 'verified_network_evidence',
         'page': 'rede.html', 'href': 'rede.html#network-evidence-inventory',
         'records_verified': network_receipt.get('verified_network_observations'),
         'state': 'VERIFIED_ROWS' if network_receipt.get('verified_network_observations') else 'NOT_VERIFIED_OR_ABSENT'},
        {'source': 'rede:network_probes', 'source_kind': 'verified_network_evidence',
         'page': 'rede.html', 'href': 'rede.html#network-evidence-inventory',
         'records_verified': network_receipt.get('verified_network_probes'),
         'state': 'VERIFIED_ROWS' if network_receipt.get('verified_network_probes') else 'NOT_VERIFIED_OR_ABSENT'},
        {'source': 'capture:sidecars', 'source_kind': 'structural_evidence_projection',
         'page': 'extracao.html', 'href': 'extracao.html#presentation-records',
         'state': editorial_receipt.get('capture_state', 'NOT_VERIFIED')},
        {'source': 'crux:history', 'source_kind': 'validated_historical_projection',
         'page': 'performance.html', 'href': 'performance.html#presentation-records',
         'state': editorial_receipt.get('history_state', 'NOT_VERIFIED')},
    ]

    receipt = {
        'contract': 'RASAI-PRESENTATION-EDITORIAL-TRIAGE-722-V1',
        'source_reference': 'audit.db + materialized source receipts',
        'review_method': 'DETERMINISTIC_POLICY_AND_PERSISTED_PROJECTIONS',
        'families_total': len(families),
        'families_with_rows': sum(f['row_count'] > 0 for f in families.values()),
        'families_classified': len(families),
        'technical_only_topics_reviewed': len(topic_review),
        'classification_counts': counts,
        'open_decision_gaps': [f['family'] for f in open_gaps],
        'sidecar_projections': sidecars,
        'technical_only_topics': topic_review,
        'absent_or_unexecuted_topics': absent_topics,
        'families': families,
        'competitive_comparability': {
            'source': 'serp_competitive_analyses + serp_competitive_pages + serp_competitive_results',
            'observations': _competitive_evidence_assessment(tables),
            'competitive_ranking_or_market_conclusion': 'INDETERMINATE',
            'editorial_interpretation_certified': False,
            'human_editorial_acceptance': 'PENDING',
        },
        'certifies_editorial_completeness': False,
        'human_editorial_acceptance': 'PENDING',
        'limitations': [
            'A contagem de anexos, tópicos ou campos não certifica suficiência editorial.',
            'Status por linha é apenas o valor persistido, não o resultado inferido da auditoria.',
            'Classificação de relevância é triagem editorial determinística, não parecer humano.',
            'Dados ausentes não equivalem a nota zero, resultado negativo nem etapa concluída.',
        ],
    }

    rendered = defaultdict(str)
    rendered['index'] += (
        '<section data-editorial-review="index"><h2>Revisão da cobertura editorial</h2>'
        '<p class="rf">Inventário determinístico das fontes persistidas. '
        'Os estados identificam projeções existentes ou revisões pendentes; '
        'não certificam completude executiva e não recalculam pontuação.</p>'
        + kv([('Famílias de fontes inventariadas', len(families)),
              ('Famílias com registros', receipt['families_with_rows']),
              ('Tópicos anteriormente apenas técnicos classificados', len(topic_review)),
              ('Análises ausentes ou não executadas declaradas', len(absent_topics)),
              ('Fontes com revisão decisória pendente', len(open_gaps))])
        + '<p><a class="tech-link" href="anexos/dados-de-apoio/editorial-review.json">'
          'Consultar recibo integral por fonte</a></p>'
    )
    if open_gaps:
        rendered['index'] += '<details class="in"><summary>Fontes prioritárias para aprofundamento editorial</summary>'
        rendered['index'] += _simple_table(open_gaps)
        rendered['index'] += '</details>'
    rendered['index'] += '</section>'
    for page, _ in PAGES:
        listed = [f for f in families.values() if f['page'] == page + '.html']
        if not listed:
            continue
        listed.sort(key=lambda f: f['family'])
        rendered[page] += (
            '<section data-editorial-review="' + text(page) + '">'
            '<details class="in"><summary>Mapa de origem e cobertura editorial por fonte'
            ' (' + text(len(listed)) + ')</summary>'
            '<p class="rf">Classificação e rastreabilidade por tabela desta página. '
            'Acesso técnico não comprova recomendação aprovada, nem comprova '
            'que uma atividade ausente tenha sido executada.</p>'
            + _simple_table(listed)
            + '</details></section>'
        )
    return rendered, receipt
