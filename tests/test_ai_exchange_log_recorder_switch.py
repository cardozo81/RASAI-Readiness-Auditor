from __future__ import annotations

from rasai.ai_exchange_log import AiExchangeRecorder, instrument_provider_transport


class _Provider:
    name = "OPENAI"
    model = "gpt-test"

    def __init__(self) -> None:
        self._transport = lambda url, headers, body, timeout: {"status": "ok"}


def _body(purpose: str) -> bytes:
    return (
        '{"model":"gpt-test","instructions":"This request purpose is '
        + purpose
        + '."}'
    ).encode("utf-8")


def test_reinstrumented_provider_routes_exchange_to_current_recorder() -> None:
    provider = _Provider()
    first = AiExchangeRecorder()
    second = AiExchangeRecorder()

    instrument_provider_transport(provider, first)
    provider._transport("https://example.test/v1", {}, _body("SEMANTIC_ANALYSIS"), 1.0)

    assert len(first.exchanges) == 1
    assert first.exchanges[0].purpose == "AI_REQUEST"
    assert not second.exchanges

    instrument_provider_transport(provider, second)
    provider._transport("https://example.test/v1", {}, _body("DIRECTED_ANALYSIS"), 1.0)

    assert len(first.exchanges) == 1
    assert len(second.exchanges) == 1
    assert second.exchanges[0].purpose == "DIRECTED_ANALYSIS"
