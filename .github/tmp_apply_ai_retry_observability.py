from __future__ import annotations

from pathlib import Path
import re

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


def regex_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{label}: expected one regex match, found {count}")
    return updated


# ---------------------------------------------------------------------------
# M18 core providers: bounded transient retry + explicit AUTO fallback metadata
# ---------------------------------------------------------------------------
path = "src/searchgeo/m18_ai.py"
text = read(path)
text = replace_once(
    text,
    "from urllib.error import HTTPError, URLError\n\nfrom searchgeo.openai_provider import (",
    "from urllib.error import HTTPError, URLError\n\nfrom searchgeo.ai_resilience import (\n"
    "    DECISION_FALLBACK,\n"
    "    DECISION_FALLBACK_SUCCESS,\n"
    "    DECISION_RETRY,\n"
    "    DECISION_STOP,\n"
    "    DECISION_SUCCESS,\n"
    "    DECISION_SUCCESS_AFTER_RETRY,\n"
    "    MAX_AUTO_ATTEMPTS_PER_CONTEXT,\n"
    "    MAX_PROVIDER_ATTEMPTS_PER_CONTEXT,\n"
    "    parse_retry_after,\n"
    "    retry_policy,\n"
    ")\nfrom searchgeo.openai_provider import (",
    "m18 imports",
)
text = replace_once(
    text,
    "    request_id: str | None = None\n\n    @property",
    "    request_id: str | None = None\n    retry_after_seconds: float | None = None\n\n    @property",
    "diagnostic retry-after",
)
text = replace_once(
    text,
    "    semantic_contract_version: str = SEMANTIC_CONTRACT_VERSION\n\n\n@dataclass(frozen=True, slots=True)\nclass SemanticProviderResult",
    "    semantic_contract_version: str = SEMANTIC_CONTRACT_VERSION\n"
    "    retry_eligible: bool = False\n"
    "    decision: str = DECISION_STOP\n"
    "    fallback_from_provider: str | None = None\n"
    "    fallback_reason: str | None = None\n\n\n@dataclass(frozen=True, slots=True)\nclass SemanticProviderResult",
    "attempt resilience fields",
)
text = replace_once(
    text,
    "    except (AttributeError, TypeError):\n        pass\n    return ProviderDiagnostic(\n        error_class=_classify_http_error(int(exc.code), error_type, error_code),\n        http_status=int(exc.code),\n        error_type=error_type,\n        error_code=error_code,\n        request_id=request_id,\n    )",
    "    except (AttributeError, TypeError):\n        pass\n"
    "    retry_after_seconds = None\n"
    "    try:\n"
    "        if exc.headers is not None:\n"
    "            retry_after_seconds = parse_retry_after(exc.headers.get('Retry-After'))\n"
    "    except (AttributeError, TypeError, ValueError):\n"
    "        pass\n"
    "    return ProviderDiagnostic(\n"
    "        error_class=_classify_http_error(int(exc.code), error_type, error_code),\n"
    "        http_status=int(exc.code),\n"
    "        error_type=error_type,\n"
    "        error_code=error_code,\n"
    "        request_id=request_id,\n"
    "        retry_after_seconds=retry_after_seconds,\n"
    "    )",
    "m18 retry-after parse",
)
text = replace_once(
    text,
    "        self._last_attempt: ProviderAttempt | None = None\n        self._history: list[ProviderAttempt] = []",
    "        self._last_attempt: ProviderAttempt | None = None\n"
    "        self._last_attempts: tuple[ProviderAttempt, ...] = ()\n"
    "        self._history: list[ProviderAttempt] = []",
    "m18 attempt buffer",
)
wrapper = '''    def analyze(
        self,
        semantic_input: SemanticInput,
        *,
        max_attempts: int = MAX_PROVIDER_ATTEMPTS_PER_CONTEXT,
    ) -> SemanticProviderResult:
        """Execute at most one bounded retry for transient integration failures."""
        self._last_attempts = ()
        collected: list[ProviderAttempt] = []
        bounded = max(1, min(int(max_attempts), MAX_PROVIDER_ATTEMPTS_PER_CONTEXT))
        last_result: SemanticProviderResult | None = None
        for ordinal in range(1, bounded + 1):
            result = self._analyze_once(semantic_input)
            last_result = result
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
                        attempt.provider, attempt.model or "", attempt.usage, attempt.finished_at
                    )
                if result.status is ProviderState.AVAILABLE:
                    decision = DECISION_SUCCESS_AFTER_RETRY if ordinal > 1 else DECISION_SUCCESS
                elif policy.eligible and ordinal < bounded:
                    decision = DECISION_RETRY
                else:
                    decision = DECISION_STOP
                annotated = replace(
                    attempt,
                    attempt_index=ordinal,
                    retry_eligible=policy.eligible,
                    decision=decision,
                    estimated_cost=estimated,
                    cost_currency=currency,
                    pricing_version=pricing_version,
                )
                if self._history and self._history[-1] == attempt:
                    self._history[-1] = annotated
                collected.append(annotated)

            if result.status is ProviderState.AVAILABLE:
                self._last_attempts = tuple(collected)
                return result
            if result.status is ProviderState.NOT_CONFIGURED:
                self._last_attempts = tuple(collected)
                return result
            if attempt is not None and policy.eligible and ordinal < bounded:
                # _analyze_once quarantines every failure. A transient retry is the
                # only case allowed to reactivate it, and only for this one retry.
                self._runtime_state = RuntimeProviderState.ACTIVE
                if policy.delay_seconds > 0:
                    time.sleep(policy.delay_seconds)
                continue
            self._last_attempts = tuple(collected)
            return result

        self._last_attempts = tuple(collected)
        return last_result or SemanticProviderResult(
            ProviderState.UNAVAILABLE,
            reason="AI_PROVIDER_UNAVAILABLE",
            provider=self.name,
            model=self.model,
            reasoning_profile=self.reasoning_profile,
        )

    def _analyze_once(self, semantic_input: SemanticInput) -> SemanticProviderResult:
        self._last_attempt = None
'''
text = replace_once(
    text,
    "    def analyze(self, semantic_input: SemanticInput) -> SemanticProviderResult:\n        self._last_attempt = None\n",
    wrapper,
    "m18 analyze wrapper",
)
text = replace_once(
    text,
    "    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:\n        attempt = self._last_attempt\n        self._last_attempt = None\n        return (attempt,) if attempt is not None else ()",
    "    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:\n"
    "        attempts = self._last_attempts\n"
    "        self._last_attempts = ()\n"
    "        self._last_attempt = None\n"
    "        return attempts",
    "m18 consume attempts",
)
text = replace_once(
    text,
    '        return ("MULTI_PROVIDER_ROUTING", "AUDIT_QUARANTINE", "URL_PROVIDER_LOCK", "USAGE_TELEMETRY")',
    '        return ("MULTI_PROVIDER_ROUTING", "AUDIT_QUARANTINE", "BOUNDED_RETRY", "BOUNDED_AUTO_FALLBACK", "USAGE_TELEMETRY")',
    "router capabilities",
)
router_method = '''    def analyze(self, semantic_input: SemanticInput) -> SemanticProviderResult:
        self._last_attempts = ()
        if not self.providers:
            return SemanticProviderResult(ProviderState.NOT_CONFIGURED, reason="AI_NOT_CONFIGURED", provider="AUTO", reasoning_profile="NONE")

        candidates = list(self._healthy_candidates())
        pinned_name = self._pins.get(semantic_input.page_url)
        if pinned_name:
            # A previous success keeps preference, but an integration failure may
            # legitimately fall back to another healthy provider for this context.
            candidates.sort(key=lambda item: (0 if item.name == pinned_name else 1, item.policy.rank))
        if not candidates:
            return SemanticProviderResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_CHAIN_EXHAUSTED", provider="AUTO", reasoning_profile="NONE")

        attempts: list[ProviderAttempt] = []
        last_result: SemanticProviderResult | None = None
        fallback_from: str | None = None
        fallback_reason: str | None = None

        for candidate_index, provider in enumerate(candidates):
            remaining = MAX_AUTO_ATTEMPTS_PER_CONTEXT - len(attempts)
            if remaining <= 0:
                break
            result = provider.analyze(
                semantic_input,
                max_attempts=min(MAX_PROVIDER_ATTEMPTS_PER_CONTEXT, remaining),
            )
            local = list(provider.consume_attempts())
            if fallback_from is not None:
                local = [
                    replace(
                        item,
                        fallback_from_provider=fallback_from,
                        fallback_reason=fallback_reason,
                    )
                    for item in local
                ]
            local = [
                replace(item, attempt_index=len(attempts) + offset)
                for offset, item in enumerate(local, 1)
            ]
            attempts.extend(local)
            last_result = result

            if result.status is ProviderState.AVAILABLE:
                if fallback_from is not None and attempts:
                    attempts[-1] = replace(
                        attempts[-1],
                        decision=DECISION_FALLBACK_SUCCESS,
                        fallback_from_provider=fallback_from,
                        fallback_reason=fallback_reason,
                    )
                self._pins[semantic_input.page_url] = provider.name
                self._promote(provider.name)
                self._successful_urls[provider.name].add(semantic_input.page_url)
                self._last_attempts = tuple(attempts)
                self._history.extend(self._last_attempts)
                return result

            if result.status is ProviderState.NOT_CONFIGURED:
                continue

            self._quarantine(provider.name)
            has_next = (
                candidate_index < len(candidates) - 1
                and len(attempts) < MAX_AUTO_ATTEMPTS_PER_CONTEXT
            )
            if has_next:
                if attempts:
                    attempts[-1] = replace(attempts[-1], decision=DECISION_FALLBACK)
                fallback_from = provider.name
                fallback_reason = result.reason or "AI_PROVIDER_UNAVAILABLE"

        self._last_attempts = tuple(attempts)
        self._history.extend(self._last_attempts)
        if len(attempts) >= MAX_AUTO_ATTEMPTS_PER_CONTEXT and self._healthy_candidates():
            return SemanticProviderResult(
                ProviderState.UNAVAILABLE,
                reason="AI_PROVIDER_ATTEMPT_BUDGET_EXHAUSTED",
                provider="AUTO",
                reasoning_profile="NONE",
            )
        if self._healthy_candidates():
            return last_result or SemanticProviderResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_UNAVAILABLE", provider="AUTO", reasoning_profile="NONE")
        return SemanticProviderResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_CHAIN_EXHAUSTED", provider="AUTO", reasoning_profile="NONE")

'''
text = regex_once(
    text,
    r"    def analyze\(self, semantic_input: SemanticInput\) -> SemanticProviderResult:\n        self\._last_attempts = \(\)\n        if not self\.providers:.*?\n    def consume_attempts\(self\) -> tuple\[ProviderAttempt, \.\.\.\]:\n",
    router_method + "    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:\n",
    "router analyze",
)
write(path, text)


# ---------------------------------------------------------------------------
# Extension providers: same bounded transient retry, never AUTO by themselves.
# ---------------------------------------------------------------------------
path = "src/searchgeo/provider_extensions.py"
text = read(path)
text = replace_once(
    text,
    "from urllib.request import Request, urlopen\n\nfrom searchgeo.m18_ai import (",
    "from urllib.request import Request, urlopen\n\nfrom searchgeo.ai_resilience import (\n"
    "    DECISION_RETRY, DECISION_STOP, DECISION_SUCCESS, DECISION_SUCCESS_AFTER_RETRY,\n"
    "    MAX_PROVIDER_ATTEMPTS_PER_CONTEXT, parse_retry_after, retry_policy,\n"
    ")\nfrom searchgeo.m18_ai import (",
    "extension resilience imports",
)
text = replace_once(
    text,
    "    ProviderUsage,\n    RuntimeProviderState,",
    "    ProviderUsage,\n    RuntimeProviderState,\n    estimate_cost,",
    "extension estimate import",
)
text = replace_once(
    text,
    "    return ProviderDiagnostic(\n        error_class=_classify_http_error(int(exc.code), error_type, error_code),\n        http_status=int(exc.code),\n        error_type=error_type,\n        error_code=error_code,\n        request_id=request_id,\n    )",
    "    retry_after_seconds = None\n"
    "    try:\n"
    "        if exc.headers is not None:\n"
    "            retry_after_seconds = parse_retry_after(exc.headers.get('Retry-After'))\n"
    "    except (AttributeError, TypeError, ValueError):\n"
    "        pass\n"
    "    return ProviderDiagnostic(\n"
    "        error_class=_classify_http_error(int(exc.code), error_type, error_code),\n"
    "        http_status=int(exc.code),\n"
    "        error_type=error_type,\n"
    "        error_code=error_code,\n"
    "        request_id=request_id,\n"
    "        retry_after_seconds=retry_after_seconds,\n"
    "    )",
    "extension retry-after",
)
text = replace_once(
    text,
    "        self._last_attempt: ProviderAttempt | None = None\n        self._history: list[ProviderAttempt] = []",
    "        self._last_attempt: ProviderAttempt | None = None\n"
    "        self._last_attempts: tuple[ProviderAttempt, ...] = ()\n"
    "        self._history: list[ProviderAttempt] = []",
    "extension buffer",
)
ext_wrapper = '''    def analyze(
        self,
        semantic_input: SemanticInput,
        *,
        max_attempts: int = MAX_PROVIDER_ATTEMPTS_PER_CONTEXT,
    ) -> SemanticProviderResult:
        self._last_attempts = ()
        collected: list[ProviderAttempt] = []
        bounded = max(1, min(int(max_attempts), MAX_PROVIDER_ATTEMPTS_PER_CONTEXT))
        last_result: SemanticProviderResult | None = None
        for ordinal in range(1, bounded + 1):
            result = self._analyze_once(semantic_input)
            last_result = result
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
                        attempt.provider, attempt.model or "", attempt.usage, attempt.finished_at
                    )
                decision = (
                    DECISION_SUCCESS_AFTER_RETRY if result.status is ProviderState.AVAILABLE and ordinal > 1
                    else DECISION_SUCCESS if result.status is ProviderState.AVAILABLE
                    else DECISION_RETRY if policy.eligible and ordinal < bounded
                    else DECISION_STOP
                )
                annotated = replace(
                    attempt,
                    attempt_index=ordinal,
                    retry_eligible=policy.eligible,
                    decision=decision,
                    estimated_cost=estimated,
                    cost_currency=currency,
                    pricing_version=pricing_version,
                )
                if self._history and self._history[-1] == attempt:
                    self._history[-1] = annotated
                collected.append(annotated)
            if result.status is ProviderState.AVAILABLE:
                self._last_attempts = tuple(collected)
                return result
            if result.status is ProviderState.NOT_CONFIGURED:
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
        return last_result or SemanticProviderResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_UNAVAILABLE", provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile)

    def _analyze_once(self, semantic_input: SemanticInput) -> SemanticProviderResult:
        self._last_attempt = None
'''
text = replace_once(
    text,
    "    def analyze(self, semantic_input: SemanticInput) -> SemanticProviderResult:\n        self._last_attempt = None\n",
    ext_wrapper,
    "extension analyze wrapper",
)
text = replace_once(
    text,
    "    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:\n        attempt = self._last_attempt\n        self._last_attempt = None\n        return (attempt,) if attempt is not None else ()",
    "    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:\n"
    "        attempts = self._last_attempts\n"
    "        self._last_attempts = ()\n"
    "        self._last_attempt = None\n"
    "        return attempts",
    "extension consume attempts",
)
write(path, text)


# ---------------------------------------------------------------------------
# M20 remediation: same paid-call protections and fallback annotations.
# ---------------------------------------------------------------------------
path = "src/searchgeo/m20_ai.py"
text = read(path)
text = replace_once(
    text,
    "from urllib.error import HTTPError, URLError\n\nfrom searchgeo.content_context import configured_content_analysis_context",
    "from urllib.error import HTTPError, URLError\n\nfrom searchgeo.ai_resilience import (\n"
    "    DECISION_FALLBACK, DECISION_FALLBACK_SUCCESS, DECISION_RETRY, DECISION_STOP,\n"
    "    DECISION_SUCCESS, DECISION_SUCCESS_AFTER_RETRY, MAX_AUTO_ATTEMPTS_PER_CONTEXT,\n"
    "    MAX_PROVIDER_ATTEMPTS_PER_CONTEXT, retry_policy,\n"
    ")\nfrom searchgeo.content_context import configured_content_analysis_context",
    "m20 resilience imports",
)
text = replace_once(
    text,
    "        self._last_attempt: ProviderAttempt | None = None\n\n    def analyze(self, request: ContentRemediationRequest) -> ContentRemediationResult:\n        self._last_attempt = None\n",
    "        self._last_attempt: ProviderAttempt | None = None\n"
    "        self._last_attempts: tuple[ProviderAttempt, ...] = ()\n\n"
    "    def analyze(\n"
    "        self, request: ContentRemediationRequest, *, max_attempts: int = MAX_PROVIDER_ATTEMPTS_PER_CONTEXT\n"
    "    ) -> ContentRemediationResult:\n"
    "        self._last_attempts = ()\n"
    "        collected: list[ProviderAttempt] = []\n"
    "        bounded = max(1, min(int(max_attempts), MAX_PROVIDER_ATTEMPTS_PER_CONTEXT))\n"
    "        last: ContentRemediationResult | None = None\n"
    "        for ordinal in range(1, bounded + 1):\n"
    "            result = self._analyze_once(request)\n"
    "            last = result\n"
    "            attempt = self._last_attempt\n"
    "            self._last_attempt = None\n"
    "            policy = retry_policy(None)\n"
    "            if attempt is not None:\n"
    "                diagnostic = attempt.diagnostic\n"
    "                policy = retry_policy(diagnostic.error_class if diagnostic else None, diagnostic.retry_after_seconds if diagnostic else None)\n"
    "                estimated = attempt.estimated_cost\n"
    "                currency = attempt.cost_currency\n"
    "                pricing_version = attempt.pricing_version\n"
    "                if attempt.usage is not None and estimated is None:\n"
    "                    estimated, currency, pricing_version = estimate_cost(attempt.provider, attempt.model or '', attempt.usage, attempt.finished_at)\n"
    "                decision = (DECISION_SUCCESS_AFTER_RETRY if result.state is ProviderState.AVAILABLE and ordinal > 1 else DECISION_SUCCESS if result.state is ProviderState.AVAILABLE else DECISION_RETRY if policy.eligible and ordinal < bounded else DECISION_STOP)\n"
    "                collected.append(replace(attempt, attempt_index=ordinal, retry_eligible=policy.eligible, decision=decision, estimated_cost=estimated, cost_currency=currency, pricing_version=pricing_version))\n"
    "            if result.state is ProviderState.AVAILABLE:\n"
    "                self._last_attempts = tuple(collected)\n"
    "                return result\n"
    "            if result.state is ProviderState.NOT_CONFIGURED:\n"
    "                self._last_attempts = tuple(collected)\n"
    "                return result\n"
    "            if attempt is not None and policy.eligible and ordinal < bounded:\n"
    "                self._runtime_state = RuntimeProviderState.ACTIVE\n"
    "                if policy.delay_seconds > 0:\n"
    "                    time.sleep(policy.delay_seconds)\n"
    "                continue\n"
    "            self._last_attempts = tuple(collected)\n"
    "            return result\n"
    "        self._last_attempts = tuple(collected)\n"
    "        return last or ContentRemediationResult(ProviderState.UNAVAILABLE, reason='AI_PROVIDER_UNAVAILABLE', provider=self.name, model=self.model, reasoning_profile=self.reasoning_profile)\n\n"
    "    def _analyze_once(self, request: ContentRemediationRequest) -> ContentRemediationResult:\n"
    "        self._last_attempt = None\n",
    "m20 analyze wrapper",
)
text = replace_once(
    text,
    "    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:\n        item = self._last_attempt\n        self._last_attempt = None\n        return (item,) if item else ()",
    "    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:\n"
    "        items = self._last_attempts\n"
    "        self._last_attempts = ()\n"
    "        self._last_attempt = None\n"
    "        return items",
    "m20 consume attempts",
)
m20_router = '''    def analyze(self, request: ContentRemediationRequest) -> ContentRemediationResult:
        self._last_attempts = ()
        if not self.providers:
            return ContentRemediationResult(ProviderState.NOT_CONFIGURED, reason="AI_NOT_CONFIGURED")
        candidates = list(self._healthy_candidates())
        pinned = self._pins.get(request.page_url)
        if pinned:
            candidates.sort(key=lambda item: (0 if item.name == pinned else 1, item.policy.rank))
        attempts: list[ProviderAttempt] = []
        last: ContentRemediationResult | None = None
        fallback_from: str | None = None
        fallback_reason: str | None = None
        for index, provider in enumerate(candidates):
            remaining = MAX_AUTO_ATTEMPTS_PER_CONTEXT - len(attempts)
            if remaining <= 0:
                break
            result = provider.analyze(request, max_attempts=min(MAX_PROVIDER_ATTEMPTS_PER_CONTEXT, remaining))
            local = list(provider.consume_attempts())
            if fallback_from is not None:
                local = [replace(item, fallback_from_provider=fallback_from, fallback_reason=fallback_reason) for item in local]
            local = [replace(item, attempt_index=len(attempts) + offset) for offset, item in enumerate(local, 1)]
            attempts.extend(local)
            last = result
            if result.state is ProviderState.AVAILABLE:
                if fallback_from is not None and attempts:
                    attempts[-1] = replace(attempts[-1], decision=DECISION_FALLBACK_SUCCESS, fallback_from_provider=fallback_from, fallback_reason=fallback_reason)
                self._pins[request.page_url] = provider.name
                self._last_attempts = tuple(attempts)
                return result
            if result.state is ProviderState.NOT_CONFIGURED:
                continue
            self._states[provider.name] = RuntimeProviderState.QUARANTINED_FOR_AUDIT
            has_next = index < len(candidates) - 1 and len(attempts) < MAX_AUTO_ATTEMPTS_PER_CONTEXT
            if has_next:
                if attempts:
                    attempts[-1] = replace(attempts[-1], decision=DECISION_FALLBACK)
                fallback_from = provider.name
                fallback_reason = result.reason or "AI_PROVIDER_UNAVAILABLE"
        self._last_attempts = tuple(attempts)
        if len(attempts) >= MAX_AUTO_ATTEMPTS_PER_CONTEXT and self._healthy_candidates():
            return ContentRemediationResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_ATTEMPT_BUDGET_EXHAUSTED")
        if not self._healthy_candidates():
            return ContentRemediationResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_CHAIN_EXHAUSTED")
        return last or ContentRemediationResult(ProviderState.UNAVAILABLE, reason="AI_PROVIDER_UNAVAILABLE")

'''
text = regex_once(
    text,
    r"    def analyze\(self, request: ContentRemediationRequest\) -> ContentRemediationResult:\n        self\._last_attempts = \(\)\n        if not self\.providers:.*?\n    def consume_attempts\(self\) -> tuple\[ProviderAttempt, \.\.\.\]:\n",
    m20_router + "    def consume_attempts(self) -> tuple[ProviderAttempt, ...]:\n",
    "m20 router",
)
write(path, text)


# ---------------------------------------------------------------------------
# Persistence: additive migration; old audit DBs remain readable.
# ---------------------------------------------------------------------------
path = "src/searchgeo/m18_persistence.py"
text = read(path)
text = replace_once(
    text,
    "            )\n            for item in PRICING_CATALOG:",
    "            )\n"
    "            existing_attempt_columns = {\n"
    "                str(row['name']) for row in self._connection.execute('PRAGMA table_info(ai_provider_attempts)').fetchall()\n"
    "            }\n"
    "            for column, ddl in (\n"
    "                ('retry_eligible', 'INTEGER NOT NULL DEFAULT 0'),\n"
    "                ('retry_after_seconds', 'REAL'),\n"
    "                ('decision', \"TEXT NOT NULL DEFAULT 'STOP'\"),\n"
    "                ('fallback_from_provider', 'TEXT'),\n"
    "                ('fallback_reason', 'TEXT'),\n"
    "            ):\n"
    "                if column not in existing_attempt_columns:\n"
    "                    self._connection.execute(f'ALTER TABLE ai_provider_attempts ADD COLUMN {column} {ddl}')\n"
    "            for item in PRICING_CATALOG:",
    "persistence migration",
)
add_attempt = '''    def add_attempt(
        self,
        *,
        attempt_id: str,
        audit_id: str,
        page_id: str,
        snapshot_id: str,
        url: str,
        device: str,
        attempt: ProviderAttempt,
    ) -> None:
        diagnostic = attempt.diagnostic
        usage = attempt.usage
        columns = (
            "attempt_id", "audit_id", "page_id", "snapshot_id", "url", "device", "provider", "model",
            "reasoning_profile", "provider_rank", "attempt_index", "started_at", "finished_at", "duration_ms",
            "status", "http_status", "error_class", "error_type", "error_code", "request_id",
            "retry_eligible", "retry_after_seconds", "decision", "fallback_from_provider", "fallback_reason",
            "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens",
            "estimated_cost", "cost_currency", "pricing_version", "request_message_summary", "request_payload_hash",
            "semantic_contract_version", "provider_qualification", "provider_reliability_score", "qualification_version",
        )
        values = (
            attempt_id, audit_id, page_id, snapshot_id, url, device, attempt.provider, attempt.model,
            attempt.reasoning_profile, attempt.provider_rank, attempt.attempt_index,
            attempt.started_at.isoformat(), attempt.finished_at.isoformat(), attempt.duration_ms, attempt.status.value,
            diagnostic.http_status if diagnostic else None,
            diagnostic.error_class.value if diagnostic and diagnostic.error_class else None,
            diagnostic.error_type if diagnostic else None,
            diagnostic.error_code if diagnostic else None,
            diagnostic.request_id if diagnostic else None,
            1 if attempt.retry_eligible else 0,
            diagnostic.retry_after_seconds if diagnostic else None,
            attempt.decision,
            attempt.fallback_from_provider,
            attempt.fallback_reason,
            usage.input_tokens if usage else None,
            usage.cached_input_tokens if usage else None,
            usage.output_tokens if usage else None,
            usage.reasoning_tokens if usage else None,
            usage.total_tokens if usage else None,
            attempt.estimated_cost,
            attempt.cost_currency,
            attempt.pricing_version,
            attempt.request_message_summary[:512],
            attempt.request_payload_hash,
            attempt.semantic_contract_version,
            attempt.provider_qualification,
            attempt.provider_reliability_score,
            attempt.qualification_version,
        )
        placeholders = ",".join("?" for _ in columns)
        with self._connection:
            self._connection.execute(
                f"INSERT INTO ai_provider_attempts ({','.join(columns)}) VALUES ({placeholders})",
                values,
            )

'''
text = regex_once(
    text,
    r"    def add_attempt\(.*?\n    def list_attempts\(self, audit_id: str\) -> tuple\[sqlite3\.Row, \.\.\.\]:\n",
    add_attempt + "    def list_attempts(self, audit_id: str) -> tuple[sqlite3.Row, ...]:\n",
    "persistence add_attempt",
)
write(path, text)


# ---------------------------------------------------------------------------
# Report: explicit error class/type/code/request id, retry and fallback cause.
# ---------------------------------------------------------------------------
path = "src/searchgeo/m18_reporting.py"
text = read(path)
report_section = '''def _report_section(session: sqlite3.Row, attempts: list[sqlite3.Row], snapshot_count: int) -> str:
    enabled = bool(session["enabled"])
    configured = _provider_configured(session)
    success = [row for row in attempts if row["status"] == "SUCCESS"]
    failures = [row for row in attempts if row["status"] != "SUCCESS"]
    provider_counts: dict[str, set[str]] = {}
    for row in success:
        provider_counts.setdefault(str(row["provider"]), set()).add(str(row["url"]))
    counts_html = "<br>".join(f"{escape(provider)}: {len(urls)}" for provider, urls in sorted(provider_counts.items())) or "NENHUMA"
    configured_chain = _json_list(session["configured_chain"])
    initial = _provider_label(session["initial_provider"], session["initial_model"])
    effective = _provider_label(session["effective_provider"], session["effective_model"])
    if not session["effective_provider"]:
        effective = "NÃO HOUVE RESULTADO SEMÂNTICO VÁLIDO"
    retry_count = sum(1 for row in attempts if _row_value(row, "decision") == "RETRY")
    fallback_used = any(_row_value(row, "fallback_from_provider") for row in attempts)
    failed_cost = sum(float(_row_value(row, "estimated_cost", 0.0) or 0.0) for row in failures)

    metrics = (
        _metric("IA habilitada pelo comando", "SIM" if enabled else "NÃO")
        + _metric("Provider configurado", "SIM" if configured else "NÃO")
        + _metric("Estratégia", str(session["strategy"]))
        + _metric("Provider que deveria atender primeiro", initial or "NÃO APLICÁVEL")
        + _metric("Provider efetivamente utilizado", effective)
        + _metric("Fallback utilizado", "SIM" if fallback_used else "NÃO")
        + _metric("Retries transitórios", str(retry_count))
        + _metric("Modelo efetivo", str(session["effective_model"] or "NÃO APLICÁVEL"))
        + _metric("Profundidade", str(session["effective_reasoning_profile"] or session["initial_reasoning_profile"] or "NÃO APLICÁVEL"))
        + _metric("Status", str(session["status"]))
        + _metric("Chamadas externas realizadas", str(len(attempts)))
        + _metric("Tentativas com sucesso", str(len(success)))
        + _metric("Custo estimado de tentativas sem sucesso", f"{failed_cost:.8f} USD" if failed_cost else "0 ou não mensurável")
        + _metric("URLs analisadas com sucesso por provider", counts_html)
    )
    chain = " → ".join(
        f"{escape(str(item.get('provider','?')))} / {escape(str(item.get('model','?')))}"
        for item in configured_chain if isinstance(item, dict)
    ) or "NENHUMA IA ELEGÍVEL"
    failover = _failover_summary(attempts)
    failure_detail = _failure_detail(attempts)
    rows = "".join(_attempt_row(row) for row in attempts)
    if not rows:
        rows = "<tr><td colspan='19'>Nenhuma chamada externa foi realizada.</td></tr>"
    coverage = f"{len(success)}/{snapshot_count} contextos Desktop/Mobile com tentativa bem-sucedida" if snapshot_count else "NÃO APLICÁVEL"
    return (
        "<section id='ai-runtime' class='m18-ai'>"
        "<h2>Uso de IA — execução, erros, retry e fallback</h2>"
        "<p class='m18-note'>Falhas de provider são limitações operacionais da auditoria; não são findings do website. Retry só ocorre para erro transitório, no máximo uma vez por provider/contexto; AUTO também possui teto global de chamadas.</p>"
        f"<div class='m18-grid'>{metrics}</div>"
        f"<p><strong>Cadeia inicial imutável:</strong> {chain}</p>"
        f"<p><strong>Cobertura semântica externa:</strong> {escape(coverage)}</p>"
        f"<p><strong>Fallback:</strong> {failover}</p>"
        f"{failure_detail}"
        "<h3>Relatório detalhado de uso da IA</h3><div class='m18-table-wrap'><table>"
        "<thead><tr><th>URL</th><th>Device</th><th>Operação</th><th>Tentativa</th><th>Provider</th><th>Model</th><th>Status</th><th>Error class</th><th>Error type</th><th>HTTP</th><th>Error code</th><th>Request ID</th><th>Retryable</th><th>Decisão</th><th>Fallback de</th><th>Tokens input</th><th>Tokens output</th><th>Estimated cost</th><th>Duration</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
        "<p class='m18-note'>Estimated cost usa catálogo versionado local e não representa invoice/billing. Uma tentativa falha pode ter custo quando o provider reporta tokens; quando não há telemetria suficiente, o relatório não inventa custo zero.</p>"
        "</section>"
    )

'''
text = regex_once(
    text,
    r"def _report_section\(session: sqlite3\.Row, attempts: list\[sqlite3\.Row\], snapshot_count: int\) -> str:.*?\ndef _remediation_context",
    report_section + "def _remediation_context",
    "m18 report section",
)
report_helpers = '''def _row_value(row: Any, key: str, default: Any = None) -> Any:
    try:
        keys = row.keys()
    except AttributeError:
        keys = row
    try:
        if key in keys:
            return row[key]
    except (KeyError, TypeError):
        pass
    return default


def _operation(row: Any) -> str:
    contract = str(_row_value(row, "semantic_contract_version", "") or "")
    return "Remediação textual" if contract.startswith("M20-") else "Análise semântica"


def _attempt_row(row: sqlite3.Row) -> str:
    cost = "—"
    if _row_value(row, "estimated_cost") is not None:
        cost = f"{float(_row_value(row, 'estimated_cost')):.8f} {_row_value(row, 'cost_currency', '') or ''}".strip()
    retryable = "SIM" if bool(_row_value(row, "retry_eligible", 0)) else "NÃO"
    return (
        "<tr>"
        f"<td title='{escape(str(row['url']))}'>{escape(_truncate(str(row['url']), 72))}</td>"
        f"<td>{escape(str(row['device'] or '—'))}</td>"
        f"<td>{escape(_operation(row))}</td>"
        f"<td>{escape(str(row['attempt_index']))}</td>"
        f"<td>{escape(str(row['provider']))}</td>"
        f"<td>{escape(str(row['model'] or '—'))}</td>"
        f"<td>{escape(str(row['status']))}</td>"
        f"<td>{escape(str(_row_value(row, 'error_class', '—') or '—'))}</td>"
        f"<td>{escape(str(_row_value(row, 'error_type', '—') or '—'))}</td>"
        f"<td>{escape(str(_row_value(row, 'http_status', '—') or '—'))}</td>"
        f"<td>{escape(str(_row_value(row, 'error_code', '—') or '—'))}</td>"
        f"<td>{escape(str(_row_value(row, 'request_id', '—') or '—'))}</td>"
        f"<td>{retryable}</td>"
        f"<td>{escape(str(_row_value(row, 'decision', '—') or '—'))}</td>"
        f"<td>{escape(str(_row_value(row, 'fallback_from_provider', '—') or '—'))}</td>"
        f"<td>{_nullable(_row_value(row, 'input_tokens'))}</td>"
        f"<td>{_nullable(_row_value(row, 'output_tokens'))}</td>"
        f"<td>{escape(cost)}</td>"
        f"<td>{int(row['duration_ms'])} ms</td>"
        "</tr>"
    )


def _failure_detail(attempts: list[sqlite3.Row]) -> str:
    failures = [row for row in attempts if str(row["status"]) != "SUCCESS"]
    if not failures:
        return "<p><strong>Diagnóstico:</strong> nenhuma falha de integração de IA registrada.</p>"
    items: list[str] = []
    for row in failures[:12]:
        parts = [
            f"{row['provider']}/{row['model'] or '—'}",
            str(_row_value(row, "error_class", row["status"]) or row["status"]),
        ]
        if _row_value(row, "error_type"):
            parts.append(f"type={_row_value(row, 'error_type')}")
        if _row_value(row, "http_status"):
            parts.append(f"HTTP={_row_value(row, 'http_status')}")
        if _row_value(row, "error_code"):
            parts.append(f"code={_row_value(row, 'error_code')}")
        parts.append(f"retryable={'SIM' if bool(_row_value(row, 'retry_eligible', 0)) else 'NÃO'}")
        parts.append(f"decisão={_row_value(row, 'decision', 'STOP')}")
        items.append("<li>" + escape(" · ".join(parts)) + "</li>")
    return (
        "<div class='m18-note'><strong>Diagnóstico das falhas:</strong><ul>"
        + "".join(items)
        + "</ul><p>Erros de autenticação, permissão, crédito, quota, modelo e contrato não são repetidos automaticamente. Erros transitórios podem ter uma única nova tentativa.</p></div>"
    )


def _failover_summary(attempts: list[sqlite3.Row]) -> str:
    events: list[str] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in attempts:
        source = str(_row_value(row, "fallback_from_provider", "") or "")
        if not source:
            continue
        target = str(row["provider"])
        reason = str(_row_value(row, "fallback_reason", "AI_PROVIDER_UNAVAILABLE") or "AI_PROVIDER_UNAVAILABLE")
        outcome = str(row["status"])
        key = (source, target, reason, str(row["url"]))
        if key in seen:
            continue
        seen.add(key)
        events.append(f"{source} deveria atender o contexto, falhou por {reason}; fallback para {target} ({outcome})")
    if events:
        return escape("; ".join(events))

    # Compatibility for pre-migration audit DBs.
    by_context: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in attempts:
        by_context.setdefault((str(row["url"]), str(row["device"])), []).append(row)
    legacy: list[str] = []
    for rows in by_context.values():
        successful = next((row for row in rows if row["status"] == "SUCCESS"), None)
        failed = [row for row in rows if row["status"] != "SUCCESS"]
        if successful and failed and str(successful["provider"]) != str(failed[0]["provider"]):
            legacy.append(f"{failed[0]['provider']} falhou; fallback para {successful['provider']}")
    return escape("; ".join(legacy)) if legacy else "NÃO OCORREU"

'''
text = regex_once(
    text,
    r"def _attempt_row\(row: sqlite3\.Row\) -> str:.*?\ndef _provider_label",
    report_helpers + "def _provider_label",
    "m18 report helpers",
)
write(path, text)


# ---------------------------------------------------------------------------
# SearchGEO page: promote operational AI cause near non-consolidated readiness.
# ---------------------------------------------------------------------------
path = "src/searchgeo/searchgeo_readiness_reporting.py"
text = read(path)
text = replace_once(
    text,
    "        apdex = _many(\n            connection,\n            \"SELECT * FROM synthetic_apdex_summaries WHERE audit_id=? ORDER BY url,device,summary_id\",\n            (audit_id,),\n        )\n        return {",
    "        apdex = _many(\n"
    "            connection,\n"
    "            \"SELECT * FROM synthetic_apdex_summaries WHERE audit_id=? ORDER BY url,device,summary_id\",\n"
    "            (audit_id,),\n"
    "        )\n"
    "        ai_session = _one(connection, \"SELECT * FROM ai_audit_sessions WHERE audit_id=?\", (audit_id,))\n"
    "        ai_attempts = _many(connection, \"SELECT * FROM ai_provider_attempts WHERE audit_id=? ORDER BY started_at,attempt_index,attempt_id\", (audit_id,))\n"
    "        return {",
    "searchgeo load ai",
)
text = replace_once(
    text,
    '            "apdex": apdex,\n        }',
    '            "apdex": apdex,\n            "ai_session": ai_session,\n            "ai_attempts": ai_attempts,\n        }',
    "searchgeo data ai",
)
text = replace_once(
    text,
    "    limitations_block = _audit_limitations_block(audit)\n    nav = report_navigation.render_report_navigation(report_dir, SEARCHGEO_FILE)",
    "    limitations_block = _audit_limitations_block(audit)\n"
    "    ai_operational_block = _ai_operational_diagnostic(data)\n"
    "    nav = report_navigation.render_report_navigation(report_dir, SEARCHGEO_FILE)",
    "searchgeo ai block variable",
)
text = replace_once(
    text,
    "{limitations_block}\n<section class='panel'><div class='kicker'>Indicadores proprietários</div>",
    "{limitations_block}\n{ai_operational_block}\n<section class='panel'><div class='kicker'>Indicadores proprietários</div>",
    "searchgeo ai block inject",
)
ai_diag = '''def _ai_operational_diagnostic(data: dict[str, Any]) -> str:
    attempts = [
        row for row in data.get("ai_attempts", [])
        if not str(row["semantic_contract_version"] or "").startswith("M20-")
    ]
    failures = [row for row in attempts if str(row["status"]) != "SUCCESS"]
    if not failures:
        return ""
    successes = [row for row in attempts if str(row["status"]) == "SUCCESS"]
    fallback_rows = [row for row in attempts if "fallback_from_provider" in row.keys() and row["fallback_from_provider"]]
    session = data.get("ai_session")
    initial = str(session["initial_provider"] or "—") if session is not None else str(failures[0]["provider"])
    effective = str(session["effective_provider"] or "—") if session is not None else (str(successes[-1]["provider"]) if successes else "—")
    detail_rows: list[str] = []
    for row in failures[:8]:
        error_class = str(row["error_class"] or row["status"])
        error_type = str(row["error_type"] or "—")
        error_code = str(row["error_code"] or "—")
        decision = str(row["decision"] if "decision" in row.keys() and row["decision"] else "STOP")
        detail_rows.append(
            "<li>" + escape(f"{row['provider']}/{row['model'] or '—'}: {error_class}; type={error_type}; code={error_code}; decisão={decision}") + "</li>"
        )
    if fallback_rows and successes:
        headline = "Fallback de IA utilizado por falha de integração"
        impact = (
            f"O provider que deveria atender primeiro era {initial}. Após erro operacional, "
            f"o SearchGEO utilizou {effective} como fallback e obteve resultado válido. "
            "O fallback é identificado na telemetria e não é atribuído ao website."
        )
        css = "notice"
    else:
        headline = "Análise semântica externa com erro operacional"
        impact = (
            f"O provider esperado era {initial}, mas não houve resultado semântico válido em todos os contextos. "
            "Regras dependentes da análise externa podem permanecer UNKNOWN e reduzir Coverage/Consolidation. "
            "Isto é limitação da integração de IA, não evidência de defeito no website."
        )
        css = "notice warn"
    return (
        f"<section class='{css}' data-ai-operational-diagnostic='true'>"
        f"<strong>{escape(headline)}</strong><p>{escape(impact)}</p>"
        f"<ul>{''.join(detail_rows)}</ul>"
        "<p>Consulte o bloco “Uso de IA — execução, erros, retry e fallback” para tokens, custo e sequência completa de tentativas.</p>"
        "</section>"
    )


'''
text = replace_once(
    text,
    "def _audit_limitations_block(audit: sqlite3.Row | None) -> str:\n",
    ai_diag + "def _audit_limitations_block(audit: sqlite3.Row | None) -> str:\n",
    "searchgeo diagnostic helper",
)
write(path, text)


# ---------------------------------------------------------------------------
# Console cost exposure: include bounded retry and AUTO global cap.
# ---------------------------------------------------------------------------
path = "src/searchgeo/console_cost.py"
text = read(path)
text = replace_once(
    text,
    "from searchgeo.cli import validate_target",
    "from searchgeo.ai_resilience import MAX_PROVIDER_ATTEMPTS_PER_CONTEXT, max_attempts_for_auto\nfrom searchgeo.cli import validate_target",
    "console resilience import",
)
text = replace_once(
    text,
    "    if provider_count:\n        min_ai = min_pages * devices\n        max_ai = max_pages * devices * provider_count\n        if state.content_remediation:\n            max_ai += max_pages * devices * provider_count",
    "    if provider_count:\n"
    "        min_ai = min_pages * devices\n"
    "        per_context_max = (\n"
    "            max_attempts_for_auto(provider_count)\n"
    "            if state.ai_provider == 'auto'\n"
    "            else MAX_PROVIDER_ATTEMPTS_PER_CONTEXT\n"
    "        )\n"
    "        max_ai = max_pages * devices * per_context_max\n"
    "        if state.content_remediation:\n"
    "            max_ai += max_pages * devices * per_context_max",
    "console retry exposure",
)
text = replace_once(
    text,
    "            f\"IA ativa: até {max_ai} tentativa(s) potenciais considerando M18, \"\n            \"cadeia de providers e M20 quando habilitado.\"",
    "            f\"IA ativa: até {max_ai} chamada(s) potenciais considerando M18, retry transitório limitado, \"\n"
    "            \"fallback AUTO e M20 quando habilitado. Cada provider/contexto tem no máximo 2 chamadas \"\n"
    "            \"(1 inicial + 1 retry); AUTO possui teto global de 4 chamadas por contexto.\"",
    "console reason retry",
)
write(path, text)


# ---------------------------------------------------------------------------
# Existing tests whose old contract intentionally forbade transient retry/fallback.
# ---------------------------------------------------------------------------
path = "tests/test_m18_multi_ai_provider.py"
text = read(path)
text = replace_once(
    text,
    "        self.assertEqual(calls, 1)\n        snapshot = provider.session_snapshot()\n        self.assertEqual(snapshot[\"strategy\"], \"SINGLE_PROVIDER\")\n        self.assertEqual(snapshot[\"provider_states\"][\"OPENAI\"], \"QUARANTINED_FOR_AUDIT\")\n        self.assertEqual(len(provider.attempt_history()), 1)",
    "        self.assertEqual(calls, 2)\n"
    "        snapshot = provider.session_snapshot()\n"
    "        self.assertEqual(snapshot[\"strategy\"], \"SINGLE_PROVIDER\")\n"
    "        self.assertEqual(snapshot[\"provider_states\"][\"OPENAI\"], \"QUARANTINED_FOR_AUDIT\")\n"
    "        self.assertEqual(len(provider.attempt_history()), 2)",
    "existing transient retry expectation",
)
old_lock = '''        self.assertEqual(router.analyze(_input(url, "SNP-A-D")).provider, "DEEPSEEK")
        failed_mobile = router.analyze(_input(url, "SNP-A-M"))
        self.assertEqual(failed_mobile.state, ProviderState.UNAVAILABLE)
        self.assertEqual(mimo_calls, 0)
        self.assertEqual(router.analyze(_input("https://example.com/b", "SNP-B-D")).provider, "MIMO")
        self.assertEqual(mimo_calls, 1)'''
new_lock = '''        self.assertEqual(router.analyze(_input(url, "SNP-A-D")).provider, "DEEPSEEK")
        recovered_mobile = router.analyze(_input(url, "SNP-A-M"))
        self.assertEqual(recovered_mobile.state, ProviderState.AVAILABLE)
        self.assertEqual(recovered_mobile.provider, "MIMO")
        self.assertEqual(mimo_calls, 1)
        attempts = router.consume_attempts()
        self.assertTrue(any(item.fallback_from_provider == "DEEPSEEK" for item in attempts))
        self.assertEqual(router.analyze(_input("https://example.com/b", "SNP-B-D")).provider, "MIMO")
        self.assertEqual(mimo_calls, 2)'''
text = replace_once(text, old_lock, new_lock, "existing url fallback expectation")
write(path, text)


# ---------------------------------------------------------------------------
# New regression suite.
# ---------------------------------------------------------------------------
new_test = ROOT / "tests/test_ai_retry_fallback_observability.py"
if not new_test.exists():
    new_test.write_text('''from __future__ import annotations

import io
import json
from email.message import Message
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from searchgeo.ai_resilience import MAX_AUTO_ATTEMPTS_PER_CONTEXT, retry_policy
from searchgeo.m18_ai import (
    DeepSeekProvider,
    MiMoProvider,
    OpenAIProvider,
    ProviderErrorClass,
    ProviderRoutingSession,
    ProviderState,
    SEMANTIC_RULE_IDS,
)
from searchgeo.m18_reporting import _attempt_row, _failover_summary
from searchgeo.semantic import SemanticEvidenceInput, SemanticInput


def semantic_input() -> SemanticInput:
    return SemanticInput(
        snapshot_id="SNP-R",
        page_url="https://example.com/",
        title="Example",
        main_content="Evidence",
        structured_data=None,
        primary_language="pt-BR",
        market="BR",
        evidence=(SemanticEvidenceInput("EVD-1", "TEXT_EXCERPT", "test", {"text": "Evidence"}),),
    )


def payload() -> dict[str, object]:
    return {
        "assessments": [
            {
                "rule_id": rule_id,
                "result": "UNKNOWN",
                "confidence": 0.0,
                "evidence_ids": [],
                "reasoning_summary": "fixture",
                "observed_value": {"summary": "", "details": []},
            }
            for rule_id in SEMANTIC_RULE_IDS
        ],
        "entities": [],
        "primary_intent": None,
        "secondary_intents": [],
    }


def success(*_):
    return {"output_text": json.dumps(payload())}


def http_error(status: int, error_type: str, code: str, retry_after: str | None = None) -> HTTPError:
    headers = Message()
    headers["x-request-id"] = "req-123"
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    body = io.BytesIO(json.dumps({"error": {"type": error_type, "code": code}}).encode())
    return HTTPError("https://provider.invalid", status, "error", headers, body)


class AiRetryFallbackTests(unittest.TestCase):
    def test_timeout_retries_once_then_succeeds(self) -> None:
        calls = 0
        def transport(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError()
            return success(*args)
        provider = OpenAIProvider(api_key="x", transport=transport)
        with patch("searchgeo.m18_ai.time.sleep", return_value=None):
            result = provider.analyze(semantic_input())
        self.assertEqual(result.state, ProviderState.AVAILABLE)
        self.assertEqual(calls, 2)
        attempts = provider.consume_attempts()
        self.assertEqual([item.decision for item in attempts], ["RETRY", "SUCCESS_AFTER_RETRY"])
        self.assertTrue(attempts[0].retry_eligible)

    def test_contract_error_is_never_retried(self) -> None:
        calls = 0
        def invalid(*_):
            nonlocal calls
            calls += 1
            return {"output_text": "{bad-json"}
        provider = OpenAIProvider(api_key="x", transport=invalid)
        result = provider.analyze(semantic_input())
        self.assertEqual(result.state, ProviderState.UNAVAILABLE)
        self.assertEqual(calls, 1)
        attempts = provider.consume_attempts()
        self.assertEqual(len(attempts), 1)
        self.assertFalse(attempts[0].retry_eligible)
        self.assertEqual(attempts[0].decision, "STOP")

    def test_retry_after_above_cap_stops_without_second_paid_call(self) -> None:
        calls = 0
        def limited(*_):
            nonlocal calls
            calls += 1
            raise http_error(429, "rate_limit", "rate_limit", "120")
        provider = OpenAIProvider(api_key="x", transport=limited)
        result = provider.analyze(semantic_input())
        self.assertEqual(result.diagnostic.error_class, ProviderErrorClass.RATE_LIMIT_ERROR)
        self.assertEqual(calls, 1)
        self.assertFalse(provider.consume_attempts()[0].retry_eligible)

    def test_auto_declares_fallback_source_reason_and_success(self) -> None:
        def primary(*_):
            raise http_error(401, "invalid_api_key", "invalid_api_key")
        router = ProviderRoutingSession((
            OpenAIProvider(api_key="x", transport=primary),
            DeepSeekProvider(api_key="x", transport=success),
            MiMoProvider(api_key="x", transport=success),
        ))
        result = router.analyze(semantic_input())
        self.assertEqual(result.provider, "DEEPSEEK")
        attempts = router.consume_attempts()
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0].decision, "FALLBACK")
        self.assertEqual(attempts[1].decision, "FALLBACK_SUCCESS")
        self.assertEqual(attempts[1].fallback_from_provider, "OPENAI")
        self.assertIn("AUTH_ERROR", attempts[1].fallback_reason or "")

    def test_auto_global_budget_prevents_loop(self) -> None:
        calls = 0
        def timeout(*_):
            nonlocal calls
            calls += 1
            raise TimeoutError()
        router = ProviderRoutingSession((
            OpenAIProvider(api_key="x", transport=timeout),
            DeepSeekProvider(api_key="x", transport=timeout),
            MiMoProvider(api_key="x", transport=timeout),
        ))
        with patch("searchgeo.m18_ai.time.sleep", return_value=None):
            result = router.analyze(semantic_input())
        self.assertEqual(result.state, ProviderState.UNAVAILABLE)
        self.assertEqual(calls, MAX_AUTO_ATTEMPTS_PER_CONTEXT)
        self.assertEqual(len(router.consume_attempts()), MAX_AUTO_ATTEMPTS_PER_CONTEXT)

    def test_report_row_exposes_diagnostic_and_fallback(self) -> None:
        row = {
            "url": "https://example.com/", "device": "MOBILE", "semantic_contract_version": "M18-SEMANTIC-22-v1",
            "attempt_index": 2, "provider": "DEEPSEEK", "model": "deepseek-v4-pro", "status": "SUCCESS",
            "error_class": None, "error_type": None, "http_status": None, "error_code": None, "request_id": None,
            "retry_eligible": 0, "decision": "FALLBACK_SUCCESS", "fallback_from_provider": "OPENAI",
            "fallback_reason": "AI_PROVIDER_UNAVAILABLE:AUTH_ERROR:HTTP_401", "input_tokens": 10, "output_tokens": 5,
            "estimated_cost": 0.001, "cost_currency": "USD", "duration_ms": 12,
        }
        html = _attempt_row(row)
        self.assertIn("FALLBACK_SUCCESS", html)
        self.assertIn("OPENAI", html)
        summary = _failover_summary([row])
        self.assertIn("deveria atender", summary)
        self.assertIn("AUTH_ERROR", summary)

    def test_policy_contract_and_auth_are_non_retryable(self) -> None:
        self.assertFalse(retry_policy("CONTRACT_ERROR").eligible)
        self.assertFalse(retry_policy("AUTH_ERROR").eligible)
        self.assertTrue(retry_policy("TIMEOUT_ERROR").eligible)


if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Normative documentation.
# ---------------------------------------------------------------------------
path = "docs/specification/18_MULTI_AI_PROVIDER_ROUTING.md"
text = read(path)
marker = "## Política de retry e fallback com controle de custo"
if marker not in text:
    text += '''\n\n## Política de retry e fallback com controle de custo\n\nO SearchGEO trata chamadas de IA como integrações potencialmente tarifadas. Retry não é genérico.\n\n- cada provider/contexto pode realizar no máximo **2 chamadas**: 1 inicial + 1 retry;\n- AUTO possui teto adicional de **4 chamadas totais por URL/device**, independentemente da quantidade de providers configurados;\n- retry é permitido somente para `NETWORK_ERROR`, `TIMEOUT_ERROR`, `SERVER_ERROR`, `RATE_LIMIT_ERROR` e `EMPTY_RESPONSE`;\n- `AUTH_ERROR`, `PERMISSION_ERROR`, `CREDIT_ERROR`, `QUOTA_ERROR`, `MODEL_ERROR`, `CONTRACT_ERROR`, `INVALID_RESPONSE` e erros desconhecidos não são repetidos automaticamente;\n- `Retry-After` só é obedecido quando o atraso calculado não excede 5 segundos; acima disso não há nova chamada automática;\n- após esgotar o retry de um provider, ele entra em quarentena para a auditoria;\n- em AUTO, erro de integração pode acionar fallback para o próximo provider saudável, inclusive quando havia preferência anterior para a URL;\n- um resultado válido encerra imediatamente a cadeia para aquele contexto; nenhum provider adicional é chamado;\n- a telemetria persiste cada tentativa, classe/tipo/código do erro, request id quando disponível, elegibilidade de retry, decisão (`RETRY`, `FALLBACK`, `STOP`, `SUCCESS_*`), origem do fallback, tokens e custo estimado quando mensurável.\n\nO relatório deve distinguir explicitamente **provider que deveria atender primeiro** de **provider efetivamente utilizado**. Quando houver fallback, deve declarar a causa que inviabilizou o provider anterior. Falha de integração não pode ser convertida em finding do website.\n'''
write(path, text)

print("AI retry/fallback observability patch applied")
