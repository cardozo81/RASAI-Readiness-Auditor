"""Read-only GEO longitudinal HTML companion; no CONS mutation (#311).

This is a *presentation* of the verified, observational JSON inventory.
No AI, Search API, collectors, scoring, evidence writes or trend estimation.
"""
from __future__ import annotations

from html import escape
from typing import Any, Mapping


def _value(raw: object) -> str:
    """Never trust stored provider/query text as HTML or script."""
    return escape(str(raw if raw is not None else "N/D")[:1500], quote=True)


def render_geo_longitudinal_html(preview: Mapping[str, Any]) -> str:
    """Produce standalone, self-contained HTML from read-only GEO cohorts.

    This preview intentionally neither rewrites nor attaches to a CONS-* report.
    An actual CONS integration requires a separate scope/acceptance contract.
    """
    if preview.get("contract_version") != "RASAI-GEO-LONGITUDINAL-ADVISORY-001":
        raise ValueError("unsupported GEO longitudinal advisory version")
    cohorts = preview.get("timelines")
    rejected = preview.get("excluded")
    if not isinstance(cohorts, list) or not isinstance(rejected, list):
        raise ValueError("invalid GEO advisory structure")
    parts = [
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>RASAi — Inventário GEO longitudinal (observacional)</title>",
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:1100px;"
        "margin:auto;padding:1.5rem;color:#18334b;background:#f5f8fa}"
        "section{background:white;border:1px solid #d6e1ed;border-left:4px solid "
        "#16758b;padding:1.2rem;margin:1rem 0;border-radius:8px}"
        "table{display:block;overflow-x:auto;border-collapse:collapse;width:100%}"
        "th,td{border-bottom:1px solid #d6e1ed;padding:.6rem;text-align:left;"
        "vertical-align:top;overflow-wrap:anywhere}th{background:#e9f2fa}"
        "code{overflow-wrap:anywhere}small{color:#526579}</style></head><body>",
        "<h1>Inventário GEO longitudinal — somente observação</h1>",
        "<p>Fonte: snapshots já persistidos das AUDs informadas. "
        "Sem aquisição de Search API, inferência por IA, recaptura ou escrita nas "
        "auditorias. Esta visualização não faz parte de um CONS-* canônico.</p>",
        "<section><h2>Elegibilidade</h2>",
        "<p>AUDs solicitadas: ", _value(preview.get("audits_requested")),
        "; elegíveis: ", _value(preview.get("audits_eligible")),
        "; excluídas: ", _value(len(rejected)), ".</p></section>",
    ]
    cons_ref = preview.get("cons_reference")
    if isinstance(cons_ref, Mapping):
        parts.extend([
            "<section><h2>Vinculo consultivo ao consolidado</h2>",
            "<p>Identificador CONS: <code>", _value(cons_ref.get("cons_id")),
            "</code>; hash do pedido do consolidado: <code>",
            _value(cons_ref.get("manifest_request_fingerprint")), "</code>.</p>",
            "<p>Esta leitura usa apenas a relacao de AUDs declaradas no",
            " manifesto e nao modifica relatorio, fonte, indices ou metadados",
            " do consolidado. Sem atestado criptografico independente.",
            " O inventario e consultivo, nao integracao nativa CONS.</p>",
            "</section>",
        ])
    coverage = preview.get("observation_coverage")
    if isinstance(coverage, Mapping):
        by_reason = coverage.get("excluded_auds_by_reason")
        by_reason = by_reason if isinstance(by_reason, Mapping) else {}
        parts.extend([
            "<section><h2>Cobertura observacional e abstenções</h2>",
            "<p>Coortes de escopo físico distintas: ",
            _value(coverage.get("distinct_observed_scope_cohorts")),
            "; coortes com somente uma AUD: ",
            _value(coverage.get("single_observation_cohorts")),
            "; coortes com duas ou mais observações: ",
            _value(coverage.get("multi_observation_cohorts_unverified_trend")),
            "; AUDs pertencentes a estas últimas: ",
            _value(coverage.get("eligible_auds_in_multi_observation_cohorts")),
            ".</p><p><strong>Coortes com tendência GEO calibrada: N/D.</strong> "
            "Os agrupamentos com múltiplas AUDs permanecem somente observacionais: "
            "não há prova de amostragem, intenção ou mercado externo equivalentes.</p>",
        ])
        if by_reason:
            parts.extend([
                "<table><thead><tr><th>Motivo de exclusão (qualidade de fonte)</th>",
                "<th>Quantidade de AUDs</th></tr></thead><tbody>",
            ])
            for reason, count in sorted(by_reason.items()):
                parts.extend([
                    "<tr><td>", _value(reason), "</td><td>",
                    _value(count), "</td></tr>",
                ])
            parts.append("</tbody></table>")
        parts.append("</section>")
    if rejected:
        parts.extend([
            "<section><h2>Auditorias excluídas</h2><table><thead><tr>",
            "<th>AUD</th><th>Motivo verificável</th></tr></thead><tbody>",
        ])
        for item in rejected:
            if not isinstance(item, Mapping):
                continue
            parts.extend([
                "<tr><td><code>", _value(item.get("audit_id")),
                "</code></td><td>", _value(item.get("reason")),
                "</td></tr>",
            ])
        parts.append("</tbody></table></section>")
    if not cohorts:
        parts.append(
            "<section><p>Nenhuma coorte GEO longitudinal elegível. "
            "Resultado N/D: não inferir queda, ganho de visibilidade ou "
            "ausência da URL em respostas generativas.</p></section>"
        )
    for series in cohorts:
        if not isinstance(series, Mapping):
            continue
        scope = series.get("serp_scope")
        scope = scope if isinstance(scope, Mapping) else {}
        observations = series.get("observations")
        observations = observations if isinstance(observations, list) else []
        parts.extend([
            "<section><h2>Coorte: <code>", _value(series.get("target_url")),
            "</code></h2><p><strong>Consulta textual:</strong> ",
            _value(series.get("query")),
            "; <strong>Método:</strong> ", _value(series.get("method_version")),
            "; <strong>Search externo:</strong> ",
            _value(series.get("external_search_mode")), ".</p>",
            "<p>Escopo SERP persistido: motor ", _value(scope.get("engine")),
            "; país ", _value(scope.get("country")),
            "; região ", _value(scope.get("region")),
            "; idioma ", _value(scope.get("language")),
            "; dispositivo ", _value(scope.get("device")), ".</p>",
            "<p><strong>Estado:</strong> ", _value(series.get("status")),
            "; tendência: <strong>N/D</strong>. Valores abaixo representam "
            "apenas ocorrências e denominadores observados, não ranking nem "
            "percentual de visibilidade generativa.</p>",
            "<table><thead><tr><th>AUD</th><th>Instante externo (UTC)</th>",
            "<th>Alvo nas fontes</th><th>URLs comuns</th>",
            "<th>URLs SERP</th><th>URLs externas</th></tr></thead><tbody>",
        ])
        for item in observations:
            if not isinstance(item, Mapping):
                continue
            parts.extend([
                "<tr><td><code>", _value(item.get("audit_id")),
                "</code></td><td>", _value(item.get("observed_at")),
                "</td><td>", _value(item.get("target_status")),
                "</td><td>", _value(item.get("url_intersection_observed")),
                "</td><td>", _value(item.get("serp_urls_observed")),
                "</td><td>", _value(item.get("external_urls_observed")),
                "</td></tr>",
            ])
        parts.extend([
            "</tbody></table><small>",
            _value(series.get("limitation")),
            "</small></section>",
        ])
    parts.extend([
        "<section><h2>Limites de interpretação</h2><p>",
        "A equivalência de intenção, mercado, país, idioma, dispositivo, "
        "cobertura de amostra e comportamento comercial da Search API não "
        "é comprovada entre observações. Presença em resultado externo não "
        "significa citação ou preferência por assistentes de IA. "
        "Não converter estas sequências em taxas de evolução ou conclusões "
        "causais sem calibração empírica adicional.</p></section>",
        "<footer><small>Relatório independente, advisory, read-only. "
        "Zero chamadas externas e nenhuma modificação em AUD/CONS.</small>",
        "</footer></body></html>",
    ])
    return "".join(parts)


__all__ = ["render_geo_longitudinal_html"]
