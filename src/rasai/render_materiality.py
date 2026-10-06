"""Bounded, deterministic materiality gate for rendered DOM evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from html.parser import HTMLParser
import re
from typing import Any


CAPTURE_QUALITY_CONTRACT_VERSION = "RENDER-CAPTURE-QUALITY-001"
_RECOVERY_STEP_MS = 250
_RECOVERY_OBSERVATIONS = 4

_TRANSIENT_TOKEN_RE = re.compile(r"(?:^|[-_\s])(skeleton|shimmer|placeholder|loading|loader)(?:$|[-_\s])", re.IGNORECASE)
_LAZY_TOKEN_RE = re.compile(r"(?:^|[-_\s])(lazy|lazyload|defer)(?:$|[-_\s])", re.IGNORECASE)
_MAIN_TOKEN_RE = re.compile(r"(?:^|[-_\s])main(?:$|[-_\s])", re.IGNORECASE)
_SHELL_TOKEN_RE = re.compile(r"^(?:app|root|__next|__nuxt)$", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


class CaptureQualityState(StrEnum):
    READY = "READY"
    RECOVERED = "RECOVERED"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class MaterialityObservation:
    text_length: int
    main_text_length: int
    dom_nodes: int
    main_nodes: int
    transient_markers: int
    lazy_markers: int
    busy_markers: int
    shell_markers: int

    @property
    def main_present(self) -> bool:
        return self.main_nodes > 0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["main_present"] = self.main_present
        return value


class _MaterialityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.dom_nodes = 0
        self.main_nodes = 0
        self.transient_markers = 0
        self.lazy_markers = 0
        self.busy_markers = 0
        self.shell_markers = 0
        self._main_stack: list[bool] = []
        self._ignored_depth = 0
        self._text: list[str] = []
        self._main_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.dom_nodes += 1
        attr_map = {str(key).casefold(): str(value or "") for key, value in attrs}
        tag_name = tag.casefold()
        if tag_name in {"script", "style", "template", "noscript"}:
            self._ignored_depth += 1

        identity = " ".join(
            value for key, value in attr_map.items()
            if key in {"id", "class", "role", "data-testid", "data-component", "data-state", "aria-label"}
        )
        is_main = (
            tag_name == "main"
            or attr_map.get("role", "").casefold() == "main"
            or bool(_MAIN_TOKEN_RE.search(attr_map.get("id", "")))
            or bool(_MAIN_TOKEN_RE.search(attr_map.get("class", "")))
        )
        if is_main:
            self.main_nodes += 1
        parent_main = self._main_stack[-1] if self._main_stack else False
        self._main_stack.append(parent_main or is_main)

        marker_values = " ".join(
            value for key, value in attr_map.items()
            if key in {"id", "class", "data-testid", "data-component", "data-state", "aria-label"}
        )
        if _TRANSIENT_TOKEN_RE.search(marker_values):
            self.transient_markers += 1
        if (
            _LAZY_TOKEN_RE.search(marker_values)
            or attr_map.get("loading", "").casefold() == "lazy"
            or any(key in attr_map for key in ("data-src", "data-lazy", "data-lazy-src"))
        ):
            self.lazy_markers += 1
        if attr_map.get("aria-busy", "").casefold() == "true":
            self.busy_markers += 1
        if _SHELL_TOKEN_RE.fullmatch(attr_map.get("id", "").strip()) or _SHELL_TOKEN_RE.fullmatch(attr_map.get("class", "").strip()):
            self.shell_markers += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.casefold()
        if tag_name in {"script", "style", "template", "noscript"} and self._ignored_depth > 0:
            self._ignored_depth -= 1
        if self._main_stack:
            self._main_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = _SPACE_RE.sub(" ", str(data or "")).strip()
        if not text:
            return
        self._text.append(text)
        if self._main_stack and self._main_stack[-1]:
            self._main_text.append(text)

    def observation(self) -> MaterialityObservation:
        text = " ".join(self._text)
        main_text = " ".join(self._main_text)
        return MaterialityObservation(
            text_length=len(text),
            main_text_length=len(main_text),
            dom_nodes=self.dom_nodes,
            main_nodes=self.main_nodes,
            transient_markers=self.transient_markers,
            lazy_markers=self.lazy_markers,
            busy_markers=self.busy_markers,
            shell_markers=self.shell_markers,
        )


def observe_materiality(rendered_html: str | None) -> MaterialityObservation:
    parser = _MaterialityParser()
    if rendered_html:
        parser.feed(rendered_html)
        parser.close()
    return parser.observation()


def _weak_primary_content(observation: MaterialityObservation) -> bool:
    if observation.main_present:
        return observation.main_text_length < 160 and observation.text_length < 420
    return observation.text_length < 220


def _transient_suspicion(observation: MaterialityObservation, settle_outcome: str) -> bool:
    if not _weak_primary_content(observation):
        return False
    explicit_transient = observation.transient_markers > 0 or observation.busy_markers > 0
    bounded_lazy = str(settle_outcome).upper() == "BOUNDED_TIMEOUT" and observation.lazy_markers > 0
    return explicit_transient or bounded_lazy


def _growth(initial: MaterialityObservation, final: MaterialityObservation) -> dict[str, Any]:
    return {
        "text_delta": final.text_length - initial.text_length,
        "main_text_delta": final.main_text_length - initial.main_text_length,
        "dom_nodes_delta": final.dom_nodes - initial.dom_nodes,
        "transient_markers_delta": final.transient_markers - initial.transient_markers,
        "lazy_markers_delta": final.lazy_markers - initial.lazy_markers,
        "materialized": (
            final.main_text_length > initial.main_text_length
            or final.text_length > initial.text_length
            or final.dom_nodes > initial.dom_nodes
            or final.transient_markers < initial.transient_markers
        ),
    }


def unavailable_capture_quality(*, settle_outcome: str, reason: str) -> dict[str, Any]:
    empty = observe_materiality(None)
    return {
        "contract_version": CAPTURE_QUALITY_CONTRACT_VERSION,
        "state": CaptureQualityState.UNAVAILABLE.value,
        "reason": reason,
        "settle_outcome": str(settle_outcome),
        "initial": empty.to_dict(),
        "final": empty.to_dict(),
        "growth": _growth(empty, empty),
        "recovery": {
            "attempted": False,
            "observation_count": 0,
            "step_ms": _RECOVERY_STEP_MS,
            "bounded_wait_ms": 0,
            "max_wait_ms": _RECOVERY_STEP_MS * _RECOVERY_OBSERVATIONS,
            "outcome": "NOT_AVAILABLE",
        },
    }


def resolve_capture_quality(
    page: Any,
    rendered_html: str | None,
    *,
    settle_outcome: str,
    recovery_step_ms: int = _RECOVERY_STEP_MS,
    recovery_observations: int = _RECOVERY_OBSERVATIONS,
) -> tuple[str | None, dict[str, Any]]:
    """Return the best bounded DOM plus durable materiality provenance.

    Low text volume alone never triggers recovery. A bounded observation loop runs only
    when weak primary content is paired with explicit transient/lazy evidence.
    """
    if rendered_html is None:
        return None, unavailable_capture_quality(
            settle_outcome=settle_outcome,
            reason="RENDERED_DOM_UNAVAILABLE",
        )

    initial = observe_materiality(rendered_html)
    if not _transient_suspicion(initial, settle_outcome):
        return rendered_html, {
            "contract_version": CAPTURE_QUALITY_CONTRACT_VERSION,
            "state": CaptureQualityState.READY.value,
            "reason": "NO_TRANSIENT_RENDER_SIGNAL",
            "settle_outcome": str(settle_outcome),
            "initial": initial.to_dict(),
            "final": initial.to_dict(),
            "growth": _growth(initial, initial),
            "recovery": {
                "attempted": False,
                "observation_count": 0,
                "step_ms": recovery_step_ms,
                "bounded_wait_ms": 0,
                "max_wait_ms": recovery_step_ms * recovery_observations,
                "outcome": "NOT_REQUIRED",
            },
        }

    final_html = rendered_html
    final = initial
    observations = 0
    outcome = "BOUND_EXHAUSTED"
    wait_ms = 0
    for _ in range(max(int(recovery_observations), 0)):
        try:
            page.wait_for_timeout(max(int(recovery_step_ms), 0))
            wait_ms += max(int(recovery_step_ms), 0)
            candidate = page.content()
        except Exception as exc:
            outcome = f"OBSERVATION_ERROR:{type(exc).__name__}"
            break
        observations += 1
        if isinstance(candidate, str) and candidate:
            final_html = candidate
            final = observe_materiality(candidate)
        if not _transient_suspicion(final, settle_outcome):
            outcome = "MATERIALIZED"
            break

    growth = _growth(initial, final)
    recovered = not _transient_suspicion(final, settle_outcome)
    state = CaptureQualityState.RECOVERED if recovered else CaptureQualityState.INCOMPLETE
    reason = "TRANSIENT_RENDER_MATERIALIZED" if recovered else "TRANSIENT_RENDER_PERSISTED"
    return final_html, {
        "contract_version": CAPTURE_QUALITY_CONTRACT_VERSION,
        "state": state.value,
        "reason": reason,
        "settle_outcome": str(settle_outcome),
        "initial": initial.to_dict(),
        "final": final.to_dict(),
        "growth": growth,
        "recovery": {
            "attempted": True,
            "observation_count": observations,
            "step_ms": recovery_step_ms,
            "bounded_wait_ms": wait_ms,
            "max_wait_ms": recovery_step_ms * recovery_observations,
            "outcome": outcome,
        },
    }
