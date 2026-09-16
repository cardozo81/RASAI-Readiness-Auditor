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


def test_local_refresh_reapplies_public_quality_final_presentation_and_catalog_projection() -> None:
    code = r'''
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from rasai import catalog_report_site
from rasai import improvement_intelligence
from rasai import progress_completion_refinement as refinement
from rasai import report_ai_cost_attribution
from rasai import report_manifest
from rasai import report_navigation
from rasai import report_presentation_finalizer
from rasai import report_quality_reconciliation
from rasai import report_scale_ux

calls = []
def record(name):
    def fn(*args, **kwargs):
        calls.append(name)
        return None
    return fn

improvement_intelligence.write_improvement_report = record("improvement")
report_ai_cost_attribution.enrich_ai_cost_attribution = record("cost")
report_navigation.normalize_report_navigation = record("navigation")
report_scale_ux.enhance_report_directory = record("ux")
report_quality_reconciliation.reconcile_public_report_quality = record("quality")
report_presentation_finalizer.finalize_report_presentation = record("finalizer")
report_manifest.write_report_manifest = record("manifest")
catalog_report_site.materialize_catalog_report_site = record("catalog")

with TemporaryDirectory() as directory:
    workspace = SimpleNamespace(root=Path(directory), database=Path(directory) / "audit.db")
    errors = refinement._refresh_reports_local_only(audit_id="AUD-LOCAL", workspace=workspace)

assert errors == ()
assert calls == ["improvement", "cost", "navigation", "ux", "quality", "finalizer", "manifest", "catalog"]
print("OK")
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
