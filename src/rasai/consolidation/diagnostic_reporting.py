"""Current diagnostic-closure notice for the consolidated report.

This presentation layer consumes the read-only source governance already built by the
consolidation pipeline. It never recollects APIs or mutates source AUDs.
"""
from __future__ import annotations

from html import escape
import json
from typing import Any, Mapping

from .models import GenerationResult


_COMPONENT_LABELS = {
    "SEMANTIC_AI": ("CAT-03", "Análise semântica por IA", "IA"),
    "WEB_PERFORMANCE": ("CAT-04", "Web Performance / PageSpeed", "API/integração"),
    "SEARCH_INTELLIGENCE": ("CAT-05", "Search Intelligence / SERP", "API/integração"),
    "GOOGLE_SEARCH_CONSOLE": ("CAT-05", "Google Search Console", "API/integração"),
    "SYNTHETIC_APDEX": ("CAT-06", "Apdex de navegação", "Coleta"),
    "EXPERIENCE_APDEX": ("CAT-07", "Apdex de experiência", "Coleta"),
    "IMPROVEMENT_INTELLIGENCE": ("CAT-08", "Análise profunda por IA", "IA"),
    "CONTENT_REMEDIATION_AI": ("CAT-09", "Remediação de conteúdo por IA", "IA"),
    "TECHNICAL_AI": ("CAT-09", "Análise técnica por IA", "IA"),
    "PASSIVE_SECURITY": ("CAT-10", "Segurança passiva", "Integração/análise"),
    "HTTP_ACQUISITION": ("CAT-01", "Aquisição HTTP", "Coleta"),
    "RENDER_CAPTURE": ("CAT-01", "Captura renderizada", "Coleta"),
    "CONTENT_EXTRACTION": ("CAT-03", "Extração de conteúdo", "Coleta"),
}


def _meta(component: Any) -> tuple[str, str, str]:
    key = str(component or "").strip().upper()
    return _COMPONENT_LABELS.get(
        key,
        ("-", key.replace("_", " ").title() or "Etapa técnica", "Etapa"),
    )


def _issue_state(issue: Mapping[str, Any]) -> str:
    status = str(issue.get("status") or "PENDING").upper()
    error_class = str(issue.get("last_error_class") or "").upper()
    component = str(issue.get("component") or "").upper()
    is_ai = component.endswith("_AI") or component in {"IMPROVEMENT_INTELLIGENCE"}
    if status == "WAITING_FOR_DATA" or error_class == "PREREQUISITE":
        return "Não executada - pré-requisitos incompletos" if is_ai else "Aguardando pré-requisito"
    if is_ai and error_class == "CONFIGURATION":
        return "Não executada - IA não configurada/disponível"
    if status == "FAILED_RETRYABLE":
        return "Falha temporária - reprocessável"
    if status == "NOT_CONFIGURED":
        return "Não configurada"
    if status == "REQUESTED_NOT_EXECUTED":
        return "Solicitada - não executada"
    if status == "BLOCKED":
        return "Bloqueada"
    return status.replace("_", " ").title()


def _issue_reason(issue: Mapping[str, Any]) -> str:
    return str(
        issue.get("last_error_message")
        or issue.get("last_error_code")
        or "requisito necessário ainda não concluído"
    )


def _rows(
    governance: Mapping[str, Any],
    *,
    ai_requested: bool,
    ai_status: str,
    ai_reason: str | None,
) -> list[tuple[str, str, str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str, str, str]] = []
    for audit in governance.get("audits", ()):
        if not isinstance(audit, Mapping):
            continue
        audit_id = str(audit.get("audit_id") or "-")
        issue_count = 0
        for issue in audit.get("required_issues", ()):
            if not isinstance(issue, Mapping):
                continue
            issue_count += 1
            catalog, integration, kind = _meta(issue.get("component"))
            rows.append(
                (
                    audit_id,
                    catalog,
                    integration,
                    kind,
                    _issue_state(issue),
                    _issue_reason(issue),
                    "Reprocessar a auditoria de origem",
                )
            )
        if issue_count == 0 and not bool(audit.get("conclusive", False)):
            limitations = [
                str(value).strip()
                for value in (audit.get("source_limitations") or ())
                if str(value).strip()
            ]
            rows.append(
                (
                    audit_id,
                    "-",
                    "Auditoria de origem",
                    "Governança",
                    str(audit.get("source_state_label") or "Conclusão não comprovada"),
                    "; ".join(limitations)
                    or "a fonte não possui evidência de fechamento integral suficiente para conclusão longitudinal",
                    "Revisar/reprocessar a AUD de origem antes de tratar a série como conclusiva",
                )
            )

    normalized_ai = str(ai_status or "NOT_REQUESTED").upper()
    if ai_requested and normalized_ai != "COMPLETE":
        state = {
            "NOT_CONFIGURED": "Não executada - IA não configurada/disponível",
            "UNAVAILABLE": "Solicitada - provider/execução não concluiu",
            "FAILED": "Solicitada - provider/execução não concluiu",
        }.get(normalized_ai, normalized_ai.replace("_", " ").title())
        rows.append(
            (
                "CONS",
                "Análise longitudinal",
                "IA especialista",
                "IA",
                state,
                str(ai_reason or "a camada de IA longitudinal não foi concluída"),
                "Reexecutar o consolidado com IA apta; não é necessário recolher as AUDs",
            )
        )
    return rows


def materialize_diagnostic_notice(
    result: GenerationResult,
    governance: Mapping[str, Any],
    *,
    ai_requested: bool,
    ai_status: str,
    ai_reason: str | None,
) -> GenerationResult:
    rows = _rows(
        governance,
        ai_requested=ai_requested,
        ai_status=ai_status,
        ai_reason=ai_reason,
    )
    try:
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    manifest["diagnostic_closure"] = {
        "status": "PENDING" if rows else "COMPLETE",
        "pending_count": len(rows),
        "source_audits_non_conclusive": [
            str(item.get("audit_id") or "")
            for item in governance.get("audits", ())
            if isinstance(item, Mapping)
            and (
                item.get("required_issues")
                or not bool(item.get("conclusive", False))
            )
        ],
        "specialist_ai_requested": bool(ai_requested),
        "specialist_ai_status": str(ai_status or "NOT_REQUESTED").upper(),
    }
    result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if not rows:
        return result

    rendered_rows = "".join(
        "<tr>"
        f"<td><code>{escape(audit)}</code></td>"
        f"<td>{escape(catalog)}</td>"
        f"<td>{escape(integration)}</td>"
        f"<td>{escape(kind)}</td>"
        f"<td>{escape(state)}</td>"
        f"<td>{escape(reason)}</td>"
        f"<td>{escape(action)}</td>"
        "</tr>"
        for audit, catalog, integration, kind, state, reason, action in rows
    )
    section = (
        "<section id='diagnostic-closure' class='panel'>"
        "<div class='kicker'>Estado atual do diagnóstico</div>"
        "<h2>Fechamento diagnóstico pendente</h2>"
        "<div class='metric-grid'>"
        "<div><small>Relatório</small><strong>Gerado</strong></div>"
        "<div><small>Integridade estrutural</small><strong>Preservada pelo contrato do CONS</strong></div>"
        "<div><small>Fechamento integral</small><strong>Pendente</strong></div>"
        "</div>"
        "<div class='notice warn'><strong>O consolidado determinístico foi materializado.</strong> "
        "As limitações abaixo permanecem explícitas e não foram convertidas em sucesso. "
        "O CONS não recolhe integrações das AUDs fonte.</div>"
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Origem</th><th>Fase/Catálogo</th><th>Integração</th><th>Tipo</th>"
        "<th>Estado</th><th>Motivo</th><th>Ação</th>"
        "</tr></thead><tbody>"
        + rendered_rows
        + "</tbody></table></div></section>"
    )
    try:
        html = result.report_path.read_text(encoding="utf-8")
    except OSError:
        return result
    if "id='diagnostic-closure'" in html or 'id="diagnostic-closure"' in html:
        return result
    if "<main>" in html:
        html = html.replace("<main>", "<main>" + section, 1)
    elif "<body>" in html:
        html = html.replace("<body>", "<body>" + section, 1)
    else:
        html = section + html
    result.report_path.write_text(html, encoding="utf-8", newline="\n")
    return result


__all__ = ["materialize_diagnostic_notice"]
