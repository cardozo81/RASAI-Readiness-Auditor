"""Only unambiguous persisted identifiers produce bidirectional links."""
from collections import defaultdict
from .read_model import thaw

# These are canonical entity owners in the inspected persistence contracts.
# Projection/extension tables may reuse the same PK as a foreign key: they must
# link to the entity, not make its identity appear ambiguous.
OWNERS = {
    'audit_id': {'audits'}, 'page_id': {'pages'}, 'snapshot_id': {'page_snapshots'},
    'finding_id': {'findings', 'improvement_intelligence_findings', 'passive_security_findings'},
    'evidence_id': {'evidence', 'request_remediation_evidence'},
    'score_id': {'scores'}, 'action_id': {'directed_analysis_actions'},
    'rule_execution_id': {'rule_executions'},
    'attempt_id': {'ai_provider_attempts', 'content_remediation_attempts'},
}


def values(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from values(item)
    elif isinstance(value, str):
        yield value


def link_records(records):
    identities = defaultdict(set)
    for record in records:
        if len(record.identity) == 1:
            key, value = record.identity[0]
            owner = key not in OWNERS or record.table in OWNERS[key]
            if owner and key.endswith('_id') and isinstance(value, str):
                identities[value].add(record.href)
    links = {r.href: set() for r in records}
    ambiguous = set()
    for record in records:
        for value in values(thaw(record.data)):
            targets = identities.get(value, set())
            if len(targets) > 1:
                ambiguous.add(value)
            elif targets:
                target = next(iter(targets))
                if target != record.href:
                    links[record.href].add(target)
                    links[target].add(record.href)
    return {k: tuple(sorted(v)) for k, v in links.items()}, len(ambiguous)
