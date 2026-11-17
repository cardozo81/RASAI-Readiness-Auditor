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
SAFE_COOKIE_METADATA = frozenset({'cookie_attribution_id', 'cookie_ref', 'cookie_name_display', 'set_cookie_index'})
SELECTOR_FIELDS = frozenset({'selector', 'css_selector', 'element_selector'})
CSS_IDENT = re.compile(r'^[.#][A-Za-z_][A-Za-z0-9_-]*(?:[.#][A-Za-z_][A-Za-z0-9_-]*)*$')
HTML_CLASS_ATTR = re.compile(r"""\bclass\s*=\s*(["'])([^"']*)\1""", re.I)
CSS_QUALIFIED = re.compile(r'[.#]sk-[A-Za-z0-9_-]+')
CREDENTIAL_PREFIXES = ('sk-proj-', 'sk-test-', 'sk-live-')


def _stable_reference(value):
    """Retain equality between ambiguous references without publishing raw data."""
    return '[REF-' + sha256(str(value).encode('utf-8')).hexdigest()[:20] + ']'


def _css_name_is_nonsecret(name):
    if name.startswith(CREDENTIAL_PREFIXES) or len(name) > 64:
        return False
    # Require at least two readable kebab-case segments after sk-. A long
    # high-entropy segment is not exempt even when adjacent to CSS syntax.
    return re.fullmatch(r'sk-(?:[a-z][a-z0-9]{1,24}-)+[a-z][a-z0-9]{1,24}', name) is not None


def _css_token_at(value, start, end, selector=False):
    token = value[start:end]
    if token.startswith(CREDENTIAL_PREFIXES):
        return False  # A selector field alone must never exempt known key prefixes.
    if selector and CSS_IDENT.fullmatch(value):
        return True  # Preserve the existing explicit selector-field contract.
    if not _css_name_is_nonsecret(token):
        return False
    if start and value[start - 1] in '.#':
        return any(m.start() == start - 1 and m.end() == end
                   for m in CSS_QUALIFIED.finditer(value))
    for attr in HTML_CLASS_ATTR.finditer(value):
        if attr.start(2) <= start and end <= attr.end(2):
            return (start == attr.start(2) or value[start - 1].isspace()) and (
                end == attr.end(2) or value[end].isspace())
    return False


def _text(value, selector=False):
    value = re.sub(r'(?is)<input\b[^>]*(?:password|api[_-]?key|access[_-]?token|secret)[^>]*>', '[REDACTED INPUT]', value)
    value = re.sub(r'(?i)\bBearer\s+[^\s<>"\']+', 'Bearer [REDACTED]', value)
    value = re.sub(r'(https?://)[^/@\s:]+:[^/@\s]+@', r'\1[REDACTED]@', value)
    value = ASSIGNMENT.sub(r'\1[REDACTED]', value)
    # Recognize qualified CSS classes and HTML class attributes, but never
    # exempt bare secret-shaped values, JSON tokens, or authorization data.
    return TOKEN.sub(
        lambda match: match.group(0)
        if match.group(0).startswith('sk-') and
           _css_token_at(value, match.start(), match.end(), selector)
        else '[REDACTED]',
        value,
    )


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
    if has_opaque_marker(value) and (
        field in {'request_payload', 'response_payload'}
        or value.lstrip().startswith(('{', '['))
    ):
        return UNPARSEABLE_STATUS
    return _text(value, selector=field in SELECTOR_FIELDS)
