"""Deterministic association between findings and concrete M14 DOM observations."""

from __future__ import annotations

from rasai.m14_persistence import ElementObservation, M14Persistence
from rasai.persistence import AuditPersistence, AuditWorkspace


_RULE_TAGS: dict[str, frozenset[str]] = {
    "BR-GEO-011": frozenset({"meta"}),
    "BR-GEO-012": frozenset({"meta"}),
    "BR-GEO-013": frozenset({"link"}),
    "BR-GEO-014": frozenset({"link"}),
    "BR-GEO-015": frozenset({"meta", "link"}),
    "BR-GEO-025": frozenset({"main"}),
    "BR-GEO-026": frozenset({"main"}),
    "BR-GEO-027": frozenset({"main"}),
    "BR-GEO-028": frozenset({"title"}),
    # BR-GEO-029 deliberately has no single-node mapping: heading hierarchy is
    # a document/set property and fabricating one selector would imply false precision.
    "BR-GEO-030": frozenset({"main"}),
    "BR-GEO-034": frozenset({"script"}),
    "BR-GEO-035": frozenset({"script"}),
    "BR-GEO-036": frozenset({"script"}),
    "BR-GEO-037": frozenset({"script"}),
}


def link_findings_to_elements(
    *,
    finding_ids: tuple[str, ...],
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
) -> int:
    """Link a finding only when its rule identifies an unambiguous observed node."""

    linked = 0
    with M14Persistence(workspace) as m14:
        for finding_id in finding_ids:
            finding = persistence.findings.get(finding_id)
            if finding is None:
                continue
            tags = _RULE_TAGS.get(finding.rule_id)
            if not tags:
                continue
            execution = persistence.rule_executions.get(finding.rule_execution_id)
            if execution is None or execution.snapshot_id is None:
                continue

            candidates = tuple(
                observation
                for observation in m14.list_for_snapshot(execution.snapshot_id)
                if observation.tag_name in tags and _matches_rule(finding.rule_id, observation)
            )
            # A single deterministic node is required.  Multiple matches remain
            # document/set-level evidence rather than choosing an arbitrary node.
            if len(candidates) != 1:
                continue
            m14.link_finding(finding_id, candidates[0].element_observation_id)
            linked += 1
    return linked


def _matches_rule(rule_id: str, observation: ElementObservation) -> bool:
    html = (observation.outer_html or "").casefold()
    if rule_id in {"BR-GEO-011", "BR-GEO-012"}:
        return observation.tag_name == "meta" and "robots" in html
    if rule_id in {"BR-GEO-013", "BR-GEO-014"}:
        return observation.tag_name == "link" and "canonical" in html
    if rule_id == "BR-GEO-015":
        return (
            (observation.tag_name == "meta" and "robots" in html)
            or (observation.tag_name == "link" and "canonical" in html)
        )
    if rule_id in {"BR-GEO-034", "BR-GEO-035", "BR-GEO-036", "BR-GEO-037"}:
        return observation.tag_name == "script" and "application/ld+json" in html
    return True
