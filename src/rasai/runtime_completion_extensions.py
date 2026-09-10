"""Small runtime extensions that close additive reporting/provider gaps.

These patches keep public console/help and report surfaces aligned with the canonical
runtime contracts without changing SARI arithmetic or evaluated website facts.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any


# Current RASAi PageSpeed transport can request only the categories accepted by
# PageSpeed Insights v5. Agentic Browsing remains a separate/future Lighthouse source.
_PAGESPEED_LIGHTHOUSE_CATEGORIES = (
    "performance",
    "accessibility",
    "best-practices",
    "seo",
)
_PAGESPEED_LIGHTHOUSE_CATEGORIES_CSV = ",".join(_PAGESPEED_LIGHTHOUSE_CATEGORIES)


def install_runtime_completion_extensions() -> None:
    """Install all additive completion patches idempotently."""
    _install_m21_runtime_contract()
    _install_cli_help()
    _install_console_environment()
    _install_dashboard_metrics()
    _install_monitoring_metrics()
    _install_agentic_provenance()
    _install_gemini_diagnostics()


def _install_m21_runtime_contract() -> None:
    """Prevent stale imports/config surfaces from sending Agentic to PSI."""
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
                    + "; Agentic Browsing is not transported by the current PageSpeed adapter "
                    "and remains outside SARI-001"
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
    original = console_environment._fixed_specs

    def fixed_specs_with_current_pagespeed_contract():
        items = []
        for spec in original():
            if spec.name == "RASAI_LIGHTHOUSE_CATEGORIES":
                spec = replace(
                    spec,
                    accepted=_PAGESPEED_LIGHTHOUSE_CATEGORIES,
                    default=_PAGESPEED_LIGHTHOUSE_CATEGORIES_CSV,
                    example=f"RASAI_LIGHTHOUSE_CATEGORIES={_PAGESPEED_LIGHTHOUSE_CATEGORIES_CSV}",
                    notes=(
                        "Uma ou mais categorias aceitas pelo provider PageSpeed, separadas por vírgula, "
                        "sem duplicar. Agentic Browsing exige fonte/adaptador Lighthouse separado."
                    ),
                )
            items.append(spec)
        return tuple(items)

    console_environment._fixed_specs = fixed_specs_with_current_pagespeed_contract
    console_environment._rasai_pagespeed_categories_current = True


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
            "Google Chrome Lighthouse",
            "Agentic Browsing configuration",
            "https://github.com/GoogleChrome/lighthouse/blob/main/core/config/agentic-browsing-config.js",
            "Categoria experimental do Lighthouse; sua composição pode mudar entre versões.",
            (
                "O adapter PageSpeed atual do RASAi não solicita esta categoria. O campo de compatibilidade "
                "pode ser materializado apenas por uma fonte Lighthouse direta/futura e permanece fora do SARI-001."
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
