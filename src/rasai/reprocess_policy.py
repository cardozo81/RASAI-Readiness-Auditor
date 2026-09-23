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


@dataclass(frozen=True, slots=True)
class ReprocessPolicy:
    selected_items: frozenset[str] | None = None
    use_ai: bool | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_reasoning: str | None = None

    def as_configuration(self) -> dict[str, Any]:
        return {
            "selected_items": (
                sorted(self.selected_items) if self.selected_items is not None else None
            ),
            "use_ai": self.use_ai,
            "ai_provider": self.ai_provider,
            "ai_model": self.ai_model,
            "ai_reasoning": self.ai_reasoning,
        }


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
    """Return only known hard prerequisites for the specific AI work item.

    This is intentionally narrow.  It does not make every integration a dependency of
    every AI task.  Registered governed AI tasks retain their own dependency graph.
    """
    component = str(getattr(item, "component", "") or "").strip().upper()
    scope_key = str(getattr(item, "scope_key", "AUDIT") or "AUDIT")
    if component not in {"SEMANTIC_AI", "TECHNICAL_AI", "IMPROVEMENT_INTELLIGENCE"}:
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
        wanted.extend(
            candidate
            for candidate in work
            if str(candidate.component) in {"RENDER_CAPTURE", "CONTENT_EXTRACTION"}
        )
    elif component == "IMPROVEMENT_INTELLIGENCE":
        # CAT-08 is currently single-URL and consumes the persisted page/render/content
        # context. External services such as GSC/CrUX/SERP are not hard dependencies:
        # their absence is represented as missing supporting context, not a global gate.
        wanted.extend(
            candidate
            for candidate in work
            if str(candidate.component) in {
                "HTTP_ACQUISITION",
                "RENDER_CAPTURE",
                "CONTENT_EXTRACTION",
            }
        )

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
) -> Iterator[ReprocessPolicy]:
    policy = ReprocessPolicy(
        selected_items=normalize_selected_items(selected_items),
        use_ai=use_ai,
        ai_provider=(str(ai_provider).strip().casefold() if ai_provider else None),
        ai_model=(str(ai_model).strip() if ai_model else None),
        ai_reasoning=(str(ai_reasoning).strip().upper() if ai_reasoning else None),
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
    "is_ai_component",
    "item_executable",
    "item_key",
    "item_selected",
    "normalize_selected_items",
    "provider_override",
    "reprocess_policy",
    "selected_counts",
]
