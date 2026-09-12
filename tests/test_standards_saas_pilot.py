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
    assert "valores secretos nunca são exibidos" in html.casefold()
    assert "s.job_field" in html
    assert "setServiceMode" in html
    assert "Controle do job" in html
    assert "Auto" in html and "Padrão" in html and "Desligado" in html
    assert "Workers podem possuir credenciais próprias" in html


def test_pilot_default_json_does_not_materialize_service_toggles() -> None:
    html = render_pilot_ui("trusted-header")
    assert "for(const s of state.standardServices||[]){if(s.job_field)delete config[s.job_field]}" in html
    assert "if(mode==='default')delete cfg[field]" in html


def test_pilot_exposes_guided_nonsecret_gsc_and_standards_fields() -> None:
    html = render_pilot_ui("trusted-header")

    assert "Configuração guiada de métricas e integrações" in html
    assert 'data-config-field="standards_max_urls"' in html
    assert 'data-config-field="standards_timeout_seconds"' in html
    assert 'data-config-field="gsc_site_url"' in html
    assert 'data-config-field="gsc_search_analytics_days"' in html
    assert 'data-config-field="gsc_search_max_rows"' in html
    assert 'data-config-field="gsc_final_data_lag_days"' in html
    assert "Configuração avançada do AuditJob (JSON)" in html
    assert "syncGuidedFromJson" in html
    assert "setGuidedField" in html
    assert "bindGuidedConfig" in html


def test_pilot_blocks_explicit_gsc_on_without_property_and_uses_existing_message_surface() -> None:
    html = render_pilot_ui("trusted-header")

    assert "field==='gsc_enabled'&&mode==='true'" in html
    assert "informe a property na configuração guiada" in html
    assert "message('Para ligar GSC explicitamente" in html
    assert "toast(" not in html


def test_pilot_keeps_secrets_out_of_guided_inputs() -> None:
    html = render_pilot_ui("trusted-header")

    assert "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN" not in html
    assert "RASAI_PAGESPEED_API_KEY" not in html
    assert "RASAI_CRUX_API_KEY" not in html
    assert "OAuth token fica somente no worker/secret store" in html


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
