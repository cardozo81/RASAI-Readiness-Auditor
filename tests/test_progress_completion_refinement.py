from __future__ import annotations

import subprocess
import sys


def test_improvement_intelligence_uses_workload_aware_progress() -> None:
    code = r'''
from types import SimpleNamespace
from rasai import console_progress_model as model
from rasai.progress_completion_refinement import install
install()
state = SimpleNamespace(
    improvement_enabled=True,
    improvement_reasoning="HIGH",
    device="mobile",
    ai_provider="none",
    content_remediation=False,
    web_performance=False,
    apdex_experience=False,
    synthetic_apdex=False,
    search_queries=(),
)
weights = model.workload_weights(state)
assert weights["IMPROVEMENT_INTELLIGENCE"] > 0
bounds = model.phase_bounds(state)
assert "IMPROVEMENT_INTELLIGENCE" in bounds
start, end = bounds["IMPROVEMENT_INTELLIGENCE"]
assert 0 <= start < end <= 99
print("OK")
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_improvement_progress_labels_only_provider_transport_as_api() -> None:
    code = r'''
from types import SimpleNamespace
from rasai import console_runtime
from rasai.progress_completion_refinement import install
install()
state = SimpleNamespace(status="IMPROVEMENT_INTELLIGENCE", operation="API:OPENAI/model")
console_runtime.set_runtime_progress(
    state,
    "Análise profunda e melhorias",
    12.0,
    detail="EVIDENCE: carregando evidências persistidas",
    exact=True,
)
assert state.operation == "LOCAL:IMPROVEMENT_EVIDENCE"
state.operation = "API:OPENAI/model"
console_runtime.set_runtime_progress(
    state,
    "Análise profunda e melhorias",
    80.0,
    detail="AI_ANALYSIS: consultando provider",
    exact=True,
)
assert state.operation == "API:OPENAI/model"
state.operation = "API:OPENAI/model"
console_runtime.set_runtime_progress(
    state,
    "Análise profunda e melhorias",
    98.0,
    detail="REPORT_REFRESH: atualizando HTML local",
    exact=True,
)
assert state.operation == "LOCAL:IMPROVEMENT_REPORT_REFRESH"
print("OK")
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
