"""Generate or reuse the verified offline presentation for one audit."""
from datetime import datetime, timezone
import json
import shutil
from pathlib import Path
from . import __version__
from .artifact_reader import confined, inventory, tree_digest, digest
from .sqlite_reader import read_database, quiescent
from .read_model import build, destination
from .crossrefs import link_records
from .cost_reconciliation import reconcile
from .evidence_index import references
from .sanitization import sanitize
from .thresholds import load
from .parity import compare
from .render import render
from .publication import (
    CONTRACT, DIRECTORY, MANIFEST, compatible_manifest, find_package,
    historical_directories, publication_work, publish,
)

EXPECTED = ('audits', 'page_snapshots', 'evidence', 'scores', 'findings', 'directed_analysis_actions', 'ai_provider_attempts', 'content_remediation_attempts', 'perplexity_search_runs')


def generate(audit_dir):
    from rasai.catalog_report_site import _sqlite_logical_digest

    root = Path(audit_dir).resolve(strict=True)
    database = confined(root, 'audit.db')
    quiescent(database)
    base = root / DIRECTORY
    with publication_work(root) as (stage, previous):
        quiescent(database)
        before = inventory(root)
        logical_before = _sqlite_logical_digest(database)
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
        if before != after or logical_before != _sqlite_logical_digest(database):
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
    records = build(tables, schema)
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
    assets = Path(__file__).parent / 'assets'
    for name in ('site.css', 'app.js', 'thresholds.json'):
        (output / 'assets' / name).write_bytes((assets / name).read_bytes())
    pages = render(records, links, tables, sanitize(evidence), sanitize(calculated), costs, parity, load(), missing)
    for name, html in pages.items():
        (output / name).write_text(html, encoding='utf-8')
    from hashlib import sha256
    for table, rows in tables.items():
        filename = sha256(table.encode()).hexdigest() + '.json'
        (output / 'anexos' / filename).write_text(json.dumps(sanitize(rows), ensure_ascii=False, indent=2), encoding='utf-8')
    coverage_map = json.loads((assets / 'coverage-map.json').read_text(encoding='utf-8'))
    # The source template can describe a technical filename as topic components.
    # Emit the same canonical_pages file contract, with resolved HTML filenames.
    coverage_map['canonical_pages'] = {
        name: ['-'.join(page['page_parts'])+'.html' if isinstance(page,dict) else page for page in pages]
        for name,pages in coverage_map['canonical_pages'].items()
    }
    coverage_map['families'] = {table: {'page': destination(table) + '.html', 'row_count': len(rows), 'columns': schema[table]['columns']} for table, rows in tables.items()}
    (output / 'assets' / 'coverage-map.json').write_text(json.dumps(coverage_map, ensure_ascii=False, indent=2), encoding='utf-8')
    generated = {p.relative_to(output).as_posix(): digest(p) for p in output.rglob('*') if p.is_file()}
    return {
        'contract': CONTRACT, 'version': 1, 'generator_version': __version__,
        'audit_id': sanitize(tables.get('audits', [{}])[0].get('audit_id')) if tables.get('audits') else None,
        'generated_at': generated_at, 'timezone': 'UTC',
        'source_db_relative_path': 'audit.db', 'source_db_sha256': before['audit.db'],
        'source_db_logical_sha256': logical_before,
        'report_catalog_tree_digest': tree_digest(before, 'report-catalog/'),
        'source_tree_digest_before': tree_digest(before),
        'source_inventory': before, 'tables_read': list(tables),
        'columns_read': {name: item['columns'] for name, item in schema.items()},
        'artifacts_read': sanitize(evidence), 'calculated_values': sanitize(calculated),
        'warnings': costs['warnings'] + [f'Ambiguous identifier values: {ambiguous}', 'HTML parity and visual human acceptance not certified', 'Credentials are redacted; sanitized payload is not the literal source'],
        'missing_data': missing, 'parity_differences': parity, 'cost_reconciliation': costs,
        'generated_files': sorted(generated), 'sha256_per_file': generated,
        'manifest_self_hash': 'Excluded to avoid recursive hashing', 'page_count': len(pages),
        'external_requests': 0, 'ai_calls': 0, 'source_writes': 0, 'score_recomputed': False,
        'integrity': 'PASS',
    }
