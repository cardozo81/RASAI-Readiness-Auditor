from __future__ import annotations

from unittest.mock import patch

from rasai import console_entrypoint
from rasai.console_environment import EnvironmentSpec


def test_console_startup_activates_only_effective_secret_specs() -> None:
    secret = EnvironmentSpec(
        "OPENAI_API_KEY",
        "IA - credenciais",
        "credencial",
        "segredo/API key",
        sensitive=False,  # naming classifier must still treat it as a secret
    )
    explicit_secret = EnvironmentSpec(
        "RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN",
        "Search Intelligence / Observability",
        "refresh token",
        "segredo/OAuth",
        sensitive=True,
    )
    plain = EnvironmentSpec(
        "RASAI_AI_MODELS_SOURCE",
        "IA - modelos e reasoning",
        "origem",
        "enum",
        sensitive=False,
    )
    captured: list[str] = []

    def activate(names):
        captured.extend(tuple(names))
        return tuple(captured)

    with (
        patch.object(
            console_entrypoint.console_environment,
            "refresh_specs",
            return_value=(secret, explicit_secret, plain),
        ),
        patch.object(console_entrypoint, "activate_persisted_environment", side_effect=activate),
    ):
        activated = console_entrypoint._activate_persisted_console_secrets()

    assert activated == ("OPENAI_API_KEY", "RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN")
    assert captured == ["OPENAI_API_KEY", "RASAI_GOOGLE_SEARCH_CONSOLE_REFRESH_TOKEN"]
