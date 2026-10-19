"""#304: accessible read-only HTML of the already verified per-query ledger.

No queries, SQLite access, persistence, score changes or web requests occur
here. All externally supplied text passes through HTML escaping.
"""
from __future__ import annotations

from html import escape
from typing import Any, Mapping


_SUPPORTED = {
    "RASAI-GEO-PER-QUERY-304-ADVISORY-005",
    "RASAI-GEO-PER-QUERY-304-ADVISORY-006",
    "RASAI-GEO-PER-QUERY-304-ADVISORY-007",
}
_SCOPE = ("engine", "country", "region", "language", "device")


def _safe(value: object, *, empty: str = "N/D") -> str:
    if value is None:
        return empty
    if not isinstance(value, (str, int, float, bool)):
        return escape(empty)
    text = str(value)
    return escape(text[:2048] if text else empty, quote=True)


def _count(value: object) -> str:
    # #304 physical input limits: at most 500 external source rows and 200 SERP rows.
    # A presentation-only projection cannot authenticate arbitrary count inflation.
    return _safe(value) if type(value) is int and 0 <= value <= 500 else "N/D"


def _rate(value: object) -> str:
    if type(value) not in (int, float) or not 0 <= value <= 1:
        return "N/D"
    return escape(f"{value * 100:.2f}%", quote=True)


def _classification(value: object) -> str:
    return {
        "BRANDED_DECLARED": "Branded (declaração do operador)",
        "UNCLASSIFIED": "Não classificada",
    }.get(value, "N/D")


def _presence(value: object) -> str:
    if value is True:
        return "Sim (URL exata no conjunto)"
    if value is False:
        return "Não (não observada nesse conjunto)"
    return "N/D"


def _table_row(cells: list[str], *, header: bool = False) -> str:
    tag = "th" if header else "td"
    return "<tr>" + "".join(f"<{tag}>{cell}</{tag}>" for cell in cells) + "</tr>"


def render_geo_query_ledger_html(projection: Mapping[str, Any]) -> str:
    """Render one self-contained, print-friendly advisory without JavaScript.

    This is a projection of evidence that was already collected; zero values
    only occur when physically verified. No inferred generative citation,
    ranking, equal market/device or longitudinal trend is ever shown.
    """
    if not isinstance(projection, Mapping):
        raise ValueError("GEO query ledger object required")
    if projection.get("contract_version") not in _SUPPORTED:
        raise ValueError("unsupported GEO query ledger contract")
    status = projection.get("status")
    if status not in {"DESCRIPTIVE_ONLY", "NOT_COMPARABLE"}:
        raise ValueError("invalid GEO query ledger status")
    entries = projection.get("queries")
    if not isinstance(entries, list) or len(entries) > 10:
        raise ValueError("bounded GEO query ledger rows required")

    verified = projection.get("source_audit_db_integrity_guard") == "DOUBLE_SHA256_MATCH"
    # Per-row status cannot override the projection-wide physical source gate.
    # A caller may retain stale rows after an upstream read/integrity failure.
    # Such rows must never be presented as measured URL overlaps.
    admissible = status == "DESCRIPTIVE_ONLY" and verified
    seal = (
        "SHA-256 local conferido em duas leituras"
        if verified else "Integridade física não comprovada"
    )
    snippets: list[str] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("malformed GEO query row")
        row_status = entry.get("status")
        if row_status not in {"DESCRIPTIVE_ONLY", "NOT_COMPARABLE"}:
            raise ValueError("invalid GEO query status")
        query = _safe(entry.get("query"))
        kind = escape(_classification(entry.get("declared_query_class")), quote=True)
        row_admissible = admissible and row_status == "DESCRIPTIVE_ONLY"
        result_label = (
            "Sobreposição descritiva de fontes URL"
            if row_admissible else "N/D - dados insuficientes"
        )
        reason = (
            "" if row_admissible
            else "<p class='muted'>Motivo: " + _safe(
                entry.get("reason") or projection.get("reason")
                or ("SOURCE_INTEGRITY_UNVERIFIED" if not verified
                    else "GLOBAL_COMPARABILITY_NOT_VERIFIED")
            ) + "</p>"
        )
        scope = entry.get("serp_scope")
        scope_text = (
            " · ".join(f"{field}: {_safe(scope.get(field))}" for field in _SCOPE)
            if isinstance(scope, Mapping) and row_admissible else "N/D"
        )
        # Both row and projection-wide provenance gates must pass. Never
        # expose stale numeric fields after a physical-source abstention.
        metric = lambda key, fmt: (
            fmt(entry.get(key)) if row_admissible else "N/D"
        )
        metrics = [
            ("URLs distintas SERP", metric("serp_distinct_urls", _count)),
            ("URLs distintas Search API", metric("perplexity_distinct_urls", _count)),
            ("URLs comuns", metric("common_urls", _count)),
            ("Exclusivas SERP", metric("serp_only_urls", _count)),
            ("Exclusivas Search API", metric("perplexity_only_urls", _count)),
            ("Overlap relativo SERP", metric("serp_overlap_rate", _rate)),
            ("Overlap relativo Search API", metric("perplexity_overlap_rate", _rate)),
            ("Jaccard (URLs exatas)", metric("jaccard_url_rate", _rate)),
        ]
        metrics_html = "".join(
            _table_row([escape(label, quote=True), metric]) for label, metric in metrics
        )
        target_html = "".join(
            _table_row([escape(label, quote=True), (
                _presence(entry.get(field))
                if row_admissible else "N/D"
            )])
            for label, field in [
                ("URL auditada no SERP", "target_url_exact_in_serp"),
                ("URL auditada no Search API", "target_url_exact_in_perplexity"),
            ]
        )
        host_overlap = entry.get("host_overlap") if row_admissible else None
        def host_value(key: str, formatter: Any) -> str:
            if not isinstance(host_overlap, Mapping):
                return "N/D"
            return formatter(host_overlap.get(key))
        host_metrics = (
            ("Hosts distintos SERP", "serp_distinct_hosts", _count),
            ("Hosts distintos Search API", "external_distinct_hosts", _count),
            ("Hosts comuns", "common_hosts", _count),
            ("Hosts exclusivos SERP", "serp_only_hosts", _count),
            ("Hosts exclusivos Search API", "external_only_hosts", _count),
            ("Sobreposição de hosts SERP", "serp_host_overlap_rate", _rate),
            ("Sobreposição de hosts Search API", "external_host_overlap_rate", _rate),
            ("Jaccard de hosts exatos", "jaccard_host_rate", _rate),
        )
        host_metrics_html = "".join(
            _table_row([escape(label, quote=True), host_value(key, formatter)])
            for label, key, formatter in host_metrics
        )
        # Persisted host groups describe alternative URLs, not competitors.
        # A source integrity or row comparability failure must hide counts.
        group_rows = []
        for label, field in (
            ("SERP", "serp_target_host_group"),
            ("Search API", "external_target_host_group"),
        ):
            group = entry.get(field) if row_admissible else None
            for description, key in (
                ("URLs alternativas no hostname do alvo", "same_host_alternative_urls"),
                ("URLs observadas em outros hostnames", "other_host_distinct_urls"),
                ("Hostnames distintos fora do alvo", "other_distinct_hosts"),
            ):
                group_rows.append(_table_row([
                    escape(f"{label}: {description}", quote=True),
                    _count(group.get(key)) if isinstance(group, Mapping) else "N/D",
                ]))
        group_html = "".join(group_rows)
        segments = [
            "<section class='query'>",
            f"<h2>{query}</h2>",
            f"<p class='meta'>{kind} · {result_label}</p>",
            reason,
            f"<p class='scope'>Escopo SERP observado: {scope_text}</p>",
            (
                "<p class='missing' data-contract='GEO-MARKET-COMPARABILITY-304'>"
                "<strong>Comparabilidade externa não comprovada:</strong> "
                "as interseções numéricas abaixo refletem apenas URLs efetivamente "
                "observadas em cada fonte, sem equivalência provada de país, idioma, "
                "dispositivo ou intenção entre SERP e Search API. Não interpretar "
                "como concordância de posicionamento, participação de mercado ou "
                "presença em respostas gerativas.</p>"
                if row_admissible else ""
            ),
            "<div class='columns'><div><h3>Conjuntos de fontes URL</h3><table>",
            metrics_html,
            "</table></div><div><h3>URL auditada (identidade exata)</h3><table>",
            target_html,
            "</table><p class='muted'>Estado: ",
            _safe(entry.get("target_url_overlap_status"))
            if row_admissible else "N/D",
            "</p></div></div>",
            "<h3>Interseção de hosts observados (sem inferir concorrência)</h3>",
            "<table>", host_metrics_html, "</table>",
            "<h3>Alternativas ao hostname da URL auditada</h3>",
            "<table>", group_html, "</table>",
            "<p class='muted'>Hostname exato: www e apex não são equivalentes; "
            "portas e protocolos distintos podem compartilhar hostname. "
            "Não é participação de mercado, ranking ou citação.</p></section>",
        ]
        snippets.append("".join(segments))

    # New recurrence is only a within-run multi-query descriptor. No
    # numerical field can be shown on failed global source authentication.
    recurrence = projection.get("recurrence")
    recurrence_html = ""
    if projection.get("contract_version") == "RASAI-GEO-PER-QUERY-304-ADVISORY-007":
        state = recurrence.get("status") if isinstance(recurrence, Mapping) else None
        if not admissible or state == "NOT_COMPARABLE" or state is None:
            recurrence_html = (
                "<section class='query' data-contract='GEO-RECURRENCE-304'>"
                "<h2>Recorrência entre consultas</h2>"
                "<p>N/D — todas as consultas e escopos precisam ter fontes "
                "e integridade verificáveis.</p></section>"
            )
        elif state == "NOT_APPLICABLE_SINGLE_QUERY":
            recurrence_html = (
                "<section class='query' data-contract='GEO-RECURRENCE-304'>"
                "<h2>Recorrência entre consultas</h2>"
                "<p>Não aplicável: somente uma consulta foi observada.</p></section>"
            )
        elif state == "OBSERVED_WITHIN_ONE_RUN":
            fields = (
                ("Consultas fisicamente comparadas", "verified_queries"),
                ("URLs exatas recorrentes em SERP", "serp_recurrent_exact_urls"),
                ("URLs exatas recorrentes em Search API", "external_recurrent_exact_urls"),
                ("URLs recorrentes nas duas fontes", "cross_source_recurrent_exact_urls"),
                ("Hostnames exatos recorrentes em SERP", "serp_recurrent_exact_hosts"),
                ("Hostnames exatos recorrentes em Search API", "external_recurrent_exact_hosts"),
                ("Hostnames recorrentes nas duas fontes", "cross_source_recurrent_exact_hosts"),
                ("Hostnames recorrentes externos ao hostname auditado",
                 "other_recurrent_cross_source_hosts"),
            )
            recurrence_html = (
                "<section class='query' data-contract='GEO-RECURRENCE-304'>"
                "<h2>Recorrência dentro do conjunto de consultas</h2><table>"
                + "".join(
                    _table_row([escape(label, quote=True), _count(recurrence.get(key))])
                    for label, key in fields
                )
                + "</table><p class='muted'>Recorrente significa presença da "
                "mesma identidade URL ou hostname em pelo menos duas consultas "
                "do mesmo run com escopo SERP uniforme e fonte por consulta "
                "verificada. Não é recorrência longitudinal, participação "
                "de mercado, concorrência factual, posição SERP, nem citação "
                "gerativa. Escopo externo Search API e intenção seguem "
                "não comprovados como equivalentes.</p></section>"
            )

    body = recurrence_html + ("\n".join(snippets) if snippets else (
        "<p class='missing'>N/D - nenhuma consulta com proveniência suficiente.</p>"
    ))
    summary = (
        "Somente observações descritivas. Não equivale a citação gerativa."
        if admissible else "N/D - comparabilidade não demonstrada."
    )
    return """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GEO por consulta - prévia consultiva RASAi</title>
<style>
:root{color-scheme:light;font-family:system-ui,-apple-system,sans-serif;color:#203147}
body{max-width:1120px;margin:0 auto;padding:clamp(14px,3vw,36px);background:#f8fafc}
h1{font-size:1.8rem;margin-bottom:.3rem}h2{font-size:1.26rem;overflow-wrap:anywhere}
h3{font-size:1rem}.intro{max-width:90ch;line-height:1.55}
.query{background:#fff;border:1px solid #cbd5e1;border-radius:10px;padding:20px;margin:20px 0;break-inside:avoid}
.meta{font-weight:600}.scope,.muted,.footnote{color:#42566b;font-size:.92rem;line-height:1.5}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:20px}
table{width:100%;border-collapse:collapse;font-size:.93rem}
td{padding:9px 7px;border-bottom:1px solid #e2e8f0;vertical-align:top;overflow-wrap:anywhere}
td:first-child{font-weight:600;width:54%}
.banner{padding:14px 18px;background:#eaf0f7;border-left:4px solid #314766;border-radius:4px}
.missing{padding:20px;border:1px solid #94a3b8}
@media(max-width:680px){.columns{grid-template-columns:1fr}.query{padding:14px}}
@media print{body{background:#fff}.query{break-inside:avoid;box-shadow:none}}
</style></head><body>
<header><h1>GEO por consulta - prévia consultiva</h1>
<p class="intro">Comparação de conjuntos de URLs observadas em SERP e Search API.
Não é relatório GEO produtivo, ranking equivalente, evidência de menção
ou citação em respostas gerativas, nem validação de intenção ou mercado.</p>
</header>
<div class="banner"><p>""" + escape(summary) + """</p>
<p class="muted">AUD: """ + _safe(projection.get("audit_id")) + (
        " · Fonte: " + escape(seal) + "</p>"
    ) + """</div>
<main>""" + body + """</main>
<footer class="footnote"><p>Escopo e idioma/dispositivo externos não foram
comprovados como equivalentes ao SERP. Query branded somente por declaração
explícita; ausência de alvo, denominador ou atribuição gera N/D, nunca 0%.</p>
<p>Advisory offline, sem chamadas comerciais, reprocessamento, alterações em
AUD, GEO v8, CONS, SARI ou SCORE-GEO.</p></footer>
</body></html>
"""


__all__ = ["render_geo_query_ledger_html"]
