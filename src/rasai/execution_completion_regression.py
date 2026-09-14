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

from contextlib import contextmanager
import os
from typing import Any, Iterator, Mapping

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
    """Carry profile policy into the child-process environment for this execution only."""
    try:
        from rasai import console_execution_profile_readiness as readiness
        from rasai import console_execution_profiles as profiles
    except ImportError:
        return

    def wrap_effective_profile() -> None:
        effective = profiles.effective_profile
        if bool(getattr(effective, "_rasai_execution_gsc_marker", False)):
            return

        @contextmanager
        def effective_profile_with_execution_marker(
            state: Any,
            session: Any | None = None,
        ) -> Iterator[None]:
            current = session or profiles.active_profile(state)
            policy = readiness.gsc_profile_policy(current)
            existed = _EXECUTION_GSC_POLICY_ENV in os.environ
            previous = os.environ.get(_EXECUTION_GSC_POLICY_ENV)
            try:
                if current is None or policy == readiness.GSC_PROFILE_INHERIT:
                    os.environ.pop(_EXECUTION_GSC_POLICY_ENV, None)
                else:
                    os.environ[_EXECUTION_GSC_POLICY_ENV] = policy
                with effective(state, current):
                    yield
            finally:
                if existed and previous is not None:
                    os.environ[_EXECUTION_GSC_POLICY_ENV] = previous
                elif not existed:
                    os.environ.pop(_EXECUTION_GSC_POLICY_ENV, None)

        effective_profile_with_execution_marker._rasai_execution_gsc_marker = True  # type: ignore[attr-defined]
        effective_profile_with_execution_marker._rasai_original = effective  # type: ignore[attr-defined]
        profiles.effective_profile = effective_profile_with_execution_marker

    # Normal console order installs AI policy before readiness/profile composition.
    # Wrap the readiness installer so the marker sits outside every existing overlay.
    original_installer = readiness._install_profile_gsc_overlay
    if not bool(getattr(original_installer, "_rasai_execution_gsc_marker", False)):
        def install_profile_gsc_overlay_with_marker() -> None:
            original_installer()
            wrap_effective_profile()

        install_profile_gsc_overlay_with_marker._rasai_execution_gsc_marker = True  # type: ignore[attr-defined]
        install_profile_gsc_overlay_with_marker._rasai_original = original_installer  # type: ignore[attr-defined]
        readiness._install_profile_gsc_overlay = install_profile_gsc_overlay_with_marker

    # Tests/embedders may have installed readiness before this module. Repair that
    # composition in place as well; the wrapper is idempotent.
    if bool(getattr(readiness, "_INSTALLED", False)):
        wrap_effective_profile()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_m24_resource_universe_alignment()
    _install_gsc_collection_execution_gate()
    _install_console_gsc_execution_marker()
    _INSTALLED = True
