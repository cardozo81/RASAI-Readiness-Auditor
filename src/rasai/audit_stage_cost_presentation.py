"""#319: bounded post-hoc stage timing and costs for console/report.

No provider calls, original AUD writes, score changes or exclusive-phase timing
claims. Both M18 and M20 physical attempt ledgers are included once.
"""
from __future__ import annotations

from contextlib import closing
from html import escape
import math
from pathlib import Path
import sqlite3
from typing import Any

from rasai.audit_attempt_timeline import read_audit_attempt_timeline
from rasai.audit_duration_forecast import _m21_http_request_sums

_STAGE_LABELS = {
    "CONTENT_REMEDIATION": "Remediação de conteúdo · IA (M20)",
    "DIRECTED_ANALYSIS": "Análise Direcionada · opcional",
    "IMPROVEMENT_INTELLIGENCE": "Improvement Intelligence · IA",
    "COMPETITIVE_AI": "Comparação competitiva · IA",
    "EXTERNAL_SEARCH_API": "Pesquisa externa Search API · opcional",
    "SEMANTIC_ANALYSIS": "Análise semântica · IA",
    "TECHNICAL_REMEDIATION": "Remediação técnica · IA",
}
_NON_AI = (
    "Captura HTTP e renderização",
    "Desempenho web · duração da fase",
    "Apdex navegação e experiência",
    "Extração e análise determinística",
    "Montagem do relatório",
)
_DISCLOSURE = (
    "Somas de tentativas IA podem conter sobreposição; união ativa de chamadas "
    "não é duração da AUD. Tempos de PSI/CrUX são somas de requests HTTP, não "
    "wall-clock de fase. Custos técnicos observados ou estimados após a chamada "
    "não são faturas nem previsão inicial. Análise Direcionada e Search API "
    "opcionais não pertencem ao forecast central sem prova de inclusão. "
    "Fases sem cronômetros exclusivos verificados permanecem N/D. "
    "Tentativas do ledger de fulfillment incluem recuperações e trabalhos "
    "que podem sobrepor IA/HTTP; não são fases exclusivas nem tempo não-IA."
)


def _duration(value: object) -> str:
    if type(value) not in (int, float):
        return "N/D"
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        return "N/D"
    return f"{numeric / 1000:.2f} s"


def _missing(reason: str) -> dict[str, Any]:
    return {
        "status": "NOT_VERIFIABLE", "reason": reason,
        "stages": [], "http_requests": [], "attempts": None,
        "total_summed_ms": None, "total_union_ms": None,
        "non_ai_stages": _NON_AI, "limitations": _DISCLOSURE,
        "fulfillment": {"status": "NOT_AVAILABLE", "components": []},
        "provider_requests": 0, "audit_writes": 0,
    }


def inspect_stage_economics(database: Path, audit_id: str) -> dict[str, Any]:
    """No partial census, cross-AUD join, concurrent journal or implicit writes."""
    if not isinstance(audit_id, str) or not audit_id.strip():
        return _missing("AUD_ID_UNAVAILABLE")
    try:
        db = Path(database)
        if db.is_symlink() or not db.is_file():
            return _missing("AUD_DATABASE_UNAVAILABLE")
        if any(Path(str(db) + suffix).exists()
               for suffix in ("-wal", "-shm", "-journal")):
            return _missing("AUD_DATABASE_NOT_CHECKPOINTED")
        timeline = read_audit_attempt_timeline(db, audit_id, sealed_source=True)
        if len(timeline.stages) > 30:
            return _missing("TOO_MANY_STAGE_IDENTITIES")
        stages = []
        for stage in timeline.stages:
            covered = stage.attempts - stage.unpriced_attempts
            stages.append({
                "name": _STAGE_LABELS.get(stage.name, stage.name),
                "operation": stage.name,
                "attempts": stage.attempts,
                "summed_ms": stage.summed_duration_ms,
                "active_ms": stage.union_active_ms,
                "overlap_ms": stage.overlapping_duration_ms,
                "unknown_intervals": stage.unknown_intervals,
                "priced_attempts": covered,
                "observed_cost_attempts": stage.observed_cost_attempts,
                "usd_posthoc": stage.priced_usd_estimate,
                "usd_provider_observed": stage.priced_usd_provider_observed,
                "usd_cost_comparable": covered == stage.attempts,
            })
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro&immutable=1",
            uri=True, timeout=2,
        )) as connection:
            connection.execute("PRAGMA query_only=ON")
            http = _m21_http_request_sums(connection, audit_id)
            from rasai.audit_fulfillment_stage_timing import fulfillment_attempt_intervals
            work = fulfillment_attempt_intervals(connection, audit_id)
        return {
            "status": "READ_ONLY_OBSERVED" if timeline.attempts else "NO_AI_ATTEMPTS",
            "reason": None, "stages": stages,
            "http_requests": [
                {"service": name, "summed_ms": value}
                for name, value in sorted(http.items())
            ],
            "attempts": timeline.attempts,
            "total_summed_ms": timeline.summed_duration_ms,
            "total_union_ms": timeline.union_active_ms,
            "non_ai_stages": _NON_AI, "limitations": _DISCLOSURE,
            "fulfillment": work,
            "provider_requests": 0, "audit_writes": 0,
        }
    except (sqlite3.Error, OSError, ValueError, TypeError, OverflowError):
        return _missing("LEDGER_OR_SCHEMA_UNVERIFIABLE")


def _price(stage: dict[str, Any]) -> str:
    if not stage["usd_cost_comparable"]:
        return "N/D (%s/%s com preço USD)" % (
            stage["priced_attempts"], stage["attempts"],
        )
    amount = stage["usd_posthoc"] + stage["usd_provider_observed"]
    if not math.isfinite(amount):
        return "N/D"
    return "USD %.6f (%s/%s; %s do provedor)" % (
        amount, stage["priced_attempts"], stage["attempts"],
        stage["observed_cost_attempts"],
    )


def stage_console_lines(projection: dict[str, Any]) -> tuple[str, ...]:
    if projection["status"] == "NOT_VERIFIABLE":
        return ("Tempos/custos por etapa: N/D (" + projection["reason"] + ")",)
    lines = [
        "Tentativas IA (M18+M20): %s; soma %s; união ativa %s." % (
            projection["attempts"], _duration(projection["total_summed_ms"]),
            _duration(projection["total_union_ms"]),
        )
    ]
    for stage in projection["stages"]:
        lines.append("%s: %s chamada(s); ativo %s; soma %s; custo %s." % (
            stage["name"], stage["attempts"], _duration(stage["active_ms"]),
            _duration(stage["summed_ms"]), _price(stage),
        ))
    for row in projection["http_requests"]:
        lines.append("HTTP %s: soma de requests %s (não tempo de fase)." % (
            row["service"], _duration(row["summed_ms"]),
        ))
    work = projection.get("fulfillment") or {}
    if work.get("status") == "OBSERVED_NONEXCLUSIVE_WORK_INTERVALS":
        lines.append(
            "Tentativas do ledger de atividades (não exclusivas): "
            + str(work.get("attempts")) + "."
        )
        for group in work.get("components", ()):
            lines.append(
                "Atividade %s: %s tentativa(s), %s cronometrada(s), "
                "recuperações %s; soma %s, união %s (não tempo de fase)."
                % (group["component"], group["attempts"],
                   group["complete_time_intervals"],
                   group["reprocess_attempts"], _duration(group["summed_ms"]),
                   _duration(group["union_active_ms"]))
            )
    lines.append("Sem tempo exclusivo: " + "; ".join(_NON_AI) + " = N/D.")
    lines.append(_DISCLOSURE)
    return tuple(lines)


def stage_report_html(projection: dict[str, Any]) -> str:
    """Safe report HTML; unknown/corrupt cost is never silently zero."""
    if projection["status"] == "NOT_VERIFIABLE":
        return ("<div class='notice'>Telemetria por etapa: N/D (" +
                escape(projection["reason"], quote=True) +
                "). Fonte SQLite ou identidade de tentativa não comprovada.</div>")
    rows = []
    for stage in projection["stages"]:
        rows.append((stage["name"], str(stage["attempts"]),
                     _duration(stage["active_ms"]),
                     _duration(stage["summed_ms"]), _price(stage)))
    for http in projection["http_requests"]:
        rows.append(("HTTP " + http["service"] + " (requests)", "N/D",
                     "N/D", _duration(http["summed_ms"]), "N/D"))
    work = projection.get("fulfillment") or {}
    if work.get("status") == "OBSERVED_NONEXCLUSIVE_WORK_INTERVALS":
        for group in work.get("components", ()):
            rows.append((
                "Atividade registrada: " + group["component"]
                + " (não exclusiva; recuperação %s)" % group["reprocess_attempts"],
                str(group["attempts"]), _duration(group["union_active_ms"]),
                _duration(group["summed_ms"]), "N/D",
            ))
    rows.extend((name, "N/D", "N/D", "N/D", "N/D")
                for name in projection["non_ai_stages"])
    cells = "".join(
        "<tr>" + "".join("<td>" + escape(value, quote=True) + "</td>"
                         for value in row) + "</tr>"
        for row in rows
    )
    return (
        "<p>Tentativas IA de M18 e M20: <strong>%s</strong>; soma "
        "<strong>%s</strong>; união ativa <strong>%s</strong>. "
        "União ativa não equivale a duração da AUD.</p>"
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Operação técnica</th><th>Tentativas IA</th>"
        "<th>Tempo ativo</th><th>Soma de durações</th><th>Custo técnico USD</th>"
        "</tr></thead><tbody>%s</tbody></table></div>"
        "<p class='muted'>%s</p>"
    ) % (
        projection["attempts"], _duration(projection["total_summed_ms"]),
        _duration(projection["total_union_ms"]), cells,
        escape(_DISCLOSURE, quote=True),
    )
