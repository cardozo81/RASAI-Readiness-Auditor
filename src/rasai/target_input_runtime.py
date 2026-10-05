"""Runtime wiring for BOM-safe URL-set input with exact line diagnostics."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Mapping

_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import cli, console_config, console_cost
    from rasai.provider_registry import get_provider_registration
    from rasai.url_utils import normalize_url, normalized_origin

    def audit_targets(args: Any) -> tuple[str, ...]:
        if getattr(args, "urls_file", None):
            raise ValueError(
                "--urls-file is not supported for new audits; provide exactly one target URL/domain"
            )
        raw = getattr(args, "target", "")
        if isinstance(raw, (list, tuple)):
            values = [str(value).strip() for value in raw if str(value).strip()]
            if len(values) != 1:
                raise ValueError("new audits require exactly one target URL/domain")
            raw = values[0]
        target = str(raw or "").strip()
        if not target:
            raise ValueError("provide exactly one target URL/domain")
        return (cli.validate_target(target),)

    def preflight(state: Any, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
        environment = env if env is not None else console_config.os.environ
        if (
            state.max_pages <= 0
            or state.web_max_pages < 0
            or state.web_timeout <= 0
            or state.ai_timeout <= 0
            or not 1 <= int(getattr(state, "ai_max_cycles", 3)) <= 10
            or not 0 <= float(getattr(state, "ai_cycle_delay", 60.0)) <= 300
        ):
            raise ValueError("limites/timeout/política de IA inválidos")
        console_config.configured_content_analysis_context(environment)
        if state.input_mode != "url":
            raise ValueError("novas auditorias exigem Entrada=URL única")
        if not state.target.strip():
            raise ValueError("informe uma URL/domínio")
        targets = (cli.validate_target(state.target),)

        normalized = tuple(dict.fromkeys(normalize_url(item) for item in targets))
        if len({normalized_origin(item) for item in normalized}) != 1:
            raise ValueError("target inválido para a origem normalizada")
        registration = get_provider_registration(state.ai_provider)
        provider_id = registration.id if registration else state.ai_provider
        capability = console_config.provider_capabilities(
            environment, state.runtime_blocks
        ).get(provider_id)
        if state.ai_provider not in {"none", "auto"} and registration is None:
            raise ValueError(f"provider de IA desconhecido: {state.ai_provider}")
        # A known provider may be unavailable, uncredentialed or exhausted. That is
        # persisted by the execution runtime and must not block deterministic work.
        if state.ai_provider == "auto" and state.ai_model:
            raise ValueError("AUTO não aceita --ai-model")
        # Direct CrUX credentials are operational readiness, not a preflight gate.
        browser = (environment.get("RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE") or "").strip()
        if browser and not Path(browser).is_file():
            raise ValueError("RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE não existe")
        return normalized

    def configured_page_range(state: Any) -> tuple[int, int]:
        if state.input_mode != "url":
            return 0, 0
        if not state.target.strip() or state.max_pages <= 0:
            return 0, 0
        return 1, state.max_pages

    cli._audit_targets = audit_targets
    console_config.preflight = preflight
    console_cost._configured_page_range = configured_page_range

    # Console modules import preflight by value. Patch only modules that are already
    # loaded; CLI execution must not import the interactive console as a side effect.
    console_runtime = sys.modules.get("rasai.console_runtime")
    if console_runtime is not None:
        console_runtime.preflight = preflight
    interactive_console = sys.modules.get("rasai.interactive_console")
    if interactive_console is not None:
        interactive_console.preflight = preflight

    _INSTALLED = True
