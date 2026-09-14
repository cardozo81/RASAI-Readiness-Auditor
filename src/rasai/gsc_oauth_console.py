"""Interactive-console metadata for the current Google Search Console OAuth contract."""
from __future__ import annotations

from rasai.gsc_oauth import CLIENT_ID_ENV, CLIENT_SECRET_ENV, REFRESH_TOKEN_ENV

_INSTALLED = False


def _oauth_specs(base):
    category = "Search Intelligence / Observability"
    source = "docs/ENVIRONMENT_VARIABLES.md"
    return (
        base.EnvironmentSpec(
            CLIENT_ID_ENV,
            category,
            "OAuth Client ID do Google usado para renovar automaticamente o access token do Search Console.",
            "texto",
            required_when="Obrigatório somente no modo OAuth durável com Refresh Token.",
            sensitive=False,
            impact="Sem custo externo direto; identifica o cliente OAuth autorizado.",
            source=source,
            notes="Pode ser persistido no INI por não ser segredo.",
        ),
        base.EnvironmentSpec(
            CLIENT_SECRET_ENV,
            category,
            "OAuth Client Secret do Google usado somente na troca do Refresh Token por access token em memória.",
            "segredo",
            required_when="Obrigatório somente no modo OAuth durável com Refresh Token.",
            sensitive=True,
            impact="Credencial sensível; nunca é gravada no INI.",
            source=source,
        ),
        base.EnvironmentSpec(
            REFRESH_TOKEN_ENV,
            category,
            "OAuth Refresh Token do Google usado para renovar automaticamente o access token do Search Console.",
            "segredo/token",
            required_when="Obrigatório somente no modo OAuth durável com Client ID + Client Secret.",
            sensitive=True,
            impact="Credencial sensível de longa duração; nunca é gravada no INI.",
            source=source,
            notes="O access token gerado existe somente em memória durante a chamada ao Google.",
        ),
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        try:
            from rasai import console_provider_environment as facade
            facade.refresh_specs()
        except ImportError:
            pass
        return

    from rasai import console_environment as base

    original_fixed_specs = base._fixed_specs
    if not bool(getattr(original_fixed_specs, "_rasai_gsc_oauth", False)):
        def fixed_specs():
            specs = list(original_fixed_specs())
            by_name = {spec.name: index for index, spec in enumerate(specs)}
            for spec in _oauth_specs(base):
                index = by_name.get(spec.name)
                if index is None:
                    by_name[spec.name] = len(specs)
                    specs.append(spec)
                else:
                    specs[index] = spec
            return tuple(specs)

        fixed_specs._rasai_gsc_oauth = True  # type: ignore[attr-defined]
        fixed_specs._rasai_original = original_fixed_specs  # type: ignore[attr-defined]
        base._fixed_specs = fixed_specs

    names = (CLIENT_ID_ENV, CLIENT_SECRET_ENV, REFRESH_TOKEN_ENV)
    base.ENV_NAMES = tuple(dict.fromkeys((*base.ENV_NAMES, *names)))
    specs = {spec.name: spec for spec in (*base.SPECS, *_oauth_specs(base))}
    base.SPECS = tuple(specs[name] for name in base.ENV_NAMES if name in specs)
    base.SPEC_BY_NAME = {spec.name: spec for spec in base.SPECS}

    try:
        from rasai import console_provider_environment as facade
        facade.refresh_specs()
    except ImportError:
        pass

    _INSTALLED = True
