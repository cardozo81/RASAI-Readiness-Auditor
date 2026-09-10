"""Interactive-console integration for point-in-time Search Intelligence.

Search terms are execution input, not environment variables and not persistent console
configuration. Provider credentials and hard safety/cost limits remain environment-owned.
When terms are present, the extension runs Search Intelligence after a successful audit
and binds the observations to the newly created AUD-* workspace.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import builtins
import io
import os
from pathlib import Path
import time
from types import ModuleType
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit

from rasai.console_artifacts import audit_workspace
from rasai.console_m23 import State as BaseState
from rasai.search_intelligence.config import SERPAPI_KEY_ENV, SerpRuntimeConfig
from rasai.search_intelligence.runtime import projected_http_request_ceiling


@dataclass(slots=True)
class SearchConsoleState(BaseState):
    """Add transient Search Intelligence input to the existing console state."""

    search_queries: tuple[str, ...] = ()
    search_depth: int = 20
    search_region: str = ""
    search_device: str = "mobile"
    search_competitive: bool = True
    search_last_status: str = "NOT_REQUESTED"
    search_last_detail: str = ""
    search_last_report: str = ""
    search_last_duration_seconds: float | None = None


def parse_search_terms(raw: str) -> tuple[str, ...]:
    """Parse semicolon/newline separated terms preserving order and removing duplicates."""

    normalized = raw.replace("\r", "\n").replace("\n", ";")
    seen: set[str] = set()
    result: list[str] = []
    for item in normalized.split(";"):
        term = " ".join(item.strip().split())
        key = term.casefold()
        if not term or key in seen:
            continue
        seen.add(key)
        result.append(term)
    return tuple(result)


def _engine_for_provider(provider: str) -> str:
    normalized = provider.strip().casefold()
    return "bing" if normalized == "serpapi-bing" else "google"


def _configured_search(state: object, env: Mapping[str, str] | None = None) -> SerpRuntimeConfig:
    environment = os.environ if env is None else env
    config = SerpRuntimeConfig.from_environment(environment)
    queries = tuple(getattr(state, "search_queries", ()) or ())
    if not queries:
        return config
    if config.mode == "disabled":
        raise ValueError(
            "Search Intelligence possui termos, mas RASAI_SERP_MODE está disabled; "
            "use live (SerpApi) ou fixture"
        )
    if len(queries) > config.max_queries:
        raise ValueError(
            f"{len(queries)} termo(s) excedem RASAI_SERP_MAX_QUERIES={config.max_queries}"
        )
    depth = int(getattr(state, "search_depth", 20))
    if depth <= 0:
        raise ValueError("profundidade SERP deve ser > 0")
    if depth > config.max_depth:
        raise ValueError(
            f"profundidade SERP {depth} excede RASAI_SERP_MAX_DEPTH={config.max_depth}"
        )
    device = str(getattr(state, "search_device", "mobile")).casefold()
    if device not in {"mobile", "desktop"}:
        raise ValueError("dispositivo SERP deve ser mobile ou desktop")
    if config.mode == "live":
        if config.provider not in {"serpapi", "serpapi-bing"}:
            raise ValueError(
                f"provider SERP live não suportado pelo console: {config.provider}"
            )
        if not (environment.get(SERPAPI_KEY_ENV) or "").strip():
            raise ValueError(
                f"{SERPAPI_KEY_ENV} não configurada para Search Intelligence live"
            )
        projected = projected_http_request_ceiling(
            config, depths=(depth for _ in queries)
        )
        if config.provider != "serpapi-bing" and projected > config.max_requests:
            raise ValueError(
                f"teto projetado de {projected} requests SERP excede "
                f"RASAI_SERP_MAX_REQUESTS={config.max_requests}"
            )
    return config


def _default_search_device(state: object) -> str:
    device = str(getattr(state, "device", "mobile")).casefold()
    return device if device in {"mobile", "desktop"} else "mobile"


def _yes_no(prompt: str, current: bool) -> bool:
    suffix = "S/n" if current else "s/N"
    raw = input(f"{prompt} [{suffix}]: ").strip().casefold()
    if not raw:
        return current
    if raw in {"s", "sim", "y", "yes", "1", "true", "on"}:
        return True
    if raw in {"n", "nao", "não", "no", "0", "false", "off"}:
        return False
    raise ValueError("responda S ou N")


def configure_search_intelligence(state: SearchConsoleState) -> None:
    """Collect execution-scoped Search terms and observation context."""

    try:
        config = SerpRuntimeConfig.from_environment()
    except ValueError as exc:
        state.error = f"configuração SERP inválida: {exc}"
        return

    print("\nSEARCH INTELLIGENCE / SERP")
    print(
        "Termos são dados desta sessão de execução; não são variáveis de ambiente "
        "e não são gravados no rasai-console.ini."
    )
    key_state = "[SET]" if (os.environ.get(SERPAPI_KEY_ENV) or "").strip() else "<não definida>"
    print(
        f"Provider atual: mode={config.mode} | provider={config.provider} | "
        f"engine={_engine_for_provider(config.provider)} | {SERPAPI_KEY_ENV}={key_state}"
    )
    print(
        f"Limites: queries={config.max_queries} | requests={config.max_requests} | "
        f"depth máxima={config.max_depth} | timeout={config.timeout_seconds:g}s"
    )

    current_enabled = bool(state.search_queries)
    try:
        enabled = _yes_no(
            "Executar Search Intelligence após a auditoria e associar ao AUD gerado?",
            current_enabled,
        )
        if not enabled:
            state.search_queries = ()
            state.search_last_status = "NOT_REQUESTED"
            state.search_last_detail = ""
            state.search_last_report = ""
            state.search_last_duration_seconds = None
            state.error = ""
            return

        if config.mode == "disabled":
            raise ValueError(
                "RASAI_SERP_MODE está disabled; configure live para SerpApi antes de habilitar termos"
            )
        if config.mode == "live" and not (os.environ.get(SERPAPI_KEY_ENV) or "").strip():
            raise ValueError(f"{SERPAPI_KEY_ENV} não configurada")

        current = "; ".join(state.search_queries)
        raw = input(
            "Termo(s) de busca; separe múltiplos por ';'"
            + (f" [{current}]" if current else "")
            + ": "
        ).strip()
        queries = parse_search_terms(raw) if raw else state.search_queries
        if not queries:
            raise ValueError("informe pelo menos um termo de busca")
        if len(queries) > config.max_queries:
            raise ValueError(
                f"foram informados {len(queries)} termos; limite atual é {config.max_queries}"
            )
        state.search_queries = queries

        current_depth = min(max(int(state.search_depth), 1), config.max_depth)
        depth_raw = input(
            f"Profundidade SERP [1-{config.max_depth}] [{current_depth}]: "
        ).strip()
        depth = current_depth if not depth_raw else int(depth_raw)
        if depth <= 0 or depth > config.max_depth:
            raise ValueError(
                f"profundidade deve estar entre 1 e {config.max_depth}"
            )
        state.search_depth = depth

        default_device = (
            state.search_device
            if state.search_queries and state.search_device in {"mobile", "desktop"}
            else _default_search_device(state)
        )
        device_raw = input(
            f"Dispositivo SERP [mobile/desktop] [{default_device}]: "
        ).strip().casefold()
        device = default_device if not device_raw else device_raw
        if device not in {"mobile", "desktop"}:
            raise ValueError("dispositivo SERP deve ser mobile ou desktop")
        state.search_device = device

        region_raw = input(
            f"Região/localidade opcional [{state.search_region or 'vazio'}]: "
        ).strip()
        if region_raw:
            state.search_region = region_raw

        state.search_competitive = _yes_no(
            "Classificar deterministicamente os resultados/concorrentes à frente?",
            state.search_competitive,
        )
        _configured_search(state)
        state.search_last_status = "PENDING"
        state.search_last_detail = (
            f"{len(state.search_queries)} termo(s); "
            f"{_engine_for_provider(config.provider)}/{state.search_device}; "
            f"depth={state.search_depth}"
        )
        state.error = ""
    except (TypeError, ValueError) as exc:
        state.error = f"Search Intelligence: {exc}"


def validate_search_readiness(
    state: object, env: Mapping[str, str] | None = None
) -> tuple[bool, str]:
    queries = tuple(getattr(state, "search_queries", ()) or ())
    if not queries:
        return True, "Search Intelligence sem termos nesta execução"
    try:
        config = _configured_search(state, env)
    except ValueError as exc:
        return False, str(exc)
    projected = projected_http_request_ceiling(
        config, depths=(int(getattr(state, "search_depth", 20)) for _ in queries)
    )
    engine = _engine_for_provider(config.provider)
    return (
        True,
        f"Search Intelligence: {len(queries)} termo(s), {engine}, "
        f"depth={getattr(state, 'search_depth', 20)}, teto provider={projected}",
    )


def build_search_argv(
    state: object,
    *,
    workspace: Path,
    target_url: str,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    config = _configured_search(state, env)
    queries = tuple(getattr(state, "search_queries", ()) or ())
    if not queries:
        raise ValueError("nenhum termo Search Intelligence configurado")
    host = urlsplit(target_url).hostname
    if not host:
        raise ValueError(f"não foi possível derivar domínio do target {target_url!r}")
    argv = [
        *queries,
        "--domain",
        host,
        "--engine",
        _engine_for_provider(config.provider),
        "--country",
        str(getattr(state, "market", "BR")),
        "--language",
        str(getattr(state, "language", "pt-BR")),
        "--device",
        str(getattr(state, "search_device", "mobile")),
        "--depth",
        str(int(getattr(state, "search_depth", 20))),
        "--audit-workspace",
        str(workspace),
    ]
    region = str(getattr(state, "search_region", "") or "").strip()
    if region:
        argv.extend(["--region", region])
    if bool(getattr(state, "search_competitive", True)):
        argv.append("--competitive")
    return argv


def execute_search_for_audit(
    state: SearchConsoleState,
    *,
    target_url: str,
    runner: Callable[[Sequence[str] | None], int] | None = None,
) -> int:
    """Run Search after the core audit; failures stay non-scoring/fail-open."""

    workspace = audit_workspace(state)
    if workspace is None:
        state.search_last_status = "UNAVAILABLE"
        state.search_last_detail = "workspace AUD da sessão não encontrado"
        state.search_last_report = ""
        return 1

    if runner is None:
        from rasai.search_intelligence.cli import main as runner

    argv = build_search_argv(state, workspace=workspace, target_url=target_url)
    output = io.StringIO()
    started = time.monotonic()
    try:
        with redirect_stdout(output), redirect_stderr(output):
            code = int(runner(argv) or 0)
    except SystemExit as exc:
        raw_code = exc.code if isinstance(exc.code, int) else 2
        code = int(raw_code)
    except (OSError, ValueError) as exc:
        code = 2
        output.write(f"{type(exc).__name__}: {exc}")
    duration = max(time.monotonic() - started, 0.0)
    report = workspace / "report" / "search-intelligence.html"

    state.search_last_duration_seconds = duration
    state.search_last_report = str(report) if report.is_file() else ""
    diagnostic_lines = [
        line.strip() for line in output.getvalue().splitlines() if line.strip()
    ]
    diagnostic = diagnostic_lines[-1] if diagnostic_lines else ""

    if code == 0 and report.is_file():
        state.search_last_status = "COMPLETE"
        state.search_last_detail = (
            f"{len(state.search_queries)} termo(s) observados; "
            f"relatório={report.name}; duração={duration:.1f}s"
        )
        return 0

    state.search_last_status = "COMPLETE_WITH_LIMITATIONS"
    if code == 0:
        state.search_last_detail = (
            "observação executada, mas search-intelligence.html não foi materializado"
        )
    else:
        state.search_last_detail = (
            f"Search Intelligence retornou código {code}"
            + (f": {diagnostic}" if diagnostic else "")
        )
    return code or 1


def _render_menu_extension(state: SearchConsoleState) -> None:
    queries = tuple(getattr(state, "search_queries", ()) or ())
    if queries:
        preview = "; ".join(queries[:2])
        if len(queries) > 2:
            preview += f"; +{len(queries) - 2}"
        try:
            config = SerpRuntimeConfig.from_environment()
            provider = f"{config.provider}/{_engine_for_provider(config.provider)}"
        except ValueError:
            provider = "configuração inválida"
        status = (
            f"{len(queries)} termo(s) | {provider} | "
            f"{state.search_device} | depth={state.search_depth} | {preview}"
        )
    else:
        mode = (os.environ.get("RASAI_SERP_MODE") or "disabled").strip().casefold()
        status = f"sem termos nesta execução | provider mode={mode}"
    print("\nSEARCH INTELLIGENCE")
    print(f"T. Termos SERP            : {status}")
    print("   Termos são transitórios da sessão; credencial/provider/limites continuam em E.")


def install(console_module: ModuleType) -> None:
    """Install Search Intelligence into the existing console without reimplementing it."""

    if getattr(console_module, "_search_intelligence_console_installed", False):
        return

    original_menu = console_module._menu
    original_configure = console_module._configure
    original_readiness = console_module._execution_readiness
    original_run = console_module.run_audit_from_console
    original_usage = console_module._render_actual_usage

    console_module.State = SearchConsoleState

    def menu(state: SearchConsoleState) -> str:
        original_input = builtins.input
        injected = False

        def decorated_input(prompt: str = "") -> str:
            nonlocal injected
            if not injected and prompt.strip().casefold().startswith("escolha"):
                _render_menu_extension(state)
                injected = True
            return original_input(prompt)

        builtins.input = decorated_input
        try:
            return original_menu(state)
        finally:
            builtins.input = original_input

    def configure(state: SearchConsoleState, choice: str) -> None:
        if choice == "T":
            configure_search_intelligence(state)
            return
        original_configure(state, choice)

    def readiness(state: SearchConsoleState) -> tuple[bool, str]:
        ready, reason = original_readiness(state)
        if not ready:
            return ready, reason
        search_ready, search_reason = validate_search_readiness(state)
        if not search_ready:
            return False, search_reason
        if state.search_queries:
            return True, f"{reason}; {search_reason}"
        return ready, reason

    def run(state: SearchConsoleState) -> int:
        code = int(original_run(state) or 0)
        if code != 0 or not state.search_queries:
            return code
        try:
            targets = console_module.preflight(state)
            target_url = targets[0]
        except (OSError, ValueError, UnicodeError) as exc:
            state.search_last_status = "COMPLETE_WITH_LIMITATIONS"
            state.search_last_detail = f"não foi possível resolver o domínio pós-auditoria: {exc}"
            if code == 0:
                state.status = "COMPLETE_WITH_LIMITATIONS"
            return code

        previous_status = state.status
        state.status = "SEARCH_INTELLIGENCE"
        state.operation = "API:SERP"
        try:
            console_module.render_header(state)
            print(
                f"Search Intelligence: consultando {len(state.search_queries)} termo(s) "
                "e associando as observações ao AUD atual..."
            )
        except Exception:
            pass

        search_code = execute_search_for_audit(state, target_url=target_url)
        if search_code == 0:
            state.status = previous_status
            state.operation = "LOCAL:DONE"
        else:
            state.status = "COMPLETE_WITH_LIMITATIONS"
            state.operation = "INTEGRATION:SEARCH_INTELLIGENCE_LIMITATION"
        return code

    def usage(state: SearchConsoleState) -> None:
        original_usage(state)
        queries = tuple(getattr(state, "search_queries", ()) or ())
        if not queries and state.search_last_status == "NOT_REQUESTED":
            print("Search Intelligence   : não solicitado nesta sessão")
            return
        print(
            f"Search Intelligence   : {state.search_last_status} | "
            f"termos={len(queries)}"
        )
        if state.search_last_detail:
            print(f"Detalhe Search       : {state.search_last_detail}")
        if state.search_last_report:
            print(f"Relatório Search     : {state.search_last_report}")

    console_module._menu = menu
    console_module._configure = configure
    console_module._execution_readiness = readiness
    console_module.run_audit_from_console = run
    console_module._render_actual_usage = usage
    console_module._search_intelligence_console_installed = True
