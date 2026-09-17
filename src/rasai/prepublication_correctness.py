"""Pre-publication correctness contracts for execution, language and fulfillment.

RASAi has not been published yet, so these rules intentionally define the current
canonical behaviour rather than preserving obsolete result shapes.  The installer is
used only to compose the present runtime owners; it is not a legacy compatibility
layer and does not preserve deprecated public values.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Mapping

_INSTALLED = False


_M7_SPECS_PT = (
    (28, "O título da página deve estar presente e representar semanticamente o conteúdo", "SEMANTIC_STRUCTURE", "HIGH", "SEMANTIC_TITLE"),
    (29, "O conteúdo principal deve expor uma hierarquia semântica compreensível", "SEMANTIC_STRUCTURE", "MEDIUM", "SEMANTIC_HIERARCHY"),
    (30, "O tópico principal e as seções relevantes devem ser identificáveis", "SEMANTIC_STRUCTURE", "MEDIUM", "SEMANTIC_TOPIC"),
    (31, "A entidade principal deve ser identificável quando aplicável", "ENTITY_CLARITY", "MEDIUM", "ENTITY_PRIMARY"),
    (32, "Tipos e relações de entidades relevantes devem ter contexto suficiente", "ENTITY_CLARITY", "MEDIUM", "ENTITY_CONTEXT"),
    (33, "Ambiguidade material de entidade deve ser detectável", "ENTITY_CLARITY", "MEDIUM", "ENTITY_AMIGUITY"),
    (34, "Dados estruturados devem ser sintaticamente interpretáveis quando presentes", "STRUCTURED_DATA", "MEDIUM", "STRUCTURED_DATA_SYNTAX"),
    (35, "Tipos e propriedades relevantes dos dados estruturados devem ser identificáveis", "STRUCTURED_DATA", "LOW", "STRUCTURED_DATA_SYNTAX"),
    (36, "Dados estruturados devem permanecer consistentes com o conteúdo visível", "STRUCTURED_DATA", "MEDIUM", "STRUCTURED_DATA_CONSISTENCY"),
    (37, "Entidades dos dados estruturados devem ser consistentes com as entidades observadas", "STRUCTURED_DATA", "MEDIUM", "STRUCTURED_DATA_CONSISTENCY"),
    (38, "A intenção principal do usuário deve ser identificável", "ANSWERABILITY", "HIGH", "PRIMARY_INTENT"),
    (39, "Perguntas primárias relevantes devem receber respostas explícitas quando aplicável", "ANSWERABILITY", "MEDIUM", "PRIMARY_ANSWERS"),
    (40, "As respostas devem conter contexto suficiente", "ANSWERABILITY", "MEDIUM", "PRIMARY_ANSWERS"),
    (41, "Afirmações factuais materiais devem ser explicitamente identificáveis", "CITATION_READINESS", "LOW", "FACTUAL_CLAIMS"),
    (42, "Afirmações factuais devem conter contexto factual suficiente", "CITATION_READINESS", "MEDIUM", "FACTUAL_CONTEXT"),
    (43, "Afirmações numéricas, temporais e quantitativas devem incluir os qualificadores necessários", "CITATION_READINESS", "MEDIUM", "FACTUAL_CONTEXT"),
    (44, "Informações importantes devem ser compreensíveis sem inferência excessiva", "CITATION_READINESS", "MEDIUM", "INFERENCE_LOAD"),
    (45, "Afirmações materiais devem expor atribuição ou evidência de suporte adequada quando necessário", "EVIDENCE_TRUST", "MEDIUM", "ATTRIBUTION"),
    (46, "Publicador, autor ou entidade responsável devem ser identificáveis quando relevante", "EVIDENCE_TRUST", "LOW", "RESPONSIBILITY"),
    (47, "Sinais de publicação e atualidade devem permanecer internamente consistentes", "EVIDENCE_TRUST", "MEDIUM", "FRESHNESS"),
    (48, "Intenções primárias e secundárias relevantes devem estar representadas", "INTENT_COVERAGE", "MEDIUM", "INTENT_SET"),
    (49, "Lacunas materiais de cobertura de intenção devem ser sustentadas por evidência", "INTENT_COVERAGE", "MEDIUM", "INTENT_GAPS"),
)

_M7_EXPECTED_PT = {
    "BR-GEO-028": "o título está presente e representa semanticamente a página",
    "BR-GEO-029": "o conteúdo principal expõe uma hierarquia semântica compreensível",
    "BR-GEO-030": "o tópico principal e as seções relevantes são identificáveis com confiança suficiente",
    "BR-GEO-031": "a entidade principal é identificável quando aplicável",
    "BR-GEO-032": "tipos e relações de entidades relevantes possuem contexto suficiente",
    "BR-GEO-033": "ambiguidade material de entidade está ausente ou é explicitamente identificável",
    "BR-GEO-034": "dados estruturados são sintaticamente interpretáveis quando presentes",
    "BR-GEO-035": "tipos e propriedades relevantes dos dados estruturados são identificáveis",
    "BR-GEO-036": "dados estruturados permanecem consistentes com o conteúdo visível da página",
    "BR-GEO-037": "entidades dos dados estruturados permanecem consistentes com as entidades observadas na página",
    "BR-GEO-038": "a intenção principal do usuário é identificável com evidência",
    "BR-GEO-039": "perguntas primárias relevantes recebem respostas explícitas quando aplicável",
    "BR-GEO-040": "as respostas contêm contexto suficiente",
    "BR-GEO-041": "afirmações factuais materiais são explicitamente identificáveis",
    "BR-GEO-042": "afirmações factuais contêm contexto factual suficiente",
    "BR-GEO-043": "afirmações numéricas, temporais e quantitativas contêm os qualificadores necessários",
    "BR-GEO-044": "informações importantes são compreensíveis sem inferência excessiva",
    "BR-GEO-045": "afirmações materiais expõem atribuição ou suporte adequado quando necessário",
    "BR-GEO-046": "publicador, autor ou entidade responsável é identificável quando relevante",
    "BR-GEO-047": "sinais de publicação e atualidade são internamente consistentes",
    "BR-GEO-048": "uma intenção primária e até cinco intenções secundárias relevantes estão representadas",
    "BR-GEO-049": "lacunas materiais de cobertura de intenção são sustentadas por evidência",
}


def _install_locale_encoder(module: Any) -> None:
    """Force PageSpeed's public locale without replacing provider runtime semantics.

    Both the base M21 client and the bounded external-measurement runtime resolve their
    imported ``urlencode`` symbol at call time. Replacing that symbol lets the current
    no-retry/wall-clock/telemetry wrapper remain intact while converting only a present
    ``locale`` query parameter to pt-BR. CrUX and unrelated query strings are unchanged.
    """
    current = getattr(module, "urlencode", None)
    if not callable(current) or getattr(current, "_rasai_pt_br_locale", False):
        return

    def encode_pt_br(query: Any, *args: Any, **kwargs: Any) -> str:
        normalized = query
        if isinstance(query, Mapping):
            normalized = dict(query)
            if "locale" in normalized:
                normalized["locale"] = "pt-BR"
        elif isinstance(query, (list, tuple)):
            converted: list[Any] = []
            for item in query:
                if isinstance(item, (list, tuple)) and len(item) == 2 and str(item[0]) == "locale":
                    converted.append((item[0], "pt-BR"))
                else:
                    converted.append(item)
            normalized = converted
        return current(normalized, *args, **kwargs)

    encode_pt_br._rasai_pt_br_locale = True  # type: ignore[attr-defined]
    encode_pt_br._rasai_original = current  # type: ignore[attr-defined]
    module.urlencode = encode_pt_br


def _install_web_performance_contract() -> None:
    from rasai import external_measurement_runtime
    from rasai import m21_web_performance as m21

    def assess_cwv(field: Mapping[str, Any] | None) -> dict[str, str | None]:
        if not field:
            return {
                "lcp_assessment": None,
                "inp_assessment": None,
                "cls_assessment": None,
                "cwv_assessment": "UNAVAILABLE",
            }

        def assess(value: Any, good_max: float, needs_improvement_max: float) -> str | None:
            if value is None:
                return None
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return None
            if numeric <= good_max:
                return "GOOD"
            if numeric <= needs_improvement_max:
                return "NEEDS_IMPROVEMENT"
            return "POOR"

        lcp = assess(field.get("lcp_p75_ms"), 2500.0, 4000.0)
        inp = assess(field.get("inp_p75_ms"), 200.0, 500.0)
        cls = assess(field.get("cls_p75"), 0.1, 0.25)
        components = (lcp, inp, cls)
        if any(value is None for value in components):
            overall = "INCOMPLETE"
        else:
            overall = "PASS" if all(value == "GOOD" for value in components) else "FAIL"
        return {
            "lcp_assessment": lcp,
            "inp_assessment": inp,
            "cls_assessment": cls,
            "cwv_assessment": overall,
        }

    assess_cwv._rasai_prepublication_correctness = True  # type: ignore[attr-defined]
    m21._assess_cwv = assess_cwv

    # Do not replace PageSpeedInsightsClient.run here. The external measurement runtime
    # owns its wall-clock deadline, no-retry policy and operational telemetry. Only the
    # provider locale is a presentation contract and is changed at URL encoding time.
    _install_locale_encoder(m21)
    _install_locale_encoder(external_measurement_runtime)


def _install_experience_apdex_contract() -> None:
    from rasai import m25_apdex_experience as m25
    from rasai import m25_reporting

    def qualifying_error(item: Any, scope: str) -> bool:
        """Return only errors that belong to the configured responsibility scope.

        Browser console/page errors do not carry a reliable first-party origin in the
        current measurement contract. They therefore remain diagnostic in
        ``first-party`` mode and may force frustration only in ``all`` mode.
        """
        if str(getattr(item, "status", "")) == "APPLICATION_ERROR":
            return True
        normalized = str(scope or "").strip().casefold()
        if normalized == "navigation":
            return False
        if normalized == "first-party":
            return (
                int(getattr(item, "first_party_request_failed_count", 0) or 0) > 0
                or int(getattr(item, "first_party_http_error_count", 0) or 0) > 0
            )
        return (
            int(getattr(item, "javascript_error_count", 0) or 0) > 0
            or int(getattr(item, "console_error_count", 0) or 0) > 0
            or int(getattr(item, "request_failed_count", 0) or 0) > 0
            or int(getattr(item, "http_error_count", 0) or 0) > 0
        )

    def error_policy_note(run: sqlite3.Row) -> str:
        if not bool(run["errors_affect_apdex"]):
            return "Erros observados permanecem diagnósticos e não forçam classificação Frustrada nesta execução."
        scope = str(run["error_scope"] or "").strip().casefold()
        if scope == "navigation":
            return (
                "Somente falhas ou estado de erro da navegação qualificam a ação por erro; erros JavaScript, "
                "erros de console e falhas de sub-requisições permanecem diagnósticos."
            )
        if scope == "first-party":
            return (
                "Somente falhas de requisição ou respostas HTTP com erro atribuídas a recursos próprios podem "
                "forçar classificação Frustrada. Erros JavaScript e de console sem origem própria confiável "
                "permanecem diagnósticos."
            )
        return (
            "Erros JavaScript, erros de console, falhas de requisição e respostas HTTP com erro observados "
            "podem forçar classificação Frustrada."
        )

    original_contract_context = m25_reporting._measurement_contract_context

    def measurement_contract_context(configuration: dict[str, Any]) -> dict[str, str]:
        result = original_contract_context(configuration)
        scope = str(configuration.get("error_scope") or "").strip().casefold()
        if scope == "first-party":
            result["runtime_errors"] = (
                "Erros JavaScript e de console sem atribuição confiável à origem própria permanecem diagnósticos; "
                "eles não forçam a classificação Frustrada no escopo first-party."
            )
            result["request_errors"] = (
                "Falhas de requisição e respostas HTTP ≥ 400 qualificam a ação somente quando pertencem a "
                "recursos próprios. Erro HTTP da navegação principal continua qualificável como erro da aplicação."
            )
        elif scope == "navigation":
            result["runtime_errors"] = (
                "Erros JavaScript, de console e de sub-requisições permanecem diagnósticos no escopo de navegação."
            )
        elif scope == "all":
            result["runtime_errors"] = (
                "Erros JavaScript e de console observados podem qualificar a ação como Frustrada no escopo amplo."
            )
        return result

    qualifying_error._rasai_prepublication_correctness = True  # type: ignore[attr-defined]
    error_policy_note._rasai_prepublication_correctness = True  # type: ignore[attr-defined]
    measurement_contract_context._rasai_prepublication_correctness = True  # type: ignore[attr-defined]
    m25._qualifying_error = qualifying_error
    m25_reporting._error_policy_note = error_policy_note
    m25_reporting._measurement_contract_context = measurement_contract_context


def _install_semantic_language_contract() -> None:
    """Make the semantic rule catalogue persist pt-BR human text for new audits."""
    from rasai import m7
    from rasai import m16_root_cause as m16

    specs = tuple(
        (
            number,
            title,
            category,
            getattr(m7.Severity, severity_name),
            scoring_group,
        )
        for number, title, category, severity_name, scoring_group in _M7_SPECS_PT
    )
    definitions = tuple(
        m7.RuleDefinition(
            f"BR-GEO-{number:03d}",
            title,
            category,
            category,
            m7.RuleScope.SNAPSHOT,
            severity=severity,
            basis="STANDARD" if number in {28, 34, 35} else "HEURISTIC",
            scoring_group=scoring_group,
        )
        for number, title, category, severity, scoring_group in specs
    )
    m7._RULE_SPECS = specs
    m7._M7_DEFINITIONS = definitions
    m7._EXPECTED = dict(_M7_EXPECTED_PT)

    # Root-cause copy must use the same vocabulary as the semantic contract.
    m16._CAUSE_SUMMARY.update(
        {
            "BR-GEO-041": "Afirmações factuais materiais não estão suficientemente distinguíveis ou explícitas.",
            "BR-GEO-042": "Afirmações factuais relevantes carecem do contexto necessário para interpretação segura.",
            "BR-GEO-043": "Afirmações numéricas, temporais ou quantitativas carecem dos qualificadores necessários.",
            "BR-GEO-045": "Afirmações materiais carecem de atribuição ou evidência de suporte quando necessário.",
            "BR-GEO-046": "A entidade responsável, o autor ou o publicador não está identificável quando relevante.",
        }
    )


def _improvement_run(workspace: Any, audit_id: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='improvement_intelligence_runs'"
        ).fetchone()
        if exists is None:
            return None
        row = connection.execute(
            "SELECT * FROM improvement_intelligence_runs WHERE audit_id=? ORDER BY rowid DESC LIMIT 1",
            (audit_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


def _install_improvement_fulfillment_contract() -> None:
    """Keep CAT-08 mandatory fulfillment visible even while the console isolates env vars."""
    from rasai import fulfillment_execution_contract as contract
    from rasai.audit_fulfillment import (
        FAILED_RETRYABLE,
        REPLAY_SAFE,
        SUCCESS,
        register_work_item,
        set_work_item_status,
    )
    from rasai.improvement_intelligence import ENABLED_ENV

    current = contract._reconcile_requested_improvement
    if getattr(current, "_rasai_prepublication_correctness", False):
        return

    def reconcile_improvement(workspace: Any, audit_id: str) -> None:
        if contract._truthy(os.environ.get(ENABLED_ENV)):
            current(workspace, audit_id)
            return

        run = _improvement_run(workspace, audit_id)
        if run is None:
            return

        raw_domains = run.get("domains_json")
        try:
            domains = json.loads(str(raw_domains)) if raw_domains else []
        except (TypeError, ValueError, json.JSONDecodeError):
            domains = []
        configuration = {
            "requested": True,
            "provider": str(run.get("provider") or ""),
            "model": str(run.get("model") or ""),
            "reasoning": str(run.get("reasoning") or ""),
            "domains": domains if isinstance(domains, list) else [],
            "max_recommendations": run.get("max_recommendations"),
            "language": run.get("analysis_language"),
        }
        register_work_item(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            required=True,
            temporal_mode=REPLAY_SAFE,
            retryable=True,
            configuration=configuration,
        )
        run_status = str(run.get("status") or "").strip().upper()
        if run_status == "COMPLETE":
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="IMPROVEMENT_INTELLIGENCE",
                status=SUCCESS,
                result_ref="improvement-intelligence:effective",
                retryable=False,
            )
            return

        reason = str(run.get("reason") or "Análise profunda não concluiu sem limitações")
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status=FAILED_RETRYABLE,
            error_class="AI_ANALYSIS",
            error_code=run_status or "IMPROVEMENT_INCOMPLETE",
            error_message=contract._safe_detail(reason),
            retryable=True,
        )

    reconcile_improvement._rasai_prepublication_correctness = True  # type: ignore[attr-defined]
    reconcile_improvement._rasai_original = current  # type: ignore[attr-defined]
    contract._reconcile_requested_improvement = reconcile_improvement


def install() -> None:
    """Install the current canonical pre-publication contracts exactly once."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_web_performance_contract()
    _install_experience_apdex_contract()
    _install_semantic_language_contract()
    _install_improvement_fulfillment_contract()
    _INSTALLED = True


__all__ = ["install"]
