"""Execution-local policy for selective AUD reprocessing.

The logical AUD remains immutable in identity/configuration.  One RPR may authorize a
subset of unresolved work and may choose an AI provider independently from the
original AUD.  The policy lives in a ContextVar so existing recovery call signatures
remain backward compatible while composed runtime wrappers can consult the same
decision before any collector/provider call.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence


AI_COMPONENTS = frozenset(
    {
        "SEMANTIC_AI",
        "TECHNICAL_AI",
        "CONTENT_REMEDIATION_AI",
        "IMPROVEMENT_INTELLIGENCE",
        "COMPETITIVE_INTELLIGENCE",
    }
)
_RESOLVED = frozenset({"SUCCESS", "DISABLED", "NOT_APPLICABLE"})

# Audit-wide components that cannot produce a meaningful result until the canonical
# core context exists. Component-level tokens are intentional: if discovery creates a
# new page/work-item during the same RPR, it remains inside the already-authorized
# dependency closure without requiring a second operator choice.
_SELECTION_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "WEB_PERFORMANCE": (
        "DISCOVERY_ACQUISITION",
        "HTTP_ACQUISITION",
        "RENDER_CAPTURE",
    ),
    "SYNTHETIC_APDEX": (
        "DISCOVERY_ACQUISITION",
        "HTTP_ACQUISITION",
        "RENDER_CAPTURE",
    ),
    "TECHNICAL_AI": (
        "DISCOVERY_ACQUISITION",
    ),
    "IMPROVEMENT_INTELLIGENCE": (
        "DISCOVERY_ACQUISITION",
        "HTTP_ACQUISITION",
        "RENDER_CAPTURE",
        "CONTENT_EXTRACTION",
    ),
}


@dataclass(frozen=True, slots=True)
class ReprocessPolicy:
    selected_items: frozenset[str] | None = None
    use_ai: bool | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_reasoning: str | None = None
    execution_context: Mapping[str, Any] | None = None

    def as_configuration(self) -> dict[str, Any]:
        value = {
            "selected_items": (
                sorted(self.selected_items) if self.selected_items is not None else None
            ),
            "use_ai": self.use_ai,
            "ai_provider": self.ai_provider,
            "ai_model": self.ai_model,
            "ai_reasoning": self.ai_reasoning,
        }
        if self.execution_context:
            value["execution_context"] = dict(self.execution_context)
        return value


_POLICY: ContextVar[ReprocessPolicy] = ContextVar(
    "rasai_reprocess_policy",
    default=ReprocessPolicy(),
)


def item_key(component: Any, scope_key: Any = "AUDIT") -> str:
    return f"{str(component or '').strip().upper()}::{str(scope_key or 'AUDIT').strip() or 'AUDIT'}"


def normalize_selected_items(values: Sequence[Any] | None) -> frozenset[str] | None:
    if values is None:
        return None
    normalized: set[str] = set()
    for raw in values:
        if isinstance(raw, Mapping):
            component = raw.get("component")
            scope_key = raw.get("scope_key", "AUDIT")
            if component:
                normalized.add(item_key(component, scope_key))
            continue
        text = str(raw or "").strip()
        if not text:
            continue
        if "::" in text:
            component, scope_key = text.split("::", 1)
            normalized.add(item_key(component, scope_key))
        elif "/" in text:
            component, scope_key = text.split("/", 1)
            normalized.add(item_key(component, scope_key))
        else:
            normalized.add(str(text).upper())
    return frozenset(normalized)


def current_policy() -> ReprocessPolicy:
    return _POLICY.get()


def _selection_contains(selected: frozenset[str] | set[str], item: Any) -> bool:
    component = str(getattr(item, "component", "") or "").strip().upper()
    key = item_key(component, getattr(item, "scope_key", "AUDIT"))
    return key in selected or component in selected


def expand_selected_items(
    workspace: Any,
    audit_id: str,
    values: Sequence[Any] | None,
    *,
    use_ai: bool | None = None,
) -> frozenset[str] | None:
    """Return the effective selective-RPR scope including mandatory prerequisites.

    The operator remains the source of intent. Dependency closure only adds work that
    is required to make an already-selected item executable; it never adds an
    unrelated optional capability. Successful requirements may match the effective
    policy but are still preserved because recovery loops only execute unresolved,
    retryable items.
    """
    normalized = normalize_selected_items(values)
    if normalized is None:
        return None

    selected: set[str] = set(normalized)
    from rasai.audit_fulfillment import list_work_items

    work = tuple(list_work_items(workspace, audit_id))
    changed = True
    while changed:
        changed = False

        selected_components = {
            (token.split("::", 1)[0] if "::" in token else token).strip().upper()
            for token in selected
        }
        for component in tuple(selected_components):
            # "Sem IA" blocks provider execution, not the non-AI data prerequisites
            # required by an explicitly selected AI requirement. This lets one RPR
            # recover evidence first while leaving the AI requirement pending.
            for dependency in _SELECTION_DEPENDENCIES.get(component, ()):
                if dependency not in selected:
                    selected.add(dependency)
                    changed = True

        for item in work:
            if not _selection_contains(selected, item):
                continue
            component = str(getattr(item, "component", "") or "").strip().upper()
            for blocker in blocking_dependencies(workspace, item):
                dep_component, sep, dep_scope = str(blocker).partition("/")
                key = item_key(dep_component, dep_scope if sep else "AUDIT")
                if key not in selected and dep_component.upper() not in selected:
                    selected.add(key)
                    changed = True

    return frozenset(selected)


def is_ai_component(component: Any) -> bool:
    return str(component or "").strip().upper() in AI_COMPONENTS


def item_selected(item: Any) -> bool:
    policy = current_policy()
    if policy.selected_items is None:
        return True
    component = str(getattr(item, "component", "") or "").strip().upper()
    key = item_key(component, getattr(item, "scope_key", "AUDIT"))
    return key in policy.selected_items or component in policy.selected_items


def item_executable(item: Any) -> bool:
    if not item_selected(item):
        return False
    policy = current_policy()
    if is_ai_component(getattr(item, "component", "")) and policy.use_ai is False:
        return False
    return True


def ai_execution_allowed() -> bool:
    return current_policy().use_ai is not False


def provider_override() -> tuple[str | None, str | None, str | None]:
    policy = current_policy()
    if policy.use_ai is not True:
        return None, None, None
    provider = str(policy.ai_provider or "").strip().casefold() or None
    model = str(policy.ai_model or "").strip() or None
    reasoning = str(policy.ai_reasoning or "").strip().upper() or None
    return provider, model, reasoning


def selected_counts(items: Sequence[Any]) -> tuple[int, int]:
    # Counts reflect the effective execution scope. An AI item named in selected_items
    # is not authorized when this RPR explicitly chose use_ai=False.
    selected = sum(1 for item in items if item_executable(item))
    return selected, max(0, len(items) - selected)


def blocking_dependencies(workspace: Any, item: Any) -> tuple[str, ...]:
    """Return unresolved hard prerequisites for one work item.

    The graph stays intentionally narrow: only dependencies required for the selected
    component to produce a meaningful result are represented here. Optional supporting
    integrations remain independent.
    """
    component = str(getattr(item, "component", "") or "").strip().upper()
    scope_key = str(getattr(item, "scope_key", "AUDIT") or "AUDIT")
    if component not in {
        "SEMANTIC_AI",
        "TECHNICAL_AI",
        "IMPROVEMENT_INTELLIGENCE",
        "WEB_PERFORMANCE",
        "SYNTHETIC_APDEX",
        "RENDER_CAPTURE",
    }:
        return ()

    from rasai.audit_fulfillment import list_work_items

    work = tuple(list_work_items(workspace, str(getattr(item, "audit_id", "") or "")))
    wanted: list[Any] = []
    if component == "SEMANTIC_AI":
        wanted.extend(
            candidate
            for candidate in work
            if str(candidate.component) in {"RENDER_CAPTURE", "CONTENT_EXTRACTION"}
            and str(candidate.scope_key) == scope_key
        )
        try:
            import sqlite3

            connection = sqlite3.connect(workspace.database)
            try:
                row = connection.execute(
                    "SELECT page_id FROM page_snapshots WHERE snapshot_id=?",
                    (scope_key,),
                ).fetchone()
            finally:
                connection.close()
            page_id = str(row[0]) if row and row[0] else ""
            if page_id:
                wanted.extend(
                    candidate
                    for candidate in work
                    if str(candidate.component) == "HTTP_ACQUISITION"
                    and str(candidate.scope_key) == page_id
                )
        except Exception:
            pass
    elif component == "TECHNICAL_AI":
        # The canonical technical-AI gate (used in initial execution and RPR) is
        # evidence-based on robots/sitemap/crawler rules. Discovery is the only live
        # prerequisite that can materialize that evidence; render/extraction are not.
        wanted.extend(
            candidate
            for candidate in work
            if str(candidate.component) == "DISCOVERY_ACQUISITION"
        )
    elif component == "IMPROVEMENT_INTELLIGENCE":
        # Use exactly the same fulfillment universe as the initial Deep Analysis gate.
        # CORE_AUDIT is excluded because it is the aggregate/finalizer; Improvement
        # itself is excluded to avoid self-dependency. Every other required applicable
        # work-item must have reached a terminal state before the provider phase.
        from rasai.ai_dependency_contract import deep_analysis_dependency_items

        wanted.extend(
            candidate
            for candidate in deep_analysis_dependency_items(
                workspace,
                str(getattr(item, "audit_id", "") or ""),
            )
            if str(candidate.work_item_id) != str(getattr(item, "work_item_id", ""))
        )
    elif component in {"WEB_PERFORMANCE", "SYNTHETIC_APDEX"}:
        # Both collectors derive their execution universe from page_snapshots. Do not
        # spend an external/local measurement attempt while the core rendered context
        # is still incomplete.
        wanted.extend(
            candidate
            for candidate in work
            if str(candidate.component) in {
                "DISCOVERY_ACQUISITION",
                "HTTP_ACQUISITION",
                "RENDER_CAPTURE",
            }
        )
    elif component == "RENDER_CAPTURE":
        page_id = ""
        if scope_key.startswith("PLANNED:"):
            parts = scope_key.split(":", 2)
            page_id = parts[1] if len(parts) >= 2 else ""
        else:
            try:
                import sqlite3

                connection = sqlite3.connect(workspace.database)
                try:
                    row = connection.execute(
                        "SELECT page_id FROM page_snapshots WHERE snapshot_id=?",
                        (scope_key,),
                    ).fetchone()
                finally:
                    connection.close()
                page_id = str(row[0]) if row and row[0] else ""
            except Exception:
                page_id = ""
        if page_id:
            wanted.extend(
                candidate
                for candidate in work
                if str(candidate.component) == "HTTP_ACQUISITION"
                and str(candidate.scope_key) == page_id
            )

    if component == "IMPROVEMENT_INTELLIGENCE":
        from rasai.ai_governance import collection_state_is_terminal

        blockers = {
            f"{str(candidate.component)}/{str(candidate.scope_key)}"
            for candidate in wanted
            if not collection_state_is_terminal(getattr(candidate, "status", None))
        }
    else:
        blockers = {
            f"{str(candidate.component)}/{str(candidate.scope_key)}"
            for candidate in wanted
            if str(getattr(candidate, "status", "")).upper() not in _RESOLVED
        }
    return tuple(sorted(blockers))


@contextmanager
def reprocess_policy(
    *,
    selected_items: Sequence[Any] | None = None,
    use_ai: bool | None = None,
    ai_provider: str | None = None,
    ai_model: str | None = None,
    ai_reasoning: str | None = None,
    execution_context: Mapping[str, Any] | None = None,
    workspace: Any | None = None,
    audit_id: str | None = None,
) -> Iterator[ReprocessPolicy]:
    normalized = normalize_selected_items(selected_items)
    if normalized is not None and workspace is not None and audit_id:
        # The execution scope must be expanded from the reconciled durable state.
        # Otherwise a backfill repair performed later in the RPR can create a new
        # required pending item after selected_items was already frozen.
        from rasai.audit_reprocess import reconcile_reprocess_state

        reconcile_reprocess_state(workspace, str(audit_id))
        normalized = expand_selected_items(
            workspace,
            str(audit_id),
            tuple(normalized),
            use_ai=use_ai,
        )
    policy = ReprocessPolicy(
        selected_items=normalized,
        use_ai=use_ai,
        ai_provider=(str(ai_provider).strip().casefold() if ai_provider else None),
        ai_model=(str(ai_model).strip() if ai_model else None),
        ai_reasoning=(str(ai_reasoning).strip().upper() if ai_reasoning else None),
        execution_context=(dict(execution_context) if execution_context else None),
    )
    token = _POLICY.set(policy)
    try:
        yield policy
    finally:
        _POLICY.reset(token)


__all__ = [
    "AI_COMPONENTS",
    "ReprocessPolicy",
    "ai_execution_allowed",
    "blocking_dependencies",
    "current_policy",
    "expand_selected_items",
    "is_ai_component",
    "item_executable",
    "item_key",
    "item_selected",
    "normalize_selected_items",
    "provider_override",
    "reprocess_policy",
    "selected_counts",
]
