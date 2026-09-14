"""Read-only diagnostics for external integrations used by RASAi.

The diagnostic layer is deliberately independent from audit execution.  It never changes
provider routing, quarantine, scoring, fulfillment or reprocessing.  Probes prefer
non-generative/non-billable authentication or catalog endpoints.  When a provider does
not expose a safe authentication probe, the result is explicitly limited rather than
spending credits merely to prove connectivity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from rasai.provider_registry import get_provider_registration, provider_registrations
from rasai.runtime_paths import runtime_directory
from rasai.search_intelligence.provider_catalog import SERP_PROVIDER_REGISTRY
from rasai.standards_service_registry import services as standards_services


FORMAT_VERSION = "RASAI-INTEGRATION-DIAGNOSTICS-001"
STORE_FILENAME = "integration-diagnostics.json"

STATUS_NOT_CONFIGURED = "NOT_CONFIGURED"
STATUS_OPERATIONAL = "OPERATIONAL"
STATUS_OPERATIONAL_LIMITED = "OPERATIONAL_LIMITED"
STATUS_CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
STATUS_AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
STATUS_AUTHORIZATION_ERROR = "AUTHORIZATION_ERROR"
STATUS_RESOURCE_ERROR = "RESOURCE_ERROR"
STATUS_QUOTA_OR_BILLING = "QUOTA_OR_BILLING"
STATUS_TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
STATUS_RASAI_ERROR = "RASAI_ERROR"

DETERMINISTIC_STATUSES = frozenset({
    STATUS_NOT_CONFIGURED,
    STATUS_CONFIGURATION_ERROR,
    STATUS_AUTHENTICATION_ERROR,
    STATUS_AUTHORIZATION_ERROR,
    STATUS_RESOURCE_ERROR,
    STATUS_QUOTA_OR_BILLING,
})
TRANSIENT_STATUSES = frozenset({STATUS_TRANSIENT_FAILURE})

PROBE_NO_GENERATION = "NO_GENERATION"
PROBE_NO_PROVIDER_FEE = "NO_PROVIDER_FEE"
PROBE_LIGHT_QUOTA = "LIGHT_QUOTA"
PROBE_SCARCE_QUOTA_AVOIDED = "SCARCE_QUOTA_AVOIDED"

JsonOpener = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class IntegrationDependency:
    name: str
    required: bool
    secret: bool
    purpose: str
    default: str | None = None


@dataclass(frozen=True, slots=True)
class IntegrationSpec:
    id: str
    label: str
    category: str
    probe_kind: str
    dependencies: tuple[IntegrationDependency, ...]
    related_envs: tuple[str, ...] = ()
    provider_id: str | None = None
    service_id: str | None = None
    probe_cost: str = PROBE_NO_PROVIDER_FEE
    safe_for_bulk: bool = True
    documentation_url: str = ""
    freshness_minutes: int = 60

    @property
    def environment_names(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*(item.name for item in self.dependencies), *self.related_envs)))


@dataclass(frozen=True, slots=True)
class IntegrationDiagnostic:
    integration_id: str
    label: str
    checked_at: str
    status: str
    category: str
    detail: str
    action: str
    configuration_fingerprint: str
    latency_ms: int | None = None
    http_status: int | None = None
    probe_cost: str = PROBE_NO_PROVIDER_FEE
    validated_facets: tuple[str, ...] = ()

    @property
    def transient(self) -> bool:
        return self.status in TRANSIENT_STATUSES

    @property
    def deterministic(self) -> bool:
        return self.status in DETERMINISTIC_STATUSES

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["transient"] = self.transient
        payload["deterministic"] = self.deterministic
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IntegrationDiagnostic":
        return cls(
            integration_id=str(payload.get("integration_id") or ""),
            label=str(payload.get("label") or ""),
            checked_at=str(payload.get("checked_at") or ""),
            status=str(payload.get("status") or STATUS_RASAI_ERROR),
            category=str(payload.get("category") or "UNKNOWN"),
            detail=str(payload.get("detail") or ""),
            action=str(payload.get("action") or ""),
            configuration_fingerprint=str(payload.get("configuration_fingerprint") or ""),
            latency_ms=_int_or_none(payload.get("latency_ms")),
            http_status=_int_or_none(payload.get("http_status")),
            probe_cost=str(payload.get("probe_cost") or PROBE_NO_PROVIDER_FEE),
            validated_facets=tuple(str(item) for item in (payload.get("validated_facets") or ())),
        )


@dataclass(frozen=True, slots=True)
class _HttpResult:
    status: int | None
    body: bytes
    latency_ms: int
    error_kind: str | None = None
    error_detail: str = ""


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dep(name: str, *, required: bool, secret: bool, purpose: str, default: str | None = None) -> IntegrationDependency:
    return IntegrationDependency(name=name, required=required, secret=secret, purpose=purpose, default=default)


def integration_specs() -> tuple[IntegrationSpec, ...]:
    """Return the diagnostics catalog derived from the canonical provider/service registries."""
    output: list[IntegrationSpec] = []

    for registration in provider_registrations():
        dependencies = [
            _dep(registration.key_env, required=True, secret=True, purpose="credencial usada pelo provider"),
            _dep(
                registration.model_env,
                required=False,
                secret=False,
                purpose="modelo efetivo; ausência usa o default do registry",
                default=registration.default_model,
            ),
        ]
        related: list[str] = []
        if registration.endpoint_env:
            dependencies.append(_dep(
                registration.endpoint_env,
                required=False,
                secret=False,
                purpose="endpoint avançado/proxy; ausência usa o endpoint oficial do adapter",
            ))
        if registration.reasoning_env:
            related.append(registration.reasoning_env)
        output.append(IntegrationSpec(
            id=f"ai:{registration.id}",
            label=registration.display_name,
            category="IA",
            probe_kind="AI_PROVIDER",
            dependencies=tuple(dependencies),
            related_envs=tuple(related),
            provider_id=registration.id,
            probe_cost=PROBE_NO_GENERATION,
            safe_for_bulk=True,
            documentation_url=registration.documentation_url,
            freshness_minutes=60,
        ))

    for registration in SERP_PROVIDER_REGISTRY:
        output.append(IntegrationSpec(
            id=f"serp:{registration.id}",
            label=registration.display_name,
            category="SERP / Search Intelligence",
            probe_kind="SERP_PROVIDER",
            dependencies=(
                _dep(registration.key_env, required=True, secret=True, purpose="credencial BYOK do provider SERP"),
            ),
            related_envs=("RASAI_SERP_MODE", "RASAI_SERP_PROVIDER"),
            provider_id=registration.id,
            probe_cost=PROBE_NO_PROVIDER_FEE,
            safe_for_bulk=True,
            documentation_url=registration.documentation_url,
            freshness_minutes=60,
        ))

    service_probe_kind = {
        "pagespeed": "PAGESPEED",
        "crux": "CRUX",
        "crux-history": "CRUX_HISTORY",
        "google-search-console": "GSC",
        "microsoft-clarity": "CLARITY",
    }
    for service in standards_services():
        if not service.credential_envs:
            continue
        probe_kind = service_probe_kind.get(service.id, "CONFIGURATION_ONLY")
        dependencies = tuple(
            _dep(name, required=True, secret=True, purpose="credencial exigida pelo serviço")
            for name in service.credential_envs
        ) + tuple(
            _dep(name, required=True, secret=False, purpose="contexto obrigatório do serviço")
            for name in service.config_envs
        )
        output.append(IntegrationSpec(
            id=f"service:{service.id}",
            label=service.label,
            category="Serviços externos",
            probe_kind=probe_kind,
            dependencies=dependencies,
            related_envs=(service.enabled_env,),
            service_id=service.id,
            probe_cost=(PROBE_SCARCE_QUOTA_AVOIDED if service.id == "microsoft-clarity" else PROBE_LIGHT_QUOTA),
            safe_for_bulk=service.id != "microsoft-clarity",
            documentation_url=service.documentation_url,
            freshness_minutes=30 if service.id == "google-search-console" else 60,
        ))

    output.append(IntegrationSpec(
        id="service:dynatrace",
        label="Dynatrace / calibração Apdex",
        category="Serviços externos",
        probe_kind="DYNATRACE",
        dependencies=(
            _dep("DYNATRACE_API_TOKEN", required=True, secret=True, purpose="token da Config API"),
            _dep("RASAI_DYNATRACE_BASE_URL", required=True, secret=False, purpose="URL HTTPS do ambiente Dynatrace"),
            _dep("RASAI_DYNATRACE_APPLICATION_ID", required=True, secret=False, purpose="application ID consultado pelo RASAi"),
        ),
        related_envs=("RASAI_APDEX_DYNATRACE_IMPORT", "RASAI_DYNATRACE_CONFIG_JSON"),
        probe_cost=PROBE_NO_PROVIDER_FEE,
        safe_for_bulk=True,
        documentation_url="https://docs.dynatrace.com/docs/dynatrace-api/basics/dynatrace-api-authentication",
        freshness_minutes=60,
    ))

    ids = [item.id for item in output]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate integration diagnostic id")
    return tuple(output)


def get_integration_spec(integration_id: str) -> IntegrationSpec | None:
    normalized = str(integration_id).strip().casefold()
    return next((item for item in integration_specs() if item.id.casefold() == normalized), None)


def configuration_fingerprint(spec: IntegrationSpec, env: Mapping[str, str] | None = None) -> str:
    environment = os.environ if env is None else env
    parts = [FORMAT_VERSION, spec.id]
    for name in spec.environment_names:
        value = str(environment.get(name) or "")
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""
        parts.append(f"{name}={digest}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def missing_dependencies(spec: IntegrationSpec, env: Mapping[str, str] | None = None) -> tuple[IntegrationDependency, ...]:
    environment = os.environ if env is None else env
    return tuple(item for item in spec.dependencies if item.required and not str(environment.get(item.name) or "").strip())


def store_path(audits_root: str | Path) -> Path:
    return runtime_directory(audits_root) / STORE_FILENAME


def load_diagnostics(audits_root: str | Path) -> dict[str, IntegrationDiagnostic]:
    path = store_path(audits_root)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("format_version") != FORMAT_VERSION:
        return {}
    rows = payload.get("results")
    if not isinstance(rows, dict):
        return {}
    output: dict[str, IntegrationDiagnostic] = {}
    for key, value in rows.items():
        if not isinstance(value, Mapping):
            continue
        result = IntegrationDiagnostic.from_dict(value)
        if result.integration_id:
            output[str(key)] = result
    return output


def save_diagnostic(audits_root: str | Path, diagnostic: IntegrationDiagnostic) -> Path:
    path = store_path(audits_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_diagnostics(audits_root)
    current[diagnostic.integration_id] = diagnostic
    payload = {
        "format_version": FORMAT_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "results": {key: value.to_dict() for key, value in sorted(current.items())},
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def result_currency(spec: IntegrationSpec, result: IntegrationDiagnostic | None, env: Mapping[str, str] | None = None) -> str:
    """Return CURRENT, CONFIG_CHANGED, STALE or MISSING without changing execution eligibility."""
    if result is None:
        return "MISSING"
    if result.configuration_fingerprint != configuration_fingerprint(spec, env):
        return "CONFIG_CHANGED"
    try:
        checked = datetime.fromisoformat(result.checked_at.replace("Z", "+00:00"))
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - checked.astimezone(timezone.utc)
    except ValueError:
        return "STALE"
    return "CURRENT" if age.total_seconds() <= spec.freshness_minutes * 60 else "STALE"


def _sanitized_text(body: bytes, secrets: tuple[str, ...]) -> str:
    text = body.decode("utf-8", errors="replace")[:4000]
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return " ".join(text.split())[:1200]


def _http(request: Request, *, timeout: float, opener: JsonOpener) -> _HttpResult:
    started = time.perf_counter()
    response = None
    try:
        response = opener(request, timeout=timeout)
        status = int(getattr(response, "status", None) or response.getcode())
        body = response.read(65536)
        return _HttpResult(status=status, body=body, latency_ms=max(0, int((time.perf_counter() - started) * 1000)))
    except HTTPError as exc:
        try:
            body = exc.read(65536)
        except OSError:
            body = b""
        return _HttpResult(status=int(exc.code), body=body, latency_ms=max(0, int((time.perf_counter() - started) * 1000)))
    except (TimeoutError, socket.timeout) as exc:
        return _HttpResult(status=None, body=b"", latency_ms=max(0, int((time.perf_counter() - started) * 1000)), error_kind="TIMEOUT", error_detail=type(exc).__name__)
    except URLError as exc:
        return _HttpResult(status=None, body=b"", latency_ms=max(0, int((time.perf_counter() - started) * 1000)), error_kind="NETWORK", error_detail=str(getattr(exc, "reason", "indisponível"))[:240])
    except OSError as exc:
        return _HttpResult(status=None, body=b"", latency_ms=max(0, int((time.perf_counter() - started) * 1000)), error_kind="NETWORK", error_detail=type(exc).__name__)
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def _payload(body: bytes) -> Any:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(token in lowered for token in tokens)


def _classify_http(
    spec: IntegrationSpec,
    result: _HttpResult,
    *,
    secrets: tuple[str, ...],
    malformed_request_is_success: bool = False,
    unsupported_method_is_limited: bool = False,
) -> IntegrationDiagnostic:
    fingerprint = configuration_fingerprint(spec)
    checked = datetime.now(timezone.utc).isoformat()
    if result.error_kind:
        return IntegrationDiagnostic(
            spec.id, spec.label, checked, STATUS_TRANSIENT_FAILURE, result.error_kind,
            "O serviço não respondeu de forma conclusiva neste momento; isso não prova erro de configuração.",
            "Tente novamente. Se persistir, verifique rede, proxy/firewall e o status do fornecedor.",
            fingerprint, result.latency_ms, None, spec.probe_cost, ("configuration", "connectivity"),
        )

    text = _sanitized_text(result.body, secrets)
    status = int(result.status or 0)
    auth_tokens = (
        "api key not valid", "invalid api key", "invalid_api_key", "incorrect api key",
        "invalid token", "token invalid", "expired token", "unauthorized", "authentication failed",
        "invalid authentication", "credentials are invalid",
    )
    billing_tokens = ("billing", "insufficient credit", "insufficient balance", "quota exceeded", "credit balance")
    permission_tokens = ("forbidden", "permission denied", "insufficient permission", "not authorized", "access denied")

    if status == 401 or _contains_any(text, auth_tokens):
        return IntegrationDiagnostic(
            spec.id, spec.label, checked, STATUS_AUTHENTICATION_ERROR, "AUTHENTICATION",
            "A credencial foi recusada pelo serviço.",
            "Revise a credencial configurada, confirme se não foi revogada/expirada e execute o teste novamente.",
            fingerprint, result.latency_ms, status, spec.probe_cost, ("configuration", "connectivity", "authentication"),
        )
    if _contains_any(text, billing_tokens):
        return IntegrationDiagnostic(
            spec.id, spec.label, checked, STATUS_QUOTA_OR_BILLING, "QUOTA_OR_BILLING",
            "O fornecedor respondeu, mas indicou limitação de quota, crédito ou billing.",
            "Revise quota, saldo/plano e permissões comerciais no fornecedor antes de processar novamente.",
            fingerprint, result.latency_ms, status, spec.probe_cost, ("configuration", "connectivity", "authentication"),
        )
    if status == 403 or _contains_any(text, permission_tokens):
        return IntegrationDiagnostic(
            spec.id, spec.label, checked, STATUS_AUTHORIZATION_ERROR, "AUTHORIZATION",
            "A credencial foi reconhecida, mas o recurso/permissão solicitado não está autorizado.",
            "Revise scopes/permissões e o recurso configurado para esta integração.",
            fingerprint, result.latency_ms, status, spec.probe_cost, ("configuration", "connectivity", "authentication", "authorization"),
        )
    if status == 429:
        return IntegrationDiagnostic(
            spec.id, spec.label, checked, STATUS_TRANSIENT_FAILURE, "RATE_LIMIT",
            "O serviço respondeu com rate limit. A integração não foi classificada como configuração inválida.",
            "Aguarde a janela do fornecedor e reteste; revise quota apenas se o erro persistir.",
            fingerprint, result.latency_ms, status, spec.probe_cost, ("configuration", "connectivity"),
        )
    if status >= 500:
        return IntegrationDiagnostic(
            spec.id, spec.label, checked, STATUS_TRANSIENT_FAILURE, "PROVIDER_UNAVAILABLE",
            f"O fornecedor respondeu HTTP {status}; a falha é tratada como temporária/externa, não como erro de configuração.",
            "Reteste posteriormente e consulte o status do fornecedor se a indisponibilidade persistir.",
            fingerprint, result.latency_ms, status, spec.probe_cost, ("configuration", "connectivity"),
        )
    if status in {400, 405, 422} and (malformed_request_is_success or unsupported_method_is_limited):
        return IntegrationDiagnostic(
            spec.id, spec.label, checked, STATUS_OPERATIONAL_LIMITED, "REACHABLE",
            "O endpoint respondeu e não indicou falha de autenticação; o probe deliberadamente não executou uma operação comercial/gerativa completa.",
            "Se a execução real exigir prova funcional adicional, valide novamente pelo fluxo normal sem interpretar este estado limitado como garantia de estabilidade.",
            fingerprint, result.latency_ms, status, spec.probe_cost, ("configuration", "connectivity"),
        )
    if status == 404:
        return IntegrationDiagnostic(
            spec.id, spec.label, checked, STATUS_RESOURCE_ERROR, "RESOURCE",
            "O endpoint/recurso configurado não foi encontrado.",
            "Revise endpoint, região, property/application ID ou modelo associado à integração.",
            fingerprint, result.latency_ms, status, spec.probe_cost, ("configuration", "connectivity"),
        )
    if 200 <= status < 300:
        return IntegrationDiagnostic(
            spec.id, spec.label, checked, STATUS_OPERATIONAL, "OK",
            "O serviço respondeu ao probe técnico sem erro de autenticação/configuração detectável.",
            "Nenhuma ação corretiva é necessária com base neste teste. O resultado descreve apenas o momento da validação.",
            fingerprint, result.latency_ms, status, spec.probe_cost, ("configuration", "connectivity", "authentication"),
        )
    return IntegrationDiagnostic(
        spec.id, spec.label, checked, STATUS_CONFIGURATION_ERROR, "HTTP_ERROR",
        f"O serviço respondeu HTTP {status or 'desconhecido'} e o probe não conseguiu confirmar uma configuração operacional.",
        "Revise as dependências exibidas e a documentação do serviço; reteste após o ajuste.",
        fingerprint, result.latency_ms, status or None, spec.probe_cost, ("configuration", "connectivity"),
    )


def _local_validation(spec: IntegrationSpec, env: Mapping[str, str]) -> IntegrationDiagnostic | None:
    fingerprint = configuration_fingerprint(spec, env)
    missing = missing_dependencies(spec, env)
    if missing:
        names = ", ".join(item.name for item in missing)
        return IntegrationDiagnostic(
            spec.id, spec.label, datetime.now(timezone.utc).isoformat(), STATUS_NOT_CONFIGURED, "DEPENDENCY",
            f"Dependência obrigatória ausente: {names}.",
            "Configure as dependências obrigatórias listadas nesta tela e execute o teste novamente.",
            fingerprint, None, None, spec.probe_cost, ("configuration",),
        )

    if spec.provider_id and spec.id.startswith("ai:"):
        registration = get_provider_registration(spec.provider_id)
        if registration is not None:
            key = str(env.get(registration.key_env) or "")
            if registration.required_key_prefixes and not key.startswith(registration.required_key_prefixes):
                return IntegrationDiagnostic(
                    spec.id, spec.label, datetime.now(timezone.utc).isoformat(), STATUS_CONFIGURATION_ERROR, "CREDENTIAL_FORMAT",
                    f"{registration.key_env} não corresponde ao formato aceito pelo adapter atual.",
                    "Gere uma credencial compatível com o contrato documentado para este provider.",
                    fingerprint, None, None, spec.probe_cost, ("configuration",),
                )
            model = str(env.get(registration.model_env) or registration.default_model).strip()
            if model not in registration.supported_models:
                return IntegrationDiagnostic(
                    spec.id, spec.label, datetime.now(timezone.utc).isoformat(), STATUS_CONFIGURATION_ERROR, "MODEL_CONFIGURATION",
                    f"Modelo configurado não pertence ao catálogo suportado pelo adapter: {model}.",
                    "Selecione um modelo aceito pelo provider registry e reteste.",
                    fingerprint, None, None, spec.probe_cost, ("configuration",),
                )

    if spec.probe_kind == "GSC":
        value = str(env.get("RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL") or "").strip()
        if not (value.startswith("sc-domain:") or value.startswith("https://") or value.startswith("http://")):
            return IntegrationDiagnostic(
                spec.id, spec.label, datetime.now(timezone.utc).isoformat(), STATUS_CONFIGURATION_ERROR, "PROPERTY_FORMAT",
                "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL deve ser sc-domain:<domínio> ou uma propriedade URL-prefix HTTP(S).",
                "Corrija a property exatamente como cadastrada no Google Search Console.",
                fingerprint, None, None, spec.probe_cost, ("configuration",),
            )

    if spec.probe_kind == "DYNATRACE":
        base = str(env.get("RASAI_DYNATRACE_BASE_URL") or "").strip()
        parsed = urlsplit(base)
        if parsed.scheme != "https" or not parsed.netloc:
            return IntegrationDiagnostic(
                spec.id, spec.label, datetime.now(timezone.utc).isoformat(), STATUS_CONFIGURATION_ERROR, "BASE_URL",
                "RASAI_DYNATRACE_BASE_URL deve ser uma URL HTTPS válida.",
                "Corrija a URL do ambiente Dynatrace e reteste.",
                fingerprint, None, None, spec.probe_cost, ("configuration",),
            )
    return None


def _derive_models_url(endpoint: str, default: str) -> str:
    if not endpoint.strip():
        return default
    parsed = urlsplit(endpoint.strip())
    path = parsed.path.rstrip("/")
    suffixes = ("/chat/completions", "/responses", "/interactions", "/messages")
    for suffix in suffixes:
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    if path.endswith("/v1beta"):
        models_path = path + "/models"
    elif path.endswith("/v1"):
        models_path = path + "/models"
    else:
        models_path = path + "/models"
    return urlunsplit((parsed.scheme, parsed.netloc, models_path, "", ""))


def _model_ids(payload: Any) -> set[str]:
    rows: Any = None
    if isinstance(payload, Mapping):
        rows = payload.get("data")
        if rows is None:
            rows = payload.get("models")
    if not isinstance(rows, list):
        return set()
    output: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        candidate = row.get("id") or row.get("name")
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text.startswith("models/"):
            text = text.split("/", 1)[1]
        if text:
            output.add(text)
    return output


def _probe_ai(spec: IntegrationSpec, env: Mapping[str, str], *, timeout: float, opener: JsonOpener) -> IntegrationDiagnostic:
    registration = get_provider_registration(spec.provider_id or "")
    if registration is None:
        return _rasai_error(spec, "Provider não encontrado no registry canônico.")
    key = str(env.get(registration.key_env) or "").strip()
    model = str(env.get(registration.model_env) or registration.default_model).strip()
    endpoint_override = str(env.get(registration.endpoint_env) or "").strip() if registration.endpoint_env else ""

    if registration.id == "copilot":
        request = Request(
            "https://api.github.com/user",
            method="GET",
            headers={
                "Authorization": f"Bearer {key}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "RASAi-Integration-Diagnostics",
            },
        )
        raw = _http(request, timeout=timeout, opener=opener)
        base = _classify_http(spec, raw, secrets=(key,))
        if base.status == STATUS_OPERATIONAL:
            return IntegrationDiagnostic(
                **{**base.to_dict(),
                   "status": STATUS_OPERATIONAL_LIMITED,
                   "category": "AUTHENTICATED_GITHUB",
                   "detail": "O token foi aceito pela API do GitHub. O probe não cria sessão Copilot nem envia prompt, portanto entitlement/modelo Copilot não são consumidos nem plenamente comprovados.",
                   "action": "Use o provider normalmente; se o runtime Copilot falhar, revise assinatura, Copilot Requests e instalação do SDK.",
                   "validated_facets": ("configuration", "connectivity", "authentication")}
            )
        return base

    defaults: dict[str, tuple[str, dict[str, str], bool]] = {
        "openai": ("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"}, False),
        "deepseek": ("https://api.deepseek.com/models", {"Authorization": f"Bearer {key}"}, False),
        "mimo": ("https://api.xiaomimimo.com/v1/models", {"api-key": key}, True),
        "xai": ("https://api.x.ai/v1/models", {"Authorization": f"Bearer {key}"}, False),
        "qwen": ("https://dashscope-us.aliyuncs.com/compatible-mode/v1/models", {"Authorization": f"Bearer {key}"}, True),
        "gemini": ("https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": key}, False),
        "anthropic": ("https://api.anthropic.com/v1/models", {"x-api-key": key, "anthropic-version": "2023-06-01"}, False),
    }
    if registration.id not in defaults:
        return _rasai_error(spec, "Provider sem probe seguro registrado.")
    default_url, headers, optional_catalog = defaults[registration.id]
    url = _derive_models_url(endpoint_override, default_url) if endpoint_override else default_url
    headers = {**headers, "Accept": "application/json", "User-Agent": "RASAi-Integration-Diagnostics"}
    raw = _http(Request(url, method="GET", headers=headers), timeout=timeout, opener=opener)
    base = _classify_http(spec, raw, secrets=(key,), unsupported_method_is_limited=optional_catalog)
    if base.status not in {STATUS_OPERATIONAL, STATUS_OPERATIONAL_LIMITED}:
        return base
    models = _model_ids(_payload(raw.body))
    if models and model not in models:
        return IntegrationDiagnostic(
            spec.id, spec.label, base.checked_at, STATUS_RESOURCE_ERROR, "MODEL_NOT_AVAILABLE",
            f"A credencial respondeu, mas o modelo configurado ({model}) não apareceu no catálogo acessível retornado pelo provider.",
            "Revise o modelo/região/endpoint configurado e reteste antes de depender deste provider.",
            base.configuration_fingerprint, base.latency_ms, base.http_status, spec.probe_cost,
            ("configuration", "connectivity", "authentication", "model_catalog"),
        )
    if base.status == STATUS_OPERATIONAL and not models:
        return IntegrationDiagnostic(
            spec.id, spec.label, base.checked_at, STATUS_OPERATIONAL_LIMITED, "CATALOG_UNVERIFIED",
            "O endpoint respondeu sem erro técnico, mas o probe não conseguiu interpretar um catálogo de modelos.",
            "A integração está comunicável; a disponibilidade do modelo será confirmada apenas pela execução real.",
            base.configuration_fingerprint, base.latency_ms, base.http_status, spec.probe_cost,
            ("configuration", "connectivity", "authentication"),
        )
    return IntegrationDiagnostic(
        spec.id, spec.label, base.checked_at, base.status, "OK",
        f"Credencial aceita e catálogo consultado sem geração de conteúdo; modelo efetivo: {model}.",
        "Nenhuma ação corretiva é necessária com base neste teste.",
        base.configuration_fingerprint, base.latency_ms, base.http_status, spec.probe_cost,
        ("configuration", "connectivity", "authentication", "model_catalog"),
    )


def _probe_serp(spec: IntegrationSpec, env: Mapping[str, str], *, timeout: float, opener: JsonOpener) -> IntegrationDiagnostic:
    provider = str(spec.provider_id or "")
    registration = next((item for item in SERP_PROVIDER_REGISTRY if item.id == provider), None)
    if registration is None:
        return _rasai_error(spec, "Provider SERP não encontrado no registry canônico.")
    key = str(env.get(registration.key_env) or "").strip()
    if provider in {"serpapi", "serpapi-bing"}:
        url = "https://serpapi.com/account.json?" + urlencode({"api_key": key})
        raw = _http(Request(url, method="GET", headers={"Accept": "application/json", "User-Agent": "RASAi-Integration-Diagnostics"}), timeout=timeout, opener=opener)
        return _classify_http(spec, raw, secrets=(key,))
    if provider == "zenserp":
        request = Request(
            "https://app.zenserp.com/api/v2/search",
            method="GET",
            headers={"Accept": "application/json", "apikey": key, "User-Agent": "RASAi-Integration-Diagnostics"},
        )
        raw = _http(request, timeout=timeout, opener=opener)
        return _classify_http(spec, raw, secrets=(key,), malformed_request_is_success=True)
    if provider == "scrapingdog":
        url = "https://api.scrapingdog.com/google/?" + urlencode({"api_key": key})
        raw = _http(Request(url, method="GET", headers={"Accept": "application/json", "User-Agent": "RASAi-Integration-Diagnostics"}), timeout=timeout, opener=opener)
        return _classify_http(spec, raw, secrets=(key,), malformed_request_is_success=True)
    return _rasai_error(spec, "Provider SERP sem probe registrado.")


def _google_key_probe(spec: IntegrationSpec, key: str, url: str, *, method: str, body: bytes | None, timeout: float, opener: JsonOpener) -> IntegrationDiagnostic:
    separator = "&" if "?" in url else "?"
    request = Request(
        url + separator + urlencode({"key": key}),
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "RASAi-Integration-Diagnostics"},
    )
    raw = _http(request, timeout=timeout, opener=opener)
    return _classify_http(spec, raw, secrets=(key,), malformed_request_is_success=True)


def _probe_gsc(spec: IntegrationSpec, env: Mapping[str, str], *, timeout: float, opener: JsonOpener) -> IntegrationDiagnostic:
    token = str(env.get("RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN") or "").strip()
    site = str(env.get("RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL") or "").strip()
    request = Request(
        "https://www.googleapis.com/webmasters/v3/sites",
        method="GET",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "RASAi-Integration-Diagnostics"},
    )
    raw = _http(request, timeout=timeout, opener=opener)
    base = _classify_http(spec, raw, secrets=(token,))
    if base.status != STATUS_OPERATIONAL:
        return base
    payload = _payload(raw.body)
    rows = payload.get("siteEntry") if isinstance(payload, Mapping) else None
    accessible = {
        str(item.get("siteUrl") or "").strip()
        for item in rows
        if isinstance(item, Mapping)
    } if isinstance(rows, list) else set()
    if site not in accessible:
        return IntegrationDiagnostic(
            spec.id, spec.label, base.checked_at, STATUS_AUTHORIZATION_ERROR, "PROPERTY_ACCESS",
            f"OAuth válido, porém a property configurada não foi encontrada entre as propriedades acessíveis: {site}.",
            "Confirme acesso da conta OAuth e use exatamente a property sc-domain/URL-prefix cadastrada no Search Console.",
            base.configuration_fingerprint, base.latency_ms, base.http_status, spec.probe_cost,
            ("configuration", "connectivity", "authentication", "property_access"),
        )
    return IntegrationDiagnostic(
        spec.id, spec.label, base.checked_at, STATUS_OPERATIONAL, "OK",
        f"OAuth aceito e acesso confirmado para a property configurada: {site}.",
        "Nenhuma ação corretiva é necessária com base neste teste.",
        base.configuration_fingerprint, base.latency_ms, base.http_status, spec.probe_cost,
        ("configuration", "connectivity", "authentication", "property_access"),
    )


def _probe_clarity(spec: IntegrationSpec, env: Mapping[str, str], *, timeout: float, opener: JsonOpener) -> IntegrationDiagnostic:
    token = str(env.get("RASAI_CLARITY_API_TOKEN") or "").strip()
    request = Request(
        "https://www.clarity.ms/export-data/api/v1/project-live-insights",
        method="OPTIONS",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "RASAi-Integration-Diagnostics"},
    )
    raw = _http(request, timeout=timeout, opener=opener)
    base = _classify_http(spec, raw, secrets=(token,), unsupported_method_is_limited=True)
    if base.status == STATUS_OPERATIONAL:
        base = IntegrationDiagnostic(
            spec.id, spec.label, base.checked_at, STATUS_OPERATIONAL_LIMITED, "REACHABLE",
            "O endpoint Clarity está comunicável. O diagnóstico não executa Data Export para preservar a quota diária escassa do serviço.",
            "A validade funcional completa do token será confirmada somente quando uma coleta Clarity for realmente solicitada.",
            base.configuration_fingerprint, base.latency_ms, base.http_status, spec.probe_cost,
            ("configuration", "connectivity"),
        )
    return base


def _probe_dynatrace(spec: IntegrationSpec, env: Mapping[str, str], *, timeout: float, opener: JsonOpener) -> IntegrationDiagnostic:
    token = str(env.get("DYNATRACE_API_TOKEN") or "").strip()
    base_url = str(env.get("RASAI_DYNATRACE_BASE_URL") or "").strip().rstrip("/")
    application_id = str(env.get("RASAI_DYNATRACE_APPLICATION_ID") or "").strip()
    url = base_url + "/api/config/v1/applications/web/" + quote(application_id, safe="")
    request = Request(
        url,
        method="GET",
        headers={"Authorization": f"Api-Token {token}", "Accept": "application/json", "User-Agent": "RASAi-Integration-Diagnostics"},
    )
    raw = _http(request, timeout=timeout, opener=opener)
    return _classify_http(spec, raw, secrets=(token,))


def _rasai_error(spec: IntegrationSpec, detail: str) -> IntegrationDiagnostic:
    return IntegrationDiagnostic(
        spec.id, spec.label, datetime.now(timezone.utc).isoformat(), STATUS_RASAI_ERROR, "RASAI",
        detail,
        "Revise o adapter/registry do RASAi; este estado não deve ser interpretado como falha do fornecedor.",
        configuration_fingerprint(spec), None, None, spec.probe_cost, ("configuration",),
    )


def run_diagnostic(
    spec: IntegrationSpec,
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = 12.0,
    opener: JsonOpener = urlopen,
) -> IntegrationDiagnostic:
    """Run one bounded, no-retry diagnostic without changing any runtime provider state."""
    environment = os.environ if env is None else env
    local = _local_validation(spec, environment)
    if local is not None:
        return local
    try:
        if spec.probe_kind == "AI_PROVIDER":
            return _probe_ai(spec, environment, timeout=timeout, opener=opener)
        if spec.probe_kind == "SERP_PROVIDER":
            return _probe_serp(spec, environment, timeout=timeout, opener=opener)
        if spec.probe_kind == "PAGESPEED":
            key = str(environment.get("RASAI_PAGESPEED_API_KEY") or "").strip()
            return _google_key_probe(spec, key, "https://www.googleapis.com/pagespeedonline/v5/runPagespeed", method="GET", body=None, timeout=timeout, opener=opener)
        if spec.probe_kind == "CRUX":
            key = str(environment.get("RASAI_CRUX_API_KEY") or "").strip()
            return _google_key_probe(spec, key, "https://chromeuxreport.googleapis.com/v1/records:queryRecord", method="POST", body=b"{}", timeout=timeout, opener=opener)
        if spec.probe_kind == "CRUX_HISTORY":
            key = str(environment.get("RASAI_CRUX_API_KEY") or "").strip()
            return _google_key_probe(spec, key, "https://chromeuxreport.googleapis.com/v1/records:queryHistoryRecord", method="POST", body=b"{}", timeout=timeout, opener=opener)
        if spec.probe_kind == "GSC":
            return _probe_gsc(spec, environment, timeout=timeout, opener=opener)
        if spec.probe_kind == "CLARITY":
            return _probe_clarity(spec, environment, timeout=timeout, opener=opener)
        if spec.probe_kind == "DYNATRACE":
            return _probe_dynatrace(spec, environment, timeout=timeout, opener=opener)
        if spec.probe_kind == "CONFIGURATION_ONLY":
            return IntegrationDiagnostic(
                spec.id, spec.label, datetime.now(timezone.utc).isoformat(), STATUS_OPERATIONAL_LIMITED, "CONFIGURATION_ONLY",
                "As dependências locais estão presentes, mas não há probe remoto seguro registrado para este serviço.",
                "Use a integração normalmente; um erro real continuará sendo tratado pelo adapter existente.",
                configuration_fingerprint(spec, environment), None, None, spec.probe_cost, ("configuration",),
            )
    except (ValueError, TypeError, KeyError) as exc:
        return IntegrationDiagnostic(
            spec.id, spec.label, datetime.now(timezone.utc).isoformat(), STATUS_RASAI_ERROR, "PROBE_CONTRACT",
            f"O probe não pôde ser montado com a configuração atual ({type(exc).__name__}).",
            "Revise a configuração exibida; se ela estiver correta, trate como problema do diagnóstico RASAi, não do fornecedor.",
            configuration_fingerprint(spec, environment), None, None, spec.probe_cost, ("configuration",),
        )
    return _rasai_error(spec, "Tipo de probe desconhecido.")
