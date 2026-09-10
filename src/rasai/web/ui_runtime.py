"""Runtime adaptation of the zero-build pilot shell for the selected auth mode."""
from __future__ import annotations

import re

from .ui import PILOT_UI_HTML


def render_pilot_ui(auth_mode: str) -> str:
    """Return the pilot shell without exposing trusted-header UX in OIDC mode.

    The base asset remains static/zero-build. In OIDC mode a stale local-development
    identity is cleared and an expired browser session restarts the OIDC login flow
    instead of displaying the ``USR-*`` trusted-header helper.
    """

    if auth_mode != "oidc":
        return PILOT_UI_HTML
    html = PILOT_UI_HTML.replace(
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
