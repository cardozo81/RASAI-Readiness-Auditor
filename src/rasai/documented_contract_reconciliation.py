"""Runtime reconciliation for documented public contracts.

The fixes in this module are intentionally narrow and additive. They keep provider
credentials separate from AUTO-pool membership, make post-run AI cost reporting derive
from persisted telemetry, reconcile the PageSpeed Agentic Browsing category with the
current API contract, clarify optional Search content comparison, and remove misleading
presentation states without changing SARI/SCORE-GEO evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from html import escape
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

AUTO_EXCLUDE_ENV = "RASAI_AI_AUTO_EXCLUDE"
_CURRENT_PSI_CATEGORIES = (
    "performance",
    "accessibility",
    "best-practices",
    "seo",
    "agentic-browsing",
)
_INSTALLED = False


def _registrations():
    from rasai.provider_registry import provider_registrations

    return provider_registrations()


def parse_auto_exclusions(
    raw: str | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Return canonical provider ids excluded from AUTO, preserving registry order."""
    from rasai.provider_registry import get_provider_registration

    environment = os.environ if env is None else env
    text = (environment.get(AUTO_EXCLUDE_ENV) if raw is None else raw) or ""
    requested: set[str] = set()
    for item in text.replace(";", ",").split(","):
        token = item.strip().casefold()
        if not token:
            continue
        registration = get_provider_registration(token)
        if registration is None:
            raise ValueError(f"{AUTO_EXCLUDE_ENV}: provider desconhecido: {item.strip()}")
        if not registration.auto_eligible:
            raise ValueError(
                f"{AUTO_EXCLUDE_ENV}: {registration.id} não é elegível para AUTO"
            )
        requested.add(registration.id)
    return tuple(
        registration.id
        for registration in _registrations()
        if registration.auto_eligible and registration.id in requested
    )


def _set_auto_exclusions(excluded: set[str]) -> None:
    ordered = [
        registration.id
        for registration in _registrations()
        if registration.auto_eligible and registration.id in excluded
    ]
    if ordered:
        os.environ[AUTO_EXCLUDE_ENV] = ",".join(ordered)
    else:
        os.environ.pop(AUTO_EXCLUDE_ENV, None)


def _install_auto_runtime_filter() -> None:
    from rasai import cli, cli_extensions, provider_runtime_policy

    original = provider_runtime_policy.build_semantic_provider
    if getattr(original, "_rasai_auto_member_filter", False):
        return

    def build_semantic_provider(
        selection: str,
        *,
        model_override: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Any:
        if selection.strip().casefold() != "auto":
            return original(selection, model_override=model_override, env=env)
        environment = dict(os.environ if env is None else env)
        excluded = parse_auto_exclusions(env=environment)
        if not excluded:
            return original(selection, model_override=model_override, env=environment)
        for registration in _registrations():
            if registration.id in excluded:
                # Deliberately mask only the copied execution environment. The user's
                # configured key remains intact for explicit provider selection later.
                environment.pop(registration.key_env, None)
        provider = original(selection, model_override=model_override, env=environment)
        current = tuple(getattr(provider, "excluded_configurations", ()) or ())
        rewritten: list[str] = []
        excluded_names = {
            registration.provider_name
            for registration in _registrations()
            if registration.id in excluded
        }
        for item in current:
            text = str(item)
            provider_name = text.split(":", 1)[0]
            if provider_name in excluded_names:
                rewritten.append(f"{provider_name}:USER_EXCLUDED_FROM_AUTO")
            else:
                rewritten.append(text)
        for provider_name in excluded_names:
            marker = f"{provider_name}:USER_EXCLUDED_FROM_AUTO"
            if marker not in rewritten:
                rewritten.append(marker)
        if hasattr(provider, "excluded_configurations"):
            provider.excluded_configurations = tuple(rewritten)
        return provider

    build_semantic_provider._rasai_auto_member_filter = True
    build_semantic_provider._rasai_original = original
    provider_runtime_policy.build_semantic_provider = build_semantic_provider
    # These modules import the builder by value; update their public-runtime references.
    cli_extensions.build_semantic_provider = build_semantic_provider
    cli.build_semantic_provider = build_semantic_provider


def _install_console_auto_capability_filter() -> None:
    from rasai import console_config, console_cost, interactive_console

    original = console_config.provider_capabilities
    if getattr(original, "_rasai_auto_member_filter", False):
        return

    def provider_capabilities(
        env: Mapping[str, str] | None = None,
        blocks: Mapping[str, str] | None = None,
    ):
        environment = os.environ if env is None else env
        result = original(environment, blocks)
        excluded = set(parse_auto_exclusions(env=environment))
        included_ready: list[str] = []
        for registration in _registrations():
            capability = result.get(registration.id)
            if (
                registration.auto_eligible
                and registration.id not in excluded
                and capability is not None
                and capability.available
            ):
                included_ready.append(registration.id)
        included_ids = [
            registration.id
            for registration in _registrations()
            if registration.auto_eligible and registration.id not in excluded
        ]
        pool = " -> ".join(item.upper() for item in included_ids) or "<vazio>"
        excluded_text = ", ".join(item.upper() for item in excluded) or "nenhum"
        result["auto"] = console_config.Capability(
            bool(included_ready),
            (
                f"{len(included_ready)} provider(s) apto(s) incluído(s); pool AUTO {pool}; "
                f"excluídos pelo usuário: {excluded_text}"
            )
            if included_ready
            else (
                f"nenhum provider apto permanece incluído no AUTO; pool {pool}; "
                f"excluídos pelo usuário: {excluded_text}"
            ),
        )
        return result

    provider_capabilities._rasai_auto_member_filter = True
    provider_capabilities._rasai_original = original
    console_config.provider_capabilities = provider_capabilities
    interactive_console.provider_capabilities = provider_capabilities
    console_cost.provider_capabilities = provider_capabilities

    original_models = console_cost._selected_provider_models

    def selected_provider_models(state: Any):
        rows = original_models(state)
        if str(getattr(state, "ai_provider", "")).casefold() != "auto":
            return rows
        excluded_names = {
            registration.provider_name
            for registration in _registrations()
            if registration.id in set(parse_auto_exclusions())
        }
        return tuple(row for row in rows if row[0] not in excluded_names)

    console_cost._selected_provider_models = selected_provider_models


def _install_console_auto_persistence() -> None:
    from rasai import console_config, console_environment, console_m23, console_settings, interactive_console

    original_known = console_settings._known_nonsecret_environment_names
    if not getattr(original_known, "_rasai_auto_member_filter", False):
        def known_nonsecret_environment_names() -> tuple[str, ...]:
            return tuple(dict.fromkeys((*original_known(), AUTO_EXCLUDE_ENV)))

        known_nonsecret_environment_names._rasai_auto_member_filter = True
        console_settings._known_nonsecret_environment_names = known_nonsecret_environment_names

    original_validate = console_config.validate_env_value
    if not getattr(original_validate, "_rasai_auto_member_filter", False):
        def validate_env_value(name: str, value: str) -> str:
            if name == AUTO_EXCLUDE_ENV:
                parsed = parse_auto_exclusions(value)
                return ",".join(parsed)
            if name == "RASAI_LIGHTHOUSE_CATEGORIES":
                values = tuple(
                    dict.fromkeys(
                        item.strip().casefold()
                        for item in value.split(",")
                        if item.strip()
                    )
                )
                allowed = set(_CURRENT_PSI_CATEGORIES)
                if not values or any(item not in allowed for item in values):
                    raise ValueError(
                        "use performance, accessibility, best-practices, seo e/ou agentic-browsing"
                    )
                return ",".join(values)
            return original_validate(name, value)

        validate_env_value._rasai_auto_member_filter = True
        console_config.validate_env_value = validate_env_value
        console_m23.validate_base_env_value = validate_env_value
        console_environment.validate_existing = console_m23.validate_env_value
        interactive_console.validate_env_value = console_m23.validate_env_value

    console_config.ENV_NAMES = tuple(dict.fromkeys((*console_config.ENV_NAMES, AUTO_EXCLUDE_ENV)))
    interactive_console.ENV_NAMES = tuple(dict.fromkeys((*interactive_console.ENV_NAMES, AUTO_EXCLUDE_ENV)))


def _configure_auto_pool(state: Any, console_module: Any) -> bool:
    capabilities = console_module.provider_capabilities(blocks=state.runtime_blocks)
    excluded = set(parse_auto_exclusions())
    auto_registrations = tuple(
        registration for registration in _registrations() if registration.auto_eligible
    )
    while True:
        console_module.render_header(state)
        print("POOL AI=AUTO - a chave continua configurada mesmo quando o provider é excluído do AUTO\n")
        for index, registration in enumerate(auto_registrations, 1):
            capability = capabilities[registration.id]
            apt = "APTA" if capability.available else "INDISPONÍVEL"
            member = "EXCLUÍDA DO AUTO" if registration.id in excluded else "INCLUÍDA NO AUTO"
            print(
                f" {index}. {registration.display_name:<20} [{apt}] [{member}] "
                f"{capability.reason}"
            )
        print("\nDigite o número para alternar inclusão. A = incluir todas. V = concluir.")
        choice = input("Escolha: ").strip().upper()
        if choice == "A":
            excluded.clear()
            capabilities = console_module.provider_capabilities(blocks=state.runtime_blocks)
            continue
        if choice == "V":
            ready = [
                registration.id
                for registration in auto_registrations
                if registration.id not in excluded
                and capabilities[registration.id].available
            ]
            if not ready:
                state.error = "AI=AUTO exige ao menos um provider APTA incluído no pool"
                return False
            _set_auto_exclusions(excluded)
            state.error = ""
            return True
        try:
            registration = auto_registrations[int(choice) - 1]
        except (ValueError, IndexError):
            state.error = "opção inválida para pool AUTO"
            continue
        if registration.id in excluded:
            excluded.remove(registration.id)
        else:
            excluded.add(registration.id)
        # Reflect the prospective set while rendering the next iteration.
        _set_auto_exclusions(excluded)
        capabilities = console_module.provider_capabilities(blocks=state.runtime_blocks)


def _install_console_ai_selector() -> None:
    from rasai import interactive_console
    from rasai.provider_runtime_policy import (
        AI_TIMEOUT_ENV,
        REASONING_OPTIONS,
        apply_console_reasoning_environment,
        configured_reasoning,
    )

    original = interactive_console._configure
    if getattr(original, "_rasai_auto_member_selector", False):
        return

    def configure(state: Any, choice: str) -> None:
        if choice != "4":
            return original(state, choice)
        console = interactive_console
        console.render_header(state)
        capabilities = console.provider_capabilities(blocks=state.runtime_blocks)
        value = console._select(
            state,
            "Provider de IA - APTA indica credencial/configuração válidas; inclusão no AUTO é controlada separadamente",
            [
                (name, capabilities[name].available, capabilities[name].reason)
                for name in console.PROVIDER_MENU_CHOICES
            ],
        )
        if not value:
            return
        state.ai_provider, state.ai_model, state.ai_reasoning = value, None, None
        if value == "none":
            state.content_remediation = False
            state.technical_remediation = False
        elif value in console.PROVIDERS:
            provider_name = console.PROVIDERS[value]
            default = os.environ.get(
                console.MODEL_ENV[provider_name],
                console.DEFAULT_MODELS[provider_name],
            )
            chosen = console._select(
                state,
                f"Modelo {provider_name} - o default público privilegia menor custo/complexidade",
                [
                    (model, True, "default" if model == default else "suportado")
                    for model in console.SUPPORTED_MODELS[provider_name]
                ],
            )
            state.ai_model = chosen or default
            effort_default = configured_reasoning(provider_name)
            efforts = REASONING_OPTIONS[provider_name]
            if len(efforts) == 1:
                state.ai_reasoning = efforts[0]
            else:
                effort = console._select(
                    state,
                    f"Esforço/profundidade {provider_name} - menor nível reduz latência/tokens",
                    [
                        (item, True, "default mínimo" if item == effort_default else "suportado")
                        for item in efforts
                    ],
                )
                state.ai_reasoning = effort or effort_default
                apply_console_reasoning_environment(provider_name, state.ai_reasoning)
        else:
            if not _configure_auto_pool(state, console):
                return
        state.ai_timeout = float(
            console._number(
                "Timeout por tentativa de IA",
                state.ai_timeout,
                minimum=1,
                help_text="limite de espera de cada chamada ao provider. Não é o tempo máximo da auditoria inteira.",
            )
        )
        os.environ[AI_TIMEOUT_ENV] = f"{state.ai_timeout:g}"
        state.error = ""

    configure._rasai_auto_member_selector = True
    configure._rasai_original = original
    interactive_console._configure = configure


def _install_current_pagespeed_categories() -> None:
    from rasai import cli, console_config, m21_web_performance

    m21_web_performance.DEFAULT_CATEGORIES = _CURRENT_PSI_CATEGORIES
    m21_web_performance.ALLOWED_CATEGORIES = frozenset(_CURRENT_PSI_CATEGORIES)
    cli.DEFAULT_CATEGORIES = _CURRENT_PSI_CATEGORIES

    original_init = m21_web_performance.WebPerformanceConfig.__init__
    if not getattr(original_init, "_rasai_agentic_default", False):
        def init(
            self,
            enabled: bool = False,
            max_pages: int = 10,
            timeout_seconds: float = 120.0,
            categories: tuple[str, ...] | None = None,
            field_source: str = "auto",
            pagespeed_api_key: str | None = None,
            crux_api_key: str | None = None,
        ) -> None:
            original_init(
                self,
                enabled=enabled,
                max_pages=max_pages,
                timeout_seconds=timeout_seconds,
                categories=_CURRENT_PSI_CATEGORIES if categories is None else categories,
                field_source=field_source,
                pagespeed_api_key=pagespeed_api_key,
                crux_api_key=crux_api_key,
            )

        init._rasai_agentic_default = True
        m21_web_performance.WebPerformanceConfig.__init__ = init

    original_apply = console_config.apply_environment_defaults
    if not getattr(original_apply, "_rasai_agentic_default", False):
        def apply_environment_defaults(state: Any, env=None, names=None):
            issues = original_apply(state, env, names)
            environment = os.environ if env is None else env
            explicit = names is None or "RASAI_LIGHTHOUSE_CATEGORIES" in names
            raw = (environment.get("RASAI_LIGHTHOUSE_CATEGORIES") or "").strip()
            if explicit and raw:
                state.lighthouse_categories = raw
            elif not raw and state.lighthouse_categories == "performance,accessibility,best-practices,seo":
                # Every previous console default was four categories because Agentic
                # was not yet transportable. Current PSI now supports it.
                state.lighthouse_categories = ",".join(_CURRENT_PSI_CATEGORIES)
            return issues

        apply_environment_defaults._rasai_agentic_default = True
        console_config.apply_environment_defaults = apply_environment_defaults


def _format_cost(value: Decimal) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


def _db_ai_costs(database: Path) -> dict[str, dict[str, Decimal]]:
    totals: dict[str, dict[str, Decimal]] = {}
    if not database.is_file():
        return totals
    connection = sqlite3.connect(database)
    try:
        for table, label_sql in (
            (
                "ai_provider_attempts",
                "CASE WHEN semantic_contract_version LIKE 'M24-%' THEN 'Remediação técnica por IA' ELSE 'Análise semântica por IA' END",
            ),
            ("content_remediation_attempts", "'Remediação textual por IA'"),
        ):
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not exists:
                continue
            rows = connection.execute(
                f"SELECT {label_sql},cost_currency,SUM(estimated_cost) "
                f"FROM {table} WHERE estimated_cost IS NOT NULL AND cost_currency IS NOT NULL "
                "GROUP BY 1,cost_currency"
            ).fetchall()
            for label, currency, amount in rows:
                totals.setdefault(str(currency), {})[str(label)] = (
                    totals.setdefault(str(currency), {}).get(str(label), Decimal("0"))
                    + Decimal(str(amount))
                )
    finally:
        connection.close()
    return totals


def _install_ai_cost_report_fix() -> None:
    from rasai import report_navigation

    original = report_navigation._enhance_ai_cost_total
    if getattr(original, "_rasai_persisted_ai_cost", False):
        return

    def enhance_ai_cost_total(report_dir: Path) -> None:
        path = report_dir / "ai-usage.html"
        if not path.is_file():
            return
        totals = _db_ai_costs(report_dir.parent / "audit.db")
        if not totals:
            return original(report_dir)
        html = path.read_text(encoding="utf-8")
        html = report_navigation._AI_COST_TOTAL_RE.sub("", html)
        banners: list[str] = []
        for currency, components in sorted(totals.items()):
            total = sum(components.values(), Decimal("0"))
            breakdown = " + ".join(
                f"{label} {_format_cost(amount)} {currency}"
                for label, amount in sorted(components.items())
            )
            banners.append(
                "<section class='notice cost-total' data-api-cost-total='true'>"
                f"<strong>Custo estimado total de IA com telemetria persistida: {_format_cost(total)} {escape(currency)}</strong>"
                f"<span class='cost-breakdown'>{escape(breakdown)}. "
                "Estimativa técnica pós-execução baseada em tokens/pricing persistidos; não substitui billing/invoice e não inventa custo para chamadas sem usage retornado.</span>"
                "</section>"
            )
        html = html.replace("</header>", "</header>" + "".join(banners), 1)
        path.write_text(html, encoding="utf-8", newline="\n")

    enhance_ai_cost_total._rasai_persisted_ai_cost = True
    enhance_ai_cost_total._rasai_original = original
    report_navigation._enhance_ai_cost_total = enhance_ai_cost_total


def _install_ai_usage_presentation_fix() -> None:
    from rasai import report_ai_runtime_enrichment, report_navigation, report_semantics

    report_ai_runtime_enrichment._RUNTIME_STYLE = (
        report_ai_runtime_enrichment._RUNTIME_STYLE.replace(
            "background:var(--code-bg,#f6f7f9);", "background:transparent;"
        )
    )
    css = (
        "\n.result-tag .badge.good,.result-tag .badge.warn,.result-tag .badge.bad,"
        ".result-tag .badge.info,.result-tag .badge.unknown{background:transparent}\n"
    )
    if ".result-tag .badge.good" not in report_semantics.SEMANTIC_CSS:
        report_semantics.SEMANTIC_CSS += css
    if ".result-tag .badge.good" not in report_navigation.SEMANTIC_CSS:
        report_navigation.SEMANTIC_CSS += css


def _install_scoring_wording_fix() -> None:
    from rasai import report_registry

    original = report_registry._normalize_known_legacy_wording
    if getattr(original, "_rasai_weighted_overall_wording", False):
        return

    def normalize(html: str, *, page_name: str) -> str:
        updated = original(html, page_name=page_name)
        stale = (
            "média aritmética de igual peso das dimensões aplicáveis que possuem valor e não estão em "
            "<code>NOT_CONSOLIDATED</code>. Uma dimensão legitimamente <code>NOT_APPLICABLE</code> sai do denominador."
        )
        current = (
            "média ponderada pelos pesos versionados das dimensões aplicáveis e efetivamente medidas, "
            "com renormalização do denominador. Uma dimensão legitimamente <code>NOT_APPLICABLE</code> "
            "sai do denominador; dimensão aplicável sem valor reduz Coverage/Confidence sem receber zero artificial."
        )
        return updated.replace(stale, current)

    normalize._rasai_weighted_overall_wording = True
    normalize._rasai_original = original
    report_registry._normalize_known_legacy_wording = normalize


def _install_crawling_capture_wording_fix() -> None:
    from rasai import m24_reporting

    original = m24_reporting._captured_resources_block
    if getattr(original, "_rasai_captured_artifact_wording", False):
        return

    def captured_resources_block(resources: list[dict[str, Any]]) -> str:
        html = original(resources)
        html = html.replace(
            "<h2>robots.txt, sitemaps e llms.txt observados</h2>",
            "<h2>Artifacts textuais efetivamente preservados</h2>",
        )
        html = html.replace(
            "Nenhum artifact textual capturado está disponível para exibição nesta auditoria.",
            "Nenhum artifact textual foi preservado para exibição. Recursos ausentes ou indisponíveis permanecem descritos pelo estado e pelos diagnósticos; não é criado accordion sem conteúdo capturado.",
        )
        html = html.replace(
            "Conteúdo read-only dos arquivos efetivamente preservados pela auditoria. Abrir um item não executa nova coleta.",
            "Conteúdo read-only das respostas/artifacts efetivamente preservados pela auditoria. Um recurso pode estar ausente e ainda possuir uma resposta HTTP capturada; recursos sem artifact, como um llms.txt 404 não preservado, permanecem somente no estado/diagnóstico. Abrir um item não executa nova coleta.",
        )
        return html

    captured_resources_block._rasai_captured_artifact_wording = True
    captured_resources_block._rasai_original = original
    m24_reporting._captured_resources_block = captured_resources_block


def _install_search_comparison_guidance() -> None:
    from rasai.search_intelligence import reporting

    original = reporting._competitive_section
    if getattr(original, "_rasai_comparison_guidance", False):
        return

    def competitive_section(analysis, classified_results, pages):
        html = original(analysis, classified_results, pages)
        status = str((analysis or {}).get("comparison_status") or "")
        if status != "CONTENT_COMPARISON_DISABLED":
            return html
        notice = (
            "<div class='notice search-comparison-disabled'><strong>Por que as listas estão vazias:</strong> "
            "esta execução fez apenas classificação determinística dos resultados SERP. Nenhuma página concorrente/cliente foi adquirida para comparação de conteúdo, portanto não existem gaps de título, headings, corpo ou structured data a materializar. "
            "No console, habilite explicitamente a comparação de conteúdo para coletar esse universo limitado. A análise por IA continua uma etapa separada e opt-in e só pode recomendar sobre evidências consolidadas, sem afirmar causalidade de ranking.</div>"
        )
        return html.replace("</section>", notice + "</section>", 1)

    competitive_section._rasai_comparison_guidance = True
    competitive_section._rasai_original = original
    reporting._competitive_section = competitive_section


def _install_console_search_content_comparison() -> None:
    from rasai import console_search_intelligence, interactive_console

    base = interactive_console.State
    if not hasattr(base, "__dataclass_fields__"):
        return
    if "search_compare_content" not in base.__dataclass_fields__:
        @dataclass(slots=True)
        class ReconciledSearchConsoleState(base):
            search_compare_content: bool = False

        interactive_console.State = ReconciledSearchConsoleState

    original_configure = console_search_intelligence.configure_search_intelligence
    if not getattr(original_configure, "_rasai_content_compare", False):
        def configure_search_intelligence(state: Any) -> None:
            original_configure(state)
            if not tuple(getattr(state, "search_queries", ()) or ()) or state.error:
                return
            print(
                "\nComparação de conteúdo é opcional e acrescenta aquisição HTTP limitada das páginas públicas selecionadas."
            )
            state.search_compare_content = console_search_intelligence._yes_no(
                "Comparar conteúdo público do domínio auditado com candidatos SERP à frente?",
                bool(getattr(state, "search_compare_content", False)),
            )

        configure_search_intelligence._rasai_content_compare = True
        configure_search_intelligence._rasai_original = original_configure
        console_search_intelligence.configure_search_intelligence = configure_search_intelligence

    original_argv = console_search_intelligence.build_search_argv
    if not getattr(original_argv, "_rasai_content_compare", False):
        def build_search_argv(state: Any, *, workspace: Path, target_url: str, env=None):
            argv = original_argv(
                state,
                workspace=workspace,
                target_url=target_url,
                env=env,
            )
            if bool(getattr(state, "search_compare_content", False)):
                if "--compare-content" not in argv:
                    argv.append("--compare-content")
                # The console's runtime executes each query independently, so the same
                # audited customer URL is an unambiguous explicit comparison target.
                if "--customer-url" not in argv:
                    argv.extend(["--customer-url", target_url])
            return argv

        build_search_argv._rasai_content_compare = True
        build_search_argv._rasai_original = original_argv
        console_search_intelligence.build_search_argv = build_search_argv

    original_menu = console_search_intelligence._render_menu_extension
    if not getattr(original_menu, "_rasai_content_compare", False):
        def render_menu_extension(state: Any) -> None:
            original_menu(state)
            if tuple(getattr(state, "search_queries", ()) or ()):
                print(
                    "   Comparação conteúdo    : "
                    + ("ATIVA (HTTP adicional limitado)" if bool(getattr(state, "search_compare_content", False)) else "DESATIVADA (somente classificação SERP)")
                )

        render_menu_extension._rasai_content_compare = True
        console_search_intelligence._render_menu_extension = render_menu_extension


def _install_m24_fallback_telemetry_fix() -> None:
    from rasai import m24_ai

    original = m24_ai.maybe_remediate_m24
    if getattr(original, "_rasai_fallback_telemetry", False):
        return

    def maybe_remediate_m24(*, audit_id: str, workspace: Any, provider: Any, diagnostics: Any):
        result = original(
            audit_id=audit_id,
            workspace=workspace,
            provider=provider,
            diagnostics=diagnostics,
        )
        database = Path(workspace.database)
        try:
            connection = sqlite3.connect(database)
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT attempt_id,provider,status,error_class,error_code,http_status,attempt_index
                   FROM ai_provider_attempts
                   WHERE audit_id=? AND semantic_contract_version='M24-TECHNICAL-REMEDIATION-v2'
                   ORDER BY attempt_index,started_at,attempt_id""",
                (audit_id,),
            ).fetchall()
            if len(rows) <= 1:
                connection.close()
                return result
            with connection:
                previous = None
                for index, row in enumerate(rows):
                    is_last = index == len(rows) - 1
                    if not is_last and str(row["status"]) != "SUCCESS":
                        connection.execute(
                            "UPDATE ai_provider_attempts SET decision='FALLBACK' WHERE attempt_id=?",
                            (row["attempt_id"],),
                        )
                    if previous is not None:
                        reason_parts = [
                            str(previous["error_class"] or "AI_PROVIDER_UNAVAILABLE"),
                            str(previous["error_code"] or ""),
                            f"HTTP_{previous['http_status']}" if previous["http_status"] is not None else "",
                        ]
                        fallback_reason = ":".join(part for part in reason_parts if part)
                        decision = (
                            "FALLBACK_SUCCESS"
                            if str(row["status"]) == "SUCCESS"
                            else ("STOP" if is_last else "FALLBACK")
                        )
                        connection.execute(
                            """UPDATE ai_provider_attempts
                               SET fallback_from_provider=?,fallback_reason=?,decision=?
                               WHERE attempt_id=?""",
                            (
                                str(previous["provider"]),
                                fallback_reason,
                                decision,
                                row["attempt_id"],
                            ),
                        )
                    previous = row
            connection.close()
        except sqlite3.Error:
            pass
        return result

    maybe_remediate_m24._rasai_fallback_telemetry = True
    maybe_remediate_m24._rasai_original = original
    m24_ai.maybe_remediate_m24 = maybe_remediate_m24


def install_documented_contract_reconciliation() -> None:
    """Install reconciliation hooks before public CLI/console work starts."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_auto_runtime_filter()
    _install_console_auto_capability_filter()
    _install_console_auto_persistence()
    _install_current_pagespeed_categories()
    _install_ai_cost_report_fix()
    _install_ai_usage_presentation_fix()
    _install_scoring_wording_fix()
    _install_crawling_capture_wording_fix()
    _install_search_comparison_guidance()
    _install_m24_fallback_telemetry_fix()
    _INSTALLED = True


def install_console_documented_contract_reconciliation() -> None:
    """Install runtime hooks plus console adapters after console extensions compose."""
    install_documented_contract_reconciliation()
    _install_console_ai_selector()
    _install_console_search_content_comparison()
