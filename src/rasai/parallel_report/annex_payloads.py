"""Per-publication content-addressed annexes for unstructured source payloads.

Never mutate audit evidence. HTML displays source-backed field summaries and a
verifiable, offline relative link to the exact sanitized JSON payload.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import json
from .sanitization import sanitize

_ACTIVE = ContextVar('rasai_presentation_payload_annexes', default=None)

# Keep the table-to-content mapping scoped to this publication, so two
# concurrent audits cannot leak their annex identities into one another.
_TABLE_FILES = ContextVar('rasai_presentation_table_annexes', default=None)


def build_table_annexes(tables):
    """Serialize sanitized rows once; filename hashes the exact UTF-8 bytes.

    Identical JSON payloads deliberately share a file. The returned table map
    retains a distinct entry for every source family, including empty tables.
    """
    names, content = {}, {}
    for table, rows in sorted(tables.items()):
        data = json.dumps(sanitize(rows), ensure_ascii=False, indent=2).encode('utf-8')
        filename = sha256(data).hexdigest() + '.json'
        prior = content.setdefault(filename, data)
        if prior != data:
            raise RuntimeError('SHA-256 table annex collision')
        names[table] = filename
    return names, content


@contextmanager
def use_table_annexes(names):
    token = _TABLE_FILES.set(dict(names))
    try:
        yield
    finally:
        _TABLE_FILES.reset(token)


def table_annex_filename(table):
    names = _TABLE_FILES.get()
    if names is not None:
        # A source table missing from the sealed map is a renderer bug, not a
        # reason to construct a dangling filename from the table name.
        return names[table]
    # Standalone projections may run without package generation.
    return sha256(table.encode('utf-8')).hexdigest() + '.json'



@contextmanager
def collect_payloads():
    payloads = {}
    token = _ACTIVE.set(payloads)
    try:
        yield payloads
    finally:
        _ACTIVE.reset(token)


def register_payload(value):
    """Return (relative basename, content digest), or None outside generation."""
    pending = _ACTIVE.get()
    if pending is None:
        return None
    data = json.dumps(value, ensure_ascii=False, indent=2, default=str).encode('utf-8')
    digest = sha256(data).hexdigest()
    name = digest + '.json'
    previous = pending.setdefault(name, data)
    if previous != data:
        raise RuntimeError('SHA-256 payload collision')
    return name, digest
