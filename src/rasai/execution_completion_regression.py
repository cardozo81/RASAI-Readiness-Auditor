"""Regression fixes proven by real AUD completion tests.

This layer addresses two integration mismatches that are not scoring-policy changes:

* M24 must validate resource assessments against the same resource-scoped evidence
  universe that is projected to the provider schema/prompt. Diagnostic evidence and
  deterministic baseline evidence for the same resource are both legitimate inputs.
* A console execution-profile GSC decision must cross the subprocess boundary. The
  global GSC toggle is configuration state, while the profile decision is execution
  state; a disabled execution must never call Google even when the global toggle is on.

CrUX transient failures and source HTTP failures are intentionally not reclassified here.
They keep the semantics defined by their own contracts.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

_EXECUTION_GSC_POLICY_ENV = "RASAI_EXECUTION_GSC_POLICY"
_INSTALLED = False


def _canonical_resource_evidence(
    facts: list[dict[str, Any]],
) -> dict[str, frozenset[str]]:
    """Return the single evidence universe used by schema, prompt and validator."""
    buckets: dict[str, list[str]] = {}
    for fact in facts:
        if not isinstance(fact, Mapping):
            continue
        if str(fact.get("scoring_role") or "") != "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE":
            continue
        resource = str(fact.get("category") or "").strip().upper()
        if resource not in {"ROBOTS", "SITEMAP"}:
            continue
        raw_evidence = fact.get("evidence_ids")
        if not isinstance(raw_evidence, (list, tuple, set, frozenset)):
            continue
        bucket = buckets.setdefault(resource, [])
        for raw in raw_evidence:
            evidence_id = str(raw or "").strip()
            if evidence_id and evidence_id not in bucket:
                bucket.append(evidence_id)
    return {
        resource: frozenset(values)
        for resource, values in buckets.items()
        if values
    }


def _install_m24_resource_universe_alignment() -> None:
    from rasai import m24_ai

    original = m24_ai._call
    if bool(getattr(original, "_rasai_resource_universe_aligned", False)):
        return

    def call_with_canonical_resource_evidence(
        candidate: Any,
        *,
        facts: list[dict[str, Any]],
        allowed_codes: frozenset[str],
        allowed_evidence: frozenset[str],
        resource_evidence: Mapping[str, frozenset[str]],
        page_row: Mapping[str, Any],
        attempt_index: int,
    ):
        canonical = _canonical_resource_evidence(facts)
        return original(
            candidate,
            facts=facts,
            allowed_codes=allowed_codes,
            allowed_evidence=allowed_evidence,
            resource_evidence=canonical or resource_evidence,
            page_row=page_row,
            attempt_index=attempt_index,
        )

    call_with_canonical_resource_evidence._rasai_resource_universe_aligned = True  # type: ignore[attr-defined]
    call_with_canonical_resource_evidence._rasai_original = original  # type: ignore[attr-defined]
    m24_ai._call = call_with_canonical_resource_evidence


def _project_gsc_policy(environment: Mapping[str, str]) -> dict[str, str]:
    """Project execution-only GSC policy over a private environment copy."""
    from rasai.gsc_scope import GSC_ENABLED_ENV

    effective = {str(key): str(value) for key, value in environment.items()}
    policy = str(effective.get(_EXECUTION_GSC_POLICY_ENV) or "").strip().casefold()
    if policy == "disabled":
        effective[GSC_ENABLED_ENV] = "false"
    elif policy == "required":
        effective[GSC_ENABLED_ENV] = "true"
    elif policy == "if-compatible":
        effective.pop(GSC_ENABLED_ENV, None)
    return effective


def _install_gsc_collection_execution_gate() -> None:
    """Make the child audit process honor the execution-profile GSC policy."""
    from rasai import standards_gsc_observability_runtime as runtime

    original = runtime.collect_configured_search_console
    if bool(getattr(original, "_rasai_execution_gsc_policy_gate", False)):
        return

    def collect_with_execution_policy(
        *,
        audit_id: str,
        workspace: Any,
        env: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        source = os.environ if env is None else env
        effective = _project_gsc_policy(source)
        return original(audit_id=audit_id, workspace=workspace, env=effective)

    collect_with_execution_policy._rasai_execution_gsc_policy_gate = True  # type: ignore[attr-defined]
    collect_with_execution_policy._rasai_original = original  # type: ignore[attr-defined]
    runtime.collect_configured_search_console = collect_with_execution_policy


def _install_console_gsc_execution_marker() -> None:
    """Compatibility hook; parent-process marker projection is intentionally disabled.

    ``RASAI_EXECUTION_GSC_POLICY`` belongs only to the private subprocess environment
    built by ``execution_context_isolation``. Keeping this public installer as a no-op
    avoids breaking embedders/tests that still invoke it while preventing any temporary
    mutation of the operator-owned console environment.
    """
    return


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_m24_resource_universe_alignment()
    _install_gsc_collection_execution_gate()
    _install_console_gsc_execution_marker()
    _INSTALLED = True