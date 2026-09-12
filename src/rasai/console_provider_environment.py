"""Provider-aware, guided environment configuration for the interactive console.

The materialized base environment catalog is the single source of variable metadata.
This facade enriches provider metadata and gives operators a consistent navigation
model: category -> variable -> action, with explicit guidance about defaults, secrets
and cross-category dependencies. Runtime enrichments already present in ``SPECS`` are
preserved; the facade must not rebuild the generic factory and discard them.
"""
from __future__ import annotations

from dataclasses import replace
from getpass import getpass
import os

from rasai import console_environment as base_environment
from rasai.console_ui import CYAN, DIM, GREEN, YELLOW, paint
from rasai.provider_registry import provider_registrations
from rasai.search_intelligence.config import SERP_PROVIDER_ENV
from rasai.search_intelligence.provider_catalog import SERP_PROVIDER_REGISTRY, serp_provider_ids

EnvironmentSpec = base_environment.EnvironmentSpec
CATEGORIES = base_environment.CATEGORIES
DOCUMENT_NAME = base_environment.DOCUMENT_NAME

_CATEGORY_GUIDANCE: dict[str, tuple[str, ...]] = {
    "Aplicação e execução": (
        "Preferências gerais do console e do pipeline local.",
        "Defina overrides somente quando o default do runtime não atende ao cenário.",
    ),
    "IA - credenciais": (
        "Credenciais habilitam providers de IA; elas nunca entram no INI.",
        "Para uso normal, prefira o gerenciador da opção IA do menu principal.",
    ),
    "IA - modelos e reasoning": (
        "Modelo e reasoning são configuração, não segredo.",
        "Os defaults públicos vêm do provider registry e podem ser mantidos sem override.",
    ),
    "IA - endpoints avançados": (
        "Use somente para endpoint compatível/proxy explicitamente homologado.",
    ),
    "IA - contexto editorial / YMYL": (
        "Contexto explícito melhora interpretação sem criar score YMYL/E-E-A-T.",
    ),
    "Search Intelligence / Observability": (
        "SERP e observabilidade são independentes do SARI/SCORE-GEO.",
        "Google Search Console usa aqui o token OAuth; a property fica em Métricas e padrões.",
    ),
    "Web Performance / Google APIs": (
        "PageSpeed e CrUX ficam AUTO quando a credencial existe, salvo hard-off explícito.",
        "API keys são secrets e não são persistidas no INI.",
    ),
    "Métricas e padrões": (
        "Serviços gratuitos/sem credencial usam o default do registry; não é preciso repetir true.",
        "GSC AUTO exige token OAuth em Search Intelligence / Observability e property neste grupo.",
        "PageSpeed/CrUX AUTO usam as chaves configuradas em Web Performance / Google APIs.",
    ),
    "Synthetic Apdex": (
        "Medições sintéticas geram navegações reais; revise volume, concorrência e timeout.",
    ),
    "Browser / Playwright": (
        "Overrides de browser afetam a captura técnica e devem ser alterados com cautela.",
    ),
    "Control plane / SaaS": (
        "Configuração de operador/deployment; não deve ser confundida com configuração de tenant.",
    ),
    "Web API / Identity": (
        "Configuração de autenticação e API do deployment; secrets seguem fora do INI.",
    ),
    "Remote control plane": (
        "Use apenas quando o console operar como cliente de um control plane remoto.",
    ),
}


def _build_specs() -> tuple[EnvironmentSpec, ...]:
    # SPECS is the runtime-composed catalog. Calling environment_specs() here would
    # rebuild only the generic base factory and silently discard metadata installed by
    # standards, synthetic profiles and other runtime extensions.
    specs = list(base_environment.SPECS)
    by_name = {spec.name: index for index, spec in enumerate(specs)}

    provider_index = by_name.get(SERP_PROVIDER_ENV)
    if provider_index is not None:
        specs[provider_index] = replace(
            specs[provider_index],
            accepted=serp_provider_ids(),
            notes=(
                "O provider selecionado determina engine, variável de credencial e "
                "estratégia de paginação. Consulte `rasai providers --kind serp`."
            ),
        )

    by_key: dict[str, list[object]] = {}
    for registration in SERP_PROVIDER_REGISTRY:
        by_key.setdefault(registration.key_env, []).append(registration)
    for key_env, registrations in by_key.items():
        index = by_name.get(key_env)
        if index is None:
            continue
        provider_ids = ", ".join(item.id for item in registrations)
        display_names = " / ".join(dict.fromkeys(item.display_name for item in registrations))
        credential_url = registrations[0].credential_url
        notes = " | ".join(dict.fromkeys(item.free_tier_note for item in registrations if item.free_tier_note))
        specs[index] = replace(
            specs[index],
            category="Search Intelligence / Observability",
            purpose=f"Credencial BYOK do provider {display_names}.",
            value_type="segredo/API key",
            required_when=(
                "Obrigatória quando RASAI_SERP_MODE=live e RASAI_SERP_PROVIDER "
                f"for um de: {provider_ids}."
            ),
            sensitive=True,
            impact="Consome quota/créditos do provider; limites do RASAi não substituem a quota do fornecedor.",
            source=f"{display_names} chave/login - {credential_url}",
            notes=notes,
        )

    ai_by_key = {registration.key_env: registration for registration in provider_registrations()}
    for index, spec in enumerate(specs):
        registration = ai_by_key.get(spec.name)
        if registration is None:
            continue
        notes = registration.auth_note or (
            f"Obtenha/gerencie a credencial em {registration.credential_url}. "
            f"Documentação: {registration.documentation_url}"
        )
        specs[index] = replace(
            spec,
            source=f"{registration.display_name} credencial/login - {registration.credential_url}",
            notes=notes,
        )
    return tuple(specs)


def environment_specs() -> tuple[EnvironmentSpec, ...]:
    return _build_specs()


def refresh_specs() -> tuple[EnvironmentSpec, ...]:
    global ENV_NAMES, SPECS, SPEC_BY_NAME, CATEGORIES
    ENV_NAMES = base_environment.ENV_NAMES
    CATEGORIES = base_environment.CATEGORIES
    SPECS = environment_specs()
    SPEC_BY_NAME = {spec.name: spec for spec in SPECS}
    return SPECS


ENV_NAMES = base_environment.ENV_NAMES
SPECS = environment_specs()
SPEC_BY_NAME = {spec.name: spec for spec in SPECS}


def _validate(name: str, raw: str) -> str:
    if name == SERP_PROVIDER_ENV:
        value = str(raw).strip().casefold()
        if not value:
            raise ValueError("valor vazio; remova a variável em vez de gravar vazio")
        allowed = serp_provider_ids()
        if value not in set(allowed):
            raise ValueError("use " + ", ".join(allowed))
        return value
    return base_environment._validate(name, raw)


def _breadcrumb(*parts: str) -> None:
    print(paint("CONFIGURAÇÃO  >  " + "  >  ".join(parts), CYAN, bold=True))
    print()


def _guidance(category: str) -> None:
    lines = _CATEGORY_GUIDANCE.get(category, ())
    if not lines:
        return
    print("COMO USAR ESTE GRUPO")
    for line in lines:
        print(f"  - {line}")
    print()


def _selection_state(spec: EnvironmentSpec) -> str:
    raw = (os.environ.get(spec.name) or "").strip()
    if raw:
        return "override/credencial definido"
    if spec.default is not None:
        return "usando default do runtime"
    return "sem valor explícito"


def _variable_menu(state: object, spec: EnvironmentSpec) -> None:
    while True:
        base_environment.render_header(state)
        _breadcrumb(spec.category, spec.name)
        base_environment._render_detail(spec)
        sensitive = base_environment._is_sensitive_spec(spec)
        print()
        print(f"Estado de decisão: {paint(_selection_state(spec), GREEN if (os.environ.get(spec.name) or '').strip() else DIM, bold=True)}")
        if sensitive:
            print(paint("Secret: use sessão/Windows User; nunca será gravado no rasai-console.ini.", YELLOW))
        elif spec.default is not None and not (os.environ.get(spec.name) or "").strip():
            print(paint("Nenhuma ação é necessária para manter o default mostrado acima.", DIM))

        if sensitive:
            print("\nAÇÕES\nS. Definir/alterar na sessão\nR. Remover da sessão\nP. Persistência Windows/User\nD. Documentação\nV. Voltar")
        else:
            print("\nAÇÕES\nS. Definir/alterar override\nR. Remover override e voltar ao default\nD. Documentação\nV. Voltar")
        action = input("Escolha: ").strip().upper()
        if action == "V":
            return
        if action == "D":
            base_environment._open_docs(state)
            continue
        if action == "P" and sensitive:
            try:
                base_environment._persist_secret(state, spec)
            except (OSError, ValueError) as exc:
                setattr(state, "error", f"falha de persistência: {type(exc).__name__}: {exc}")
            continue
        if action == "R":
            os.environ.pop(spec.name, None)
            if sensitive:
                base_environment._sync_secret_state(state, spec.name)
            base_environment._apply_change(state, spec.name)
            setattr(state, "operation", "LOCAL:CONFIG_OVERRIDE_REMOVED")
            continue
        if action != "S":
            setattr(state, "error", "ação inválida")
            continue
        try:
            if spec.accepted and spec.value_type in {"enum", "enum inteiro", "booleano"}:
                raw = base_environment._prompt_choice(spec)
                if raw is None:
                    continue
            else:
                raw = getpass(f"{spec.name}: ") if sensitive else input(f"{spec.name}: ")
            os.environ[spec.name] = _validate(spec.name, raw)
            if sensitive:
                base_environment._sync_secret_state(state, spec.name)
            base_environment._apply_change(state, spec.name)
            setattr(state, "operation", "LOCAL:CONFIG_UPDATED")
        except (ValueError, OverflowError) as exc:
            setattr(state, "error", str(exc))


def _category_menu(state: object, title: str, specs: tuple[EnvironmentSpec, ...]) -> None:
    configured_only = False
    while True:
        base_environment.render_header(state)
        _breadcrumb(title)
        _guidance(title)
        visible = tuple(
            spec for spec in specs
            if not configured_only or bool((os.environ.get(spec.name) or "").strip())
        )
        if not visible:
            print(paint("Nenhum override/secret definido neste grupo.", DIM))
        for index, spec in enumerate(visible, 1):
            status = base_environment._status(spec)
            decision = _selection_state(spec)
            print(f"{index:2d}. {spec.name:<44} {status:<20} {decision}")
        print("\nAÇÕES")
        print("F. " + ("Mostrar todas" if configured_only else "Mostrar somente definidas"))
        print("D. Abrir documentação detalhada")
        print("V. Voltar")
        raw = input("Selecione a variável ou ação: ").strip().upper()
        if raw == "V":
            return
        if raw == "D":
            base_environment._open_docs(state)
            continue
        if raw == "F":
            configured_only = not configured_only
            continue
        try:
            _variable_menu(state, visible[int(raw) - 1])
        except (ValueError, IndexError):
            setattr(state, "error", "variável inválida")


def environment_menu(state: object) -> None:
    """Show the complete registry-aware configuration catalog by functional context."""
    refresh_specs()
    grouped = {category: tuple(spec for spec in SPECS if spec.category == category) for category in CATEGORIES}
    while True:
        base_environment.render_header(state)
        _breadcrumb("Configuração avançada")
        print("FLUXO RECOMENDADO")
        print("  1. Use o menu principal para Entrada, Device, IA, Web Performance e Apdex.")
        print("  2. Use esta área para integrações, credenciais e overrides avançados.")
        print("  3. Salve o INI no menu principal para persistir somente configurações não secretas.")
        print("  4. Antes de executar, revise o preflight; integração ausente não vira finding do website.\n")
        print(paint("AUTO/Padrão significa deixar o runtime resolver pelo registry e requisitos; não é necessário repetir defaults.", DIM))
        print(paint("Secrets nunca entram no INI. Windows/User exige ação explícita do operador.", YELLOW))
        print()

        choices: dict[str, str] = {}
        for index, category in enumerate(CATEGORIES, 1):
            specs = grouped[category]
            configured = sum(1 for spec in specs if (os.environ.get(spec.name) or "").strip())
            marker = paint(f"{configured}/{len(specs)} definidos", GREEN if configured else DIM)
            print(f" {index:2d}. {category:<36} {marker}")
            choices[str(index)] = category
        print("\n A. Todas as variáveis")
        print(f" D. Abrir documentação detalhada (docs/{DOCUMENT_NAME})")
        print(" V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return
        if raw == "D":
            base_environment._open_docs(state)
            continue
        if raw == "A":
            _category_menu(state, "Todas", SPECS)
            continue
        category = choices.get(raw)
        if category:
            _category_menu(state, category, grouped[category])
        else:
            setattr(state, "error", "grupo inválido")
