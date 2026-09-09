"""SerpApi adapter. All vendor-specific request/response details stay here."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
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


class SerpApiProvider(SerpProvider):
    provider_id = "serpapi"
    data_mode = SerpDataMode.OBSERVED_API
    supported_engines = ("google",)
    endpoint = "https://serpapi.com/search.json"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 20.0,
        retries: int = 1,
        min_interval_seconds: float = 1.0,
        budget: RequestBudget | None = None,
        opener: _OpenUrl = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not api_key.strip():
            raise ValueError("SerpApi live mode requires RASAI_SERPAPI_API_KEY")
        if timeout_seconds <= 0:
            raise ValueError("SERP timeout_seconds must be greater than zero")
        if retries < 0:
            raise ValueError("SERP retries must be >= 0")
        if min_interval_seconds < 0:
            raise ValueError("SERP min_interval_seconds must be >= 0")
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

    def _request_url(self, request: SerpQueryRequest) -> str:
        engine = request.engine.strip().casefold()
        if not self.supports_engine(engine):
            raise SerpUnsupportedEngine(
                f"provider {self.provider_id} does not support engine {request.engine!r}"
            )
        device = request.device.strip().casefold()
        if device not in {"mobile", "desktop"}:
            raise SerpProviderError(
                f"provider {self.provider_id} supports device mobile or desktop, not {request.device!r}"
            )
        language = request.language.split("-", 1)[0].strip().casefold()
        params: dict[str, str | int] = {
            "engine": "google",
            "q": request.query,
            "api_key": self._api_key,
            "gl": request.country.strip().casefold(),
            "hl": language,
            "device": device,
            "num": request.depth,
        }
        if request.region and request.region.strip():
            params["location"] = request.region.strip()
        return self.endpoint + "?" + urlencode(params)

    def _fetch(self, request: SerpQueryRequest) -> bytes:
        url = self._request_url(request)
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            if self._budget is not None:
                self._budget.consume()
            self._wait_rate_limit()
            http_request = Request(
                url,
                method="GET",
                headers={"Accept": "application/json", "User-Agent": "RASAi/0.1 SERP adapter"},
            )
            try:
                with self._opener(http_request, timeout=self._timeout) as response:
                    return response.read()
            except HTTPError as exc:
                last_error = exc
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if not retryable:
                    raise SerpProviderError(f"SerpApi HTTP {exc.code}") from exc
            except (TimeoutError, socket.timeout) as exc:
                last_error = exc
            except URLError as exc:
                last_error = exc
            if attempt < self._retries:
                continue
        if isinstance(last_error, (TimeoutError, socket.timeout)):
            raise SerpProviderTimeout("SerpApi request timed out") from last_error
        if isinstance(last_error, HTTPError):
            raise SerpProviderUnavailable(f"SerpApi HTTP {last_error.code}") from last_error
        raise SerpProviderUnavailable("SerpApi request unavailable") from last_error

    @staticmethod
    def _parse_collected_at(payload: dict[str, Any]) -> datetime:
        metadata = payload.get("search_metadata")
        if isinstance(metadata, dict):
            created_at = metadata.get("created_at")
            if created_at:
                text = str(created_at).replace("Z", "+00:00")
                try:
                    parsed = datetime.fromisoformat(text)
                except ValueError:
                    pass
                else:
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed
        return utc_now()

    @staticmethod
    def _normalize_results(payload: dict[str, Any]) -> tuple[tuple[SerpResult, ...], dict[str, Any]]:
        organic = payload.get("organic_results", [])
        if organic is None:
            organic = []
        if not isinstance(organic, list):
            raise SerpMalformedResponse("SerpApi organic_results must be an array")
        results: list[SerpResult] = []
        dropped = 0
        seen: set[tuple[int, str]] = set()
        for index, item in enumerate(organic, 1):
            if not isinstance(item, dict):
                dropped += 1
                continue
            url = str(item.get("link") or "").strip()
            domain = domain_from_result_url(url)
            if domain is None:
                dropped += 1
                continue
            try:
                position = int(item.get("position", index))
            except (TypeError, ValueError):
                dropped += 1
                continue
            if position <= 0:
                dropped += 1
                continue
            key = (position, url)
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
            features: list[str] = []
            if item.get("sitelinks"):
                features.append("sitelinks")
            if item.get("rich_snippet") or item.get("rich_snippet_table"):
                features.append("rich_snippet")
            metadata: dict[str, Any] = {}
            if item.get("displayed_link") is not None:
                metadata["displayed_link"] = str(item["displayed_link"])
            if item.get("source") is not None:
                metadata["source"] = str(item["source"])
            results.append(
                SerpResult(
                    position=position,
                    domain=domain,
                    url=url,
                    title=str(item["title"]) if item.get("title") is not None else None,
                    snippet=str(item["snippet"]) if item.get("snippet") is not None else None,
                    result_type="organic",
                    serp_features=tuple(features),
                    metadata=metadata,
                ).validate()
            )
        results.sort(key=lambda result: result.position)
        return tuple(results), {
            "raw_organic_result_count": len(organic),
            "dropped_results": dropped,
        }

    def observe(self, request: SerpQueryRequest) -> ProviderObservation:
        request.validate()
        raw = self._fetch(request)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SerpMalformedResponse("SerpApi returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise SerpMalformedResponse("SerpApi response root must be an object")
        if payload.get("error"):
            message = str(payload["error"]).replace(self._api_key, "[REDACTED]")
            raise SerpProviderError(f"SerpApi returned provider error: {message[:240]}")
        results, quality = self._normalize_results(payload)
        metadata = payload.get("search_metadata")
        request_id = str(metadata.get("id")) if isinstance(metadata, dict) and metadata.get("id") else None
        observation = SerpObservation(
            observation_id=new_identifier("SERP"),
            run_id=request.run_id,
            query=request.query,
            query_origin=request.query_origin,
            engine=request.engine.strip().casefold(),
            country=request.country,
            region=request.region,
            language=request.language,
            device=request.device.strip().casefold(),
            collected_at=self._parse_collected_at(payload),
            provider=self.provider_id,
            provider_request_id=request_id,
            requested_depth=request.depth,
            result_count=len(results),
            results=results,
            data_mode=self.data_mode,
            status=SerpObservationStatus.OBSERVED,
            config_metadata=dict(request.config_metadata),
            quality_metadata=quality,
        )
        return ProviderObservation(observation=observation, raw_evidence=raw)
