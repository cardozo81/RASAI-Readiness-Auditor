"""M20 execution: optional AI content suggestions and deterministic JSON-LD guidance."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Any
from urllib.parse import urlsplit

from rasai.domain import new_id, utc_now
from rasai.m20_ai import (
    ContentEvidenceInput,
    ContentFindingInput,
    ContentRemediationRequest,
    ProviderState,
    build_content_remediation_router,
)
from rasai.m20_persistence import (
    ContentRemediationRun,
    M20Persistence,
    PersistedContentSuggestion,
    PersistedJsonLdSuggestion,
)
from rasai.persistence import AuditWorkspace

ELIGIBLE_CONTENT_RULES = frozenset(
    [f"BR-GEO-{number:03d}" for number in range(28, 34)]
    + [f"BR-GEO-{number:03d}" for number in range(38, 50)]
)
_MAX_MAIN_CONTENT_CHARS = 16_000
_ENTITY_SCHEMA_TYPES = {
    "ORGANIZATION": "Organization",
    "PERSON": "Person",
    "PRODUCT": "Product",
    "SERVICE": "Service",
    "PLACE": "Place",
    "BRAND": "Brand",
}


@dataclass(frozen=True, slots=True)
class M20ExecutionResult:
    status: str
    suggestion_ids: tuple[str, ...]
    jsonld_suggestion_ids: tuple[str, ...]
    attempted_contexts: int


def execute_m20(
    *,
    audit_id: str,
    enabled: bool,
    semantic_provider: Any,
    workspace: AuditWorkspace,
) -> M20ExecutionResult:
    """Materialize auxiliary suggestions without changing scored entities."""
    jsonld_ids = _materialize_jsonld(audit_id=audit_id, workspace=workspace)
    router = build_content_remediation_router(semantic_provider)

    with M20Persistence(workspace) as store:
        if not enabled:
            store.upsert_run(ContentRemediationRun(
                audit_id=audit_id, enabled=False, strategy=router.strategy,
                status="DISABLED", eligible_findings=0, attempted_contexts=0,
                generated_suggestions=0, reason="DEFAULT_OFF",
            ))
            return M20ExecutionResult("DISABLED", (), jsonld_ids, 0)

        requests = _load_requests(audit_id=audit_id, workspace=workspace)
        eligible_findings = sum(len(item.findings) for item in requests)
        if eligible_findings == 0:
            store.upsert_run(ContentRemediationRun(
                audit_id=audit_id, enabled=True, strategy=router.strategy,
                status="NO_ELIGIBLE_FINDINGS", eligible_findings=0,
                attempted_contexts=0, generated_suggestions=0,
            ))
            return M20ExecutionResult("NO_ELIGIBLE_FINDINGS", (), jsonld_ids, 0)

        if not router.providers:
            store.upsert_run(ContentRemediationRun(
                audit_id=audit_id, enabled=True, strategy=router.strategy,
                status="NOT_CONFIGURED", eligible_findings=eligible_findings,
                attempted_contexts=0, generated_suggestions=0,
                reason="AI_NOT_CONFIGURED_OR_QUARANTINED",
            ))
            return M20ExecutionResult("NOT_CONFIGURED", (), jsonld_ids, 0)

        suggestion_ids: list[str] = []
        attempted = 0
        degraded = False
        successful_contexts = 0
        last_reason: str | None = None
        for request in requests:
            attempted += 1
            result = router.analyze(request)
            for attempt in router.consume_attempts():
                store.add_attempt(
                    attempt_id=new_id("M20A"), audit_id=audit_id,
                    page_id=request.page_id, snapshot_id=request.snapshot_id,
                    device=request.device, url=request.page_url, attempt=attempt,
                )
            if result.state is not ProviderState.AVAILABLE:
                degraded = True
                last_reason = result.reason
                continue
            successful_contexts += 1
            for suggestion in result.suggestions:
                suggestion_id = new_id("M20S")
                store.add_suggestion(PersistedContentSuggestion(
                    suggestion_id=suggestion_id, audit_id=audit_id,
                    finding_id=suggestion.finding_id, page_id=request.page_id,
                    snapshot_id=request.snapshot_id, device=request.device,
                    provider=result.provider or "UNKNOWN", model=result.model,
                    objective=suggestion.objective,
                    target_location=suggestion.target_location,
                    proposed_text=suggestion.proposed_text,
                    evidence_ids=suggestion.evidence_ids,
                    confidence=suggestion.confidence,
                    review_note=suggestion.review_note,
                    created_at=utc_now().isoformat(),
                ))
                suggestion_ids.append(suggestion_id)

        if suggestion_ids and degraded:
            status = "PARTIAL"
        elif suggestion_ids:
            status = "SUCCESS"
        elif successful_contexts:
            status = "NO_SAFE_SUGGESTIONS"
        else:
            status = "DEGRADED"
        store.upsert_run(ContentRemediationRun(
            audit_id=audit_id, enabled=True, strategy=router.strategy,
            status=status, eligible_findings=eligible_findings,
            attempted_contexts=attempted,
            generated_suggestions=len(suggestion_ids), reason=last_reason,
        ))
        return M20ExecutionResult(status, tuple(suggestion_ids), jsonld_ids, attempted)


def _load_requests(*, audit_id: str, workspace: AuditWorkspace) -> tuple[ContentRemediationRequest, ...]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        snapshots = connection.execute(
            """
            SELECT ps.*, p.normalized_url
            FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
            WHERE p.audit_id=? ORDER BY p.normalized_url,ps.device
            """, (audit_id,),
        ).fetchall()
        requests: list[ContentRemediationRequest] = []
        placeholders = ",".join("?" for _ in ELIGIBLE_CONTENT_RULES)
        allowed_rules = sorted(ELIGIBLE_CONTENT_RULES)
        for snapshot in snapshots:
            params: list[Any] = [audit_id, snapshot["page_id"], snapshot["device"], *allowed_rules]
            findings = connection.execute(
                f"""
                SELECT f.* FROM findings f
                WHERE f.audit_id=? AND f.page_id=?
                  AND f.device IN (?, 'BOTH')
                  AND f.rule_id IN ({placeholders})
                ORDER BY f.rule_id,f.finding_id
                """, tuple(params),
            ).fetchall()
            if not findings:
                continue
            finding_inputs: list[ContentFindingInput] = []
            all_evidence_ids: list[str] = []
            for finding in findings:
                evidence_ids = tuple(_json_list(finding["evidence_ids"]))
                all_evidence_ids.extend(evidence_ids)
                finding_inputs.append(ContentFindingInput(
                    finding_id=str(finding["finding_id"]), rule_id=str(finding["rule_id"]),
                    title=str(finding["title"]), severity=str(finding["severity"]),
                    expected_condition=str(finding["expected_condition"] or ""),
                    observed_value=_json_value(finding["observed_value"]),
                    evidence_ids=evidence_ids,
                ))
            requests.append(ContentRemediationRequest(
                snapshot_id=str(snapshot["snapshot_id"]), page_id=str(snapshot["page_id"]),
                page_url=str(snapshot["normalized_url"]), device=str(snapshot["device"]),
                title=str(snapshot["title"]) if snapshot["title"] else None,
                main_content=_read_artifact(workspace, snapshot["main_content_ref"], _MAX_MAIN_CONTENT_CHARS),
                findings=tuple(finding_inputs),
                evidence=_load_evidence(connection, tuple(dict.fromkeys(all_evidence_ids))),
            ))
        return tuple(requests)
    finally:
        connection.close()


def _load_evidence(connection: sqlite3.Connection, evidence_ids: tuple[str, ...]) -> tuple[ContentEvidenceInput, ...]:
    if not evidence_ids:
        return ()
    placeholders = ",".join("?" for _ in evidence_ids)
    rows = connection.execute(
        f"SELECT * FROM evidence WHERE evidence_id IN ({placeholders}) ORDER BY evidence_id",
        evidence_ids,
    ).fetchall()
    return tuple(ContentEvidenceInput(
        evidence_id=str(row["evidence_id"]), evidence_type=str(row["evidence_type"]),
        source=str(row["source"]), observed_value=_json_value(row["observed_value"]),
    ) for row in rows)


def _materialize_jsonld(*, audit_id: str, workspace: AuditWorkspace) -> tuple[str, ...]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        language_row = connection.execute(
            "SELECT primary_language FROM audits WHERE audit_id=?", (audit_id,)
        ).fetchone()
        language = str(language_row["primary_language"]) if language_row else "pt-BR"
        rows = connection.execute(
            """
            SELECT ps.*,p.normalized_url
            FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
            WHERE p.audit_id=? ORDER BY p.normalized_url,ps.device
            """, (audit_id,),
        ).fetchall()
        ids: list[str] = []
        with M20Persistence(workspace) as store:
            for row in rows:
                suggestion_id = new_id("JLD")
                evidence_ids = tuple(str(item["evidence_id"]) for item in connection.execute(
                    """
                    SELECT evidence_id FROM evidence
                    WHERE snapshot_id=? AND evidence_type IN
                    ('STRUCTURED_DATA','HTML_ELEMENT','META_TAG','CANONICAL','MAIN_CONTENT')
                    ORDER BY evidence_id
                    """, (row["snapshot_id"],),
                ).fetchall())
                status, types, proposed, improvements = _jsonld_for_snapshot(
                    connection=connection, workspace=workspace, snapshot=row, language=language,
                )
                store.add_jsonld(PersistedJsonLdSuggestion(
                    suggestion_id=suggestion_id, audit_id=audit_id,
                    page_id=str(row["page_id"]), snapshot_id=str(row["snapshot_id"]),
                    device=str(row["device"]), status=status, existing_types=types,
                    proposed_json=proposed, improvements=improvements,
                    evidence_ids=evidence_ids, created_at=utc_now().isoformat(),
                ))
                ids.append(suggestion_id)
        return tuple(ids)
    finally:
        connection.close()


def _high_confidence_entities(connection: sqlite3.Connection, snapshot_id: str) -> tuple[sqlite3.Row, ...]:
    """Return optional semantic entities without making M7 tables a prerequisite."""
    try:
        return tuple(connection.execute(
            """
            SELECT name,entity_type,confidence FROM entity_observations
            WHERE snapshot_id=? AND confidence>=0.9 AND entity_type NOT IN ('TOPIC','OTHER')
            ORDER BY confidence DESC,entity_observation_id LIMIT 2
            """, (snapshot_id,),
        ).fetchall())
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return ()
        raise


def _jsonld_for_snapshot(
    *, connection: sqlite3.Connection, workspace: AuditWorkspace,
    snapshot: sqlite3.Row, language: str,
) -> tuple[str, tuple[str, ...], Any | None, tuple[str, ...]]:
    ref = snapshot["structured_data_ref"]
    if not ref:
        proposed: dict[str, Any] = {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "url": _safe_page_url(snapshot["canonical"], snapshot["normalized_url"]),
            "inLanguage": language,
        }
        if snapshot["title"]:
            proposed["name"] = str(snapshot["title"]).strip()
        if snapshot["description"]:
            proposed["description"] = str(snapshot["description"]).strip()
        entities = _high_confidence_entities(connection, str(snapshot["snapshot_id"]))
        if len(entities) == 1 and str(entities[0]["entity_type"]) in _ENTITY_SCHEMA_TYPES:
            proposed["mainEntity"] = {
                "@type": _ENTITY_SCHEMA_TYPES[str(entities[0]["entity_type"])],
                "name": str(entities[0]["name"]),
            }
        return "MISSING_PROPOSED", (), proposed, (
            "JSON-LD não foi observado. A proposta é um baseline WebPage baseado somente em dados já visíveis/persistidos.",
            "Use tipo mais específico apenas quando o conteúdo visível sustentar esse tipo e valide as propriedades exigidas pela feature alvo.",
            "JSON-LD é reforço opcional; não é requisito universal de GEO nem garantia de rich result.",
        )

    path = workspace.root / str(ref)
    if not path.is_file():
        return "UNAVAILABLE", (), None, ("Artifact estruturado referenciado não está disponível para revisão.",)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "UNAVAILABLE", (), None, ("Artifact de Structured Data não pôde ser interpretado.",)

    blocks = payload.get("blocks") if isinstance(payload, dict) else None
    if not isinstance(blocks, list):
        return "UNAVAILABLE", (), None, ("Formato persistido de Structured Data não reconhecido.",)
    types = tuple(dict.fromkeys(
        str(value) for block in blocks if isinstance(block, dict)
        for value in (block.get("types") or []) if value
    ))
    improvements: list[str] = []
    parse_errors = [block for block in blocks if isinstance(block, dict) and block.get("parse_error")]
    if parse_errors:
        improvements.append(
            f"Corrigir {len(parse_errors)} bloco(s) JSON-LD com erro de parse antes de qualquer otimização semântica."
        )
    raw_values = [
        str(block.get("raw") or "").strip()
        for block in blocks if isinstance(block, dict) and block.get("raw")
    ]
    if len(raw_values) != len(set(raw_values)):
        improvements.append(
            "Há blocos JSON-LD idênticos repetidos; consolidar duplicações evita ambiguidade e manutenção redundante."
        )

    nodes: list[dict[str, Any]] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("parsed") is not None:
            nodes.extend(_jsonld_nodes(block["parsed"]))
    if nodes:
        if not any("@context" in node for node in nodes):
            improvements.append("Adicionar @context=https://schema.org no documento/graph JSON-LD.")
        if any("@type" not in node for node in nodes):
            improvements.append(
                "Existem nós sem @type; definir o tipo Schema.org somente quando ele representar o conteúdo visível."
            )
        web_pages = [node for node in nodes if _has_type(node, "WebPage")]
        if web_pages:
            web = web_pages[0]
            if not web.get("url"):
                improvements.append("O nó WebPage pode declarar url usando a URL canônica/normalizada observada.")
            if snapshot["title"] and not web.get("name"):
                improvements.append("O nó WebPage pode declarar name coerente com o <title> observado.")
            if snapshot["description"] and not web.get("description"):
                improvements.append("O nó WebPage pode declarar description coerente com a meta description observada.")
            if language and not web.get("inLanguage"):
                improvements.append("O nó WebPage pode declarar inLanguage conforme o idioma configurado da auditoria.")
        elif types:
            improvements.append(
                "Opcionalmente, avaliar um nó WebPage ligado aos tipos existentes quando isso representar a página; não substituir o tipo principal específico."
            )
    if not improvements:
        improvements.append(
            "Nenhum problema estrutural genérico foi detectado automaticamente; validar propriedades obrigatórias/recomendadas do tipo específico e correspondência com conteúdo visível."
        )
    improvements.append(
        "Não marcar conteúdo oculto, irrelevante ou não sustentado pela página; Structured Data deve representar fielmente o conteúdo visível."
    )
    return "EXISTING_REVIEW", types, None, tuple(improvements)


def _jsonld_nodes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [node for item in value for node in _jsonld_nodes(item)]
    if not isinstance(value, dict):
        return []
    nodes = [value]
    graph = value.get("@graph")
    if isinstance(graph, list):
        nodes.extend(item for item in graph if isinstance(item, dict))
    return nodes


def _has_type(node: dict[str, Any], expected: str) -> bool:
    value = node.get("@type")
    if isinstance(value, str):
        return value == expected
    if isinstance(value, list):
        return expected in value
    return False


def _safe_page_url(canonical: Any, normalized_url: Any) -> str:
    candidate = str(canonical or "").strip()
    if candidate:
        parsed = urlsplit(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
    return str(normalized_url)


def _read_artifact(workspace: AuditWorkspace, ref: Any, limit: int) -> str:
    if not ref:
        return ""
    path = workspace.root / str(ref)
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _json_value(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _json_list(value: Any) -> list[str]:
    parsed = _json_value(value)
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
