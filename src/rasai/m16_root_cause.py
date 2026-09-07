"""M16 evidence-backed root cause and element-level remediation materialization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import sqlite3
from typing import Any

from rasai.domain import new_id, utc_now
from rasai.persistence import AuditWorkspace
from rasai.remediation import RemediationRecipe, recipe_for


@dataclass(frozen=True, slots=True)
class AffectedElement:
    element_observation_id: str | None
    relation: str
    selector: str | None
    tag_name: str | None
    element_id: str | None
    classes: tuple[str, ...]
    outer_html: str | None
    text_excerpt: str | None
    snapshot_id: str | None
    device: str | None


@dataclass(frozen=True, slots=True)
class RootCauseAnalysis:
    analysis_id: str
    audit_id: str
    finding_id: str
    rule_id: str
    cause_type: str
    affected_scope: str
    cause_summary: str
    evidence_basis: tuple[str, ...]
    affected_elements: tuple[AffectedElement, ...]
    selector_status: str
    observed_value: Any
    expected_condition: str | None
    exact_change: str
    example_after: str | None
    acceptance_criteria: tuple[str, ...]
    revalidation_steps: tuple[str, ...]
    human_decision_required: str | None
    diagnostic_confidence: str
    materialized_at: datetime


_CAUSE_TYPE: dict[str, str] = {
    "BR-GEO-005": "TECHNICAL_ACCESS_FAILURE",
    "BR-GEO-011": "INDEXING_DIRECTIVE_CONFLICT",
    "BR-GEO-012": "NOINDEX_POLICY",
    "BR-GEO-013": "CANONICAL_DECLARATION",
    "BR-GEO-014": "CANONICAL_TARGET",
    "BR-GEO-015": "RAW_RENDERED_SIGNAL_CONFLICT",
    "BR-GEO-017": "ROBOTS_RESOURCE",
    "BR-GEO-018": "CRAWLER_ACCESS_POLICY",
    "BR-GEO-025": "CONTENT_EXTRACTABILITY",
    "BR-GEO-026": "CONTENT_PARITY",
    "BR-GEO-027": "CONTENT_DUPLICATION",
    "BR-GEO-028": "TITLE_SEMANTICS",
    "BR-GEO-029": "HEADING_HIERARCHY",
    "BR-GEO-030": "TOPIC_SECTION_STRUCTURE",
    "BR-GEO-031": "PRIMARY_ENTITY_CLARITY",
    "BR-GEO-032": "ENTITY_RELATIONSHIP_CONTEXT",
    "BR-GEO-033": "ENTITY_AMBIGUITY",
    "BR-GEO-034": "STRUCTURED_DATA_SYNTAX",
    "BR-GEO-035": "STRUCTURED_DATA_TYPES",
    "BR-GEO-036": "STRUCTURED_DATA_VISIBLE_CONSISTENCY",
    "BR-GEO-037": "STRUCTURED_DATA_ENTITY_CONSISTENCY",
    "BR-GEO-038": "PRIMARY_INTENT_CLARITY",
    "BR-GEO-039": "ANSWER_GAP",
    "BR-GEO-040": "ANSWER_CONTEXT_GAP",
    "BR-GEO-041": "FACTUAL_CLAIM_CLARITY",
    "BR-GEO-042": "FACTUAL_CONTEXT_GAP",
    "BR-GEO-043": "CLAIM_QUALIFIER_GAP",
    "BR-GEO-044": "EXCESSIVE_INFERENCE_LOAD",
    "BR-GEO-045": "ATTRIBUTION_EVIDENCE_GAP",
    "BR-GEO-046": "RESPONSIBILITY_SIGNAL_GAP",
    "BR-GEO-047": "FRESHNESS_SIGNAL_INCONSISTENCY",
    "BR-GEO-048": "INTENT_COVERAGE_GAP",
    "BR-GEO-049": "INTENT_GAP_EVIDENCE",
}

_CAUSE_SUMMARY: dict[str, str] = {
    "BR-GEO-005": "A aquisição técnica da URL não satisfez a condição mínima de recuperação utilizável.",
    "BR-GEO-011": "Os sinais de indexação observados apresentam conflito material entre fontes aplicáveis.",
    "BR-GEO-012": "Foi observada diretiva noindex e a decisão correta depende da intenção aprovada para a URL.",
    "BR-GEO-013": "A declaração canonical observada está ausente, ambígua ou não satisfaz a condição esperada da regra.",
    "BR-GEO-014": "O destino canonical observado não satisfaz os critérios técnicos/contextuais avaliáveis.",
    "BR-GEO-015": "Sinais relevantes divergem entre a resposta RAW e o DOM renderizado.",
    "BR-GEO-017": "O recurso robots.txt observado não satisfez a condição de disponibilidade/interpretabilidade da regra.",
    "BR-GEO-018": "A política observada para pelo menos um crawler requer revisão contra a intenção de acesso aprovada.",
    "BR-GEO-025": "O conteúdo principal não ficou extraível de forma suficiente no contexto avaliado.",
    "BR-GEO-026": "O conteúdo principal apresenta diferença material entre contextos comparados pela regra.",
    "BR-GEO-027": "A estrutura observada indica duplicação ou fragmentação material do conteúdo principal.",
    "BR-GEO-028": "O título observado não satisfaz presença e/ou representatividade semântica exigida pela regra.",
    "BR-GEO-029": "O conjunto de headings observado não expressa uma hierarquia semântica suficientemente compreensível.",
    "BR-GEO-030": "O tópico principal e/ou as seções materiais não estão explicitamente identificáveis com evidência suficiente.",
    "BR-GEO-031": "A entidade principal aplicável não está identificável com clareza suficiente.",
    "BR-GEO-032": "Tipos ou relações entre entidades relevantes carecem de contexto suficiente.",
    "BR-GEO-033": "Existe ambiguidade material de entidade que não é resolvida pelas evidências da página.",
    "BR-GEO-034": "Pelo menos um bloco de dados estruturados não é sintaticamente interpretável.",
    "BR-GEO-035": "Tipos ou propriedades relevantes dos dados estruturados não puderam ser identificados de forma suficiente.",
    "BR-GEO-036": "Dados estruturados e conteúdo visível apresentam inconsistência material na evidência avaliada.",
    "BR-GEO-037": "As entidades declaradas nos dados estruturados não estão suficientemente alinhadas às entidades observadas.",
    "BR-GEO-038": "A intenção principal atendida pela página não está identificável de forma suficientemente explícita.",
    "BR-GEO-039": "Uma ou mais perguntas/intuições primárias aplicáveis não possuem resposta explícita suficiente.",
    "BR-GEO-040": "A resposta observada depende de contexto ou inferência adicional para ser compreendida adequadamente.",
    "BR-GEO-041": "Afirmações factuais materiais não estão suficientemente distinguíveis ou explícitas.",
    "BR-GEO-042": "Afirmações factuais relevantes carecem do contexto necessário para interpretação segura.",
    "BR-GEO-043": "Claims numéricos, temporais ou quantitativos carecem de qualificadores necessários.",
    "BR-GEO-044": "Informações importantes exigem inferência excessiva em vez de estarem explícitas no conteúdo.",
    "BR-GEO-045": "Claims materiais carecem de atribuição ou evidência de suporte quando isso é necessário.",
    "BR-GEO-046": "A entidade responsável, publisher ou autor não está identificável quando relevante.",
    "BR-GEO-047": "Sinais de publicação/atualização observados são insuficientes ou internamente inconsistentes.",
    "BR-GEO-048": "O conteúdo observado não representa suficientemente o conjunto de intenções relevantes identificado.",
    "BR-GEO-049": "Existe lacuna material de intenção sustentada pelas evidências disponíveis.",
}

_EXACT_TAGS: dict[str, tuple[str, ...]] = {
    "BR-GEO-011": ("meta",),
    "BR-GEO-012": ("meta",),
    "BR-GEO-013": ("link",),
    "BR-GEO-014": ("link",),
    "BR-GEO-015": ("meta", "link"),
    "BR-GEO-025": ("main",),
    "BR-GEO-026": ("main",),
    "BR-GEO-027": ("main",),
    "BR-GEO-028": ("title",),
    "BR-GEO-030": ("main",),
    "BR-GEO-034": ("script",),
    "BR-GEO-035": ("script",),
    "BR-GEO-036": ("script",),
    "BR-GEO-037": ("script",),
}

# Structured-data rules have concrete script nodes and must be resolved through
# _EXACT_TAGS before falling back to semantic content context. Context-only rules
# are entity/answerability/citation/evidence/intent semantics.
_SEMANTIC_CONTEXT_RULES = frozenset(
    f"BR-GEO-{number:03d}" for number in (*range(31, 34), *range(38, 50))
)
_PAGE_RESOURCE_RULES = frozenset({"BR-GEO-005"})
_GLOBAL_RESOURCE_RULES = frozenset({"BR-GEO-017", "BR-GEO-018"})


class M16Persistence:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self.workspace = workspace
        self._connection = sqlite3.connect(workspace.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def __enter__(self) -> "M16Persistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS root_cause_analyses (
                    analysis_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    finding_id TEXT NOT NULL UNIQUE REFERENCES findings(finding_id) ON DELETE CASCADE,
                    rule_id TEXT NOT NULL,
                    cause_type TEXT NOT NULL,
                    affected_scope TEXT NOT NULL,
                    cause_summary TEXT NOT NULL,
                    evidence_basis TEXT NOT NULL,
                    affected_elements TEXT NOT NULL,
                    selector_status TEXT NOT NULL,
                    observed_value TEXT,
                    expected_condition TEXT,
                    exact_change TEXT NOT NULL,
                    example_after TEXT,
                    acceptance_criteria TEXT NOT NULL,
                    revalidation_steps TEXT NOT NULL,
                    human_decision_required TEXT,
                    diagnostic_confidence TEXT NOT NULL,
                    materialized_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_root_cause_audit_rule
                    ON root_cause_analyses(audit_id, rule_id);
                """
            )

    def upsert(self, analysis: RootCauseAnalysis) -> None:
        payload = (
            analysis.analysis_id,
            analysis.audit_id,
            analysis.finding_id,
            analysis.rule_id,
            analysis.cause_type,
            analysis.affected_scope,
            analysis.cause_summary,
            _dump(list(analysis.evidence_basis)),
            _dump([_element_to_json(item) for item in analysis.affected_elements]),
            analysis.selector_status,
            _dump(analysis.observed_value) if analysis.observed_value is not None else None,
            analysis.expected_condition,
            analysis.exact_change,
            analysis.example_after,
            _dump(list(analysis.acceptance_criteria)),
            _dump(list(analysis.revalidation_steps)),
            analysis.human_decision_required,
            analysis.diagnostic_confidence,
            analysis.materialized_at.isoformat(),
        )
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO root_cause_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(finding_id) DO UPDATE SET
                    rule_id=excluded.rule_id,
                    cause_type=excluded.cause_type,
                    affected_scope=excluded.affected_scope,
                    cause_summary=excluded.cause_summary,
                    evidence_basis=excluded.evidence_basis,
                    affected_elements=excluded.affected_elements,
                    selector_status=excluded.selector_status,
                    observed_value=excluded.observed_value,
                    expected_condition=excluded.expected_condition,
                    exact_change=excluded.exact_change,
                    example_after=excluded.example_after,
                    acceptance_criteria=excluded.acceptance_criteria,
                    revalidation_steps=excluded.revalidation_steps,
                    human_decision_required=excluded.human_decision_required,
                    diagnostic_confidence=excluded.diagnostic_confidence,
                    materialized_at=excluded.materialized_at
                """,
                payload,
            )

    def get(self, finding_id: str) -> RootCauseAnalysis | None:
        row = self._connection.execute(
            "SELECT * FROM root_cause_analyses WHERE finding_id=?", (finding_id,)
        ).fetchone()
        return None if row is None else _map_analysis(row)

    def list_for_audit(self, audit_id: str) -> tuple[RootCauseAnalysis, ...]:
        rows = self._connection.execute(
            "SELECT * FROM root_cause_analyses WHERE audit_id=? ORDER BY rule_id,finding_id",
            (audit_id,),
        ).fetchall()
        return tuple(_map_analysis(row) for row in rows)


def materialize_root_causes(*, audit_id: str, workspace: AuditWorkspace) -> int:
    """Derive one reproducible root-cause record for every persisted finding."""

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        findings = list(connection.execute(
            """SELECT f.*, re.snapshot_id AS execution_snapshot_id,
                      re.observed_value AS execution_observed_value,
                      re.expected_condition AS execution_expected_condition,
                      re.evidence_ids AS execution_evidence_ids
               FROM findings f
               JOIN rule_executions re ON re.rule_execution_id=f.rule_execution_id
               WHERE f.audit_id=? ORDER BY f.finding_id""",
            (audit_id,),
        ).fetchall())
        with M16Persistence(workspace) as store:
            for finding in findings:
                current = store.get(str(finding["finding_id"]))
                analysis_id = current.analysis_id if current is not None else new_id("RCA")
                analysis = derive_root_cause(
                    finding=finding,
                    observations=_affected_elements(connection, finding),
                    analysis_id=analysis_id,
                    audit_id=audit_id,
                )
                store.upsert(analysis)
        return len(findings)
    finally:
        connection.close()


def derive_root_cause(
    *,
    finding: Any,
    observations: tuple[AffectedElement, ...],
    analysis_id: str,
    audit_id: str,
) -> RootCauseAnalysis:
    rule_id = str(finding["rule_id"])
    recipe = recipe_for(rule_id)
    observed = _json_value(
        finding["execution_observed_value"]
        if "execution_observed_value" in finding.keys()
        else finding["observed_value"]
    )
    expected = (
        finding["execution_expected_condition"]
        if "execution_expected_condition" in finding.keys() and finding["execution_expected_condition"]
        else finding["expected_condition"]
    )
    evidence = _json_list(
        finding["execution_evidence_ids"]
        if "execution_evidence_ids" in finding.keys() and finding["execution_evidence_ids"]
        else finding["evidence_ids"]
    )

    scope, selector_status, confidence = _scope_status(rule_id, observations)
    cause = _CAUSE_SUMMARY.get(
        rule_id,
        "A condição observada não satisfaz a condição esperada da Business Rule para esta ocorrência.",
    )
    observed_summary = _observed_summary(observed)
    if observed_summary:
        cause += f" Evidência observada: {observed_summary}"

    return RootCauseAnalysis(
        analysis_id=analysis_id,
        audit_id=audit_id,
        finding_id=str(finding["finding_id"]),
        rule_id=rule_id,
        cause_type=_CAUSE_TYPE.get(rule_id, "RULE_CONDITION_MISMATCH"),
        affected_scope=scope,
        cause_summary=cause,
        evidence_basis=tuple(str(item) for item in evidence),
        affected_elements=observations,
        selector_status=selector_status,
        observed_value=observed,
        expected_condition=str(expected) if expected is not None else None,
        exact_change=_exact_change(recipe),
        example_after=recipe.example,
        acceptance_criteria=recipe.acceptance,
        revalidation_steps=recipe.validation,
        human_decision_required=recipe.human_decision,
        diagnostic_confidence=confidence,
        materialized_at=utc_now(),
    )


def _affected_elements(connection: sqlite3.Connection, finding: sqlite3.Row) -> tuple[AffectedElement, ...]:
    finding_id = str(finding["finding_id"])
    linked = _query_rows(
        connection,
        """SELECT eo.* FROM element_observations eo
           JOIN finding_element_observations feo
             ON feo.element_observation_id=eo.element_observation_id
           WHERE feo.finding_id=? ORDER BY eo.element_observation_id""",
        (finding_id,),
    )
    if linked:
        return tuple(_element(row, "EXACT") for row in linked[:12])

    snapshot_id = finding["execution_snapshot_id"]
    if not snapshot_id:
        return ()
    rule_id = str(finding["rule_id"])

    if rule_id == "BR-GEO-029":
        rows = _query_rows(
            connection,
            """SELECT * FROM element_observations
               WHERE snapshot_id=? AND tag_name IN ('h1','h2','h3','h4','h5','h6')
               ORDER BY element_observation_id LIMIT 40""",
            (snapshot_id,),
        )
        return tuple(_element(row, "SET_MEMBER") for row in rows)

    tags = _EXACT_TAGS.get(rule_id)
    if tags:
        placeholders = ",".join("?" for _ in tags)
        rows = _query_rows(
            connection,
            f"SELECT * FROM element_observations WHERE snapshot_id=? AND tag_name IN ({placeholders}) ORDER BY element_observation_id LIMIT 12",
            (snapshot_id, *tags),
        )
        rows = [row for row in rows if _candidate_matches(rule_id, row)]
        if len(rows) == 1:
            return (_element(rows[0], "EXACT"),)
        if len(rows) > 1:
            return tuple(_element(row, "SET_MEMBER") for row in rows)

    if rule_id in _SEMANTIC_CONTEXT_RULES:
        rows = _query_rows(
            connection,
            """SELECT * FROM element_observations
               WHERE snapshot_id=? AND tag_name='main'
               ORDER BY element_observation_id LIMIT 4""",
            (snapshot_id,),
        )
        return tuple(_element(row, "CONTEXT_REGION") for row in rows)

    return ()


def _candidate_matches(rule_id: str, row: sqlite3.Row) -> bool:
    html = str(row["outer_html"] or "").casefold()
    tag = str(row["tag_name"])
    if rule_id in {"BR-GEO-011", "BR-GEO-012"}:
        return tag == "meta" and "robots" in html
    if rule_id in {"BR-GEO-013", "BR-GEO-014"}:
        return tag == "link" and "canonical" in html
    if rule_id == "BR-GEO-015":
        return (tag == "meta" and "robots" in html) or (tag == "link" and "canonical" in html)
    if rule_id in {"BR-GEO-034", "BR-GEO-035", "BR-GEO-036", "BR-GEO-037"}:
        return tag == "script" and "application/ld+json" in html
    return True


def _scope_status(rule_id: str, elements: tuple[AffectedElement, ...]) -> tuple[str, str, str]:
    if rule_id in _PAGE_RESOURCE_RULES:
        return "PAGE_RESOURCE", "NOT_APPLICABLE", "HIGH"
    if rule_id in _GLOBAL_RESOURCE_RULES:
        return "DOMAIN_RESOURCE", "NOT_APPLICABLE", "HIGH"
    if not elements:
        return "DOCUMENT_OR_CONTENT", "NOT_DETERMINED", "MEDIUM"
    relations = {item.relation for item in elements}
    if relations == {"EXACT"} and len(elements) == 1:
        return "EXACT_ELEMENT", "EXACT", "HIGH"
    if "CONTEXT_REGION" in relations:
        return "CONTENT_REGION", "CONTEXT_REGION", "MEDIUM"
    return "ELEMENT_SET_OR_DOCUMENT", "MULTI_ELEMENT_SET", "MEDIUM"


def _exact_change(recipe: RemediationRecipe) -> str:
    parts = [f"Ação: {recipe.action}", f"Alvo: {recipe.target}"]
    if recipe.element:
        parts.append(f"Elemento/estrutura: {recipe.element}")
    if recipe.location:
        parts.append(f"Local: {recipe.location}")
    parts.append(recipe.description)
    return " · ".join(parts)


def _observed_summary(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("reason", "summary", "state", "status", "error"):
            candidate = value.get(key)
            if isinstance(candidate, (str, int, float, bool)) and str(candidate).strip():
                return str(candidate).strip()[:360]
        provider = value.get("provider_observed")
        if isinstance(provider, dict):
            candidate = provider.get("summary")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()[:360]
    if isinstance(value, (str, int, float, bool)):
        return str(value)[:360]
    return None


def _element(row: sqlite3.Row, relation: str) -> AffectedElement:
    return AffectedElement(
        element_observation_id=str(row["element_observation_id"]),
        relation=relation,
        selector=str(row["selector"]) if row["selector"] else None,
        tag_name=str(row["tag_name"]) if row["tag_name"] else None,
        element_id=str(row["element_id"]) if row["element_id"] else None,
        classes=tuple(str(item) for item in (_json_value(row["classes"]) or [])),
        outer_html=str(row["outer_html"]) if row["outer_html"] else None,
        text_excerpt=str(row["text_excerpt"]) if row["text_excerpt"] else None,
        snapshot_id=str(row["snapshot_id"]) if row["snapshot_id"] else None,
        device=str(row["device"]) if row["device"] else None,
    )


def _query_rows(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_value(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return str(value)


def _json_list(value: Any) -> list[Any]:
    parsed = _json_value(value)
    return parsed if isinstance(parsed, list) else []


def _element_to_json(element: AffectedElement) -> dict[str, Any]:
    data = asdict(element)
    data["classes"] = list(element.classes)
    return data


def _map_analysis(row: sqlite3.Row) -> RootCauseAnalysis:
    elements = []
    for item in _json_value(row["affected_elements"]) or []:
        if not isinstance(item, dict):
            continue
        elements.append(AffectedElement(
            element_observation_id=item.get("element_observation_id"),
            relation=str(item.get("relation") or "CONTEXT_REGION"),
            selector=item.get("selector"),
            tag_name=item.get("tag_name"),
            element_id=item.get("element_id"),
            classes=tuple(str(value) for value in item.get("classes", [])),
            outer_html=item.get("outer_html"),
            text_excerpt=item.get("text_excerpt"),
            snapshot_id=item.get("snapshot_id"),
            device=item.get("device"),
        ))
    return RootCauseAnalysis(
        analysis_id=row["analysis_id"],
        audit_id=row["audit_id"],
        finding_id=row["finding_id"],
        rule_id=row["rule_id"],
        cause_type=row["cause_type"],
        affected_scope=row["affected_scope"],
        cause_summary=row["cause_summary"],
        evidence_basis=tuple(str(item) for item in (_json_value(row["evidence_basis"]) or [])),
        affected_elements=tuple(elements),
        selector_status=row["selector_status"],
        observed_value=_json_value(row["observed_value"]),
        expected_condition=row["expected_condition"],
        exact_change=row["exact_change"],
        example_after=row["example_after"],
        acceptance_criteria=tuple(str(item) for item in (_json_value(row["acceptance_criteria"]) or [])),
        revalidation_steps=tuple(str(item) for item in (_json_value(row["revalidation_steps"]) or [])),
        human_decision_required=row["human_decision_required"],
        diagnostic_confidence=row["diagnostic_confidence"],
        materialized_at=datetime.fromisoformat(row["materialized_at"]),
    )
