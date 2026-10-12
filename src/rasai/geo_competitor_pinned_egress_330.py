"""#330: DNS-rebinding-safe, no-redirect public HTTP transport for COBS opt-in.

Unlike a DNS preflight followed by a second implicit hostname lookup, every
connection here goes to a *verified public numeric address*. The original
hostname remains the HTTP Host header and the TLS SNI/certificate identity.
No proxy, redirect, retry, cookie jar, or request body is involved.
This adapter does not change the homologated Search Intelligence fetcher.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlsplit

from rasai.search_intelligence.content import (
    PublicWebBlocked, Resolver, _default_resolver, _validate_public_url,
)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, hostname: str, ip: str, port: int, timeout: float) -> None:
        super().__init__(hostname, port=port, timeout=timeout)
        self._numeric_ip = ip

    def connect(self) -> None:
        # Numeric IP, NEVER the DNS hostname. In particular, no proxy from
        # HTTPS_PROXY/HTTP_PROXY can override the verified destination.
        self.sock = socket.create_connection(
            (self._numeric_ip, self.port), timeout=self.timeout,
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname: str, ip: str, port: int, timeout: float) -> None:
        # create_default_context verifies the certificate against hostname,
        # not the pinned numeric IP. Disabling verify/check_hostname is unsafe.
        super().__init__(
            hostname, port=port, timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._numeric_ip = ip

    def connect(self) -> None:
        raw = socket.create_connection(
            (self._numeric_ip, self.port), timeout=self.timeout,
        )
        try:
            self.sock = self._context.wrap_socket(
                raw, server_hostname=self.host,
            )
        except BaseException:
            raw.close()
            raise


class _BoundedConnectionResponse:
    """Give PublicWebFetcher its usual response API and close both handles."""

    def __init__(
        self, connection: http.client.HTTPConnection,
        response: http.client.HTTPResponse,
    ) -> None:
        self._connection = connection
        self._response = response
        self.headers = response.headers

    def getcode(self) -> int:
        return self._response.getcode()

    def read(self, size: int = -1) -> bytes:
        return self._response.read(size)

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._connection.close()


def _public_numeric_address(
    hostname: str, port: int, resolver: Resolver,
) -> str:
    """Select only an actual globally routable answer from ONE DNS snapshot.

    Reject the entire address set if one answer is non-public; an attacker
    must not use a mixed public/private DNS response to pass the gate.
    """
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        addresses = tuple(resolver(hostname, port))
        if not addresses:
            raise PublicWebBlocked("pinned transport DNS returned no addresses")
    else:
        addresses = (str(literal),)
    verified = []
    for raw in addresses:
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise PublicWebBlocked("pinned transport DNS returned invalid IP") from exc
        if not addr.is_global:
            raise PublicWebBlocked("pinned transport refused non-public DNS answer")
        verified.append(addr.compressed)
    return verified[0]


class PublicWebPinnedOpener:
    """Callable transport for PublicWebFetcher, bound to validated numeric IPs.

    No implicit DNS resolution occurs at connect time. HTTPS always verifies
    the certificate and SNI for the original requested hostname.
    """

    def __init__(self, resolver: Resolver | None = None) -> None:
        self.resolver = resolver or _default_resolver

    def __call__(self, request, *, timeout: float) -> _BoundedConnectionResponse:
        # Revalidate at this boundary, not just in the calling fetcher's
        # earlier preflight (whose DNS answers might already be stale).
        try:
            normalized = _validate_public_url(request.full_url, self.resolver)
            parsed = urlsplit(normalized)
            if request.get_method() != "GET" or parsed.scheme not in {"http", "https"}:
                raise PublicWebBlocked("only a public HTTP(S) GET is permitted")
            hostname = parsed.hostname
            if not hostname:
                raise PublicWebBlocked("public URL hostname missing")
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            pinned = _public_numeric_address(hostname, port, self.resolver)
        except (ValueError, OSError) as exc:
            # PublicWebFetcher turns URLError into UNAVAILABLE with no body.
            # The rejection occurs before socket connection, even if DNS
            # changed from public to private after its own preflight.
            raise URLError("pinned public egress denied: " + str(exc)) from exc

        connection: http.client.HTTPConnection
        if parsed.scheme == "https":
            connection = _PinnedHTTPSConnection(hostname, pinned, port, timeout)
        else:
            connection = _PinnedHTTPConnection(hostname, pinned, port, timeout)
        target = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
        try:
            connection.request(
                "GET", target, headers=dict(request.header_items()),
            )
            return _BoundedConnectionResponse(connection, connection.getresponse())
        except BaseException:
            connection.close()
            raise
