"""Opt-in GEO multi-query orchestration over the EXISTING Perplexity/AI engines.

No new HTTP client, retry logic, pricing adapter or provider registry. A durable
batch reservation precedes every external request; ambiguous outcomes are never
resent automatically. Only the console's authorised initial-AUD path calls this.
"""
from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Callable

from rasai.geo_multiquery_batch import (
    latest_batch, record_item, request_fingerprint, reserve_batch,
)


def execute_geo_multiquery_for_audit(
    state: Any,
    runner: Callable[..., Any],
    workspace_path: Path,
    audit_id: str,
    search_kwargs: dict[str, Any],
) -> int:
    """Execute each query separately to preserve physical source attribution."""
    from rasai.persistence import AuditWorkspace
    from rasai.geo_observation import materialize_geo_observation
    from rasai.geo_ai import execute_geo_ai
    from rasai.report_completion import materialize_catalog_report_projection

    queries = tuple(getattr(state, "perplexity_queries", ()) or ())
    mode = str(search_kwargs["search_type"]).lower()
    expected = request_fingerprint(queries, mode)
    if getattr(state, "geo_multiquery_approval", "") != expected:
        state.perplexity_last_status = "COMPLETE_WITH_LIMITATIONS"
        state.perplexity_last_detail = (
            "GEO multiquery não executada: autorização financeira para "
            "requisições individuais ausente ou desatualizada. "
            "Revise CAT-05 > Perplexity > 5; zero chamadas externas."
        )
        return 1

    start = time.monotonic()
    try:
        workspace = AuditWorkspace.open(workspace_path)
        database = Path(workspace.database)
        batch_id = reserve_batch(database, audit_id, queries, mode)
    except Exception as exc:
        state.perplexity_last_status = "COMPLETE_WITH_LIMITATIONS"
        state.perplexity_last_detail = (
            "GEO multiquery não iniciada: reserva persistente indisponível "
            f"({type(exc).__name__}); zero chamadas externas."
        )
        return 1

    successful = 0
    ai_available = 0
    source_count = 0
    known_cost = 0.0
    cost_complete = True
    for pos, query in enumerate(queries):
        options = dict(search_kwargs)
        options["query"] = (query,)
        try:
            result = runner(workspace, **options)
        except Exception as exc:
            # The request might have reached Perplexity and been billed.
            # The pre-reserved item remains identifiable; NEVER retry here.
            record_item(database, audit_id, batch_id, pos, run_id=None,
                        search_state="PENDING_UNCERTAIN",
                        geo_ai_state="NOT_EXECUTED",
                        reason="POSSIBLY_BILLABLE_" + type(exc).__name__)
            cost_complete = False
            continue

        run_id = str(getattr(result, "run_id", "") or "")
        search_state = str(getattr(result, "status", "UNAVAILABLE") or "UNAVAILABLE")
        source_count += len(getattr(result, "sources", ()) or ())
        pricing = getattr(result, "pricing", None)
        cost = getattr(pricing, "estimated_cost", None)
        if cost is None:
            cost_complete = False
        else:
            known_cost += float(cost)
        ai_state = "NOT_EXECUTED"
        reason = None
        if search_state == "SUCCESS":
            successful += 1
            try:
                # Existing canonical selectors intentionally inspect the latest
                # verified single-query run. No synthetic source mapping.
                materialize_geo_observation(
                    database, audit_id, source_run_id=run_id,
                )
                ai_state = execute_geo_ai(
                    database, audit_id,
                    provider_selection=str(getattr(state, "ai_provider", "none")),
                    source_run_id=run_id,
                )
                if ai_state == "AVAILABLE":
                    ai_available += 1
            except Exception as exc:
                ai_state = "UNAVAILABLE"
                reason = "GEO_AI_" + type(exc).__name__
        else:
            reason = "PERPLEXITY_" + search_state

        record_item(
            database, audit_id, batch_id, pos, run_id=run_id or None,
            search_state=search_state, geo_ai_state=ai_state, reason=reason,
        )

    # One report projection for the entire batch; never start another provider.
    try:
        if (Path(workspace.root) / "report-catalog").exists():
            completion = materialize_catalog_report_projection(
                audit_id=audit_id, workspace=workspace,
            )
            if completion.renderer_errors:
                cost_complete = False
    except Exception:
        cost_complete = False

    state.perplexity_last_duration_seconds = max(time.monotonic() - start, 0.0)
    complete = successful == len(queries) and ai_available == len(queries)
    state.perplexity_last_status = "COMPLETE" if complete else "COMPLETE_WITH_LIMITATIONS"
    state.perplexity_last_detail = (
        f"Perplexity GEO por consulta | lote={batch_id} | "
        f"queries={len(queries)} | requests previstos={len(queries)} | "
        f"Search SUCCESS={successful}/{len(queries)} | fontes={source_count} | "
        f"GEO IA AVAILABLE={ai_available}/{len(queries)} | "
        + (f"custo Search estimado=USD {known_cost:.6f}"
           if cost_complete else "custo Search completo=N/D")
        + " | custo de IA generativa: consultar ledger canônico"
    )
    return 0 if complete else 1
