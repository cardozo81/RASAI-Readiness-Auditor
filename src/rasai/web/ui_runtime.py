"""Runtime adaptation of the zero-build pilot shell for the selected auth mode."""
from __future__ import annotations

from html import escape
import re

from rasai.provider_registry import provider_registrations

from .ui import PILOT_UI_HTML


def _provider_options_html() -> str:
    """Project the canonical provider registry into the pilot audit selector."""

    choices = [("none", "Sem IA"), ("auto", "Auto")]
    choices.extend((registration.id, registration.display_name) for registration in provider_registrations())
    return "".join(
        f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'
        for value, label in choices
    )


def _align_provider_selector(html: str) -> str:
    """Remove the static provider-list drift from the zero-build base asset."""

    return re.sub(
        r'<select id="audit-ai">.*?</select>',
        f'<select id="audit-ai">{_provider_options_html()}</select>',
        html,
        count=1,
        flags=re.DOTALL,
    )


def render_pilot_ui(auth_mode: str) -> str:
    """Return the pilot shell without exposing trusted-header UX in OIDC mode.

    The base asset remains static/zero-build. Provider choices are projected from the
    canonical registry at render time so the Web UI cannot drift from the execution
    contract. In OIDC mode a stale local-development identity is cleared and an expired
    browser session restarts the OIDC login flow instead of displaying the ``USR-*``
    trusted-header helper.
    """

    html = _align_provider_selector(PILOT_UI_HTML)
    if auth_mode != "oidc":
        return html
    html = html.replace(
        "const state=",
        "sessionStorage.removeItem('rasai-dev-user');\nconst state=",
        1,
    )
    return re.sub(
        r"function renderDevLogin\(err\)\{.*?\}\nasync function chooseOrganization",
        "function renderDevLogin(err){sessionStorage.removeItem('rasai-dev-user');location.assign('/auth/login')}\nasync function chooseOrganization",
        html,
        count=1,
        flags=re.DOTALL,
    )
