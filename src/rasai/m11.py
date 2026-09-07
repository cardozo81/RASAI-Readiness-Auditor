"""M11/M14/M15/M16/M17 - Static HTML Report orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
import re
import sqlite3
from typing import Any

from rasai.m14_persistence import M14Persistence
from rasai.m14_reporting import TEMPLATE_VERSION, _metric, new_m14_report_record
from rasai.m15_reporting import write_remediation_report
from rasai.m15_style_overrides import SCORE_LAYOUT_CSS
from rasai.m16_root_cause import materialize_root_causes
from rasai.m17_duplicate_remediation import refine_br_geo_051_html
from rasai.m17_precision import materialize_m17_precision
from rasai.m17_reporting import M17RemediationReportBuilder, M17ReportBuilder
from rasai.m19_reporting import refine_score_applicability_html
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai import reporting as reporting_module
from rasai.reporting import ReportPersistence, _redact, write_report
from rasai.remediation import recipe_for

# REPORT-GEO-003 remains the page-oriented report contract. M17 tightens the
# remediation projection; SCORE-GEO-002 only refines applicability aggregation.
reporting_module.TEMPLATE_VERSION = TEMPLATE_VERSION


def _ai_usage_status(semantic: list[sqlite3.Row]) -> str:
    """Return the human state of external semantic AI for this audit report."""

    providers = {str(row["provider"]).upper() for row in semantic if row["provider"]}
    if "OPENAI" in providers:
        return "SIM"
    if "UNAVAILABLE" in providers:
        return "TENTATIVA SEM SUCESSO"
    return "NÃO"


def _configured_semantic_provider(audit: sqlite3.Row, semantic: list[sqlite3.Row]) -> str:
    """Resolve provider configuration independently from provider call outcome."""

    capabilities = tuple(str(item) for item in _json_list(audit["capabilities"]))
    for capability in capabilities:
        if capability.startswith("semantic_provider:"):
            return capability.split(":", 1)[1].strip().upper() or "NÃO INFORMADO"

    providers = {str(row["provider"]).upper() for row in semantic if row["provider"]}
    if "OPENAI" in providers or "UNAVAILABLE" in providers:
        return "OPENAI"
    if providers:
        return ", ".join(sorted(providers))
    return "NÃO INFORMADO"


class _PersistedInputAwareReportBuilder(M17ReportBuilder):
    """Use raw operator input counts while rendering the deduplicated URL set."""

    def __init__(self, workspace: AuditWorkspace) -> None:
        super().__init__()
        self._workspace = workspace
        self._input_summary = None

    def build(self, *, audit_id: str, workspace: AuditWorkspace) -> str:
        with M14Persistence(workspace) as m14:
            self._input_summary = m14.get_input_summary(audit_id)
        html = super().build(audit_id=audit_id, workspace=workspace)
        html = html.replace("</style>", f"{SCORE_LAYOUT_CSS}</style>", 1)

        # Keep the old report contract traceable without restoring the former
        # always-expanded duplicate remediation section. The compatibility
        # details are collapsed and backed by the same persisted findings and
        # deterministic recipes used by remediation.html.
        trace = _collapsed_trace_details(audit_id, workspace)
        anchor = '<p class="m17-link"><a href="remediation.html">Abrir achados e remediações agrupados →</a></p>'
        if trace and anchor in html:
            html = html.replace(anchor, trace + anchor, 1)

        # An empty audit has no page context to which external best-practice
        # references can be applied. Keep labels but remove external hrefs in
        # that degenerate report, preserving the long-standing self-contained
        # empty-report invariant. Real audited page universes keep the links.
        connection = sqlite3.connect(workspace.database)
        try:
            page_count = connection.execute(
                "SELECT COUNT(*) FROM pages WHERE audit_id = ?", (audit_id,)
            ).fetchone()[0]
        finally:
            connection.close()
        if page_count == 0:
            html = re.sub(
                r"<a href='https?://[^']+' target='_blank' rel='noopener'>(.*?)</a>",
                r"\1",
                html,
                flags=re.DOTALL,
            )
        html = refine_br_geo_051_html(html)
        return refine_score_applicability_html(
            html,
            audit_id=audit_id,
            workspace=workspace,
        )

    def _executive(
        self,
        *,
        audit: sqlite3.Row,
        domain: str,
        target_type: str,
        supplied_count: int,
        audited_count: int,
        semantic: list[sqlite3.Row],
    ) -> str:
        summary = self._input_summary
        if summary is not None:
            supplied_count = summary.supplied_count
            target_type = summary.input_mode

        html = super()._executive(
            audit=audit,
            domain=domain,
            target_type=target_type,
            supplied_count=supplied_count,
            audited_count=audited_count,
            semantic=semantic,
        )

        providers = sorted({str(row["provider"]) for row in semantic if row["provider"]})
        models = sorted({str(row["model"]) for row in semantic if row["model"]})
        legacy_ai_used = any(provider.casefold() not in {"none", "fallback", ""} for provider in providers)
        usage_status = _ai_usage_status(semantic)
        configured_provider = _configured_semantic_provider(audit, semantic)

        if configured_provider == "OPENAI" and usage_status == "TENTATIVA SEM SUCESSO":
            provider_display = "OPENAI - CHAMADA INDISPONÍVEL"
        elif configured_provider == "OPENAI" and usage_status == "SIM" and "UNAVAILABLE" in {item.upper() for item in providers}:
            provider_display = "OPENAI - SUCESSO PARCIAL"
        else:
            provider_display = configured_provider

        if models:
            model_display = ", ".join(models)
        elif configured_provider == "OPENAI":
            # CLI only constructs OpenAIProvider when a model is configured. A
            # failed HTTP call, however, has no response model to persist. Do
            # not mislabel that state as "not applicable".
            model_display = "CONFIGURADO · NÃO CONFIRMADO PELA API"
        else:
            model_display = "NÃO APLICÁVEL"

        html = html.replace(
            _metric("Uso de IA", "SIM" if legacy_ai_used else "NÃO"),
            _metric("Uso de IA", usage_status),
            1,
        )
        html = html.replace(
            _metric("Provider", ", ".join(providers) or "NÃO INFORMADO"),
            _metric("Provider configurado", provider_display),
            1,
        )
        html = html.replace(
            _metric("Modelo", ", ".join(models) or "NÃO APLICÁVEL"),
            _metric("Modelo", model_display),
            1,
        )
        return html


def _collapsed_trace_details(audit_id: str, workspace: AuditWorkspace) -> str:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        findings = list(connection.execute(
            """
            SELECT f.*, re.observed_value AS execution_observed_value
            FROM findings f JOIN rule_executions re ON re.rule_execution_id=f.rule_execution_id
            WHERE f.audit_id=? ORDER BY f.rule_id,f.finding_id
            """,
            (audit_id,),
        ).fetchall())
        groups = _optional_rows(
            connection,
            "SELECT group_id,affected_findings FROM remediation_groups WHERE audit_id=?",
            (audit_id,),
        )
        recommendations = _optional_rows(
            connection,
            "SELECT remediation_group_id,title FROM recommendations WHERE audit_id=? ORDER BY recommendation_id",
            (audit_id,),
        )
        evidence_rows = list(connection.execute(
            "SELECT evidence_id,observed_value FROM evidence WHERE audit_id=? ORDER BY evidence_id",
            (audit_id,),
        ).fetchall())
    finally:
        connection.close()

    if not findings:
        return ""

    evidence_by_id = {str(row["evidence_id"]): row for row in evidence_rows}
    titles_by_group: dict[str, list[str]] = {}
    for row in recommendations:
        titles_by_group.setdefault(str(row["remediation_group_id"]), []).append(str(row["title"]))
    titles_by_finding: dict[str, list[str]] = {}
    for row in groups:
        group_titles = titles_by_group.get(str(row["group_id"]), [])
        for finding_id in _json_list(row["affected_findings"]):
            titles_by_finding.setdefault(str(finding_id), []).extend(group_titles)

    blocks: list[str] = []
    for finding in findings:
        rule_id = str(finding["rule_id"])
        finding_id = str(finding["finding_id"])
        recipe = recipe_for(rule_id)
        observed = _json_object(finding["execution_observed_value"])
        problem = _compat_problem_description(rule_id, observed, str(finding["title"]))
        recommendation_titles = tuple(dict.fromkeys(titles_by_finding.get(finding_id, [])))
        recommendations_html = "".join(
            f"<li>{escape(title)}</li>" for title in recommendation_titles
        )
        example = (
            f"<h5>Estrutura recomendada - exemplo</h5><pre><code>{escape(recipe.example)}</code></pre>"
            if recipe.example else ""
        )
        acceptance = "".join(f"<li>{escape(item)}</li>" for item in recipe.acceptance)
        validation = "".join(f"<li>{escape(item)}</li>" for item in recipe.validation)
        recommendation_block = (
            f"<h5>Recomendação técnica registrada</h5><ul>{recommendations_html}</ul>"
            if recommendations_html else ""
        )
        evidence_block = _sanitized_evidence_block(
            tuple(str(item) for item in _json_list(finding["evidence_ids"])),
            evidence_by_id,
        )
        blocks.append(
            "<details class='m17-compat-trace'>"
            f"<summary>Rastreabilidade técnica compatível · {escape(rule_id)}</summary>"
            f"<p><strong>Problema encontrado:</strong> {escape(problem)}</p>"
            f"<p><strong>Recipe técnica:</strong> {escape(recipe.title)}</p>"
            f"{recommendation_block}{evidence_block}{example}"
            f"<h5>Critério de aceite</h5><ul>{acceptance}</ul>"
            f"<h5>Como revalidar</h5><ol>{validation}</ol>"
            "</details>"
        )
    return "<div class='m17-compat-traces'>" + "".join(blocks) + "</div>"


def _sanitized_evidence_block(
    evidence_ids: tuple[str, ...],
    evidence_by_id: dict[str, sqlite3.Row],
) -> str:
    entries: list[str] = []
    for evidence_id in evidence_ids:
        row = evidence_by_id.get(evidence_id)
        if row is None:
            continue
        raw = row["observed_value"]
        try:
            parsed = json.loads(str(raw)) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = str(raw)
        sanitized = _redact(parsed)
        if isinstance(sanitized, (dict, list, tuple)):
            rendered = json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True)
        else:
            rendered = str(sanitized)
        entries.append(
            f"<div class='evidence'><strong>{escape(evidence_id)}</strong>"
            f"<pre><code>{escape(rendered)}</code></pre></div>"
        )
    if not entries:
        return ""
    return "<h5>Evidência sanitizada</h5>" + "".join(entries)


def _compat_problem_description(rule_id: str, observed: dict[str, Any], title: str) -> str:
    if rule_id == "BR-GEO-013":
        canonicals = observed.get("canonicals")
        declared = observed.get("declared")
        if canonicals == [] or declared == []:
            return "Nenhuma declaração canonical válida foi encontrada."
    return title


def _optional_rows(
    connection: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...],
) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise


def _json_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


@dataclass(frozen=True, slots=True)
class M11ExecutionResult:
    report_id: str
    file_path: str
    template_version: str
    remediation_file_path: str = "remediation.html"


def execute_m11(
    *,
    audit_id: str,
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
) -> M11ExecutionResult:
    audit = persistence.audits.get(audit_id)
    if audit is None:
        raise ValueError(f"audit not found: {audit_id}")

    # M16 materializes the evidence-backed root cause. M17 then adds a separate
    # precision projection (reason code, observed element state and target
    # selector) so old audit databases remain compatible and no M16 record is
    # destructively rewritten.
    materialize_root_causes(audit_id=audit_id, workspace=workspace)
    materialize_m17_precision(audit_id=audit_id, workspace=workspace)

    html = _PersistedInputAwareReportBuilder(workspace).build(
        audit_id=audit_id,
        workspace=workspace,
    )
    path = write_report(workspace=workspace, html=html)

    remediation_html = M17RemediationReportBuilder().build(
        audit_id=audit_id,
        workspace=workspace,
    )
    remediation_html = refine_br_geo_051_html(remediation_html)
    remediation_path = write_remediation_report(workspace=workspace, html=remediation_html)

    record = new_m14_report_record(
        audit_id=audit_id,
        auditor_version=audit.auditor_version,
        file_path=path.name,
    )
    with ReportPersistence(workspace) as reports:
        reports.add(record)
        reopened = reports.get(record.report_id)
        if reopened != record:
            raise RuntimeError("report metadata is not reproducible after persistence")

    return M11ExecutionResult(
        report_id=record.report_id,
        file_path=record.file_path,
        template_version=record.template_version,
        remediation_file_path=remediation_path.name,
    )
