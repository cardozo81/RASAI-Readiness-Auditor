"""Read-only explanation of optional SEO signals penalized by SCORE-GEO-004.

These numbers describe isolated contributions under the *current* contract.
They are not a counterfactual score, an alternative scorer or a vendor rule.
"""
from __future__ import annotations

from html import escape
from math import isfinite
import sqlite3
from typing import Any

from rasai.optional_seo_policy import classify_seo_evidence

_OPTIONAL_RULES = {
    "BR-GEO-003": ("Sitemap convencional não observado", "DISCOVERY_ACCESS"),
    "BR-GEO-017": ("robots.txt ausente", "DISCOVERY_ACCESS"),
    "BR-GEO-013": ("Canonical não declarada", "INDEXABILITY"),
}


def _isolated_optional_absence(rule_id: str, raw: Any) -> bool:
    # Fail closed on malformed, duplicate-key or unknown provider evidence.
    return classify_seo_evidence(rule_id, raw) == "OPTIONAL_ABSENCE"


def optional_seo_penalties(database: Any, audit_id: str) -> list[dict[str, Any]]:
    """Only verified absence + matching score contribution is reportable."""
    try:
        with sqlite3.connect(database) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT c.rule_id,c.dimension,c.device,c.weight,c.result_factor,"
                "c.result,r.observed_value,s.scoring_version "
                "FROM score_contributions c "
                "JOIN rule_executions r ON r.rule_execution_id=c.rule_execution_id "
                "JOIN scores s ON s.score_id=c.score_id "
                "WHERE s.audit_id=? AND c.rule_id IN (?,?,?) AND "
                "c.dimension=s.dimension AND c.device=s.device "
                "ORDER BY c.rule_id,c.device",
                (audit_id, *_OPTIONAL_RULES),
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    items: list[dict[str, Any]] = []
    for row in rows:
        rule_id = str(row["rule_id"])
        if (
            str(row["scoring_version"] or "") != "SCORE-GEO-004"
            or str(row["result"] or "").upper() != "WARNING"
            or not _isolated_optional_absence(rule_id, row["observed_value"])
            or str(row["dimension"]) != _OPTIONAL_RULES[rule_id][1]
        ):
            continue
        try:
            weight = float(row["weight"])
            factor = float(row["result_factor"])
        except (TypeError, ValueError, OverflowError):
            continue
        if not (isfinite(weight) and isfinite(factor) and 0 <= weight <= 1 and 0 <= factor <= 1):
            continue
        items.append({
            "rule_id": rule_id,
            "label": _OPTIONAL_RULES[rule_id][0],
            "device": str(row["device"] or "-"),
            "dimension": str(row["dimension"]),
            "isolated_discount_points": round(100 * weight * (1 - factor), 4),
            "version": str(row["scoring_version"] or "-"),
        })
    return items


def optional_seo_notice_html(database: Any, audit_id: str) -> str:
    observed = optional_seo_penalties(database, audit_id)
    if not observed:
        return ""
    rows = "".join(
        "<tr>"
        + "<td><code>" + escape(item["rule_id"]) + "</code></td>"
        + "<td>" + escape(item["label"]) + "</td>"
        + "<td>" + escape(item["device"]) + "</td>"
        + "<td>" + escape(item["dimension"]) + "</td>"
        + "<td>" + f"{item['isolated_discount_points']:.2f}" + "</td>"
        + "</tr>"
        for item in observed
    )
    return (
        "<section id='seo-optional-policy-observation' class='section'>"
        "<h2>Interpretação de sinais SEO opcionais</h2>"
        "<p>A ausência isolada de robots.txt, canonical declarada ou sitemap "
        "convencional não comprova bloqueio, falha de indexação ou ausência "
        "de sitemap em outros caminhos. O SCORE-GEO-004 vigente ainda reduz "
        "o valor da dimensão nos casos abaixo. O desconto é uma contribuição "
        "isolada, <strong>não</strong> uma projeção de novo índice SARI.</p>"
        "<div class='table-wrap'><table><thead><tr><th>Regra</th><th>Observação</th>"
        "<th>Dispositivo</th><th>Dimensão</th><th>Desconto atual (pontos da dimensão)"
        "</th></tr></thead><tbody>" + rows + "</tbody></table></div>"
        "<p class='muted'>A política de classificação e pesos está sob revisão "
        "metodológica versionada. Nenhum score persistido foi recalculado.</p>"
        "</section>"
    )
