"""#602: read-only evidence inventory of optional SEO rule outcomes.

Never recompute or normalize SCORE-GEO-004, change weights, promote absent
optional files to causal failures, or modify a historical audit database.
"""
from __future__ import annotations

from contextlib import closing
from html import escape
from pathlib import Path
import sqlite3
from typing import Any

from rasai.optional_seo_policy import classify_seo_evidence

_RULE_LABELS = {
    "BR-GEO-003": "Sitemap convencional",
    "BR-GEO-013": "Declaração canonical",
    "BR-GEO-017": "Arquivo robots.txt",
}
_EVIDENCE_LABELS = {
    "OPTIONAL_ABSENCE": "Ausência opcional no escopo observado",
    "OBSERVED_CONFLICT": "Conflito técnico observado",
    "AVAILABLE": "Sinal encontrado no escopo observado",
    "UNKNOWN": "Evidência insuficiente ou contraditória",
}
_RESULT_LABELS = {
    "PASS": "Aprovado no contrato atual",
    "WARNING": "Advertência no contrato atual",
    "FAIL": "Falha no contrato atual",
    "NOT_APPLICABLE": "Não aplicável no contrato atual",
    "UNKNOWN": "Indeterminado no contrato atual",
}
_MAX_ROWS = 100


def inspect_optional_seo_evidence(database: Any, audit_id: str) -> tuple[dict[str, str], ...]:
    """Include available, conflicts and unknown evidence, not just penalties.

    An audit may contain multiple distinct rule executions. Render each
    separately; do not average them into an invented dimensional score.
    """
    try:
        db = Path(database)
        if (not isinstance(audit_id, str) or not audit_id.strip()
                or db.is_symlink() or not db.is_file()
                or any(Path(str(db) + suffix).exists()
                       for suffix in ("-wal", "-shm", "-journal"))):
            return ()
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2,
        )) as con:
            con.execute("PRAGMA query_only=ON")
            rows = con.execute(
                "SELECT r.rule_execution_id, c.rule_id, c.device, c.result, "
                "r.observed_value, s.scoring_version "
                "FROM score_contributions c "
                "JOIN scores s ON s.score_id=c.score_id "
                "JOIN rule_executions r ON r.rule_execution_id=c.rule_execution_id "
                "AND r.audit_id=s.audit_id AND r.rule_id=c.rule_id "
                "WHERE s.audit_id=? AND c.rule_id IN (?,?,?) "
                "AND c.device=s.device AND c.dimension=s.dimension "
                "ORDER BY c.rule_id,c.device,r.rule_execution_id LIMIT ?",
                (audit_id, *_RULE_LABELS, _MAX_ROWS + 1),
            ).fetchall()
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return ()
    if len(rows) > _MAX_ROWS:
        # Do not publish a silently truncated or biased population.
        return ()
    projected: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for execution_id, rule_id, device, result, observed, version in rows:
        if (not isinstance(execution_id, str) or not execution_id.strip()
                or not isinstance(device, str) or not device.strip()
                or version != "SCORE-GEO-004"):
            return ()
        key = (execution_id, rule_id, device)
        if key in seen:
            return ()
        seen.add(key)
        state = classify_seo_evidence(rule_id, observed)
        projected.append({
            "rule": rule_id,
            "signal": _RULE_LABELS[rule_id],
            "device": device,
            "evidence": _EVIDENCE_LABELS.get(state, _EVIDENCE_LABELS["UNKNOWN"]),
            "current_result": _RESULT_LABELS.get(str(result), "Indeterminado"),
        })
    return tuple(projected)


def optional_seo_evidence_matrix_html(database: Any, audit_id: str) -> str:
    """Advisory report section with explicit evidence vs scoring separation."""
    rows = inspect_optional_seo_evidence(database, audit_id)
    if not rows:
        return ""
    table = "".join(
        "<tr>"
        + "".join("<td>" + escape(row[key], quote=True) + "</td>"
                  for key in ("rule", "signal", "device", "evidence", "current_result"))
        + "</tr>" for row in rows
    )
    return (
        "<section id='optional-seo-evidence-matrix' class='section' "
        "data-contract='OPTIONAL-SEO-EVIDENCE-602-001'>"
        "<h2>Evidências dos sinais SEO opcionais</h2>"
        "<p>O inventário distingue sinal disponível, ausência opcional, "
        "conflito observado e informação inconclusiva. O estado do SCORE-GEO-004 "
        "vigente é apresentado separadamente e não é recalculado. "
        "Um robots.txt encontrado não atesta permissão de rastreamento; "
        "a ausência de /sitemap.xml não exclui sitemaps em outros caminhos. "
        "Canonical ausente não demonstra duplicidade nem bloqueio.</p>"
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Regra</th><th>Sinal</th><th>Dispositivo</th>"
        "<th>Evidência observada</th><th>Resultado da regra vigente</th>"
        "</tr></thead><tbody>" + table + "</tbody></table></div>"
        "<p class='muted'>Este inventário é interpretativo; não altera pesos, "
        "readiness gates, confiança, cobertura, SARI ou snapshots antigos. "
        "Alteração do efeito numérico requer decisão metodológica e nova "
        "versão de contrato.</p></section>"
    )


__all__ = ["inspect_optional_seo_evidence", "optional_seo_evidence_matrix_html"]
