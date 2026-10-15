"""#330: safe standalone HTML of already verified COBS static metadata.

Never fetch URLs, consume provider APIs, infer editorial gaps or rewrite AUD/
CONS/GEO reports. Only input is the validated read-only pair projection.
"""
from __future__ import annotations

from html import escape
import math
import re
from typing import Any, Mapping


_CONTRACT = "RASAI-COBS-STATIC-METADATA-PAIR-330-001"
_SHA = re.compile(r"^[0-9a-f]{64}$")


def _safe(value: object, *, empty: str = "N/D") -> str:
    if value is None or not isinstance(value, (str, int, float)):
        return escape(empty)
    rendered = str(value)
    return escape(rendered[:1000] if rendered else empty, quote=True)


def _count(value: object) -> str:
    return str(value) if type(value) is int and 0 <= value <= 1_000_000 else "N/D"


def _safe_list(values: object) -> str:
    if not isinstance(values, list) or not 0 <= len(values) <= 100:
        return "<span class='nd'>N/D</span>"
    if any(not isinstance(v, str) or len(v) > 500 for v in values):
        return "<span class='nd'>N/D</span>"
    if not values:
        return "<span class='nd'>Nenhum item no extrato estatico observado</span>"
    return "<ul>" + "".join(f"<li>{_safe(item)}</li>" for item in values) + "</ul>"


def _card(title: str, facts: Mapping[str, Any]) -> str:
    cells = [
        ("URL exata", _safe(facts.get("url"))),
        ("Title observado", _safe(facts.get("title"))),
        ("Palavras no HTML estatico", _count(facts.get("word_count_observed_static"))),
        ("Captura HTTP", _safe(facts.get("html_fetch_timestamp"))),
        ("SHA-256 do HTML", _safe(facts.get("content_sha256"))),
    ]
    table = "".join(
        f"<tr><th scope='row'>{escape(name)}</th><td>{value}</td></tr>"
        for name, value in cells
    )
    return (
        "<section class='panel'><h2>" + escape(title) + "</h2>"
        "<table>" + table + "</table>"
        "<h3>Headings observados</h3>" + _safe_list(facts.get("headings"))
        + "<h3>Tipos JSON-LD observados</h3>" + _safe_list(facts.get("jsonld_types"))
        + "<h3>Termos de consulta no HTML estatico</h3>"
        + _safe_list(facts.get("query_body_terms")) + "</section>"
    )


def _lexical_group(
    title: str, projection: Mapping[str, Any], prefix: str,
) -> str:
    categories = (
        ("Nas duas capturas", "both"),
        ("Somente no extrato do alvo", "customer_only"),
        ("Somente no extrato do concorrente", "competitor_only"),
    )
    return (
        "<section class='lexical'><h3>" + escape(title) + "</h3>"
        + "".join(
            "<div class='lexical-item'><h4>" + escape(label) + "</h4>"
            + _safe_list(projection.get(prefix + suffix)) + "</div>"
            for label, suffix in categories
        ) + "</section>"
    )


def render_cobs_static_pair_html(projection: Mapping[str, Any]) -> str:
    """Render an untrusted projection only if it retains strict static gates."""
    if not isinstance(projection, Mapping):
        raise ValueError("COBS static pair object required")
    if (
        projection.get("contract_version") != _CONTRACT
        or projection.get("status") != "DESCRIPTIVE_STATIC_HTML_ONLY"
        or not isinstance(projection.get("customer"), Mapping)
        or not isinstance(projection.get("competitor"), Mapping)
        or not isinstance(projection.get("source_audit_db_sha256"), str)
        or not _SHA.fullmatch(projection["source_audit_db_sha256"])
    ):
        raise ValueError("unverified COBS static pair projection")
    for gate in (
        "rendered_or_primary_content_verified",
        "primary_content_comparison_eligible",
        "localisation_equivalence_proven",
        "device_equivalence_proven",
        "intent_equivalence_proven",
        "same_browser_sample_proven",
        "generative_citation_proven",
        "editorial_gap_claim_eligible",
        "word_count_delta_eligible",
        "static_text_differences_are_editorial_gaps",
    ):
        if projection.get(gate) is not False:
            raise ValueError("COBS projection claims unsupported comparability")
    if (
        type(projection.get("provider_requests")) is not int
        or projection["provider_requests"] != 0
        or type(projection.get("audit_writes")) is not int
        or projection["audit_writes"] != 0
    ):
        raise ValueError("COBS HTML must be offline and read-only")
    if projection.get("serp_and_html_same_population_proven") is True:
        raise ValueError("COBS cannot claim equal SERP and HTML sample populations")
    gap = projection.get("html_capture_gap_seconds")
    if (
        type(gap) not in (int, float) or not math.isfinite(gap)
        or gap < 0 or gap > 24 * 3600
    ):
        raise ValueError("COBS pair capture clocks invalid")
    for role in ("customer", "competitor"):
        facts = projection[role]
        if (
            not isinstance(facts.get("url"), str)
            or not isinstance(facts.get("title"), str)
            or not isinstance(facts.get("html_fetch_timestamp"), str)
            or not isinstance(facts.get("content_sha256"), str)
            or not _SHA.fullmatch(facts["content_sha256"])
            or _count(facts.get("word_count_observed_static")) == "N/D"
        ):
            raise ValueError("COBS static HTML facts invalid")
    # The source/HTML timing is an observational context flag, not
    # a population-equivalence certificate. Older pair projections show N/D.
    gaps = (
        projection.get("serp_to_customer_html_gap_seconds"),
        projection.get("serp_to_competitor_html_gap_seconds"),
    )
    if all(type(value) in (int, float) and math.isfinite(value) and value >= 0
           for value in gaps):
        chronology = (
            f"SERP - alvo: {gaps[0]:.0f}s; SERP - concorrente: {gaps[1]:.0f}s"
        )
    else:
        chronology = "N/D"
    if projection.get("serp_capture_temporal_scope") == "BOTH_CAPTURES_WITHIN_24H_OF_SERP":
        time_status = "Capturas em ate 24h da SERP, sem equivalencia de populacao comprovada"
    elif projection.get("serp_capture_temporal_scope") == "SERP_CAPTURE_TEMPORAL_SCOPE_NOT_COMPARABLE":
        time_status = "Pelo menos uma captura fora da janela SERP de 24h; escopo temporal nao comparavel"
    else:
        time_status = "Proximidade temporal da SERP N/D"
    source = _safe(projection.get("source_audit_id"))
    observation = _safe(projection.get("source_serp_observation_id"))
    scope = projection.get("source_serp_scope")
    scope_text = (
        " | ".join(
            f"{escape(key)}: {_safe(scope.get(key))}"
            for key in ("engine", "country", "region", "language", "device")
        )
        if isinstance(scope, Mapping) else "N/D"
    )
    parts = [
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; form-action 'none'; base-uri 'none'\">",
        "<title>RASAi - Comparacao lexical estatica COBS</title>",
        "<style>",
        ":root{color-scheme:light;font-family:system-ui,-apple-system,sans-serif;color:#193248}",
        "body{margin:auto;max-width:1160px;padding:clamp(16px,3vw,34px);background:#f5f8fc}",
        "header{background:#e7eef7;padding:20px;border-left:5px solid #335979}",
        "h1{font-size:1.8rem}h2{font-size:1.25rem}h3{font-size:1.05rem}",
        ".muted,.nd{color:#42566a}.warning{border:1px solid #bd8737;background:#fff8e9;padding:14px}",
        ".grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}",
        ".panel,.lexical{background:#fff;border:1px solid #ccd6e1;padding:18px;border-radius:8px;min-width:0}",
        ".panel{break-inside:avoid}table{border-collapse:collapse;width:100%;font-size:.9rem}",
        "th,td{text-align:left;vertical-align:top;border-bottom:1px solid #e0e6ee;padding:9px;overflow-wrap:anywhere}",
        "th{width:37%}.lexical-item{border-top:1px solid #d6e1eb;padding:9px 0}",
        "h4{margin-bottom:4px}li{overflow-wrap:anywhere;margin:5px 0}",
        "@media(max-width:720px){.grid{grid-template-columns:1fr}body{padding:14px}}",
        "@media print{body{background:#fff}.panel,.lexical{break-inside:avoid}header{background:#fff}}",
        "</style></head><body>",
        "<header><h1>Comparacao lexical observacional - COBS</h1>",
        "<p>Previa independente de HTML estatico autorizado. Nao e comparacao profunda de conteudo renderizado, ranking ou relatorio GEO canônico.</p>",
        f"<p><strong>AUD:</strong> {source} &middot; <strong>SERP:</strong> {observation}</p>",
        f"<p class='muted'>Escopo SERP: {scope_text}</p>",
        f"<p class='muted'>Intervalo entre capturas: {gap:.0f} segundos. Proximidade nao prova equivalencia de intencao, idioma, dispositivo ou sessao.</p>",
        f"<p class='muted'>Relogio SERP vs capturas: {escape(chronology)}. {escape(time_status)}.</p>",
        "</header>",
        "<p class='warning'><strong>Limite de inferencia:</strong> somente texto e metadados do HTML estatico coletado. "
        "Elementos ausentes na extracao NAO sao lacunas editoriais comprovadas; "
        "nao gerar priorizacao, recomendacao comercial, percentual de qualidade ou score.</p>",
        "<main><div class='grid'>",
        _card("URL auditada - extrato estatico", projection["customer"]),
        _card("URL concorrente - extrato estatico", projection["competitor"]),
        "</div><h2>Intersecoes lexicais exatas (nao semanticas)</h2><div class='grid'>",
        _lexical_group("Headings", projection, "observed_heading_text_"),
        _lexical_group("Termos de consulta", projection, "observed_query_body_terms_"),
        "</div><section class='lexical'><h3>Tipos JSON-LD</h3><div class='grid'>",
        _lexical_group("No mesmo conjunto", projection, "observed_jsonld_types_"),
        "</div></section></main>",
        "<footer class='muted'><p>Origem: dois sidecars COBS content-addressed, confrontados offline com SQLite e SERP da AUD. "
        "O SHA-256 local nao atesta autenticidade do fornecedor. Sem JS, DNS, HTTP, IA, AUD writes, "
        "SARI, SCORE-GEO ou alteracoes no CONS.</p></footer></body></html>",
    ]
    return "".join(parts)


__all__ = ["render_cobs_static_pair_html"]
