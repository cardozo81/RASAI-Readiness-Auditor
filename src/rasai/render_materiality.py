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
_CHROME_TOKEN_RE = re.compile(
    r"(?:^|[-_\s])(cookie|consent|gdpr|privacy-consent|cookie-banner)(?:$|[-_\s])",
    re.IGNORECASE,
)
_SPACE_RE = re.compile(r"\s+")
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})


class CaptureQualityState(StrEnum):
    READY = "READY"
    RECOVERED = "RECOVERED"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"


def persisted_capture_quality_state(metadata: Any) -> CaptureQualityState | None:
    """Return only an explicitly persisted #233 state.

    Missing/legacy metadata deliberately returns None so historical AUDs are not
    reinterpreted retroactively.
    """
    if not isinstance(metadata, dict):
        return None
    quality = metadata.get("capture_quality")
    if not isinstance(quality, dict):
        return None
    raw = str(quality.get("state") or "").strip().upper()
    try:
        return CaptureQualityState(raw)
    except ValueError:
        return None


def capture_quality_materialized(metadata: Any) -> bool:
    """Whether rendered evidence may be consumed as materialized semantic input."""
    state = persisted_capture_quality_state(metadata)
    return state is None or state in {
        CaptureQualityState.READY,
        CaptureQualityState.RECOVERED,
    }


def capture_quality_block_reason(metadata: Any) -> str | None:
    state = persisted_capture_quality_state(metadata)
    if state in {CaptureQualityState.INCOMPLETE, CaptureQualityState.UNAVAILABLE}:
        return f"RENDER_CAPTURE_QUALITY_{state.value}"
    return None


@dataclass(frozen=True, slots=True)
class MaterialityObservation:
    text_length: int
    main_text_length: int
    primary_text_length: int
    dom_nodes: int
    main_nodes: int
    heading_nodes: int
    content_nodes: int
    chrome_nodes: int
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
        self.heading_nodes = 0
        self.content_nodes = 0
        self.chrome_nodes = 0
        self.transient_markers = 0
        self.lazy_markers = 0
        self.busy_markers = 0
        self.shell_markers = 0
        self._main_stack: list[bool] = []
        self._chrome_stack: list[bool] = []
        self._ignored_depth = 0
        self._text: list[str] = []
        self._main_text: list[str] = []
        self._primary_text: list[str] = []

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

        is_chrome = (
            tag_name in {"header", "nav", "footer", "aside"}
            or bool(_CHROME_TOKEN_RE.search(identity))
        )
        parent_chrome = self._chrome_stack[-1] if self._chrome_stack else False
        chrome_context = parent_chrome or is_chrome
        if tag_name not in _VOID_TAGS:
            self._main_stack.append(parent_main or is_main)
            self._chrome_stack.append(chrome_context)
        if is_chrome:
            self.chrome_nodes += 1

        if not chrome_context:
            if tag_name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                self.heading_nodes += 1
                self.content_nodes += 1
            elif tag_name in {"article", "section", "p"}:
                self.content_nodes += 1

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
        if tag.casefold() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.casefold()
        if tag_name in {"script", "style", "template", "noscript"} and self._ignored_depth > 0:
            self._ignored_depth -= 1
        if self._main_stack:
            self._main_stack.pop()
        if self._chrome_stack:
            self._chrome_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = _SPACE_RE.sub(" ", str(data or "")).strip()
        if not text:
            return
        self._text.append(text)
        if self._main_stack and self._main_stack[-1]:
            self._main_text.append(text)
        if not self._chrome_stack or not self._chrome_stack[-1]:
            self._primary_text.append(text)

    def observation(self) -> MaterialityObservation:
        text = " ".join(self._text)
        main_text = " ".join(self._main_text)
        primary_text = " ".join(self._primary_text)
        return MaterialityObservation(
            text_length=len(text),
            main_text_length=len(main_text),
            primary_text_length=len(primary_text),
            dom_nodes=self.dom_nodes,
            main_nodes=self.main_nodes,
            heading_nodes=self.heading_nodes,
            content_nodes=self.content_nodes,
            chrome_nodes=self.chrome_nodes,
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


def _strong_primary_content(observation: MaterialityObservation) -> bool:
    """Require material text plus structural evidence without requiring <main>."""
    if observation.main_text_length >= 160:
        return True
    # Preserve short but semantically explicit pages: a primary landmark with a
    # heading is stronger evidence than raw text volume alone.
    if (
        observation.main_present
        and observation.main_text_length > 0
        and observation.heading_nodes > 0
    ):
        return True
    semantic_content = observation.heading_nodes > 0 and observation.content_nodes >= 2
    if observation.primary_text_length >= 160 and semantic_content:
        return True
    # Non-semantic SPAs remain observable when there is a large body of text outside
    # known chrome containers. The higher threshold prevents nav/footer copy alone
    # from becoming material just because the document omits <main>.
    if observation.primary_text_length >= 600 and observation.dom_nodes >= 4:
        return True
    return False


def _weak_primary_content(observation: MaterialityObservation) -> bool:
    return not _strong_primary_content(observation)


def _materiality_reason(observation: MaterialityObservation) -> str:
    outside_main_text = max(
        observation.primary_text_length - observation.main_text_length,
        0,
    )
    if (
        observation.main_present
        and observation.main_text_length < 160
        and _strong_primary_content(observation)
        and outside_main_text >= 160
    ):
        return "EMPTY_MAIN_WITH_EXTERNAL_PRIMARY_CONTENT"
    if _strong_primary_content(observation):
        return "PRIMARY_CONTENT_MATERIAL"
    if (
        observation.text_length >= 220
        and observation.primary_text_length < 80
        and observation.chrome_nodes > 0
    ):
        return "CHROME_ONLY"
    if observation.transient_markers or observation.busy_markers or observation.shell_markers:
        return "TRANSIENT_SHELL"
    return "PRIMARY_CONTENT_WEAK"


def _transient_suspicion(observation: MaterialityObservation, settle_outcome: str) -> bool:
    if not _weak_primary_content(observation):
        return False
    # App/root shell identifiers are structural containers and usually remain after
    # hydration. By themselves they indicate a transient shell only while primary
    # content is still empty; otherwise they would keep a valid hydrated DOM blocked.
    shell_suspicion = observation.shell_markers > 0 and observation.main_text_length == 0
    explicit_transient = (
        observation.transient_markers > 0
        or observation.busy_markers > 0
        or shell_suspicion
    )
    bounded_lazy = str(settle_outcome).upper() == "BOUNDED_TIMEOUT" and observation.lazy_markers > 0
    return explicit_transient or bounded_lazy


def _growth(initial: MaterialityObservation, final: MaterialityObservation) -> dict[str, Any]:
    return {
        "text_delta": final.text_length - initial.text_length,
        "main_text_delta": final.main_text_length - initial.main_text_length,
        "primary_text_delta": final.primary_text_length - initial.primary_text_length,
        "dom_nodes_delta": final.dom_nodes - initial.dom_nodes,
        "heading_nodes_delta": final.heading_nodes - initial.heading_nodes,
        "content_nodes_delta": final.content_nodes - initial.content_nodes,
        "transient_markers_delta": final.transient_markers - initial.transient_markers,
        "lazy_markers_delta": final.lazy_markers - initial.lazy_markers,
        "materialized": (
            final.main_text_length > initial.main_text_length
            or final.primary_text_length > initial.primary_text_length
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
    if not _weak_primary_content(initial):
        return rendered_html, {
            "contract_version": CAPTURE_QUALITY_CONTRACT_VERSION,
            "state": CaptureQualityState.READY.value,
            "reason": "NO_TRANSIENT_RENDER_SIGNAL",
            "materiality_reason": _materiality_reason(initial),
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

    if not _transient_suspicion(initial, settle_outcome):
        return rendered_html, {
            "contract_version": CAPTURE_QUALITY_CONTRACT_VERSION,
            "state": CaptureQualityState.INCOMPLETE.value,
            "reason": "PRIMARY_CONTENT_INSUFFICIENT",
            "materiality_reason": _materiality_reason(initial),
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
                "outcome": "NOT_APPLICABLE",
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
        if not _weak_primary_content(final):
            outcome = "MATERIALIZED"
            break

    growth = _growth(initial, final)
    recovered = not _weak_primary_content(final)
    state = CaptureQualityState.RECOVERED if recovered else CaptureQualityState.INCOMPLETE
    reason = "TRANSIENT_RENDER_MATERIALIZED" if recovered else "TRANSIENT_RENDER_PERSISTED"
    materiality_reason = "SLOW_HYDRATION" if recovered else _materiality_reason(final)
    return final_html, {
        "contract_version": CAPTURE_QUALITY_CONTRACT_VERSION,
        "state": state.value,
        "reason": reason,
        "materiality_reason": materiality_reason,
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
