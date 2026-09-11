from __future__ import annotations

from rasai.provider_registry import provider_registrations
from rasai.web.ui_runtime import render_pilot_ui


def test_trusted_header_shell_keeps_local_development_helper() -> None:
    html = render_pilot_ui("trusted-header")
    assert "rasai-dev-user" in html
    assert "Conectar localmente" in html


def test_pilot_ai_provider_selector_uses_canonical_registry() -> None:
    html = render_pilot_ui("trusted-header")
    assert '<option value="none">Sem IA</option>' in html
    assert '<option value="auto">Auto</option>' in html
    for registration in provider_registrations():
        assert f'<option value="{registration.id}">{registration.display_name}</option>' in html
    assert '<option value="github-copilot">' not in html
    assert '<option value="grok">' not in html
    assert '<option value="claude">' not in html


def test_oidc_shell_removes_local_identity_helper_and_restarts_login() -> None:
    html = render_pilot_ui("oidc")
    assert "Conectar localmente" not in html
    assert "location.assign('/auth/login')" in html
    assert "sessionStorage.removeItem('rasai-dev-user')" in html
