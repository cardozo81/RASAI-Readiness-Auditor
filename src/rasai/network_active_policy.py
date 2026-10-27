"""Canonical, non-secret network setting validation.

Active collection is disabled unless both explicit enablement and an exact
public hostname are present. Console settings persist these strings via the
existing EnvironmentSpec/INI machinery; removal revokes future authorization.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit


def hostname_from_audit_url(value: str) -> str:
    """Derive an exact public hostname, never an active-probe authorization.

    The URL may include HTTPS, a path and a query. Those components are never
    copied to RASAI_NETWORK_ACTIVE_HOST. A domain-only input follows the same
    canonical URL normalization used by the audit target editor.
    """
    from rasai.target_scope_reconciliation import canonical_target
    from rasai.network_active_probe import _host

    target = canonical_target(value)
    if not target:
        raise ValueError("URL da auditoria inválida para configuração de rede")
    parts = urlsplit(target)
    if parts.scheme not in ("http", "https") or parts.username is not None or parts.password is not None:
        raise ValueError("Informe uma URL HTTP(S) pública, sem credenciais")
    try:
        _ = parts.port
    except ValueError as exc:
        raise ValueError("Porta inválida na URL da auditoria") from exc
    return _host(parts.hostname or "")


def validate_network_setting(name: str, value: str) -> str:
    text = str(value).strip()
    if name in ("RASAI_NETWORK_ACTIVE_ENABLED", "RASAI_GEOIP_ACQUIRE_TOOLS"):
        if text.lower() not in ("true", "false"):
            raise ValueError("Use true ou false")
        return text.lower()
    if name == "RASAI_NETWORK_MAX_HOPS":
        if not text.isascii() or not text.isdecimal() or not 1 <= int(text) <= 16:
            raise ValueError("Limite de saltos deve estar entre 1 e 16")
        return str(int(text))
    if name == "RASAI_NETWORK_GEOIP_SOURCE":
        if text not in ("LOCAL_FIRST", "DISABLED"):
            raise ValueError("Fonte GeoIP não reconhecida")
        return text
    if name == "RASAI_NETWORK_ACTIVE_HOST":
        from rasai.network_active_probe import _host
        # The persisted setting is always a bare hostname. Accept a complete
        # HTTP(S) URL as input convenience, without persisting scheme/path.
        if "://" in text:
            return hostname_from_audit_url(text)
        return _host(text)
    raise ValueError("Configuração de rede desconhecida")


def authorized_hostname(environment=None) -> str | None:
    """Fail closed for incomplete or malformed persistent preferences."""
    env = os.environ if environment is None else environment
    try:
        enabled = validate_network_setting(
            "RASAI_NETWORK_ACTIVE_ENABLED",
            env.get("RASAI_NETWORK_ACTIVE_ENABLED", "false"))
        if enabled != "true":
            return None
        return validate_network_setting(
            "RASAI_NETWORK_ACTIVE_HOST", env.get("RASAI_NETWORK_ACTIVE_HOST", ""))
    except (ValueError, TypeError):
        return None


def max_hops(environment=None) -> int:
    env = os.environ if environment is None else environment
    try:
        return int(validate_network_setting(
            "RASAI_NETWORK_MAX_HOPS", env.get("RASAI_NETWORK_MAX_HOPS", "8")))
    except (ValueError, TypeError):
        return 8
