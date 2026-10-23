"""Bounded #304 per-query GEO advisory for the canonical report page.

The physical source and all denominator/attribution checks are owned by
geo_query_ledger.inspect_geo_per_query. This consumer cannot infer provider
scope equivalence, change historical snapshots or trigger any network call.
"""
from __future__ import annotations

from html import escape
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

from rasai.geo_query_ledger import inspect_geo_per_query


def _e(value: object, *, limit: int = 300) -> str:
    text = value if isinstance(value, str) else "N/D"
    return escape(text[:limit], quote=True)


def _count(value: object) -> str:
    return str(value) if type(value) is int and 0 <= value <= 500 else "N/D"


def _pct(value: object) -> str:
    return f"{value * 100:.2f}%" if (
        type(value) in (int, float) and isfinite(value) and 0 <= value <= 1
    ) else "N/D"


def _advisory_unavailable(reason: str) -> str:
    return (
        '<section id="geo-per-query-304" data-contract="GEO-PER-QUERY-304">'
        "<h2>SERP × Search API por consulta — observação</h2>"
        "<p>N/D — comparação individual indisponível: " + _e(reason) + ".</p>"
        "<p>A ausência de atribuição, escopo ou amostra verificável "
        "não equivale a zero resultados.</p></section>"
    )



_GEO_REASON_LABELS = {
    "PER_QUERY_SOURCE_ATTRIBUTION_UNPROVEN": "Fonte externa não atribuível individualmente a esta consulta",
    "NO_COMPARABLE_OBSERVED_SERP_SCOPE_WITHIN_24H": "Nenhuma SERP live elegível da mesma consulta na janela de 24 horas",
    "NO_VALID_EXTERNAL_URL_DENOMINATOR": "Sem URLs externas válidas para a consulta",
    "NO_VALID_SERP_URL_DENOMINATOR": "Sem URLs SERP válidas para a consulta",
    "SERP_CHRONOLOGY_UNVERIFIABLE_FOR_QUERY": "Data/hora de coleta SERP não verificável",
    "SERP_QUERY_IDENTITY_UNVERIFIABLE": "Identidade da consulta SERP não verificável",
    "SERP_SCOPE_INCOMPLETE_ALONGSIDE_VERIFIED_SAMPLE": "Há observação SERP com escopo incompleto na mesma janela",
    "AMBIGUOUS_SERP_MARKET_LANGUAGE_DEVICE_SCOPE": "Mais de um escopo SERP de mercado, idioma ou dispositivo",
    "AMBIGUOUS_EQUIDISTANT_SERP_OBSERVATIONS": "Há observações SERP igualmente elegíveis sem desempate verificável",
    "SERP_SOURCE_URL_IDENTITY_UNVERIFIABLE": "Identidade de uma URL SERP não verificável",
    "EXTERNAL_SOURCE_URL_IDENTITY_UNVERIFIABLE": "Identidade de uma URL Search API não verificável",
    "NO_QUERY_WITH_VERIFIED_SOURCE_DENOMINATORS": "Nenhuma consulta possui denominadores verificáveis nas duas fontes",
    "SERP_SCOPE_SCHEMA_UNVERIFIABLE": "Estrutura de escopo SERP ausente ou incompatível",
    "SERP_RESULTS_SCHEMA_UNVERIFIABLE": "Estrutura dos resultados SERP ausente ou incompatível",
    "EXTERNAL_SEARCH_NOT_FOUND": "Nenhuma execução Search API persistida nesta AUD",
    "EXTERNAL_SEARCH_NOT_SUCCESSFUL": "Execução Search API ausente ou sem sucesso verificável",
    "AUD_NOT_COMPLETE_OR_FOREIGN": "Identidade ou conclusão da AUD não verificada",
    "AUD_METADATA_UNVERIFIABLE": "Metadados de identificação da AUD não verificáveis",
    "AUD_SQLITE_SIDECAR_APPEARED_DURING_READ": "Arquivos SQLite auxiliares surgiram durante a leitura",
    "AUD_SOURCE_CHANGED_DURING_READ": "Fonte SQLite alterada durante a verificação",
}


def _reason_html(value: object) -> str:
    """Human explanation and immutable technical code, never an unknown-enum fallback."""
    code = value if isinstance(value, str) and value else "QUERY_NOT_VERIFIED"
    label = _GEO_REASON_LABELS.get(code, "Pré-requisito técnico não comprovado")
    return escape(label) + " (<code>" + _e(code, limit=120) + "</code>)"


def _source_host_roster(row: Mapping[str, Any], admissible: bool) -> str:
    """Optional read-only expansion, never promoted without source integrity."""
    roster = row.get("host_source_inventory") if admissible else None
    if (not isinstance(roster, Mapping)
            or roster.get("status") != "OBSERVED_RETURNED_HOSTNAMES_ONLY"
            or type(roster.get("distinct_hostnames")) is not int
            or not 0 < roster["distinct_hostnames"] <= 1000
            or not isinstance(roster.get("entries"), list)
            or not 0 < len(roster["entries"]) <= 12):
        return ""
    lines = []
    for entry in roster["entries"]:
        if not isinstance(entry, Mapping):
            return ""
        host = entry.get("hostname")
        numbers = [_count(entry.get(key)) for key in (
            "serp_distinct_urls", "external_distinct_urls", "common_distinct_urls",
        )]
        if (not isinstance(host, str) or not host or len(host) > 253
                or "N/D" in numbers):
            return ""
        lines.append(
            "<tr><td>" + _e(host, limit=253) + "</td><td>"
            + "</td><td>".join(numbers) + "</td></tr>"
        )
    return (
        "<details><summary>Hosts observados na consulta " + _e(row.get("query"))
        + ": " + str(roster["distinct_hostnames"]) + " hostnames, "
        + str(len(lines)) + " exibidos</summary><table><thead>"
        "<tr><th>Hostname exato</th><th>URLs SERP</th>"
        "<th>URLs Search API</th><th>URLs exatas comuns</th>"
        "</tr></thead><tbody>" + "".join(lines) + "</tbody></table>"
        "<p>Hostnames de fontes, não concorrentes comerciais comprovados "
        "ou participação de mercado. Limite de exibição: 12 hostnames, "
        "sem mudar denominadores das taxas.</p></details>"
    )


def geo_query_advisory_html(database: Path, audit_id: str) -> str:
    """Render descriptive per-query URL-set rates from a sealed local AUD.

    No report can treat an arbitrary temporary database or copied directory
    with mismatched AUD identity as the canonical physical input.
    """
    db = Path(database)
    if (not isinstance(audit_id, str) or not audit_id.startswith("AUD-")
            or db.name != "audit.db" or db.parent.name != audit_id):
        return _advisory_unavailable("PHYSICAL_AUD_SCOPE_NOT_VERIFIED")
    try:
        projection = inspect_geo_per_query(db.parent)
    except (OSError, ValueError, OverflowError):
        return _advisory_unavailable("PHYSICAL_SOURCE_UNAVAILABLE")

    if (not isinstance(projection, Mapping)
            or projection.get("audit_id") != audit_id
            or projection.get("contract_version")
            != "RASAI-GEO-PER-QUERY-304-ADVISORY-008"
            or projection.get("status") not in ("DESCRIPTIVE_ONLY", "NOT_COMPARABLE")
            or projection.get("source_audit_db_integrity_guard") != "DOUBLE_SHA256_MATCH"):
        return _advisory_unavailable("SOURCE_INTEGRITY_OR_CONTRACT_UNVERIFIED")

    rows = projection.get("queries")
    if not isinstance(rows, list) or len(rows) > 10:
        return _advisory_unavailable("QUERY_PROVENANCE_UNVERIFIABLE")
    parts = [
        '<section id="geo-per-query-304" data-contract="GEO-PER-QUERY-304">',
        "<h2>SERP × Search API por consulta — observação</h2>",
        "<p>Conjuntos de URLs distintas fisicamente retornadas por consulta, "
        "com hash da fonte local verificado. Não comprova equivalência de "
        "mercado, idioma, dispositivo, intenção ou cobertura generativa. "
        "Zero numérico só corresponde a uma comparação com denominadores "
        "observados; demais casos são N/D.</p>",
        "<table><thead><tr><th>Consulta</th><th>Escopo SERP e coleta</th>"
        "<th>URLs SERP</th><th>URLs Search API</th><th>Em ambas</th>"
        "<th>Overlap SERP</th><th>Overlap Search API</th>"
        "<th>URL exata auditada</th><th>Limite</th></tr></thead><tbody>",
    ]
    if projection.get("status") == "NOT_COMPARABLE" and not rows:
        parts.append(
            "<p>Comparação por consulta: N/D. Motivo físico: "
            + _reason_html(projection.get("reason")) + ". "
            "Não significa ausência de resultados ou falha da Search API.</p>"
        )
    roster_details: list[str] = []
    for item in rows:
        if not isinstance(item, Mapping):
            return _advisory_unavailable("QUERY_ROW_UNVERIFIABLE")
        valid = (
            projection.get("status") == "DESCRIPTIVE_ONLY"
            and item.get("status") == "DESCRIPTIVE_ONLY"
        )
        scope = item.get("serp_scope")
        if valid and not isinstance(scope, Mapping):
            valid = False
        scope_text = (
            "; ".join(_e(scope.get(k), limit=90) for k in (
                "engine", "country", "region", "language", "device",
            )) + "; SERP " + _e(item.get("serp_collected_at"), limit=36)
            + "; Search API " + _e(item.get("external_run_started_at"), limit=36)
            if valid else "N/D"
        )
        # A declared class is editorial, never an inferred provider intent.
        cls = {
            "BRANDED_DECLARED": "Branded declarado",
            "NONBRANDED_DECLARED": "Non-branded declarado",
            "UNCLASSIFIED": "Não classificado",
        }.get(item.get("declared_query_class"), "N/D")
        target = (
            ("SERP: " + ("sim" if item.get("target_url_exact_in_serp") is True
                         else "não" if item.get("target_url_exact_in_serp") is False
                         else "N/D")
             + "; Search API: "
             + ("sim" if item.get("target_url_exact_in_perplexity") is True
                else "não" if item.get("target_url_exact_in_perplexity") is False
                else "N/D"))
            if valid else "N/D"
        )
        nums = (
            [_count(item.get("serp_distinct_urls")),
             _count(item.get("perplexity_distinct_urls")),
             _count(item.get("common_urls")),
             _pct(item.get("serp_overlap_rate")),
             _pct(item.get("perplexity_overlap_rate"))]
            if valid else ["N/D"] * 5
        )
        if valid and ("N/D" in nums or nums[0] == "0" or nums[1] == "0"):
            # Inconsistent projection is not a measured zero.
            valid = False
            nums = ["N/D"] * 5
            target = "N/D"
            scope_text = "N/D"
        note = (
            "Só URLs; mesma intenção/mercado não comprovados"
            if valid else _reason_html(item.get("reason"))
        )
        cells = [
            _e(item.get("query")) + " — " + escape(cls),
            scope_text, *nums, target, note,
        ]
        parts.append("<tr>" + "".join("<td>" + v + "</td>" for v in cells) + "</tr>")
        roster_details.append(_source_host_roster(item, valid))
    parts.append("</tbody></table>")
    parts.extend(roster_details)
    recurrence = projection.get("recurrence")
    if isinstance(recurrence, Mapping) and projection.get("status") == "DESCRIPTIVE_ONLY":
        state = recurrence.get("status")
        if state == "NOT_APPLICABLE_SINGLE_QUERY":
            parts.append("<p>Recorrência entre consultas: não aplicável à consulta única.</p>")
        elif state == "OBSERVED_WITHIN_ONE_RUN":
            parts.append(
                "<p>Recorrência de URL exata dentro do mesmo run — SERP: "
                + _count(recurrence.get("serp_recurrent_exact_urls"))
                + "; Search API: "
                + _count(recurrence.get("external_recurrent_exact_urls"))
                + ". Não representa tendência longitudinal.</p>"
            )
        else:
            parts.append("<p>Recorrência entre consultas: N/D (sem coorte física comparável).</p>")
    else:
        parts.append("<p>Recorrência entre consultas: N/D.</p>")
    parts.append("<p>Denominador: URLs distintas por fonte e consulta, nunca "
                 "impressões, posições solicitadas ou participação de mercado. "
                 "A presença em fontes Search API não atesta resposta gerativa "
                 "nem ranking; escopo externo permanece sem equivalência comprovada.</p>")
    parts.append("</section>")
    return "".join(parts)


__all__ = ["geo_query_advisory_html"]
