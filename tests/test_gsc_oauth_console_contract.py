from __future__ import annotations

from rasai import console_environment as base
from rasai.gsc_oauth import CLIENT_ID_ENV, CLIENT_SECRET_ENV, REFRESH_TOKEN_ENV
from rasai.gsc_oauth_console import install


def test_gsc_oauth_variables_are_exposed_with_secret_safety() -> None:
    install()
    by_name = {spec.name: spec for spec in base.SPECS}

    assert CLIENT_ID_ENV in base.ENV_NAMES
    assert CLIENT_SECRET_ENV in base.ENV_NAMES
    assert REFRESH_TOKEN_ENV in base.ENV_NAMES

    assert by_name[CLIENT_ID_ENV].sensitive is False
    assert by_name[CLIENT_SECRET_ENV].sensitive is True
    assert by_name[REFRESH_TOKEN_ENV].sensitive is True
