"""Generate or reuse the verified offline presentation for one audit."""
from datetime import datetime, timezone
import json
import shutil
from pathlib import Path
from . import __version__
from .artifact_reader import confined, inventory, tree_digest, digest
from .sqlite_reader import read_database, quiescent, logical_digest
from .read_model import build, destination
from .crossrefs import link_records
from .cost_reconciliation import reconcile
from .evidence_index import references
from .sanitization import sanitize
from .thresholds import load
from .parity import compare
from .render import render
from .capture_gallery import package_captures, capture_gallery_html
from .publication import (
    CONTRACT, DIRECTORY, MANIFEST, compatible_manifest, find_package,
    historical_directories, publication_work, publish,
)

EXPECTED = ('audits', 'page_snapshots', 'evidence', 'scores', 'findings', 'directed_analysis_actions', 'ai_provider_attempts', 'content_remediation_attempts', 'perplexity_search_runs')


def generate(audit_dir):
    root = Path(audit_dir).resolve(strict=True)
    database = confined(root, 'audit.db')
    quiescent(database)
    base = root / DIRECTORY
    with publication_work(root) as (stage, previous):
        quiescent(database)
        before = inventory(root)
        logical_before = logical_digest(database)
        historical = historical_directories(base)
        package = find_package(base, historical, before, logical_before)
        if package is not None and package[0] == base and not historical:
            return base
        stage.mkdir()
        if package is None:
            manifest = _render_package(root, database, before, logical_before, stage)
        else:
            directory, manifest = package
            for name in [*manifest['generated_files'], MANIFEST]:
                target = stage / name
                target.parent.mkdir(exist_ok=True, parents=True)
                shutil.copy2(confined(directory, name), target)
        after = inventory(root)
        quiescent(database)
        if before != after or logical_before != logical_digest(database):
            raise RuntimeError('Source changed before presentation publication')
        if package is None:
            manifest['source_tree_digest_after'] = tree_digest(after)
            (stage / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        if compatible_manifest(stage, after, logical_before) is None:
            raise RuntimeError('Incomplete staged presentation')
        publish(stage, base, previous)
    return base


def _render_package(root, database, before, logical_before, output):
    tables, schema = read_database(database)
    from .annex_payloads import build_table_annexes, use_table_annexes, collect_payloads
    table_annexes, table_payloads = build_table_annexes(tables)
    records = build(tables, schema, table_annexes)
    links, ambiguous = link_records(records)
    evidence, calculated = references(tables, root)
    costs, parity = reconcile(tables), compare(tables, root)
    missing = [name + ': Não medido — não disponível nesta versão' for name in EXPECTED if name not in tables]
    required_columns = {'scores': ('value', 'coverage', 'confidence', 'dimension', 'device'),
                        'evidence': ('artifact_reference', 'snapshot_id'),
                        'directed_analysis_actions': ('action_id', 'source_id', 'validation_steps_json')}
    for table, columns in required_columns.items():
        if table in schema:
            missing.extend(f'{table}.{column}: N/D — coluna não disponível nesta versão'
                           for column in columns if column not in schema[table]['columns'])
    generated_at = datetime.now(timezone.utc).isoformat()
    for value in calculated:
        value['generated_at'] = generated_at
    (output / 'assets').mkdir()
    (output / 'anexos').mkdir()
    (output / 'anexos' / 'dados-de-apoio').mkdir()
    assets = Path(__file__).parent / 'assets'
    for name in ('site.css', 'app.js', 'thresholds.json'):
        (output / 'assets' / name).write_bytes((assets / name).read_bytes())
    from .catalog_context import catalog_context
    from .scope_context import scope_context
    from .presentation_labels import timezone_for_records

    timezone_name, _ = timezone_for_records(records)
    from .capture_projection import project_capture
    from .executive_evidence import summaries
    capture_projection = project_capture(root, tables, before)
    with collect_payloads() as payload_annexes, use_table_annexes(table_annexes):
        supplements = scope_context(root, tables, timezone_name, costs, capture_projection)
        summary_html, editorial_receipt = summaries(root, tables, before, records, capture_projection)
        from .analytical_views import build_analytical_views
        analytical_html, analytical_receipt = build_analytical_views(tables, records, schema, timezone_name)
        editorial_receipt['analytical'] = analytical_receipt
        # A family may have analytical fields even when it has no executive
        # interpretation. Preserve the legacy receipt state and add the precise
        # representation level instead of calling every routed family technical-only.
        for page, topics in editorial_receipt['pages'].items():
            for topic in topics:
                scopes = [analytical_receipt.get(page, {}).get(name, {})
                          for name in topic.get('families', ())]
                has_fields = any(scope.get('direct_fields') for scope in scopes)
                topic['representation_level'] = (
                    'PRESENT_EXECUTIVE_SUMMARY' if topic['state'] == 'PRESENT_SUMMARIZED'
                    else 'PRESENT_ANALYTICAL_FIELDS' if has_fields
                    else 'NOT_EXECUTED' if topic['state'] == 'PROCESSING_NOT_EXECUTED'
                    else 'TECHNICAL_DETAIL_ONLY' if topic['state'] == 'PRESENT_TECHNICAL_ONLY'
                    else topic['state'])
        for page, body in analytical_html.items():
            summary_html[page] += body
        if (capture_projection['state'] == 'SOURCE_INTEGRITY_MISMATCH'
                or editorial_receipt['history_state'] == 'SOURCE_INTEGRITY_MISMATCH'
                or editorial_receipt['overview_state'] == 'SOURCE_INTEGRITY_MISMATCH'):
            raise RuntimeError('Source integrity mismatch; presentation publication refused')
        for page, body in summary_html.items():
            supplements[page] += body
        visual_previews = package_captures(root, tables.get('page_snapshots', ()), output, before)
        supplements['extracao:visual'] = capture_gallery_html(
            tables.get('page_snapshots', ()), visual_previews, timezone_name)
        audit = next(iter(tables.get('audits', ())), {})
        for page, body in catalog_context(root, logical_before, audit.get('audit_id'), tables, timezone_name).items():
            supplements[page] += body
        from .evidence_coverage import build_coverage
        coverage_html, coverage_receipt = build_coverage(root, audit.get('audit_id'), tables)
        supplements.update(coverage_html)
        from .execution_context import build_execution_context
        execution_html, execution_receipt = build_execution_context(tables, coverage_receipt, timezone_name)
        supplements.update(execution_html)
        coverage_receipt['execution'] = execution_receipt
        coverage_receipt['editorial'] = editorial_receipt
        from .editorial_review import build_editorial_review
        review_html, review_receipt = build_editorial_review(
            tables, editorial_receipt, analytical_receipt, table_annexes, coverage_receipt)
        for page, body in review_html.items():
            supplements[page] += body
        (output / 'anexos' / 'dados-de-apoio' / 'editorial-review.json').write_text(
            json.dumps(review_receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        (output / 'anexos' / 'dados-de-apoio' / 'evidence-coverage.json').write_text(
            json.dumps(coverage_receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        pages = render(records, links, tables, sanitize(evidence), sanitize(calculated), costs, parity, load(), missing, supplements)
    for filename, content in payload_annexes.items():
        prior = table_payloads.get(filename)
        if prior is not None and prior != content:
            raise RuntimeError('SHA-256 annex namespace collision')
        (output / 'anexos' / filename).write_bytes(content)
    from rasai.report_presentation import humanize_module_references_html
    for name, html in pages.items():
        html = humanize_module_references_html(html)
        # Only visible copy is humanized; SQLite and annex JSON remain exact.
        # retain the precise persisted bytes and any original punctuation.
        (output / name).write_text(html.replace('\u2014', '-'), encoding='utf-8')
    for filename, content in table_payloads.items():
        (output / 'anexos' / filename).write_bytes(content)
    coverage_map = json.loads((assets / 'coverage-map.json').read_text(encoding='utf-8'))
    # The source template can describe a technical filename as topic components.
    # Emit the same canonical_pages file contract, with resolved HTML filenames.
    coverage_map['canonical_pages'] = {
        name: ['-'.join(page['page_parts'])+'.html' if isinstance(page,dict) else page for page in pages]
        for name,pages in coverage_map['canonical_pages'].items()
    }
    from .page_views import SECTIONS
    from .catalog_context import STRUCTURED
    from .governance import Governance
    # A route is not automatically a summary, and a summary is not a decision.
    editorial_fields = {}
    for sections in SECTIONS.values():
        for _, sources, fields in sections:
            for source in sources:
                editorial_fields.setdefault(source, set()).update(key for key, _ in fields)
    for specs in STRUCTURED.values():
        for _, source, fields, _, _ in specs:
            editorial_fields.setdefault(source, set()).update(key for key, _ in fields)
    editorial_fields.update({
        'audits': {'audit_id', 'status', 'completion_status'},
        'audit_targets': {'normalized_origin', 'input_url'},
        'scores': {'value', 'coverage', 'confidence', 'dimension'},
        'recommendation_governance': {'decision', 'source_id'},
        'directed_analysis_actions': {'title', 'source_id', 'priority'},
        'directed_analysis_runs': {'strategic_summary_json', 'roadmap_json', 'status'},
    })
    governance = Governance(tables.get('recommendation_governance', ()))
    governed_families = {
        'directed_analysis_actions', 'recommendations',
        'improvement_intelligence_recommendations',
        'content_remediation_suggestions', 'jsonld_remediation_suggestions',
    }
    family_coverage = {}
    for source, rows in tables.items():
        page = destination(source)
        fields = editorial_fields.get(source, set())
        has_summary = bool(rows and fields and any(
            isinstance(row, dict) and any(row.get(field) is not None for field in fields)
            for row in rows))
        has_conclusion = (
            source == 'scores' and any(row.get('value') is not None for row in rows)
            or source == 'recommendation_governance' and any(
                row.get('decision') in {'ACCEPTED', 'REJECTED'} for row in rows)
            or source in governed_families and any(
                governance.disposition(source, row) == 'Aceita pela governança'
                for row in rows)
        )
        family_coverage[source] = {
            'page': page + '.html' if page is not None else None,
            'representation': 'editorial' if has_summary else (
                'navigable-record' if page is not None else 'technical-only'),
            'levels': {
                'preserved_annex': True,
                'navigable_record': page is not None and bool(rows),
                'editorial_summary': has_summary,
                'conclusion_or_decision_present': bool(has_conclusion),
            },
            'row_count': len(rows),
            'columns': schema[source]['columns'],
        }
    coverage_map['families'] = family_coverage
    # Explicit projection receipts supersede route/field heuristics where available.
    for source, entry in family_coverage.items():
        uses = [(page, topic) for page, topics in editorial_receipt['pages'].items()
                for topic in topics if source in topic.get('families', ())]
        if uses:
            summarized = any(t['state'] == 'PRESENT_SUMMARIZED' for _,t in uses)
            entry['levels']['editorial_summary'] = summarized
            entry['representation'] = 'editorial' if summarized else 'navigable-record'
            entry['editorial_uses'] = [dict(page=p, topic=t['topic'], state=t['state']) for p,t in uses]
    coverage_map['editorial'] = editorial_receipt
    coverage_map['editorial_review'] = {
        'contract': review_receipt['contract'],
        'families_classified': review_receipt['families_classified'],
        'classification_counts': review_receipt['classification_counts'],
        'certifies_editorial_completeness': False,
    }
    for page, families in analytical_receipt.items():
        for source, scope in families.items():
            entry = family_coverage[source]
            entry['analytical_projection'] = scope
            entry['adequate_representation_certified'] = False
            entry['levels']['analytical_field_projection'] = bool(scope['direct_fields'])
    (output / 'anexos' / 'dados-de-apoio' / 'coverage-map.json').write_text(json.dumps(coverage_map, ensure_ascii=False, indent=2), encoding='utf-8')
    generated = {p.relative_to(output).as_posix(): digest(p) for p in output.rglob('*') if p.is_file()}
    return {
        'contract': CONTRACT, 'version': 1, 'generator_version': __version__,
        'audit_id': sanitize(tables.get('audits', [{}])[0].get('audit_id')) if tables.get('audits') else None,
        'generated_at': generated_at, 'timezone': 'UTC',
        'source_db_relative_path': 'audit.db', 'source_db_sha256': before['audit.db'],
        'source_db_logical_sha256': logical_before,
        'source_tree_digest_before': tree_digest(before),
        'source_inventory': before, 'tables_read': list(tables),
        'annex_contract': 'CONTENT_SHA256_V1', 'table_annexes': table_annexes,
        'columns_read': {name: item['columns'] for name, item in schema.items()},
        'artifacts_read': sanitize(evidence), 'calculated_values': sanitize(calculated),
        'warnings': costs['warnings'] + [f'Ambiguous identifier values: {ambiguous}', 'HTML parity and visual human acceptance not certified', 'Credentials are redacted; sanitized payload is not the literal source'],
        'missing_data': missing, 'parity_differences': parity, 'cost_reconciliation': costs,
        'generated_files': sorted(generated), 'sha256_per_file': generated,
        'payload_annexes': sorted(payload_annexes),
        'visual_previews': visual_previews,
        'manifest_self_hash': 'Excluded to avoid recursive hashing', 'page_count': len(pages),
        'external_requests': 0, 'ai_calls': 0, 'source_writes': 0, 'score_recomputed': False,
        'integrity': 'PASS',
    }
