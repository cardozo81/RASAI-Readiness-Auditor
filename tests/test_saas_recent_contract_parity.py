from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from rasai import audit_execution_contract as contract
from rasai.web import saas_management_routes
from rasai.web.pilot_app import create_app


ROOT = Path(__file__).resolve().parents[1]


def test_direct_asgi_composition_exposes_improvement_intelligence_options() -> None:
    # ``rasai.web.pilot_app:app`` may be imported directly by an ASGI server, bypassing
    # the top-level ``rasai api`` command router. Its composition root must still install
    # every durable, secret-free AuditJob extension.
    create_app()

    defaults = contract.audit_job_defaults()
    option_names = {item.name for item in saas_management_routes.audit_job_options()}

    expected = {
        "improvement_intelligence",
        "improvement_ai_provider",
        "improvement_ai_model",
        "improvement_ai_reasoning",
        "improvement_domains",
        "improvement_max_recommendations",
        "improvement_ai_timeout_seconds",
        "ai_analysis_language",
    }
    assert expected <= set(defaults)
    assert expected <= option_names


def test_direct_worker_cli_installs_improvement_contract_before_context_wrapper() -> None:
    # Source-level ordering is intentional: standards/GSC establish their extension,
    # Improvement Intelligence composes on top, then capture-context/profile wrappers
    # bind to the final normalized payload contract.
    source = (ROOT / "src/rasai/worker_cli.py").read_text(encoding="utf-8")

    standards = source.index("install_standards_saas_runtime()")
    improvement = source.index("install_improvement_intelligence_saas()")
    context = source.index("install_saas_context_integration()")
    assert standards < improvement < context
