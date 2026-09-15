"""Session-local audit catalog plan, readiness and execution projection.

Console-only: this module maps an operator selection onto existing State fields without
changing collectors, scoring, provider routing, retries or fulfillment rules.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import os
from types import ModuleType
from typing import Any, Iterator

from rasai.audit_catalog import (
    AI_NONE,
    AI_OPTIONAL,
    AI_REQUIRED,
    CATALOGS,
    CATALOG_VERSION,
    PRODUCER_CATALOG_IDS,
    AuditCatalog,
)


@dataclass(slots=True)
class _Plan:
    selected: set[str] = field(default_factory=set)
    # Optional AI is an execution choice, not an implication of having a provider configured.
    # Required-AI catalogs override this flag at resolution time.
    ai_enabled: bool = False


_PLANS: dict[int, tuple[Any, _Plan]] = {}


def _plan(state: Any) -> _Plan:
    key = id(state)
    entry = _PLANS.get(key)
    if entry is not None and entry[0] is state:
        return entry[1]
    _PLANS.pop(key, None)
    selected: set[str] = set()
    if bool(getattr(state, "web_performance", False)):
        selected.add("CAT-04")
    if tuple(getattr(state, "search_queries", ()) or ()):
        selected.add("CAT-05")
    if bool(getattr(state, "synthetic_apdex", False)):
        selected.add("CAT-06")
    if bool(getattr(state, "apdex_experience", False)):
        selected.update(("CAT-06", "CAT-07"))
    if bool(getattr(state, "improvement_enabled", False)):
        selected.add("CAT-08")
    if bool(getattr(state, "content_remediation", False) or getattr(state, "technical_remediation", False)):
        selected.add("CAT-09")
    explicit_ai_work = bool(
        getattr(state, "improvement_enabled", False)
        or getattr(state, "content_remediation", False)
        or getattr(state, "technical_remediation", False)
    )
    result = _Plan(selected, ai_enabled=explicit_ai_work)
    _PLANS[key] = (state, result)
    return result


def selected_catalog_ids(state: Any) -> tuple[str, ...]:
    selected = _plan(state).selected
    return tuple(item.id for item in CATALOGS if item.id in selected)


def set_selected_catalog_ids(state: Any, catalog_ids: tuple[str, ...] | list[str]) -> None:
    allowed = {item.id for item in CATALOGS}
    selected = {str(item).strip().upper() for item in catalog_ids if str(item).strip()}
    unknown = selected - allowed
    if unknown:
        raise ValueError("catálogo(s) desconhecido(s): " + ", ".join(sorted(unknown)))
    if "CAT-07" in selected:
        selected.add("CAT-06")
    plan = _plan(state)
    plan.selected = selected
    if any(item.id in selected and item.ai_mode == AI_REQUIRED for item in CATALOGS):
        plan.ai_enabled = True


def is_selected(state: Any, catalog_id: str) -> bool:
    return catalog_id in _plan(state).selected


def ai_required(state: Any) -> bool:
    selected = _plan(state).selected
    return any(item.id in selected and item.ai_mode == AI_REQUIRED for item in CATALOGS)


def ai_optional(state: Any) -> bool:
    selected = _plan(state).selected
    return any(item.id in selected and item.ai_mode == AI_OPTIONAL for item in CATALOGS)


def ai_execution_enabled(state: Any) -> bool:
    if ai_required(state):
        return True
    return ai_optional(state) and bool(_plan(state).ai_enabled)


def set_ai_execution_enabled(state: Any, enabled: bool) -> None:
    if not enabled and ai_required(state):
        raise ValueError("IA é obrigatória enquanto houver catálogo REQUIRED selecionado")
    _plan(state).ai_enabled = bool(enabled)


def select_catalog(state: Any, catalog: AuditCatalog) -> None:
    plan = _plan(state)
    plan.selected.add(catalog.id)
    if catalog.id == "CAT-07":
        plan.selected.add("CAT-06")
    if catalog.ai_mode == AI_REQUIRED:
        plan.ai_enabled = True


def deselect_catalog(state: Any, catalog: AuditCatalog) -> bool:
    if catalog.id == "CAT-06" and "CAT-07" in _plan(state).selected:
        state.error = "Apdex de navegação é dependência do Apdex de experiência; remova CAT-07 primeiro."
        return False
    _plan(state).selected.discard(catalog.id)
    return True


def _capability_by_key(key: str) -> Any:
    from rasai.console_ui_catalog import CAPABILITIES
    return next((item for item in CAPABILITIES if item.key == key), None)


def raw_capability_status(state: Any, key: str) -> tuple[str, str]:
    from rasai.console_ui_catalog import capability_status
    capability = _capability_by_key(key)
    if capability is None:
        return "NÃO CONFIGURADO", "capacidade não publicada na composição atual"
    return capability_status(state, capability)


def _single_status(state: Any, key: str) -> tuple[str, str]:
    status, detail = raw_capability_status(state, key)
    value = str(status).strip().upper()
    if value in {"CONFIGURAR", "BLOQUEADO", "ERRO", "INDISPONÍVEL", "DESABILITADO", "NÃO CONFIGURADO"}:
        return "BLOQUEADO", detail
    if value in {"APTO COM LIMITAÇÕES", "PARCIAL"}:
        return "APTO COM LIMITAÇÕES", detail
    return "APTO", detail


def _search_status(state: Any) -> tuple[str, str]:
    serp_status, serp_detail = raw_capability_status(state, "search-intelligence")
    gsc_status, gsc_detail = raw_capability_status(state, "google-search-console")
    queries = tuple(getattr(state, "search_queries", ()) or ())
    try:
        from rasai.gsc_scope import MODE_REQUIRED, gsc_request_mode
        gsc_required = gsc_request_mode(os.environ) == MODE_REQUIRED
    except (ImportError, ValueError):
        gsc_required = False
    serp_ready = bool(queries) and str(serp_status).upper() == "APTO"
    gsc_ready = str(gsc_status).upper() in {"APTO", "AUTOMÁTICO"}
    blocked_values = {"CONFIGURAR", "BLOQUEADO", "ERRO", "INDISPONÍVEL"}
    if gsc_required and not gsc_ready:
        return "BLOQUEADO", f"GSC obrigatório: {gsc_detail}"
    if queries and str(serp_status).upper() in blocked_values:
        return "BLOQUEADO", f"SERP solicitado: {serp_detail}"
    if serp_ready and gsc_ready:
        return "APTO", "SERP e GSC possuem readiness suficiente para o alvo"
    if serp_ready:
        if str(gsc_status).upper() in blocked_values:
            return "APTO COM LIMITAÇÕES", f"SERP apto; GSC opcional: {gsc_detail}"
        return "APTO", f"SERP apto ({len(queries)} termo(s)); GSC não é requisito deste plano"
    if gsc_ready:
        return "APTO", "GSC possui readiness suficiente; SERP não foi solicitado por termos"
    if str(gsc_status).upper() in blocked_values:
        return "BLOQUEADO", "nenhuma fonte Search está apta; configure termos SERP ou corrija GSC: " + gsc_detail
    return "BLOQUEADO", "configure termos SERP ou uma fonte GSC aplicável para produzir Search Intelligence"


def catalog_status(state: Any, catalog: AuditCatalog) -> tuple[str, str]:
    if not is_selected(state, catalog.id):
        return "NÃO SELECIONADO", "fora do plano da próxima auditoria"
    if not str(getattr(state, "target", "") or "").strip():
        return "BLOQUEADO", "informe a URL/entrada da auditoria"
    if catalog.id == "CAT-01":
        return "APTO", "baseline técnico utiliza a configuração vigente do alvo"
    if catalog.id == "CAT-02":
        return "APTO", "auditoria determinística de acessibilidade disponível"
    if catalog.id == "CAT-03":
        try:
            from rasai.content_context import configured_content_analysis_context
            configured_content_analysis_context()
        except (ImportError, ValueError) as exc:
            return "BLOQUEADO", f"contexto de conteúdo inválido: {exc}"
        return "APTO", "validações estruturais disponíveis; IA semântica é opcional"
    if catalog.id == "CAT-04":
        if not bool(getattr(state, "web_performance", False)):
            return "BLOQUEADO", "Web Performance está desabilitado; habilite/configure a análise"
        return _single_status(state, "web-performance")
    if catalog.id == "CAT-05":
        return _search_status(state)
    if catalog.id == "CAT-06":
        if not bool(getattr(state, "synthetic_apdex", False)):
            return "BLOQUEADO", "Apdex de navegação ainda não foi habilitado/configurado"
        return _single_status(state, "apdex-navigation")
    if catalog.id == "CAT-07":
        if "CAT-06" not in _plan(state).selected:
            return "BLOQUEADO", "CAT-07 exige CAT-06 como dependência técnica"
        if not bool(getattr(state, "apdex_experience", False)):
            return "BLOQUEADO", "Apdex de experiência ainda não foi habilitado/configurado"
        return _single_status(state, "apdex-experience")
    producers = bool(_plan(state).selected & PRODUCER_CATALOG_IDS)
    if catalog.id == "CAT-08":
        if not producers:
            return "BLOQUEADO", "análise profunda exige ao menos um catálogo produtor de evidências"
        return _single_status(state, "deep-analysis")
    if catalog.id == "CAT-09":
        if not producers:
            return "BLOQUEADO", "remediações exigem ao menos um catálogo produtor de evidências"
        if not ai_execution_enabled(state):
            return "APTO", "remediações determinísticas; enriquecimento por IA não foi escolhido para esta execução"
        status, detail = _single_status(state, "remediation")
        if status == "BLOQUEADO":
            return status, detail
        return "APTO", "remediações determinísticas permanecem válidas; IA enriquece somente o advisory solicitado"
    return "BLOQUEADO", "catálogo desconhecido"


def _ai_provider(state: Any) -> str:
    return str(getattr(state, "ai_provider", "none") or "none").strip().casefold()


def ai_provider_readiness(state: Any) -> tuple[bool, str]:
    """Resolve readiness through the canonical provider registry without making calls."""
    provider = _ai_provider(state)
    if provider == "none":
        return False, "IA principal não configurada"
    try:
        from rasai.console_config import provider_capabilities

        capability = provider_capabilities(
            blocks=getattr(state, "runtime_blocks", {}),
        ).get(provider)
    except (ImportError, KeyError, TypeError, ValueError) as exc:
        return False, f"não foi possível validar a IA principal: {exc}"
    if capability is None:
        return False, f"provider de IA desconhecido: {provider}"
    return bool(capability.available), str(capability.reason or "")


def plan_status(state: Any) -> tuple[str, str]:
    selected = tuple(item for item in CATALOGS if is_selected(state, item.id))
    if not selected:
        return "BLOQUEADO", "selecione ao menos um catálogo"
    blockers: list[str] = []
    limitations: list[str] = []
    for item in selected:
        status, detail = catalog_status(state, item)
        if status == "BLOQUEADO":
            blockers.append(f"{item.id}: {detail}")
        elif status == "APTO COM LIMITAÇÕES":
            limitations.append(f"{item.id}: {detail}")
    required = tuple(item for item in selected if item.ai_mode == AI_REQUIRED)
    optional = tuple(item for item in selected if item.ai_mode == AI_OPTIONAL)
    ai_ready, ai_detail = ai_provider_readiness(state)
    if required and not ai_ready:
        blockers.append(
            "IA principal é obrigatória para "
            + ", ".join(item.id for item in required)
            + (f": {ai_detail}" if ai_detail else "")
        )
    elif optional and ai_execution_enabled(state) and not ai_ready:
        blockers.append(
            "execução com IA foi escolhida, mas a IA principal não está apta"
            + (f": {ai_detail}" if ai_detail else "")
        )
    if blockers:
        return "BLOQUEADO", blockers[0] if len(blockers) == 1 else f"{len(blockers)} pendências obrigatórias"
    if limitations:
        return "APTO COM LIMITAÇÕES", f"{len(limitations)} limitação(ões) não bloqueante(s)"
    return "APTO", "catálogos selecionados possuem configuração mínima conhecida"


def _optional_environment_switches() -> tuple[str, ...]:
    """Environment toggles owned by CAT-05 observability sources.

    Credentials and non-boolean parameters are deliberately excluded: the projection only
    suppresses execution, never rewrites the operator's configuration data.
    """
    try:
        from rasai.external_observability_policy import (
            CLARITY_ENABLED_ENV,
            COMMON_CRAWL_ENABLED_ENV,
            CRUX_HISTORY_ENABLED_ENV,
        )
    except ImportError:
        return ()
    return (CRUX_HISTORY_ENABLED_ENV, CLARITY_ENABLED_ENV, COMMON_CRAWL_ENABLED_ENV)


@contextmanager
def project_plan(state: Any) -> Iterator[None]:
    selected = _plan(state).selected
    names = (
        "web_performance", "search_queries", "synthetic_apdex", "apdex_experience",
        "improvement_enabled", "content_remediation", "technical_remediation",
        "ai_provider", "ai_model", "ai_reasoning",
    )
    saved = {name: getattr(state, name) for name in names if hasattr(state, name)}
    environment_switches = ("RASAI_GSC_ENABLED", *_optional_environment_switches())
    environment_snapshot = {
        name: (name in os.environ, os.environ.get(name))
        for name in environment_switches
    }
    try:
        if "CAT-04" not in selected and hasattr(state, "web_performance"):
            state.web_performance = False
        if "CAT-05" not in selected:
            if hasattr(state, "search_queries"):
                state.search_queries = ()
            for name in environment_switches:
                os.environ[name] = "false"
        if "CAT-06" not in selected and hasattr(state, "synthetic_apdex"):
            state.synthetic_apdex = False
        if "CAT-07" not in selected and hasattr(state, "apdex_experience"):
            state.apdex_experience = False
        if "CAT-08" not in selected and hasattr(state, "improvement_enabled"):
            state.improvement_enabled = False
        if "CAT-09" not in selected or not ai_execution_enabled(state):
            if hasattr(state, "content_remediation"):
                state.content_remediation = False
            if hasattr(state, "technical_remediation"):
                state.technical_remediation = False
        if not ai_execution_enabled(state) and hasattr(state, "ai_provider"):
            state.ai_provider = "none"
            if hasattr(state, "ai_model"):
                state.ai_model = None
            if hasattr(state, "ai_reasoning"):
                state.ai_reasoning = None
        yield
    finally:
        for name, value in saved.items():
            setattr(state, name, value)
        for name, (existed, value) in environment_snapshot.items():
            if existed and value is not None:
                os.environ[name] = value
            else:
                os.environ.pop(name, None)


def execution_ready(console_module: ModuleType, state: Any) -> tuple[str, str]:
    status, detail = plan_status(state)
    if status == "BLOQUEADO":
        return status, detail
    try:
        with project_plan(state):
            ready, reason = console_module._execution_readiness(state)
    except (OSError, ValueError, UnicodeError) as exc:
        return "BLOQUEADO", str(exc)
    if not ready:
        return "BLOQUEADO", reason
    return status, detail if status != "APTO" else reason


def catalog_snapshot(state: Any) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for item in CATALOGS:
        status, detail = catalog_status(state, item)
        rows.append({
            "catalog_version": CATALOG_VERSION,
            "catalog_id": item.id,
            "label": item.label,
            "selected": is_selected(state, item.id),
            "status": status,
            "detail": detail,
            "ai_mode": item.ai_mode,
            "ai_execution_enabled": ai_execution_enabled(state) and item.ai_mode != AI_NONE,
            "result": item.expected_result,
            "capability_ids": item.capability_ids,
        })
    return tuple(rows)
