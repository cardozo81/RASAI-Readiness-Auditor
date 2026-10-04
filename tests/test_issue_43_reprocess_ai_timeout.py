from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from rasai.persistence import AuditWorkspace
from rasai.reprocess_ai import build_reprocess_provider
from rasai.reprocess_policy import reprocess_policy


AUDIT_ID = "AUD-ISSUE-43"


def _workspace(tmp_path: Path) -> AuditWorkspace:
    return AuditWorkspace.create(tmp_path, AUDIT_ID)


def test_reprocess_provider_applies_execution_ai_timeout(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    environment = {
        "OPENAI_API_KEY": "test-key",
        "RASAI_AI_TIMEOUT_SECONDS": "180",
    }
    with patch.dict(os.environ, environment, clear=True):
        with reprocess_policy(
            use_ai=True,
            ai_provider="openai",
            ai_timeout_seconds=181,
            ai_max_cycles=2,
            ai_cycle_delay_seconds=0,
        ):
            provider = build_reprocess_provider(workspace, AUDIT_ID)

    assert provider.name == "OPENAI"
    assert provider.timeout == 181.0
    assert provider._rasai_execution_policy.max_cycles == 2
    assert provider._rasai_execution_policy.cycle_delay_seconds == 0


def test_reprocess_auto_provider_applies_timeout_to_every_candidate(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    environment = {
        "OPENAI_API_KEY": "openai-key",
        "DEEPSEEK_API_KEY": "deepseek-key",
        "GEMINI_API_KEY": "gemini-key",
        "RASAI_AI_TIMEOUT_SECONDS": "195",
    }
    with patch.dict(os.environ, environment, clear=True):
        with reprocess_policy(
            use_ai=True,
            ai_provider="auto",
            ai_timeout_seconds=196,
            ai_max_cycles=4,
            ai_cycle_delay_seconds=10,
        ):
            router = build_reprocess_provider(workspace, AUDIT_ID)

    assert len(router.providers) >= 2
    assert all(item.timeout == 196.0 for item in router.providers)
    assert router._rasai_execution_policy.max_cycles == 4
    assert router._rasai_execution_policy.cycle_delay_seconds == 10


def test_reprocess_without_override_restores_original_aud_ai_cadence(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    current_environment = {
        "OPENAI_API_KEY": "test-key",
        "RASAI_AI_TIMEOUT_SECONDS": "30",
        "RASAI_AI_MAX_CYCLES": "1",
        "RASAI_AI_CYCLE_DELAY_SECONDS": "0",
    }
    saved = {
        "RASAI_AI_TIMEOUT_SECONDS": "210",
        "RASAI_AI_MAX_CYCLES": "4",
        "RASAI_AI_CYCLE_DELAY_SECONDS": "12",
    }
    with patch.dict(os.environ, current_environment, clear=True):
        with patch(
            "rasai.reprocess_ai._contract_configuration",
            return_value={"semantic_provider": "OPENAI"},
        ), patch(
            "rasai.reprocess_ai._saved_ai_policy_environment",
            return_value=saved,
        ):
            provider = build_reprocess_provider(workspace, AUDIT_ID)

    assert provider.name == "OPENAI"
    assert provider.timeout == 210.0
    assert provider._rasai_execution_policy.max_cycles == 4
    assert provider._rasai_execution_policy.cycle_delay_seconds == 12
