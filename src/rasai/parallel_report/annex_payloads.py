"""Per-publication content-addressed annexes for unstructured source payloads.

Never mutate audit evidence. HTML displays source-backed field summaries and a
verifiable, offline relative link to the exact sanitized JSON payload.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import json

_ACTIVE = ContextVar('rasai_presentation_payload_annexes', default=None)


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
