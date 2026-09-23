"""Desktop × Mobile comparison primitives for M8."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from rasai.domain import PageSnapshot, RuleResult
from rasai.extraction import ContentExtractor
from rasai.semantic_persistence import EntityObservation, SemanticAssessment


class DeviceComparisonOutcome(StrEnum):
    SAME = "SAME"
    DIFFERENT = "DIFFERENT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class DeviceComparison:
    outcome: DeviceComparisonOutcome
    changed_fields: tuple[str, ...]
    material_fields: tuple[str, ...]
    desktop: dict[str, Any]
    mobile: dict[str, Any]
    limitations: tuple[str, ...] = ()

    @property
    def materially_problematic(self) -> bool:
        return bool(self.material_fields)


class DeviceComparator:
    """Compare persisted Desktop/Mobile observations without assuming difference is a defect."""

    def __init__(self) -> None:
        self._extractor = ContentExtractor()

    def compare(
        self,
        *,
        desktop: PageSnapshot | None,
        mobile: PageSnapshot | None,
        workspace_root: Path,
        desktop_entities: tuple[EntityObservation, ...] = (),
        mobile_entities: tuple[EntityObservation, ...] = (),
        desktop_assessments: tuple[SemanticAssessment, ...] = (),
        mobile_assessments: tuple[SemanticAssessment, ...] = (),
    ) -> DeviceComparison:
        if desktop is None and mobile is None:
            return DeviceComparison(
                DeviceComparisonOutcome.NOT_APPLICABLE, (), (), {}, {},
                ("NO_DEVICE_SNAPSHOTS",),
            )
        if desktop is None or mobile is None:
            return DeviceComparison(
                DeviceComparisonOutcome.UNKNOWN, (), (),
                self._snapshot_state(desktop, workspace_root, desktop_entities, desktop_assessments),
                self._snapshot_state(mobile, workspace_root, mobile_entities, mobile_assessments),
                ("ONE_DEVICE_SNAPSHOT_MISSING",),
            )

        d = self._snapshot_state(desktop, workspace_root, desktop_entities, desktop_assessments)
        m = self._snapshot_state(mobile, workspace_root, mobile_entities, mobile_assessments)
        changed = tuple(key for key in d if d[key] != m[key])
        material = tuple(key for key in changed if self._material(key, d[key], m[key]))
        return DeviceComparison(
            DeviceComparisonOutcome.DIFFERENT if changed else DeviceComparisonOutcome.SAME,
            changed,
            material,
            d,
            m,
        )

    def _snapshot_state(
        self,
        snapshot: PageSnapshot | None,
        workspace_root: Path,
        entities: tuple[EntityObservation, ...],
        assessments: tuple[SemanticAssessment, ...],
    ) -> dict[str, Any]:
        if snapshot is None:
            return {}
        html = _read(workspace_root, snapshot.rendered_artifact_ref)
        extracted = self._extractor.extract(html) if html is not None else None
        return {
            "http_status": snapshot.http_status,
            "final_url": snapshot.final_url,
            "canonical": snapshot.canonical,
            "robots": snapshot.meta_robots,
            "title": snapshot.title,
            "headings": tuple((item.level, item.text) for item in extracted.headings) if extracted else None,
            "main_content": extracted.main_content if extracted else None,
            "links": tuple(item.href for item in extracted.links) if extracted else None,
            "structured_data_types": _structured_types(extracted) if extracted else None,
            "architecture": snapshot.architecture_classification.value,
            "entities": tuple(sorted((item.name.casefold(), item.entity_type.value) for item in entities)),
            "semantic_assessments": tuple(
                sorted((item.assessment_type, item.result.value) for item in assessments)
            ),
        }

    @staticmethod
    def _material(field: str, desktop: Any, mobile: Any) -> bool:
        if field == "http_status":
            return _usable_status(desktop) != _usable_status(mobile)
        if field in {"canonical", "robots"}:
            return True
        if field == "main_content":
            return bool(desktop) != bool(mobile)
        if field == "semantic_assessments":
            return _material_semantic_difference(desktop, mobile)
        # Differences in title/headings/links/entities/structured data/final URL/
        # architecture are explicitly classified but are not automatically defects.
        return False


def _usable_status(value: Any) -> bool:
    return isinstance(value, int) and 200 <= value <= 399


def _structured_types(extracted: Any) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            item
            for block in extracted.structured_data
            for item in block.types
        )
    )


def _material_semantic_difference(desktop: Any, mobile: Any) -> bool:
    d = dict(desktop or ())
    m = dict(mobile or ())
    material_results = {RuleResult.FAIL.value, RuleResult.WARNING.value}
    for rule_id in set(d) | set(m):
        left = d.get(rule_id)
        right = m.get(rule_id)
        if left == right:
            continue
        if left in material_results or right in material_results:
            return True
    return False


def _read(root: Path, reference: str | None) -> str | None:
    if not reference:
        return None
    path = root / reference
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")
