"""Deterministic provider-independent fixture adapter."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from ..domain import domain_from_result_url
from ..models import (
    QueryOrigin,
    SerpDataMode,
    SerpObservation,
    SerpObservationStatus,
    SerpQueryRequest,
    SerpResult,
    new_identifier,
    utc_now,
)
from ..provider import ProviderObservation, SerpMalformedResponse, SerpProvider


class FixtureSerpProvider(SerpProvider):
    """Read controlled canonical fixtures without any network access."""

    provider_id = "fixture"
    data_mode = SerpDataMode.FIXTURE
    supported_engines: tuple[str, ...] = ()

    def __init__(self, fixture: str | Path | Mapping[str, Any]) -> None:
        self._fixture = fixture

    def _load(self) -> tuple[dict[str, Any], bytes]:
        if isinstance(self._fixture, Mapping):
            payload = dict(self._fixture)
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            return payload, raw
        path = Path(self._fixture)
        try:
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SerpMalformedResponse(f"cannot load SERP fixture: {type(exc).__name__}: {exc}") from exc
        if not isinstance(payload, dict):
            raise SerpMalformedResponse("SERP fixture root must be a JSON object")
        return payload, raw

    @staticmethod
    def _optional_context_match(payload: Mapping[str, Any], key: str, expected: str | None) -> None:
        actual = payload.get(key)
        if actual is None or expected is None:
            return
        if str(actual).strip().casefold() != str(expected).strip().casefold():
            raise SerpMalformedResponse(
                f"SERP fixture {key}={actual!r} does not match request {expected!r}"
            )

    def observe(self, request: SerpQueryRequest) -> ProviderObservation:
        request.validate()
        payload, raw = self._load()
        self._optional_context_match(payload, "query", request.query)
        self._optional_context_match(payload, "engine", request.engine)
        self._optional_context_match(payload, "country", request.country)
        self._optional_context_match(payload, "language", request.language)
        self._optional_context_match(payload, "device", request.device)
        self._optional_context_match(payload, "region", request.region)

        raw_results = payload.get("results", [])
        if not isinstance(raw_results, list):
            raise SerpMalformedResponse("SERP fixture results must be an array")
        results: list[SerpResult] = []
        dropped = 0
        for index, item in enumerate(raw_results, 1):
            if not isinstance(item, dict):
                dropped += 1
                continue
            url = str(item.get("url") or "").strip()
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
            features = item.get("serp_features", ())
            if isinstance(features, str):
                features = (features,)
            if not isinstance(features, (list, tuple)):
                features = ()
            metadata = item.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            results.append(
                SerpResult(
                    position=position,
                    domain=domain,
                    url=url,
                    title=str(item["title"]) if item.get("title") is not None else None,
                    snippet=str(item["snippet"]) if item.get("snippet") is not None else None,
                    result_type=str(item.get("result_type") or "organic"),
                    serp_features=tuple(str(value) for value in features),
                    metadata=metadata,
                ).validate()
            )
        results.sort(key=lambda item: item.position)

        collected_raw = payload.get("collected_at")
        if collected_raw:
            try:
                collected_at = datetime.fromisoformat(str(collected_raw).replace("Z", "+00:00"))
                if collected_at.tzinfo is None:
                    collected_at = collected_at.replace(tzinfo=timezone.utc)
            except ValueError as exc:
                raise SerpMalformedResponse("SERP fixture collected_at must be ISO-8601") from exc
        else:
            collected_at = utc_now()

        observation = SerpObservation(
            observation_id=str(payload.get("observation_id") or new_identifier("SERP")),
            run_id=request.run_id,
            query=request.query,
            query_origin=request.query_origin,
            engine=request.engine,
            country=request.country,
            region=request.region,
            language=request.language,
            device=request.device,
            collected_at=collected_at,
            provider="fixture",
            provider_request_id=str(payload["provider_request_id"]) if payload.get("provider_request_id") else None,
            requested_depth=request.depth,
            result_count=len(results),
            results=tuple(results),
            data_mode=SerpDataMode.FIXTURE,
            status=SerpObservationStatus.OBSERVED,
            config_metadata=dict(request.config_metadata),
            quality_metadata={
                "fixture": True,
                "fixture_version": str(payload.get("fixture_version") or "SERP-FIXTURE-001"),
                "dropped_results": dropped,
                "raw_result_count": len(raw_results),
            },
        )
        return ProviderObservation(observation=observation, raw_evidence=raw)
