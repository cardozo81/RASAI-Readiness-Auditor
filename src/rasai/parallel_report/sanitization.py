"""Context-aware redaction of credentials without erasing technical identity."""
from hashlib import sha256
import json
import re

from rasai.report_opaque_projection import (
    UNPARSEABLE_STATUS, has_opaque_marker, opaque_metadata,
)

SENSITIVE = re.compile(r'(^|[_-])(api[_-]?key|secret|password|passwd|authorization|cookie|access[_-]?token|refresh[_-]?token|credential)(s|[_-]|$)', re.I)
ASSIGNMENT = re.compile(r'(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization|set-cookie|cookie)\s*[=:]\s*)[^\s,;<>]+')
TOKEN = re.compile(r'\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}')
# Exact metadata fields, never generic *cookie* exemptions.
SAFE_COOKIE_METADATA = frozenset({'cookie_attribution_id', 'cookie_ref', 'cookie_name_display', 'set_cookie_index'})
SELECTOR_FIELDS = frozenset({'selector', 'css_selector', 'element_selector'})
# Only explicit class/ID selector syntax is sufficient context for sk-* names.
CSS_IDENT = re.compile(r'^[.#][A-Za-z_][A-Za-z0-9_-]*(?:[.#][A-Za-z_][A-Za-z0-9_-]*)*$')


def _stable_reference(value):
    """Retain equality between ambiguous references without publishing raw data."""
    return '[REF-' + sha256(str(value).encode('utf-8')).hexdigest()[:20] + ']'


def _text(value, selector=False):
    value = re.sub(r'(?is)<input\b[^>]*(?:password|api[_-]?key|access[_-]?token|secret)[^>]*>', '[REDACTED INPUT]', value)
    value = re.sub(r'(?i)\bBearer\s+[^\s<>"\']+', 'Bearer [REDACTED]', value)
    value = re.sub(r'(https?://)[^/@\s:]+:[^/@\s]+@', r'\1[REDACTED]@', value)
    value = ASSIGNMENT.sub(r'\1[REDACTED]', value)
    # A CSS class .sk-something is not an API key; unqualified sk-* remains secret-shaped.
    if not selector or not CSS_IDENT.fullmatch(value):
        value = TOKEN.sub('[REDACTED]', value)
    return value


def sanitize(value, key=''):
    field = str(key).lower()
    if field == 'encrypted_content':
        return opaque_metadata(value)
    if field in SAFE_COOKIE_METADATA:
        if field == 'set_cookie_index':
            return value if type(value) is int and value >= 0 else '[REDACTED]'
        if not isinstance(value, str) or not value or len(value) > 512:
            return _stable_reference(value) if value is not None else None
        clean = _text(value)
        # Ambiguous or redacted metadata gets a deterministic, non-reversible alias.
        if clean != value or any(x in value for x in ('\r', '\n', ';', '=')):
            return _stable_reference(value)
        return clean
    if SENSITIVE.search(field):
        return '[REDACTED]'
    if isinstance(value, bytes):
        return {'binary_bytes': len(value), 'coverage': 'Parcial — conteúdo binário não publicado'}
    if isinstance(value, dict):
        return {k: sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, key) for v in value]
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(('{', '[')):
        try:
            return sanitize(json.loads(value), key)
        except (ValueError, TypeError):
            pass
    if has_opaque_marker(value):
        # Invalid or unstructured opaque provider content cannot be safely
        # split into individual fields. Do not publish any of its bytes.
        return UNPARSEABLE_STATUS
    return _text(value, selector=field in SELECTOR_FIELDS)
