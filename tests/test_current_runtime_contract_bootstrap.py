"""Collect-time bootstrap for the current unpublished RASAi runtime contract.

Public entrypoints install the cross-provider AI policy before exposing runtime surfaces.
The test suite exercises that same composed product contract so low-level modules are not
validated in an intermediate, uncomposed import state that users cannot execute.
"""
from rasai.ai_efficiency_policy import install as install_ai_efficiency_policy


install_ai_efficiency_policy()


def test_current_runtime_contract_is_installed() -> None:
    from rasai.ai_efficiency_policy import strategy_summary

    assert strategy_summary()["version"] == "AI-CALL-POLICY-002"
