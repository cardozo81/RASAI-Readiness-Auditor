"""Command-line interface for RASAi - Search & AI Readiness Auditor."""

from __future__ import annotations

import argparse
import ipaddress
import logging
import math
import os
from pathlib import Path
import re
import tomllib
from urllib.parse import urlsplit

from rasai import __version__
from rasai.audit_runner import run_audit
from rasai.config import load_config
from rasai.device_context import DEVICE_CONTEXT_ENV, configured_device_context
from rasai.logging_config import configure_logging
from rasai.m18_ai import build_semantic_provider
from rasai.m21_reporting import enrich_m21_report_site
from rasai.m24_cli import configured_m24, register_m24_arguments
from rasai.m21_web_performance import DEFAULT_CATEGORIES, WebPerformanceConfig, execute_m21
from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditWorkspace

_LOGGER = logging.getLogger(__name__)
_DOMAIN_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
_DEFAULT_AI_TIMEOUT_SECONDS = 180.0
_AI_TIMEOUT_ENV = "RASAI_AI_TIMEOUT_SECONDS"
_CONTENT_REMEDIATION_ENV = "RASAI_AI_CONTENT_REMEDIATION"

_WEB_PERFORMANCE_ENV = "RASAI_WEB_PERFORMANCE"
_WEB_PERFORMANCE_MAX_PAGES_ENV = "RASAI_WEB_PERFORMANCE_MAX_PAGES"
_WEB_PERFORMANCE_TIMEOUT_ENV = "RASAI_WEB_PERFORMANCE_TIMEOUT_SECONDS"
_WEB_PERFORMANCE_FIELD_SOURCE_ENV = "RASAI_WEB_PERFORMANCE_FIELD_SOURCE"
_LIGHTHOUSE_CATEGORIES_ENV = "RASAI_LIGHTHOUSE_CATEGORIES"
_PAGESPEED_API_KEY_ENV = "RASAI_PAGESPEED_API_KEY"
_CRUX_API_KEY_ENV = "RASAI_CRUX_API_KEY"
_DEFAULT_WEB_PERFORMANCE_MAX_PAGES = 10
_DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS = 120.0


def _valid_hostname(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return True

    try:
        ascii_hostname = hostname.rstrip(".").encode("idna").decode("ascii")
    except UnicodeError:
        return False

    if len(ascii_hostname) > 253 or "." not in ascii_hostname:
        return False

    return all(_DOMAIN_LABEL.fullmatch(label) for label in ascii_hostname.split("."))


def validate_target(value: str) -> str:
    """Validate a domain or an HTTP(S) URL without performing network access."""

    target = value.strip()
    if not target or any(character.isspace() for character in target):
        raise ValueError("target must be a non-empty domain or HTTP(S) URL")

    has_scheme = "://" in target
    candidate = target if has_scheme else f"https://{target}"
    parsed = urlsplit(candidate)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("target URL scheme must be http or https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("target must not contain user credentials")
    if parsed.hostname is None or not _valid_hostname(parsed.hostname):
        raise ValueError("target must contain a valid hostname, IP address, or localhost")

    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("target contains an invalid port") from exc

    if not has_scheme and (parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("a target with path, query, or fragment must include http:// or https://")

    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rasai")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", help="path to rasai.toml; currently used for application logging settings")

    subparsers = parser.add_subparsers(dest="command", required=True)
    audit_parser = subparsers.add_parser("audit", help="execute a local RASAi readiness audit")
    audit_parser.add_argument(
        "target",
        nargs="*",
        help="one or more domains/HTTP(S) URLs to audit in the same audit_id",
    )
    audit_parser.add_argument(
        "--urls-file",
        help="UTF-8 text file with one domain/HTTP(S) URL per line; blank lines and # comments are ignored",
    )
    audit_parser.add_argument("--project", help="human-readable project name")
    audit_parser.add_argument("--language", default="pt-BR", help="primary content/reporting language context")
    audit_parser.add_argument("--market", default="BR", help="market context")
    audit_parser.add_argument("--max-pages", type=int, default=100, help="deterministic maximum number of audited pages")
    audit_parser.add_argument("--audits-root", default="audits", help="local directory that will contain audit workspaces")
    audit_parser.add_argument(
        "--device-context",
        choices=("mobile", "desktop", "both"),
        default=None,
        help=(
            "device context for rendering and semantic analysis; default is mobile, "
            f"or {DEVICE_CONTEXT_ENV} when configured"
        ),
    )
    audit_parser.add_argument(
        "--ai-provider",
        choices=("none", "openai", "deepseek", "mimo", "auto"),
        default="none",
        help="semantic analysis provider or deterministic AUTO routing",
    )
    audit_parser.add_argument(
        "--ai-model",
        help="model override for an explicit provider; AUTO uses RASAI_<PROVIDER>_MODEL",
    )
    audit_parser.add_argument(
        "--ai-content-remediation",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "enable evidence-bound exact-text content suggestions; default OFF, "
            f"or {_CONTENT_REMEDIATION_ENV} when configured. JSON-LD guidance is generated deterministically regardless"
        ),
    )
    audit_parser.add_argument(
        "--web-performance",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "enable external PageSpeed/Lighthouse and Core Web Vitals evidence; default OFF, "
            f"or {_WEB_PERFORMANCE_ENV} when configured"
        ),
    )
    audit_parser.add_argument(
        "--web-performance-max-pages",
        type=int,
        default=None,
        help=(
            "maximum audited pages sent to external web-performance services; 0 means all; "
            f"default {_DEFAULT_WEB_PERFORMANCE_MAX_PAGES} or {_WEB_PERFORMANCE_MAX_PAGES_ENV}"
        ),
    )
    audit_parser.add_argument(
        "--web-performance-timeout-seconds",
        type=float,
        default=None,
        help=(
            "timeout per PageSpeed/CrUX external request; "
            f"default {_DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS:g}s or {_WEB_PERFORMANCE_TIMEOUT_ENV}"
        ),
    )
    audit_parser.add_argument(
        "--web-performance-field-source",
        choices=("auto", "pagespeed", "crux", "none"),
        default=None,
        help=(
            "field-data policy: auto uses PageSpeed CrUX data and direct CrUX fallback when configured; "
            "pagespeed uses only PageSpeed field data; crux requires RASAI_CRUX_API_KEY; none disables field data"
        ),
    )
    register_m24_arguments(audit_parser)
    audit_parser.add_argument(
        "--lighthouse-categories",
        default=None,
        help=(
            "comma-separated Lighthouse categories: performance,accessibility,best-practices,seo,agentic-browsing; "
            "default requests all five in one PageSpeed call; agentic-browsing is experimental"
        ),
    )

    return parser


def _configured_ai_timeout_seconds() -> float:
    raw = os.environ.get(_AI_TIMEOUT_ENV)
    if raw is None or not raw.strip():
        return _DEFAULT_AI_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{_AI_TIMEOUT_ENV} must be a positive number of seconds") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{_AI_TIMEOUT_ENV} must be a positive finite number of seconds")
    return value


def _configured_bool(cli_value: bool | None, env_name: str, default: bool = False) -> bool:
    if cli_value is not None:
        return bool(cli_value)
    raw = os.environ.get(env_name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{env_name} must be one of: true/false, 1/0, yes/no, on/off")


def _configured_content_remediation(cli_value: bool | None) -> bool:
    return _configured_bool(cli_value, _CONTENT_REMEDIATION_ENV, False)


def _configured_nonnegative_int(cli_value: int | None, env_name: str, default: int) -> int:
    if cli_value is not None:
        value = cli_value
    else:
        raw = os.environ.get(env_name)
        if raw is None or not raw.strip():
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{env_name} must be an integer >= 0") from exc
    if value < 0:
        raise ValueError(f"{env_name} / CLI value must be >= 0")
    return value


def _configured_positive_float(cli_value: float | None, env_name: str, default: float) -> float:
    if cli_value is not None:
        value = cli_value
    else:
        raw = os.environ.get(env_name)
        if raw is None or not raw.strip():
            return default
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{env_name} must be a positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{env_name} / CLI value must be a positive finite number")
    return value


def _configured_lighthouse_categories(cli_value: str | None) -> tuple[str, ...]:
    raw = cli_value if cli_value is not None else os.environ.get(_LIGHTHOUSE_CATEGORIES_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_CATEGORIES
    values = tuple(item.strip().casefold() for item in raw.split(",") if item.strip())
    if not values:
        raise ValueError(f"{_LIGHTHOUSE_CATEGORIES_ENV} / --lighthouse-categories must not be empty")
    return values


def _configured_web_performance(args: argparse.Namespace) -> WebPerformanceConfig:
    enabled = _configured_bool(args.web_performance, _WEB_PERFORMANCE_ENV, False)
    # When M21 network collection is OFF, its tuning variables must not become
    # a new failure surface for the pre-existing audit command. Real workspaces
    # still materialize a DISABLED state using stable defaults.
    if not enabled:
        return WebPerformanceConfig(enabled=False).validate()

    max_pages = _configured_nonnegative_int(
        args.web_performance_max_pages,
        _WEB_PERFORMANCE_MAX_PAGES_ENV,
        _DEFAULT_WEB_PERFORMANCE_MAX_PAGES,
    )
    timeout = _configured_positive_float(
        args.web_performance_timeout_seconds,
        _WEB_PERFORMANCE_TIMEOUT_ENV,
        _DEFAULT_WEB_PERFORMANCE_TIMEOUT_SECONDS,
    )
    field_source = (
        args.web_performance_field_source
        or os.environ.get(_WEB_PERFORMANCE_FIELD_SOURCE_ENV, "auto")
    ).strip().casefold()
    config = WebPerformanceConfig(
        enabled=True,
        max_pages=max_pages,
        timeout_seconds=timeout,
        categories=_configured_lighthouse_categories(args.lighthouse_categories),
        field_source=field_source,
        pagespeed_api_key=os.environ.get(_PAGESPEED_API_KEY_ENV),
        crux_api_key=os.environ.get(_CRUX_API_KEY_ENV),
    )
    return config.validate()


def _apply_ai_timeout(provider, timeout: float):
    routed = getattr(provider, "providers", None)
    if isinstance(routed, tuple):
        for item in routed:
            if hasattr(item, "timeout"):
                item.timeout = timeout
    elif hasattr(provider, "timeout"):
        provider.timeout = timeout
    return provider


def _semantic_provider(args: argparse.Namespace):
    if args.ai_provider == "auto" and args.ai_model:
        raise ValueError("--ai-model cannot be used with --ai-provider=auto; configure per-provider RASAI_*_MODEL variables")
    provider = build_semantic_provider(args.ai_provider, model_override=args.ai_model)
    if args.ai_provider == "none":
        return provider
    return _apply_ai_timeout(provider, _configured_ai_timeout_seconds())


def _audit_targets(args: argparse.Namespace) -> tuple[str, ...]:
    values = list(args.target)
    if args.urls_file:
        path = Path(args.urls_file)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ValueError(f"cannot read --urls-file {path}: {exc}") from exc
        values.extend(
            line.strip()
            for line in lines
            if line.strip() and not line.lstrip().startswith("#")
        )
    if not values:
        raise ValueError("provide at least one target URL/domain or --urls-file")
    return tuple(validate_target(value) for value in values)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        configure_logging(config.log_level)
    except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
        parser.error(str(exc))

    if args.command == "audit":
        web_result = None
        web_report_path: Path | None = None
        web_runtime_failed = False
        workspace: AuditWorkspace | None = None
        try:
            targets = _audit_targets(args)
            if args.max_pages <= 0:
                raise ValueError("--max-pages must be greater than zero")

            device_context = configured_device_context(cli_value=args.device_context, default="mobile")
            content_remediation = _configured_content_remediation(args.ai_content_remediation)
            technical_remediation = configured_m24(args).technical_ai
            web_performance = _configured_web_performance(args)
            previous_device_context = os.environ.get(DEVICE_CONTEXT_ENV)
            os.environ[DEVICE_CONTEXT_ENV] = device_context
            try:
                provider = _semantic_provider(args)
                audit_target: str | tuple[str, ...] = (
                    targets
                    if args.urls_file or len(targets) > 1
                    else targets[0]
                )
                result = run_audit(
                    audit_target,
                    audits_root=Path(args.audits_root),
                    project_name=args.project,
                    language=args.language,
                    market=args.market,
                    max_pages=args.max_pages,
                    semantic_provider=provider,
                    content_remediation=content_remediation,
                    technical_remediation=technical_remediation,
                )
                # Real audit workspaces materialize the M21 state even when
                # external collection is OFF, so the report can explain the
                # opt-in status. Mocked/internal callers that return no actual
                # workspace retain the default-OFF path without failure.
                # Any M21 problem after core completion remains fail-open.
                if web_performance.enabled or result.audit_root.is_dir():
                    try:
                        workspace = AuditWorkspace.open(result.audit_root)
                        web_result = execute_m21(
                            audit_id=result.audit_id,
                            workspace=workspace,
                            config=web_performance,
                        )
                        web_report_path = enrich_m21_report_site(
                            audit_id=result.audit_id,
                            workspace=workspace,
                        )
                        try_append_operational_event(
                            workspace,
                            "M21_REPORT_GENERATED",
                            audit_id=result.audit_id,
                            report_path=str(web_report_path.relative_to(workspace.root)),
                        )
                    except Exception as exc:
                        web_runtime_failed = True
                        if workspace is not None:
                            try_append_operational_event(
                                workspace,
                                "M21_RUNTIME_FAILURE",
                                level="ERROR",
                                audit_id=result.audit_id,
                                error_type=type(exc).__name__,
                                error_message=str(exc)[:512],
                            )
                        _LOGGER.exception(
                            "External web-performance enrichment failed after core audit completion"
                        )
            finally:
                if previous_device_context is None:
                    os.environ.pop(DEVICE_CONTEXT_ENV, None)
                else:
                    os.environ[DEVICE_CONTEXT_ENV] = previous_device_context
        except (OSError, ValueError, RuntimeError) as exc:
            _LOGGER.exception("Audit failed")
            parser.error(str(exc))

        print(f"Auditoria concluída: {result.audit_id}")
        print(f"Status: {result.completion_status.value}")
        print(f"Páginas auditadas: {result.audited_pages}")
        print(f"Contexto de dispositivo: {device_context.upper()}")
        print(f"Sugestões de conteúdo por IA: {'HABILITADAS' if content_remediation else 'DESABILITADAS'}")
        if not web_performance.enabled:
            print("Web Performance externo: DESABILITADO")
        elif web_result is not None:
            print(
                "Web Performance externo: HABILITADO "
                f"({web_result.status}; páginas {web_result.pages_considered}; "
                f"contextos úteis {web_result.successful_contexts}/{web_result.context_attempts}; "
                f"PageSpeed {web_result.pagespeed_successes}/{web_result.pagespeed_attempts}; "
                f"CrUX {web_result.crux_successes}/{web_result.crux_attempts})"
            )
            if web_result.status == "PARTIAL":
                print(
                    "Web Performance aviso: coleta parcial; um ou mais componentes externos falharam "
                    "ou ficaram indisponíveis. Consulte o relatório e o log operacional."
                )
        elif web_runtime_failed:
            print(
                "Web Performance externo: HABILITADO (INCOMPLETO por erro operacional do enriquecimento; "
                "o resultado RASAi principal foi preservado)"
            )
        print(f"Problemas identificados: {result.finding_count}")
        print(f"Recomendações: {result.recommendation_count}")
        print(f"Relatório: {result.report_path}")
        remediation_path = result.audit_root / "report" / "remediation.html"
        if remediation_path.is_file():
            print(f"Relatório por problemas: {remediation_path}")
        content_path = result.audit_root / "report" / "content-suggestions.html"
        if content_path.is_file():
            print(f"Conteúdo e JSON-LD: {content_path}")
        if web_report_path is not None and web_report_path.is_file():
            print(f"Core Web Vitals e Lighthouse: {web_report_path}")
        log_path = result.audit_root / "logs" / "audit.log"
        if log_path.is_file():
            print(f"Log operacional: {log_path}")
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2
