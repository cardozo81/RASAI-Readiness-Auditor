"""Read-only executive evidence reconciliation for #600/#604.

This is a *presentation model*, never a competing scorer. Its purpose is to
make unlike populations and independent verification limits visible together:
SARI method score != lab Lighthouse != CrUX field != SERP depth !=
editorial claim authenticity. Unknown evidence is not 0 or success.
"""
from __future__ import annotations

from html import escape
from math import isfinite
from typing import Any, Mapping, Sequence

_CONTRACT = "RASAI-DECISION-EVIDENCE-604-001"
_MAX_DIMENSIONS = 64
_MAX_ROWS = 32

def _number(value: object, low: float = 0, high: float = 100) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if isfinite(parsed) and low <= parsed <= high else None


def _score(value: object) -> str:
    bounded = _number(value)
    return (f"{bounded:.1f} / 100".replace(".", ",")
            if bounded is not None else "N/D")


def _coverage(value: object) -> str:
    bounded = _number(value, 0, 1)
    return (
        f"{bounded * 100:.1f}".replace(".", ",")
        + f"% (fração {bounded:.6f})"
        if bounded is not None else "N/D"
    )


def _item(name: str, value: str, scope: str, source: str, limitation: str) -> dict[str, str]:
    return {
        "indicator": name, "observed": value,
        "scope": scope, "source": source, "limitation": limitation,
    }


def decision_evidence_matrix(
    *,
    audit_id: str,
    scores: Sequence[Mapping[str, Any]],
    web: Mapping[str, Any] | None = None,
    catalog_statuses: Mapping[str, str] | None = None,
    serp_depth: tuple[int, int] | None = None,
    optional_seo_discounts: Sequence[Mapping[str, Any]] = (),
    include_external: bool = True,
) -> dict[str, Any]:
    """Cross-check proven populations, never manufacture cross-signal causality.

    The caller is responsible for ensuring that each source originates from
    the same AUD. This pure function does not query SQLite or the Internet.
    """
    entries: list[dict[str, str]] = []
    if not isinstance(audit_id, str) or not audit_id.startswith("AUD-"):
        return {"contract": _CONTRACT, "audit_id": None, "rows": [],
                "status": "NOT_VERIFIABLE", "provider_requests": 0,
                "audit_writes": 0}
    if len(scores) > _MAX_DIMENSIONS:
        return {"contract": _CONTRACT, "audit_id": audit_id, "rows": [],
                "status": "NOT_VERIFIABLE", "provider_requests": 0,
                "audit_writes": 0}
    overall = [
        row for row in scores
        if isinstance(row, Mapping)
        and str(row.get("dimension")) == "OVERALL_READINESS"
    ]
    seen_devices: set[str] = set()
    for row in overall:
        device = str(row.get("device") or "").upper()
        if device in seen_devices or device not in {"MOBILE", "DESKTOP"}:
            return {"contract": _CONTRACT, "audit_id": audit_id, "rows": [],
                    "status": "NOT_VERIFIABLE", "provider_requests": 0,
                    "audit_writes": 0}
        seen_devices.add(device)
        from rasai.sari_readiness_presentation import public_readiness_condition
        _tone, readiness, _quality = public_readiness_condition(row)
        entries.append(_item(
            f"SARI / {device}", _score(row.get("value")),
            "Escopo da AUD, dispositivo e regras versionadas",
            "scores.OVERALL_READINESS",
            "Cobertura " + _coverage(row.get("coverage"))
            + "; " + readiness + ". Confiança do método, não "
            "certeza estatística, aprovação de experiência ou visibilidade real.",
        ))
    if not overall:
        entries.append(_item(
            "SARI", "N/D", "Escopo da AUD",
            "scores.OVERALL_READINESS",
            "Nenhuma pontuação global atribuível; não equivale a 0/100.",
        ))
    limited = sorted({
        (str(row.get("dimension")), str(row.get("device") or "N/D"),
         _coverage(row.get("coverage")))
        for row in scores if isinstance(row, Mapping)
        and row.get("dimension") not in ("OVERALL_READINESS", None)
        and (_number(row.get("coverage"), 0, 1) is None
             or _number(row.get("coverage"), 0, 1) < 1)
    })
    if limited:
        entries.append(_item(
            "Dimensões SARI com cobertura não integral",
            f"{len(limited)} dimensão/dispositivo(s)",
            "Cobertura por dimensão / dispositivo",
            "scores.coverage",
            "Confiança agregada não elimina medição parcial; detalhamento "
            "nas páginas SARI e metodologia.",
        ))
    if isinstance(web, Mapping):
        lab = _number(web.get("performance_score"))
        entries.append(_item(
            "Lighthouse / desempenho",
            _score(lab), "Medição de laboratório de CAT-04",
            "web_performance_observations.performance_score",
            "Não mede o índice SARI, uso real nem série CrUX de campo.",
        ))
        field_keys = ("lcp_p75_ms", "inp_p75_ms", "cls_p75")
        present = any(web.get(k) is not None for k in field_keys)
        if present:
            raw_scope = str(web.get("field_scope") or "").upper()
            if raw_scope == "ORIGIN":
                scope = "Origem agregada (ORIGIN), não a URL exata"
            elif raw_scope == "URL":
                scope = "URL específica medida em campo (URL)"
            else:
                scope = "Escopo de campo não comprovado"
            fields = []
            for key, label, unit, limit in (
                ("lcp_p75_ms", "LCP p75", "ms", 60_000),
                ("inp_p75_ms", "INP p75", "ms", 60_000),
                ("cls_p75", "CLS p75", "", 10),
            ):
                value = _number(web.get(key), 0, limit)
                if value is not None:
                    fields.append(f"{label} {value:g}{unit}")
            entries.append(_item(
                "Core Web Vitals / CrUX", "; ".join(fields) if fields else "N/D",
                scope, "web_performance_observations",
                "Amostra de campo e janela própria, não resultado da URL "
                "quando a origem agregada foi medida. Não é Lighthouse lab.",
            ))
    statuses = catalog_statuses if isinstance(catalog_statuses, Mapping) else {}
    for cat_id, title in (("CAT-06", "Apdex de navegação"),
                          ("CAT-07", "Apdex de experiência")):
        status = str(statuses.get(cat_id) or "").strip()
        if status:
            entries.append(_item(
                title, "Parcial" if status.casefold() in ("partial", "parcial") else status,
                f"{cat_id} / coorte sintética de amostras",
                "audit_catalog + audit_fulfillment_work_items",
                "Resultado operacional não prova suficiência estatística, "
                "representatividade de tráfego real ou prontidão do conteúdo "
                "após o carregamento.",
            ))
    if serp_depth is not None:
        n, requested = serp_depth
        if (type(n) is int and type(requested) is int
                and 0 <= n < requested <= 1000):
            entries.append(_item(
                "SERP / profundidade", f"{n} / {requested} posições",
                "Uma observação SERP atribuível à AUD",
                "serp_observations + serp_results",
                "Coleta incompleta; posições não retornadas são N/D. "
                "Uma consulta não mede participação de mercado nem citação em IA.",
            ))
    if optional_seo_discounts:
        verified = [row for row in optional_seo_discounts
                    if isinstance(row, Mapping) and row.get("version") == "SCORE-GEO-004"]
        if verified:
            entries.append(_item(
                "Sinais SEO opcionais", f"{len(verified)} contribuição(ões)",
                "Descontos isolados do método vigente",
                "score_contributions + rule_executions",
                "Ausência convencional de sitemap, canonical ou robots não "
                "comprova falha de indexação. Estes descontos já integram o "
                "score persistido; não devem ser aplicados outra vez.",
            ))
    if include_external:
        entries.append(_item(
            "Validação externa de alegações comerciais", "Não atestada por esta matriz",
            "Documentação primária e versão independente",
            "Contrato consultivo CAT-03 / revisão documental segregada",
            "A existência de um link ou alegação não comprova contrato vigente, "
            "registro regulatório, autenticidade nem falsidade; a matriz não "
            "ingere recibos assinados nem altera o CAT-03.",
        ))
        entries.append(_item(
            "Presença / citação generativa", "N/D",
            "Fontes externas e respostas generativas não equivalentes à SERP",
            "Sem denominador generativo autenticado neste cruzamento",
            "Search API e listas de links não comprovam menção, citação, "
            "posição generativa ou participação de mercado.",
        ))
    return {
        "contract": _CONTRACT, "audit_id": audit_id,
        "status": "DESCRIPTIVE_ONLY",
        "rows": entries[:_MAX_ROWS],
        "non_additive": True,
        "provider_requests": 0, "audit_writes": 0,
        "methodology": (
            "Observações possuem universos, métodos e tempos distintos. "
            "Nenhum total, média entre catálogos, alteração de score, "
            "certificação regulatória ou decisão de elegibilidade é gerada."
        ),
    }


def decision_evidence_matrix_html(projection: Mapping[str, Any]) -> str:
    """Render existing facts only; escape every dynamic field."""
    if (not isinstance(projection, Mapping)
            or projection.get("contract") != _CONTRACT
            or projection.get("status") != "DESCRIPTIVE_ONLY"
            or not isinstance(projection.get("rows"), list)
            or len(projection["rows"]) > _MAX_ROWS):
        return "<div class='notice'>Reconciliação de evidências: N/D.</div>"
    html = []
    for row in projection["rows"]:
        if not isinstance(row, Mapping):
            return "<div class='notice'>Reconciliação de evidências: N/D.</div>"
        html.append(
            "<tr>" + "".join(
                "<td>" + (
                    "<code>" + escape(str(row.get(field) or "N/D"), quote=True) + "</code>"
                    if field == "source"
                    else escape(str(row.get(field) or "N/D"), quote=True)
                ) + "</td>"
                for field in ("indicator", "observed", "scope", "source", "limitation")
            ) + "</tr>"
        )
    return (
        "<div data-contract='DECISION-EVIDENCE-604-001'>"
        "<p>Evidências da mesma AUD, sem consolidação numérica "
        "entre metodologias. Valores N/D não equivalem a zero e estados "
        "operacionais não certificam amostras representativas.</p>"
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Indicador</th><th>Valor observado</th><th>Escopo físico</th>"
        "<th>Origem</th><th>Limitação decisória</th>"
        "</tr></thead><tbody>" + "".join(html) + "</tbody></table></div>"
        "<p class='muted'>"
        + escape(str(projection.get("methodology") or ""), quote=True)
        + "</p></div>"
    )


__all__ = ["decision_evidence_matrix", "decision_evidence_matrix_html"]
