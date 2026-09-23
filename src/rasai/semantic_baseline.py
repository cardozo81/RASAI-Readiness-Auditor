"""Evidence-bound deterministic semantic baseline for M7.

The baseline is deliberately conservative: it emits PASS only when preserved page
signals are sufficient to support the rule, NOT_APPLICABLE only when applicability
can be resolved from the evidence, and otherwise leaves the rule unresolved so M7
can use an optional semantic provider or persist UNKNOWN.

It never calls an external service and never fabricates semantic facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
import unicodedata
from typing import Any, Iterable
from urllib.parse import urlparse

from rasai.domain import RuleResult
from rasai.semantic import SemanticEvidenceInput, SemanticInput


BASELINE_VERSION = "SEMANTIC-BASELINE-001"


@dataclass(frozen=True, slots=True)
class BaselineAssessment:
    rule_id: str
    result: RuleResult
    confidence: float
    evidence_ids: tuple[str, ...]
    observed_value: dict[str, Any]
    reason: str | None
    reasoning_summary: str


_STOPWORDS = frozenset(
    {
        "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
        "e", "em", "entre", "esse", "esta", "este", "isso", "mais", "na", "nas",
        "no", "nos", "o", "os", "ou", "para", "pela", "pelo", "por", "que", "se",
        "sem", "sobre", "sua", "suas", "seu", "seus", "um", "uma", "the", "and",
        "for", "from", "into", "of", "on", "or", "to", "with", "your", "our", "is",
        "are", "this", "that", "these", "those",
    }
)
_QUESTION_WORDS = (
    "como ", "qual ", "quais ", "quando ", "quanto ", "quantos ", "onde ",
    "por que ", "porque ", "o que ", "quem ", "what ", "which ", "when ",
    "where ", "why ", "how ", "who ",
)
_DATE_RE = re.compile(r"\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}[/.-]\d{1,2}[/.-](?:19|20)\d{2}\b")
_QUALIFIED_NUMBER_RE = re.compile(
    r"(?ix)(?:"
    r"(?:R\$|US\$|USD|BRL|EUR|€|£|\$)\s*\d[\d.,]*"
    r"|\d[\d.,]*\s*(?:%|kg|g|mg|km|m|cm|mm|h|hr|hrs|hora|horas|dia|dias|"
    r"semana|semanas|mes|meses|mês|mêses|ano|anos|mb|gb|tb|kbps|mbps|gbps|ms|s)\b"
    r"|(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}"
    r"|\d{1,2}[/.-]\d{1,2}[/.-](?:19|20)\d{2}"
    r")"
)
_ANY_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_BRAND_RE = re.compile(
    r"(?i:\b(?:marca|brand)\s+)([A-ZÀ-Ý][\wÀ-ÿ&.\'-]*(?:\s+[A-ZÀ-Ý][\wÀ-ÿ&.\'-]*){0,4})"
)
_RESPONSIBILITY_RE = re.compile(
    r"(?i:\b(?:"
    r"publicad[oa](?:\s+em\s+(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2})?\s+(?:por|pela|pelo)"
    r"|escrit[oa]\s+por|desenvolvid[oa]\s+por|published(?:\s+on\s+[^,.;]{1,40})?\s+by|written\s+by"
    r")\s+)([A-ZÀ-Ý][\wÀ-ÿ&.\'-]*(?:\s+[A-ZÀ-Ý][\wÀ-ÿ&.\'-]*){0,5})"
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|[\r\n]+")


def evaluate_semantic_baseline(semantic_input: SemanticInput) -> dict[str, BaselineAssessment]:
    """Return deterministic assessments that are safe to use without an AI provider."""

    title = (semantic_input.title or "").strip()
    content = (semantic_input.main_content or "").strip()
    headings = _headings(semantic_input)
    h1 = next((text for level, text in headings if level == 1 and text.strip()), "")
    primary_signal = h1 or title
    structured_nodes = tuple(_structured_nodes(semantic_input.structured_data))
    structured_types = _structured_types(structured_nodes)
    structured_names = _structured_values(
        structured_nodes,
        {"name", "headline", "alternatename"},
    )
    responsible_names = _responsible_names(structured_nodes, content)
    relations = _structured_relation_signals(structured_nodes)
    dates = _date_signals(structured_nodes, content)
    qualified_claims = tuple(_QUALIFIED_NUMBER_RE.finditer(content))
    question_pairs = _question_answer_pairs(structured_nodes, content)
    question_signals = bool(question_pairs) or any(_looks_like_question(text) for _, text in headings)
    secondary_headings = tuple(text for level, text in headings if level >= 2 and text.strip())
    assessments: dict[str, BaselineAssessment] = {}

    def add(item: BaselineAssessment | None) -> None:
        if item is not None:
            assessments[item.rule_id] = item

    # BR-GEO-028: positive lexical evidence can establish a baseline representation check.
    if title and content:
        title_tokens = _tokens(title)
        overlap_content = _token_overlap(title_tokens, _tokens(content))
        overlap_h1 = _token_overlap(title_tokens, _tokens(h1)) if h1 else 0.0
        if title_tokens and max(overlap_content, overlap_h1) >= 0.50:
            add(
                _assessment(
                    semantic_input,
                    "BR-GEO-028",
                    RuleResult.PASS,
                    {"title_present": True, "title_content_overlap": round(overlap_content, 3), "title_h1_overlap": round(overlap_h1, 3)},
                    "Title and preserved visible content share a strong lexical topic signal.",
                    evidence_types=("HTML_ELEMENT", "HEADING", "MAIN_CONTENT", "TEXT_EXCERPT"),
                )
            )

    # BR-GEO-029: only a demonstrably coherent heading sequence is promoted to PASS.
    if headings and _heading_hierarchy_is_coherent(headings):
        add(
            _assessment(
                semantic_input,
                "BR-GEO-029",
                RuleResult.PASS,
                {"headings": [{"level": level, "text": text} for level, text in headings[:20]]},
                "Preserved heading levels expose a coherent hierarchy without material level jumps.",
                evidence_types=("HEADING",),
            )
        )

    # BR-GEO-030: topic is identifiable when the primary title/H1 signal is materially present in content.
    if primary_signal and content:
        topic_overlap = _token_overlap(_tokens(primary_signal), _tokens(content))
        if topic_overlap >= 0.50:
            add(
                _assessment(
                    semantic_input,
                    "BR-GEO-030",
                    RuleResult.PASS,
                    {"primary_signal": primary_signal[:240], "content_overlap": round(topic_overlap, 3), "section_count": len(secondary_headings)},
                    "The primary title/H1 topic is materially represented in the extracted main content.",
                    evidence_types=("HEADING", "MAIN_CONTENT", "TEXT_EXCERPT"),
                )
            )

    # Entity clarity uses only explicit structured names or a title/H1 topic anchor.
    primary_entity = _select_primary_entity(structured_names, primary_signal, content)
    if primary_entity is not None:
        add(
            _assessment(
                semantic_input,
                "BR-GEO-031",
                RuleResult.PASS,
                {"primary_entity": primary_entity, "structured_types": sorted(structured_types)},
                "A primary entity/topic is explicitly recoverable from structured data or aligned title/H1 content.",
                evidence_types=("STRUCTURED_DATA", "HEADING", "MAIN_CONTENT", "TEXT_EXCERPT"),
            )
        )

    if primary_entity is not None and (relations or responsible_names or _entity_is_contextualized(primary_entity, content)):
        add(
            _assessment(
                semantic_input,
                "BR-GEO-032",
                RuleResult.PASS,
                {
                    "primary_entity": primary_entity,
                    "relationship_signals": list(relations[:12]),
                    "responsible_entities": list(responsible_names[:8]),
                },
                "The primary entity has explicit contextual or relationship signals in preserved evidence.",
                evidence_types=("STRUCTURED_DATA", "MAIN_CONTENT", "TEXT_EXCERPT"),
            )
        )

    if primary_entity is not None and _primary_signals_are_consistent(primary_entity, title, h1, structured_names, content):
        add(
            _assessment(
                semantic_input,
                "BR-GEO-033",
                RuleResult.PASS,
                {"primary_entity": primary_entity, "title": title[:240], "h1": h1[:240], "structured_names": list(structured_names[:8])},
                "Independent primary signals align on the same entity/topic; no material ambiguity is evidenced by the baseline inputs.",
                evidence_types=("STRUCTURED_DATA", "HEADING", "MAIN_CONTENT", "TEXT_EXCERPT"),
            )
        )

    # BR-GEO-036/037 only run here when structured data exists. Absence is handled by M7 as N/A.
    if structured_nodes:
        comparable_values = _structured_values(
            structured_nodes,
            {"name", "headline", "description", "text", "sku", "model"},
        )
        visible = f"{title}\n{content}"
        matched_values = [value for value in comparable_values if _value_visible(value, visible)]
        if comparable_values and matched_values:
            ratio = len(matched_values) / len(comparable_values)
            if ratio >= 0.50:
                add(
                    _assessment(
                        semantic_input,
                        "BR-GEO-036",
                        RuleResult.PASS,
                        {"comparable_values": len(comparable_values), "visible_matches": len(matched_values), "match_ratio": round(ratio, 3)},
                        "Material structured-data text values are also represented in visible title/main-content evidence.",
                        evidence_types=("STRUCTURED_DATA", "MAIN_CONTENT", "TEXT_EXCERPT"),
                    )
                )
        if primary_entity is not None and structured_names:
            entity_matches = [name for name in structured_names if _semantic_label_overlap(name, primary_entity) >= 0.50 or _value_visible(name, visible)]
            if entity_matches:
                add(
                    _assessment(
                        semantic_input,
                        "BR-GEO-037",
                        RuleResult.PASS,
                        {"primary_entity": primary_entity, "matching_structured_entities": entity_matches[:8]},
                        "Structured-data entity names align with the primary entity/topic observed in visible evidence.",
                        evidence_types=("STRUCTURED_DATA", "HEADING", "MAIN_CONTENT", "TEXT_EXCERPT"),
                    )
                )

    # Answerability: primary intent can be established structurally; explicit Q/A rules are N/A when no Q/A signal exists.
    if primary_signal and content and len(content) >= 80:
        intent_overlap = _token_overlap(_tokens(primary_signal), _tokens(content))
        if intent_overlap >= 0.50:
            add(
                _assessment(
                    semantic_input,
                    "BR-GEO-038",
                    RuleResult.PASS,
                    {"primary_intent_signal": primary_signal[:240], "content_overlap": round(intent_overlap, 3)},
                    "A primary user-facing topic/intent is explicit in title/H1 and materially represented in main content.",
                    evidence_types=("HEADING", "MAIN_CONTENT", "TEXT_EXCERPT"),
                )
            )

    if not question_signals:
        for rule_id in ("BR-GEO-039", "BR-GEO-040"):
            add(
                _assessment(
                    semantic_input,
                    rule_id,
                    RuleResult.NOT_APPLICABLE,
                    {"question_signals_detected": False},
                    "No explicit FAQ, question heading, or question/answer pair is present in the preserved page evidence.",
                    reason="NO_EXPLICIT_QA_APPLICABILITY_SIGNAL",
                    evidence_types=("STRUCTURED_DATA", "HEADING", "MAIN_CONTENT", "TEXT_EXCERPT"),
                )
            )
    elif question_pairs:
        answered = [pair for pair in question_pairs if len(pair[1].strip()) >= 20]
        if answered and len(answered) == len(question_pairs):
            add(
                _assessment(
                    semantic_input,
                    "BR-GEO-039",
                    RuleResult.PASS,
                    {"question_count": len(question_pairs), "answered_count": len(answered)},
                    "Explicit questions have recoverable answer text in the preserved evidence.",
                    evidence_types=("STRUCTURED_DATA", "MAIN_CONTENT", "HEADING"),
                )
            )
            if all(len(answer.strip()) >= 40 for _, answer in answered):
                add(
                    _assessment(
                        semantic_input,
                        "BR-GEO-040",
                        RuleResult.PASS,
                        {"answer_count": len(answered), "minimum_answer_characters": min(len(answer.strip()) for _, answer in answered)},
                        "Recovered answers contain enough surrounding text to be independently understandable at baseline level.",
                        evidence_types=("STRUCTURED_DATA", "MAIN_CONTENT", "HEADING"),
                    )
                )

    # Citation-readiness baseline only evaluates objectively identifiable quantitative/temporal claims.
    if not qualified_claims:
        for rule_id in ("BR-GEO-041", "BR-GEO-042", "BR-GEO-043"):
            add(
                _assessment(
                    semantic_input,
                    rule_id,
                    RuleResult.NOT_APPLICABLE,
                    {"qualified_numeric_or_temporal_claims": 0},
                    "No explicit numeric, monetary, percentage, unit-qualified or date claim was detected by the deterministic baseline.",
                    reason="NO_BASELINE_FACTUAL_CLAIM_SIGNAL",
                    evidence_types=("MAIN_CONTENT", "TEXT_EXCERPT"),
                )
            )
    else:
        claim_samples = [match.group(0)[:80] for match in qualified_claims[:12]]
        add(
            _assessment(
                semantic_input,
                "BR-GEO-041",
                RuleResult.PASS,
                {"claim_count": len(qualified_claims), "samples": claim_samples},
                "Material quantitative/temporal claims are explicit and mechanically identifiable in main content.",
                evidence_types=("MAIN_CONTENT", "TEXT_EXCERPT"),
            )
        )
        if _claims_have_context(content, qualified_claims):
            add(
                _assessment(
                    semantic_input,
                    "BR-GEO-042",
                    RuleResult.PASS,
                    {"claim_count": len(qualified_claims), "context_check": "sufficient_sentence_context"},
                    "Detected factual claims appear inside sufficiently descriptive sentence context.",
                    evidence_types=("MAIN_CONTENT", "TEXT_EXCERPT"),
                )
            )
        if not _has_unqualified_material_numbers(content, qualified_claims):
            add(
                _assessment(
                    semantic_input,
                    "BR-GEO-043",
                    RuleResult.PASS,
                    {"qualified_claim_count": len(qualified_claims), "unqualified_material_numbers": 0},
                    "Detected numeric/temporal claims include an explicit currency, unit, percentage or date qualifier.",
                    evidence_types=("MAIN_CONTENT", "TEXT_EXCERPT"),
                )
            )

    if _content_is_contextualized(content, headings):
        add(
            _assessment(
                semantic_input,
                "BR-GEO-044",
                RuleResult.PASS,
                {"character_count": len(content), "heading_count": len(headings), "sentence_count": len(_sentences(content))},
                "Main content is expressed as contextualized prose rather than isolated fragments in the preserved extraction.",
                evidence_types=("MAIN_CONTENT", "HEADING", "TEXT_EXCERPT"),
            )
        )

    # Evidence & trust: attribution applies only to detected baseline claims.
    if not qualified_claims:
        add(
            _assessment(
                semantic_input,
                "BR-GEO-045",
                RuleResult.NOT_APPLICABLE,
                {"baseline_claims_requiring_attribution": 0},
                "No baseline quantitative/temporal claim requiring an attribution check was detected.",
                reason="NO_BASELINE_ATTRIBUTION_APPLICABILITY_SIGNAL",
                evidence_types=("MAIN_CONTENT", "TEXT_EXCERPT"),
            )
        )
    else:
        external_links = _external_links(semantic_input)
        attribution_values = _structured_values(
            structured_nodes,
            {"citation", "sameas", "source", "isBasedOn", "isbasedon", "publisher", "author"},
        )
        if external_links or responsible_names or attribution_values:
            add(
                _assessment(
                    semantic_input,
                    "BR-GEO-045",
                    RuleResult.PASS,
                    {
                        "external_link_count": len(external_links),
                        "responsible_entities": list(responsible_names[:8]),
                        "structured_attribution_signals": len(attribution_values),
                    },
                    "Detected factual claims have an explicit attribution/support signal in links, structured data, or visible responsibility text.",
                    evidence_types=("LINK", "STRUCTURED_DATA", "MAIN_CONTENT", "TEXT_EXCERPT"),
                )
            )

    if responsible_names or _title_domain_alignment(title, semantic_input.page_url):
        add(
            _assessment(
                semantic_input,
                "BR-GEO-046",
                RuleResult.PASS,
                {"responsible_entities": list(responsible_names[:8]), "title_domain_alignment": _title_domain_alignment(title, semantic_input.page_url)},
                "A publisher, author, brand, provider or responsible entity is explicitly identifiable in preserved page signals.",
                evidence_types=("STRUCTURED_DATA", "MAIN_CONTENT", "HTML_ELEMENT", "TEXT_EXCERPT"),
            )
        )

    if not dates:
        add(
            _assessment(
                semantic_input,
                "BR-GEO-047",
                RuleResult.NOT_APPLICABLE,
                {"freshness_signals": 0},
                "No publication/modification/freshness signal is present in the deterministic evidence set.",
                reason="NO_FRESHNESS_SIGNAL",
                evidence_types=("STRUCTURED_DATA", "MAIN_CONTENT", "TEXT_EXCERPT"),
            )
        )
    elif _dates_are_consistent(dates):
        add(
            _assessment(
                semantic_input,
                "BR-GEO-047",
                RuleResult.PASS,
                {"freshness_signals": [value for _kind, value in dates[:12]]},
                "Observed publication/modification/freshness dates contain no deterministic chronological contradiction.",
                evidence_types=("STRUCTURED_DATA", "MAIN_CONTENT", "TEXT_EXCERPT"),
            )
        )

    # Intent coverage is limited to intents explicitly represented by the page itself; no external demand is invented.
    if primary_signal and content and _token_overlap(_tokens(primary_signal), _tokens(content)) >= 0.50:
        add(
            _assessment(
                semantic_input,
                "BR-GEO-048",
                RuleResult.PASS,
                {"primary_intent": primary_signal[:240], "secondary_intents": list(secondary_headings[:5])},
                "The page explicitly represents one primary intent/topic and preserves its observable section intents.",
                evidence_types=("HEADING", "MAIN_CONTENT", "TEXT_EXCERPT"),
            )
        )

    material_secondary = tuple(text for text in secondary_headings if len(_tokens(text)) >= 1)
    if len(material_secondary) <= 1:
        add(
            _assessment(
                semantic_input,
                "BR-GEO-049",
                RuleResult.NOT_APPLICABLE,
                {"material_secondary_intents": list(material_secondary)},
                "The baseline does not infer external intent gaps when the page exposes at most one secondary section intent.",
                reason="NO_MATERIAL_BASELINE_INTENT_GAP_SET",
                evidence_types=("HEADING", "MAIN_CONTENT", "TEXT_EXCERPT"),
            )
        )
    elif content:
        coverage = [
            _token_overlap(_tokens(heading), _tokens(content))
            for heading in material_secondary[:5]
        ]
        if coverage and min(coverage) >= 0.50:
            add(
                _assessment(
                    semantic_input,
                    "BR-GEO-049",
                    RuleResult.PASS,
                    {"secondary_intents": list(material_secondary[:5]), "minimum_content_overlap": round(min(coverage), 3)},
                    "Every material secondary intent explicitly signaled by headings is represented in extracted main content.",
                    evidence_types=("HEADING", "MAIN_CONTENT", "TEXT_EXCERPT"),
                )
            )

    return assessments


def _assessment(
    semantic_input: SemanticInput,
    rule_id: str,
    result: RuleResult,
    observed_value: dict[str, Any],
    reasoning_summary: str,
    *,
    reason: str | None = None,
    evidence_types: tuple[str, ...] = (),
    confidence: float = 0.9,
) -> BaselineAssessment | None:
    evidence_ids = _evidence_ids(semantic_input, evidence_types)
    if not evidence_ids:
        return None
    return BaselineAssessment(
        rule_id=rule_id,
        result=result,
        confidence=confidence,
        evidence_ids=evidence_ids,
        observed_value={"baseline_version": BASELINE_VERSION, **observed_value},
        reason=reason,
        reasoning_summary=reasoning_summary,
    )


def _evidence_ids(semantic_input: SemanticInput, evidence_types: tuple[str, ...]) -> tuple[str, ...]:
    wanted = {value.upper() for value in evidence_types}
    selected = [
        item.evidence_id
        for item in semantic_input.evidence
        if not wanted or item.evidence_type.upper() in wanted
    ]
    if not selected:
        selected = [
            item.evidence_id
            for item in semantic_input.evidence
            if item.evidence_type.upper() == "TEXT_EXCERPT"
        ]
    if not selected and semantic_input.evidence:
        selected = [semantic_input.evidence[0].evidence_id]
    return tuple(dict.fromkeys(selected))


def _headings(semantic_input: SemanticInput) -> tuple[tuple[int, str], ...]:
    rows: list[tuple[int, str]] = []
    for evidence in semantic_input.evidence:
        if evidence.evidence_type.upper() != "HEADING" or not isinstance(evidence.observed_value, list):
            continue
        for item in evidence.observed_value:
            if not isinstance(item, dict):
                continue
            try:
                level = int(item.get("level"))
            except (TypeError, ValueError):
                continue
            text = str(item.get("text") or "").strip()
            if 1 <= level <= 6 and text:
                rows.append((level, text))
    return tuple(rows)


def _heading_hierarchy_is_coherent(headings: tuple[tuple[int, str], ...]) -> bool:
    if not headings or not any(level in {1, 2} for level, _ in headings):
        return False
    previous = headings[0][0]
    if previous > 2:
        return False
    for level, _text in headings[1:]:
        if level - previous > 1:
            return False
        previous = level
    return True


def _structured_nodes(value: Any) -> Iterable[dict[str, Any]]:
    if not isinstance(value, dict):
        return ()
    blocks = value.get("blocks")
    if not isinstance(blocks, list):
        return ()
    nodes: list[dict[str, Any]] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            nodes.append(item)
            for nested in item.values():
                walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)

    for block in blocks:
        if isinstance(block, dict) and not block.get("parse_error"):
            walk(block.get("parsed"))
    return tuple(nodes)


def _structured_types(nodes: Iterable[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for node in nodes:
        raw = node.get("@type")
        if isinstance(raw, str) and raw.strip():
            values.add(raw.strip())
        elif isinstance(raw, list):
            values.update(str(item).strip() for item in raw if str(item).strip())
    return values


def _structured_values(nodes: Iterable[dict[str, Any]], keys: set[str]) -> tuple[str, ...]:
    normalized_keys = {key.casefold() for key in keys}
    values: list[str] = []
    for node in nodes:
        for key, value in node.items():
            if str(key).casefold() not in normalized_keys:
                continue
            values.extend(_scalar_text_values(value))
    return tuple(dict.fromkeys(value for value in values if value.strip()))


def _scalar_text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            return [name.strip()]
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_scalar_text_values(item))
        return result
    return []


def _structured_relation_signals(nodes: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    keys = {
        "about", "author", "brand", "creator", "ispartof", "mainentity", "manufacturer",
        "memberof", "offers", "provider", "publisher", "sponsor",
    }
    signals: list[str] = []
    for node in nodes:
        for key, value in node.items():
            if str(key).casefold() in keys and value is not None and value != "" and value != [] and value != {}:
                signals.append(str(key))
    return tuple(dict.fromkeys(signals))


def _responsible_names(nodes: tuple[dict[str, Any], ...], content: str) -> tuple[str, ...]:
    values = list(
        _structured_values(
            nodes,
            {"author", "publisher", "provider", "brand", "manufacturer", "creator", "sponsor"},
        )
    )
    for pattern in (_RESPONSIBILITY_RE, _BRAND_RE):
        for match in pattern.finditer(content):
            value = match.group(1).strip(" .,:;-\n\r\t")
            if len(value) >= 3:
                values.append(value)
    return tuple(dict.fromkeys(values))


def _select_primary_entity(structured_names: tuple[str, ...], primary_signal: str, content: str) -> str | None:
    visible = f"{primary_signal}\n{content}"
    for name in structured_names:
        if _value_visible(name, visible):
            return name
    if primary_signal and content and _token_overlap(_tokens(primary_signal), _tokens(content)) >= 0.50:
        return primary_signal
    return None


def _entity_is_contextualized(entity: str, content: str) -> bool:
    tokens = _tokens(entity)
    if not tokens or not content:
        return False
    normalized_content = _normalize(content)
    hits = sum(normalized_content.count(token) for token in set(tokens) if len(token) >= 3)
    return hits >= max(1, min(2, len(set(tokens)))) and len(content) >= 80


def _primary_signals_are_consistent(
    primary_entity: str,
    title: str,
    h1: str,
    structured_names: tuple[str, ...],
    content: str,
) -> bool:
    if not _value_visible(primary_entity, f"{title}\n{h1}\n{content}"):
        return False
    if title and h1 and _semantic_label_overlap(title, h1) < 0.35:
        return False
    if structured_names and not any(
        _semantic_label_overlap(primary_entity, name) >= 0.35 or _value_visible(name, f"{title}\n{content}")
        for name in structured_names
    ):
        return False
    return True


def _value_visible(value: str, visible: str) -> bool:
    normalized_value = _normalize(value).strip()
    normalized_visible = _normalize(visible)
    if not normalized_value or not normalized_visible:
        return False
    compact_value = normalized_value.replace(" ", "")
    compact_visible = normalized_visible.replace(" ", "")
    if len(compact_value) >= 4 and compact_value in compact_visible:
        return True
    tokens = _tokens(value)
    return bool(tokens) and _token_overlap(tokens, _tokens(visible)) >= 0.60


def _semantic_label_overlap(left: str, right: str) -> float:
    return max(_token_overlap(_tokens(left), _tokens(right)), _token_overlap(_tokens(right), _tokens(left)))


def _question_answer_pairs(nodes: tuple[dict[str, Any], ...], content: str) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for node in nodes:
        if "Question" not in _node_types(node):
            continue
        question = str(node.get("name") or node.get("text") or "").strip()
        answer_value = node.get("acceptedAnswer") or node.get("suggestedAnswer")
        answer = ""
        if isinstance(answer_value, dict):
            answer = str(answer_value.get("text") or answer_value.get("name") or "").strip()
        elif isinstance(answer_value, str):
            answer = answer_value.strip()
        if question:
            pairs.append((question, answer))
    if pairs:
        return tuple(pairs)
    for match in re.finditer(r"([^?\n]{5,160}\?)\s*([^?\n]{20,500})", content):
        pairs.append((match.group(1).strip(), match.group(2).strip()))
    return tuple(pairs[:20])


def _node_types(node: dict[str, Any]) -> set[str]:
    raw = node.get("@type")
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {str(item) for item in raw}
    return set()


def _looks_like_question(text: str) -> bool:
    normalized = _normalize(text).strip()
    return text.strip().endswith("?") or any(normalized.startswith(prefix) for prefix in _QUESTION_WORDS)


def _claims_have_context(content: str, matches: tuple[re.Match[str], ...]) -> bool:
    if not matches:
        return False
    for match in matches:
        start = max(content.rfind(".", 0, match.start()), content.rfind("!", 0, match.start()), content.rfind("?", 0, match.start()), content.rfind("\n", 0, match.start())) + 1
        ends = [index for index in (content.find(".", match.end()), content.find("!", match.end()), content.find("?", match.end()), content.find("\n", match.end())) if index >= 0]
        end = min(ends) + 1 if ends else min(len(content), match.end() + 180)
        if len(content[start:end].strip()) < 20:
            return False
    return True


def _has_unqualified_material_numbers(content: str, qualified: tuple[re.Match[str], ...]) -> bool:
    spans = tuple((item.start(), item.end()) for item in qualified)
    for match in _ANY_NUMBER_RE.finditer(content):
        if any(start <= match.start() and match.end() <= end for start, end in spans):
            continue
        token = match.group(0)
        # Single-digit list/section markers are not treated as material claims.
        if token.isdigit() and int(token) < 10:
            continue
        return True
    return False


def _content_is_contextualized(content: str, headings: tuple[tuple[int, str], ...]) -> bool:
    if len(content) < 80:
        return False
    sentences = _sentences(content)
    if len(sentences) >= 2 and sum(len(item) for item in sentences) / len(sentences) >= 25:
        return True
    return bool(headings) and bool(sentences) and len(sentences[0]) >= 50


def _sentences(content: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in _SENTENCE_SPLIT_RE.split(content) if len(part.strip()) >= 10)


def _external_links(semantic_input: SemanticInput) -> tuple[str, ...]:
    page_host = (urlparse(semantic_input.page_url).hostname or "").casefold()
    links: list[str] = []
    for evidence in semantic_input.evidence:
        if evidence.evidence_type.upper() != "LINK" or not isinstance(evidence.observed_value, list):
            continue
        for item in evidence.observed_value:
            if not isinstance(item, dict):
                continue
            href = str(item.get("href") or "").strip()
            parsed = urlparse(href)
            if parsed.scheme in {"http", "https"} and parsed.hostname and parsed.hostname.casefold() != page_host:
                links.append(href)
    return tuple(dict.fromkeys(links))


def _date_signals(nodes: tuple[dict[str, Any], ...], content: str) -> tuple[tuple[str, str], ...]:
    values: list[tuple[str, str]] = []
    for node in nodes:
        for key in ("datePublished", "dateModified", "dateCreated", "uploadDate", "expires"):
            raw = node.get(key)
            if isinstance(raw, str) and raw.strip():
                values.append((key, raw.strip()))
    for match in _DATE_RE.finditer(content):
        values.append(("visible", match.group(0)))
    return tuple(dict.fromkeys(values))


def _dates_are_consistent(values: tuple[tuple[str, str], ...]) -> bool:
    parsed: dict[str, list[date]] = {}
    for kind, raw in values:
        value = _parse_date(raw)
        if value is not None:
            parsed.setdefault(kind.casefold(), []).append(value)
    published = parsed.get("datepublished", []) + parsed.get("datecreated", [])
    modified = parsed.get("datemodified", [])
    if published and modified and min(modified) < min(published):
        return False
    return bool(values)


def _parse_date(raw: str) -> date | None:
    match = re.search(r"((?:19|20)\d{2})[-/](\d{1,2})[-/](\d{1,2})", raw)
    if match:
        year, month, day = map(int, match.groups())
    else:
        match = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-]((?:19|20)\d{2})", raw)
        if not match:
            return None
        day, month, year = map(int, match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _title_domain_alignment(title: str, page_url: str) -> bool:
    if not title:
        return False
    host = (urlparse(page_url).hostname or "").casefold()
    if not host or re.fullmatch(r"\d+(?:\.\d+){3}", host):
        return False
    labels = [part for part in host.split(".") if part not in {"www", "com", "org", "net", "br", "co", "io", "loja", "shop"}]
    if not labels:
        return False
    title_compact = _normalize(title).replace(" ", "")
    return any(len(label) >= 4 and _normalize(label).replace("-", "") in title_compact for label in labels)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_like = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", ascii_like, flags=re.UNICODE).strip()


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in _normalize(value).split()
        if len(token) >= 2 and token not in _STOPWORDS and not token.isdigit()
    )


def _token_overlap(source: tuple[str, ...], target: tuple[str, ...]) -> float:
    source_set = set(source)
    if not source_set:
        return 0.0
    target_set = set(target)
    return len(source_set & target_set) / len(source_set)
