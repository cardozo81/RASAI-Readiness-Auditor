"""Resolve the client disposition using only the persisted source identity."""
from collections import defaultdict

_KEYS = {
    'improvement_intelligence_recommendations': ('DEEP_ANALYSIS', 'recommendation_id'),
    'recommendations': ('DETERMINISTIC', 'recommendation_id'),
    'content_remediation_suggestions': ('CONTENT_AI', 'suggestion_id'),
    'jsonld_remediation_suggestions': ('JSONLD', 'suggestion_id'),
}


class Governance:
    def __init__(self, decisions):
        self.by_source = defaultdict(list)
        for row in decisions:
            if row.get('source_kind') and row.get('source_id'):
                self.by_source[row['source_kind'], row['source_id']].append(row)

    def disposition(self, table, row):
        if table in _KEYS:
            kind, field = _KEYS[table]
            key = kind, row.get(field)
        else:
            key = row.get('source_kind'), row.get('source_id')
        matches = self.by_source.get(key, ())
        if any(r.get('decision') == 'REJECTED' or r.get('target_class') == 'AUDITOR_INTERNAL' for r in matches):
            return 'Excluída do plano do cliente'
        if len(matches) == 1 and matches[0].get('decision') == 'ACCEPTED':
            return 'Aceita pela governança'
        if matches:
            return 'Verificar decisão e responsabilidade'
        return 'Sem decisão de governança vinculada'

    def excluded(self, table, row):
        return self.disposition(table, row) == 'Excluída do plano do cliente'
