"""Static Google Search Console scope checks shared by console and runtime gates.

The checks in this module deliberately do not call Google. They answer only what can
be proven locally from the configured Search Console property and the audited URL.
OAuth token validity and the authenticated account's permission on the property remain
provider-side facts and are validated only when Google accepts a request.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit

GSC_ENABLED_ENV = "RASAI_GSC_ENABLED"
GSC_TOKEN_ENV = "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN"
GSC_SITE_URL_ENV = "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL"

MODE_AUTO = "auto"
MODE_REQUIRED = "required"
MODE_DISABLED = "disabled"
MODE_INVALID = "invalid"

STATE_COMPATIBLE = "COMPATIBLE"
STATE_DISABLED = "DISABLED"
STATE_NOT_CONFIGURED = "NOT_CONFIGURED"
STATE_PROPERTY_URL_MISMATCH = "PROPERTY_URL_MISMATCH"
STATE_INVALID_SCOPE = "INVALID_SCOPE"
STATE_CONFIGURATION_INVALID = "CONFIGURATION_INVALID"


@dataclass(frozen=True, slots=True)
class GscScopeAssessment:
    mode: str
    state: str
    target_url: str
    site_url: str
    token_present: bool
    configured: bool
    property_covers_target: bool | None
    blocking: bool
    message: str

    @property
    def eligible(self) -> bool:
        return self.state == STATE_COMPATIBLE and self.configured


def _bool_override(raw: str | None) -> bool | None:
    text = str(raw or "").strip().casefold()
    if not text:
        return None
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError("use true/false, 1/0, yes/no or on/off")


def gsc_request_mode(environment: Mapping[str, str]) -> str:
    """Resolve global GSC intent without contacting Google."""
    try:
        explicit = _bool_override(environment.get(GSC_ENABLED_ENV))
    except ValueError:
        return MODE_INVALID
    if explicit is True:
        return MODE_REQUIRED
    if explicit is False:
        return MODE_DISABLED
    return MODE_AUTO


def _normalized_host(value: str | None) -> str:
    return str(value or "").strip().rstrip(".").casefold()


def _effective_port(parsed: object) -> int | None:
    scheme = str(getattr(parsed, "scheme", "") or "").casefold()
    port = getattr(parsed, "port", None)
    if port is not None:
        return int(port)
    if scheme == "https":
        return 443
    if scheme == "http":
        return 80
    return None


def _target_parts(target_url: str) -> tuple[str, str, int | None, str]:
    parsed = urlsplit(str(target_url).strip())
    scheme = parsed.scheme.casefold()
    host = _normalized_host(parsed.hostname)
    if scheme not in {"http", "https"} or not host:
        raise ValueError("URL auditada deve ser HTTP(S) absoluta")
    return scheme, host, _effective_port(parsed), parsed.path or "/"


def gsc_property_covers_url(site_url: str, target_url: str) -> bool:
    """Return whether a Search Console property can structurally cover ``target_url``.

    ``sc-domain:example.com`` covers the domain and all of its subdomains. URL-prefix
    properties are protocol/host/port specific and use path-prefix semantics.
    """
    property_value = str(site_url or "").strip()
    if not property_value:
        raise ValueError("propriedade GSC ausente")
    target_scheme, target_host, target_port, target_path = _target_parts(target_url)

    if property_value.casefold().startswith("sc-domain:"):
        domain = _normalized_host(property_value.split(":", 1)[1])
        if not domain or "/" in domain or ":" in domain:
            raise ValueError("propriedade sc-domain inválida")
        return target_host == domain or target_host.endswith("." + domain)

    parsed = urlsplit(property_value)
    property_scheme = parsed.scheme.casefold()
    property_host = _normalized_host(parsed.hostname)
    if property_scheme not in {"http", "https"} or not property_host:
        raise ValueError("propriedade GSC deve ser sc-domain:<domínio> ou URL-prefix HTTP(S)")
    if property_scheme != target_scheme or property_host != target_host:
        return False
    if _effective_port(parsed) != target_port:
        return False
    property_path = parsed.path or "/"
    return target_path.startswith(property_path)


def assess_gsc_target(
    target_url: str,
    environment: Mapping[str, str],
    *,
    mode_override: str | None = None,
) -> GscScopeAssessment:
    """Assess static GSC readiness for one audited URL.

    ``mode_override`` accepts ``auto``, ``required`` or ``disabled`` and is used by
    session-only execution profiles. When omitted, ``RASAI_GSC_ENABLED`` controls the
    intent: unset=auto, true=required, false=disabled.
    """
    mode = mode_override or gsc_request_mode(environment)
    target = str(target_url or "").strip()
    site_url = str(environment.get(GSC_SITE_URL_ENV) or "").strip()
    token_present = bool(str(environment.get(GSC_TOKEN_ENV) or "").strip())

    if mode == MODE_INVALID or mode not in {MODE_AUTO, MODE_REQUIRED, MODE_DISABLED}:
        return GscScopeAssessment(
            mode=MODE_INVALID,
            state=STATE_CONFIGURATION_INVALID,
            target_url=target,
            site_url=site_url,
            token_present=token_present,
            configured=False,
            property_covers_target=None,
            blocking=True,
            message=f"{GSC_ENABLED_ENV} possui valor inválido",
        )

    if mode == MODE_DISABLED:
        return GscScopeAssessment(
            mode=mode,
            state=STATE_DISABLED,
            target_url=target,
            site_url=site_url,
            token_present=token_present,
            configured=False,
            property_covers_target=None,
            blocking=False,
            message="Google Search Console está desabilitado para esta execução",
        )

    missing: list[str] = []
    if not token_present:
        missing.append(GSC_TOKEN_ENV)
    if not site_url:
        missing.append(GSC_SITE_URL_ENV)
    if missing:
        required = mode == MODE_REQUIRED
        return GscScopeAssessment(
            mode=mode,
            state=STATE_NOT_CONFIGURED,
            target_url=target,
            site_url=site_url,
            token_present=token_present,
            configured=False,
            property_covers_target=None,
            blocking=required,
            message=(
                "Google Search Console obrigatório sem configuração completa: "
                + ", ".join(missing)
                if required
                else "Google Search Console automático não está configurado por completo e não será exigido"
            ),
        )

    try:
        covers = gsc_property_covers_url(site_url, target)
    except ValueError as exc:
        required = mode == MODE_REQUIRED
        return GscScopeAssessment(
            mode=mode,
            state=STATE_INVALID_SCOPE,
            target_url=target,
            site_url=site_url,
            token_present=token_present,
            configured=True,
            property_covers_target=None,
            blocking=required,
            message=f"escopo GSC inválido: {exc}",
        )

    if not covers:
        required = mode == MODE_REQUIRED
        consequence = (
            "A auditoria não poderá atingir resultado completo/final enquanto GSC permanecer obrigatório."
            if required
            else "No modo automático/compatível o GSC será ignorado para esta URL e não será requisito de conclusão."
        )
        return GscScopeAssessment(
            mode=mode,
            state=STATE_PROPERTY_URL_MISMATCH,
            target_url=target,
            site_url=site_url,
            token_present=token_present,
            configured=True,
            property_covers_target=False,
            blocking=required,
            message=(
                f"propriedade GSC {site_url!r} não cobre a URL auditada {target!r}. {consequence}"
            ),
        )

    return GscScopeAssessment(
        mode=mode,
        state=STATE_COMPATIBLE,
        target_url=target,
        site_url=site_url,
        token_present=token_present,
        configured=True,
        property_covers_target=True,
        blocking=False,
        message=(
            f"propriedade GSC {site_url!r} cobre a URL auditada. "
            "Esta validação é somente de escopo; validade do OAuth e permissão da conta sobre a propriedade "
            "só são confirmadas pela API do Google."
        ),
    )
