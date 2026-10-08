"""Interactive-console integration for point-in-time Search Intelligence.

Search terms are execution input, not environment variables and not persistent console
configuration. Provider credentials and hard safety/cost limits remain environment-owned.
When terms are present, the extension binds Search Intelligence execution to the AUD
workspace and reports execution state from persisted evidence.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
import builtins
import io
import math
import os
import sqlite3
from pathlib import Path
import time
from types import ModuleType
from typing import Callable, Mapping, Sequence
from urllib.parse import urlsplit

from rasai.console_artifacts import audit_workspace
from rasai.console_m23 import State as BaseState
from rasai.persistence import AuditWorkspace
from rasai.search_intelligence.config import SerpRuntimeConfig, provider_key_env
from rasai.search_intelligence.perplexity import (
    API_KEY_ENV as PERPLEXITY_API_KEY_ENV,
    MAX_QUERIES_PER_REQUEST as PERPLEXITY_MAX_QUERIES,
    execute_perplexity_search,
    humanized_perplexity_summary,
    perplexity_configuration_status,
)
from rasai.search_intelligence.provider_catalog import serp_provider_registration
from rasai.search_intelligence.runtime import (
    projected_http_request_ceiling,
    validate_live_provider_engine,
)


@dataclass(slots=True)
class SearchConsoleState(BaseState):
    """Add transient Search Intelligence input to the existing console state."""

    search_queries: tuple[str, ...] = ()
    search_depth: int = 20
    search_region: str = ""
    search_device: str = "mobile"
    search_competitive: bool = True
    search_compare_content: bool = False
    search_max_content_pages: int = 3
    search_content_timeout_seconds: float = 10.0
    search_content_max_bytes: int = 2_000_000
    search_content_max_redirects: int = 5
    search_ai_competitive: bool = False
    search_ymyl_mode: str = "AUTO"
    search_last_status: str = "NOT_REQUESTED"
    search_last_detail: str = ""
    search_last_report: str = ""
    search_last_duration_seconds: float | None = None
    perplexity_queries: tuple[str, ...] = ()
    perplexity_search_type: str = "web"
    geo_ai_requested: bool = False
    perplexity_last_status: str = "NOT_REQUESTED"
    perplexity_last_detail: str = ""
    perplexity_last_duration_seconds: float | None = None


def _explicit_brazil_scope(region: str) -> bool:
    """Detect explicit Brazilian locale, never guess from provider defaults."""
    normalized = " ".join(str(region or "").casefold().split())
    if normalized in {"br", "brasil", "brazil", "brazilian"}:
        return True
    suffixes = (", br", ", brasil", ", brazil")
    return normalized.endswith(suffixes) or any(
        token in normalized for token in (", br,", ", brasil,", ", brazil,")
    )


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


def _provider_registration(provider: str):
    return serp_provider_registration(provider)


def _engine_for_provider(provider: str) -> str:
    registration = _provider_registration(provider)
    return registration.engine if registration is not None else "unknown"


def _configured_search(state: object, env: Mapping[str, str] | None = None) -> SerpRuntimeConfig:
    environment = os.environ if env is None else env
    config = SerpRuntimeConfig.from_environment(environment)
    queries = tuple(getattr(state, "search_queries", ()) or ())
    if not queries:
        return config
    if config.mode == "disabled":
        raise ValueError(
            "Search Intelligence possui termos, mas RASAI_SERP_MODE está disabled; "
            "use live ou fixture"
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

    compare_content = bool(getattr(state, "search_compare_content", False))
    max_content_pages = int(getattr(state, "search_max_content_pages", 3))
    if max_content_pages < 0 or max_content_pages > config.max_competitors:
        raise ValueError(
            "páginas competitivas deve ficar entre 0 e "
            f"RASAI_SERP_MAX_COMPETITORS={config.max_competitors}"
        )
    content_timeout = float(getattr(state, "search_content_timeout_seconds", 10.0))
    if not math.isfinite(content_timeout) or content_timeout <= 0:
        raise ValueError("timeout da comparação de conteúdo deve ser finito e > 0")
    if int(getattr(state, "search_content_max_bytes", 2_000_000)) <= 0:
        raise ValueError("limite de bytes da comparação de conteúdo deve ser > 0")
    if int(getattr(state, "search_content_max_redirects", 5)) < 0:
        raise ValueError("máximo de redirects da comparação de conteúdo deve ser >= 0")
    ai_competitive = bool(getattr(state, "search_ai_competitive", False))
    if ai_competitive and not compare_content:
        raise ValueError("IA competitiva exige Comparação de conteúdo ativada")
    # AI provider readiness is evaluated by the governed AI phase. The real
    # prerequisite here is competitive content evidence, enforced above.
    ymyl_mode = str(getattr(state, "search_ymyl_mode", "AUTO") or "AUTO").strip().upper()
    if ymyl_mode not in {"AUTO", "ON", "OFF"}:
        raise ValueError("modo YMYL competitivo deve ser AUTO, ON ou OFF")
    if config.mode == "live":
        registration = _provider_registration(config.provider)
        if registration is None:
            raise ValueError(f"provider SERP live desconhecido: {config.provider}")
        validate_live_provider_engine(config.provider, registration.engine)
        key_env = provider_key_env(config.provider)
        # Missing live-provider credentials become a persisted integration
        # NOT_CONFIGURED/UNAVAILABLE outcome instead of aborting the whole audit.
        projected = projected_http_request_ceiling(
            config, depths=(depth for _ in queries)
        )
        if registration.pagination_mode != "provider-driven" and projected > config.max_requests:
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

    registration = _provider_registration(config.provider)
    engine = registration.engine if registration is not None else "unknown"
    key_env = registration.key_env if registration is not None else "<provider sem credencial conhecida>"
    key_state = (
        "[SET]"
        if registration is not None and (os.environ.get(registration.key_env) or "").strip()
        else "<não definida>"
    )

    print("\nSEARCH INTELLIGENCE / SERP")
    print(
        "Termos são dados desta sessão de execução; não são variáveis de ambiente "
        "e não são gravados no rasai-console.ini."
    )
    print(
        f"Provider atual: mode={config.mode} | provider={config.provider} | "
        f"engine={engine} | {key_env}={key_state}"
    )
    if registration is not None:
        print(f"Chave/login: {registration.credential_url}")
        print(
            f"Free tier: {'sim' if registration.free_tier else 'não'}"
            + (f" | {registration.free_tier_note}" if registration.free_tier_note else "")
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
                "RASAI_SERP_MODE está disabled; configure um provider live ou fixture antes de habilitar termos"
            )
        if config.mode == "live":
            if registration is None:
                raise ValueError(f"provider SERP live desconhecido: {config.provider}")
            if not (os.environ.get(registration.key_env) or "").strip():
                raise ValueError(
                    f"{registration.key_env} não configurada; obtenha a chave em {registration.credential_url}"
                )

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


def configure_perplexity_search(state: SearchConsoleState) -> None:
    """Collect execution-scoped Perplexity external-research input."""

    status = perplexity_configuration_status()
    key_state = "[SET]" if status["configured"] else "<não definida>"
    print("\nSEARCH INTELLIGENCE / PERPLEXITY")
    print(
        "Esta superfície é pesquisa externa com provenance própria; não substitui SERP "
        "observada e não altera scoring, SARI, CATs ou evidência determinística."
    )
    print(
        f"Provider: Perplexity | surface=SEARCH_API | "
        f"{PERPLEXITY_API_KEY_ENV}={key_state}"
    )
    print(
        f"Limite desta integração: até {PERPLEXITY_MAX_QUERIES} queries por request; "
        "WEB e FAST usam a mesma estrutura de resposta."
    )

    try:
        enabled = _yes_no(
            "Executar pesquisa externa Perplexity após a auditoria?",
            bool(state.perplexity_queries),
        )
        if not enabled:
            state.perplexity_queries = ()
            state.perplexity_last_status = "NOT_REQUESTED"
            state.perplexity_last_detail = ""
            state.perplexity_last_duration_seconds = None
            state.error = ""
            return

        current = "; ".join(state.perplexity_queries)
        raw = input(
            "Query(s) Perplexity; separe múltiplas por ';'"
            + (f" [{current}]" if current else "")
            + ": "
        ).strip()
        queries = parse_search_terms(raw) if raw else state.perplexity_queries
        if not queries:
            raise ValueError("informe pelo menos uma query Perplexity")
        if len(queries) > PERPLEXITY_MAX_QUERIES:
            raise ValueError(
                f"a Search API aceita no máximo {PERPLEXITY_MAX_QUERIES} queries por request"
            )
        state.perplexity_queries = queries

        current_type = (
            state.perplexity_search_type
            if state.perplexity_search_type in {"web", "fast"}
            else "web"
        )
        raw_type = input(
            f"Tipo de busca Perplexity [web/fast] [{current_type}]: "
        ).strip().casefold()
        search_type = current_type if not raw_type else raw_type
        if search_type not in {"web", "fast"}:
            raise ValueError("tipo Perplexity deve ser web ou fast")
        state.perplexity_search_type = search_type
        state.perplexity_last_status = "PENDING"
        state.perplexity_last_detail = (
            f"{len(queries)} query(s); Search API {search_type.upper()}; "
            + ("credencial configurada" if status["configured"] else "credencial não configurada")
        )
        state.error = ""
    except (TypeError, ValueError) as exc:
        state.error = f"Perplexity Search Intelligence: {exc}"


def perplexity_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Explicit opt-out; an absent flag preserves compatibility for configured credentials."""
    values = os.environ if env is None else env
    raw = str(values.get("RASAI_PERPLEXITY_ENABLED", "") or "").strip().casefold()
    if not raw:
        return True  # Historical compatibility; no query is created automatically.
    # Malformed overrides may never trigger billable requests.
    return raw in {"true", "1", "on", "yes"}


def validate_perplexity_readiness(
    state: object, env: Mapping[str, str] | None = None
) -> tuple[bool, str]:
    queries = tuple(getattr(state, "perplexity_queries", ()) or ())
    if not queries:
        return True, "Perplexity não solicitada nesta execução"
    if not perplexity_enabled(env):
        values = os.environ if env is None else env
        raw = str(values.get("RASAI_PERPLEXITY_ENABLED", "") or "").strip().casefold()
        if raw not in {"false", "0", "off", "no"}:
            return True, "RASAI_PERPLEXITY_ENABLED inválida; nenhuma chamada externa por segurança"
        return True, "Perplexity desabilitada pelo usuário; nenhuma chamada externa"
    if len(queries) > PERPLEXITY_MAX_QUERIES:
        return False, f"Perplexity excede {PERPLEXITY_MAX_QUERIES} queries por request"
    search_type = str(getattr(state, "perplexity_search_type", "web") or "web").casefold()
    if search_type not in {"web", "fast"}:
        return False, "Perplexity search_type inválido"
    try:
        from rasai.search_intelligence.perplexity_request_policy import resolve_request_options
        resolve_request_options(
            env, explicit_brazil=_explicit_brazil_scope(
                str(getattr(state, "search_region", "") or "")
            ), search_type=search_type,
        )
    except ValueError as exc:
        return False, f"Configuração de escopo Perplexity inválida: {exc}"
    configured = perplexity_configuration_status(env)["configured"]
    suffix = "configurada" if configured else "não configurada; execução será contida como limitação externa"
    return True, (
        f"Perplexity Search API: {len(queries)} query(s), {search_type.upper()}, {suffix}"
    )


def execute_perplexity_for_audit(
    state: SearchConsoleState,
    *,
    runner: Callable[..., object] | None = None,
) -> int:
    """Run isolated external research after the deterministic audit; always fail open."""

    queries = tuple(getattr(state, "perplexity_queries", ()) or ())
    if not queries:
        return 0
    if not perplexity_enabled():
        state.perplexity_last_status = "DISABLED_BY_USER"
        state.perplexity_last_detail = "Perplexity desabilitada pelo usuário; nenhuma chamada ou custo"
        state.perplexity_last_duration_seconds = None
        return 0
    optional_ready, optional_reason = validate_perplexity_readiness(state)
    if not optional_ready:
        # An invalid *optional* query contract must never create a paid request
        # or prevent deterministic collection, canonical AI, or persistence.
        state.perplexity_last_status = "COMPLETE_WITH_LIMITATIONS"
        state.perplexity_last_detail = "Pesquisa Perplexity não executada: " + optional_reason
        state.perplexity_last_duration_seconds = None
        return 1
    workspace_path = audit_workspace(state)
    if workspace_path is None:
        state.perplexity_last_status = "UNAVAILABLE"
        state.perplexity_last_detail = "workspace AUD da sessão não encontrado"
        return 1

    audit_id = str(getattr(state, "audit_id", "") or "").strip()
    if not audit_id:
        state.perplexity_last_status = "UNAVAILABLE"
        state.perplexity_last_detail = "audit_id da sessão não encontrado"
        return 1

    effective_runner = execute_perplexity_search if runner is None else runner
    started = time.monotonic()
    try:
        # Match the SERP geographic intent where explicitly configured.
        # A ccTLD is not a country detector; Perplexity's country/language
        # filters are best-effort provider constraints, not guaranteed BR-only.
        brazil_scope = _explicit_brazil_scope(
            str(getattr(state, "search_region", "") or "")
        )
        search_kwargs = {
            "audit_id": audit_id,
            "query": queries,
            "search_type": str(getattr(state, "perplexity_search_type", "web") or "web"),
        }
        if runner is None:
            # Effective AUD scope takes priority over integration overrides.
            # The adapter validates the same policy again before any POST.
            from rasai.search_intelligence.perplexity_request_policy import resolve_request_options
            search_kwargs["search_options"] = resolve_request_options(
                explicit_brazil=brazil_scope,
                search_type=search_kwargs["search_type"],
            )
        result = effective_runner(AuditWorkspace.open(workspace_path), **search_kwargs)
        summary = humanized_perplexity_summary(result)
        state.perplexity_last_duration_seconds = max(time.monotonic() - started, 0.0)
        state.perplexity_last_status = (
            "COMPLETE" if str(result.status) == "SUCCESS" else "COMPLETE_WITH_LIMITATIONS"
        )
        state.perplexity_last_detail = (
            f"{summary['origem']} | modo={summary['modo']} | "
            f"queries={summary['consultas']} | requests={summary['requests']} | "
            f"fontes={summary['fontes']} | custo={summary['custo']} | status={summary['status']}"
        )
        # Additive snapshot and canonical re-projection follow the optional
        # search. They never invoke any collector/provider or change scoring.
        if str(result.status) == "SUCCESS":
            try:
                from rasai.geo_observation import materialize_geo_observation
                from rasai.report_completion import materialize_catalog_report_projection
                workspace = AuditWorkspace.open(workspace_path)
                materialize_geo_observation(Path(workspace.database), audit_id)
                if bool(getattr(state, "geo_ai_requested", False)):
                    try:
                        from rasai.geo_ai import execute_geo_ai
                        ai_state = execute_geo_ai(
                            Path(workspace.database),
                            audit_id,
                            provider_selection=str(getattr(state, "ai_provider", "none")),
                        )
                        state.perplexity_last_detail += f" | GEO IA: {ai_state}"
                    except Exception as ai_exc:
                        state.perplexity_last_detail += (
                            f" | GEO IA indisponível: {type(ai_exc).__name__}"
                        )
                if (Path(workspace.root) / "report-catalog").exists():
                    completion = materialize_catalog_report_projection(
                        audit_id=audit_id, workspace=workspace
                    )
                    if completion.renderer_errors:
                        state.perplexity_last_detail += " | GEO: relatório pendente de atualização"
            except Exception as exc:
                state.perplexity_last_detail += f" | GEO advisory indisponível: {type(exc).__name__}"
        return 0 if str(result.status) == "SUCCESS" else 1
    except Exception as exc:
        # Last-resort isolation of optional integration failures, including
        # provider adapters or their own provenance writer. Never propagate
        # to the already-finished AUD or its independent AI/SERP pipelines.
        state.perplexity_last_duration_seconds = max(time.monotonic() - started, 0.0)
        state.perplexity_last_status = "COMPLETE_WITH_LIMITATIONS"
        state.perplexity_last_detail = f"Perplexity indisponível/ inválida: {type(exc).__name__}"
        return 1


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
    state.search_last_duration_seconds = duration
    state.search_last_report = ""
    diagnostic_lines = [
        line.strip() for line in output.getvalue().splitlines() if line.strip()
    ]
    diagnostic = diagnostic_lines[-1] if diagnostic_lines else ""

    if code == 0:
        state.search_last_status = "COMPLETE"
        state.search_last_detail = (
            f"{len(state.search_queries)} termo(s) observados; duração={duration:.1f}s"
        )
        return 0

    state.search_last_status = "COMPLETE_WITH_LIMITATIONS"
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
            registration = _provider_registration(config.provider)
            if registration is None:
                provider = f"{config.provider}/unknown"
            else:
                provider = f"{registration.id}/{registration.engine}"
        except ValueError:
            provider = "configuração inválida"
        status = (
            f"{len(queries)} termo(s) | {provider} | "
            f"{state.search_device} | depth={state.search_depth} | {preview}"
        )
    else:
        mode = (os.environ.get("RASAI_SERP_MODE") or "disabled").strip().casefold()
        status = f"sem termos nesta execução | provider mode={mode}"
    perplexity_queries = tuple(getattr(state, "perplexity_queries", ()) or ())
    px_status = perplexity_configuration_status()
    px_mode = str(getattr(state, "perplexity_search_type", "web") or "web").upper()
    if perplexity_queries:
        px_preview = "; ".join(perplexity_queries[:2])
        if len(perplexity_queries) > 2:
            px_preview += f"; +{len(perplexity_queries) - 2}"
        perplexity_line = (
            f"{len(perplexity_queries)} query(s) | {px_mode} | "
            f"{'configurada' if px_status['configured'] else 'não configurada'} | {px_preview}"
        )
    else:
        perplexity_line = (
            "não solicitado | "
            + ("credencial configurada" if px_status["configured"] else "credencial não configurada")
        )

    print("\nSEARCH INTELLIGENCE")
    print(f"T. Termos SERP            : {status}")
    print(f"U. Perplexity externa     : {perplexity_line}")
    print("   Termos são transitórios da sessão; credenciais/provider/limites continuam em E.")


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
        if choice == "U":
            configure_perplexity_search(state)
            return
        original_configure(state, choice)

    def readiness(state: SearchConsoleState) -> tuple[bool, str]:
        ready, reason = original_readiness(state)
        if not ready:
            return ready, reason
        search_ready, search_reason = validate_search_readiness(state)
        if not search_ready:
            return False, search_reason
        # The Perplexity request is advisory and independent of the AUD gate.
        # A malformed optional query is reported, not allowed to cancel the AUD.
        try:
            perplexity_ready, perplexity_reason = validate_perplexity_readiness(state)
        except Exception as exc:
            perplexity_ready = False
            perplexity_reason = f"validação Perplexity indisponível: {type(exc).__name__}"
        details = [reason]
        if state.search_queries:
            details.append(search_reason)
        if state.perplexity_queries:
            details.append(
                perplexity_reason if perplexity_ready
                else "Perplexity opcional não será executada: " + perplexity_reason
            )
        return True, "; ".join(item for item in details if item)

    def run(state: SearchConsoleState) -> int:
        code = int(original_run(state) or 0)
        if code != 0:
            return code

        previous_status = state.status
        any_limitation = False

        if state.search_queries:
            try:
                targets = console_module.preflight(state)
                target_url = targets[0]
            except (OSError, ValueError, UnicodeError) as exc:
                state.search_last_status = "COMPLETE_WITH_LIMITATIONS"
                state.search_last_detail = f"não foi possível resolver o domínio pós-auditoria: {exc}"
                any_limitation = True
            else:
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
                if execute_search_for_audit(state, target_url=target_url) != 0:
                    any_limitation = True

        if state.perplexity_queries:
            state.status = "SEARCH_INTELLIGENCE"
            state.operation = "API:PERPLEXITY_SEARCH"
            try:
                console_module.render_header(state)
                print(
                    f"Perplexity Search Intelligence: consultando "
                    f"{len(state.perplexity_queries)} query(s) como pesquisa externa..."
                )
            except Exception:
                pass
            # Perplexity is optional advisory enrichment. Contain even an
            # unexpected adapter exception so the AUD status and canonical
            # collection/AI/persistence results remain unchanged.
            try:
                execute_perplexity_for_audit(state)
            except Exception as exc:
                state.perplexity_last_status = "COMPLETE_WITH_LIMITATIONS"
                state.perplexity_last_detail = (
                    f"Perplexity opcional indisponível: {type(exc).__name__}"
                )
                state.perplexity_last_duration_seconds = None

        if any_limitation:
            state.status = "COMPLETE_WITH_LIMITATIONS"
            state.operation = "INTEGRATION:SEARCH_INTELLIGENCE_LIMITATION"
        else:
            state.status = previous_status
            state.operation = "LOCAL:DONE"
        return code

    def usage(state: SearchConsoleState) -> None:
        original_usage(state)
        # This block describes accumulated persisted coverage of the current AUD, not
        # merely what the latest RPR selected. Re-project Search Intelligence from
        # fulfillment so a preserved prior SUCCESS does not appear as NOT_REQUESTED.
        if str(getattr(state, "audit_id", "") or "").strip():
            try:
                from rasai.console_governed_search_runtime import _project_result

                _project_result(state)
            except (OSError, ValueError, RuntimeError, sqlite3.Error):
                pass
        queries = tuple(getattr(state, "search_queries", ()) or ())
        if not queries and state.search_last_status == "NOT_REQUESTED":
            print("Search Intelligence   : não solicitado nesta sessão")
        else:
            print(
                f"Search Intelligence   : {state.search_last_status} | "
                f"termos={len(queries)}"
            )
            if state.search_last_detail:
                print(f"Detalhe Search       : {state.search_last_detail}")
            if state.search_last_report:
                print(f"Relatório Search     : {state.search_last_report}")

        perplexity_queries = tuple(getattr(state, "perplexity_queries", ()) or ())
        if not perplexity_queries and state.perplexity_last_status == "NOT_REQUESTED":
            print("Perplexity externa    : não solicitada nesta sessão")
        else:
            print(
                f"Perplexity externa    : {state.perplexity_last_status} | "
                f"queries={len(perplexity_queries)} | "
                f"modo={state.perplexity_search_type.upper()}"
            )
            if state.perplexity_last_detail:
                print(f"Detalhe Perplexity   : {state.perplexity_last_detail}")

    console_module._menu = menu
    console_module._configure = configure
    console_module._execution_readiness = readiness
    console_module.run_audit_from_console = run
    console_module._render_actual_usage = usage
    console_module._search_intelligence_console_installed = True
