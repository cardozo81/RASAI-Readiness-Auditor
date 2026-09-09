"""SerpApi Bing adapter with provider-driven pagination.

Bing pagination does not guarantee a fixed number of organic results per page. The
adapter therefore follows only the provider-reported ``first`` cursor, reconstructs
requests locally, and remains bounded by the shared RequestBudget.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from ..models import (
    SerpObservation,
    SerpObservationStatus,
    SerpQueryRequest,
    SerpResult,
    new_identifier,
    utc_now,
)
from ..provider import SerpMalformedResponse, SerpProviderError, SerpUnsupportedEngine
from .serpapi import SerpApiProvider


class SerpApiBingProvider(SerpApiProvider):
    """Live Bing organic-result adapter using SerpApi.

    ``provider_id`` is intentionally distinct from the existing Google adapter so the
    established ``serpapi`` runtime contract remains backward compatible.
    """

    provider_id = "serpapi-bing"
    supported_engines = ("bing",)

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

        language = request.language.replace("_", "-").split("-", 1)[0].strip().casefold()
        country = request.country.strip().upper()
        params: dict[str, str | int] = {
            "engine": "bing",
            "q": request.query,
            "api_key": self._api_key,
            "mkt": f"{language}-{country}",
            "device": device,
        }
        if start > 0:
            params["first"] = start
        if request.region and request.region.strip():
            params["location"] = request.region.strip()
        return self.endpoint + "?" + urlencode(params)

    @staticmethod
    def _next_first(payload: dict[str, Any]) -> int | None:
        pagination = payload.get("serpapi_pagination")
        if not isinstance(pagination, dict):
            return None
        target = pagination.get("next") or pagination.get("next_link")
        if not target:
            return None
        values = parse_qs(urlsplit(str(target)).query).get("first")
        if not values:
            raise SerpMalformedResponse("SerpApi Bing pagination next link has no first cursor")
        try:
            cursor = int(values[0])
        except (TypeError, ValueError) as exc:
            raise SerpMalformedResponse("SerpApi Bing pagination first cursor is invalid") from exc
        if cursor <= 0:
            raise SerpMalformedResponse("SerpApi Bing pagination first cursor must be positive")
        return cursor

    def observe(self, request: SerpQueryRequest):
        request.validate()
        pages: list[dict[str, Any]] = []
        result_map: dict[tuple[int, str], SerpResult] = {}
        request_ids: list[str] = []
        collected_at_values = []
        raw_organic_count = 0
        dropped_results = 0
        cursor = 0
        seen_cursors = {0}
        pagination_ended = False
        budget_ended = False
        requested_depth_complete = False

        while True:
            if pages and self._budget is not None and self._budget.remaining <= 0:
                budget_ended = True
                break
            if len(pages) >= request.depth:
                budget_ended = True
                break

            raw = self._fetch(request, start=cursor)
            payload = self._decode_payload(raw)
            pages.append(payload)
            position_offset = max(0, cursor - 1) if cursor else 0
            page_results, page_quality = self._normalize_results(
                payload, position_offset=position_offset
            )
            for item in page_results:
                if item.position <= request.depth:
                    result_map[(item.position, item.url)] = item
            raw_organic_count += int(page_quality["raw_organic_result_count"])
            dropped_results += int(page_quality["dropped_results"])

            metadata = payload.get("search_metadata")
            if isinstance(metadata, dict) and metadata.get("id"):
                request_ids.append(str(metadata["id"]))
            collected_at_values.append(self._parse_collected_at(payload))

            observed_ceiling = max((item.position for item in result_map.values()), default=0)
            if observed_ceiling >= request.depth:
                requested_depth_complete = True
                break

            next_cursor = self._next_first(payload)
            if next_cursor is None:
                pagination_ended = True
                requested_depth_complete = True
                break
            if next_cursor in seen_cursors or next_cursor <= cursor:
                raise SerpMalformedResponse("SerpApi Bing pagination cursor did not advance")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        results = tuple(sorted(result_map.values(), key=lambda result: result.position))
        observed_ceiling = max((item.position for item in results), default=0)
        quality: dict[str, Any] = {
            "page_size": "provider-variable",
            "pagination_strategy": "serpapi_next_first",
            "pages_collected": len(pages),
            "raw_organic_result_count": raw_organic_count,
            "dropped_results": dropped_results,
            "observed_position_ceiling": observed_ceiling,
            "requested_depth_complete": requested_depth_complete,
            "pagination_ended_before_requested_depth": pagination_ended and observed_ceiling < request.depth,
            "request_budget_ended_before_requested_depth": budget_ended and not requested_depth_complete,
        }
        if request_ids:
            quality["provider_request_ids"] = tuple(request_ids)
        if collected_at_values:
            quality["collection_window_start"] = min(collected_at_values).isoformat()
            quality["collection_window_end"] = max(collected_at_values).isoformat()

        raw_evidence = json.dumps(
            {
                "provider": self.provider_id,
                "engine": "bing",
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
            engine="bing",
            country=request.country,
            region=request.region,
            language=request.language,
            device=request.device.strip().casefold(),
            collected_at=collected_at,
            provider=self.provider_id,
            provider_request_id=provider_request_id,
            requested_depth=request.depth,
            result_count=len(results),
            results=results,
            data_mode=self.data_mode,
            status=SerpObservationStatus.OBSERVED,
            config_metadata=dict(request.config_metadata),
            quality_metadata=quality,
        )
        from ..provider import ProviderObservation

        return ProviderObservation(observation=observation, raw_evidence=raw_evidence)
