"""Runtime wiring for BOM-safe URL-set input with exact line diagnostics."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from rasai.target_file import validated_target_file

_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import cli, console_config, console_cost
    from rasai.provider_registry import get_provider_registration
    from rasai.url_utils import normalize_url, normalized_origin

    def audit_targets(args: Any) -> tuple[str, ...]:
        values = list(args.target)
        if args.urls_file:
            path = Path(args.urls_file)
            if not path.is_file():
                raise ValueError(f"cannot read --urls-file {path}: file not found")
            values.extend(validated_target_file(path, cli.validate_target))
        if not values:
            raise ValueError("provide at least one target URL/domain or --urls-file")
        return tuple(cli.validate_target(value) for value in values)

    def preflight(state: Any, env: Mapping[str, str] | None = None) -> tuple[str, ...]:
        environment = env if env is not None else console_config.os.environ
        if state.max_pages <= 0 or state.web_max_pages < 0 or state.web_timeout <= 0 or state.ai_timeout <= 0:
            raise ValueError("limites/timeout inválidos")
        console_config.configured_content_analysis_context(environment)
        if state.input_mode == "url":
            if not state.target.strip():
                raise ValueError("informe uma URL/domínio")
            targets = (cli.validate_target(state.target),)
        elif state.input_mode == "file":
            path = Path(state.target)
            if not path.is_file():
                raise ValueError(f"TXT não encontrado: {path}")
            targets = validated_target_file(path, cli.validate_target)
        else:
            raise ValueError("modo de entrada inválido")

        normalized = tuple(dict.fromkeys(normalize_url(item) for item in targets))
        if len({normalized_origin(item) for item in normalized}) != 1:
            raise ValueError("todos os targets devem pertencer à mesma origem normalizada")
        if state.input_mode == "file" and len(normalized) > state.max_pages:
            raise ValueError(
                f"TXT possui {len(normalized)} URLs únicas e max-pages={state.max_pages}"
            )
        registration = get_provider_registration(state.ai_provider)
        provider_id = registration.id if registration else state.ai_provider
        capability = console_config.provider_capabilities(
            environment, state.runtime_blocks
        ).get(provider_id)
        if not capability or not capability.available:
            reason = capability.reason if capability else "inválido"
            raise ValueError(f"provider {state.ai_provider} indisponível: {reason}")
        if state.ai_provider == "none" and (
            state.content_remediation or state.technical_remediation
        ):
            raise ValueError("remediações de IA exigem provider de IA apto")
        if state.ai_provider == "auto" and state.ai_model:
            raise ValueError("AUTO não aceita --ai-model")
        if state.web_performance and state.field_source == "crux" and not (
            environment.get("RASAI_CRUX_API_KEY") or ""
        ).strip():
            raise ValueError("field source crux exige RASAI_CRUX_API_KEY")
        browser = (environment.get("RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE") or "").strip()
        if browser and not Path(browser).is_file():
            raise ValueError("RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE não existe")
        return normalized

    def configured_page_range(state: Any) -> tuple[int, int]:
        if state.input_mode == "file":
            path = Path(state.target).expanduser()
            if not path.is_file():
                return 0, 0
            try:
                targets = validated_target_file(path, cli.validate_target)
                urls = [normalize_url(value) for value in targets]
            except (ValueError, OSError, UnicodeError):
                # Preflight surfaces the exact line error.  The exposure preview must
                # never hide invalid lines and pretend the file contains fewer URLs.
                return 0, 0
            count = len(dict.fromkeys(urls))
            return count, count
        if not state.target.strip() or state.max_pages <= 0:
            return 0, 0
        return 1, state.max_pages

    cli._audit_targets = audit_targets
    console_config.preflight = preflight
    console_cost._configured_page_range = configured_page_range
    _INSTALLED = True
