"""Network-layer evidence for external integration diagnostics.

The feature is intentionally advisory. It diagnoses where communication stopped (DNS,
TCP, TLS or HTTP) without changing audit retries, provider routing, quarantine, scoring,
execution eligibility or reprocessing. Low-level retries never repeat a billable/provider
API operation; they only test transport layers after an inconclusive network failure.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import ssl
import time
from types import ModuleType
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit
from urllib.request import getproxies

from rasai import integration_diagnostics as diagnostics
from rasai.console_confirmation_contract import confirm_continue
from rasai.provider_registry import get_provider_registration, provider_registrations
from rasai.runtime_paths import runtime_directory


FORMAT_VERSION = "RASAI-INTEGRATION-NETWORK-001"
STORE_FILENAME = "integration-network-diagnostics.json"
CONTROL_ENDPOINT = "https://example.com"
DEFAULT_ATTEMPTS = 3
_RETRY_DELAYS_SECONDS = (0.0, 0.20, 0.50)

NETWORK_PATH_OK = "NETWORK_PATH_OK"
NETWORK_PATH_OK_AFTER_RETRY = "NETWORK_PATH_OK_AFTER_RETRY"
DNS_DESTINATION_FAILURE = "DNS_DESTINATION_FAILURE"
NETWORK_DESTINATION_UNREACHABLE = "NETWORK_DESTINATION_UNREACHABLE"
TLS_INTERCEPTION_OR_POLICY = "TLS_INTERCEPTION_OR_POLICY"
TLS_DESTINATION_FAILURE = "TLS_DESTINATION_FAILURE"
NETWORK_GENERAL_OR_LOCAL_FAILURE = "NETWORK_GENERAL_OR_LOCAL_FAILURE"
NETWORK_INCONCLUSIVE_PROXY_OR_VPN = "NETWORK_INCONCLUSIVE_PROXY_OR_VPN"
HTTP_PATH_INCONCLUSIVE = "HTTP_PATH_INCONCLUSIVE"
NETWORK_NOT_TESTED = "NETWORK_NOT_TESTED"

Resolver = Callable[..., Any]
Connector = Callable[..., Any]
ContextFactory = Callable[[], Any]


@dataclass(frozen=True, slots=True)
class _LayerProbe:
    endpoint: str
    host: str
    port: int
    dns_status: str
    tcp_status: str
    tls_status: str
    attempt_count: int
    latencies_ms: tuple[int, ...]
    error_code: str = ""
    error_detail: str = ""

    @property
    def ok(self) -> bool:
        return self.dns_status == self.tcp_status == self.tls_status == "OK"


@dataclass(frozen=True, slots=True)
class NetworkAssessment:
    integration_id: str
    checked_at: str
    endpoint: str
    host: str
    port: int
    dns_status: str
    tcp_status: str
    tls_status: str
    http_status: int | None
    attempt_count: int
    latencies_ms: tuple[int, ...]
    classification: str
    error_code: str
    error_detail: str
    control_host: str = ""
    control_status: str = "NOT_USED"
    proxy_configured: bool = False
    inferred_from_http: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NetworkAssessment":
        latencies: list[int] = []
        for value in payload.get("latencies_ms") or ():
            try:
                latencies.append(max(0, int(value)))
            except (TypeError, ValueError):
                continue
        try:
            http_status = None if payload.get("http_status") is None else int(payload.get("http_status"))
        except (TypeError, ValueError):
            http_status = None
        try:
            port = int(payload.get("port") or 443)
        except (TypeError, ValueError):
            port = 443
        try:
            attempt_count = max(0, int(payload.get("attempt_count") or 0))
        except (TypeError, ValueError):
            attempt_count = 0
        return cls(
            integration_id=str(payload.get("integration_id") or ""),
            checked_at=str(payload.get("checked_at") or ""),
            endpoint=str(payload.get("endpoint") or ""),
            host=str(payload.get("host") or ""),
            port=port,
            dns_status=str(payload.get("dns_status") or "NOT_TESTED"),
            tcp_status=str(payload.get("tcp_status") or "NOT_TESTED"),
            tls_status=str(payload.get("tls_status") or "NOT_TESTED"),
            http_status=http_status,
            attempt_count=attempt_count,
            latencies_ms=tuple(latencies),
            classification=str(payload.get("classification") or NETWORK_NOT_TESTED),
            error_code=str(payload.get("error_code") or ""),
            error_detail=str(payload.get("error_detail") or ""),
            control_host=str(payload.get("control_host") or ""),
            control_status=str(payload.get("control_status") or "NOT_USED"),
            proxy_configured=bool(payload.get("proxy_configured", False)),
            inferred_from_http=bool(payload.get("inferred_from_http", False)),
        )


def store_path(audits_root: str | Path) -> Path:
    return runtime_directory(audits_root) / STORE_FILENAME


def load_network_assessments(audits_root: str | Path) -> dict[str, NetworkAssessment]:
    path = store_path(audits_root)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, Mapping) or payload.get("format_version") != FORMAT_VERSION:
        return {}
    rows = payload.get("results")
    if not isinstance(rows, Mapping):
        return {}
    output: dict[str, NetworkAssessment] = {}
    for key, value in rows.items():
        if not isinstance(value, Mapping):
            continue
        row = NetworkAssessment.from_dict(value)
        if row.integration_id:
            output[str(key)] = row
    return output


def save_network_assessment(audits_root: str | Path, assessment: NetworkAssessment) -> Path:
    path = store_path(audits_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_network_assessments(audits_root)
    current[assessment.integration_id] = assessment
    payload = {
        "format_version": FORMAT_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "results": {key: value.to_dict() for key, value in sorted(current.items())},
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def _safe_endpoint(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if not parsed.scheme or not parsed.hostname:
        return ""
    host = parsed.hostname
    if parsed.port:
        host += f":{parsed.port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme, host, path, "", ""))


def endpoint_for_spec(spec: diagnostics.IntegrationSpec, env: Mapping[str, str] | None = None) -> str:
    environment = os.environ if env is None else env
    if spec.id.startswith("ai:"):
        provider = str(spec.provider_id or "")
        if provider == "copilot":
            # GitHub token validation uses api.github.com, but Copilot runtime traffic
            # reaches a distinct host. Test that path without creating a chat session.
            return "https://api.githubcopilot.com/_ping"
        registration = get_provider_registration(provider)
        if registration is not None and registration.endpoint_env:
            override = str(environment.get(registration.endpoint_env) or "").strip()
            if override:
                return _safe_endpoint(override)
        return {
            "openai": "https://api.openai.com/v1/models",
            "deepseek": "https://api.deepseek.com/models",
            "mimo": "https://api.xiaomimimo.com/v1/models",
            "xai": "https://api.x.ai/v1/models",
            "qwen": "https://dashscope-us.aliyuncs.com/compatible-mode/v1/models",
            "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
            "anthropic": "https://api.anthropic.com/v1/models",
        }.get(provider, "")
    if spec.id.startswith("serp:"):
        return {
            "serpapi": "https://serpapi.com/account.json",
            "serpapi-bing": "https://serpapi.com/account.json",
            "zenserp": "https://app.zenserp.com/api/v2/search",
            "scrapingdog": "https://api.scrapingdog.com/google/",
        }.get(str(spec.provider_id or ""), "")
    if spec.probe_kind == "PAGESPEED":
        return "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    if spec.probe_kind in {"CRUX", "CRUX_HISTORY"}:
        return "https://chromeuxreport.googleapis.com/"
    if spec.probe_kind == "GSC":
        return "https://www.googleapis.com/webmasters/v3/sites"
    if spec.probe_kind == "CLARITY":
        return "https://www.clarity.ms/export-data/api/v1/project-live-insights"
    if spec.probe_kind == "DYNATRACE":
        base = str(environment.get("RASAI_DYNATRACE_BASE_URL") or "").strip().rstrip("/")
        return _safe_endpoint(base + "/") if base else ""
    return ""


def _proxy_configured() -> bool:
    try:
        proxies = getproxies()
    except (OSError, ValueError):
        proxies = {}
    if proxies:
        return True
    return any(
        str(os.environ.get(name) or "").strip()
        for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")
    )


def _error_parts(exc: BaseException) -> tuple[str, str]:
    code = type(exc).__name__
    detail = str(exc).strip().replace("\r", " ").replace("\n", " ")[:240]
    return code, detail


def _probe_endpoint_layers(
    endpoint: str,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    timeout: float = 2.5,
    resolver: Resolver = socket.getaddrinfo,
    connector: Connector = socket.create_connection,
    context_factory: ContextFactory = ssl.create_default_context,
) -> _LayerProbe:
    parsed = urlsplit(endpoint)
    host = str(parsed.hostname or "").strip()
    port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
    if not host:
        return _LayerProbe(endpoint, "", port, "INVALID", "NOT_TESTED", "NOT_TESTED", 0, (), "INVALID_ENDPOINT", "endpoint sem host")

    latencies: list[int] = []
    dns_seen = False
    tcp_seen = False
    tls_seen = parsed.scheme != "https"
    last_code = ""
    last_detail = ""
    total_attempts = max(1, min(int(attempts), DEFAULT_ATTEMPTS))

    for index in range(total_attempts):
        if index and index < len(_RETRY_DELAYS_SECONDS):
            time.sleep(_RETRY_DELAYS_SECONDS[index])
        started = time.perf_counter()
        raw_socket = None
        wrapped_socket = None
        try:
            resolver(host, port, type=socket.SOCK_STREAM)
            dns_seen = True
        except (socket.gaierror, OSError) as exc:
            last_code, last_detail = _error_parts(exc)
            latencies.append(max(0, int((time.perf_counter() - started) * 1000)))
            continue
        try:
            raw_socket = connector((host, port), timeout=timeout)
            tcp_seen = True
        except (TimeoutError, socket.timeout, OSError) as exc:
            last_code, last_detail = _error_parts(exc)
            latencies.append(max(0, int((time.perf_counter() - started) * 1000)))
            continue
        try:
            if parsed.scheme == "https":
                wrapped_socket = context_factory().wrap_socket(raw_socket, server_hostname=host)
                tls_seen = True
            latencies.append(max(0, int((time.perf_counter() - started) * 1000)))
            return _LayerProbe(
                endpoint=endpoint,
                host=host,
                port=port,
                dns_status="OK",
                tcp_status="OK",
                tls_status="OK" if parsed.scheme == "https" else "N/A",
                attempt_count=index + 1,
                latencies_ms=tuple(latencies),
            )
        except (ssl.SSLCertVerificationError, ssl.SSLError, TimeoutError, socket.timeout, OSError) as exc:
            last_code, last_detail = _error_parts(exc)
            latencies.append(max(0, int((time.perf_counter() - started) * 1000)))
        finally:
            for candidate in (wrapped_socket, raw_socket):
                close = getattr(candidate, "close", None)
                if callable(close):
                    try:
                        close()
                    except OSError:
                        pass

    return _LayerProbe(
        endpoint=endpoint,
        host=host,
        port=port,
        dns_status="OK" if dns_seen else "FALHA",
        tcp_status="OK" if tcp_seen else ("NÃO ALCANÇADO" if not dns_seen else "FALHA"),
        tls_status=("OK" if tls_seen else ("NÃO ALCANÇADO" if not tcp_seen else "FALHA")),
        attempt_count=total_attempts,
        latencies_ms=tuple(latencies),
        error_code=last_code,
        error_detail=last_detail,
    )


def _looks_like_tls_interception(probe: _LayerProbe) -> bool:
    text = f"{probe.error_code} {probe.error_detail}".casefold()
    return any(token in text for token in (
        "certificateverify", "certificate verify", "self signed", "unknown ca",
        "unable to get local issuer", "hostname mismatch", "certificate_unknown",
    ))


def _classification_for_failure(target: _LayerProbe, control: _LayerProbe, *, proxy: bool) -> str:
    if proxy:
        return NETWORK_INCONCLUSIVE_PROXY_OR_VPN
    if not control.ok:
        return NETWORK_GENERAL_OR_LOCAL_FAILURE
    if target.dns_status != "OK":
        return DNS_DESTINATION_FAILURE
    if target.tcp_status != "OK":
        return NETWORK_DESTINATION_UNREACHABLE
    if target.tls_status != "OK":
        return TLS_INTERCEPTION_OR_POLICY if _looks_like_tls_interception(target) else TLS_DESTINATION_FAILURE
    return HTTP_PATH_INCONCLUSIVE


def assess_network(
    spec: diagnostics.IntegrationSpec,
    result: diagnostics.IntegrationDiagnostic,
    *,
    env: Mapping[str, str] | None = None,
    attempts: int = DEFAULT_ATTEMPTS,
    layer_probe: Callable[..., _LayerProbe] = _probe_endpoint_layers,
) -> NetworkAssessment:
    endpoint = endpoint_for_spec(spec, env)
    checked = datetime.now(timezone.utc).isoformat()
    if not endpoint:
        return NetworkAssessment(
            spec.id, checked, "", "", 443, "NOT_TESTED", "NOT_TESTED", "NOT_TESTED",
            result.http_status, 0, (), NETWORK_NOT_TESTED, "NO_ENDPOINT", "sem endpoint de rede registrado",
        )
    parsed = urlsplit(endpoint)
    host = str(parsed.hostname or "")
    port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
    proxy = _proxy_configured()
    separate_runtime_path = spec.id == "ai:copilot"

    # Any real HTTP response proves that DNS/transport/TLS were good enough for the
    # actual probe path. Do not add redundant sockets. Copilot is the exception because
    # authentication is checked on api.github.com while runtime traffic uses a distinct
    # Copilot host that may be filtered independently by VPN/firewall policy.
    if result.http_status is not None and not separate_runtime_path:
        return NetworkAssessment(
            spec.id, checked, endpoint, host, port, "OK", "OK", "OK", result.http_status,
            1, (() if result.latency_ms is None else (result.latency_ms,)), NETWORK_PATH_OK,
            "", "caminho inferido pela resposta HTTP real do serviço", proxy_configured=proxy,
            inferred_from_http=True,
        )

    should_probe_layers = separate_runtime_path or (
        result.status == diagnostics.STATUS_TRANSIENT_FAILURE
        and result.http_status is None
        and result.category in {"TIMEOUT", "NETWORK"}
    )
    if not should_probe_layers:
        return NetworkAssessment(
            spec.id, checked, endpoint, host, port, "NOT_TESTED", "NOT_TESTED", "NOT_TESTED",
            result.http_status, 0, (), NETWORK_NOT_TESTED, "NOT_REQUIRED",
            "o resultado não exige diagnóstico adicional de transporte", proxy_configured=proxy,
        )

    target = layer_probe(endpoint, attempts=attempts)
    if target.ok:
        classification = NETWORK_PATH_OK_AFTER_RETRY if target.attempt_count > 1 else (
            NETWORK_PATH_OK if separate_runtime_path else HTTP_PATH_INCONCLUSIVE
        )
        detail = (
            "o host de runtime do Copilot concluiu DNS/TCP/TLS sem criar sessão nem enviar prompt"
            if separate_runtime_path
            else "DNS/TCP/TLS concluíram; o timeout/falha ocorreu acima da camada de transporte"
        )
        return NetworkAssessment(
            spec.id, checked, endpoint, target.host, target.port, target.dns_status, target.tcp_status,
            target.tls_status, result.http_status, target.attempt_count, target.latencies_ms,
            classification, target.error_code, detail, proxy_configured=proxy,
        )

    control = layer_probe(CONTROL_ENDPOINT, attempts=min(2, attempts))
    classification = _classification_for_failure(target, control, proxy=proxy)
    return NetworkAssessment(
        spec.id, checked, endpoint, target.host, target.port, target.dns_status, target.tcp_status,
        target.tls_status, result.http_status, target.attempt_count, target.latencies_ms,
        classification, target.error_code, target.error_detail,
        control_host=control.host, control_status="OK" if control.ok else "FALHA",
        proxy_configured=proxy,
    )


def _truthy(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on", "sim", "s"}


def _relevant_spec_ids_for_state(state: Any) -> tuple[str, ...]:
    ids: list[str] = []
    provider = str(getattr(state, "ai_provider", "none") or "none").strip().casefold()
    if provider == "auto":
        for registration in provider_registrations():
            spec = diagnostics.get_integration_spec(f"ai:{registration.id}")
            if spec is not None and not diagnostics.missing_dependencies(spec):
                ids.append(spec.id)
    elif provider not in {"", "none"}:
        ids.append(f"ai:{provider}")

    if bool(getattr(state, "web_performance", False)):
        ids.append("service:pagespeed")
        if str(getattr(state, "field_source", "auto") or "auto").casefold() in {"auto", "crux"}:
            ids.append("service:crux")

    queries = tuple(getattr(state, "search_queries", ()) or ())
    if queries:
        serp_provider = str(os.environ.get("RASAI_SERP_PROVIDER") or "").strip().casefold()
        if serp_provider:
            ids.append(f"serp:{serp_provider}")

    for spec in diagnostics.integration_specs():
        if not spec.id.startswith("service:") or spec.id in {"service:pagespeed", "service:crux", "service:crux-history", "service:dynatrace"}:
            continue
        if spec.related_envs and _truthy(os.environ.get(spec.related_envs[0])):
            ids.append(spec.id)
    if bool(getattr(state, "apdex_dynatrace_import", False)):
        ids.append("service:dynatrace")
    return tuple(dict.fromkeys(ids))


def _relevant_spec_ids_for_audit(state: Any, audit_id: str) -> tuple[str, ...]:
    try:
        from rasai.audit_configuration_reuse import KIND_CONSOLE, load_reusable_audit_configuration
        source = load_reusable_audit_configuration(state.audits_root, audit_id, expected_kind=KIND_CONSOLE)
    except (FileNotFoundError, OSError, ValueError):
        return ()
    configuration = source.configuration
    settings = configuration.get("settings") if isinstance(configuration, Mapping) else None
    if not isinstance(settings, Mapping):
        return ()
    ids: list[str] = []
    ai = settings.get("ai")
    if isinstance(ai, Mapping):
        provider = str(ai.get("provider") or "none").strip().casefold()
        if provider == "auto":
            for registration in provider_registrations():
                spec = diagnostics.get_integration_spec(f"ai:{registration.id}")
                if spec is not None and not diagnostics.missing_dependencies(spec):
                    ids.append(spec.id)
        elif provider not in {"", "none"}:
            ids.append(f"ai:{provider}")
    web = settings.get("web_performance")
    if isinstance(web, Mapping) and _truthy(web.get("enabled")):
        ids.append("service:pagespeed")
        if str(web.get("field_source") or "auto").casefold() in {"auto", "crux"}:
            ids.append("service:crux")
    search = configuration.get("search_intelligence") if isinstance(configuration, Mapping) else None
    if isinstance(search, Mapping) and _truthy(search.get("enabled")):
        provider = str(os.environ.get("RASAI_SERP_PROVIDER") or "").strip().casefold()
        if provider:
            ids.append(f"serp:{provider}")
    environment = settings.get("environment")
    if isinstance(environment, Mapping):
        for spec in diagnostics.integration_specs():
            if spec.id.startswith("service:") and spec.related_envs and _truthy(environment.get(spec.related_envs[0])):
                ids.append(spec.id)
    return tuple(dict.fromkeys(ids))


def _warning_rows(state: Any, integration_ids: tuple[str, ...]) -> tuple[tuple[diagnostics.IntegrationSpec, diagnostics.IntegrationDiagnostic, NetworkAssessment | None, str], ...]:
    results = diagnostics.load_diagnostics(state.audits_root)
    networks = load_network_assessments(state.audits_root)
    rows: list[tuple[diagnostics.IntegrationSpec, diagnostics.IntegrationDiagnostic, NetworkAssessment | None, str]] = []
    for integration_id in integration_ids:
        spec = diagnostics.get_integration_spec(integration_id)
        result = results.get(integration_id)
        if spec is None or result is None:
            continue
        currency = diagnostics.result_currency(spec, result)
        if currency == "CONFIG_CHANGED":
            continue
        network = networks.get(integration_id)
        network_problem = network is not None and network.classification not in {
            NETWORK_PATH_OK, NETWORK_PATH_OK_AFTER_RETRY, NETWORK_NOT_TESTED,
        }
        result_problem = result.status not in {
            diagnostics.STATUS_OPERATIONAL, diagnostics.STATUS_OPERATIONAL_LIMITED,
        }
        if result_problem or network_problem:
            rows.append((spec, result, network, currency))
    return tuple(rows)


def _network_label(classification: str) -> str:
    return {
        NETWORK_PATH_OK: "REDE OPERACIONAL",
        NETWORK_PATH_OK_AFTER_RETRY: "REDE OPERACIONAL APÓS RETENTATIVA",
        DNS_DESTINATION_FAILURE: "PROVÁVEL FALHA/BLOQUEIO DNS DO DESTINO",
        NETWORK_DESTINATION_UNREACHABLE: "PROVÁVEL BLOQUEIO/INACESSIBILIDADE DO DESTINO",
        TLS_INTERCEPTION_OR_POLICY: "PROVÁVEL INSPEÇÃO TLS/PROXY/POLÍTICA",
        TLS_DESTINATION_FAILURE: "FALHA TLS DO DESTINO",
        NETWORK_GENERAL_OR_LOCAL_FAILURE: "PROVÁVEL FALHA DE CONECTIVIDADE LOCAL/GERAL",
        NETWORK_INCONCLUSIVE_PROXY_OR_VPN: "INCONCLUSIVO — PROXY/VPN PODE ALTERAR A ROTA",
        HTTP_PATH_INCONCLUSIVE: "TRANSPORTE OK; FALHA ACIMA DE TLS/HTTP",
        NETWORK_NOT_TESTED: "REDE NÃO TESTADA",
    }.get(classification, classification.replace("_", " "))


def _confirm_warning(console_module: ModuleType, state: Any, rows: tuple[Any, ...], *, context: str) -> bool:
    if not rows:
        return True
    from rasai.console_ui import DIM, RED, YELLOW, paint

    console_module.render_header(state)
    print(paint("ATENÇÃO — DIAGNÓSTICO ANTERIOR DE INTEGRAÇÃO", RED, bold=True))
    print(f"Contexto: {context}")
    print("Há serviço(s) desta operação com diagnóstico anterior problemático usando a mesma configuração atual.\n")
    for spec, result, network, currency in rows:
        print(f"- {spec.label}")
        print(f"  Testado em    : {result.checked_at}")
        print(f"  Estado API    : {result.status} / {result.category}")
        if network is not None:
            print(f"  Rede          : {_network_label(network.classification)}")
            print(f"  DNS/TCP/TLS   : {network.dns_status} / {network.tcp_status} / {network.tls_status}")
        if currency == "STALE":
            print(paint("  Observação    : diagnóstico antigo; serve somente como alerta histórico.", YELLOW))
    print(paint("\nO alerta é consultivo. Ele não prova que a falha continua ocorrendo e não altera retry/quarentena do runtime.", DIM))
    return confirm_continue(
        "Continuar mesmo assim",
        back_label="Voltar sem executar",
    )


def _render_network_assessment(assessment: NetworkAssessment | None) -> None:
    if assessment is None:
        return
    from rasai.console_ui import DIM, GREEN, RED, YELLOW, paint

    ok = assessment.classification in {NETWORK_PATH_OK, NETWORK_PATH_OK_AFTER_RETRY}
    inconclusive = assessment.classification in {HTTP_PATH_INCONCLUSIVE, NETWORK_INCONCLUSIVE_PROXY_OR_VPN, NETWORK_NOT_TESTED}
    color = GREEN if ok else YELLOW if inconclusive else RED
    print("\nREDE / CONECTIVIDADE")
    print(f"Endpoint     : {assessment.host or '<não aplicável>'}:{assessment.port}")
    print(f"DNS          : {assessment.dns_status}")
    print(f"TCP {assessment.port:<5} : {assessment.tcp_status}")
    print(f"TLS          : {assessment.tls_status}")
    if assessment.http_status is not None:
        print(f"HTTP         : {assessment.http_status}")
    print(f"Tentativas   : {assessment.attempt_count}")
    if assessment.latencies_ms:
        print("Latências    : " + " / ".join(f"{value} ms" for value in assessment.latencies_ms))
    print("Classificação: " + paint(_network_label(assessment.classification), color, bold=True))
    if assessment.control_host:
        print(f"Controle     : {assessment.control_host} = {assessment.control_status}")
    if assessment.proxy_configured:
        print(paint("Proxy detectado no ambiente; uma VPN/proxy pode alterar a rota e limitar a certeza do diagnóstico direto.", YELLOW))
    if assessment.error_detail:
        print(paint(f"Detalhe      : {assessment.error_code}: {assessment.error_detail}", DIM))


def install(console_module: ModuleType) -> None:
    """Install network evidence and advisory warnings on the final console surfaces."""
    if getattr(console_module, "_rasai_integration_network_diagnostics", False):
        return
    from rasai import console_navigation
    from rasai import integration_diagnostics_console as diagnostic_console

    active_root: dict[str, str] = {"value": ""}
    original_detail = diagnostic_console._detail_menu
    original_render_result = diagnostic_console._render_result
    original_run_and_store = diagnostic_console._run_and_store

    def detail_with_root(module: ModuleType, state: Any, spec: diagnostics.IntegrationSpec) -> None:
        active_root["value"] = str(state.audits_root)
        original_detail(module, state, spec)

    def render_with_network(spec: diagnostics.IntegrationSpec, result: diagnostics.IntegrationDiagnostic | None) -> None:
        original_render_result(spec, result)
        root = active_root.get("value")
        assessment = load_network_assessments(root).get(spec.id) if root else None
        _render_network_assessment(assessment)

    def run_and_store_with_network(state: Any, spec: diagnostics.IntegrationSpec) -> diagnostics.IntegrationDiagnostic:
        result = original_run_and_store(state, spec)
        assessment = assess_network(spec, result)
        save_network_assessment(state.audits_root, assessment)
        active_root["value"] = str(state.audits_root)
        return result

    diagnostic_console._detail_menu = detail_with_root
    diagnostic_console._render_result = render_with_network
    diagnostic_console._run_and_store = run_and_store_with_network

    original_menu = console_module._menu

    def menu_with_execution_warning(state: Any) -> str:
        while True:
            choice = original_menu(state)
            if choice != "R":
                return choice
            try:
                ready, _ = console_module._execution_readiness(state)
            except (AttributeError, TypeError, ValueError):
                ready = True
            if not ready:
                return choice
            rows = _warning_rows(state, _relevant_spec_ids_for_state(state))
            if _confirm_warning(console_module, state, rows, context="processamento"):
                return choice
            state.status = "READY"
            state.operation = "LOCAL:INTEGRATION_WARNING_CANCELLED"
            state.error = "execução cancelada após alerta consultivo de integração"

    console_module._menu = menu_with_execution_warning

    original_reprocess = console_navigation._reprocess_selected

    def reprocess_with_warning(module: ModuleType, state: Any, audit_id: str) -> None:
        rows = _warning_rows(state, _relevant_spec_ids_for_audit(state, audit_id))
        if not _confirm_warning(module, state, rows, context=f"reprocessamento {audit_id}"):
            state.operation = "LOCAL:INTEGRATION_WARNING_CANCELLED"
            state.error = "reprocessamento cancelado após alerta consultivo de integração"
            return
        original_reprocess(module, state, audit_id)

    console_navigation._reprocess_selected = reprocess_with_warning
    console_module._rasai_integration_network_diagnostics = True
