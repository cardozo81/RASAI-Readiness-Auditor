"""Issue #722: source-level editorial triage, not completeness certification."""
import json
import sqlite3
from hashlib import sha256

from rasai.parallel_report.editorial_review import build_editorial_review
from rasai.parallel_report.generator import generate
from rasai.parallel_report.read_model import destination, SEARCH_PAGE


def _inputs():
    tables = {
        'audits': [{'status': 'COMPLETED'}],
        'audit_fulfillment_contracts': [{'processing_status': 'COMPLETE'}],
        'ai_provider_native_usage': [{'status': 'SUCCESS', 'native_usage_quantity': 0}],
        'serp_results': [],
        'ai_task_dependency_specs': [{'id': 'tracked'}],
        'unmapped_new_source': [{'id': 'unknown'}],
    }
    names = {
        source: sha256(json.dumps(rows, ensure_ascii=False, indent=2).encode()).hexdigest()+'.json'
        for source, rows in tables.items()
    }
    editorial = {'capture_state': 'AVAILABLE', 'history_state': 'SOURCE_ABSENT',
                 'pages': {
                     'index.html': [{'topic': 'audits', 'state': 'PRESENT_TECHNICAL_ONLY',
                                     'families': ['audits']}],
                     'ia-custos.html': [{'topic': 'native usage',
                                        'state': 'PRESENT_TECHNICAL_ONLY',
                                        'families': ['ai_provider_native_usage']}],
                 }}
    return tables, names, editorial


def test_inventory_classifies_every_family_without_claiming_executive_acceptance():
    tables, names, editorial = _inputs()
    rendered, receipt = build_editorial_review(
        tables, editorial, {}, names,
        {'pages': {'rede.html': {
            'verified_network_observations': 2, 'verified_network_probes': 0}}})
    assert receipt['families_total'] == receipt['families_classified'] == len(tables)
    assert receipt['certifies_editorial_completeness'] is False
    assert receipt['human_editorial_acceptance'] == 'PENDING'
    assert len(receipt['technical_only_topics']) == 2
    assert receipt['absent_or_unexecuted_topics'] == []
    families = receipt['families']
    assert families['audits']['classification'] == 'PRESENT_CONTEXTUAL'
    assert families['audit_fulfillment_contracts']['classification'] == 'PRESENT_CONTEXTUAL'
    assert families['ai_provider_native_usage']['classification'] == 'REQUIRES_ANALYTICAL_REVIEW'
    assert families['ai_provider_native_usage']['status_field_observations'] == {'SUCCESS': 1}
    assert families['serp_results']['classification'] == 'SOURCE_EMPTY'
    assert families['ai_task_dependency_specs']['classification'] == 'TECHNICAL_BY_DESIGN'
    assert families['unmapped_new_source']['classification'] == 'POLICY_REVIEW_REQUIRED'
    assert families['unmapped_new_source']['href'] == 'anexos/' + names['unmapped_new_source']
    assert receipt['sidecar_projections'][0]['records_verified'] == 2
    assert receipt['sidecar_projections'][1]['state'] == 'NOT_VERIFIED_OR_ABSENT'
    assert 'data-editorial-review="index"' in rendered['index']
    assert 'editorial-review.json' in rendered['index']
    assert 'report-catalog' not in ''.join(rendered.values())
    assert '<pre>' not in ''.join(rendered.values())


def test_actual_summary_and_analytical_fields_take_precedence_over_triage_policy():
    tables, names, editorial = _inputs()
    editorial['pages']['ia-custos.html'] = [{
        'topic': 'resumo medido', 'state': 'PRESENT_SUMMARIZED',
        'families': ['ai_provider_native_usage']}]
    analytical = {'ia-custos.html': {
        'ai_provider_native_usage': {'direct_fields': ['native_usage_quantity']},
        'ai_task_dependency_specs': {'direct_fields': ['id']}}}
    _, receipt = build_editorial_review(tables, editorial, analytical, names,
                                       {'pages': {}})
    assert receipt['families']['ai_provider_native_usage']['classification'] == 'PRESENT_EXECUTIVE'
    assert receipt['families']['ai_task_dependency_specs']['classification'] == 'PRESENT_ANALYTICAL'
    assert receipt['families']['ai_provider_native_usage']['analytical_direct_fields'] == ['native_usage_quantity']


def test_absent_or_unexecuted_source_is_reported_separately_from_sqlite_families():
    tables, names, editorial = _inputs()
    editorial['pages']['conteudo.html'] = [{
        'topic': 'Coerência semântica', 'state': 'PROCESSING_NOT_EXECUTED',
        'families': ['semantic_coherence_assessments'],
        'component': 'CORE_AUDIT', 'persisted_execution_state': 'NOT_REQUESTED',
        'limitation': 'ABSENCE_IS_NOT_A_NEGATIVE_FINDING'}]
    _, receipt = build_editorial_review(tables, editorial, {}, names,
                                       {'pages': {}})
    assert receipt['families_total'] == len(tables)
    assert 'semantic_coherence_assessments' not in receipt['families']
    assert receipt['absent_or_unexecuted_topics'] == [{
        'page': 'conteudo.html', 'family': 'semantic_coherence_assessments',
        'table_present': False, 'persisted_rows': 0,
        'state': 'PROCESSING_NOT_EXECUTED',
        'source_component': 'CORE_AUDIT',
        'persisted_execution_state': 'NOT_REQUESTED',
        'limitation': 'ABSENCE_IS_NOT_A_NEGATIVE_FINDING'}]


def test_existing_field_projection_is_not_mislabeled_as_missing():
    tables, names, editorial = _inputs()
    editorial['pages']['ia-custos.html'] = [{
        'topic': 'Campos do uso nativo', 'state': 'PRESENT_FIELD_PROJECTION',
        'families': ['ai_provider_native_usage']}]
    _, receipt = build_editorial_review(tables, editorial, {}, names,
                                       {'pages': {}})
    item = receipt['families']['ai_provider_native_usage']
    assert item['classification'] == 'PRESENT_ANALYTICAL'
    assert item['human_editorial_acceptance'] == 'PENDING'


def test_generation_seals_editorial_review_receipt_and_keeps_sources(tmp_path):
    root = tmp_path / 'AUD-EDITORIAL-722'
    root.mkdir()
    with sqlite3.connect(root / 'audit.db') as db:
        db.executescript("""
        CREATE TABLE audits(audit_id TEXT PRIMARY KEY, status TEXT);
        INSERT INTO audits VALUES('AUD-EDITORIAL-722','PARTIAL');
        CREATE TABLE scores(score_id TEXT PRIMARY KEY, value REAL, dimension TEXT);
        INSERT INTO scores VALUES('missing',NULL,'INDEXABILITY');
        CREATE TABLE ai_provider_native_usage(id INTEGER PRIMARY KEY, native_usage_quantity REAL);
        INSERT INTO ai_provider_native_usage VALUES(1,0);
        CREATE TABLE audit_reprocess_runs(reprocess_id TEXT PRIMARY KEY, status TEXT);
        INSERT INTO audit_reprocess_runs VALUES('R-1','FAILED_RETRYABLE');
        CREATE TABLE unknown_new_family(id INTEGER PRIMARY KEY, value TEXT);
        INSERT INTO unknown_new_family VALUES(1,'only-technical-source');
        """)
    (root / 'artifacts').mkdir()
    before = sha256((root/'audit.db').read_bytes()).hexdigest()
    out = generate(root)
    manifest = json.loads((out/'_geracao.json').read_text(encoding='utf-8'))
    receipt_file = out/'anexos/dados-de-apoio/editorial-review.json'
    receipt = json.loads(receipt_file.read_text(encoding='utf-8'))
    assert manifest['generator_version'] == '0.4.24'
    assert manifest['sha256_per_file']['anexos/dados-de-apoio/editorial-review.json'] == sha256(receipt_file.read_bytes()).hexdigest()
    assert receipt['families_total'] == 5
    assert receipt['families_classified'] == 5
    assert receipt['families']['scores']['row_count'] == 1
    assert receipt['families']['scores']['classification'] in {'PRESENT_EXECUTIVE','PRESENT_ANALYTICAL','POLICY_REVIEW_REQUIRED'}
    assert receipt['families']['audit_reprocess_runs']['row_count'] == 1
    assert receipt['families']['unknown_new_family']['classification'] == 'POLICY_REVIEW_REQUIRED'
    for name, row in receipt['families'].items():
        assert row['annex'] == 'anexos/' + manifest['table_annexes'][name]
        assert (out / row['annex']).is_file()
        if destination(name):
            assert row['href'].startswith(destination(name) + '.html#source-')
    assert receipt['certifies_editorial_completeness'] is False
    assert sha256((root/'audit.db').read_bytes()).hexdigest() == before
    assert generate(root) == out


def test_competitor_fields_do_not_falsely_close_executive_gap():
    tables,names,editorial=_inputs()
    tables['serp_competitive_pages']=[{'role':'CUSTOMER', 'fetch_status':'OBSERVED'}]
    names['serp_competitive_pages']=sha256(json.dumps(tables['serp_competitive_pages'],ensure_ascii=False,indent=2).encode()).hexdigest()+'.json'
    editorial['pages'][f'{SEARCH_PAGE}.html']=[{'topic':'conteúdo observado',
        'state':'PRESENT_FIELD_PROJECTION','families':['serp_competitive_pages']}]
    analytical={f'{SEARCH_PAGE}.html':{'serp_competitive_pages':{
        'direct_fields':['role','fetch_status']}}}
    _,receipt=build_editorial_review(tables,editorial,analytical,names,{'pages':{}})
    family=receipt['families']['serp_competitive_pages']
    assert family['analytical_direct_fields']==['role','fetch_status']
    assert family['classification']=='REQUIRES_EXECUTIVE_REVIEW'
    assert 'serp_competitive_pages' in receipt['open_decision_gaps']
    assert receipt['certifies_editorial_completeness'] is False

def test_725_competitive_receipt_has_source_bound_indeterminate_observations():
    """Source pages are not automatically an executive comparison or consent."""
    tables, names, editorial = _inputs()
    tables['serp_competitive_pages'] = [{
        'observation_id': 'OBS-725', 'role': 'COMPETITOR_CANDIDATE',
        'fetch_status': 'OBSERVED', 'requested_url': 'https://candidate.example/',
    }]
    tables['serp_competitive_analyses'] = [{
        'observation_id': 'OBS-725', 'comparison_status': 'CUSTOMER_CONTENT_UNAVAILABLE',
        'gap_count': 0, 'observed_competitor_pages': 1,
    }]
    for name in ('serp_competitive_pages', 'serp_competitive_analyses'):
        names[name] = sha256(json.dumps(tables[name], ensure_ascii=False).encode()).hexdigest() + '.json'
    _, receipt = build_editorial_review(tables, editorial, {}, names, {'pages': {}})
    evidence = receipt['competitive_comparability']
    assert evidence['source'].startswith('serp_competitive_analyses')
    assert evidence['competitive_ranking_or_market_conclusion'] == 'INDETERMINATE'
    assert evidence['editorial_interpretation_certified'] is False
    assert evidence['human_editorial_acceptance'] == 'PENDING'
    assert evidence['observations'][0]['observation_id'] == 'OBS-725'
    assert evidence['observations'][0]['content_comparison_verified'] is False
    assert evidence['observations'][0]['observed_gap_count'] is None
    assert receipt['families']['serp_competitive_pages']['classification'] == 'REQUIRES_EXECUTIVE_REVIEW'
    assert receipt['certifies_editorial_completeness'] is False
