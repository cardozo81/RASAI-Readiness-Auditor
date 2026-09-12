from __future__ import annotations

from rasai.standards_gsc_contract import install as install_gsc_contract
from rasai.web.ui_runtime import render_pilot_ui


def test_pilot_uses_auto_web_performance_by_default() -> None:
    html = render_pilot_ui("trusted-header")
    assert '<option value="auto">Auto por serviços/requisitos</option>' in html
    assert "delete config.web_performance" in html
    assert "if(performanceMode==='auto'){delete auditConfig.web_performance}" in html
    assert "web_performance:$('audit-performance').value==='true'" not in html


def test_pilot_exposes_standards_capability_catalog_without_secrets() -> None:
    html = render_pilot_ui("trusted-header")
    assert "/api/v1/standards/services" in html
    assert "Serviços de métricas e padrões" in html
    assert "missing_configuration" in html
    assert "Valores secretos nunca são exibidos" in html


def test_audit_job_defaults_preserve_auto_for_credential_driven_services() -> None:
    install_gsc_contract()
    from rasai import audit_execution_contract as contract

    defaults = contract.audit_job_defaults()
    assert defaults["pagespeed_enabled"] is None
    assert defaults["crux_enabled"] is None
    assert defaults["gsc_enabled"] is None

    normalized = contract.normalize_audit_job_payload({})
    assert normalized["pagespeed_enabled"] is None
    assert normalized["crux_enabled"] is None
    assert normalized["gsc_enabled"] is None
