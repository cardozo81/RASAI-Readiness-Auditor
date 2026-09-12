"""Small runtime extensions that close additive reporting/provider gaps.

These patches keep public console/help and report surfaces aligned with the canonical
runtime contracts without changing SARI arithmetic or evaluated website facts.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any


# Current PageSpeed Insights v5 accepts Agentic Browsing together with the stable
# Lighthouse categories. Agentic remains experimental and outside SARI-001.
_PAGESPEED_LIGHTHOUSE_CATEGORIES = (
    "performance",
    "accessibility",
    "best-practices",
    "seo",
    "agentic-browsing",
)
_PAGESPEED_LIGHTHOUSE_CATEGORIES_CSV = ",".join(_PAGESPEED_LIGHTHOUSE_CATEGORIES)
_AI_EXCHANGE_LOG_MAX_BYTES_ENV = "RASAI_AI_EXCHANGE_LOG_MAX_BYTES"
_PRESENTATION_TIMEZONE_ENV = "RASAI_PRESENTATION_TIMEZONE"
_APDEX_ACQUISITION_MODE_ENV = "RASAI_APDEX_ACQUISITION_MODE"
_AI_ANALYSIS_LANGUAGE_ENV = "RASAI_AI_ANALYSIS_LANGUAGE"
_IMPROVEMENT_ENABLED_ENV = "RASAI_IMPROVEMENT_INTELLIGENCE"
_IMPROVEMENT_PROVIDER_ENV = "RASAI_IMPROVEMENT_AI_PROVIDER"
_IMPROVEMENT_MODEL_ENV = "RASAI_IMPROVEMENT_AI_MODEL"
_IMPROVEMENT_REASONING_ENV = "RASAI_IMPROVEMENT_AI_REASONING"
_IMPROVEMENT_DOMAINS_ENV = "RASAI_IMPROVEMENT_DOMAINS"
_IMPROVEMENT_MAX_RECOMMENDATIONS_ENV = "RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS"
_IMPROVEMENT_TIMEOUT_ENV = "RASAI_IMPROVEMENT_AI_TIMEOUT_SECONDS"
_IMPROVEMENT_ENV_NAMES = (
    _AI_ANALYSIS_LANGUAGE_ENV,
    _IMPROVEMENT_ENABLED_ENV,
    _IMPROVEMENT_PROVIDER_ENV,
    _IMPROVEMENT_MODEL_ENV,
    _IMPROVEMENT_REASONING_ENV,
    _IMPROVEMENT_DOMAINS_ENV,
    _IMPROVEMENT_MAX_RECOMMENDATIONS_ENV,
    _IMPROVEMENT_TIMEOUT_ENV,
)


def install_runtime_completion_extensions() -> None:
    """Install all additive completion patches idempotently."""
    _install_m21_runtime_contract()
    _install_cli_help()
    _install_console_environment()
    _install_improvement_environment_contract()
    _install_console_cost()
    _install_dashboard_metrics()
    _install_monitoring_metrics()
    _install_agentic_provenance()
    _install_gemini_diagnostics()


def _install_m21_runtime_contract() -> None:
    """Keep stale imports/config surfaces aligned with current PageSpeed categories."""
    from rasai import m21_web_performance as m21

    m21.DEFAULT_CATEGORIES = _PAGESPEED_LIGHTHOUSE_CATEGORIES
    m21.ALLOWED_CATEGORIES = frozenset(_PAGESPEED_LIGHTHOUSE_CATEGORIES)


def _install_cli_help() -> None:
    from rasai import cli_extensions

    if getattr(cli_extensions, "_rasai_runtime_help_current", False):
        return
    original = cli_extensions.build_parser

    def build_parser_with_current_help():
        parser = original()
        subparsers = next(
            action
            for action in parser._actions
            if getattr(action, "choices", None) and "audit" in action.choices
        )
        audit_parser = subparsers.choices["audit"]
        for action in audit_parser._actions:
            if action.dest == "lighthouse_categories":
                action.default = _PAGESPEED_LIGHTHOUSE_CATEGORIES_CSV
                action.help = (
                    "comma-separated PageSpeed/Lighthouse categories: "
                    + _PAGESPEED_LIGHTHOUSE_CATEGORIES_CSV
                    + "; Agentic Browsing is experimental and remains outside SARI-001"
                )
            elif action.dest in {"ai_provider", "semantic_provider"}:
                action.help = (
                    "semantic analysis provider; AUTO considers every registered provider with "
                    "valid credentials/configuration, rotates eligible providers round-robin across "
                    "AI needs, uses at most one attempt per provider per need, and applies an "
                    "execution-wide circuit breaker; explicit provider selection keeps its own retry policy"
                )
        return parser

    cli_extensions.build_parser = build_parser_with_current_help
    cli_extensions._rasai_runtime_help_current = True


def _install_console_environment() -> None:
    from rasai import console_environment

    if getattr(console_environment, "_rasai_pagespeed_categories_current", False):
        return
    original_fixed_specs = console_environment._fixed_specs
    original_validate = console_environment._validate

    for name in (_AI_EXCHANGE_LOG_MAX_BYTES_ENV, _PRESENTATION_TIMEZONE_ENV, _APDEX_ACQUISITION_MODE_ENV):
        if name not in console_environment.ENV_NAMES:
            console_environment.ENV_NAMES = (*console_environment.ENV_NAMES, name)

    def fixed_specs_with_current_pagespeed_contract():
        items = []
        for spec in original_fixed_specs():
            if spec.name == "RASAI_LIGHTHOUSE_CATEGORIES":
                spec = replace(
                    spec,
                    accepted=_PAGESPEED_LIGHTHOUSE_CATEGORIES,
                    default=_PAGESPEED_LIGHTHOUSE_CATEGORIES_CSV,
                    example=f"RASAI_LIGHTHOUSE_CATEGORIES={_PAGESPEED_LIGHTHOUSE_CATEGORIES_CSV}",
                    notes=(
                        "Uma ou mais categorias aceitas pelo provider PageSpeed, separadas por vírgula, "
                        "sem duplicar. Agentic Browsing é experimental e pode ficar indisponível na resposta."
                    ),
                )
            items.append(spec)
        if not any(spec.name == _PRESENTATION_TIMEZONE_ENV for spec in items):
            items.append(
                console_environment.EnvironmentSpec(
                    _PRESENTATION_TIMEZONE_ENV,
                    "Aplicação e execução",
                    "Timezone IANA usado apenas na camada de apresentação dos relatórios e do console.",
                    "timezone IANA",
                    default="America/Sao_Paulo",
                    required_when="Opcional; use somente para substituir o timezone padrão de apresentação.",
                    impact="Sem efeito no instante canônico UTC, scoring, coleta ou audit.db.",
                    example="RASAI_PRESENTATION_TIMEZONE=Europe/London",
                    notes="Use identificador IANA. Offsets fixos como -03:00 não são aceitos como preferência persistida.",
                )
            )
        if not any(spec.name == _APDEX_ACQUISITION_MODE_ENV for spec in items):
            items.append(
                console_environment.EnvironmentSpec(
                    _APDEX_ACQUISITION_MODE_ENV,
                    "Synthetic Apdex",
                    "Controla somente o compartilhamento da aquisição física entre Navigation Apdex e Experience Apdex.",
                    "enum",
                    ("auto", "isolated"),
                    "auto",
                    required_when="Nunca; auto é o default seguro e só compartilha aquisições comprovadamente compatíveis.",
                    impact="auto pode reduzir navegações físicas contra o alvo; não altera targets, device mix, thresholds ou scores.",
                    example="RASAI_APDEX_ACQUISITION_MODE=isolated",
                    source="docs/SYNTHETIC_SHARED_ACQUISITION.md",
                    notes="Use isolated para comparação/troubleshooting. Não existe modo de compartilhamento forçado.",
                )
            )
        return tuple(items)

    def validate_with_current_contract(name: str, raw: str) -> str:
        if name == "RASAI_LIGHTHOUSE_CATEGORIES":
            value = raw.strip()
            if not value:
                raise ValueError("valor vazio; remova a variável em vez de gravar vazio")
            items = [item.strip().casefold() for item in value.split(",") if item.strip()]
            if not items or any(item not in _PAGESPEED_LIGHTHOUSE_CATEGORIES for item in items):
                raise ValueError(
                    "categorias PageSpeed suportadas: " + ", ".join(_PAGESPEED_LIGHTHOUSE_CATEGORIES)
                )
            if len(items) != len(set(items)):
                raise ValueError("não duplique categorias Lighthouse")
            return ",".join(items)
        if name == _AI_EXCHANGE_LOG_MAX_BYTES_ENV:
            value = raw.strip()
            try:
                parsed = int(value)
            except ValueError as exc:
                raise ValueError("use inteiro entre 4096 e 4194304") from exc
            if not 4096 <= parsed <= 4194304:
                raise ValueError("use inteiro entre 4096 e 4194304")
            return str(parsed)
        if name == _PRESENTATION_TIMEZONE_ENV:
            from rasai.time_contract import validate_presentation_timezone

            return validate_presentation_timezone(raw)
        return original_validate(name, raw)

    console_environment._fixed_specs = fixed_specs_with_current_pagespeed_contract
    console_environment._validate = validate_with_current_contract
    # SPECS is materialized at import time. Rebuild it after patching the source
    # factories so the actual interactive UI, tests and ENV_NAMES stay coherent.
    console_environment.SPECS = console_environment.environment_specs()
    console_environment.SPEC_BY_NAME = {spec.name: spec for spec in console_environment.SPECS}
    console_environment._rasai_pagespeed_categories_current = True


def _install_improvement_environment_contract() -> None:
    """Expose every Improvement Intelligence runtime setting through the guided console catalog."""
    from rasai import console_environment
    from rasai.improvement_intelligence import DEFAULT_DOMAINS, parse_domains, validate_analysis_language
    from rasai.provider_registry import get_provider_registration, provider_registrations

    if getattr(console_environment, "_rasai_improvement_environment_current", False):
        return
    original_fixed_specs = console_environment._fixed_specs
    original_validate = console_environment._validate

    for name in _IMPROVEMENT_ENV_NAMES:
        if name not in console_environment.ENV_NAMES:
            console_environment.ENV_NAMES = (*console_environment.ENV_NAMES, name)
    if "IA - análise profunda" not in console_environment.CATEGORIES:
        categories = list(console_environment.CATEGORIES)
        insert_at = categories.index("IA - contexto editorial / YMYL") + 1
        categories.insert(insert_at, "IA - análise profunda")
        console_environment.CATEGORIES = tuple(categories)

    provider_ids = tuple(item.id for item in provider_registrations())
    domains_csv = ",".join(DEFAULT_DOMAINS)

    def fixed_specs_with_improvement_contract():
        items = list(original_fixed_specs())
        known = {item.name for item in items}

        def add(spec: Any) -> None:
            if spec.name not in known:
                items.append(spec)
                known.add(spec.name)

        add(
            console_environment.EnvironmentSpec(
                _AI_ANALYSIS_LANGUAGE_ENV,
                "IA - contexto editorial / YMYL",
                "Idioma preferencial das explicações e sugestões geradas por IA; auto usa o idioma da auditoria sem substituir a detecção do conteúdo.",
                "tag BCP-47 ou auto",
                default="auto",
                impact="Sem custo externo direto; altera somente idioma preferencial de leitura/resposta.",
                example="RASAI_AI_ANALYSIS_LANGUAGE=pt-BR",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            )
        )
        add(
            console_environment.EnvironmentSpec(
                _IMPROVEMENT_ENABLED_ENV,
                "IA - análise profunda",
                "Habilita Improvement Intelligence evidence-bound para uma única URL explícita.",
                "booleano",
                ("true", "false"),
                "false",
                required_when="Somente com exatamente uma URL de entrada e provider explícito apto.",
                impact="Quando true, pode gerar chamadas adicionais de IA, tokens, latência e custo.",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            )
        )
        add(
            console_environment.EnvironmentSpec(
                _IMPROVEMENT_PROVIDER_ENV,
                "IA - análise profunda",
                "Provider explícito usado somente pela análise profunda; reutiliza a credencial já configurada.",
                "provider explícito",
                provider_ids,
                None,
                required_when="Obrigatório quando RASAI_IMPROVEMENT_INTELLIGENCE=true; AUTO/NONE não são permitidos.",
                impact="Seleciona qual provider poderá gerar cobrança na análise profunda.",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            )
        )
        add(
            console_environment.EnvironmentSpec(
                _IMPROVEMENT_MODEL_ENV,
                "IA - análise profunda",
                "Override de modelo exclusivo da análise profunda.",
                "modelo suportado pelo provider selecionado",
                default=None,
                required_when="Opcional; vazio usa o modelo público default do provider selecionado.",
                impact="Modelo pode alterar capacidade, latência, tokens e custo.",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            )
        )
        add(
            console_environment.EnvironmentSpec(
                _IMPROVEMENT_REASONING_ENV,
                "IA - análise profunda",
                "Esforço/reasoning exclusivo da análise profunda.",
                "valor suportado pelo provider selecionado",
                default=None,
                required_when="Opcional; vazio usa o maior perfil suportado definido pelo contrato da feature.",
                impact="Esforço maior pode elevar latência, tokens e custo.",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            )
        )
        add(
            console_environment.EnvironmentSpec(
                _IMPROVEMENT_DOMAINS_ENV,
                "IA - análise profunda",
                "Domínios correlacionados pela análise profunda.",
                "lista CSV",
                tuple(DEFAULT_DOMAINS),
                domains_csv,
                required_when="Opcional; o default inclui todos os domínios suportados.",
                impact="Mais domínios podem aumentar contexto enviado, tokens e profundidade da resposta.",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            )
        )
        add(
            console_environment.EnvironmentSpec(
                _IMPROVEMENT_MAX_RECOMMENDATIONS_ENV,
                "IA - análise profunda",
                "Teto de recomendações materializadas pela análise profunda.",
                "inteiro 1..100",
                default="30",
                required_when="Opcional; limite de custo/volume do output.",
                impact="Limite maior pode elevar output tokens e custo.",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            )
        )
        add(
            console_environment.EnvironmentSpec(
                _IMPROVEMENT_TIMEOUT_ENV,
                "IA - análise profunda",
                "Timeout da tentativa estruturada de Improvement Intelligence.",
                "número > 0 (segundos)",
                default="240",
                required_when="Opcional; use override somente quando o provider/modelo exigir outra janela.",
                impact="Timeout maior amplia tempo máximo de espera, sem garantir sucesso.",
                source="docs/IMPROVEMENT_INTELLIGENCE.md",
            )
        )
        return tuple(items)

    def validate_with_improvement_contract(name: str, raw: str) -> str:
        if name not in _IMPROVEMENT_ENV_NAMES:
            return original_validate(name, raw)
        value = raw.strip()
        if not value:
            raise ValueError("valor vazio; remova a variável em vez de gravar vazio")
        if name == _AI_ANALYSIS_LANGUAGE_ENV:
            return validate_analysis_language(value)
        if name == _IMPROVEMENT_ENABLED_ENV:
            normalized = value.casefold()
            if normalized not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
                raise ValueError("use true/false")
            return normalized
        if name == _IMPROVEMENT_PROVIDER_ENV:
            provider = value.casefold()
            registration = get_provider_registration(provider)
            if registration is None or provider in {"auto", "none"}:
                raise ValueError("use um provider explícito registrado; AUTO/NONE não são permitidos")
            return registration.id
        if name == _IMPROVEMENT_REASONING_ENV:
            return value.upper()
        if name == _IMPROVEMENT_DOMAINS_ENV:
            return ",".join(parse_domains(value))
        if name == _IMPROVEMENT_MAX_RECOMMENDATIONS_ENV:
            parsed = int(value)
            if parsed < 1 or parsed > 100:
                raise ValueError("use inteiro entre 1 e 100")
            return str(parsed)
        if name == _IMPROVEMENT_TIMEOUT_ENV:
            parsed = float(value)
            if parsed <= 0:
                raise ValueError("use número > 0")
            return f"{parsed:g}"
        if name == _IMPROVEMENT_MODEL_ENV:
            provider = __import__("os").environ.get(_IMPROVEMENT_PROVIDER_ENV, "").strip().casefold()
            registration = get_provider_registration(provider) if provider else None
            if registration is not None and value not in registration.supported_models:
                raise ValueError(
                    f"modelo não suportado por {registration.display_name}; use {', '.join(registration.supported_models)}"
                )
            return value
        return value

    console_environment._fixed_specs = fixed_specs_with_improvement_contract
    console_environment._validate = validate_with_improvement_contract
    console_environment.SPECS = console_environment.environment_specs()
    console_environment.SPEC_BY_NAME = {spec.name: spec for spec in console_environment.SPECS}

    # The provider-aware facade is imported before runtime extensions by the public
    # console entrypoint. Refresh it after composing the base catalog so the actual
    # user-facing menu sees the same variables, categories and validation metadata.
    try:
        from rasai import console_provider_environment
        console_provider_environment.refresh_specs()
    except Exception:
        pass

    console_environment._rasai_improvement_environment_current = True


def _install_console_cost() -> None:
    """Keep the pre-run exposure explanation consistent with dynamic AUTO routing."""
    from rasai import console_cost

    if getattr(console_cost, "_rasai_dynamic_auto_exposure_current", False):
        return
    original = console_cost.estimate_exposure

    def estimate_exposure_with_dynamic_auto(state):
        estimate = original(state)
        if state.ai_provider != "auto":
            return estimate
        provider_count = len(console_cost._selected_provider_models(state))
        reasons: list[str] = []
        for reason in estimate.reasons:
            if reason.startswith("IA ativa:"):
                reasons.append(
                    f"IA AUTO ativa: até {estimate.max_ai_attempts} chamada(s) potenciais no pior caso "
                    f"da configuração atual. Cada necessidade visita no máximo {provider_count} provider(s) "
                    "e cada provider é tentado no máximo uma vez naquela necessidade; remediações opcionais "
                    "podem criar necessidades adicionais."
                )
                continue
            if reason.startswith("AUTO considera somente a cadeia homologada"):
                continue
            reasons.append(reason)
        reasons.append(
            f"AUTO possui {provider_count} provider(s) apto(s) na projeção atual; a ordem efetiva usa "
            "round-robin e pode encolher durante a execução por falha terminal ou circuit breaker."
        )
        return replace(estimate, reasons=tuple(reasons))

    console_cost.estimate_exposure = estimate_exposure_with_dynamic_auto
    console_cost._rasai_dynamic_auto_exposure_current = True


def _install_dashboard_metrics() -> None:
    from rasai import rasai_readiness_reporting as reporting

    if getattr(reporting, "_rasai_extended_lighthouse_dashboard", False):
        return
    original_dashboard = reporting._dashboard

    def dashboard_with_extended_lighthouse(data: dict[str, Any], report_dir):
        html = original_dashboard(data, report_dir)
        web = data.get("web", [])
        specifications = (
            ("Lighthouse Best Practices", "best_practices_score", "Chrome Lighthouse via PageSpeed", "web-performance.html"),
            ("Lighthouse SEO técnico", "seo_score", "Chrome Lighthouse via PageSpeed", "web-performance.html"),
        )
        additions: list[str] = []
        for title, column, source, href in specifications:
            if f"<h3>{title}</h3>" in html:
                continue
            value, detail = reporting._device_ranges(web, column, scale=1.0, suffix="/100")
            condition, condition_label = reporting._lighthouse_condition(web, column)
            additions.append(reporting._indicator_card(title, value, detail, href, source, condition, condition_label))
        if not additions:
            return html
        target = "</div></section>" + reporting._DASHBOARD_END
        if target not in html:
            return html
        return html.replace(target, "".join(additions) + target, 1)

    reporting._dashboard = dashboard_with_extended_lighthouse
    reporting._rasai_extended_lighthouse_dashboard = True


def _install_monitoring_metrics() -> None:
    from rasai.monitoring import reader

    if getattr(reader, "_rasai_extended_lighthouse_monitoring", False):
        return
    original = reader._read_performance

    def read_performance_with_extended_categories(connection, tables: set[str], audit_id: str, signals: dict[str, Any]) -> None:
        original(connection, tables, audit_id, signals)
        if "web_performance_observations" not in tables:
            return
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(web_performance_observations)").fetchall()}
        if "best_practices_score" not in columns:
            return
        rows = connection.execute(
            "SELECT * FROM web_performance_observations WHERE audit_id=? ORDER BY captured_at,rowid",
            (audit_id,),
        ).fetchall()
        latest: dict[tuple[str, str], Any] = {}
        for row in rows:
            latest[(str(row["device"]).upper(), str(row["url"]))] = row
        for (device, url), row in latest.items():
            value = row["best_practices_score"]
            if value is None:
                continue
            names = set(row.keys())
            key = f"PERF|{device}|{url}|best_practices_score"
            signals[key] = reader.Signal(
                key=key,
                domain="PERFORMANCE",
                label="Lighthouse Best Practices",
                value=float(value),
                device=device,
                url=url,
                severity="MEDIUM",
                direction="HIGHER_BETTER",
                unit="score",
                metadata={
                    "field_source": row["field_source"] if "field_source" in names else None,
                    "field_scope": row["field_scope"] if "field_scope" in names else None,
                    "captured_at": row["captured_at"] if "captured_at" in names else None,
                },
            )

    reader._read_performance = read_performance_with_extended_categories
    reader._rasai_extended_lighthouse_monitoring = True


def _install_agentic_provenance() -> None:
    from rasai import indicator_provenance as provenance

    if any("Agentic Browsing" in item.indicator for item in provenance.INDICATORS):
        return
    provenance.INDICATORS += (
        provenance.IndicatorProvenance(
            "Lighthouse Agentic Browsing - experimental category score",
            "EXTERNAL_DEFINED_METRIC",
            "CONTEXT_ONLY",
            "Google Chrome Lighthouse via PageSpeed Insights",
            "PageSpeed v5 category + Lighthouse Agentic Browsing configuration",
            "https://googleapis.github.io/google-api-python-client/docs/dyn/pagespeedonline_v5.pagespeedapi.html",
            "Categoria experimental do Lighthouse; sua composição pode mudar entre versões.",
            (
                "O adapter PageSpeed atual do RASAi solicita a categoria. O valor só é materializado quando "
                "a resposta a fornece; ausência permanece indisponível e o indicador fica fora do SARI-001."
            ),
        ),
    )


def _install_gemini_diagnostics() -> None:
    from rasai import provider_extensions as extensions

    cls = extensions.GeminiProvider
    if getattr(cls, "_rasai_embedded_error_diagnostics", False):
        return
    original_native_error = cls._native_error

    def gemini_native_error(self, raw: Mapping[str, Any]):
        inherited = original_native_error(self, raw)
        if inherited is not None:
            return inherited
        error = raw.get("error")
        if not isinstance(error, Mapping):
            return None
        raw_status = error.get("code")
        try:
            http_status = int(raw_status) if raw_status is not None else None
        except (TypeError, ValueError):
            http_status = None
        error_type = extensions._safe_token(error.get("status") or error.get("type"))
        raw_code = error.get("reason") if error.get("reason") is not None else error.get("code")
        error_code = extensions._safe_token(raw_code)
        classified_status = http_status if http_status is not None else 400
        return extensions.ProviderDiagnostic(
            error_class=extensions._classify_http_error(classified_status, error_type, error_code),
            http_status=http_status,
            error_type=error_type,
            error_code=error_code,
        )

    cls._native_error = gemini_native_error
    cls._rasai_embedded_error_diagnostics = True
