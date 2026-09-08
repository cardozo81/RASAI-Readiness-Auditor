"""Static, self-contained Actionable GEO Remediation Report from persisted audit data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from rasai.domain import AuditMode, new_id, utc_now
from rasai.persistence import AuditWorkspace
from rasai.remediation import RemediationRecipe, recipe_for


TEMPLATE_VERSION = "REPORT-GEO-002"

_DIMENSION_LABELS = {
    "TECHNICAL_ACCESSIBILITY": "Acessibilidade Técnica",
    "INDEXABILITY": "Capacidade de Indexação",
    "CONTENT_EXTRACTABILITY": "Extração de Conteúdo",
    "SEMANTIC_STRUCTURE": "Estrutura Semântica",
    "ENTITY_CLARITY": "Clareza de Entidades",
    "STRUCTURED_DATA": "Dados Estruturados",
    "ANSWERABILITY": "Capacidade de Resposta",
    "CITATION_READINESS": "Preparação para Citação",
    "EVIDENCE_TRUST": "Evidências e Confiabilidade",
    "INTENT_COVERAGE": "Cobertura de Intenções",
    "OVERALL_READINESS": "Readiness Search & AI",
}
_STATUS_LABELS = {
    "PASS": "APROVADO",
    "FAIL": "PROBLEMA",
    "WARNING": "ALERTA",
    "UNKNOWN": "NÃO DETERMINADO",
    "NOT_APPLICABLE": "NÃO APLICÁVEL",
    "ERROR": "ERRO DE ANÁLISE",
    "CONSOLIDATED": "CONSOLIDADO",
    "PARTIAL": "PARCIAL",
    "NOT_CONSOLIDATED": "NÃO CONSOLIDADO",
    "HIGH": "ALTA",
    "MEDIUM": "MÉDIA",
    "LOW": "BAIXA",
    "UNAVAILABLE": "INDISPONÍVEL",
}
_PRIORITY_LABELS = {
    "P0": "P0 - blocker crítico",
    "P1": "P1 - prioridade muito alta",
    "P2": "P2 - prioridade alta",
    "P3": "P3 - prioridade média",
    "P4": "P4 - prioridade baixa",
    "INFO": "Informacional",
}
_CATEGORY_DIMENSION = {
    "TECHNICAL_ACCESSIBILITY": "TECHNICAL_ACCESSIBILITY",
    "DISCOVERY": "TECHNICAL_ACCESSIBILITY",
    "ROBOTS": "TECHNICAL_ACCESSIBILITY",
    "INDEXABILITY": "INDEXABILITY",
    "CANONICAL": "INDEXABILITY",
    "CONTENT_EXTRACTABILITY": "CONTENT_EXTRACTABILITY",
    "JAVASCRIPT_RENDERING": "CONTENT_EXTRACTABILITY",
    "SEMANTIC_STRUCTURE": "SEMANTIC_STRUCTURE",
    "ENTITY_CLARITY": "ENTITY_CLARITY",
    "STRUCTURED_DATA": "STRUCTURED_DATA",
    "ANSWERABILITY": "ANSWERABILITY",
    "CITATION_READINESS": "CITATION_READINESS",
    "EVIDENCE_TRUST": "EVIDENCE_TRUST",
    "INTENT_COVERAGE": "INTENT_COVERAGE",
}
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|password|passwd|secret|access[_-]?token|bearer|credential)",
    re.I,
)
_MAX_PAGES_RE = re.compile(r"MAX_PAGES_REACHED:discovered=(\d+);audited=(\d+)")


@dataclass(frozen=True, slots=True)
class ReportRecord:
    report_id: str
    audit_id: str
    format: str
    status: str
    generated_at: datetime
    template_version: str
    auditor_version: str
    file_path: str


class ReportPersistence:
    """Persist report metadata; HTML remains a projection, never primary data."""

    def __init__(self, workspace: AuditWorkspace) -> None:
        self._connection = sqlite3.connect(workspace.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "ReportPersistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    format TEXT NOT NULL,
                    status TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    template_version TEXT NOT NULL,
                    auditor_version TEXT NOT NULL,
                    file_path TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reports_audit_generated
                    ON reports(audit_id, generated_at DESC);
                """
            )

    def add(self, report: ReportRecord) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO reports VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    report.report_id,
                    report.audit_id,
                    report.format,
                    report.status,
                    report.generated_at.isoformat(),
                    report.template_version,
                    report.auditor_version,
                    report.file_path,
                ),
            )

    def get(self, report_id: str) -> ReportRecord | None:
        row = self._connection.execute(
            "SELECT * FROM reports WHERE report_id = ?", (report_id,)
        ).fetchone()
        if row is None:
            return None
        return ReportRecord(
            report_id=row["report_id"],
            audit_id=row["audit_id"],
            format=row["format"],
            status=row["status"],
            generated_at=datetime.fromisoformat(row["generated_at"]),
            template_version=row["template_version"],
            auditor_version=row["auditor_version"],
            file_path=row["file_path"],
        )


class ReportBuilder:
    """Render the actionable report exclusively from persisted audit state."""

    def build(self, *, audit_id: str, workspace: AuditWorkspace) -> str:
        connection = sqlite3.connect(workspace.database)
        connection.row_factory = sqlite3.Row
        try:
            audit = connection.execute(
                "SELECT * FROM audits WHERE audit_id = ?", (audit_id,)
            ).fetchone()
            if audit is None:
                raise ValueError(f"audit not found: {audit_id}")

            pages = self._query(
                connection,
                "SELECT * FROM pages WHERE audit_id = ? ORDER BY depth, normalized_url",
                (audit_id,),
            )
            snapshots = self._query_optional(
                connection,
                """
                SELECT ps.*, p.normalized_url
                FROM page_snapshots ps
                JOIN pages p ON p.page_id = ps.page_id
                WHERE p.audit_id = ?
                ORDER BY p.normalized_url, ps.device
                """,
                (audit_id,),
            )
            scores = self._query_optional(
                connection,
                "SELECT * FROM scores WHERE audit_id = ? ORDER BY device, dimension",
                (audit_id,),
            )
            findings = self._query(
                connection,
                """
                SELECT * FROM findings WHERE audit_id = ?
                ORDER BY CASE severity
                    WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3 ELSE 4 END,
                    rule_id, finding_id
                """,
                (audit_id,),
            )
            recommendations = self._query_optional(
                connection,
                "SELECT * FROM recommendations WHERE audit_id = ? ORDER BY priority_score DESC, recommendation_id",
                (audit_id,),
            )
            groups = self._query_optional(
                connection,
                "SELECT * FROM remediation_groups WHERE audit_id = ? ORDER BY priority_score DESC, group_id",
                (audit_id,),
            )
            executions = self._query(
                connection,
                "SELECT * FROM rule_executions WHERE audit_id = ? ORDER BY rule_id, rule_execution_id",
                (audit_id,),
            )
            evidence = self._evidence_for_findings(
                connection, audit_id=audit_id, findings=findings
            )
            crawl_evidence = self._query(
                connection,
                """
                SELECT * FROM evidence
                WHERE audit_id = ?
                  AND evidence_type IN ('ROBOTS_RULE','SITEMAP_ENTRY','HTTP_RESPONSE')
                ORDER BY evidence_type, evidence_id
                """,
                (audit_id,),
            )
            semantic_assessments = self._query_optional(
                connection,
                """
                SELECT sa.*, ps.device, ps.page_id, p.normalized_url
                FROM semantic_assessments sa
                JOIN page_snapshots ps ON ps.snapshot_id = sa.snapshot_id
                JOIN pages p ON p.page_id = ps.page_id
                WHERE p.audit_id = ?
                ORDER BY p.normalized_url, ps.device, sa.assessment_type, sa.assessment_id
                """,
                (audit_id,),
            )
            entities = self._query_optional(
                connection,
                """
                SELECT eo.*, ps.device, ps.page_id, p.normalized_url
                FROM entity_observations eo
                JOIN page_snapshots ps ON ps.snapshot_id = eo.snapshot_id
                JOIN pages p ON p.page_id = ps.page_id
                WHERE p.audit_id = ?
                ORDER BY p.normalized_url, ps.device, eo.entity_observation_id
                """,
                (audit_id,),
            )
        finally:
            connection.close()

        audit_mode = AuditMode(audit["audit_mode"]) if audit["audit_mode"] else None
        limitations = tuple(_json_list(audit["limitations"]))
        capabilities = tuple(_json_list(audit["capabilities"]))
        score_by_device = self._score_groups(scores)
        page_by_id = {row["page_id"]: row for row in pages}
        group_by_id = {row["group_id"]: row for row in groups}
        recommendation_by_group = {
            row["remediation_group_id"]: row
            for row in recommendations
            if row["remediation_group_id"]
        }
        finding_by_id = {row["finding_id"]: row for row in findings}
        finding_to_group: dict[str, sqlite3.Row] = {}
        for group in groups:
            for finding_id in _json_list(group["affected_findings"]):
                finding_to_group[str(finding_id)] = group

        body = "".join(
            (
                self._compatibility(
                    audit=audit,
                    pages=pages,
                    findings=findings,
                    recommendations=recommendations,
                    grouped=score_by_device,
                    audit_mode=audit_mode,
                    limitations=limitations,
                ),
                self._coverage_and_confidence(
                    grouped=score_by_device,
                    audit_mode=audit_mode,
                    capabilities=capabilities,
                ),
                self._opportunities(
                    groups=groups,
                    finding_by_id=finding_by_id,
                    recommendation_by_group=recommendation_by_group,
                    grouped=score_by_device,
                ),
                self._device_scorecard("DESKTOP", score_by_device.get("DESKTOP", [])),
                self._device_scorecard("MOBILE", score_by_device.get("MOBILE", [])),
                self._correction_plan(
                    recommendations=recommendations,
                    groups=group_by_id,
                    finding_by_id=finding_by_id,
                ),
                self._detailed_corrections(
                    findings=findings,
                    evidence=evidence,
                    page_by_id=page_by_id,
                    finding_to_group=finding_to_group,
                    recommendation_by_group=recommendation_by_group,
                ),
                self._semantic_analysis(
                    audit_mode=audit_mode,
                    assessments=semantic_assessments,
                    rule_min=28,
                    rule_max=40,
                ),
                self._entities_and_intents(
                    audit_mode=audit_mode,
                    entities=entities,
                    executions=executions,
                    page_by_id=page_by_id,
                ),
                self._semantic_analysis(
                    audit_mode=audit_mode,
                    assessments=semantic_assessments,
                    rule_min=41,
                    rule_max=47,
                    heading="Citation Readiness / Evidence Trust",
                ),
                self._crawl_coverage(
                    audit=audit,
                    pages=pages,
                    evidence=crawl_evidence,
                    limitations=limitations,
                ),
                self._limitations(
                    audit_mode=audit_mode, limitations=limitations
                ),
                self._technical(
                    audit=audit,
                    pages=pages,
                    snapshots=snapshots,
                    executions=executions,
                ),
                self._interpretation(),
                self._glossary(),
            )
        )
        return self._document(
            title=f"Search & AI Readiness - {_text(audit['project_name'])}", body=body
        )

    @staticmethod
    def _query(
        connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]
    ) -> list[sqlite3.Row]:
        return list(connection.execute(sql, params).fetchall())

    @staticmethod
    def _query_optional(
        connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]
    ) -> list[sqlite3.Row]:
        try:
            return list(connection.execute(sql, params).fetchall())
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return []
            raise

    @classmethod
    def _evidence_for_findings(
        cls,
        connection: sqlite3.Connection,
        *,
        audit_id: str,
        findings: list[sqlite3.Row],
    ) -> dict[str, sqlite3.Row]:
        ids: list[str] = []
        for finding in findings:
            ids.extend(str(value) for value in _json_list(finding["evidence_ids"]))
        unique = tuple(dict.fromkeys(ids))
        if not unique:
            return {}
        placeholders = ",".join("?" for _ in unique)
        rows = connection.execute(
            f"SELECT * FROM evidence WHERE audit_id = ? AND evidence_id IN ({placeholders}) ORDER BY evidence_id",
            (audit_id, *unique),
        ).fetchall()
        return {row["evidence_id"]: row for row in rows}

    @staticmethod
    def _score_groups(scores: list[sqlite3.Row]) -> dict[str, list[sqlite3.Row]]:
        grouped: dict[str, list[sqlite3.Row]] = {"DESKTOP": [], "MOBILE": []}
        for score in scores:
            grouped.setdefault(score["device"], []).append(score)
        return grouped

    def _compatibility(
        self,
        *,
        audit: sqlite3.Row,
        pages: list[sqlite3.Row],
        findings: list[sqlite3.Row],
        recommendations: list[sqlite3.Row],
        grouped: dict[str, list[sqlite3.Row]],
        audit_mode: AuditMode | None,
        limitations: tuple[str, ...],
    ) -> str:
        overalls = {
            device: _overall(grouped.get(device, []))
            for device in ("DESKTOP", "MOBILE")
        }
        valid = [row for row in overalls.values() if _is_valid_overall(row)]
        if not valid:
            headline = "NÃO DETERMINADA"
            headline_state = "unknown"
            explanation = (
                "Não há evidência suficiente para determinar o nível geral de readiness Search & AI deste website. "
                "Cobertura e confiabilidade abaixo não são uma nota GEO."
            )
        else:
            headline = "RESULTADOS CONSOLIDADOS POR DISPOSITIVO"
            headline_state = "info"
            explanation = (
                "A readiness Search & AI é apresentada separadamente para Desktop e Mobile. "
                "Nenhuma nota combinada entre dispositivos é criada."
            )

        device_cards = "".join(
            self._overall_card(device, overalls[device])
            for device in ("DESKTOP", "MOBILE")
        )
        limitation_summary = self._principal_limitations(limitations)
        return f"""
        <header class="hero">
          <div class="eyebrow">RASAi - Search & AI Readiness Auditor · Actionable Remediation</div>
          <h1>Readiness Search & AI</h1>
          <div class="compatibility-state state-{headline_state}">{escape(headline)}</div>
          <p class="lead">{escape(explanation)}</p>
          <div class="overall-grid">{device_cards}</div>
          <div class="meta-grid">
            {_metric("Projeto", audit['project_name'])}
            {_metric("Auditoria", audit['audit_id'])}
            {_metric("Páginas analisadas", len(pages))}
            {_metric("Modo da auditoria", audit_mode.value if audit_mode else "NÃO INFORMADO")}
            {_metric("Problemas identificados", len(findings))}
            {_metric("Recomendações", len(recommendations))}
          </div>
          <div class="notice notice-info"><strong>Principais limitações</strong><br>{escape(limitation_summary)}</div>
          <p class="method-note">O produto mede readiness. Não promete ranking, citação, visibilidade ou presença em mecanismos generativos.</p>
        </header>
        """

    @staticmethod
    def _overall_card(device: str, row: sqlite3.Row | None) -> str:
        label = _device_label(device)
        if not _is_valid_overall(row):
            coverage = _coverage_text(row)
            return f"""
            <article class="overall-card state-unknown">
              <div class="card-label">{label}</div>
              <div class="overall-value">NÃO DETERMINADA</div>
              <div class="classification">Informação insuficiente</div>
              <dl class="mini-list">
                <div><dt>Cobertura da análise</dt><dd>{escape(coverage)}</dd></div>
                <div><dt>Confiabilidade</dt><dd>INSUFICIENTE</dd></div>
                <div><dt>Consolidação</dt><dd>{escape(_consolidation_text(row))}</dd></div>
              </dl>
            </article>
            """
        assert row is not None
        score = float(row["value"])
        classification, state = _score_classification(score)
        return f"""
        <article class="overall-card state-{state}">
          <div class="card-label">{label}</div>
          <div class="overall-value">{score:.1f}<span>/100</span></div>
          <div class="classification">{escape(classification)}</div>
          <dl class="mini-list">
            <div><dt>Cobertura da análise</dt><dd>{float(row['coverage']) * 100:.0f}%</dd></div>
            <div><dt>Confiabilidade</dt><dd>{escape(_STATUS_LABELS.get(row['confidence'], row['confidence']))}</dd></div>
            <div><dt>Consolidação</dt><dd>{escape(_STATUS_LABELS.get(row['consolidation_status'], row['consolidation_status']))}</dd></div>
          </dl>
        </article>
        """

    def _coverage_and_confidence(
        self,
        *,
        grouped: dict[str, list[sqlite3.Row]],
        audit_mode: AuditMode | None,
        capabilities: tuple[str, ...],
    ) -> str:
        cards: list[str] = []
        for device in ("DESKTOP", "MOBILE"):
            overall = _overall(grouped.get(device, []))
            cards.append(
                f"""
                <article class="reliability-card">
                  <h3>{_device_label(device)}</h3>
                  <div class="reliability-grid">
                    <div><span>Readiness Search & AI</span><strong>{escape(_score_value_text(overall))}</strong><small>Quão preparado está o site?</small></div>
                    <div><span>Cobertura da análise</span><strong>{escape(_coverage_text(overall))}</strong><small>Quanto do universo aplicável foi avaliado?</small></div>
                    <div><span>Confiabilidade</span><strong>{escape(_confidence_text(overall))}</strong><small>Quanto podemos confiar na conclusão?</small></div>
                  </div>
                </article>
                """
            )
        return f"""
        <section>
          <div class="section-kicker">Leitura obrigatória</div>
          <h2>Cobertura e confiabilidade</h2>
          <p class="section-intro">Readiness Search & AI, cobertura e confiabilidade são conceitos distintos. Cobertura baixa nunca deve ser lida como uma nota baixa do website.</p>
          {''.join(cards)}
          <div class="notice notice-info">{escape(self._ai_disclaimer(audit_mode=audit_mode, capabilities=capabilities))}</div>
        </section>
        """

    def _opportunities(
        self,
        *,
        groups: list[sqlite3.Row],
        finding_by_id: dict[str, sqlite3.Row],
        recommendation_by_group: dict[str, sqlite3.Row],
        grouped: dict[str, list[sqlite3.Row]],
    ) -> str:
        if not groups:
            return "<section><h2>Principais oportunidades de melhoria</h2><p class='muted'>Nenhum problema evidence-backed foi priorizado.</p></section>"
        rows: list[str] = []
        for group in groups[:8]:
            finding_ids = [str(value) for value in _json_list(group["affected_findings"])]
            finding = next((finding_by_id.get(item) for item in finding_ids if finding_by_id.get(item)), None)
            if finding is None:
                continue
            category = _text(finding["category"])
            dimension = _CATEGORY_DIMENSION.get(category.upper(), category.upper())
            area = _DIMENSION_LABELS.get(dimension, category.replace("_", " ").title())
            recommendation = recommendation_by_group.get(group["group_id"])
            device = recommendation["device"] if recommendation is not None else "BOTH"
            result = self._dimension_result_for_opportunity(
                grouped=grouped, dimension=dimension, device=device
            )
            rows.append(
                "<tr>"
                f"<td><span class='badge priority-{escape(group['priority_class'].lower())}'>{escape(group['priority_class'])}</span></td>"
                f"<td>{escape(_text(area))}</td>"
                f"<td>{escape(result)}</td>"
                f"<td>{escape(_text(finding['title']))}</td>"
                "</tr>"
            )
        body = "".join(rows) or "<tr><td colspan='4'>Nenhuma oportunidade publicável.</td></tr>"
        return f"""
        <section>
          <h2>Principais oportunidades de melhoria</h2>
          <p class="section-intro">Lista derivada exclusivamente de findings persistidos e priorizados. Dimensões apenas UNKNOWN não geram oportunidade fictícia.</p>
          <div class="table-wrap"><table><thead><tr><th>Prioridade</th><th>Área</th><th>Resultado</th><th>Problema principal</th></tr></thead><tbody>{body}</tbody></table></div>
        </section>
        """

    @staticmethod
    def _dimension_result_for_opportunity(
        *, grouped: dict[str, list[sqlite3.Row]], dimension: str, device: str
    ) -> str:
        devices = ("DESKTOP", "MOBILE") if device == "BOTH" else (device,)
        parts: list[str] = []
        for current in devices:
            row = next(
                (item for item in grouped.get(current, []) if item["dimension"] == dimension),
                None,
            )
            parts.append(f"{_device_label(current)}: {_score_value_text(row)}")
        return " · ".join(parts)

    def _device_scorecard(self, device: str, rows: list[sqlite3.Row]) -> str:
        heading = f"Score GEO - {_device_label(device)}"
        dimension_rows = [row for row in rows if row["dimension"] != "OVERALL_READINESS"]
        if not dimension_rows:
            return f"<section><h2>{escape(heading)}</h2><p class='muted'>Nenhum score persistido disponível para este dispositivo.</p></section>"
        cards = "".join(self._score_row(row) for row in dimension_rows)
        return f"""
        <section>
          <h2>{escape(heading)}</h2>
          <p class="section-intro">Cada dimensão apresenta nota, classificação, cobertura, confiabilidade e consolidação independentemente.</p>
          <div class="score-list">{cards}</div>
        </section>
        """

    @staticmethod
    def _score_row(row: sqlite3.Row) -> str:
        dimension = _DIMENSION_LABELS.get(
            row["dimension"], row["dimension"].replace("_", " ").title()
        )
        if row["value"] is None:
            value = "NÃO DETERMINADO"
            classification = "Informação insuficiente"
            state = "unknown"
        else:
            numeric = float(row["value"])
            value = f"{numeric:.1f}"
            classification, state = _score_classification(numeric)
        coverage = f"{float(row['coverage']) * 100:.0f}%"
        confidence = _STATUS_LABELS.get(row["confidence"], row["confidence"])
        consolidation = _STATUS_LABELS.get(
            row["consolidation_status"], row["consolidation_status"]
        )
        return f"""
        <article class="score-row state-{state}">
          <div class="score-main"><strong>{escape(_text(dimension))}</strong><span class="badge state-{state}">{escape(classification.upper())}</span></div>
          <div class="score-number">{escape(value)}</div>
          <div><small>Classificação</small><strong>{escape(classification)}</strong></div>
          <div><small>Cobertura</small><strong>{escape(coverage)}</strong></div>
          <div><small>Confiabilidade</small><strong>{escape(_text(confidence))}</strong></div>
          <div><small>Consolidação</small><strong>{escape(_text(consolidation))}</strong></div>
        </article>
        """

    def _correction_plan(
        self,
        *,
        recommendations: list[sqlite3.Row],
        groups: dict[str, sqlite3.Row],
        finding_by_id: dict[str, sqlite3.Row],
    ) -> str:
        if not recommendations:
            return "<section><h2>Plano de correção priorizado</h2><p class='muted'>Nenhuma recomendação persistida disponível.</p></section>"
        cards: list[str] = []
        for recommendation in recommendations:
            group = groups.get(recommendation["remediation_group_id"])
            if group is None:
                continue
            affected = [str(value) for value in _json_list(group["affected_findings"])]
            first = next((finding_by_id.get(item) for item in affected if finding_by_id.get(item)), None)
            problem = _text(first["title"]) if first is not None else group["root_cause"]
            recipe = recipe_for(group["rule_id"])
            fallback = "<span class='badge state-unknown'>FALLBACK</span>" if recipe.fallback else ""
            cards.append(
                f"""
                <article class="recommendation state-{_priority_state(recommendation['priority_class'])}">
                  <div class="finding-head">
                    <span class="badge priority-{escape(recommendation['priority_class'].lower())}">{escape(_PRIORITY_LABELS.get(recommendation['priority_class'], recommendation['priority_class']))}</span>
                    <span class="rule">{escape(group['rule_id'])} · {float(recommendation['priority_score']):.2f}</span>
                  </div>
                  <h3>{escape(_text(recommendation['title']))} {fallback}</h3>
                  <p><strong>Problema:</strong> {escape(problem)}</p>
                  <p>{escape(_text(recommendation['description']))}</p>
                  <div class="pill-row"><span>Dispositivo: {escape(_device_label(recommendation['device']))}</span><span>Impacto: {escape(recommendation['impact'])}</span><span>Esforço: {escape(recommendation['effort'])}</span><span>Confiabilidade: {escape(recommendation['confidence'])}</span></div>
                  <p class="muted">Escopo: {len(affected)} finding(s), {len(_json_list(group['affected_pages']))} página(s).</p>
                </article>
                """
            )
        return f"<section><h2>Plano de correção priorizado</h2>{''.join(cards)}</section>"

    def _detailed_corrections(
        self,
        *,
        findings: list[sqlite3.Row],
        evidence: dict[str, sqlite3.Row],
        page_by_id: dict[str, sqlite3.Row],
        finding_to_group: dict[str, sqlite3.Row],
        recommendation_by_group: dict[str, sqlite3.Row],
    ) -> str:
        if not findings:
            return "<section><h2>Correções técnicas detalhadas</h2><p class='muted'>Nenhum finding persistido foi fornecido para remediação.</p></section>"
        cards: list[str] = []
        for finding in findings:
            recipe = recipe_for(finding["rule_id"])
            group = finding_to_group.get(finding["finding_id"])
            recommendation = recommendation_by_group.get(group["group_id"]) if group is not None else None
            page = page_by_id.get(finding["page_id"]) if finding["page_id"] else None
            page_text = page["normalized_url"] if page is not None else "Escopo global da auditoria"
            evidence_ids = tuple(str(value) for value in _json_list(finding["evidence_ids"]))
            observed = _pretty_json(finding["observed_value"])
            html_snippet = self._persisted_html_snippet(evidence_ids, evidence)
            problem = self._problem_description(finding)
            priority = recommendation["priority_class"] if recommendation is not None else "NÃO PRIORIZADO"
            target = self._recipe_target(recipe)
            example = (
                f"<div class='recipe-block'><h4>Estrutura recomendada (exemplo)</h4><pre><code>{escape(recipe.example)}</code></pre></div>"
                if recipe.example
                else ""
            )
            if html_snippet is None:
                observed_html = (
                    "<div class='notice notice-unknown'><strong>HTML efetivamente observado</strong><br>"
                    "Trecho HTML original não persistido para esta evidência.</div>"
                )
            else:
                observed_html = (
                    "<div class='recipe-block'><h4>HTML efetivamente observado</h4>"
                    f"<pre><code>{escape(html_snippet)}</code></pre></div>"
                )
            acceptance = "".join(f"<li>{escape(item)}</li>" for item in recipe.acceptance)
            validation = "".join(f"<li>{escape(item)}</li>" for item in recipe.validation)
            evidence_html = "".join(
                self._evidence_item(evidence_id, evidence.get(evidence_id))
                for evidence_id in evidence_ids
            )
            human = (
                f"<div class='notice notice-warning'><strong>Decisão humana necessária</strong><br>{escape(recipe.human_decision)}</div>"
                if recipe.human_decision
                else ""
            )
            fallback = (
                "<span class='badge state-unknown'>FALLBACK DE REMEDIAÇÃO</span>"
                if recipe.fallback
                else ""
            )
            cards.append(
                f"""
                <article class="finding state-{_severity_state(finding['severity'])}">
                  <div class="finding-head">
                    <div><span class="badge severity-{escape(finding['severity'].lower())}">{escape(finding['severity'])}</span> {fallback}</div>
                    <span class="rule">{escape(finding['rule_id'])} · {escape(priority)}</span>
                  </div>
                  <h3>{escape(_text(recipe.title))}</h3>
                  <div class="detail-grid">
                    <div><small>Página</small><strong>{escape(_text(page_text))}</strong></div>
                    <div><small>Dispositivo</small><strong>{escape(_device_label(finding['device']))}</strong></div>
                    <div><small>Categoria GEO</small><strong>{escape(_DIMENSION_LABELS.get(_CATEGORY_DIMENSION.get(finding['category'], finding['category']), finding['category']))}</strong></div>
                    <div><small>Prioridade</small><strong>{escape(priority)}</strong></div>
                  </div>
                  <h4>Problema encontrado</h4><p>{escape(problem)}</p>
                  <div class="recipe-grid">
                    <div><small>Alvo técnico</small><strong>{escape(target)}</strong></div>
                    <div><small>Ação</small><strong>{escape(recipe.action)}</strong></div>
                  </div>
                  <h4>Valor observado</h4><pre>{escape(observed)}</pre>
                  {observed_html}
                  <h4>Correção recomendada</h4><p>{escape(recipe.description)}</p>
                  {human}
                  {example}
                  <h4>Critério de aceite</h4><ul>{acceptance}</ul>
                  <h4>Como revalidar</h4><ol>{validation}</ol>
                  <details><summary>Evidências rastreáveis ({len(evidence_ids)})</summary>{evidence_html}</details>
                </article>
                """
            )
        return f"""
        <section>
          <h2>Correções técnicas detalhadas</h2>
          <p class="section-intro">Cada correção liga regra, página, dispositivo, evidência, alvo técnico, ação, aceite e revalidação. Exemplos de código são recomendações; não são apresentados como HTML observado.</p>
          {''.join(cards)}
        </section>
        """

    @staticmethod
    def _recipe_target(recipe: RemediationRecipe) -> str:
        parts = [recipe.target]
        if recipe.element:
            parts.append(recipe.element)
        if recipe.location:
            parts.append(f"local: {recipe.location}")
        return " · ".join(parts)

    @staticmethod
    def _problem_description(finding: sqlite3.Row) -> str:
        observed = _json_object(finding["observed_value"])
        if finding["rule_id"] == "BR-GEO-013":
            canonicals = observed.get("canonicals")
            declared = observed.get("declared")
            if canonicals == [] or declared == []:
                return "Nenhuma declaração canonical válida foi encontrada."
        expected = _text(finding["expected_condition"])
        if expected:
            return f"{_text(finding['title'])}. Condição esperada: {expected}."
        return _text(finding["title"])

    @staticmethod
    def _persisted_html_snippet(
        evidence_ids: tuple[str, ...], evidence: dict[str, sqlite3.Row]
    ) -> str | None:
        for evidence_id in evidence_ids:
            row = evidence.get(evidence_id)
            if row is None:
                continue
            value = _json_object(row["observed_value"])
            for key in ("html", "outer_html", "snippet", "source_html"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        return None

    @staticmethod
    def _evidence_item(evidence_id: str, row: sqlite3.Row | None) -> str:
        if row is None:
            return f"<div class='evidence'><strong>{escape(evidence_id)}</strong><p class='muted'>Referência não reaberta no momento da geração.</p></div>"
        observed = _pretty_json(row["observed_value"])
        return f"""
        <div class="evidence">
          <strong>{escape(evidence_id)}</strong>
          <span>{escape(_text(row['evidence_type']))} · {escape(_text(row['source']))}</span>
          <pre>{escape(observed)}</pre>
        </div>
        """

    def _semantic_analysis(
        self,
        *,
        audit_mode: AuditMode | None,
        assessments: list[sqlite3.Row],
        rule_min: int,
        rule_max: int,
        heading: str = "Análise de conteúdo e semântica",
    ) -> str:
        selected = [
            row
            for row in assessments
            if rule_min <= _rule_number(row["assessment_type"]) <= rule_max
        ]
        if not selected:
            if audit_mode is AuditMode.NO_AI:
                note = (
                    "As avaliações semânticas dependentes de IA estão indisponíveis em modo NO_AI. "
                    "Isso reduz cobertura e não representa defeito do website."
                )
            else:
                note = "Nenhuma avaliação semântica persistida está disponível para esta seção."
            return f"<section><h2>{escape(heading)}</h2><div class='notice notice-unknown'>{escape(note)}</div></section>"

        cards: list[str] = []
        for row in selected:
            result = _STATUS_LABELS.get(row["result"], row["result"])
            state = _result_state(row["result"])
            evidence_ids = [str(value) for value in _json_list(row["evidence_ids"])]
            evidence_text = ", ".join(evidence_ids) or "nenhuma evidence_id"
            cards.append(
                f"""
                <article class="semantic-card state-{state}">
                  <div class="finding-head"><span class="badge state-{state}">{escape(result)}</span><span class="rule">{escape(row['assessment_type'])}</span></div>
                  <h3>{escape(_text(row['normalized_url']))} · {_device_label(row['device'])}</h3>
                  <p>{escape(_text(row['reasoning_summary']))}</p>
                  <p class="muted">Confiabilidade semântica normalizada: {float(row['confidence']) * 100:.0f}% · Evidências: {escape(evidence_text)}</p>
                </article>
                """
            )
        return f"""
        <section>
          <h2>{escape(heading)}</h2>
          <p class="section-intro">Síntese das avaliações semânticas persistidas do M7. O relatório não executa uma segunda chamada livre de IA.</p>
          {''.join(cards)}
        </section>
        """

    def _entities_and_intents(
        self,
        *,
        audit_mode: AuditMode | None,
        entities: list[sqlite3.Row],
        executions: list[sqlite3.Row],
        page_by_id: dict[str, sqlite3.Row],
    ) -> str:
        entity_rows = "".join(
            f"<tr><td>{escape(_text(row['normalized_url']))}</td><td>{escape(_device_label(row['device']))}</td><td>{escape(_text(row['name']))}</td><td>{escape(_text(row['entity_type']))}</td><td>{float(row['confidence']) * 100:.0f}%</td><td>{escape(', '.join(str(v) for v in _json_list(row['evidence_ids'])))}</td></tr>"
            for row in entities
        )
        intents: list[str] = []
        for execution in executions:
            if execution["rule_id"] != "BR-GEO-048":
                continue
            observed = _json_object(execution["observed_value"])
            primary = observed.get("primary_intent")
            secondary = observed.get("secondary_intents")
            if primary is None and not secondary:
                continue
            page = page_by_id.get(execution["page_id"]) if execution["page_id"] else None
            url = page["normalized_url"] if page is not None else "Escopo global"
            secondary_text = ", ".join(str(item) for item in secondary) if isinstance(secondary, list) else "-"
            intents.append(
                f"<tr><td>{escape(_text(url))}</td><td>{escape(_device_label(execution['device']))}</td><td>{escape(_text(primary or 'NÃO DETERMINADO'))}</td><td>{escape(secondary_text or '-')}</td><td>{escape(', '.join(str(v) for v in _json_list(execution['evidence_ids'])))}</td></tr>"
            )
        if not entity_rows and not intents:
            if audit_mode is AuditMode.NO_AI:
                note = "Entidades e intenções semânticas não ficaram disponíveis em modo NO_AI; isso é uma limitação da auditoria, não um defeito do site."
            elif audit_mode is AuditMode.DEGRADED:
                note = "O provider externo foi configurado, mas a análise válida não ficou disponível para este contexto; o estado é DEGRADED, não NO_AI."
            else:
                note = "Nenhuma entidade ou intenção persistida está disponível."
            return f"<section><h2>Entidades e intenções</h2><div class='notice notice-unknown'>{escape(note)}</div></section>"
        entities_table = (
            f"<h3>Entidades observadas</h3><div class='table-wrap'><table><thead><tr><th>Página</th><th>Dispositivo</th><th>Entidade</th><th>Tipo</th><th>Confiança</th><th>Evidências</th></tr></thead><tbody>{entity_rows}</tbody></table></div>"
            if entity_rows
            else "<p class='muted'>Nenhuma entidade persistida.</p>"
        )
        intents_table = (
            f"<h3>Intenções</h3><div class='table-wrap'><table><thead><tr><th>Página</th><th>Dispositivo</th><th>Intenção primária</th><th>Intenções secundárias</th><th>Evidências</th></tr></thead><tbody>{''.join(intents)}</tbody></table></div>"
            if intents
            else "<p class='muted'>Nenhuma intenção persistida.</p>"
        )
        return f"<section><h2>Entidades e intenções</h2>{entities_table}{intents_table}</section>"

    def _crawl_coverage(
        self,
        *,
        audit: sqlite3.Row,
        pages: list[sqlite3.Row],
        evidence: list[sqlite3.Row],
        limitations: tuple[str, ...],
    ) -> str:
        total_discovered = len(pages)
        total_audited = len(pages)
        limit_reached = False
        for limitation in limitations:
            match = _MAX_PAGES_RE.search(_text(limitation))
            if match:
                total_discovered = int(match.group(1))
                total_audited = int(match.group(2))
                limit_reached = True
                break

        source_counts = {"SEED": 0, "SITEMAP": 0, "INTERNAL_LINK": 0, "REDIRECT": 0, "MANUAL": 0}
        for page in pages:
            for source in _json_list(page["discovery_sources"]):
                source_name = str(source)
                source_counts[source_name] = source_counts.get(source_name, 0) + 1

        robots = next((row for row in evidence if row["evidence_type"] == "ROBOTS_RULE"), None)
        robots_value = _json_object(robots["observed_value"]) if robots is not None else {}
        robots_state = _text(robots_value.get("state") or "NÃO DETERMINADO")
        declared_sitemaps = robots_value.get("declared_sitemaps")
        declared_count = len(declared_sitemaps) if isinstance(declared_sitemaps, list) else 0

        sitemap_resources: list[tuple[str, str, str]] = []
        redirect_hops = 0
        for row in evidence:
            value = _json_object(row["observed_value"])
            if row["evidence_type"] == "SITEMAP_ENTRY" and row["page_id"] is None and "state" in value:
                sitemap_resources.append(
                    (_text(row["source"]), _text(value.get("state") or "NÃO DETERMINADO"), _text(value.get("error") or ""))
                )
            if row["evidence_type"] == "HTTP_RESPONSE":
                chain = value.get("redirect_chain")
                if isinstance(chain, list):
                    redirect_hops += len(chain)

        if limit_reached:
            diagnosis = (
                "O limite configurado foi atingido. Existem URLs descobertas fora do universo auditado; "
                "a cobertura de crawl foi limitada por configuração, não por uma conclusão sobre a qualidade do site."
            )
        elif total_discovered <= 1 and source_counts.get("SITEMAP", 0) == 0 and source_counts.get("INTERNAL_LINK", 0) == 0:
            diagnosis = "Nenhuma URL adicional elegível foi descoberta além da seed dentro do escopo e das fontes persistidas."
        elif any(state in {"INVALID", "HTTP_ERROR", "NETWORK_ERROR"} for _, state, _ in sitemap_resources):
            diagnosis = "A descoberta terminou sem atingir max_pages, mas existe sitemap com estado degradado; revise os detalhes abaixo."
        else:
            diagnosis = "A descoberta terminou sem atingir o limite configurado."

        sitemap_rows = "".join(
            f"<tr><td>{escape(url)}</td><td>{escape(state)}</td><td>{escape(error or '-')}</td></tr>"
            for url, state, error in sitemap_resources
        ) or "<tr><td colspan='3'>Nenhum recurso de sitemap persistido.</td></tr>"

        return f"""
        <section>
          <h2>Cobertura do Crawl</h2>
          <div class="crawl-grid">
            {_metric("URLs descobertas", total_discovered)}
            {_metric("URLs auditadas", total_audited)}
            {_metric("Limite configurado", audit['max_pages'])}
            {_metric("Limite atingido", "Sim" if limit_reached else "Não")}
            {_metric("robots.txt", robots_state)}
            {_metric("Sitemaps declarados", declared_count)}
            {_metric("Redirect hops observados", redirect_hops)}
          </div>
          <h3>Fontes de descoberta</h3>
          <div class="source-grid">
            {_metric("Seed", source_counts.get('SEED', 0))}
            {_metric("Sitemap", source_counts.get('SITEMAP', 0))}
            {_metric("Links internos", source_counts.get('INTERNAL_LINK', 0))}
            {_metric("Redirect", source_counts.get('REDIRECT', 0))}
          </div>
          <div class="notice notice-info"><strong>Diagnóstico</strong><br>{escape(diagnosis)}</div>
          <h3>Estado dos sitemaps</h3>
          <div class="table-wrap"><table><thead><tr><th>Recurso</th><th>Estado</th><th>Observação</th></tr></thead><tbody>{sitemap_rows}</tbody></table></div>
        </section>
        """

    @staticmethod
    def _principal_limitations(limitations: tuple[str, ...]) -> str:
        if not limitations:
            return "Nenhuma limitação adicional registrada."
        visible = [_text(item) for item in limitations[:3]]
        suffix = "" if len(limitations) <= 3 else f" (+{len(limitations) - 3} adicional(is))"
        return " · ".join(visible) + suffix

    @staticmethod
    def _ai_disclaimer(*, audit_mode: AuditMode | None, capabilities: tuple[str, ...]) -> str:
        if audit_mode is AuditMode.NO_AI or any("NO_AI" in value.upper() for value in capabilities):
            return (
                "Algumas avaliações semânticas não foram executadas porque não havia um provedor de inteligência artificial disponível ou configurado. "
                "Essa limitação reduz a cobertura da auditoria e não representa um problema do website analisado."
            )
        provider_configured = any(
            value.upper().startswith("SEMANTIC_PROVIDER:") and not value.upper().endswith(":NONE")
            for value in capabilities
        )
        if audit_mode is AuditMode.DEGRADED and provider_configured:
            return (
                "Um provider externo foi configurado e houve tentativa de análise, mas ao menos um contexto ficou indisponível ou teve a resposta rejeitada pelo contrato evidence-bound. "
                "Somente resultados externos válidos são reutilizados; o baseline determinístico permanece disponível como fallback onde houver evidência suficiente."
            )
        if audit_mode is AuditMode.FULL and provider_configured:
            return (
                "Análises semânticas utilizaram o provider externo configurado. O relatório reutiliza somente resultados normalizados e persistidos; "
                "credenciais não são incluídas e nenhuma chamada livre adicional é feita para redigir remediações."
            )
        return (
            "A disponibilidade semântica é refletida em cobertura, confiabilidade e limitações. "
            "Ausência de capacidade do auditor não é tratada como defeito do website."
        )

    def _limitations(
        self, *, audit_mode: AuditMode | None, limitations: tuple[str, ...]
    ) -> str:
        items = [
            "Readiness Search & AI, cobertura e confiabilidade devem ser interpretadas separadamente.",
            "Desktop e Mobile são independentes e não são combinados em uma nota artificial.",
            "Findings e remediações são limitados ao universo auditado e às evidências persistidas.",
            "Exemplos de HTML representam estruturas recomendadas; não são apresentados como código originalmente observado quando o trecho não foi persistido.",
            "Remediações que dependem de decisão editorial, jurídica ou de negócio permanecem explicitamente condicionadas à validação humana.",
        ]
        items.extend(_text(item) for item in limitations)
        if audit_mode is AuditMode.NO_AI:
            items.append(
                "Avaliações semânticas dependentes de IA podem estar NÃO DETERMINADAS; isso reduz cobertura sem penalizar o website."
            )
        html = "".join(f"<li>{escape(item)}</li>" for item in dict.fromkeys(items))
        return f"<section><h2>Limitações</h2><ul>{html}</ul></section>"

    @staticmethod
    def _technical(
        *,
        audit: sqlite3.Row,
        pages: list[sqlite3.Row],
        snapshots: list[sqlite3.Row],
        executions: list[sqlite3.Row],
    ) -> str:
        counts: dict[str, int] = {}
        for row in executions:
            counts[row["result"]] = counts.get(row["result"], 0) + 1
        executions_html = "".join(
            f"<tr><td>{escape(_STATUS_LABELS.get(result, result))}</td><td>{count}</td></tr>"
            for result, count in sorted(counts.items())
        ) or "<tr><td colspan='2'>Sem RuleExecutions</td></tr>"
        return f"""
        <section>
          <h2>Detalhes técnicos</h2>
          <div class="technical-grid">
            <div><strong>Auditor version</strong><span>{escape(_text(audit['auditor_version']))}</span></div>
            <div><strong>Ruleset version</strong><span>{escape(_text(audit['ruleset_version']))}</span></div>
            <div><strong>Template version</strong><span>{TEMPLATE_VERSION}</span></div>
            <div><strong>max_pages</strong><span>{int(audit['max_pages'])}</span></div>
            <div><strong>Páginas persistidas</strong><span>{len(pages)}</span></div>
            <div><strong>Snapshots persistidos</strong><span>{len(snapshots)}</span></div>
          </div>
          <h3>Resultados de regras</h3>
          <div class="table-wrap"><table><thead><tr><th>Resultado</th><th>Quantidade</th></tr></thead><tbody>{executions_html}</tbody></table></div>
        </section>
        """

    @staticmethod
    def _interpretation() -> str:
        items = (
            ("Readiness Search & AI", "Quão preparado está o site segundo scores consolidados. Nunca é substituída pela cobertura."),
            ("Cobertura da Análise", "Quanto do universo aplicável pôde ser efetivamente avaliado. Baixa cobertura não significa baixa qualidade do site."),
            ("Confiabilidade", "Grau de segurança da conclusão com base em evidências, método, cobertura e limitações."),
            ("NÃO DETERMINADO", "Não existe base suficiente para apresentar conclusão consolidada; não equivale a zero nem a falha."),
            ("Consolidado", "Há cobertura e confiabilidade suficientes para apresentar o resultado como consolidado."),
            ("Parcial", "Parte relevante da avaliação está disponível, mas existem limitações."),
            ("Severidade", "Gravidade intrínseca do problema identificado."),
            ("Prioridade", "Ordem recomendada de ação considerando gravidade, impacto, confiabilidade e facilidade."),
            ("Desktop e Mobile", "São contextos independentes e podem apresentar resultados diferentes."),
        )
        cards = "".join(
            f"<div class='explain'><h3>{escape(title)}</h3><p>{escape(text)}</p></div>"
            for title, text in items
        )
        return f"<section><h2>Metodologia / Como interpretar este relatório</h2><div class='explain-grid'>{cards}</div></section>"

    @staticmethod
    def _glossary() -> str:
        terms = (
            ("Readiness", "Grau de preparação observado segundo as regras da auditoria; não equivale a garantia de desempenho externo."),
            ("NÃO DETERMINADO", "Estado usado quando não há cobertura/confiabilidade/consolidação suficientes para conclusão."),
            ("Canonical (URL canônica)", "Sinal técnico de URL preferencial; a URL preferencial não deve ser inventada pelo auditor."),
            ("Evidence-bound", "Conclusão limitada ao conjunto de evidências persistidas e permitidas."),
            ("Remediation Recipe", "Receita determinística por regra com alvo, ação, exemplo opcional, aceite e revalidação."),
            ("Soft 404", "Página com semântica de erro sem status HTTP apropriado."),
            ("Client-Side Rendering - CSR", "Renderização no navegador."),
            ("SPA", "Single-Page Application."),
            ("JSON-LD", "Formato comum de Dados Estruturados."),
        )
        rows = "".join(
            f"<dt>{escape(term)}</dt><dd>{escape(definition)}</dd>"
            for term, definition in terms
        )
        return f"<section><h2>Glossário</h2><dl>{rows}</dl></section>"

    @staticmethod
    def _document(*, title: str, body: str) -> str:
        css = """
        :root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#172033;background:#eef2f7;line-height:1.5;--success:#16803C;--warning:#D99A00;--problem:#D65A00;--critical:#C62828;--unknown:#667085;--info:#2563EB;--border:#dce3ec;--muted:#667085}
        *{box-sizing:border-box}body{margin:0}.page{max-width:1200px;margin:0 auto;padding:32px 24px 72px}section,.hero{background:#fff;border:1px solid var(--border);border-radius:16px;padding:28px;margin:0 0 20px;box-shadow:0 8px 24px rgba(25,39,67,.05)}
        .hero{padding:38px}.eyebrow,.section-kicker{font-size:.76rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--info)}h1{font-size:2.15rem;line-height:1.1;margin:.5rem 0}h2{font-size:1.38rem;margin:0 0 16px}h3{font-size:1.03rem;margin:0 0 8px}h4{font-size:.94rem;margin:18px 0 7px}.lead,.section-intro{max-width:900px;color:#536078}.method-note{color:#68758a;font-size:.86rem}.compatibility-state{font-size:1.45rem;font-weight:900;letter-spacing:.02em;margin:.25rem 0 1rem}.state-success{border-color:rgba(22,128,60,.35)!important}.state-warning{border-color:rgba(217,154,0,.45)!important}.state-problem{border-color:rgba(214,90,0,.4)!important}.state-critical{border-color:rgba(198,40,40,.4)!important}.state-unknown{border-color:rgba(102,112,133,.35)!important}.state-info{border-color:rgba(37,99,235,.35)!important}.compatibility-state.state-success,.badge.state-success{color:var(--success)}.compatibility-state.state-warning,.badge.state-warning{color:#9c6e00}.compatibility-state.state-problem,.badge.state-problem{color:var(--problem)}.compatibility-state.state-critical,.badge.state-critical{color:var(--critical)}.compatibility-state.state-unknown,.badge.state-unknown{color:var(--unknown)}.compatibility-state.state-info,.badge.state-info{color:var(--info)}
        .overall-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:22px 0}.overall-card{border:2px solid var(--border);border-radius:14px;padding:20px;background:#fff}.card-label{font-size:.8rem;font-weight:800;text-transform:uppercase;color:#59667a}.overall-value{font-size:2rem;font-weight:900;margin:5px 0}.overall-value span{font-size:.85rem;color:#657086}.classification{font-weight:800}.mini-list{margin:12px 0 0}.mini-list>div{display:flex;justify-content:space-between;border-top:1px solid #edf0f4;padding:7px 0}.mini-list dt{font-weight:500;color:#657086}.mini-list dd{font-weight:800;margin:0}
        .meta-grid,.crawl-grid,.source-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:18px}.metric{background:#f6f8fb;border:1px solid #e5eaf1;border-radius:12px;padding:14px}.metric small,.score-row small,.detail-grid small,.recipe-grid small{display:block;color:#657086}.metric strong{display:block;margin-top:4px;overflow-wrap:anywhere}.notice{border-radius:10px;padding:14px;margin:14px 0;border:1px solid var(--border);background:#f6f8fb}.notice-info{border-left:4px solid var(--info);background:#f4f7ff}.notice-warning{border-left:4px solid var(--warning);background:#fffbef}.notice-unknown{border-left:4px solid var(--unknown);background:#f7f7f8}
        .reliability-card{border:1px solid var(--border);border-radius:12px;padding:16px;margin:12px 0}.reliability-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.reliability-grid>div{background:#f8fafc;border-radius:10px;padding:14px}.reliability-grid span,.reliability-grid small{display:block;color:#657086}.reliability-grid strong{display:block;font-size:1.2rem;margin:4px 0}
        .score-list{display:grid;gap:10px}.score-row{display:grid;grid-template-columns:minmax(190px,1.7fr) 130px 120px 90px 100px 130px;gap:12px;align-items:center;border:1px solid var(--border);border-left-width:5px;border-radius:11px;padding:13px}.score-main{display:flex;flex-direction:column;align-items:flex-start;gap:6px}.score-number{font-size:1.35rem;font-weight:900}.badge{display:inline-block;border-radius:999px;padding:4px 9px;background:#eef2f7;font-size:.74rem;font-weight:900;line-height:1.2}.priority-p0{background:#f8dddd;color:var(--critical)}.priority-p1{background:#fae7dd;color:var(--problem)}.priority-p2{background:#fff1d1;color:#926600}.priority-p3,.priority-p4{background:#eef2f7;color:#536078}.severity-critical{background:#f8dddd;color:var(--critical)}.severity-high{background:#fae7dd;color:var(--problem)}.severity-medium{background:#fff1d1;color:#926600}.severity-low{background:#eef2f7;color:#536078}
        .finding,.recommendation,.semantic-card{border:1px solid var(--border);border-left-width:5px;border-radius:12px;padding:19px;margin:13px 0}.finding-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.rule{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#5b6679}.pill-row{display:flex;flex-wrap:wrap;gap:7px}.pill-row span{font-size:.79rem;background:#f3f6fa;border-radius:999px;padding:5px 9px}.detail-grid,.recipe-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin:14px 0}.detail-grid>div,.recipe-grid>div{background:#f8fafc;border-radius:9px;padding:10px}.detail-grid strong,.recipe-grid strong{display:block;overflow-wrap:anywhere}.recipe-block{margin:14px 0}.muted{color:#68758a}details{margin-top:10px}summary{cursor:pointer;font-weight:700}.evidence{border-top:1px solid #edf0f4;padding:10px 0}.evidence span{display:block;color:#637087;font-size:.85rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fb;border:1px solid #e7ebf0;border-radius:8px;padding:11px;font-size:.78rem}code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
        .table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #e8edf3;padding:10px;vertical-align:top}th{font-size:.78rem;text-transform:uppercase;color:#657086}.technical-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.technical-grid div{display:flex;flex-direction:column;background:#f8fafc;padding:10px;border-radius:8px}.explain-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}.explain{border-left:3px solid var(--info);padding:10px 14px;background:#fafbfd}.explain p{margin:0;color:#58657a}dl{display:grid;grid-template-columns:minmax(180px,280px) 1fr;gap:8px 18px}dt{font-weight:800}dd{margin:0;color:#59667a}
        footer{text-align:center;color:#6c778a;font-size:.82rem;padding:18px}@media(max-width:920px){.score-row{grid-template-columns:1fr 110px 110px}.score-row>div:nth-child(n+4){padding-top:4px}.reliability-grid{grid-template-columns:1fr}.overall-grid{grid-template-columns:1fr}}@media(max-width:620px){.score-row{grid-template-columns:1fr}.finding-head{align-items:flex-start;flex-direction:column}.page{padding:14px}section,.hero{padding:20px}dl{grid-template-columns:1fr}.mini-list>div{display:block}.mini-list dd{margin-top:2px}}
        @media print{body{background:#fff}.page{max-width:none;padding:0}section,.hero{box-shadow:none;break-inside:auto}.finding,.recommendation,.semantic-card,.overall-card{break-inside:avoid}.table-wrap{overflow:visible}}
        """
        return f"""<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title><style>{css}</style></head>
<body><main class="page">{body}<footer>Relatório estático · {TEMPLATE_VERSION} · gerado exclusivamente a partir de dados persistidos da auditoria.</footer></main></body>
</html>"""


def write_report(
    *, workspace: AuditWorkspace, html: str, filename: str = "report.html"
) -> Path:
    path = workspace.root / filename
    temporary = workspace.root / f".{filename}.tmp"
    temporary.write_text(html, encoding="utf-8", newline="\n")
    temporary.replace(path)
    return path


def new_report_record(
    *, audit_id: str, auditor_version: str, file_path: str
) -> ReportRecord:
    return ReportRecord(
        report_id=new_id("RPT"),
        audit_id=audit_id,
        format="HTML",
        status="GENERATED",
        generated_at=utc_now(),
        template_version=TEMPLATE_VERSION,
        auditor_version=auditor_version,
        file_path=file_path,
    )


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><small>{escape(_text(label))}</small><strong>{escape(_text(value))}</strong></div>"


def _overall(rows: list[sqlite3.Row]) -> sqlite3.Row | None:
    return next((row for row in rows if row["dimension"] == "OVERALL_READINESS"), None)


def _is_valid_overall(row: sqlite3.Row | None) -> bool:
    return bool(
        row is not None
        and row["value"] is not None
        and row["consolidation_status"] == "CONSOLIDATED"
    )


def _score_value_text(row: sqlite3.Row | None) -> str:
    if not _is_valid_overall(row) and (row is None or row["dimension"] == "OVERALL_READINESS"):
        return "NÃO DETERMINADA"
    if row is None or row["value"] is None:
        return "NÃO DETERMINADO"
    return f"{float(row['value']):.1f}/100"


def _coverage_text(row: sqlite3.Row | None) -> str:
    return "NÃO DISPONÍVEL" if row is None else f"{float(row['coverage']) * 100:.0f}%"


def _confidence_text(row: sqlite3.Row | None) -> str:
    if row is None:
        return "NÃO DISPONÍVEL"
    if not _is_valid_overall(row) and row["dimension"] == "OVERALL_READINESS":
        return "INSUFICIENTE"
    return _STATUS_LABELS.get(row["confidence"], row["confidence"])


def _consolidation_text(row: sqlite3.Row | None) -> str:
    if row is None:
        return "NÃO CONSOLIDADO"
    return _STATUS_LABELS.get(row["consolidation_status"], row["consolidation_status"])


def _score_classification(value: float) -> tuple[str, str]:
    if value >= 90:
        return "Excelente", "success"
    if value >= 75:
        return "Alta", "success"
    if value >= 60:
        return "Moderada", "warning"
    if value >= 40:
        return "Baixa", "problem"
    return "Crítica", "critical"


def _priority_state(priority: str) -> str:
    if priority == "P0":
        return "critical"
    if priority == "P1":
        return "problem"
    if priority == "P2":
        return "warning"
    return "unknown"


def _severity_state(severity: str) -> str:
    return {
        "CRITICAL": "critical",
        "HIGH": "problem",
        "MEDIUM": "warning",
        "LOW": "unknown",
        "INFO": "info",
    }.get(severity, "unknown")


def _result_state(result: str) -> str:
    return {
        "PASS": "success",
        "WARNING": "warning",
        "FAIL": "problem",
        "ERROR": "critical",
        "UNKNOWN": "unknown",
        "NOT_APPLICABLE": "unknown",
    }.get(result, "unknown")


def _device_label(device: Any) -> str:
    value = _text(device)
    return {
        "DESKTOP": "Desktop",
        "MOBILE": "Mobile",
        "BOTH": "Ambos",
        "NOT_APPLICABLE": "Não aplicável",
        "": "Global",
    }.get(value, value.title())


def _rule_number(rule_id: Any) -> int:
    try:
        return int(_text(rule_id).rsplit("-", 1)[1])
    except (ValueError, IndexError):
        return -1


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _json_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
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


def _pretty_json(value: Any) -> str:
    parsed: Any = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = value
    sanitized = _redact(parsed)
    if isinstance(sanitized, (dict, list, tuple)):
        return json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True)
    return _text(sanitized)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    return value
