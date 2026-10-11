"""#210: standalone HTML view of same-domain comparison proof, never a CONS report.

Safe for stdout, without a file write or reuse of canonical report manifests.
No page-level trends, scores or time-series are derived.
"""
from __future__ import annotations

from html import escape
from typing import Any, Mapping


_REASON_PT = {
    "AUDIT_COUNT_OUT_OF_RANGE": "A seleção exige entre duas e cem auditorias.",
    "INVALID_CANDIDATE": "Um ou mais registros de auditoria estão inválidos.",
    "INVALID_OR_DUPLICATE_AUD_ID": "Identificadores ausentes, inválidos ou repetidos.",
    "AUD_NOT_LOGICALLY_COMPLETE": "Há auditorias sem conclusão lógica comprovada.",
    "UNVERIFIABLE_SINGLE_URL": "A URL exata de uma auditoria não foi comprovada.",
    "DIFFERENT_HOSTNAMES": "Os nomes de host das auditorias são diferentes.",
    "INCOMPATIBLE_DEVICE": "Os dispositivos são incompatíveis.",
    "SAME_URL_USE_STRICT_LONGITUDINAL_MODE": "A mesma URL deve usar o modo longitudinal estrito.",
    "UNVERIFIABLE_OBSERVATION_CHRONOLOGY": "A cronologia não está comprovada.",
}


def render_same_domain_advisory_html(advisory: Mapping[str, Any]) -> str:
    """Display only explicitly proven audit/URL inventory in escaped HTML."""
    if not isinstance(advisory, Mapping) or (
        advisory.get("comparison_mode") != "SAME_DOMAIN_COMPARATIVE"
        or advisory.get("production_cons_mode_changed") is not False
        or advisory.get("audit_score_deltas_eligible") is not False
        or advisory.get("page_level_trends_eligible") is not False
        or advisory.get("apdex_or_cwv_deltas_eligible") is not False
    ):
        raise ValueError("unverified same-domain advisory contract")
    good = advisory.get("eligible") is True
    reason = _REASON_PT.get(advisory.get("reason"), "Não comparável")
    source = advisory.get("index_reference", {})
    source = source if isinstance(source, Mapping) else {}
    if source.get("source_package_freshness_verified") is not False:
        raise ValueError("index freshness disclosure is missing")
    title = "Prévia comparativa por domínio (não é CONS)"
    parts = [
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>" + escape(title) + "</title>",
        "<style>body{max-width:1000px;margin:2rem auto;padding:0 1rem;"
        "font:16px/1.5 system-ui,sans-serif;color:#1a2234}"
        "table{border-collapse:collapse;width:100%}th,td{padding:.65rem;"
        "border:1px solid #ccd3de;text-align:left;overflow-wrap:anywhere}"
        ".notice{border-left:4px solid #596d9c;padding:1rem;background:#f5f7fb}"
        "@media(max-width:680px){.wide{overflow-x:auto;max-width:100%}}"
        "@media print{body{max-width:none}.notice{background:#fff}}</style>",
        "</head><body><main>",
        "<h1>" + escape(title) + "</h1>",
        "<p class='notice'><strong>Semantica e origem:</strong> "
        "Esta prévia utiliza exclusivamente um índice analítico local já existente. "
        "Seu frescor frente às AUDs não foi revalidado; "
        "nenhum relatório CONS, score, Apdex, CWV ou tendência por página é criado."
        "</p>",
        "<p><strong>Elegibilidade:</strong> " +
        ("Comparação descritiva de inventário" if good else "Não comparável: " + escape(reason))
        + "</p>",
    ]
    if good:
        audits = advisory.get("audits", ())
        if not isinstance(audits, list):
            raise ValueError("invalid same-domain records")
        parts.append("<p><strong>Hostname exato:</strong> " +
                     escape(str(advisory.get("hostname") or "N/D")) +
                     "; <strong>dispositivo:</strong> " +
                     escape(str(advisory.get("device") or "N/D")) + "</p>")
        parts.append(
            "<div class='wide'><table><thead><tr><th>AUD</th><th>URL observada</th>"
            "<th>Instante UTC</th><th>Fingerprint do universo</th>"
            "<th>Métricas por URL</th></tr></thead><tbody>"
        )
        for row in audits:
            if not isinstance(row, Mapping) or row.get("page_metrics_comparison") != "N/D":
                raise ValueError("page-level metric comparison not eligible")
            parts.append("<tr>" + "".join(
                "<td>" + escape(str(row.get(key) or "N/D")) + "</td>"
                for key in ("audit_id", "url", "observed_at_utc",
                            "url_universe_fingerprint", "page_metrics_comparison")
            ) + "</tr>")
        parts.append("</tbody></table></div>")
    parts.append(
        "<p><strong>Limite metodológico:</strong> URLs distintas não formam "
        "antes/depois da mesma página. Não há compatibilidade comprovada para "
        "agregação de scores, desempenho ou cobertura GEO entre esses universos.</p>"
        "</main></body></html>"
    )
    return "".join(parts)
