"""Ensure semantic profile injection reaches provider classes with their own request builder."""
from __future__ import annotations

from typing import Any

from rasai.ai_task_profile_runtime import _inject_payload

_INSTALLED = False


def _patch_owned_request_builder(cls: Any) -> None:
    """Wrap only a request builder owned by ``cls``; inherited markers must not suppress it."""
    if cls.__dict__.get("_rasai_task_profiles_semantic_compat", False):
        return
    original = cls.__dict__.get("_request_payload")
    if not callable(original):
        return

    def request_payload(self: Any, *args: Any, **kwargs: Any) -> Any:
        return _inject_payload(original(self, *args, **kwargs), "SEMANTIC_READINESS")

    cls._request_payload = request_payload
    cls._rasai_task_profiles_semantic_compat = True


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import m18_ai, openai_provider

    # Both classes implement their own semantic request builder. A marker inherited
    # from a parent class must never make either implementation skip specialization.
    _patch_owned_request_builder(openai_provider.OpenAIProvider)
    _patch_owned_request_builder(m18_ai.ResponsesSemanticProvider)
    _INSTALLED = True
