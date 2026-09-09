"""Deterministic Rules Engine core for M5."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable, Iterable

from rasai.domain import RuleResult, Severity


class RuleScope(StrEnum):
    GLOBAL = "GLOBAL"
    PAGE = "PAGE"
    SNAPSHOT = "SNAPSHOT"


@dataclass(frozen=True, slots=True)
class Check:
    """Smallest deterministic validation used by a Business Rule."""

    check_id: str
    passed: bool | None
    observed: Any
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    rule_id: str
    name: str
    category: str
    dimension: str
    scope: RuleScope
    dependencies: tuple[str, ...] = ()
    severity: Severity = Severity.INFO
    basis: str = "HEURISTIC"
    scoring_group: str | None = None


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    result: RuleResult
    observed_value: Any
    expected_condition: str
    checks: tuple[Check, ...] = ()
    reason: str | None = None


class RuleRegistry:
    """Versioned in-process registry for deterministic rule definitions."""

    def __init__(self, definitions: Iterable[RuleDefinition] = ()) -> None:
        self._definitions: dict[str, RuleDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: RuleDefinition) -> None:
        if definition.rule_id in self._definitions:
            raise ValueError(f"duplicate rule_id: {definition.rule_id}")
        self._definitions[definition.rule_id] = definition

    def get(self, rule_id: str) -> RuleDefinition:
        try:
            return self._definitions[rule_id]
        except KeyError as exc:
            raise KeyError(f"rule not registered: {rule_id}") from exc

    def ids(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def definitions(self) -> tuple[RuleDefinition, ...]:
        return tuple(self._definitions.values())


@dataclass(frozen=True, slots=True)
class DependencyState:
    applicable: bool
    result: RuleResult | None = None
    reason: str | None = None


class DependencyResolver:
    """Prevent derivative failures when a prerequisite is unavailable or failed."""

    _BLOCKING = {RuleResult.FAIL, RuleResult.ERROR, RuleResult.UNKNOWN, RuleResult.NOT_APPLICABLE}

    def resolve(
        self,
        definition: RuleDefinition,
        result_lookup: Callable[[str], RuleResult | None],
    ) -> DependencyState:
        for dependency in definition.dependencies:
            result = result_lookup(dependency)
            if result is None:
                return DependencyState(
                    applicable=False,
                    result=RuleResult.UNKNOWN,
                    reason=f"DEPENDENCY_NOT_EXECUTED:{dependency}",
                )
            if result in self._BLOCKING:
                return DependencyState(
                    applicable=False,
                    result=RuleResult.NOT_APPLICABLE,
                    reason=f"DEPENDENCY_BLOCKED:{dependency}:{result.value}",
                )
        return DependencyState(applicable=True)


def baseline_registry() -> RuleRegistry:
    """Return the M5 registry for BR-GEO-001..018."""

    definitions = (
        RuleDefinition("BR-GEO-001", "Audit target must be valid and normalized", "ACQUISITION", "AUDITOR_INTEGRITY", RuleScope.GLOBAL, severity=Severity.CRITICAL, basis="OFFICIAL"),
        RuleDefinition("BR-GEO-002", "Every discovered URL must have traceable discovery provenance", "ACQUISITION", "AUDITOR_INTEGRITY", RuleScope.PAGE, severity=Severity.INFO, basis="OFFICIAL"),
        RuleDefinition("BR-GEO-003", "Sitemap resources must be acquired and interpreted when available", "DISCOVERY_ACCESS", "DISCOVERY_ACCESS", RuleScope.GLOBAL, severity=Severity.LOW, basis="STANDARD", scoring_group="SITEMAP"),
        RuleDefinition("BR-GEO-004", "HTTP acquisition artifacts must be preserved for reproducible analysis", "ACQUISITION", "AUDITOR_INTEGRITY", RuleScope.PAGE, severity=Severity.INFO, basis="OFFICIAL"),
        RuleDefinition("BR-GEO-005", "Page must be technically retrievable", "DISCOVERY_ACCESS", "DISCOVERY_ACCESS", RuleScope.PAGE, severity=Severity.HIGH, basis="STANDARD", scoring_group="PAGE_ACCESS"),
        RuleDefinition("BR-GEO-006", "Final HTTP response must be usable for intended page content", "DISCOVERY_ACCESS", "DISCOVERY_ACCESS", RuleScope.PAGE, dependencies=("BR-GEO-005",), severity=Severity.HIGH, basis="STANDARD", scoring_group="PAGE_ACCESS"),
        RuleDefinition("BR-GEO-007", "Redirect behavior must resolve without loops or invalid chains", "DISCOVERY_ACCESS", "DISCOVERY_ACCESS", RuleScope.PAGE, dependencies=("BR-GEO-005",), severity=Severity.HIGH, basis="STANDARD", scoring_group="REDIRECT"),
        RuleDefinition("BR-GEO-008", "Redirect chains must not introduce material crawl/accessibility problems", "DISCOVERY_ACCESS", "DISCOVERY_ACCESS", RuleScope.PAGE, dependencies=("BR-GEO-005", "BR-GEO-007"), severity=Severity.LOW, basis="HEURISTIC", scoring_group="REDIRECT"),
        RuleDefinition("BR-GEO-009", "Expected HTML documents must provide analyzable document content", "CONTENT_EXTRACTABILITY", "CONTENT_EXTRACTABILITY", RuleScope.PAGE, dependencies=("BR-GEO-005", "BR-GEO-006"), severity=Severity.HIGH, basis="STANDARD", scoring_group="RENDER_ACCESS"),
        RuleDefinition("BR-GEO-010", "Rendering failures must not prevent access to essential content", "CONTENT_EXTRACTABILITY", "CONTENT_EXTRACTABILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-005", "BR-GEO-009"), severity=Severity.HIGH, basis="HEURISTIC", scoring_group="RENDER_ACCESS"),
        RuleDefinition("BR-GEO-011", "Indexability directives must be consistently resolved", "INDEXABILITY", "INDEXABILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-005", "BR-GEO-009"), severity=Severity.HIGH, basis="STANDARD", scoring_group="INDEX_DIRECTIVES"),
        RuleDefinition("BR-GEO-012", "Explicit noindex directives must be identified correctly", "INDEXABILITY", "INDEXABILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-011",), severity=Severity.MEDIUM, basis="STANDARD", scoring_group="INDEX_DIRECTIVES"),
        RuleDefinition("BR-GEO-013", "Canonical declarations must be interpretable and non-conflicting", "INDEXABILITY", "INDEXABILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-009",), severity=Severity.MEDIUM, basis="STANDARD", scoring_group="CANONICAL"),
        RuleDefinition("BR-GEO-014", "Canonical target must be technically valid and contextually plausible", "INDEXABILITY", "INDEXABILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-013",), severity=Severity.MEDIUM, basis="HEURISTIC", scoring_group="CANONICAL"),
        RuleDefinition("BR-GEO-015", "JavaScript must not introduce unsafe canonical/indexability conflicts", "INDEXABILITY", "INDEXABILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-009", "BR-GEO-011"), severity=Severity.HIGH, basis="STANDARD", scoring_group="INDEX_DIRECTIVES"),
        RuleDefinition("BR-GEO-016", "Error-like pages must not masquerade as valid indexable pages", "INDEXABILITY", "INDEXABILITY", RuleScope.SNAPSHOT, dependencies=("BR-GEO-006",), severity=Severity.MEDIUM, basis="HEURISTIC", scoring_group="SOFT_ERROR"),
        RuleDefinition("BR-GEO-017", "robots.txt must be interpretable when present", "DISCOVERY_ACCESS", "DISCOVERY_ACCESS", RuleScope.GLOBAL, severity=Severity.MEDIUM, basis="STANDARD", scoring_group="ROBOTS"),
        RuleDefinition("BR-GEO-018", "Crawler access must be resolved independently per configured crawler", "DISCOVERY_ACCESS", "DISCOVERY_ACCESS", RuleScope.GLOBAL, dependencies=("BR-GEO-017",), severity=Severity.HIGH, basis="STANDARD", scoring_group="ROBOTS"),
    )
    return RuleRegistry(definitions)
