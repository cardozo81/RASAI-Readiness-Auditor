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
        ):
            provider = build_reprocess_provider(workspace, AUDIT_ID)

    assert provider.name == "OPENAI"
    assert provider.timeout == 180.0


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
        ):
            router = build_reprocess_provider(workspace, AUDIT_ID)

    assert len(router.providers) >= 2
    assert all(item.timeout == 195.0 for item in router.providers)
