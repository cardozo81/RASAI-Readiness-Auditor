"""Optional, authorized public egress discovery for the post-AUD network probe.

Only fixed HTTPS endpoints; no audit URL, keys, cookies or private identifiers.
This observation belongs to the *external echo request*, not the browser or
the independent TCP probe. A failure never invalidates the existing probe.
"""
from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import json
import socket
import ssl
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener,
)

ENABLED = "RASAI_NETWORK_EGRESS_ENABLED"
IPIFY_ENABLED = "RASAI_NETWORK_EGRESS_IPIFY_ENABLED"
IDENTME_ENABLED = "RASAI_NETWORK_EGRESS_IDENTME_ENABLED"

# Explicitly fixed provider+family pairs. Changing providers needs a code review.
ENDPOINTS = {
    "IPIFY": {
        4: "https://api.ipify.org?format=json",
        6: "https://api6.ipify.org?format=json",
    },
    "IDENTME": {
        4: "https://4.ident.me",
        6: "https://6.ident.me",
    },
}
PROVIDER_FLAGS = {"IPIFY": IPIFY_ENABLED, "IDENTME": IDENTME_ENABLED}
TIMEOUT_SECONDS = 2.0
MAX_REPLY_BYTES = 256
_METHOD = "FIXED_HTTPS_IP_ECHO_NO_PROXY"

# Human-readable, bounded descriptions. Never render HTTP bodies or exception text.
ERROR_REASONS = {
    "TIMEOUT": "O serviço não respondeu no prazo.",
    "DNS_UNAVAILABLE": "Não foi possível resolver o nome do serviço.",
    "NETWORK_UNREACHABLE": "A conexão de rede não pôde ser estabelecida.",
    "TLS_INVALID": "A conexão HTTPS não pôde ser validada.",
    "RATE_LIMITED": "O serviço limitou temporariamente as consultas.",
    "HTTP_FAILURE": "O serviço retornou erro HTTP.",
    "REDIRECT_REJECTED": "O serviço respondeu com redirecionamento não autorizado.",
    "INVALID_RESPONSE": "O serviço retornou um endereço IP inválido ou de outra família.",
    "UNAVAILABLE": "O serviço não estava acessível para esta medição.",
    "PROBE_ERROR": "A medição externa não pôde ser concluída.",
}


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def enabled_providers(environment: Mapping[str, str]) -> tuple[str, ...]:
    """A separate, explicit opt-in and independently reversible provider flags."""
    if environment.get(ENABLED, "false").strip().lower() != "true":
        return ()
    return tuple(
        name for name, flag in PROVIDER_FLAGS.items()
        if environment.get(flag, "true").strip().lower() == "true"
    )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _opener():
    # This probes the executor's direct HTTPS route, not environment proxy
    # configuration. No implicit proxy credentials are sent to third parties.
    return build_opener(
        ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()),
        _NoRedirect(),
    )


def _reason(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        if exc.code == 429:
            return "RATE_LIMITED"
        if exc.code in (301, 302, 303, 307, 308):
            return "REDIRECT_REJECTED"
        return "HTTP_FAILURE"
    source = exc.reason if isinstance(exc, URLError) else exc
    if isinstance(source, (TimeoutError, socket.timeout)):
        return "TIMEOUT"
    if isinstance(source, (ssl.SSLError, ssl.CertificateError)):
        return "TLS_INVALID"
    if isinstance(source, socket.gaierror):
        return "DNS_UNAVAILABLE"
    if isinstance(source, OSError):
        if source.errno in (getattr(__import__("errno"), name) for name in
                            ("ENETUNREACH", "EHOSTUNREACH", "EAFNOSUPPORT")):
            return "NETWORK_UNREACHABLE"
    return "UNAVAILABLE"


def _parse_address(raw: bytes, *, provider: str, family: int) -> str:
    if len(raw) > MAX_REPLY_BYTES:
        raise ValueError("oversized reply")
    text = raw.decode("utf-8", errors="strict").strip()
    if provider == "IPIFY":
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("not JSON object")
        text = payload.get("ip")
    if not isinstance(text, str) or len(text) > 64:
        raise ValueError("invalid address text")
    address = ipaddress.ip_address(text)
    if address.version != family or not address.is_global:
        raise ValueError("non-public address or wrong family")
    return str(address)


def discover_public_egress(
    environment: Mapping[str, str], *, opener: Any = None,
) -> dict[str, Any]:
    """One request per enabled provider/family, in precedence order.

    No new request occurs without the separately enabled operator opt-in.
    No retries, redirects, proxies, user-supplied URLs, or requests on render.
    """
    providers = enabled_providers(environment)
    if not providers:
        return {"state": "NOT_REQUESTED", "method": _METHOD,
                "families": {}, "providers_enabled": []}
    client = opener if opener is not None else _opener()
    families: dict[str, dict[str, Any]] = {}
    for family in (4, 6):
        attempts = []
        entry: dict[str, Any] = {
            "state": "UNAVAILABLE", "ip": None, "provider": None,
            "capture_utc": None, "attempts": attempts,
        }
        for provider in providers:
            url = ENDPOINTS[provider][family]
            attempt = {"provider": provider, "endpoint": url,
                       "state": "UNAVAILABLE", "reason": None}
            attempts.append(attempt)
            try:
                request = Request(
                    url, headers={"Accept": "application/json" if provider == "IPIFY"
                                  else "text/plain", "User-Agent": "RASAi-IP-Egress/1"},
                    method="GET",
                )
                with client.open(request, timeout=TIMEOUT_SECONDS) as response:
                    if getattr(response, "status", 200) != 200:
                        raise ValueError("unexpected status")
                    data = response.read(MAX_REPLY_BYTES + 1)
                value = _parse_address(data, provider=provider, family=family)
                instant = _stamp()
                entry.update(state="OBSERVED", ip=value, provider=provider,
                             capture_utc=instant)
                attempt.update(state="OBSERVED")
                break
            except (HTTPError, URLError, OSError, ValueError, UnicodeError,
                    json.JSONDecodeError, TimeoutError) as exc:
                attempt["reason"] = (
                    "INVALID_RESPONSE"
                    if isinstance(exc, (ValueError, UnicodeError, json.JSONDecodeError))
                    else _reason(exc)
                )
            except Exception:
                # Optional service defects must never affect the original AUD.
                attempt["reason"] = "PROBE_ERROR"
        families["ipv" + str(family)] = entry
    count = sum(row["state"] == "OBSERVED" for row in families.values())
    state = "OBSERVED" if count == 2 else "PARTIAL" if count == 1 else "UNAVAILABLE"
    return {
        "state": state,
        "method": _METHOD,
        "measurement_origin": "LOCAL_OPERATOR_PROCESS",
        "scope": "EXTERNAL_ECHO_REQUEST_ONLY_NOT_BROWSER_OR_TARGET_TCP",
        "providers_enabled": list(providers),
        "families": families,
    }


def verified_families(packet: Any) -> dict[int, dict]:
    """Read-only minimal validation of an integrity-checked probe's observations."""
    if not isinstance(packet, dict):
        return {}
    families = packet.get("families")
    if not isinstance(families, dict):
        return {}
    output = {}
    for family in (4, 6):
        row = families.get("ipv" + str(family))
        if not isinstance(row, dict) or row.get("state") != "OBSERVED":
            continue
        if row.get("provider") not in ENDPOINTS:
            continue
        try:
            address = ipaddress.ip_address(row.get("ip"))
        except (ValueError, TypeError):
            continue
        if address.version == family and address.is_global:
            output[family] = {**row, "ip": str(address)}
    return output


def error_summary(packet: Any) -> str | None:
    """Short, deterministic, safe reason for partial/unavailable results."""
    if not isinstance(packet, dict) or packet.get("state") not in ("PARTIAL", "UNAVAILABLE"):
        return None
    families = packet.get("families")
    if not isinstance(families, dict):
        return "A medição externa não produziu resultados verificáveis."
    failures = []
    for family in (4, 6):
        row = families.get("ipv" + str(family))
        if not isinstance(row, dict) or row.get("state") == "OBSERVED":
            continue
        attempts = row.get("attempts")
        reasons = []
        if isinstance(attempts, list):
            for attempt in attempts[:2]:
                if not isinstance(attempt, dict):
                    continue
                code = attempt.get("reason")
                if code in ERROR_REASONS and code not in reasons:
                    reasons.append(code)
        reason = " / ".join(ERROR_REASONS[code] for code in reasons)
        failures.append("IPv" + str(family) + ": " +
                        (reason or "Sem resultado verificável."))
    return " ".join(failures) if failures else "A medição externa não produziu resultados verificáveis."
