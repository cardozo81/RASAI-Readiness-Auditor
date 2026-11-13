"""Redact structured credentials and credential-shaped text before rendering."""
import json
import re

SENSITIVE = re.compile(r'(^|[_-])(api[_-]?key|secret|password|passwd|authorization|cookie|access[_-]?token|refresh[_-]?token|credential)(s|[_-]|$)', re.I)
ASSIGNMENT = re.compile(r'(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization|set-cookie|cookie)\s*[=:]\s*)[^\s,;<>]+')


def sanitize(value, key=''):
    if SENSITIVE.search(key):
        return '[REDACTED]'
    if isinstance(value, bytes):
        return {'binary_bytes': len(value), 'coverage': 'Parcial — conteúdo binário não publicado'}
    if isinstance(value, dict):
        return {k: sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(('{', '[')):
        try:
            return sanitize(json.loads(value))
        except (ValueError, TypeError):
            pass
    value = re.sub(r'(?is)<input\b[^>]*(?:password|api[_-]?key|access[_-]?token|secret)[^>]*>', '[REDACTED INPUT]', value)
    value = re.sub(r'(?i)\bBearer\s+[^\s<>"\']+', 'Bearer [REDACTED]', value)
    value = re.sub(r'\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}', '[REDACTED]', value)
    value = re.sub(r'(https?://)[^/@\s:]+:[^/@\s]+@', r'\1[REDACTED]@', value)
    return ASSIGNMENT.sub(r'\1[REDACTED]', value)
