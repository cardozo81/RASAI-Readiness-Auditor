"""Read-only per-query GEO batch report projection; no network or DB writes."""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import sqlite3

from rasai.geo_multiquery_batch import latest_batch
from rasai.geo_temporal_provenance import _last_temporally_verified, _UNVERIFIABLE


def geo_multiquery_html(database: Path, audit_id: str) -> str:
    batch = latest_batch(database, audit_id)
    if not batch:
        return ""
    entries = batch["items"]
    # Do not present a stale batch after a newer independent Search request.
    try:
        with sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro",
                             uri=True) as con:
            latest = _last_temporally_verified(
                con, table="perplexity_search_runs", audit_id=audit_id,
                columns=("run_id", "started_at"), time_column="started_at",
            )
            if latest is _UNVERIFIABLE:
                return ""
            if latest is not None and latest[0] not in {
                item["run_id"] for item in entries if item.get("run_id")
            }:
                search_time = datetime.fromisoformat(
                    str(latest[1]).replace("Z", "+00:00"))
                batch_time = datetime.fromisoformat(
                    str(batch["created_at"]).replace("Z", "+00:00"))
                if (search_time.tzinfo is None or batch_time.tzinfo is None
                        or search_time.astimezone(timezone.utc)
                        >= batch_time.astimezone(timezone.utc)):
                    return ""
            ai_rows = {}
            has_ai = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='geo_ai_interpretations'"
            ).fetchone()
            if has_ai:
                for item in entries:
                    run_id = item.get("run_id")
                    if not isinstance(run_id, str) or not run_id:
                        continue
                    row = con.execute(
                        "SELECT state, summary, opportunities_json FROM "
                        "geo_ai_interpretations WHERE audit_id=? AND perplexity_run_id=? "
                        "ORDER BY created_at DESC LIMIT 1", (audit_id, run_id)
                    ).fetchone()
                    if row is not None:
                        ai_rows[run_id] = row
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return ""

    rows = []
    observed = 0
    interpreted = 0
    opportunities = 0
    for item in entries:
        state = str(item.get("search_state") or "N/D")
        geo_state = str(item.get("geo_ai_state") or "N/D")
        if state == "SUCCESS":
            observed += 1
        if geo_state == "AVAILABLE":
            interpreted += 1
        run_id = str(item.get("run_id") or "")
        saved = ai_rows.get(run_id)
        summary = ""
        if saved and saved[1] and geo_state == "AVAILABLE":
            summary = str(saved[1])[:2500]
        if saved and saved[2] and geo_state == "AVAILABLE":
            try:
                proposals = json.loads(saved[2])
                if isinstance(proposals, list):
                    opportunities += len(proposals)
            except (ValueError, TypeError):
                pass
        reason = str(item.get("reason") or "")
        detail = ("<p>" + escape(summary) + "</p>") if summary else ""
        if reason:
            detail += "<p>Limitação: " + escape(reason) + "</p>"
        rows.append(
            "<tr><td>" + escape(str(item.get("query") or "")) + "</td>"
            "<td>" + escape(state) + "</td>"
            "<td>" + escape(geo_state) + "</td>"
            "<td><code>" + escape(run_id or "N/D") + "</code>" + detail
            + "</td></tr>"
        )
    return (
        "<section><h2>Síntese GEO consolidada por consulta</h2>"
        "<p>Grupo de pesquisa externa com proveniência por consulta física. "
        "A consolidação é determinística e não executa outra IA.</p>"
        f"<p>Consultas pesquisadas: {observed}/{len(entries)}; "
        f"interpretações IA disponíveis: {interpreted}/{len(entries)}; "
        f"oportunidades referenciadas: {opportunities}. "
        "Resultados parciais não representam ausência de oportunidade.</p>"
        "<table><thead><tr><th>Consulta</th><th>Perplexity Search</th>"
        "<th>Interpretação GEO IA</th><th>Proveniência e síntese</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        "<p>Fontes da Search API não comprovam citação em respostas generativas. "
        "Custos de Search e IA são contabilizados separadamente nos ledgers.</p>"
        "</section>"
    )
