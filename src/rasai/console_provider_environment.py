"""Provider-aware, guided environment configuration for the interactive console.

The materialized base environment catalog is the single source of variable metadata.
This facade enriches provider metadata and gives operators a consistent navigation
model: category -> context -> variable -> action, with explicit guidance about defaults,
secrets, references and cross-category dependencies. Runtime enrichments already present
in ``SPECS`` are preserved; the facade must not rebuild the generic factory and discard
them.
"""
from __future__ import annotations

from dataclasses import replace
from rasai.console_secret_input import masked_secret_input as getpass
import os

from rasai import console_environment as base_environment
from rasai.console_input_contract import EditCancelled, prompt_secret, prompt_text
from rasai.console_configuration_guidance import (
    context_for,
    decision_badge,
    grouped_by_context,
    normalize_spec,
    normalize_specs,
    prompt_guided_value,
    render_enrichment,
)
from rasai.console_ui import CYAN, DIM, GRAY, GREEN, YELLOW, paint
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
    "IA - análise profunda": (
        "Provider, modelo, reasoning e domínios pertencem ao mesmo contexto de Improvement Intelligence.",
        "Modelo e reasoning passam a usar a lista válida do provider selecionado quando essa dependência é conhecida.",
    ),
    "Search Intelligence / Observability": (
        "SERP e observabilidade são independentes do SARI/SCORE-GEO.",
        "Google Search Console usa token OAuth e property; o console agrupa essas variáveis pelo contexto GSC.",
    ),
    "Web Performance / Google APIs": (
        "PageSpeed e CrUX ficam AUTO quando a credencial existe, salvo hard-off explícito.",
        "API keys são secrets e não são persistidas no INI.",
    ),
    "Métricas e padrões": (
        "Serviços gratuitos/sem credencial usam o default do registry; não é preciso repetir true.",
        "GSC AUTO exige token OAuth e property; PageSpeed/CrUX AUTO usam as respectivas chaves.",
        "As variáveis são agrupadas pelo recurso externo para reduzir navegação cruzada.",
    ),
    "Synthetic Apdex": (
        "Medições sintéticas geram navegações reais; revise volume, concorrência e timeout.",
        "Navigation, Experience e calibração Dynatrace aparecem em contextos separados.",
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


# Runtime configuration names reconciled from real operator INI and consumers.
# Deliberately explicit: do not allowlist arbitrary RASAI_* names or secrets.
_ADDITIONAL_RUNTIME_INPUTS = (
    ("RASAI_AI_ANALYSIS_LANGUAGE", "IA - modelos e reasoning", "tag BCP-47 ou auto", (), "src/rasai/improvement_intelligence.py"),
    ("RASAI_AI_MODELS_FILE", "IA - modelos e reasoning", "caminho de arquivo", (), "src/rasai/ai_model_catalog.py"),
    ("RASAI_AI_MODELS_SOURCE", "IA - modelos e reasoning", "enum", ("factory", "file", "auto"), "src/rasai/ai_model_catalog.py"),
    ("RASAI_AI_PRICING_FILE", "IA - pricing", "caminho de arquivo", (), "src/rasai/ai_pricing_catalog.py"),
    ("RASAI_AI_PRICING_SOURCE", "IA - pricing", "enum", ("factory", "file", "auto"), "src/rasai/ai_pricing_catalog.py"),
    ("RASAI_AI_TASK_PROFILES_FILE", "IA - modelos e reasoning", "caminho de arquivo", (), "src/rasai/ai_task_profiles.py"),
    ("RASAI_AI_TASK_PROFILES_SOURCE", "IA - modelos e reasoning", "enum", ("factory", "file", "auto"), "src/rasai/ai_task_profiles.py"),
    # GSC's nonsecret inputs were listed as static consumers but absent
    # from the canonical EnvironmentSpec persistence allowlist. The console
    # silently skipped these legitimate INI values on reload (#523).
    ("RASAI_GSC_ENABLED", "Search Intelligence / Observability", "booleano", ("true", "false"), "src/rasai/gsc_scope.py"),
    ("RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL", "Search Intelligence / Observability", "propriedade GSC", (), "src/rasai/gsc_scope.py"),
    ("RASAI_GSC_SEARCH_ANALYTICS_DAYS", "Search Intelligence / Observability", "inteiro 0..31", (), "src/rasai/standards_gsc_policy.py"),
    ("RASAI_GSC_SEARCH_MAX_ROWS", "Search Intelligence / Observability", "inteiro 1..50000", (), "src/rasai/standards_gsc_policy.py"),
    ("RASAI_GSC_FINAL_DATA_LAG_DAYS", "Search Intelligence / Observability", "inteiro 0..30", (), "src/rasai/standards_gsc_policy.py"),
    ("RASAI_GOOGLE_SEARCH_CONSOLE_CLIENT_ID", "Search Intelligence / Observability", "OAuth client ID publico", (), "src/rasai/gsc_oauth.py"),
    ("RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS", "IA - modelos e reasoning", "numero > 0", (), "src/rasai/improvement_intelligence.py"),
    ("RASAI_IMPROVEMENT_DOMAINS", "IA - modelos e reasoning", "lista CSV", (), "src/rasai/improvement_intelligence.py"),
    ("RASAI_IMPROVEMENT_INTELLIGENCE", "IA - modelos e reasoning", "booleano", ("true", "false"), "src/rasai/improvement_intelligence.py"),
    ("RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS", "IA - modelos e reasoning", "inteiro 1..100", (), "src/rasai/improvement_intelligence.py"),
    ("RASAI_GEOIP_ACQUIRE_TOOLS", "Search Intelligence / Observability", "booleano", ("true", "false"), "src/rasai/network_geoip_bootstrap.py"),
    ("RASAI_NETWORK_ACTIVE_ENABLED", "Search Intelligence / Observability", "booleano", ("true", "false"), "src/rasai/network_active_policy.py"),
    ("RASAI_NETWORK_ACTIVE_HOST", "Search Intelligence / Observability", "hostname público exato", (), "src/rasai/network_active_policy.py"),
    ("RASAI_NETWORK_MAX_HOPS", "Search Intelligence / Observability", "inteiro 1..16", (), "src/rasai/network_traceroute.py"),
    ("RASAI_NETWORK_GEOIP_SOURCE", "Search Intelligence / Observability", "enum", ("LOCAL_FIRST", "DISABLED"), "src/rasai/network_enrichment.py"),
    ("RASAI_PASSIVE_SECURITY", "Aplicação e execução", "booleano", ("true", "false"), "src/rasai/passive_security.py"),
    ("RASAI_PRESENTATION_TIMEZONE", "Aplicação e execução", "timezone IANA", (), "src/rasai/time_contract.py"),
    ("RASAI_SECURITY_CISA_KEV", "Aplicação e execução", "booleano", ("true", "false"), "src/rasai/passive_security.py"),
    ("RASAI_SECURITY_COOKIES", "Aplicação e execução", "booleano", ("true", "false"), "src/rasai/passive_security.py"),
    ("RASAI_SECURITY_EXTERNAL_TIMEOUT_SECONDS", "Aplicação e execução", "numero > 0", (), "src/rasai/passive_security.py"),
    ("RASAI_SECURITY_HEADERS", "Aplicação e execução", "booleano", ("true", "false"), "src/rasai/passive_security.py"),
    ("RASAI_SECURITY_OSV", "Aplicação e execução", "booleano", ("true", "false"), "src/rasai/passive_security.py"),
    ("RASAI_SECURITY_RESOURCES", "Aplicação e execução", "booleano", ("true", "false"), "src/rasai/passive_security.py"),
    ("RASAI_SECURITY_RUNTIME_CORRELATION", "Aplicação e execução", "booleano", ("true", "false"), "src/rasai/passive_security.py"),
    ("RASAI_SECURITY_THIRD_PARTY", "Aplicação e execução", "booleano", ("true", "false"), "src/rasai/passive_security.py"),
)

def _build_specs() -> tuple[EnvironmentSpec, ...]:
    specs = list(base_environment.SPECS)
    existing = {spec.name for spec in specs}
    specs.extend(
        EnvironmentSpec(
            name=name,
            category=category,
            purpose=f"Configuracao operacional lida por {source}.",
            value_type=value_type,
            accepted=accepted,
            source=source,
        )
        for name, category, value_type, accepted, source in _ADDITIONAL_RUNTIME_INPUTS
        if name not in existing
    )
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
        documentation_urls = ", ".join(dict.fromkeys(item.documentation_url for item in registrations))
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
            source=(
                f"Credencial/login: {credential_url} | documentação oficial: {documentation_urls}"
            ),
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
            source=(
                f"Credencial/login: {registration.credential_url} | "
                f"documentação oficial: {registration.documentation_url}"
            ),
            notes=notes,
        )
    return normalize_specs(tuple(specs))


def environment_specs() -> tuple[EnvironmentSpec, ...]:
    return _build_specs()


def refresh_specs() -> tuple[EnvironmentSpec, ...]:
    global ENV_NAMES, SPECS, SPEC_BY_NAME, CATEGORIES
    CATEGORIES = base_environment.CATEGORIES
    SPECS = environment_specs()
    ENV_NAMES = tuple(spec.name for spec in SPECS)
    SPEC_BY_NAME = {spec.name: spec for spec in SPECS}
    return SPECS


SPECS = environment_specs()
ENV_NAMES = tuple(spec.name for spec in SPECS)
SPEC_BY_NAME = {spec.name: spec for spec in SPECS}


def _validate(name: str, raw: str) -> str:
    if name in {"RASAI_GEOIP_ACQUIRE_TOOLS", "RASAI_NETWORK_ACTIVE_ENABLED", "RASAI_NETWORK_ACTIVE_HOST",
                "RASAI_NETWORK_MAX_HOPS", "RASAI_NETWORK_GEOIP_SOURCE"}:
        from rasai.network_active_policy import validate_network_setting
        return validate_network_setting(name, raw)
    if name in {
        "RASAI_GSC_SEARCH_ANALYTICS_DAYS", "RASAI_GSC_SEARCH_MAX_ROWS",
        "RASAI_GSC_FINAL_DATA_LAG_DAYS",
    }:
        # One shared bounded policy for the menu, INI and consumer.
        # Integer parsing alone would accept negatives, 50k+ rows and
        # silently over-collect from an operator's stored preference.
        from rasai import standards_gsc_policy as gsc_policy
        methods = {
            gsc_policy.GSC_SEARCH_ANALYTICS_DAYS_ENV: gsc_policy.search_analytics_days,
            gsc_policy.GSC_SEARCH_MAX_ROWS_ENV: gsc_policy.search_max_rows,
            gsc_policy.GSC_FINAL_DATA_LAG_DAYS_ENV: gsc_policy.final_data_lag_days,
        }
        value = str(raw).strip()
        if not value:
            raise ValueError("valor vazio; remova o override em vez de gravar vazio")
        # The shared policy only accepts bounded decimal integers after the
        # canonical validator, never an accidental float/boolean surrogate.
        if not value.isdecimal() or not value.isascii():
            raise ValueError("use inteiro decimal não negativo")
        return str(methods[name](value))
    if name == "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL":
        from urllib.parse import urlsplit
        from rasai.gsc_scope import gsc_property_covers_url
        value = str(raw).strip()
        if not value or any(ord(char) < 33 or ord(char) == 127 for char in value):
            raise ValueError("propriedade GSC vazia ou inválida")
        if value.casefold().startswith("sc-domain:"):
            # The runtime covers subdomains of the explicitly declared
            # property. Do not persist a URL with a secret-like userinfo.
            domain = value.split(":", 1)[1]
            if (not domain or any(char in domain for char in "/\\@?#:")
                    or domain.startswith(".") or domain.endswith(".")
                    or ".." in domain):
                raise ValueError("domínio da propriedade GSC inválido")
        else:
            parsed = urlsplit(value)
            if (parsed.scheme not in {"http", "https"}
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.query or parsed.fragment):
                raise ValueError("property URL-prefix não pode conter credenciais/query/fragmento")
            # Parsing the port here also checks malformed authority.
            _port = parsed.port
        # Reuse the real runtime's structural property parser; the dummy
        # target is never sent to Google or used to select an AUD.
        gsc_property_covers_url(value, "https://example.invalid/")
        return value
    if name == SERP_PROVIDER_ENV:
        value = str(raw).strip().casefold()
        if not value:
            raise ValueError("valor vazio; remova a variável em vez de gravar vazio")
        allowed = serp_provider_ids()
        if value not in set(allowed):
            raise ValueError("use " + ", ".join(allowed))
        return value
    if name in {entry[0] for entry in _ADDITIONAL_RUNTIME_INPUTS}:
        from rasai.time_contract import validate_presentation_timezone
        # Use the explicit validation contract rather than mutable UI metadata:
        # console plug-ins may enrich a spec after registry composition.
        definition = next(row for row in _ADDITIONAL_RUNTIME_INPUTS if row[0] == name)
        expected_type, expected_choices = definition[2], definition[3]
        candidate = str(raw).strip()
        if not candidate:
            raise ValueError("valor vazio; remova o override em vez de gravar vazio")
        if expected_choices:
            canonical = candidate.casefold()
            if canonical not in expected_choices:
                raise ValueError("use " + ", ".join(expected_choices))
            return canonical
        if expected_type == "inteiro > 0":
            if int(candidate) <= 0:
                raise ValueError("use inteiro > 0")
        elif expected_type == "numero > 0":
            from math import isfinite
            number = float(candidate)
            if not isfinite(number) or number <= 0:
                raise ValueError("use numero finito > 0")
        elif expected_type == "timezone IANA":
            return validate_presentation_timezone(candidate)
        elif expected_type == "inteiro 1..100":
            count = int(candidate)
            if not 1 <= count <= 100:
                raise ValueError("use inteiro 1..100")
        elif expected_type == "lista CSV" and name == "RASAI_IMPROVEMENT_DOMAINS":
            from rasai.improvement_intelligence import parse_domains
            return ",".join(parse_domains(candidate))
        elif expected_type == "tag BCP-47 ou auto":
            from rasai.improvement_intelligence import validate_analysis_language
            return validate_analysis_language(candidate)
        return candidate
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
    required = str(spec.required_when or "").casefold()
    if required and not required.startswith("nunca") and "opcional" not in required:
        return "configuração condicional"
    return "sem valor explícito"


def _variable_menu(state: object, spec: EnvironmentSpec) -> None:
    while True:
        # Re-evaluate dependent domains on every visit. Example: the valid model and
        # reasoning lists for Improvement Intelligence depend on the provider selected
        # immediately before this screen.
        spec = normalize_spec(spec)
        base_environment.render_header(state)
        from rasai.console_configuration_presentation import friendly_label
        _breadcrumb(spec.category, context_for(spec), friendly_label(spec))
        print(paint(f"Variável técnica: {spec.name}", GRAY))
        base_environment._render_detail(spec)
        render_enrichment(spec)
        sensitive = base_environment._is_sensitive_spec(spec)
        print()
        print(f"Estado de decisão: {decision_badge(spec)} | {_selection_state(spec)}")
        if sensitive:
            print(paint("Secret: use sessão/Windows User; nunca será gravado no rasai-console.ini.", YELLOW))
        elif spec.default is not None and not (os.environ.get(spec.name) or "").strip():
            print(paint("Nenhuma ação é necessária para manter o default mostrado acima.", DIM))

        if sensitive:
            print("\nAÇÕES\nS. Definir/alterar na sessão\nR. Remover da sessão\nP. Persistência Windows/User\nD. Documentação\nV. Voltar")
        else:
            print("\nAÇÕES\nS. Definir/alterar override\nR. Remover override e voltar ao default/auto\nD. Documentação\nV. Voltar")
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
            if spec.accepted:
                raw = prompt_guided_value(spec)
                if raw is None:
                    continue
            else:
                if sensitive:
                    raw = prompt_secret(
                        f"Novo valor - {friendly_label(spec)}",
                        input_fn=getpass,
                    )
                else:
                    raw = prompt_text(
                        f"Novo valor - {friendly_label(spec)}",
                        current=os.environ.get(spec.name, ""),
                        empty_keeps_current=False,
                    )
            os.environ[spec.name] = _validate(spec.name, raw)
            if sensitive:
                base_environment._sync_secret_state(state, spec.name)
            base_environment._apply_change(state, spec.name)
            setattr(state, "operation", "LOCAL:CONFIG_UPDATED")
            # Recompose metadata after a dependency such as provider changed.
            refresh_specs()
        except EditCancelled:
            setattr(state, "error", "")
            setattr(state, "operation", "LOCAL:CONFIG_EDIT_CANCELLED")
            continue
        except (ValueError, OverflowError) as exc:
            setattr(state, "error", str(exc))


def _category_menu(state: object, title: str, specs: tuple[EnvironmentSpec, ...]) -> None:
    configured_only = False
    while True:
        base_environment.render_header(state)
        _breadcrumb(title)
        _guidance(title)
        visible = tuple(
            normalize_spec(spec)
            for spec in specs
            if not configured_only or bool((os.environ.get(spec.name) or "").strip())
        )
        if not visible:
            print(paint("Nenhum override/secret definido neste grupo.", DIM))
        for context, rows in grouped_by_context(visible):
            print(paint(f"\n[{context}]", CYAN, bold=True))
            for index, spec in rows:
                status = base_environment._status(spec)
                print(f"{index:2d}. {spec.name:<44} {status:<20} {decision_badge(spec)}")
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


def _search_menu(state: object) -> None:
    """Search the complete configuration registry while preserving result context."""
    from rasai.console_configuration_presentation import friendly_label

    query = ""
    while True:
        refresh_specs()
        if not query:
            base_environment.render_header(state)
            _breadcrumb("Pesquisar configurações")
            query = input("Pesquisar por nome, variável técnica, contexto ou finalidade (V para voltar): ").strip()
            if query.upper() == "V":
                return
        needle = query.casefold()
        matches: list[EnvironmentSpec] = []
        for spec in SPECS:
            context = context_for(spec)
            haystack = " ".join((
                friendly_label(spec),
                spec.name,
                spec.category,
                context,
                str(spec.purpose or ""),
                str(spec.notes or ""),
            )).casefold()
            if needle in haystack:
                matches.append(normalize_spec(spec))
        matches.sort(key=lambda spec: (spec.category.casefold(), context_for(spec).casefold(), friendly_label(spec).casefold()))

        base_environment.render_header(state)
        _breadcrumb("Pesquisar configurações")
        print(f"Pesquisa: {query}")
        print(f"Resultados: {len(matches)}\n")
        if not matches:
            print(paint("Nenhuma configuração encontrada.", DIM))
        else:
            for index, spec in enumerate(matches, 1):
                print(f"{index:2d}. {friendly_label(spec)}")
                print(paint(f"    Variável técnica: {spec.name}", GRAY))
                print(paint(f"    {spec.category} > {context_for(spec)}", DIM))
        print("\nP. Nova pesquisa")
        print("V. Voltar")
        raw = input("Selecione uma configuração ou ação: ").strip().upper()
        if raw == "V":
            return
        if raw == "P":
            query = ""
            continue
        try:
            selected = int(raw) - 1
        except ValueError:
            setattr(state, "error", "opção de pesquisa inválida")
            continue
        if 0 <= selected < len(matches):
            _variable_menu(state, matches[selected])
            # Keep the same query/results after returning from the detail screen.
            continue
        setattr(state, "error", "configuração inválida")


def environment_menu(state: object) -> None:
    """Show the complete registry-aware configuration catalog by functional context."""
    refresh_specs()
    while True:
        # Rebuild category slices each pass so runtime-added/dependent metadata remains
        # current after edits made in nested screens.
        grouped = {category: tuple(spec for spec in SPECS if spec.category == category) for category in CATEGORIES}
        base_environment.render_header(state)
        _breadcrumb("Configuração avançada")
        print("FLUXO RECOMENDADO")
        print("  1. Use o menu principal para Entrada, Device, IA, Web Performance e Apdex.")
        print("  2. Use esta área para integrações, credenciais e overrides avançados.")
        print("  3. Dentro de cada grupo, variáveis relacionadas aparecem juntas por contexto/recurso.")
        print("  4. Valores fechados são selecionados de listas; texto livre fica restrito a dados realmente abertos.")
        print("  5. Salve o INI no menu principal para persistir somente configurações não secretas.")
        print("  6. Antes de executar, revise o preflight; integração ausente não vira finding do website.\n")
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
        print(" P. Pesquisar configuração")
        print(f" D. Abrir documentação detalhada (docs/{DOCUMENT_NAME})")
        print(" V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return
        if raw == "D":
            base_environment._open_docs(state)
            continue
        if raw == "P":
            _search_menu(state)
            continue
        if raw == "A":
            _category_menu(state, "Todas", SPECS)
            continue
        category = choices.get(raw)
        if category:
            _category_menu(state, category, grouped[category])
        else:
            setattr(state, "error", "grupo inválido")