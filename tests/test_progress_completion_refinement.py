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


def test_improvement_report_refresh_does_not_reenter_external_finalizer_chain() -> None:
    code = r'''
from types import SimpleNamespace
from rasai import improvement_intelligence_console as improvement_console
from rasai import report_completion
from rasai import progress_completion_refinement as refinement

external_calls = []
progress_events = []

def fake_finalize(*, audit_id, workspace, **kwargs):
    external_calls.append((audit_id, workspace, kwargs))
    return "EXTERNAL_CHAIN"

def fake_execute(*args, **kwargs):
    return SimpleNamespace(status="COMPLETE")

report_completion.finalize_audit_report_site = fake_finalize
improvement_console.execute_improvement_intelligence = fake_execute
refinement.install()
refinement._refresh_reports_local_only = lambda **kwargs: ()
report_completion.inspect_audit_report_site = lambda **kwargs: SimpleNamespace(
    expected_pages=("index.html",),
    generated_pages=("index.html",),
    missing_pages=(),
    renderer_errors=(),
)

progress = lambda stage, percent, detail: progress_events.append((stage, percent, detail))
improvement_console.execute_improvement_intelligence(progress=progress)
completion = report_completion.finalize_audit_report_site(audit_id="AUD-1", workspace=SimpleNamespace())
assert external_calls == []
assert completion.complete is True
assert [item[1] for item in progress_events] == [98.0, 100.0]
assert all("API" in item[2] or "relatórios" in item[2] for item in progress_events)

# A normal finalization still traverses the original collector/finalizer chain.
report_completion.finalize_audit_report_site(audit_id="AUD-2", workspace=SimpleNamespace())
assert len(external_calls) == 1
assert external_calls[0][0] == "AUD-2"
print("OK")
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
