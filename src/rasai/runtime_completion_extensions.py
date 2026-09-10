"""Small runtime extensions that close additive reporting/provider gaps.

The project already uses installation-time report/provider shims to preserve the
stable core.  These patches remain presentation/telemetry-only: they do not change
SARI arithmetic, scoring weights or evaluated website facts.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def install_runtime_completion_extensions() -> None:
    """Install all additive completion patches idempotently."""
    _install_dashboard_metrics()
    _install_monitoring_metrics()
    _install_agentic_provenance()
    _install_gemini_diagnostics()


def _install_dashboard_metrics() -> None:
    from rasai import rasai_readiness_reporting as reporting

    if getattr(reporting, "_rasai_extended_lighthouse_dashboard", False):
        return
    original_dashboard = reporting._dashboard

    def dashboard_with_extended_lighthouse(data: dict[str, Any], report_dir):
        html = original_dashboard(data, report_dir)
        web = data.get("web", [])
        specifications = (
            (
                "Lighthouse Best Practices",
                "best_practices_score",
                "Chrome Lighthouse",
                "web-performance.html",
            ),
            (
                "Lighthouse SEO técnico",
                "seo_score",
                "Chrome Lighthouse",
                "web-performance.html",
            ),
            (
                "Lighthouse Agentic Browsing",
                "agentic_browsing_score",
                "Chrome Lighthouse · experimental",
                "web-performance.html",
            ),
        )
        additions: list[str] = []
        for title, column, source, href in specifications:
            if f"<h3>{title}</h3>" in html:
                continue
            value, detail = reporting._device_ranges(
                web,
                column,
                scale=1.0,
                suffix="/100",
            )
            condition, condition_label = reporting._lighthouse_condition(web, column)
            if column == "agentic_browsing_score":
                detail += "; categoria experimental do Lighthouse, fora do SARI-001"
            additions.append(
                reporting._indicator_card(
                    title,
                    value,
                    detail,
                    href,
                    source,
                    condition,
                    condition_label,
                )
            )
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

    def read_performance_with_extended_categories(
        connection,
        tables: set[str],
        audit_id: str,
        signals: dict[str, Any],
    ) -> None:
        original(connection, tables, audit_id, signals)
        if "web_performance_observations" not in tables:
            return
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(web_performance_observations)"
            ).fetchall()
        }
        specifications = (
            ("best_practices_score", "Lighthouse Best Practices"),
            ("agentic_browsing_score", "Lighthouse Agentic Browsing"),
        )
        available = tuple(item for item in specifications if item[0] in columns)
        if not available:
            return
        rows = connection.execute(
            "SELECT * FROM web_performance_observations WHERE audit_id=? ORDER BY captured_at,rowid",
            (audit_id,),
        ).fetchall()
        latest: dict[tuple[str, str], Any] = {}
        for row in rows:
            latest[(str(row["device"]).upper(), str(row["url"]))] = row
        for (device, url), row in latest.items():
            names = set(row.keys())
            metadata = {
                "field_source": row["field_source"] if "field_source" in names else None,
                "field_scope": row["field_scope"] if "field_scope" in names else None,
                "captured_at": row["captured_at"] if "captured_at" in names else None,
            }
            for field, label in available:
                value = row[field]
                if value is None:
                    continue
                key = f"PERF|{device}|{url}|{field}"
                signals[key] = reader.Signal(
                    key=key,
                    domain="PERFORMANCE",
                    label=label,
                    value=float(value),
                    device=device,
                    url=url,
                    severity="MEDIUM",
                    direction="HIGHER_BETTER",
                    unit="score",
                    metadata=metadata,
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
            (
                "Categoria experimental do Lighthouse com auditorias voltadas à capacidade de agentes "
                "automatizados compreenderem e operarem páginas Web. Sua composição pode mudar entre versões."
            ),
            (
                "RASAi coleta e persiste o score e seus audit-level diagnostics como evidência complementar. "
                "O valor não é renomeado como indicador proprietário e não entra automaticamente no SARI-001."
            ),
        ),
    )
    summary = provenance._PAGE_SUMMARY.get("web-performance.html")
    if summary is not None and "Agentic" not in summary[1]:
        provenance._PAGE_SUMMARY["web-performance.html"] = (
            summary[0],
            summary[1].rstrip(".")
            + "; Agentic Browsing permanece identificado como categoria experimental do Lighthouse.",
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
            error_class=extensions._classify_http_error(
                classified_status,
                error_type,
                error_code,
            ),
            http_status=http_status,
            error_type=error_type,
            error_code=error_code,
        )

    cls._native_error = gemini_native_error
    cls._rasai_embedded_error_diagnostics = True
