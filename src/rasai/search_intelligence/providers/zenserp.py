"""Zenserp Google adapter with RASAi-normalized organic observations."""
from __future__ import annotations

import json
import socket
from threading import Lock
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..budget import RequestBudget
from ..domain import domain_from_result_url
from ..models import (
    SerpDataMode,
    SerpObservation,
    SerpObservationStatus,
    SerpQueryRequest,
    SerpResult,
    new_identifier,
    utc_now,
)
from ..provider import (
    ProviderObservation,
    SerpMalformedResponse,
    SerpProvider,
    SerpProviderError,
    SerpProviderTimeout,
    SerpProviderUnavailable,
    SerpUnsupportedEngine,
)

_OpenUrl = Callable[..., Any]
_PAGE_SIZE = 10


class ZenserpProvider(SerpProvider):
    provider_id = "zenserp"
    data_mode = SerpDataMode.OBSERVED_API
    supported_engines = ("google",)
    endpoint = "https://app.zenserp.com/api/v2/search"

    def __init__(self, *, api_key: str, timeout_seconds: float = 20.0, retries: int = 1,
                 min_interval_seconds: float = 1.0, budget: RequestBudget | None = None,
                 opener: _OpenUrl = urlopen, sleeper: Callable[[float], None] = time.sleep,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        if not api_key.strip():
            raise ValueError("Zenserp live mode requires RASAI_ZENSERP_API_KEY")
        if timeout_seconds <= 0 or retries < 0 or min_interval_seconds < 0:
            raise ValueError("invalid Zenserp timeout/retry/rate configuration")
        self._api_key = api_key.strip()
        self._timeout = float(timeout_seconds)
        self._retries = int(retries)
        self._min_interval = float(min_interval_seconds)
        self._budget = budget
        self._opener = opener
        self._sleep = sleeper
        self._monotonic = monotonic
        self._last_started: float | None = None
        self._rate_lock = Lock()

    def _wait_rate_limit(self) -> None:
        if self._min_interval <= 0:
            return
        with self._rate_lock:
            now = self._monotonic()
            if self._last_started is not None:
                wait = self._min_interval - (now - self._last_started)
                if wait > 0:
                    self._sleep(wait)
                    now = self._monotonic()
            self._last_started = now

    def _request(self, request: SerpQueryRequest, *, start: int) -> bytes:
        if not self.supports_engine(request.engine):
            raise SerpUnsupportedEngine(f"provider {self.provider_id} supports google only")
        language = request.language.split("-", 1)[0].strip().casefold()
        params: dict[str, str | int] = {
            "q": request.query,
            "engine": "google",
            "num": _PAGE_SIZE,
            "start": start,
            "gl": request.country.strip().casefold(),
            "hl": language,
        }
        if request.region and request.region.strip():
            params["location"] = request.region.strip()
        # Zenserp accepts device-dependent Google results through its request surface;
        # keep the requested device in evidence even when no dedicated parameter exists.
        url = self.endpoint + "?" + urlencode(params)
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            if self._budget is not None:
                self._budget.consume()
            self._wait_rate_limit()
            http_request = Request(url, method="GET", headers={
                "Accept": "application/json", "apikey": self._api_key,
                "User-Agent": "RASAi/0.1 SERP adapter",
            })
            try:
                with self._opener(http_request, timeout=self._timeout) as response:
                    return response.read()
            except HTTPError as exc:
                last_error = exc
                if exc.code != 429 and not (500 <= exc.code <= 599):
                    raise SerpProviderError(f"Zenserp HTTP {exc.code}") from exc
            except (TimeoutError, socket.timeout, URLError) as exc:
                last_error = exc
            if attempt < self._retries:
                continue
        if isinstance(last_error, (TimeoutError, socket.timeout)):
            raise SerpProviderTimeout("Zenserp request timed out") from last_error
        raise SerpProviderUnavailable("Zenserp request unavailable") from last_error

    def _decode(self, raw: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SerpMalformedResponse("Zenserp returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise SerpMalformedResponse("Zenserp response root must be an object")
        if payload.get("error") or payload.get("message") and not payload.get("organic"):
            message = str(payload.get("error") or payload.get("message"))
            raise SerpProviderError("Zenserp provider error: " + message[:240])
        return payload

    @staticmethod
    def _normalize(payload: dict[str, Any], *, offset: int) -> tuple[SerpResult, ...]:
        organic = payload.get("organic", [])
        if organic is None:
            organic = []
        if not isinstance(organic, list):
            raise SerpMalformedResponse("Zenserp organic must be an array")
        output: list[SerpResult] = []
        for index, item in enumerate(organic, 1):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("link") or "").strip()
            domain = domain_from_result_url(url)
            if domain is None:
                continue
            try:
                local_position = int(item.get("position", index))
            except (TypeError, ValueError):
                continue
            if local_position <= 0:
                continue
            position = local_position if local_position > offset else offset + local_position
            output.append(SerpResult(
                position=position, domain=domain, url=url,
                title=str(item["title"]) if item.get("title") is not None else None,
                snippet=str(item.get("description") or item.get("snippet")) if (item.get("description") is not None or item.get("snippet") is not None) else None,
                result_type="organic", serp_features=(), metadata={},
            ).validate())
        output.sort(key=lambda item: item.position)
        return tuple(output)

    def observe(self, request: SerpQueryRequest) -> ProviderObservation:
        request.validate()
        pages: list[dict[str, Any]] = []
        results: list[SerpResult] = []
        ended = False
        for start in range(0, request.depth, _PAGE_SIZE):
            payload = self._decode(self._request(request, start=start))
            pages.append(payload)
            page_results = self._normalize(payload, offset=start)
            results.extend(item for item in page_results if item.position <= request.depth)
            if len(page_results) < _PAGE_SIZE:
                ended = True
                break
        results.sort(key=lambda item: item.position)
        collected_at = utc_now()
        raw_evidence = json.dumps({
            "provider": self.provider_id, "engine": "google", "requested_depth": request.depth,
            "requested_device": request.device, "pages": pages,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        observation = SerpObservation(
            observation_id=new_identifier("SERP"), run_id=request.run_id, query=request.query,
            query_origin=request.query_origin, engine="google", country=request.country,
            region=request.region, language=request.language, device=request.device.strip().casefold(),
            collected_at=collected_at, provider=self.provider_id, provider_request_id=None,
            requested_depth=request.depth, result_count=len(results), results=tuple(results),
            data_mode=self.data_mode, status=SerpObservationStatus.OBSERVED,
            config_metadata=dict(request.config_metadata), quality_metadata={
                "page_size": _PAGE_SIZE,
                "pages_requested_ceiling": len(tuple(range(0, request.depth, _PAGE_SIZE))),
                "pages_collected": len(pages),
                "pagination_ended_before_requested_depth": ended,
            },
        )
        return ProviderObservation(observation=observation, raw_evidence=raw_evidence)
