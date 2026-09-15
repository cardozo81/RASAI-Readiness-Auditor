from __future__ import annotations

from rasai.ai_task_profile_semantic_compat import _patch_owned_request_builder


def test_owned_request_builder_is_patched_even_when_parent_has_marker() -> None:
    class Parent:
        _rasai_task_profiles_request_payload = True

        def _request_payload(self, value: str):
            return {"instructions": "parent " + value}

    class Child(Parent):
        def _request_payload(self, value: str):
            return {"instructions": "child " + value}

    _patch_owned_request_builder(Child)
    payload = Child()._request_payload("request")

    assert payload["instructions"].startswith(
        "Task specialization profile: SEMANTIC_READINESS (version 1.0)."
    )
    assert payload["instructions"].endswith("child request")
