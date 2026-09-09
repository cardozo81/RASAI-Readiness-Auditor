"""Evidence-bound baseline for the SARI CONTENT_VALUE dimension.

The rules in this module are deliberately conservative.  They do not claim to
measure originality or usefulness as universal facts.  They only materialize a
RASAi heuristic when preserved page evidence can support it; otherwise the state
is UNKNOWN and reduces measurement coverage instead of penalizing the website.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Iterable

from rasai.domain import DeviceContext, EvidenceType, RuleExecution, RuleResult, new_id, utc_now
from rasai.evidence import EvidenceManager
from rasai.persistence import AuditPersistence, AuditWorkspace


CONTENT_VALUE_RULE_IDS = ("BR-GEO-057", "BR-GEO-058", "BR-GEO-059")
_RULE_VERSION = "1"

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
_WORD_RE = re.compile(r"[\wÀ-ÿ'-]+", flags=re.UNICODE)
_FIRST_PARTY_RE = re.compile(
    r"(?ix)\b(?:"
    r"nossa\s+(?:pesquisa|an[aá]lise|metodologia|experi[eê]ncia|equipe|base|amostra|medi[cç][aã]o)"
    r"|nosso\s+(?:estudo|teste|levantamento|experimento|m[eé]todo|dataset)"
    r"|dados\s+pr[oó]prios|estudo\s+pr[oó]prio|metodologia\s+pr[oó]pria"
    r"|testamos|medimos|analisamos|observamos|pesquisamos"
    r"|our\s+(?:research|analysis|methodology|experience|team|data|dataset|study|test|measurement)"
    r"|we\s+(?:tested|measured|analysed|analyzed|observed|researched|built|collected)"
    r")\b"
)


@dataclass(frozen=True, slots=True)
class ContentValueMaterialization:
    rule_execution_ids: tuple[str, ...]


def materialize_content_value_executions(
    *,
    audit_id: str,
    source_executions: Iterable[RuleExecution],
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
) -> ContentValueMaterialization:
    """Materialize BR-GEO-057..059 once per semantic snapshot.

    M7 already provides one BR-GEO-038 execution per semantic snapshot.  That is
    used only as a stable enumeration anchor; its result is not copied into the
    new score.  The new rules evaluate their own preserved main-content evidence.
    """

    execution_list = tuple(source_executions)
    existing = {
        (item.rule_id, item.snapshot_id)
        for item in execution_list
        if item.rule_id in CONTENT_VALUE_RULE_IDS and item.snapshot_id
    }
    anchors = {
        item.snapshot_id: item
        for item in execution_list
        if item.rule_id == "BR-GEO-038" and item.snapshot_id
    }
    if not anchors:
        return ContentValueMaterialization(())

    manager = EvidenceManager(persistence)
    created: list[str] = []
    for snapshot_id, anchor in anchors.items():
        snapshot = persistence.snapshots.get(snapshot_id)
        if snapshot is None or snapshot.page_id != anchor.page_id:
            continue
        content = _read_text(workspace, snapshot.main_content_ref)
        signals = _signals(content)
        evidence = manager.record(
            audit_id=audit_id,
            page_id=anchor.page_id,
            snapshot_id=snapshot_id,
            device=anchor.device,
            evidence_type=EvidenceType.TEXT_EXCERPT,
            source="content-value-baseline",
            observed_value={
                **signals,
                "main_content_excerpt": content[:2000],
                "method": "CONTENT-VALUE-BASELINE-001",
                "interpretation": "RASAI_HEURISTIC",
            },
            artifact_reference=snapshot.main_content_ref,
        )

        evaluations = _evaluate(signals)
        for rule_id, (result, reason, expected) in evaluations.items():
            if (rule_id, snapshot_id) in existing:
                continue
            execution = RuleExecution(
                rule_execution_id=new_id("REX"),
                audit_id=audit_id,
                rule_id=rule_id,
                rule_version=_RULE_VERSION,
                page_id=anchor.page_id,
                snapshot_id=snapshot_id,
                device=anchor.device,
                result=result,
                observed_value={**signals, "reason": reason},
                expected_condition=expected,
                evidence_ids=(evidence.evidence_id,),
                executed_at=utc_now(),
                error=None,
            )
            persistence.rule_executions.add(execution)
            created.append(execution.rule_execution_id)

    return ContentValueMaterialization(tuple(created))


def _read_text(workspace: AuditWorkspace, reference: str | None) -> str:
    if not reference:
        return ""
    path: Path = workspace.root / reference
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _signals(content: str) -> dict[str, object]:
    sentences = tuple(
        item.strip()
        for item in _SENTENCE_RE.split(content)
        if len(item.strip()) >= 20
    )
    paragraphs = tuple(
        item.strip()
        for item in re.split(r"\n\s*\n", content)
        if len(item.strip()) >= 40
    )
    words = [match.group(0).casefold() for match in _WORD_RE.finditer(content)]
    lexical_diversity = len(set(words)) / len(words) if words else 0.0
    first_party = tuple(dict.fromkeys(match.group(0).strip() for match in _FIRST_PARTY_RE.finditer(content)))
    return {
        "character_count": len(content),
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "word_count": len(words),
        "lexical_diversity": round(lexical_diversity, 4),
        "explicit_first_party_signals": list(first_party[:12]),
    }


def _evaluate(signals: dict[str, object]) -> dict[str, tuple[RuleResult, str, str]]:
    chars = int(signals["character_count"])
    sentences = int(signals["sentence_count"])
    paragraphs = int(signals["paragraph_count"])
    words = int(signals["word_count"])
    diversity = float(signals["lexical_diversity"])
    first_party = tuple(signals["explicit_first_party_signals"])

    if chars <= 0:
        usefulness = (
            RuleResult.UNKNOWN,
            "CONTENT_VALUE_INPUT_UNAVAILABLE",
            "preserved main content provides enough evidence to assess useful and specific value",
        )
        depth = (
            RuleResult.UNKNOWN,
            "CONTENT_VALUE_INPUT_UNAVAILABLE",
            "content depth and context are proportionate to the page purpose and available evidence",
        )
    elif chars >= 800 and sentences >= 5 and words >= 120 and diversity >= 0.22:
        usefulness = (
            RuleResult.PASS,
            "BASELINE_USEFULNESS_SIGNALS_SUFFICIENT",
            "preserved main content provides useful, specific and non-trivial information for its apparent purpose",
        )
    elif chars >= 300 and sentences >= 2:
        usefulness = (
            RuleResult.WARNING,
            "BASELINE_USEFULNESS_SIGNALS_LIMITED",
            "preserved main content provides useful, specific and non-trivial information for its apparent purpose",
        )
    else:
        usefulness = (
            RuleResult.WARNING,
            "BASELINE_CONTENT_SUBSTANTIALLY_THIN",
            "preserved main content provides useful, specific and non-trivial information for its apparent purpose",
        )

    if first_party:
        differentiation = (
            RuleResult.PASS,
            "EXPLICIT_FIRST_PARTY_DIFFERENTIATION_SIGNAL",
            "first-party experience, analysis, data or differentiation is explicit when the page claims it",
        )
    else:
        differentiation = (
            RuleResult.UNKNOWN,
            "DIFFERENTIATION_NOT_PROVABLE_FROM_LOCAL_EVIDENCE",
            "first-party experience, analysis, data or differentiation is explicit when the page claims it",
        )

    if chars <= 0:
        pass
    elif chars >= 1400 and sentences >= 8 and paragraphs >= 3:
        depth = (
            RuleResult.PASS,
            "BASELINE_DEPTH_SIGNALS_SUFFICIENT",
            "content depth and context are proportionate to the page purpose and available evidence",
        )
    elif chars >= 600 and sentences >= 4:
        depth = (
            RuleResult.WARNING,
            "BASELINE_DEPTH_SIGNALS_MODERATE",
            "content depth and context are proportionate to the page purpose and available evidence",
        )
    else:
        depth = (
            RuleResult.UNKNOWN,
            "DEPTH_NOT_CONCLUSIVELY_MEASURABLE_FROM_LOCAL_EVIDENCE",
            "content depth and context are proportionate to the page purpose and available evidence",
        )

    return {
        "BR-GEO-057": usefulness,
        "BR-GEO-058": differentiation,
        "BR-GEO-059": depth,
    }
