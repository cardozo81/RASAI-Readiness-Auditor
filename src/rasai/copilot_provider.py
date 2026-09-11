"""GitHub Copilot SDK adapter for evidence-bound RASAi semantic analysis.

The adapter is intentionally explicit-only.  It requires a user-scoped GitHub token in
``COPILOT_GITHUB_TOKEN`` and disables fallback to locally logged-in credentials so an
audit cannot silently consume a different Copilot subscription.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import time
from typing import Any, Mapping

from rasai.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
    ProviderPolicy,
    RuntimeProviderState,
    SemanticProviderResult,
)
from rasai.openai_provider import SEMANTIC_RULE_CRITERIA
from rasai.provider_extensions import IsolatedStructuredSemanticProvider
from rasai.semantic import SEMANTIC_RULE_IDS, SemanticInput, SemanticProviderError

COPILOT_PROVIDER_NAME = "COPILOT"
COPILOT_KEY_ENV = "COPILOT_GITHUB_TOKEN"
COPILOT_MODEL_ENV = "RASAI_COPILOT_MODEL"
COPILOT_DEFAULT_MODEL = "auto"
COPILOT_SUPPORTED_MODELS = ("auto",)
COPILOT_DOCS_URL = "https://docs.github.com/en/copilot/how-tos/copilot-sdk/auth/authenticate"
COPILOT_TOKEN_URL = "https://github.com/settings/personal-access-tokens/new"
COPILOT_SETTINGS_URL = "https://github.com/settings/copilot"


def _semantic_prompt(semantic_input: SemanticInput) -> str:
    criteria = "\n".join(
        f"- {rule_id}: {SEMANTIC_RULE_CRITERIA[rule_id]}" for rule_id in SEMANTIC_RULE_IDS
    )
    return (
        "You are the semantic analysis provider for RASAi Search & AI Readiness Auditor. "
        "Evaluate only the supplied evidence. Return one JSON object only, with exactly "
        "the RASAi semantic response contract. Never call tools, browse, read files, run "
        "commands, or invent evidence IDs. Use UNKNOWN when evidence is insufficient. "
        "The assessments array must contain exactly one assessment for every rule below.\n\n"
        f"Semantic rules:\n{criteria}\n\n"
        "Required JSON top-level fields: assessments, entities, primary_intent, "
        "secondary_intents. Each assessment requires rule_id, result, confidence, "
        "evidence_ids, reasoning_summary and observed_value.\n\n"
        "JSON page evidence:\n"
        + json.dumps(semantic_input.provider_payload(), ensure_ascii=False)
    )


def _run_async(coro):
    """Run the SDK coroutine from the synchronous provider contract.

    RASAi's audit pipeline is synchronous today.  Fail closed when called from a thread
    that already owns an event loop rather than creating an unsafe nested loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise SemanticProviderError(
        "GitHub Copilot provider requires the synchronous RASAi runtime; an event loop is already running"
    )


class GitHubCopilotProvider(IsolatedStructuredSemanticProvider):
    """Semantic provider backed by the official GitHub Copilot SDK."""

    name = COPILOT_PROVIDER_NAME
    endpoint = "copilot://sdk"
    reasoning_profile = "PROVIDER_DEFAULT"
    capabilities = IsolatedStructuredSemanticProvider.capabilities + (
        "GITHUB_COPILOT_SDK",
        "USER_SUBSCRIPTION",
        "TOOLS_DISABLED",
    )

    def __init__(
        self,
        *,
        model: str = COPILOT_DEFAULT_MODEL,
        api_key: str | None,
        timeout: float = 180.0,
        transport=None,
    ) -> None:
        if model not in COPILOT_SUPPORTED_MODELS:
            raise ValueError(
                f"unsupported RASAi model for COPILOT: {model}; allowed: "
                + ", ".join(COPILOT_SUPPORTED_MODELS)
            )
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        # Initialize the same state used by IsolatedStructuredSemanticProvider without
        # relying on its extension-policy registry. Copilot is a separate SDK adapter.
        self.model = model
        self.api_key = api_key
        self.endpoint = self.endpoint
        self.timeout = float(timeout)
        self.configuration_version = "1"
        self.prompt_id = "rasai-semantic-copilot-v1"
        self.prompt_version = "1"
        self._transport = transport or self._copilot_transport
        self.policy = ProviderPolicy(
            106,
            self.name,
            self.model,
            "PROVIDER_DEFAULT",
            "PROVISIONAL-A-",
            "PROVISIONAL",
            "explicit-only GitHub Copilot SDK qualification",
        )
        self._last_attempt: ProviderAttempt | None = None
        self._last_attempts: tuple[ProviderAttempt, ...] = ()
        self._history: list[ProviderAttempt] = []
        self._runtime_state = RuntimeProviderState.ACTIVE
        self._successful_urls: set[str] = set()

    def _headers(self) -> dict[str, str]:
        # The token is supplied directly to the SDK, never serialized into the exchange
        # body/header capture used by HTTP providers.
        return {"Content-Type": "application/json"}

    def _request_payload(self, semantic_input: SemanticInput) -> dict[str, Any]:
        return {"model": self.model, "prompt": _semantic_prompt(semantic_input)}

    def _extract_payload(self, raw: Mapping[str, Any]) -> Any:
        text = raw.get("output_text")
        if not isinstance(text, str) or not text.strip():
            raise SemanticProviderError("GitHub Copilot response contained no textual output")
        candidate = text.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            candidate = "\n".join(lines).strip()
        return json.loads(candidate)

    def _copilot_transport(
        self,
        _url: str,
        _headers: dict[str, str],
        body: bytes,
        timeout: float,
    ) -> dict[str, Any]:
        payload = json.loads(body.decode("utf-8"))
        prompt = str(payload.get("prompt") or "")
        model = str(payload.get("model") or COPILOT_DEFAULT_MODEL)
        token = (self.api_key or "").strip()
        if not token:
            raise SemanticProviderError(f"{COPILOT_KEY_ENV} is required")

        async def invoke() -> dict[str, Any]:
            try:
                from copilot import CopilotClient, CopilotClientOptions
                from copilot.rpc import PermissionDecisionReject
            except ImportError as exc:
                raise SemanticProviderError(
                    "GitHub Copilot SDK is not installed; install RASAi with the copilot extra"
                ) from exc

            def reject_permission(_request, _invocation):
                return PermissionDecisionReject(
                    feedback="RASAi semantic analysis does not permit tool execution"
                )

            options = CopilotClientOptions(
                github_token=token,
                use_logged_in_user=False,
            )
            client = CopilotClient(options)
            await client.start()
            session = None
            try:
                session = await client.create_session(
                    model=model,
                    available_tools=[],
                    on_permission_request=reject_permission,
                )
                response = await session.send_and_wait(prompt, timeout=float(timeout))
                if response is None:
                    raise SemanticProviderError("GitHub Copilot returned no assistant message")
                data = getattr(response, "data", None)
                content = getattr(data, "content", None)
                if not isinstance(content, str) or not content.strip():
                    raise SemanticProviderError("GitHub Copilot returned an empty assistant message")
                return {"output_text": content}
            finally:
                if session is not None:
                    disconnect = getattr(session, "disconnect", None)
                    if callable(disconnect):
                        await disconnect()
                await client.stop()

        return _run_async(invoke())


def build_copilot_provider(
    *,
    model_override: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float = 180.0,
) -> GitHubCopilotProvider:
    import os

    environment = os.environ if env is None else env
    model = (model_override or environment.get(COPILOT_MODEL_ENV) or COPILOT_DEFAULT_MODEL).strip()
    key = (environment.get(COPILOT_KEY_ENV) or "").strip() or None
    return GitHubCopilotProvider(model=model, api_key=key, timeout=timeout)
