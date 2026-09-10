from __future__ import annotations

from rasai.web.ui_runtime import render_pilot_ui


def test_trusted_header_shell_keeps_local_development_helper() -> None:
    html = render_pilot_ui("trusted-header")
    assert "rasai-dev-user" in html
    assert "Conectar localmente" in html


def test_oidc_shell_removes_local_identity_helper_and_restarts_login() -> None:
    html = render_pilot_ui("oidc")
    assert "Conectar localmente" not in html
    assert "location.assign('/auth/login')" in html
    assert "sessionStorage.removeItem('rasai-dev-user')" in html
