"""Reconcile persisted attempts, not tasks, forecasts, or native-usage components."""
from decimal import Decimal, InvalidOperation


def amount(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except InvalidOperation:
        return None


def reconcile(tables):
    entries, warnings, seen = [], [], set()
    ledgers = ('ai_provider_attempts', 'content_remediation_attempts')
    for table in ledgers:
        for row in tables.get(table, ()):
            identity = row.get('attempt_id')
            if identity is None or identity in seen:
                warnings.append('Identidade de tentativa ausente/duplicada; total parcial')
                continue
            seen.add(identity)
            entries.append((table, row))
    for row in tables.get('perplexity_search_runs', ()):
        if row.get('attempt_id') in seen:
            continue  # result of an already counted operational envelope
        # A run without its envelope is visible, but cannot prove distinct consumption.
        warnings.append('Perplexity sem envelope correlacionado; custo excluído do total conciliado')
    totals, output = {}, []
    for table, row in entries:
        observed, estimated = amount(row.get('observed_cost')), amount(row.get('estimated_cost'))
        selected = observed if observed is not None else estimated
        kind = 'observado' if observed is not None else 'estimado'
        currency = (row.get('observed_cost_currency') or row.get('cost_currency')) if observed is not None else row.get('cost_currency')
        if selected is None or not currency:
            warnings.append('Tentativa sem custo/moeda mensurável; total parcial')
        else:
            group = totals.setdefault(currency, {'observado': None, 'estimado': None, 'conciliado': Decimal(0)})
            group[kind] = (group[kind] if group[kind] is not None else Decimal(0)) + selected
            group['conciliado'] += selected
        output.append({'source': table, 'attempt_id': row.get('attempt_id'), 'kind': kind if selected is not None else 'N/D',
                       'amount': str(selected) if selected is not None else None, 'currency': currency})
    return {'attempt_count': len(entries), 'totals': {c: {k: str(v) if v is not None else None for k, v in values.items()} for c, values in totals.items()},
            'entries': output, 'warnings': sorted(set(warnings)),
            'coverage': 'Parcial' if warnings else ('Medido' if entries else 'Não medido'),
            'method': 'Tentativas únicas; observado prevalece; componentes nativos e forecast não somados; sem inferência de tokens.'}
