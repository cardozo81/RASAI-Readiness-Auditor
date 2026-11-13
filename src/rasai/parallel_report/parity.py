"""Parity with the persisted canonical snapshot, never with guessed HTML text."""
from pathlib import Path
from .artifact_reader import confined
from .sqlite_reader import read_database
from .cost_reconciliation import reconcile


def compare(tables, root):
    reference = 'report-catalog/integrity/audit-snapshot.db'
    try:
        snapshot = confined(root, reference)
    except (OSError, ValueError):
        return {'status': 'PENDING', 'reference': reference, 'reason': 'Snapshot canônico ausente/inseguro; paridade HTML não certificada'}
    try:
        canonical, _ = read_database(snapshot)
    except (OSError, ValueError):
        return {'status': 'PENDING', 'reference': reference, 'reason': 'Snapshot canônico não está selado'}
    result = {'reference': reference, 'comparisons': {}, 'differences': [], 'html_parity': 'NOT_VERIFIED'}
    for table in ('scores', 'web_performance_observations', 'synthetic_apdex_summaries', 'synthetic_ux_apdex_summaries', 'findings', 'directed_analysis_actions', 'recommendations'):
        left, right = tables.get(table), canonical.get(table)
        if left is None or right is None:
            status = 'N/D'
        else:
            import json
            normalize = lambda rows: sorted(json.dumps(row, sort_keys=True, default=str) for row in rows)
            status = 'PASS' if normalize(left) == normalize(right) else 'DIFFERENT'
        result['comparisons'][table] = {'status': status, 'source_count': None if left is None else len(left), 'catalog_count': None if right is None else len(right)}
        if status == 'DIFFERENT':
            result['differences'].append(table)
    source_cost, catalog_cost = reconcile(tables), reconcile(canonical)
    status = 'PASS' if source_cost == catalog_cost else 'DIFFERENT'
    result['comparisons']['costs'] = {'status': status, 'source': source_cost['totals'], 'catalog': catalog_cost['totals']}
    if status == 'DIFFERENT':
        result['differences'].append('costs')
    result['status'] = 'DIFFERENT' if result['differences'] else 'PASS_AVAILABLE_SNAPSHOT_FIELDS'
    return result
