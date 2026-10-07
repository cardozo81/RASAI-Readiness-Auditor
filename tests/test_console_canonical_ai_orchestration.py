from __future__ import annotations

import subprocess
import sys


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )


def test_console_environment_exposes_no_feature_local_ai_provider_controls() -> None:
    code = r'''
from rasai.ai_efficiency_policy import install as install_ai
from rasai.runtime_completion_extensions import install_runtime_completion_extensions
from rasai import console_environment

install_ai()
install_runtime_completion_extensions()

obsolete = {
    "RASAI_SEARCH_AI_PROVIDER",
    "RASAI_IMPROVEMENT_AI_PROVIDER",
    "RASAI_IMPROVEMENT_AI_MODEL",
    "RASAI_IMPROVEMENT_AI_REASONING",
}
assert obsolete.isdisjoint(console_environment.ENV_NAMES), obsolete.intersection(console_environment.ENV_NAMES)
assert obsolete.isdisjoint({item.name for item in console_environment.SPECS})
required = {
    "RASAI_IMPROVEMENT_INTELLIGENCE",
    "RASAI_IMPROVEMENT_DOMAINS",
    "RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS",
    "RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS",
}
assert required.issubset(set(console_environment.ENV_NAMES))
print("OK")
'''
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_item_13_persists_only_feature_controls_and_uses_primary_ai() -> None:
    code = r'''
import os
from rasai.ai_efficiency_policy import install as install_ai
from rasai import interactive_console
from rasai.improvement_intelligence_console import install as install_improvement
from rasai import console_settings

os.environ["OPENAI_API_KEY"] = "sk-test"
install_ai()
install_improvement(interactive_console)

state = interactive_console.State()
state.input_mode = "url"
state.target = "https://example.test/"
state.ai_provider = "openai"
state.ai_model = "gpt-5.6-luna"
state.ai_reasoning = "NONE"
state.improvement_enabled = True

values = console_settings._state_values(state)["improvement_intelligence"]
assert values["enabled"] == "true"
assert "provider" not in values
assert "model" not in values
assert "reasoning_effort" not in values

from rasai import improvement_intelligence_console as deep
config = deep._config_from_state(state)
assert config.provider == "openai"
assert config.model == "gpt-5.6-luna"
ready, reason = deep._single_url_ready(state)
assert ready, reason
assert "IA principal" in reason

state.ai_provider = "auto"
state.ai_model = None
state.ai_reasoning = None
config = deep._config_from_state(state)
assert config.provider == "auto"
ready, reason = deep._single_url_ready(state)
assert ready, reason
print("OK")
'''
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_deep_analysis_profile_keeps_deterministic_execution_ready_when_primary_ai_is_unavailable() -> None:
    code = r'''
import os
from types import SimpleNamespace
from rasai.ai_efficiency_policy import install as install_ai
from rasai.console_execution_profile_readiness import install as install_readiness, profile_status
from rasai import console_execution_profiles as profiles

os.environ["OPENAI_API_KEY"] = "sk-test"
install_ai()
install_readiness()

state = SimpleNamespace(
    input_mode="url",
    target="https://example.test/",
    runtime_blocks={},
    ai_provider="openai",
    ai_model="gpt-5.6-luna",
    ai_reasoning="NONE",
    content_remediation=False,
    technical_remediation=False,
    web_performance=False,
    lighthouse_categories="",
    synthetic_apdex=False,
    apdex_experience=False,
    search_queries=(),
    improvement_enabled=True,
    improvement_domains=("CONTENT",),
    improvement_max_recommendations=10,
    improvement_timeout=60.0,
    error="",
    operation="",
)

ready, blockers, _ = profile_status(state, "deep-analysis")
assert ready, blockers

session = profiles.set_profile(
    state,
    profile_id="deep-analysis",
    ai_mode=profiles.AI_OFF,
)
assert session.ai_mode == profiles.AI_IF_AVAILABLE
with profiles.effective_profile(state, session):
    assert state.ai_provider == "openai"

state.ai_provider = "none"
session.manual_overrides.add("ai")
ready, blockers, advisories = profiles.dependency_status(state, session)
assert ready, blockers
assert not blockers
assert any("fechamento por IA" in item for item in advisories), advisories
print("OK")
'''
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_improvement_environment_override_is_canonical_for_snapshot_and_runtime() -> None:
    code = r'''
import os
from rasai.ai_efficiency_policy import install as install_ai
from rasai.runtime_completion_extensions import install_runtime_completion_extensions
from rasai import interactive_console
from rasai.improvement_intelligence_console import install as install_improvement
from rasai import console_settings
from rasai.audit_configuration_reuse_console import _export_settings

install_ai()
install_runtime_completion_extensions()
install_improvement(interactive_console)

state = interactive_console.State()
state.input_mode = "url"
state.target = "https://example.test/"
state.ai_provider = "auto"
state.ai_model = None
state.ai_reasoning = None
state.improvement_enabled = True
state.improvement_domains = (
    "TECHNICAL_HTML",
    "SEMANTICS_STRUCTURE",
    "CONTENT",
)
state.improvement_max_recommendations = 30
state.improvement_timeout = 240.0

os.environ["RASAI_IMPROVEMENT_INTELLIGENCE"] = "true"
os.environ["RASAI_IMPROVEMENT_DOMAINS"] = "CONTENT,PERFORMANCE"
os.environ["RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS"] = "50"
os.environ["RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS"] = "333"

from rasai import improvement_intelligence_console as deep
config = deep._config_from_state(state)
assert config.enabled is True
assert config.domains == ("CONTENT", "PERFORMANCE")
assert config.max_recommendations == 50
assert config.timeout_seconds == 333.0
assert config.provider == "auto"

values = console_settings._state_values(state)["improvement_intelligence"]
assert values == {
    "enabled": "true",
    "domains": "CONTENT,PERFORMANCE",
    "max_recommendations": "50",
    "timeout_seconds": "333",
}

snapshot = _export_settings(state, ("https://example.test/",))
assert snapshot["settings"]["environment"]["RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS"] == "50"
assert snapshot["settings"]["improvement_intelligence"]["max_recommendations"] == "50"
assert snapshot["settings"]["environment"]["RASAI_IMPROVEMENT_DOMAINS"] == "CONTENT,PERFORMANCE"
assert snapshot["settings"]["improvement_intelligence"]["domains"] == "CONTENT,PERFORMANCE"
assert snapshot["settings"]["environment"]["RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS"] == "333"
assert snapshot["settings"]["improvement_intelligence"]["timeout_seconds"] == "333"

os.environ.pop("RASAI_IMPROVEMENT_DOMAINS", None)
os.environ.pop("RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS", None)
os.environ.pop("RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS", None)
fallback = deep._config_from_state(state)
assert fallback.domains == state.improvement_domains
assert fallback.max_recommendations == 30
assert fallback.timeout_seconds == 240.0
print("OK")
'''
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_improvement_invalid_environment_limit_remains_rejected() -> None:
    code = r'''
import os
from rasai.ai_efficiency_policy import install as install_ai
from rasai import interactive_console
from rasai.improvement_intelligence_console import install as install_improvement

install_ai()
install_improvement(interactive_console)
state = interactive_console.State()
state.ai_provider = "auto"
state.improvement_enabled = True
state.improvement_max_recommendations = 30

os.environ["RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS"] = "101"
from rasai import improvement_intelligence_console as deep
try:
    deep._config_from_state(state)
except ValueError as exc:
    assert "entre 1 e 100" in str(exc)
else:
    raise AssertionError("invalid explicit max_recommendations was accepted")
print("OK")
'''
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
