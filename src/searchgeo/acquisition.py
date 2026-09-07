"""Deterministic HTTP acquisition for M2, independent from browser rendering."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import http.client
import socket
import ssl
from time import perf_counter
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from searchgeo.url_utils import InvalidUrl, normalize_url


class NetworkErrorKind(StrEnum):
    DNS = "DNS"
    CONNECTION = "CONNECTION"
    TIMEOUT = "TIMEOUT"
    TLS = "TLS"
    PROTOCOL = "PROTOCOL"
    REDIRECT_LOOP = "REDIRECT_LOOP"
    TOO_MANY_REDIRECTS = "TOO_MANY_REDIRECTS"
    INVALID_REDIRECT = "INVALID_REDIRECT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class NetworkError:
    kind: NetworkErrorKind
    message: str


@dataclass(frozen=True, slots=True)
class RedirectHop:
    status: int
    source_url: str
    location: str
    target_url: str


@dataclass(frozen=True, slots=True)
class HttpAcquisitionResult:
    requested_url: str
    final_url: str | None
    status: int | None
    headers: tuple[tuple[str, str], ...]
    body: bytes
    redirects: tuple[RedirectHop, ...]
    network_error: NetworkError | None
    elapsed_ms: int

    def header_values(self, name: str) -> tuple[str, ...]:
        expected = name.casefold()
        return tuple(value for key, value in self.headers if key.casefold() == expected)

    def header(self, name: str) -> str | None:
        values = self.header_values(name)
        return values[-1] if values else None


class _NoRedirectHandler(HTTPRedirectHandler):
    """Expose redirects to the acquisition loop instead of following implicitly."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class HttpClient:
    """Synchronous bounded HTTP client using only the Python standard library."""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        max_redirects: int = 10,
        user_agent: str = "RASAI-Readiness-Auditor/0.1",
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if max_redirects < 0:
            raise ValueError("max_redirects must not be negative")
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        self._opener = build_opener(_NoRedirectHandler())

    def acquire(self, url: str) -> HttpAcquisitionResult:
        requested_url = normalize_url(url)
        current_url = requested_url
        redirects: list[RedirectHop] = []
        seen = {requested_url}
        started = perf_counter()

        while True:
            response = None
            try:
                request = Request(
                    current_url,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Encoding": "identity",
                        "Connection": "close",
                    },
                    method="GET",
                )
                try:
                    response = self._opener.open(request, timeout=self.timeout)
                except HTTPError as exc:
                    # HTTP errors, including redirects blocked by _NoRedirectHandler,
                    # are protocol responses and must not be misclassified as network errors.
                    response = exc

                status = int(response.getcode())
                headers = tuple((str(key), str(value)) for key, value in response.headers.items())

                if 300 <= status <= 399:
                    location = response.headers.get("Location")
                    body = response.read()
                    if not location:
                        return self._finish(
                            requested_url,
                            current_url,
                            status,
                            headers,
                            body,
                            redirects,
                            NetworkError(NetworkErrorKind.INVALID_REDIRECT, "redirect response has no Location header"),
                            started,
                        )
                    if len(redirects) >= self.max_redirects:
                        return self._finish(
                            requested_url,
                            current_url,
                            status,
                            headers,
                            body,
                            redirects,
                            NetworkError(
                                NetworkErrorKind.TOO_MANY_REDIRECTS,
                                f"redirect chain exceeded {self.max_redirects} hops",
                            ),
                            started,
                        )
                    try:
                        target_url = normalize_url(location, base_url=current_url)
                    except (InvalidUrl, ValueError) as exc:
                        return self._finish(
                            requested_url,
                            current_url,
                            status,
                            headers,
                            body,
                            redirects,
                            NetworkError(NetworkErrorKind.INVALID_REDIRECT, str(exc)),
                            started,
                        )
                    redirects.append(
                        RedirectHop(
                            status=status,
                            source_url=current_url,
                            location=location,
                            target_url=target_url,
                        )
                    )
                    if target_url in seen:
                        return self._finish(
                            requested_url,
                            target_url,
                            status,
                            headers,
                            body,
                            redirects,
                            NetworkError(NetworkErrorKind.REDIRECT_LOOP, f"redirect loop reached {target_url}"),
                            started,
                        )
                    seen.add(target_url)
                    current_url = target_url
                    continue

                body = response.read()
                return self._finish(
                    requested_url,
                    current_url,
                    status,
                    headers,
                    body,
                    redirects,
                    None,
                    started,
                )
            except URLError as exc:
                error = _classify_network_error(exc.reason)
                return self._finish(
                    requested_url,
                    current_url,
                    None,
                    (),
                    b"",
                    redirects,
                    error,
                    started,
                )
            except (socket.timeout, TimeoutError) as exc:
                return self._finish(
                    requested_url,
                    current_url,
                    None,
                    (),
                    b"",
                    redirects,
                    NetworkError(NetworkErrorKind.TIMEOUT, str(exc)),
                    started,
                )
            except ssl.SSLError as exc:
                return self._finish(
                    requested_url,
                    current_url,
                    None,
                    (),
                    b"",
                    redirects,
                    NetworkError(NetworkErrorKind.TLS, str(exc)),
                    started,
                )
            except http.client.HTTPException as exc:
                return self._finish(
                    requested_url,
                    current_url,
                    None,
                    (),
                    b"",
                    redirects,
                    NetworkError(NetworkErrorKind.PROTOCOL, str(exc)),
                    started,
                )
            except OSError as exc:
                return self._finish(
                    requested_url,
                    current_url,
                    None,
                    (),
                    b"",
                    redirects,
                    _classify_network_error(exc),
                    started,
                )
            finally:
                if response is not None:
                    response.close()

    @staticmethod
    def _finish(
        requested_url: str,
        final_url: str | None,
        status: int | None,
        headers: Iterable[tuple[str, str]],
        body: bytes,
        redirects: list[RedirectHop],
        network_error: NetworkError | None,
        started: float,
    ) -> HttpAcquisitionResult:
        return HttpAcquisitionResult(
            requested_url=requested_url,
            final_url=final_url,
            status=status,
            headers=tuple(headers),
            body=body,
            redirects=tuple(redirects),
            network_error=network_error,
            elapsed_ms=max(0, round((perf_counter() - started) * 1000)),
        )


def _classify_network_error(reason: object) -> NetworkError:
    message = str(reason)
    if isinstance(reason, socket.gaierror):
        return NetworkError(NetworkErrorKind.DNS, message)
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return NetworkError(NetworkErrorKind.TIMEOUT, message)
    if isinstance(reason, (ssl.SSLError, ssl.CertificateError)):
        return NetworkError(NetworkErrorKind.TLS, message)
    if isinstance(
        reason,
        (ConnectionRefusedError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError),
    ):
        return NetworkError(NetworkErrorKind.CONNECTION, message)
    if isinstance(reason, http.client.HTTPException):
        return NetworkError(NetworkErrorKind.PROTOCOL, message)
    if isinstance(reason, OSError):
        return NetworkError(NetworkErrorKind.CONNECTION, message)
    return NetworkError(NetworkErrorKind.UNKNOWN, message)


def decode_body(result: HttpAcquisitionResult) -> str:
    """Decode response bytes for HTML/XML parsing without altering the artifact bytes."""

    content_type = result.header("Content-Type") or ""
    charset = "utf-8"
    for parameter in content_type.split(";")[1:]:
        key, separator, value = parameter.partition("=")
        if separator and key.strip().casefold() == "charset":
            candidate = value.strip().strip('"\'')
            if candidate:
                charset = candidate
                break
    try:
        return result.body.decode(charset, errors="replace")
    except LookupError:
        return result.body.decode("utf-8", errors="replace")
