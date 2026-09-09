"""SerpApi adapter. All vendor-specific request/response details stay here."""
from __future__ import annotations

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
_GOOGLE_PAGE_SIZE = 10


class SerpApiProvider(SerpProvider):
    provider_id = "serpapi"
    data_mode = SerpDataMode.OBSERVED_API
    supported_engines = ("google",)
    endpoint = "https://serpapi.com/search"

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

    def _request_url(self, request: SerpQueryRequest, *, start: int) -> str:
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
        }
        if start:
            params["start"] = start
        if request.region and request.region.strip():
            params["location"] = request.region.strip()
        return self.endpoint + "?" + urlencode(params)

    def _fetch(self, request: SerpQueryRequest, *, start: int) -> bytes:
        url = self._request_url(request, start=start)
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

    def _decode_payload(self, raw: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SerpMalformedResponse("SerpApi returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise SerpMalformedResponse("SerpApi response root must be an object")
        if payload.get("error"):
            message = str(payload["error"]).replace(self._api_key, "[REDACTED]")
            raise SerpProviderError(f"SerpApi returned provider error: {message[:240]}")
        return payload

    @staticmethod
    def _parse_collected_at(payload: dict[str, Any]) -> datetime:
        metadata = payload.get("search_metadata")
        if isinstance(metadata, dict):
            created_at = metadata.get("created_at")
            if created_at:
                text = str(created_at).strip()
                if text.endswith(" UTC"):
                    text = text[:-4] + "+00:00"
                else:
                    text = text.replace("Z", "+00:00")
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
    def _normalize_results(
        payload: dict[str, Any], *, position_offset: int
    ) -> tuple[tuple[SerpResult, ...], dict[str, Any]]:
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
                local_position = int(item.get("position", index))
            except (TypeError, ValueError):
                dropped += 1
                continue
            if local_position <= 0:
                dropped += 1
                continue
            position = position_offset + local_position
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

    @staticmethod
    def _has_next_page(payload: dict[str, Any]) -> bool:
        pagination = payload.get("serpapi_pagination")
        if not isinstance(pagination, dict):
            return False
        return bool(pagination.get("next") or pagination.get("next_link"))

    def observe(self, request: SerpQueryRequest) -> ProviderObservation:
        request.validate()
        pages: list[dict[str, Any]] = []
        results: list[SerpResult] = []
        request_ids: list[str] = []
        collected_at_values: list[datetime] = []
        raw_organic_count = 0
        dropped_results = 0
        pagination_ended = False
        page_offsets = tuple(range(0, request.depth, _GOOGLE_PAGE_SIZE))

        for page_number, start in enumerate(page_offsets, 1):
            raw = self._fetch(request, start=start)
            payload = self._decode_payload(raw)
            pages.append(payload)
            page_results, page_quality = self._normalize_results(
                payload, position_offset=start
            )
            results.extend(
                item for item in page_results if item.position <= request.depth
            )
            raw_organic_count += int(page_quality["raw_organic_result_count"])
            dropped_results += int(page_quality["dropped_results"])

            metadata = payload.get("search_metadata")
            if isinstance(metadata, dict) and metadata.get("id"):
                request_ids.append(str(metadata["id"]))
            collected_at_values.append(self._parse_collected_at(payload))

            if page_number < len(page_offsets) and not self._has_next_page(payload):
                pagination_ended = True
                break

        results.sort(key=lambda result: result.position)
        quality: dict[str, Any] = {
            "page_size": _GOOGLE_PAGE_SIZE,
            "pages_requested_ceiling": len(page_offsets),
            "pages_collected": len(pages),
            "raw_organic_result_count": raw_organic_count,
            "dropped_results": dropped_results,
            "pagination_ended_before_requested_depth": pagination_ended,
        }
        if request_ids:
            quality["provider_request_ids"] = tuple(request_ids)
        if collected_at_values:
            quality["collection_window_start"] = min(collected_at_values).isoformat()
            quality["collection_window_end"] = max(collected_at_values).isoformat()

        raw_evidence = json.dumps(
            {
                "provider": self.provider_id,
                "engine": request.engine.strip().casefold(),
                "requested_depth": request.depth,
                "pages": pages,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        provider_request_id = request_ids[0] if len(request_ids) == 1 else None
        collected_at = min(collected_at_values) if collected_at_values else utc_now()
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
            collected_at=collected_at,
            provider=self.provider_id,
            provider_request_id=provider_request_id,
            requested_depth=request.depth,
            result_count=len(results),
            results=tuple(results),
            data_mode=self.data_mode,
            status=SerpObservationStatus.OBSERVED,
            config_metadata=dict(request.config_metadata),
            quality_metadata=quality,
        )
        return ProviderObservation(observation=observation, raw_evidence=raw_evidence)
