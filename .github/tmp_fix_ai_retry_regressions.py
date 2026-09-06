from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one occurrence, found {count}")
    return text.replace(old, new, 1)


# Semantic extension providers use dataclasses.replace in the retry wrapper.
path = "src/searchgeo/provider_extensions.py"
text = read(path)
text = replace_once(
    text,
    "from __future__ import annotations\n\nfrom datetime import datetime, timezone",
    "from __future__ import annotations\n\nfrom dataclasses import replace\nfrom datetime import datetime, timezone",
    "provider extension replace import",
)
write(path, text)


# Explicit-only M20 providers need the same bounded retry contract accepted by
# ContentRemediationRoutingSession. They remain explicit-only and are never
# inserted into AUTO provider discovery.
path = "src/searchgeo/provider_extensions_m20.py"
text = read(path)
text = replace_once(
    text,
    "from __future__ import annotations\n\nfrom datetime import datetime, timezone",
    "from __future__ import annotations\n\nfrom dataclasses import replace\nfrom datetime import datetime, timezone",
    "m20 extension replace import",
)
text = replace_once(
    text,
    "from urllib.error import HTTPError, URLError\n\nfrom searchgeo.m18_ai import (",
    "from urllib.error import HTTPError, URLError\n\n"
    "from searchgeo.ai_resilience import (\n"
    "    DECISION_RETRY,\n"
    "    DECISION_STOP,\n"
    "    DECISION_SUCCESS,\n"
    "    DECISION_SUCCESS_AFTER_RETRY,\n"
    "    MAX_PROVIDER_ATTEMPTS_PER_CONTEXT,\n"
    "    retry_policy,\n"
    ")\n"
    "from searchgeo.m18_ai import (",
    "m20 extension resilience imports",
)
text = replace_once(
    text,
    "    ProviderState,\n    RuntimeProviderState,\n)",
    "    ProviderState,\n    RuntimeProviderState,\n    estimate_cost,\n)",
    "m20 extension estimate cost import",
)
text = replace_once(
    text,
    "        self._runtime_state = RuntimeProviderState.ACTIVE\n        self._last_attempt: ProviderAttempt | None = None\n\n    def _request_payload",
    "        self._runtime_state = RuntimeProviderState.ACTIVE\n"
    "        self._last_attempt: ProviderAttempt | None = None\n"
    "        self._last_attempts: tuple[ProviderAttempt, ...] = ()\n\n"
    "    def _request_payload",
    "m20 extension attempt buffer",
)
old = "    def analyze(self, request: ContentRemediationRequest) -> ContentRemediationResult:\n        self._last_attempt = None\n"
new = '''    def analyze(
        self,
        request: ContentRemediationRequest,
        *,
        max_attempts: int = MAX_PROVIDER_ATTEMPTS_PER_CONTEXT,
    ) -> ContentRemediationResult:
        """Retry only one transient integration failure; never loop paid calls."""
        self._last_attempts = ()
        collected: list[ProviderAttempt] = []
        bounded = max(1, min(int(max_attempts), MAX_PROVIDER_ATTEMPTS_PER_CONTEXT))
        last: ContentRemediationResult | None = None
        for ordinal in range(1, bounded + 1):
            result = self._analyze_once(request)
            last = result
            attempt = self._last_attempt
            self._last_attempt = None
            policy = retry_policy(None)
            if attempt is not None:
                diagnostic = attempt.diagnostic
                policy = retry_policy(
                    diagnostic.error_class if diagnostic else None,
                    diagnostic.retry_after_seconds if diagnostic else None,
                )
                estimated = attempt.estimated_cost
                currency = attempt.cost_currency
                pricing_version = attempt.pricing_version
                if attempt.usage is not None and estimated is None:
                    estimated, currency, pricing_version = estimate_cost(
                        attempt.provider,
                        attempt.model or "",
                        attempt.usage,
                        attempt.finished_at,
                    )
                if result.state is ProviderState.AVAILABLE:
                    decision = DECISION_SUCCESS_AFTER_RETRY if ordinal > 1 else DECISION_SUCCESS
                elif policy.eligible and ordinal < bounded:
                    decision = DECISION_RETRY
                else:
                    decision = DECISION_STOP
                collected.append(
                    replace(
                        attempt,
                        attempt_index=ordinal,
                        retry_eligible=policy.eligible,
                        decision=decision,
                        estimated_cost=estimated,
                        cost_currency=currency,
                        pricing_version=pricing_version,
                    )
                )

            if result.state is ProviderState.AVAILABLE:
                self._last_attempts = tuple(collected)
                return result
            if result.state is ProviderState.NOT_CONFIGURED:
                self._last_attempts = tuple(collected)
                return result
            if attempt is not None and policy.eligible and ordinal < bounded:
                self._runtime_state = RuntimeProviderState.ACTIVE
                if policy.delay_seconds > 0:
                    time.sleep(policy.delay_seconds)
                continue
            self._last_attempts = tuple(collected)
            return result

        self._last_attempts = tuple(collected)
        return last or ContentRemediationResult(
            ProviderState.UNAVAILABLE,
            reason="AI_PROVIDER_UNAVAILABLE",
            provider=self.name,
            model=self.model,
            reasoning_profile=self.reasoning_profile,
        )

    def _analyze_once(self, request: ContentRemediationRequest) -> ContentRemediationResult:
        self._last_attempt = None
'''
text = replace_once(text, old, new, "m20 extension analyze wrapper")
text = replace_once(
    text,
    "    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:\n        item = self._last_attempt\n        self._last_attempt = None\n        return (item,) if item is not None else ()",
    "    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:\n"
    "        items = self._last_attempts\n"
    "        self._last_attempts = ()\n"
    "        self._last_attempt = None\n"
    "        return items",
    "m20 extension consume attempts",
)
write(path, text)


# Old exposure tests intentionally encoded the pre-retry upper bound. Update
# only the maximum side; the minimum still assumes the first call succeeds.
path = "tests/test_console_provider_registry.py"
text = read(path)
text = replace_once(
    text,
    "self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (1, 2))",
    "self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (1, 4))",
    "auto exposure bounded retry expectation",
)
write(path, text)

path = "tests/test_interactive_console.py"
text = read(path)
text = replace_once(
    text,
    "self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (6, 12))",
    "self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (6, 24))",
    "txt exposure bounded retry expectation",
)
text = replace_once(
    text,
    "self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (1, 5))",
    "self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (1, 10))",
    "seed exposure bounded retry expectation",
)
write(path, text)

print("AI retry compatibility regressions patched")
