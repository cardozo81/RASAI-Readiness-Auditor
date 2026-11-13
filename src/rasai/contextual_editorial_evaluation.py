"""Reproducible C0 evaluation of the existing deterministic editorial queue.

This measures local contract sufficiency, not model quality or factual truth.
It deliberately permits zero qualified opportunities and never supplies a score.
"""
from collections import Counter

from rasai.contextual_ai_contract import KINDS, prepare_input

CONTRACT = "contextual-editorial-evaluation-v1"


def evaluate_editorial(report, *, source_inventory):
    snapshots, inputs, blocked = {}, {}, set()
    captures = report.get("captures", ())
    if len(captures) > 256:
        raise ValueError("editorial evaluation capture limit")
    for capture in captures:
        snapshot = capture["snapshot_id"]
        snapshots[snapshot] = capture
        try:
            inputs[snapshot] = prepare_input(report, snapshot, source_inventory=source_inventory,
                                             prepared_at=capture["captured_at"])
        except (ValueError, TypeError, KeyError):
            blocked.add(snapshot)
    results = []
    tasks = (report.get("reverse_review") or {}).get("tasks", ())
    if len(tasks) > 512:
        raise ValueError("editorial evaluation task limit")
    for task in tasks:
        refs = task.get("evidence_refs", ())
        involved = {r.get("snapshot_id") for r in refs}
        physical = bool(refs) and all(s in inputs and s not in blocked for s in involved)
        known_kind = task.get("kind") in KINDS
        if physical:
            physical = all(any(t["kind"] == task.get("kind") for t in inputs[s].payload["tasks"])
                           for s in involved)
        checks = dict(physical_evidence=physical,
            factual_support_or_explicit_nd=(known_kind and task.get("status") == "VALIDACAO_NECESSARIA"
                and task.get("evidence_sufficiency") in {"PARCIAL", "INSUFICIENTE"}),
            reviewable_materiality=known_kind,
            specific_action_and_human_validation=bool(known_kind and task.get("validation") and task.get("rationale")),
            no_score_or_authentication=("NOT_AN_ENGINE_FINDING" in task.get("limitations", ())
                and "NO_RANKING_OR_INDEXATION_INFERENCE" in task.get("limitations", ())),
            privacy=True)  # This result contains only counters, fixed labels and no captured text.
        results.append(dict(kind=task.get("kind") if known_kind else "UNKNOWN_N_D",
            state="COMPROVADO" if all(checks.values()) else "N/D", checks=checks))
    history = (report.get("semantic_v2") or {}).get("recommendation_counts") or {}
    coverage_nd = sum(c.get("surface") != "RENDERED_DOM"
                      or c.get("counts", {}).get("observed_occurrences") is None
                      or c.get("counts", {}).get("omitted", 0) > 0 for c in captures)
    states = Counter(r["state"] for r in results)
    return dict(contract=CONTRACT, baseline="AI=none", method="DETERMINISTIC_CONTRACT_CHECKS",
        counts=dict(historical_candidates=len(report.get("recommendations", ())),
            historical_non_actionable=history.get("not_actionable", 0),
            historical_nd=history.get("nd", 0), verification_candidates=len(tasks),
            qualified_conditional_verifications=states["COMPROVADO"],
            verification_nd=states["N/D"], capture_coverage_nd=coverage_nd,
            physical_scope_nd=len(blocked), qualified_opportunities=0),
        checks=results, ai_incremental_quality="N/D", provider_calls=0, network_requests=0,
        observed_external_cost=0, currency=None,
        limitations=["CONTRACT_SUFFICIENCY_IS_NOT_EDITORIAL_ACCEPTANCE",
            "CONDITIONAL_VERIFICATION_IS_NOT_PROVEN_OPPORTUNITY",
            "NO_CALIBRATED_CONFIDENCE_PERCENTAGE", "NO_AUTHORIZED_COMPARABLE_REAL_AI_OUTPUT",
            "C0_2_REQUIRES_AUTHORIZED_REAL_PILOT", "NO_SCORE_OR_RANKING_CHANGE"])
