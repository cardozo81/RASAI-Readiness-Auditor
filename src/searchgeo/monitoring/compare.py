"""Comparison and release-gate logic for RASAI monitoring."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .models import ChangeEvent, ComparisonResult, GatePolicy, GateResult, Signal
from .reader import read_audit_snapshot

_RESULT_RANK = {"FAIL": 0, "WARNING": 1, "PASS": 2}
_UNKNOWN_RESULTS = {"UNKNOWN", "ERROR", "NOT_APPLICABLE", "NOT_APPLICABLE_BY_DEPENDENCY"}
_SEVERITY_RANK = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
_DETERMINISTIC_RULES = frozenset(
    [f"BR-GEO-{number:03d}" for number in range(1, 28)]
    + ["BR-GEO-050", "BR-GEO-051", "BR-GEO-052", "BR-GEO-053", "BR-GEO-054"]
)


def compare_audits(baseline_workspace: str | Path, current_workspace: str | Path) -> ComparisonResult:
    baseline = read_audit_snapshot(baseline_workspace)
    current = read_audit_snapshot(current_workspace)
    notes: list[str] = []
    comparable = True
    if baseline.domains != current.domains:
        comparable = False
        notes.append(f"domain set differs: baseline={baseline.domains} current={current.domains}")
    if baseline.ruleset_version != current.ruleset_version:
        notes.append(
            f"ruleset version differs ({baseline.ruleset_version} → {current.ruleset_version}); rule-level changes require interpretation"
        )
    score_versions_compatible = bool(set(baseline.scoring_versions) & set(current.scoring_versions))
    if baseline.scoring_versions and current.scoring_versions and not score_versions_compatible:
        notes.append(
            "scoring versions have no overlap; SCORE events are marked NOT_COMPARABLE rather than converted across methodologies"
        )
    baseline_urls = set(baseline.urls)
    current_urls = set(current.urls)
    overlap = len(baseline_urls & current_urls)
    union = len(baseline_urls | current_urls)
    if union and overlap / union < 0.8:
        notes.append(f"URL universe overlap is {overlap}/{union}; page-level trend interpretation is limited")
    if baseline.devices != current.devices:
        notes.append(f"device sets differ: baseline={baseline.devices} current={current.devices}")

    events: list[ChangeEvent] = []
    keys = sorted(set(baseline.signals) | set(current.signals))
    for key in keys:
        before = baseline.signals.get(key)
        after = current.signals.get(key)
        if before is not None and before.domain == "SCORE" and not score_versions_compatible:
            events.append(_event(before, after, "NOT_COMPARABLE", before.value, after.value if after else None, False, reason="scoring version mismatch"))
            continue
        events.append(_compare_signal(before, after))

    counts: dict[str, int] = {}
    material_counts: dict[str, int] = {}
    for event in events:
        counts[event.status] = counts.get(event.status, 0) + 1
        if event.material:
            material_counts[event.status] = material_counts.get(event.status, 0) + 1
    return ComparisonResult(
        baseline=baseline,
        current=current,
        comparable=comparable,
        compatibility_notes=tuple(notes),
        events=tuple(events),
        counts=counts,
        material_counts=material_counts,
    )


def _compare_signal(before: Signal | None, after: Signal | None) -> ChangeEvent:
    if before is None and after is not None:
        return _event(None, after, "NEW", None, after.value, _new_signal_material(after), reason="signal did not exist in baseline")
    if before is not None and after is None:
        return _event(before, None, "DATA_UNAVAILABLE", before.value, None, False, reason="signal unavailable in current audit; absence is not treated as resolution")
    assert before is not None and after is not None
    if _same(before.value, after.value):
        return _event(before, after, "UNCHANGED", before.value, after.value, False)

    if after.direction == "RESULT":
        return _compare_result(before, after)
    if after.direction in {"HIGHER_BETTER", "LOWER_BETTER"}:
        return _compare_numeric(before, after)
    return _compare_state(before, after)


def _compare_result(before: Signal, after: Signal) -> ChangeEvent:
    old = str(before.value).upper()
    new = str(after.value).upper()
    if old in _UNKNOWN_RESULTS or new in _UNKNOWN_RESULTS:
        if old == new:
            return _event(before, after, "UNCHANGED", old, new, False)
        return _event(before, after, "DATA_UNAVAILABLE", old, new, False, reason="one side is inconclusive; do not convert UNKNOWN/ERROR/N/A into quality change")
    if old in _RESULT_RANK and new in _RESULT_RANK:
        if _RESULT_RANK[new] < _RESULT_RANK[old]:
            return _event(before, after, "REGRESSED", old, new, True, reason=f"rule result degraded {old} → {new}")
        if _RESULT_RANK[new] > _RESULT_RANK[old]:
            status = "RESOLVED" if new == "PASS" and old in {"FAIL", "WARNING"} else "IMPROVED"
            return _event(before, after, status, old, new, True, reason=f"rule result improved {old} → {new}")
    return _event(before, after, "CHANGED", old, new, True, reason="rule state changed without an ordered PASS/WARNING/FAIL interpretation")


def _compare_numeric(before: Signal, after: Signal) -> ChangeEvent:
    try:
        old = float(before.value)
        new = float(after.value)
    except (TypeError, ValueError):
        return _event(before, after, "CHANGED", before.value, after.value, True, reason="non-numeric value in numeric signal")
    if not math.isfinite(old) or not math.isfinite(new):
        return _event(before, after, "DATA_UNAVAILABLE", before.value, after.value, False, reason="non-finite metric")
    delta = new - old
    delta_percent = None if old == 0 else (delta / abs(old)) * 100.0
    threshold = _material_threshold(after, old)
    material = abs(delta) >= threshold
    if not material:
        return _event(before, after, "CHANGED", old, new, False, delta=delta, delta_percent=delta_percent, reason=f"change below materiality threshold {threshold:g} {after.unit or ''}".strip())
    improved = delta > 0 if after.direction == "HIGHER_BETTER" else delta < 0
    status = "IMPROVED" if improved else "REGRESSED"
    return _event(before, after, status, old, new, True, delta=delta, delta_percent=delta_percent)


def _compare_state(before: Signal, after: Signal) -> ChangeEvent:
    field = str(after.metadata.get("field") or "")
    old = before.value
    new = after.value
    if field == "http_status":
        old_ok = _http_ok(old)
        new_ok = _http_ok(new)
        if old_ok and not new_ok:
            return _event(before, after, "REGRESSED", old, new, True, reason="HTTP changed from usable 2xx/3xx to error/unknown")
        if not old_ok and new_ok:
            return _event(before, after, "IMPROVED", old, new, True, reason="HTTP recovered to usable 2xx/3xx")
    if field == "meta_robots":
        old_block = _contains_index_block(old)
        new_block = _contains_index_block(new)
        if not old_block and new_block:
            return _event(before, after, "REGRESSED", old, new, True, reason="index-blocking robots directive appeared")
        if old_block and not new_block:
            return _event(before, after, "IMPROVED", old, new, True, reason="index-blocking robots directive disappeared")
    # Canonical, title and final URL changes are material observations, but are
    # not called regressions without a directional rule finding.
    return _event(before, after, "CHANGED", old, new, True, reason="non-directional page state changed; inspect correlated rule events")


def _material_threshold(signal: Signal, old: float) -> float:
    if signal.domain == "SCORE":
        return 3.0
    if signal.domain in {"APDEX", "UX_APDEX"} and signal.unit == "score":
        return 0.05
    if signal.domain == "PERFORMANCE" and signal.unit == "score":
        return 0.05
    if signal.unit == "ms":
        return max(50.0, abs(old) * 0.10)
    if signal.unit == "ratio":
        return 0.03
    if signal.unit == "count":
        return 1.0
    return max(0.01, abs(old) * 0.05)


def _new_signal_material(signal: Signal) -> bool:
    if signal.domain == "RULE":
        return str(signal.value).upper() in {"FAIL", "WARNING"}
    if signal.domain == "FINDINGS":
        try:
            return int(signal.value) > 0
        except (TypeError, ValueError):
            return False
    return False


def _http_ok(value: Any) -> bool:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return False
    return 200 <= code < 400


def _contains_index_block(value: Any) -> bool:
    text = str(value or "").casefold()
    return "noindex" in text or "none" == text.strip()


def _same(left: Any, right: Any) -> bool:
    if isinstance(left, float) or isinstance(right, float):
        try:
            return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)
        except (TypeError, ValueError):
            return left == right
    return left == right


def _event(
    before: Signal | None,
    after: Signal | None,
    status: str,
    old: Any,
    new: Any,
    material: bool,
    *,
    delta: float | None = None,
    delta_percent: float | None = None,
    reason: str | None = None,
) -> ChangeEvent:
    signal = after or before
    assert signal is not None
    return ChangeEvent(
        key=signal.key,
        domain=signal.domain,
        label=signal.label,
        status=status,  # type: ignore[arg-type]
        before=old,
        after=new,
        severity=signal.severity,
        material=material,
        device=signal.device,
        url=signal.url,
        rule_id=signal.rule_id,
        unit=signal.unit,
        delta=delta,
        delta_percent=delta_percent,
        reason=reason,
    )


def evaluate_release_gate(result: ComparisonResult, policy: GatePolicy | None = None) -> GateResult:
    effective = policy or GatePolicy()
    regressions = [event for event in result.events if event.status == "REGRESSED" and event.material]
    if effective.deterministic_only:
        regressions = [event for event in regressions if _deterministic(event)]

    blocking: list[ChangeEvent] = []
    warnings: list[ChangeEvent] = []
    high_count = 0
    medium_count = 0
    for event in regressions:
        severity_rank = _SEVERITY_RANK.get(event.severity.upper(), 0)
        if event.domain == "SCORE" and event.label in effective.fail_dimensions and event.delta is not None:
            if event.delta <= -abs(effective.dimension_drop_points):
                blocking.append(event)
                continue
        if severity_rank >= _SEVERITY_RANK["CRITICAL"] and effective.fail_on_critical:
            blocking.append(event)
        elif severity_rank >= _SEVERITY_RANK["HIGH"]:
            high_count += 1
            warnings.append(event)
        elif severity_rank >= _SEVERITY_RANK["MEDIUM"]:
            medium_count += 1
            warnings.append(event)
        else:
            warnings.append(event)
    if high_count > effective.max_high_regressions:
        blocking.extend(event for event in warnings if _SEVERITY_RANK.get(event.severity.upper(), 0) >= _SEVERITY_RANK["HIGH"])
    if medium_count > effective.max_medium_regressions:
        blocking.extend(event for event in warnings if event.severity.upper() == "MEDIUM")
    # stable de-dup preserving order
    seen: set[str] = set()
    unique_blocking: list[ChangeEvent] = []
    for event in blocking:
        if event.key not in seen:
            seen.add(event.key)
            unique_blocking.append(event)
    passed = not unique_blocking
    reason = "PASS: no blocking deterministic regression" if passed else f"FAIL: {len(unique_blocking)} blocking regression(s)"
    return GateResult(passed, tuple(unique_blocking), tuple(warnings), effective, reason)


def _deterministic(event: ChangeEvent) -> bool:
    if event.domain == "RULE":
        return bool(event.rule_id and event.rule_id in _DETERMINISTIC_RULES)
    if event.domain == "PAGE":
        return True
    if event.domain in {"PERFORMANCE", "APDEX", "UX_APDEX"}:
        return True
    if event.domain == "FINDINGS":
        return True
    # SCORE dimensions can include semantic rules, so deterministic-only gate
    # does not block on aggregated score deltas.
    return False
