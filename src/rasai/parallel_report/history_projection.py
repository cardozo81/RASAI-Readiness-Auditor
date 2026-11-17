"""Read-only CrUX history with dataset/hash/period/scope reconciliation."""
from collections import defaultdict
from datetime import date
import json
import math
import sqlite3

from .artifact_reader import confined
from .capture_projection import read_source, public_data
from .sqlite_reader import connect


def crux_history(root, tables, inventory):
    runs = [r for r in tables.get('standards_service_runs', ()) if r.get('service_id') == 'crux-history']
    result = dict(state='SOURCE_ABSENT', sources=[], groups=[], limitations=[])
    if not runs:
        return result
    ids = []
    for row in runs:
        from .capture_projection import object_value
        datasets = object_value(row.get('details_json')).get('datasets', [])
        if isinstance(datasets, list):
            ids.extend(x for x in datasets if isinstance(x, str))
    if not ids:
        result['limitations'].append('NO_PERSISTED_DATASET_REFERENCE')
        return result
    ref = 'artifacts/observability/observability.db'
    try:
        database = confined(root, ref)
        # The generator protects the full source inventory before/after publication.
        if database.stat().st_size > 64 * 1024 * 1024:
            result['state'] = 'RESOURCE_LIMIT'
            return result
        with connect(database) as con:
            con.set_progress_handler(lambda: 1, 2_000_000)
            datasets = con.execute('SELECT * FROM datasets LIMIT 201').fetchall()
            if len(datasets) > 200:
                raise ValueError('dataset limit')
            groups = defaultdict(list)
            for dataset in datasets:
                dataset = dict(dataset)
                if dataset['dataset_id'] not in ids:
                    continue
                raw, state = read_source(root, dataset['artifact_path'], inventory,
                    expected=dataset.get('artifact_sha256'), limit=4_000_000)
                source = dict(dataset_id=dataset['dataset_id'], reference=dataset['artifact_path'],
                    sha256=dataset.get('artifact_sha256'), state=state,
                    sidecar_reference=ref, sidecar_sha256=inventory.get(ref))
                result['sources'].append(source)
                if raw is None:
                    continue
                try:
                    payload = json.loads(raw)
                    if payload.get('format_version') != 'RASAI-CRUX-HISTORY-001':
                        raise ValueError('history contract')
                    request = payload['request']
                    record = payload['response']['record']
                    periods = record['collectionPeriods']
                    metrics = record['metrics']
                    key = record['key']
                    points = con.execute('SELECT * FROM crux_history WHERE dataset_id=? LIMIT 2001',
                                         (dataset['dataset_id'],)).fetchall()
                    if len(points) > 2000:
                        raise ValueError('history point limit')
                    accepted = []
                    for point in points:
                        p = dict(point)
                        if p['metric'] not in {'largest_contentful_paint', 'interaction_to_next_paint',
                                                'cumulative_layout_shift'}:
                            continue
                        scope = p['target_scope']
                        target = request.get('origin' if scope == 'ORIGIN' else 'url')
                        form = request.get('formFactor')
                        if (not target or scope not in {'ORIGIN', 'URL'} or p['target'] != target
                                or key.get('origin' if scope == 'ORIGIN' else 'url') != target
                                or p['form_factor'] != form or key.get('formFactor') != form):
                            raise ValueError('history scope mismatch')
                        start, end = date.fromisoformat(p['period_start']), date.fromisoformat(p['period_end'])
                        if start > end:
                            raise ValueError('history period')
                        value = p['p75']
                        if type(value) not in (float, int) or not math.isfinite(value):
                            continue
                        verified = False
                        for i, period in enumerate(periods):
                            def stamp(v):
                                return date(v['year'], v['month'], v['day'])
                            series = metrics[p['metric']]['percentilesTimeseries']['p75s']
                            if (stamp(period['firstDate']) == start and stamp(period['lastDate']) == end
                                    and i < len(series) and float(series[i]) == value):
                                verified = True
                                break
                        if not verified:
                            raise ValueError('history normalized point mismatch')
                        accepted.append(((target, scope, form, p['metric']), p))
                    for group, point in accepted:
                        groups[group].append(point)
                except (ValueError, TypeError, KeyError, IndexError, AttributeError):
                    source['state'] = 'PROJECTION_ERROR'
                    source['limitation'] = 'HISTORY_CONTRACT_OR_PROVENANCE_MISMATCH'
            for (target, scope, form, metric), points in sorted(groups.items(), key=lambda x: str(x[0])):
                # Exact duplicate windows are one observation; conflicting values are not comparable.
                windows = defaultdict(set)
                for p in points:
                    windows[p['period_start'], p['period_end']].add(p['p75'])
                if any(len(values) != 1 for values in windows.values()):
                    result['limitations'].append('CONFLICTING_HISTORY_WINDOWS')
                    continue
                series = sorted((a, b, next(iter(values))) for (a, b), values in windows.items())
                if len(series) < 2:
                    result['limitations'].append('INSUFFICIENT_COMPARABLE_PERIODS')
                    continue
                result['groups'].append(dict(target=target, scope=scope, form_factor=form,
                    metric=metric, unit='fração' if metric == 'cumulative_layout_shift' else 'ms',
                    periods=len(series), first_start=series[0][0], first_end=series[0][1],
                    first_p75=series[0][2], last_start=series[-1][0], last_end=series[-1][1],
                    last_p75=series[-1][2], dataset_ids=sorted({p['dataset_id'] for p in points}),
                    series=[dict(period_start=a,period_end=b,p75=v) for a,b,v in series]))
    except (OSError, ValueError, sqlite3.Error):
        result['state'] = 'PROJECTION_ERROR'
        result['limitations'].append('HISTORY_SIDECAR_UNAVAILABLE_OR_INVALID')
        return public_data(result)
    states = [s['state'] for s in result['sources']]
    missing = set(ids) - {s['dataset_id'] for s in result['sources']}
    if missing:
        result['limitations'].append('REFERENCED_DATASET_ABSENT')
    result['state'] = ('SOURCE_INTEGRITY_MISMATCH' if 'SOURCE_INTEGRITY_MISMATCH' in states else
                       ('PARTIAL' if missing or result['limitations'] or any(s != 'AVAILABLE' for s in states)
                        else 'AVAILABLE') if result['groups'] else
                       'PROJECTION_ERROR' if 'PROJECTION_ERROR' in states else
                       'MATERIALIZED_NO_PERTINENT_PROJECTION' if 'AVAILABLE' in states else 'SOURCE_ABSENT')
    return public_data(result)
