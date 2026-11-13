"""Explicit one-shot generation; only a newly reserved output may be written."""
from datetime import datetime, timezone
import json
from pathlib import Path
from . import __version__
from .artifact_reader import confined, inventory, tree_digest, digest
from .sqlite_reader import read_database, quiescent
from .read_model import build, thaw, destination
from .crossrefs import link_records
from .cost_reconciliation import reconcile
from .evidence_index import references
from .sanitization import sanitize
from .thresholds import load
from .parity import compare
from .render import render

EXPECTED = ('audits', 'page_snapshots', 'evidence', 'scores', 'findings', 'directed_analysis_actions', 'ai_provider_attempts', 'content_remediation_attempts', 'perplexity_search_runs')


def reserve_output(root):
    base = root / 'report-presentation'
    if base.is_symlink() or base.is_junction():
        raise ValueError('Linked output is forbidden')
    try:
        base.mkdir(exist_ok=False)
        return base
    except FileExistsError:
        if not base.is_dir():
            raise ValueError('Output path is not a directory')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    for index in range(10000):
        candidate = base / (stamp + (f'-{index}' if index else ''))
        try:
            candidate.mkdir(exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError('Cannot reserve unique output')


def generate(audit_dir):
    root = Path(audit_dir).resolve(strict=True)
    database = confined(root, 'audit.db')
    quiescent(database)
    before = inventory(root)
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
    output = reserve_output(root)
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
    coverage_map['families'] = {table: {'page': destination(table) + '.html', 'row_count': len(rows), 'columns': schema[table]['columns']} for table, rows in tables.items()}
    (output / 'assets' / 'coverage-map.json').write_text(json.dumps(coverage_map, ensure_ascii=False, indent=2), encoding='utf-8')
    after = inventory(root)
    quiescent(database)
    if before != after:
        raise RuntimeError('Source changed during generation; output is NOT validated')
    generated = {p.relative_to(output).as_posix(): digest(p) for p in output.rglob('*') if p.is_file()}
    manifest = {
        'contract': 'RASAI-PARALLEL-REPORT-001', 'version': 1, 'generator_version': __version__,
        'audit_id': sanitize(tables.get('audits', [{}])[0].get('audit_id')) if tables.get('audits') else None,
        'generated_at': generated_at, 'timezone': 'UTC',
        'source_db_relative_path': 'audit.db', 'source_db_sha256': before['audit.db'],
        'report_catalog_tree_digest': tree_digest(before, 'report-catalog/'),
        'source_tree_digest_before': tree_digest(before), 'source_tree_digest_after': tree_digest(after),
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
    (output / '_geracao.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return output
