"""Only unambiguous persisted identifiers produce bidirectional links."""
from collections import defaultdict
from .read_model import thaw


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
            if key.endswith('_id') and isinstance(value, str):
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
