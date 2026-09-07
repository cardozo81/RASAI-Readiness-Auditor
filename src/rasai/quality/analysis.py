"""Read-only audit quality and decision-support analysis.

This module evaluates the quality/completeness of RASAi evidence and produces
operational prioritization. It never changes BR-GEO findings, SARI-001 or
SCORE-GEO-003 and must not be interpreted as another readiness score.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

_DETERMINISTIC_RULES = frozenset(
    [f"BR-GEO-{number:03d}" for number in range(1, 28)]
    + ["BR-GEO-050", "BR-GEO-051", "BR-GEO-052", "BR-GEO-053", "BR-GEO-054"]
)
_SEVERITY_WEIGHT = {"INFO": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5}
_CONFIDENCE_POINTS = {"LOW": 8.0, "MEDIUM": 14.0, "HIGH": 20.0}
_EFFORT_FACTOR = {"LOW": 1.0, "MEDIUM": 0.85, "HIGH": 0.70}
_RESULT_RANK = {"PASS": 0, "NOT_APPLICABLE": 1, "UNKNOWN": 2, "ERROR": 3, "WARNING": 4, "FAIL": 5}


@dataclass(frozen=True, slots=True)
class HealthCheck:
    code: str
    status: str
    severity: str
    title: str
    detail: str
    evidence: dict[str, Any]


@dataclass(frozen=True, slots=True)
class FindingAssessment:
    finding_id: str
    rule_id: str
    severity: str
    status: str
    url: str | None
    device: str | None
    title: str
    evidence_confidence: str
    confidence_reasons: tuple[str, ...]
    provenance: str
    scope_count: int
    effort: str
    operational_priority: float
    priority_class: str


@dataclass(frozen=True, slots=True)
class RecommendationAssessment:
    recommendation_id: str
    title: str
    status: str
    reason: str
    finding_id: str | None
    remediation_group_id: str | None
    confidence: str | None
    priority_class: str | None


@dataclass(frozen=True, slots=True)
class QualityBundle:
    audit_id: str
    generated_at: str
    health_checks: tuple[HealthCheck, ...]
    finding_assessments: tuple[FindingAssessment, ...]
    coverage_map: tuple[dict[str, Any], ...]
    recommendation_assessments: tuple[RecommendationAssessment, ...]
    methodology: dict[str, str]

    @property
    def health_status(self) -> str:
        statuses = {item.status for item in self.health_checks}
        if "FAIL" in statuses:
            return "FAIL"
        if "WARNING" in statuses:
            return "WARNING"
        return "PASS"

    @property
    def top_priorities(self) -> tuple[FindingAssessment, ...]:
        return tuple(sorted(self.finding_assessments, key=lambda item: (-item.operational_priority, item.rule_id, item.finding_id))[:10])


def analyze_quality(audit_workspace: str | Path) -> QualityBundle:
    workspace = Path(audit_workspace)
    connection = _ro(workspace / "audit.db")
    try:
        tables = _tables(connection)
        audit = connection.execute("SELECT * FROM audits ORDER BY rowid LIMIT 1").fetchone()
        if audit is None:
            raise ValueError("audit metadata unavailable")
        audit_id = str(audit["audit_id"])
        page_map = _page_map(connection, audit_id)
        executions = _latest_executions(connection, audit_id) if "rule_executions" in tables else {}
        health = _health_checks(workspace, connection, tables, audit, audit_id, page_map)
        findings = _finding_assessments(connection, tables, audit_id, page_map, executions)
        coverage = _coverage_map(executions, page_map)
        recommendations = _recommendation_assessments(connection, tables, audit_id, findings, executions)
        return QualityBundle(
            audit_id=audit_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            health_checks=tuple(health),
            finding_assessments=tuple(findings),
            coverage_map=tuple(coverage),
            recommendation_assessments=tuple(recommendations),
            methodology={
                "audit_health": "RASAI-AUDIT-HEALTH-001",
                "evidence_confidence": "RASAI-EVIDENCE-CONFIDENCE-001",
                "operational_priority": "RASAI-QUALITY-PRIORITY-001",
                "coverage_map": "RASAI-COVERAGE-MAP-001",
                "recommendation_validation": "RASAI-RECOMMENDATION-VALIDATION-001",
                "scoring_impact": "NONE",
            },
        )
    finally:
        connection.close()


def _health_checks(
    workspace: Path,
    connection: sqlite3.Connection,
    tables: set[str],
    audit: sqlite3.Row,
    audit_id: str,
    page_map: dict[str, str],
) -> list[HealthCheck]:
    out: list[HealthCheck] = []
    integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    out.append(_health(
        "AUDIT-DB-INTEGRITY", "PASS" if integrity.casefold() == "ok" else "FAIL",
        "CRITICAL", "Integridade do audit.db",
        "SQLite integrity_check concluído." if integrity.casefold() == "ok" else f"SQLite integrity_check={integrity}",
        {"integrity_check": integrity},
    ))

    audit_status = str(audit["status"] or "UNKNOWN").upper()
    complete = audit_status in {"COMPLETED", "COMPLETE", "COMPLETE_WITH_LIMITATIONS"}
    out.append(_health(
        "AUDIT-COMPLETION", "PASS" if complete else "WARNING", "HIGH", "Conclusão da auditoria",
        f"status={audit_status}; completion_status={_row_value(audit, 'completion_status') or '-'}",
        {"status": audit_status, "completion_status": _row_value(audit, "completion_status")},
    ))

    pages = len(page_map)
    if "page_snapshots" in tables and pages:
        rows = connection.execute(
            """SELECT ps.page_id,UPPER(ps.device) device FROM page_snapshots ps
               JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=?""",
            (audit_id,),
        ).fetchall()
        devices = sorted({str(row["device"]) for row in rows if row["device"]})
        actual = len({(str(row["page_id"]), str(row["device"])) for row in rows})
        expected = pages * max(1, len(devices))
        ratio = actual / expected if expected else 0.0
        status = "PASS" if ratio >= 1.0 else ("WARNING" if ratio >= 0.8 else "FAIL")
        out.append(_health(
            "AUDIT-SNAPSHOT-COVERAGE", status, "HIGH", "Cobertura de snapshots",
            f"{actual}/{expected} combinações URL×device observadas ({ratio*100:.1f}%).",
            {"pages": pages, "devices": devices, "actual": actual, "expected": expected, "ratio": ratio},
        ))
    else:
        out.append(_health(
            "AUDIT-SNAPSHOT-COVERAGE", "FAIL" if pages else "WARNING", "HIGH", "Cobertura de snapshots",
            "Nenhum snapshot persistido." if pages else "Nenhuma página persistida.", {"pages": pages},
        ))

    if "rule_executions" in tables:
        columns = _columns(connection, "rule_executions")
        error_expr = "error" if "error" in columns else "NULL"
        rows = connection.execute(
            f"SELECT result,{error_expr} error FROM rule_executions WHERE audit_id=?", (audit_id,)
        ).fetchall()
        total = len(rows)
        errors = sum(bool(row["error"]) or str(row["result"] or "").upper() == "ERROR" for row in rows)
        ratio = errors / total if total else 0.0
        status = "PASS" if errors == 0 and total else ("WARNING" if ratio <= 0.05 and total else "FAIL")
        out.append(_health(
            "AUDIT-RULE-EXECUTION-QUALITY", status, "HIGH", "Qualidade da execução das regras",
            f"{errors}/{total} execuções com erro ({ratio*100:.1f}%).",
            {"executions": total, "errors": errors, "error_ratio": ratio},
        ))

    if "scores" in tables:
        rows = connection.execute(
            "SELECT scoring_version,coverage,consolidation_status,dimension FROM scores WHERE audit_id=?",
            (audit_id,),
        ).fetchall()
        versions = sorted({str(row["scoring_version"]) for row in rows if row["scoring_version"]})
        coverages = [float(row["coverage"]) for row in rows if row["coverage"] is not None and str(row["dimension"]) != "OVERALL_READINESS"]
        minimum = min(coverages, default=0.0)
        current_only = bool(versions) and all(version == "SCORE-GEO-003" for version in versions)
        status = "PASS" if current_only and minimum >= 0.8 else "WARNING"
        out.append(_health(
            "AUDIT-SCORING-COVERAGE", status, "MEDIUM", "Cobertura e versão de scoring",
            f"versions={versions or ['-']}; minimum_dimension_coverage={minimum:.3f}.",
            {"versions": versions, "minimum_dimension_coverage": minimum},
        ))

    artifact_total, artifact_missing = _artifact_integrity(workspace, connection, tables, audit_id)
    artifact_status = "PASS" if artifact_missing == 0 else ("WARNING" if artifact_missing <= max(1, artifact_total // 20) else "FAIL")
    out.append(_health(
        "AUDIT-ARTIFACT-INTEGRITY", artifact_status, "HIGH", "Integridade de artifacts referenciados",
        f"{artifact_missing}/{artifact_total} referências de arquivo verificáveis estão ausentes.",
        {"checked": artifact_total, "missing": artifact_missing},
    ))

    index = workspace / "report" / "index.html"
    out.append(_health(
        "AUDIT-REPORT-ENTRYPOINT", "PASS" if index.is_file() else "WARNING", "MEDIUM", "Entrada do relatório HTML",
        "report/index.html presente." if index.is_file() else "report/index.html não encontrado neste workspace.",
        {"path": index.relative_to(workspace).as_posix()},
    ))

    out.extend(_observability_health(workspace))
    return out


def _observability_health(workspace: Path) -> list[HealthCheck]:
    database = workspace / "observability.db"
    if not database.is_file():
        return [_health(
            "OBS-SIDECAR", "PASS", "INFO", "Sidecar observacional",
            "observability.db não existe; observability é opcional e sua ausência não reduz readiness.", {"present": False},
        )]
    connection = _ro(database)
    try:
        tables = _tables(connection)
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        out = [_health(
            "OBS-SIDECAR-INTEGRITY", "PASS" if integrity.casefold() == "ok" else "FAIL", "HIGH",
            "Integridade do observability.db", f"SQLite integrity_check={integrity}.", {"integrity_check": integrity},
        )]
        if "search_performance" in tables:
            pk = [
                str(row[1]) for row in sorted(connection.execute("PRAGMA table_info(search_performance)"), key=lambda item: int(item[5]))
                if int(row[5]) > 0
            ]
            out.append(_health(
                "OBS-COMPOSITE-IDENTITY", "PASS" if pk == ["record_id", "dataset_id"] or pk == ["dataset_id", "record_id"] else "FAIL",
                "CRITICAL", "Identidade de registros observacionais",
                f"Primary key observada={pk}; esperado record_id namespaced por dataset.", {"primary_key": pk},
            ))
        if "datasets" in tables:
            datasets = [dict(row) for row in connection.execute("SELECT * FROM datasets ORDER BY source_type,period_start,period_end,collected_at")]
            overlaps = _dataset_overlaps(datasets)
            out.append(_health(
                "OBS-DATASET-OVERLAP", "WARNING" if overlaps else "PASS", "MEDIUM", "Sobreposição de datasets",
                f"{len(overlaps)} sobreposição(ões) temporal(is) detectada(s); análises devem selecionar dataset, não somar períodos sobrepostos."
                if overlaps else "Nenhuma sobreposição temporal detectada entre datasets da mesma fonte.",
                {"datasets": len(datasets), "overlaps": overlaps[:20]},
            ))
            missing = 0
            hash_mismatch = 0
            for item in datasets:
                relative = str(item.get("artifact_path") or "")
                path = workspace / relative
                if not path.is_file():
                    missing += 1
                    continue
                expected = str(item.get("artifact_sha256") or "")
                if expected:
                    actual = hashlib.sha256(path.read_bytes()).hexdigest()
                    if actual != expected:
                        hash_mismatch += 1
            status = "PASS" if missing == 0 and hash_mismatch == 0 else "FAIL"
            out.append(_health(
                "OBS-ARTIFACT-PROVENANCE", status, "HIGH", "Proveniência dos datasets observacionais",
                f"artifacts ausentes={missing}; hash divergente={hash_mismatch}.",
                {"missing_artifacts": missing, "hash_mismatch": hash_mismatch},
            ))
        return out
    finally:
        connection.close()


def _finding_assessments(
    connection: sqlite3.Connection,
    tables: set[str],
    audit_id: str,
    page_map: dict[str, str],
    executions: dict[tuple[str, str | None, str | None], sqlite3.Row],
) -> list[FindingAssessment]:
    if "findings" not in tables:
        return []
    rows = connection.execute("SELECT * FROM findings WHERE audit_id=?", (audit_id,)).fetchall()
    selector_counts: Counter[tuple[str, str]] = Counter()
    rule_counts: Counter[str] = Counter()
    parsed: list[tuple[sqlite3.Row, str | None]] = []
    for row in rows:
        rule_id = str(_row_value(row, "rule_id") or "UNKNOWN")
        selector = _selector(_json(_row_value(row, "observed_value"), {}))
        rule_counts[rule_id] += 1
        if selector:
            selector_counts[(rule_id, selector)] += 1
        parsed.append((row, selector))

    output: list[FindingAssessment] = []
    for index, (row, selector) in enumerate(parsed, 1):
        finding_id = str(_row_value(row, "finding_id") or f"FINDING-{index:08d}")
        rule_id = str(_row_value(row, "rule_id") or "UNKNOWN")
        page_id = _optional_text(_row_value(row, "page_id"))
        device = _optional_text(_row_value(row, "device"))
        severity = str(_row_value(row, "severity") or "INFO").upper()
        status = str(_row_value(row, "status") or "OPEN").upper()
        title = str(_row_value(row, "title") or rule_id)
        execution = executions.get((rule_id, page_id, device)) or executions.get((rule_id, page_id, None))
        confidence, reasons, provenance = _evidence_confidence(row, rule_id, execution)
        scope_count = selector_counts[(rule_id, selector)] if selector else rule_counts[rule_id]
        effort = _effort(rule_id, selector, scope_count)
        score = _priority(severity, confidence, scope_count, effort)
        output.append(
            FindingAssessment(
                finding_id=finding_id,
                rule_id=rule_id,
                severity=severity,
                status=status,
                url=page_map.get(page_id or ""),
                device=device,
                title=title,
                evidence_confidence=confidence,
                confidence_reasons=tuple(reasons),
                provenance=provenance,
                scope_count=scope_count,
                effort=effort,
                operational_priority=score,
                priority_class=_priority_class(score),
            )
        )
    return output


def _evidence_confidence(row: sqlite3.Row, rule_id: str, execution: sqlite3.Row | None) -> tuple[str, list[str], str]:
    deterministic = rule_id in _DETERMINISTIC_RULES
    provenance = "DETERMINISTIC_RULE" if deterministic else "SEMANTIC_OR_DERIVED_RULE"
    reasons: list[str] = [provenance]
    if execution is None:
        reasons.append("RULE_EXECUTION_NOT_RESOLVED")
        return "LOW", reasons, provenance
    error = _row_value(execution, "error")
    result = str(_row_value(execution, "result") or "UNKNOWN").upper()
    if error or result in {"ERROR", "UNKNOWN"}:
        reasons.append("EXECUTION_INCONCLUSIVE")
        return "LOW", reasons, provenance
    evidence_ids = _json(_row_value(execution, "evidence_ids"), [])
    evidence_count = len(evidence_ids) if isinstance(evidence_ids, list) else 0
    if evidence_count:
        reasons.append(f"PERSISTED_EVIDENCE:{evidence_count}")
    else:
        reasons.append("NO_EXPLICIT_EVIDENCE_IDS")
    if deterministic and evidence_count:
        return "HIGH", reasons, provenance
    if deterministic or evidence_count:
        return "MEDIUM", reasons, provenance
    return "LOW", reasons, provenance


def _coverage_map(
    executions: dict[tuple[str, str | None, str | None], sqlite3.Row],
    page_map: dict[str, str],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for (rule_id, page_id, device), row in executions.items():
        if not page_id or page_id not in page_map:
            continue
        grouped[(page_id, device or "GLOBAL")][_rule_domain(rule_id)].append(str(_row_value(row, "result") or "UNKNOWN").upper())
    output: list[dict[str, Any]] = []
    domains = ("TECHNICAL_ACCESS", "CONTENT_RENDERING", "SEMANTIC_ENTITY", "ANSWER_EVIDENCE_INTENT", "GOVERNANCE")
    for (page_id, device), states in sorted(grouped.items(), key=lambda item: (page_map.get(item[0][0], ""), item[0][1])):
        row: dict[str, Any] = {"url": page_map.get(page_id), "device": device}
        for domain in domains:
            values = states.get(domain, [])
            row[domain] = _worst(values) if values else "NOT_OBSERVED"
            row[f"{domain}_count"] = len(values)
        output.append(row)
    return output


def _recommendation_assessments(
    connection: sqlite3.Connection,
    tables: set[str],
    audit_id: str,
    findings: list[FindingAssessment],
    executions: dict[tuple[str, str | None, str | None], sqlite3.Row],
) -> list[RecommendationAssessment]:
    if "recommendations" not in tables:
        return []
    finding_by_id = {item.finding_id: item for item in findings}
    groups = {
        str(row[0]) for row in connection.execute("SELECT group_id FROM remediation_groups WHERE audit_id=?", (audit_id,)).fetchall()
    } if "remediation_groups" in tables else set()
    rows = connection.execute("SELECT * FROM recommendations WHERE audit_id=? ORDER BY priority_score DESC,recommendation_id", (audit_id,)).fetchall()
    output: list[RecommendationAssessment] = []
    for row in rows:
        rec_id = str(row["recommendation_id"])
        finding_id = _optional_text(_row_value(row, "finding_id"))
        group_id = _optional_text(_row_value(row, "remediation_group_id"))
        title = str(_row_value(row, "title") or rec_id)
        confidence = _optional_text(_row_value(row, "confidence"))
        priority_class = _optional_text(_row_value(row, "priority_class"))
        status = "SUPPORTED_BY_PERSISTED_EVIDENCE"
        reason = "Reference exists and no contradiction was detected in the persisted audit state."
        if finding_id:
            finding = finding_by_id.get(finding_id)
            if finding is None:
                status, reason = "INVALID_REFERENCE", "Referenced finding is absent from the current audit."
            elif finding.status in {"RESOLVED", "CLOSED", "DISMISSED"}:
                status, reason = "STALE_RESOLVED", "Referenced finding is already resolved/closed/dismissed."
            elif finding.evidence_confidence == "LOW" and str(confidence or "").upper() == "HIGH":
                status, reason = "CONFIDENCE_MISMATCH", "Recommendation confidence exceeds the evidence confidence derived for its finding."
        elif group_id:
            if group_id not in groups:
                status, reason = "INVALID_REFERENCE", "Referenced remediation group is absent from the current audit."
            else:
                status, reason = "SUPPORTED_BY_GROUP", "Referenced remediation group exists; recommendation correctness still requires human validation."
        else:
            status, reason = "INVALID_REFERENCE", "Recommendation has neither finding_id nor remediation_group_id."
        output.append(
            RecommendationAssessment(
                recommendation_id=rec_id,
                title=title,
                status=status,
                reason=reason,
                finding_id=finding_id,
                remediation_group_id=group_id,
                confidence=confidence,
                priority_class=priority_class,
            )
        )
    return output


def _latest_executions(connection: sqlite3.Connection, audit_id: str) -> dict[tuple[str, str | None, str | None], sqlite3.Row]:
    rows = connection.execute("SELECT rowid,* FROM rule_executions WHERE audit_id=? ORDER BY rowid", (audit_id,)).fetchall()
    latest: dict[tuple[str, str | None, str | None], sqlite3.Row] = {}
    for row in rows:
        latest[(str(_row_value(row, "rule_id")), _optional_text(_row_value(row, "page_id")), _optional_text(_row_value(row, "device")))] = row
    return latest


def _page_map(connection: sqlite3.Connection, audit_id: str) -> dict[str, str]:
    return {
        str(row["page_id"]): str(row["normalized_url"])
        for row in connection.execute("SELECT page_id,normalized_url FROM pages WHERE audit_id=?", (audit_id,)).fetchall()
    }


def _artifact_integrity(workspace: Path, connection: sqlite3.Connection, tables: set[str], audit_id: str) -> tuple[int, int]:
    if "page_snapshots" not in tables:
        return 0, 0
    columns = [column for column in _columns(connection, "page_snapshots") if column.endswith("_ref")]
    if not columns:
        return 0, 0
    rows = connection.execute(
        f"SELECT {','.join(columns)} FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=?",
        (audit_id,),
    ).fetchall()
    checked = 0
    missing = 0
    for row in rows:
        for column in columns:
            value = _optional_text(row[column])
            if not value or not _looks_like_file_reference(value):
                continue
            checked += 1
            candidate = workspace / value
            if not candidate.is_file():
                missing += 1
    return checked, missing


def _dataset_overlaps(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_source[str(item.get("source_type") or "UNKNOWN")].append(item)
    for source, datasets in by_source.items():
        ordered = sorted(datasets, key=lambda item: str(item.get("period_start") or ""))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1:]:
                ls, le = str(left.get("period_start") or ""), str(left.get("period_end") or "")
                rs, re = str(right.get("period_start") or ""), str(right.get("period_end") or "")
                if not all((ls, le, rs, re)):
                    continue
                if max(ls, rs) <= min(le, re):
                    output.append({"source": source, "left": str(left.get("dataset_id")), "right": str(right.get("dataset_id"))})
    return output


def _effort(rule_id: str, selector: str | None, scope_count: int) -> str:
    if selector and scope_count >= 2:
        return "LOW"
    try:
        number = int(rule_id.rsplit("-", 1)[-1])
    except ValueError:
        return "MEDIUM"
    if 28 <= number <= 49:
        return "HIGH"
    if number in {1, 2, 3, 4, 13, 14, 15, 50, 51}:
        return "MEDIUM"
    return "LOW"


def _priority(severity: str, confidence: str, scope_count: int, effort: str) -> float:
    severity_component = (_SEVERITY_WEIGHT.get(severity, 1) / 5.0) * 60.0
    scope_component = (min(max(scope_count, 1), 5) / 5.0) * 20.0
    confidence_component = _CONFIDENCE_POINTS.get(confidence, 8.0)
    return round(min(100.0, (severity_component + scope_component + confidence_component) * _EFFORT_FACTOR.get(effort, 0.85)), 2)


def _priority_class(score: float) -> str:
    if score >= 80:
        return "P0"
    if score >= 60:
        return "P1"
    if score >= 40:
        return "P2"
    return "P3"


def _rule_domain(rule_id: str) -> str:
    try:
        number = int(rule_id.rsplit("-", 1)[-1])
    except ValueError:
        return "GOVERNANCE"
    if 1 <= number <= 18:
        return "TECHNICAL_ACCESS"
    if 19 <= number <= 27:
        return "CONTENT_RENDERING"
    if 28 <= number <= 37:
        return "SEMANTIC_ENTITY"
    if 38 <= number <= 49:
        return "ANSWER_EVIDENCE_INTENT"
    return "GOVERNANCE"


def _worst(values: list[str]) -> str:
    if not values:
        return "NOT_OBSERVED"
    return max(values, key=lambda value: _RESULT_RANK.get(value, 2))


def _selector(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("selector", "css_selector", "element_selector"):
        text = _optional_text(value.get(key))
        if text:
            return text
    return None


def _looks_like_file_reference(value: str) -> bool:
    lowered = value.casefold()
    return "/" in value or "\\" in value or lowered.endswith((".html", ".json", ".txt", ".xml", ".gz", ".har"))


def _health(code: str, status: str, severity: str, title: str, detail: str, evidence: dict[str, Any]) -> HealthCheck:
    return HealthCheck(code, status, severity, title, detail, evidence)


def _ro(database: Path) -> sqlite3.Connection:
    if not database.is_file():
        raise FileNotFoundError(database)
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _row_value(row: sqlite3.Row, key: str) -> Any:
    return row[key] if key in row.keys() else None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
