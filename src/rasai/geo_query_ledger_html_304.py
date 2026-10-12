"""#304: accessible read-only HTML of the already verified per-query ledger.

No queries, SQLite access, persistence, score changes or web requests occur
here. All externally supplied text passes through HTML escaping.
"""
from __future__ import annotations

from html import escape
from typing import Any, Mapping


_SUPPORTED = {
    "RASAI-GEO-PER-QUERY-304-ADVISORY-005",
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
    return _safe(value) if type(value) is int and value >= 0 else "N/D"


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
        segments = [
            "<section class='query'>",
            f"<h2>{query}</h2>",
            f"<p class='meta'>{kind} · {result_label}</p>",
            reason,
            f"<p class='scope'>Escopo SERP observado: {scope_text}</p>",
            "<div class='columns'><div><h3>Conjuntos de fontes URL</h3><table>",
            metrics_html,
            "</table></div><div><h3>URL auditada (identidade exata)</h3><table>",
            target_html,
            "</table><p class='muted'>Estado: ",
            _safe(entry.get("target_url_overlap_status"))
            if row_admissible else "N/D",
            "</p></div></div></section>",
        ]
        snippets.append("".join(segments))

    body = "\n".join(snippets) if snippets else (
        "<p class='missing'>N/D - nenhuma consulta com proveniência suficiente.</p>"
    )
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
