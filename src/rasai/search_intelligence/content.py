"""Safe, bounded public-web content inspection for Search Intelligence.

The feature is explicit opt-in. It stores extracted features and content hashes, not raw
HTML. The default fetcher rejects non-public destinations before each request/redirect.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import math
import re
import socket
import ssl
import unicodedata
from typing import Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from rasai.url_utils import InvalidUrl, normalize_url

from .competitive import CompetitiveSelection, select_competitive_candidates
from .models import SearchIntelligenceResult


class ContentFetchStatus(StrEnum):
    OBSERVED = "OBSERVED"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class CompetitivePageFeatures:
    role: str
    domain: str
    requested_url: str
    final_url: str | None
    status: ContentFetchStatus
    http_status: int | None
    content_type: str | None
    content_sha256: str | None
    bytes_read: int
    title: str | None = None
    meta_description: str | None = None
    headings: tuple[str, ...] = ()
    word_count: int = 0
    query_terms: tuple[str, ...] = ()
    query_terms_in_title: tuple[str, ...] = ()
    query_terms_in_description: tuple[str, ...] = ()
    query_terms_in_headings: tuple[str, ...] = ()
    query_terms_in_body: tuple[str, ...] = ()
    jsonld_types: tuple[str, ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    redirects: tuple[str, ...] = ()

    @property
    def query_body_coverage(self) -> float | None:
        if not self.query_terms:
            return None
        return len(self.query_terms_in_body) / len(self.query_terms)


@dataclass(frozen=True, slots=True)
class CompetitiveGap:
    code: str
    severity: str
    message: str
    customer_value: float | int | None
    leader_reference: float | int | None
    evidence_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompetitiveContentAnalysis:
    selection: CompetitiveSelection
    customer_page: CompetitivePageFeatures | None
    competitor_pages: tuple[CompetitivePageFeatures, ...]
    gaps: tuple[CompetitiveGap, ...]
    comparison_status: str
    methodology: str = "DETERMINISTIC-CORRELATIONAL-001"


class PublicWebBlocked(ValueError):
    code = "PUBLIC_WEB_DESTINATION_BLOCKED"


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


Resolver = Callable[[str, int | None], Iterable[str]]


def _default_resolver(hostname: str, port: int | None) -> tuple[str, ...]:
    addresses: list[str] = []
    for item in socket.getaddrinfo(hostname, port or 443, type=socket.SOCK_STREAM):
        address = str(item[4][0])
        if address not in addresses:
            addresses.append(address)
    return tuple(addresses)


def _validate_public_url(url: str, resolver: Resolver) -> str:
    normalized = normalize_url(url)
    parsed = urlsplit(normalized)
    hostname = parsed.hostname
    if hostname is None:
        raise PublicWebBlocked("URL has no hostname")
    hostname_l = hostname.rstrip(".").casefold()
    if (
        hostname_l == "localhost"
        or hostname_l.endswith(".localhost")
        or hostname_l.endswith(".local")
        or hostname_l.endswith(".internal")
    ):
        raise PublicWebBlocked("local/internal hostname is not eligible for competitor crawling")
    if parsed.port not in {None, 80, 443}:
        raise PublicWebBlocked("only standard public web ports 80/443 are eligible")

    try:
        literal = ipaddress.ip_address(hostname_l)
    except ValueError:
        try:
            addresses = tuple(resolver(hostname_l, parsed.port))
        except OSError as exc:
            raise PublicWebBlocked(f"hostname resolution failed: {exc}") from exc
        if not addresses:
            raise PublicWebBlocked("hostname resolved to no addresses")
        for value in addresses:
            try:
                address = ipaddress.ip_address(value)
            except ValueError as exc:
                raise PublicWebBlocked("resolver returned an invalid IP address") from exc
            if not address.is_global:
                raise PublicWebBlocked(
                    f"hostname resolves to non-public address {address.compressed}"
                )
    else:
        if not literal.is_global:
            raise PublicWebBlocked(
                f"non-public IP literal {literal.compressed} is not eligible"
            )
    return normalized


@dataclass(frozen=True, slots=True)
class _FetchedDocument:
    requested_url: str
    final_url: str | None
    http_status: int | None
    headers: Mapping[str, str]
    body: bytes
    redirects: tuple[str, ...]
    status: ContentFetchStatus
    error_code: str | None = None
    error_message: str | None = None


class PublicWebFetcher:
    """Bounded fetcher for explicit competitor-content inspection.

    It performs a public-address preflight for every request and redirect. For a
    server-side SaaS deployment, network-layer egress filtering/proxy enforcement should
    additionally be used to eliminate DNS-rebinding TOCTOU risk.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_redirects: int = 5,
        max_bytes: int = 2_000_000,
        resolver: Resolver | None = None,
        opener=None,
        user_agent: str = "RASAI-Search-Intelligence/0.1",
    ) -> None:
        if timeout_seconds <= 0 or not math.isfinite(timeout_seconds):
            raise ValueError("content timeout_seconds must be finite and > 0")
        if max_redirects < 0:
            raise ValueError("content max_redirects must be >= 0")
        if max_bytes <= 0:
            raise ValueError("content max_bytes must be > 0")
        self.timeout_seconds = timeout_seconds
        self.max_redirects = max_redirects
        self.max_bytes = max_bytes
        self.resolver = resolver or _default_resolver
        self.opener = opener or build_opener(_NoRedirectHandler()).open
        self.user_agent = user_agent
        self.requests_used = 0

    def fetch(self, url: str) -> _FetchedDocument:
        try:
            requested = _validate_public_url(url, self.resolver)
        except (InvalidUrl, PublicWebBlocked, ValueError) as exc:
            return _FetchedDocument(
                requested_url=str(url),
                final_url=None,
                http_status=None,
                headers={},
                body=b"",
                redirects=(),
                status=ContentFetchStatus.BLOCKED,
                error_code=getattr(exc, "code", "INVALID_PUBLIC_WEB_URL"),
                error_message=str(exc)[:512],
            )

        current = requested
        redirects: list[str] = []
        seen = {requested}
        for _ in range(self.max_redirects + 1):
            try:
                current = _validate_public_url(current, self.resolver)
            except (InvalidUrl, PublicWebBlocked, ValueError) as exc:
                return _FetchedDocument(
                    requested_url=requested,
                    final_url=current,
                    http_status=None,
                    headers={},
                    body=b"",
                    redirects=tuple(redirects),
                    status=ContentFetchStatus.BLOCKED,
                    error_code=getattr(exc, "code", "PUBLIC_WEB_DESTINATION_BLOCKED"),
                    error_message=str(exc)[:512],
                )

            response = None
            try:
                request = Request(
                    current,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.2",
                        "Accept-Encoding": "identity",
                        "Connection": "close",
                    },
                    method="GET",
                )
                try:
                    self.requests_used += 1
                    response = self.opener(request, timeout=self.timeout_seconds)
                except HTTPError as exc:
                    response = exc
                status = int(response.getcode())
                headers = {
                    str(key).casefold(): str(value)
                    for key, value in response.headers.items()
                }
                if 300 <= status <= 399:
                    location = response.headers.get("Location")
                    if not location:
                        return _FetchedDocument(
                            requested, current, status, headers, b"", tuple(redirects),
                            ContentFetchStatus.ERROR, "INVALID_REDIRECT",
                            "redirect response has no Location header",
                        )
                    if len(redirects) >= self.max_redirects:
                        return _FetchedDocument(
                            requested, current, status, headers, b"", tuple(redirects),
                            ContentFetchStatus.ERROR, "TOO_MANY_REDIRECTS",
                            f"redirect chain exceeded {self.max_redirects} hops",
                        )
                    try:
                        target = normalize_url(location, base_url=current)
                        _validate_public_url(target, self.resolver)
                    except (InvalidUrl, PublicWebBlocked, ValueError) as exc:
                        return _FetchedDocument(
                            requested, current, status, headers, b"", tuple(redirects),
                            ContentFetchStatus.BLOCKED,
                            getattr(exc, "code", "PUBLIC_WEB_REDIRECT_BLOCKED"),
                            str(exc)[:512],
                        )
                    if target in seen:
                        return _FetchedDocument(
                            requested, target, status, headers, b"", tuple(redirects),
                            ContentFetchStatus.ERROR, "REDIRECT_LOOP",
                            f"redirect loop reached {target}",
                        )
                    redirects.append(target)
                    seen.add(target)
                    current = target
                    continue

                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    return _FetchedDocument(
                        requested, current, status, headers, b"", tuple(redirects),
                        ContentFetchStatus.ERROR, "CONTENT_BODY_LIMIT",
                        f"response exceeded {self.max_bytes} bytes",
                    )
                return _FetchedDocument(
                    requested, current, status, headers, body, tuple(redirects),
                    ContentFetchStatus.OBSERVED,
                )
            except (socket.timeout, TimeoutError) as exc:
                return _FetchedDocument(
                    requested, current, None, {}, b"", tuple(redirects),
                    ContentFetchStatus.UNAVAILABLE, "CONTENT_TIMEOUT", str(exc)[:512],
                )
            except ssl.SSLError as exc:
                return _FetchedDocument(
                    requested, current, None, {}, b"", tuple(redirects),
                    ContentFetchStatus.UNAVAILABLE, "CONTENT_TLS_ERROR", str(exc)[:512],
                )
            except URLError as exc:
                return _FetchedDocument(
                    requested, current, None, {}, b"", tuple(redirects),
                    ContentFetchStatus.UNAVAILABLE, "CONTENT_NETWORK_ERROR", str(exc)[:512],
                )
            except (http.client.HTTPException, OSError) as exc:
                return _FetchedDocument(
                    requested, current, None, {}, b"", tuple(redirects),
                    ContentFetchStatus.UNAVAILABLE, "CONTENT_NETWORK_ERROR", str(exc)[:512],
                )
            finally:
                if response is not None:
                    response.close()

        return _FetchedDocument(
            requested, current, None, {}, b"", tuple(redirects),
            ContentFetchStatus.ERROR, "CONTENT_REDIRECT_STATE", "unexpected redirect state",
        )


class _FeatureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta_description: str | None = None
        self.headings: list[str] = []
        self.text_parts: list[str] = []
        self._title = False
        self._heading: str | None = None
        self._heading_parts: list[str] = []
        self._skip_depth = 0
        self._jsonld = False
        self._jsonld_parts: list[str] = []
        self.jsonld_types: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.casefold()
        values = {str(k).casefold(): (v or "") for k, v in attrs}
        if name in {"style", "noscript", "template"}:
            self._skip_depth += 1
        elif name == "script":
            script_type = values.get("type", "").casefold()
            if "ld+json" in script_type:
                self._jsonld = True
                self._jsonld_parts = []
            else:
                self._skip_depth += 1
        elif name == "title":
            self._title = True
        elif name in {"h1", "h2", "h3"}:
            self._heading = name
            self._heading_parts = []
        elif name == "meta":
            meta_name = values.get("name", "").casefold()
            if meta_name == "description" and values.get("content", "").strip():
                self.meta_description = values["content"].strip()

    def handle_endtag(self, tag: str) -> None:
        name = tag.casefold()
        if name == "script" and self._jsonld:
            self._consume_jsonld("".join(self._jsonld_parts))
            self._jsonld = False
            self._jsonld_parts = []
        elif name in {"style", "noscript", "template", "script"} and self._skip_depth:
            self._skip_depth -= 1
        elif name == "title":
            self._title = False
        elif self._heading == name:
            value = " ".join("".join(self._heading_parts).split())
            if value:
                self.headings.append(value)
            self._heading = None
            self._heading_parts = []

    def handle_data(self, data: str) -> None:
        if self._jsonld:
            self._jsonld_parts.append(data)
            return
        if self._skip_depth:
            return
        if self._title:
            self.title_parts.append(data)
        if self._heading is not None:
            self._heading_parts.append(data)
        if data.strip():
            self.text_parts.append(data)

    def _consume_jsonld(self, raw: str) -> None:
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return

        def walk(item) -> None:
            if isinstance(item, dict):
                type_value = item.get("@type")
                if isinstance(type_value, str) and type_value.strip():
                    self.jsonld_types.add(type_value.strip())
                elif isinstance(type_value, list):
                    for entry in type_value:
                        if isinstance(entry, str) and entry.strip():
                            self.jsonld_types.add(entry.strip())
                for nested in item.values():
                    if isinstance(nested, (dict, list)):
                        walk(nested)
            elif isinstance(item, list):
                for nested in item:
                    walk(nested)
        walk(value)


_STOPWORDS = frozenset({
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos", "e",
    "em", "na", "nas", "no", "nos", "o", "os", "ou", "para", "por", "que", "se",
    "um", "uma", "the", "and", "or", "for", "of", "to", "in",
})
_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def query_terms(query: str) -> tuple[str, ...]:
    terms: list[str] = []
    for item in _TOKEN_RE.findall(_fold(query)):
        if item in _STOPWORDS or item in terms:
            continue
        terms.append(item)
    return tuple(terms)


def _present(terms: Iterable[str], text: str | None) -> tuple[str, ...]:
    folded = _fold(text or "")
    tokens = set(_TOKEN_RE.findall(folded))
    return tuple(term for term in terms if term in tokens)


def extract_page_features(
    fetched: _FetchedDocument,
    *,
    role: str,
    domain: str,
    query: str,
) -> CompetitivePageFeatures:
    content_type = fetched.headers.get("content-type")
    terms = query_terms(query)
    if fetched.status is not ContentFetchStatus.OBSERVED:
        return CompetitivePageFeatures(
            role=role, domain=domain, requested_url=fetched.requested_url,
            final_url=fetched.final_url, status=fetched.status,
            http_status=fetched.http_status, content_type=content_type,
            content_sha256=None, bytes_read=0, query_terms=terms,
            error_code=fetched.error_code, error_message=fetched.error_message,
            redirects=fetched.redirects,
        )
    if fetched.http_status is None or fetched.http_status >= 400:
        return CompetitivePageFeatures(
            role=role, domain=domain, requested_url=fetched.requested_url,
            final_url=fetched.final_url, status=ContentFetchStatus.ERROR,
            http_status=fetched.http_status, content_type=content_type,
            content_sha256=sha256(fetched.body).hexdigest(), bytes_read=len(fetched.body),
            query_terms=terms, error_code="CONTENT_HTTP_STATUS",
            error_message=f"HTTP {fetched.http_status}", redirects=fetched.redirects,
        )
    media_type = (content_type or "").split(";", 1)[0].strip().casefold()
    if media_type and media_type not in {"text/html", "application/xhtml+xml"}:
        return CompetitivePageFeatures(
            role=role, domain=domain, requested_url=fetched.requested_url,
            final_url=fetched.final_url, status=ContentFetchStatus.ERROR,
            http_status=fetched.http_status, content_type=content_type,
            content_sha256=sha256(fetched.body).hexdigest(), bytes_read=len(fetched.body),
            query_terms=terms, error_code="CONTENT_UNSUPPORTED_MEDIA_TYPE",
            error_message=f"unsupported content type {media_type}", redirects=fetched.redirects,
        )

    charset = "utf-8"
    if content_type and "charset=" in content_type.casefold():
        charset = content_type.split("charset=", 1)[-1].split(";", 1)[0].strip().strip("\"'")
    try:
        html = fetched.body.decode(charset, errors="replace")
    except LookupError:
        html = fetched.body.decode("utf-8", errors="replace")

    parser = _FeatureParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    title = " ".join("".join(parser.title_parts).split()) or None
    body_text = " ".join(" ".join(parser.text_parts).split())
    headings_text = " ".join(parser.headings)
    word_count = len(_TOKEN_RE.findall(_fold(body_text)))
    return CompetitivePageFeatures(
        role=role,
        domain=domain,
        requested_url=fetched.requested_url,
        final_url=fetched.final_url,
        status=ContentFetchStatus.OBSERVED,
        http_status=fetched.http_status,
        content_type=content_type,
        content_sha256=sha256(fetched.body).hexdigest(),
        bytes_read=len(fetched.body),
        title=title,
        meta_description=parser.meta_description,
        headings=tuple(parser.headings),
        word_count=word_count,
        query_terms=terms,
        query_terms_in_title=_present(terms, title),
        query_terms_in_description=_present(terms, parser.meta_description),
        query_terms_in_headings=_present(terms, headings_text),
        query_terms_in_body=_present(terms, body_text),
        jsonld_types=tuple(sorted(parser.jsonld_types, key=str.casefold)),
        redirects=fetched.redirects,
    )


def _median(values: Iterable[float | int]) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def compare_content_features(
    customer: CompetitivePageFeatures,
    competitors: Iterable[CompetitivePageFeatures],
) -> tuple[CompetitiveGap, ...]:
    leaders = tuple(
        item for item in competitors if item.status is ContentFetchStatus.OBSERVED
    )
    if customer.status is not ContentFetchStatus.OBSERVED or not leaders:
        return ()

    urls = tuple(item.final_url or item.requested_url for item in leaders)
    gaps: list[CompetitiveGap] = []
    terms = max(1, len(customer.query_terms))

    dimensions = (
        (
            "QUERY_BODY_COVERAGE_LOWER_THAN_OBSERVED_LEADERS",
            len(customer.query_terms_in_body) / terms,
            _median(len(item.query_terms_in_body) / max(1, len(item.query_terms)) for item in leaders),
            "Cobertura lexical dos termos da consulta no conteúdo é menor que a mediana das páginas observadas à frente.",
        ),
        (
            "TITLE_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS",
            len(customer.query_terms_in_title),
            _median(len(item.query_terms_in_title) for item in leaders),
            "Presença dos termos da consulta no title é menor que a mediana das páginas observadas à frente.",
        ),
        (
            "HEADING_QUERY_ALIGNMENT_LOWER_THAN_OBSERVED_LEADERS",
            len(customer.query_terms_in_headings),
            _median(len(item.query_terms_in_headings) for item in leaders),
            "Presença dos termos da consulta em H1-H3 é menor que a mediana das páginas observadas à frente.",
        ),
        (
            "CONTENT_WORD_COUNT_LOWER_THAN_OBSERVED_LEADERS",
            customer.word_count,
            _median(item.word_count for item in leaders),
            "Volume textual observável é menor que a mediana das páginas à frente; volume não é tratado como qualidade nem causa de ranking.",
        ),
    )
    for code, customer_value, reference, message in dimensions:
        if reference is not None and float(customer_value) < float(reference):
            gaps.append(
                CompetitiveGap(
                    code=code,
                    severity="INFO",
                    message=message,
                    customer_value=customer_value,
                    leader_reference=reference,
                    evidence_urls=urls,
                )
            )

    leader_types = set().union(*(set(item.jsonld_types) for item in leaders))
    missing_types = sorted(leader_types.difference(customer.jsonld_types), key=str.casefold)
    if missing_types:
        gaps.append(
            CompetitiveGap(
                code="STRUCTURED_DATA_TYPES_DIFFER_FROM_OBSERVED_LEADERS",
                severity="INFO",
                message=(
                    "Tipos JSON-LD presentes em páginas observadas à frente e ausentes na página do cliente: "
                    + ", ".join(missing_types[:10])
                    + ". Isso é diferença observada, não recomendação automática de markup."
                ),
                customer_value=len(customer.jsonld_types),
                leader_reference=len(leader_types),
                evidence_urls=urls,
            )
        )
    return tuple(gaps)


def analyze_competitive_content(
    search_result: SearchIntelligenceResult,
    *,
    customer_url: str | None = None,
    max_competitor_pages: int = 3,
    fetcher: PublicWebFetcher | None = None,
) -> CompetitiveContentAnalysis:
    selection = select_competitive_candidates(
        search_result, max_pages=max_competitor_pages
    )
    effective_customer_url = customer_url or (
        selection.customer_result.url if selection.customer_result is not None else None
    )
    if not effective_customer_url:
        return CompetitiveContentAnalysis(
            selection=selection,
            customer_page=None,
            competitor_pages=(),
            gaps=(),
            comparison_status="CUSTOMER_URL_REQUIRED",
        )

    client = fetcher or PublicWebFetcher()
    customer_domain = selection.customer_domain or urlsplit(
        normalize_url(effective_customer_url)
    ).hostname or ""
    customer_page = extract_page_features(
        client.fetch(effective_customer_url),
        role="CUSTOMER",
        domain=customer_domain,
        query=selection.query,
    )
    competitor_pages = tuple(
        extract_page_features(
            client.fetch(item.result.url),
            role="COMPETITOR_CANDIDATE",
            domain=item.result.domain,
            query=selection.query,
        )
        for item in selection.selected_candidates
    )
    gaps = compare_content_features(customer_page, competitor_pages)
    observed_competitors = sum(
        item.status is ContentFetchStatus.OBSERVED for item in competitor_pages
    )
    if customer_page.status is not ContentFetchStatus.OBSERVED:
        status = "CUSTOMER_CONTENT_UNAVAILABLE"
    elif not selection.selected_candidates:
        status = "NO_ELIGIBLE_COMPETITOR_CANDIDATES"
    elif observed_competitors == 0:
        status = "COMPETITOR_CONTENT_UNAVAILABLE"
    else:
        status = "CONSOLIDATED"
    return CompetitiveContentAnalysis(
        selection=selection,
        customer_page=customer_page,
        competitor_pages=competitor_pages,
        gaps=gaps,
        comparison_status=status,
    )
