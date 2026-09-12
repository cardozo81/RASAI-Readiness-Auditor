"""Composable, session-only execution profiles for the interactive console.

Profiles are an operator UX overlay. They never rewrite canonical defaults, never persist
into rasai-console.ini or Windows environment scopes, and never carry credentials.
They are deliberately restricted to one explicit URL so dependency/readiness semantics
remain unambiguous.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import builtins
import os
from types import ModuleType
from typing import Any, Iterator

from rasai.console_config import provider_capabilities
from rasai.console_cost import ExposureEstimate, estimate_exposure
from rasai.console_m23 import synthetic_load_summary
from rasai.console_ui import CYAN, DIM, GREEN, RED, YELLOW, paint
from rasai.content_context import configured_content_analysis_context
from rasai.improvement_intelligence import ENABLED_ENV as IMPROVEMENT_ENABLED_ENV

PROFILE_CHOICE = "F"
AI_OFF = "off"
AI_IF_AVAILABLE = "if-available"


@dataclass(frozen=True, slots=True)
class ExecutionModule:
    id: str
    label: str
    description: str
    lighthouse_categories: tuple[str, ...] = ()
    cost_note: str = "Sem custo externo adicional específico do módulo."
    dependency_note: str = "Sem preenchimento prévio adicional."


@dataclass(frozen=True, slots=True)
class ExecutionProfile:
    id: str
    label: str
    description: str
    modules: tuple[str, ...]


@dataclass(slots=True)
class SessionProfile:
    profile_id: str
    label: str
    modules: tuple[str, ...]
    ai_mode: str
    baseline: dict[str, object]
    manual_overrides: set[str] = field(default_factory=set)


MODULES: tuple[ExecutionModule, ...] = (
    ExecutionModule(
        "seo",
        "SEO / Search Readiness",
        "Prioriza sinais técnicos de descoberta/indexabilidade e Lighthouse SEO/boas práticas; o core determinístico continua canônico.",
        ("seo", "best-practices"),
        "Pode gerar chamadas PageSpeed/Lighthouse e CrUX conforme credenciais/configuração. IA é opcional e separada.",
        "GSC permanece condicionado a token OAuth + propriedade quando configurado; o perfil não inventa propriedade nem credencial.",
    ),
    ExecutionModule(
        "geo",
        "GEO / AI Readiness",
        "Prioriza evidências para descoberta/consumo por agentes e conteúdo semântico, incluindo Lighthouse SEO/agentic-browsing.",
        ("seo", "best-practices", "agentic-browsing"),
        "Pode gerar chamadas PageSpeed/Lighthouse. Se IA padrão for usada, há tokens/custo do provider configurado.",
        "YMYL e demais contextos editoriais permanecem AUTO ou explicitamente configurados pelo usuário; nunca são inferidos como fato pelo preset.",
    ),
    ExecutionModule(
        "performance",
        "Performance",
        "Prioriza Lighthouse Performance, boas práticas e dados de campo disponíveis sem alterar os cálculos metodológicos existentes.",
        ("performance", "best-practices"),
        "Pode consumir quota PageSpeed/CrUX; não presume cobrança monetária quando o provider expõe apenas quota.",
    ),
    ExecutionModule(
        "accessibility",
        "Acessibilidade",
        "Prioriza Lighthouse Accessibility e boas práticas, preservando as demais verificações determinísticas já existentes.",
        ("accessibility", "best-practices"),
        "Pode gerar chamadas PageSpeed/Lighthouse; sem IA obrigatória.",
    ),
    ExecutionModule(
        "web-quality",
        "Web Quality",
        "Combina boas práticas, SEO e acessibilidade como visão de qualidade Web; validadores/observability já configurados continuam sob seus contratos próprios.",
        ("best-practices", "seo", "accessibility"),
        "Pode gerar chamadas PageSpeed/Lighthouse e serviços externos já habilitados no ambiente (ex.: W3C/MDN).",
    ),
    ExecutionModule(
        "search-intelligence",
        "Search Intelligence / SERP",
        "Executa observação SERP associada ao AUD quando os termos transitórios desta sessão estiverem configurados.",
        (),
        "Consome requests/quota do provider SERP conforme quantidade de termos, profundidade e paginação.",
        "Exige termos no item T, provider SERP apto e credencial quando o modo for live. O preset nunca cria termos.",
    ),
    ExecutionModule(
        "experience",
        "Experiência sintética",
        "Inclui medições Synthetic Apdex já configuradas pelo operador para a URL desta execução.",
        (),
        "Sem API paga própria, mas gera navegações reais, CPU/tempo local e carga HTTP contra o alvo.",
        "Exige Synthetic Apdex e/ou Experience Apdex previamente configurado. O preset não inventa threshold, amostras ou carga.",
    ),
    ExecutionModule(
        "deep-analysis",
        "Análise profunda URL",
        "Inclui Improvement Intelligence evidence-bound, mantendo segurança passiva e sem alterar SARI/SCORE-GEO.",
        (),
        "Gera chamadas adicionais de IA com provider/model/reasoning próprios da análise profunda.",
        "Exige item 13 habilitado e provider/modelo deep válidos. A IA padrão do perfil é independente desta IA profunda.",
    ),
)

MODULE_BY_ID = {item.id: item for item in MODULES}
_CATEGORY_ORDER = ("performance", "accessibility", "best-practices", "seo", "agentic-browsing")

PROFILES: tuple[ExecutionProfile, ...] = (
    ExecutionProfile("seo", "SEO / Search Readiness", "Auditoria orientada a search readiness com Lighthouse SEO e boas práticas.", ("seo",)),
    ExecutionProfile("geo", "GEO / AI Readiness", "Auditoria orientada a consumo por agentes/IA e semântica, preservando contexto editorial explícito/AUTO.", ("geo",)),
    ExecutionProfile("performance", "Performance", "Foco em laboratório/field performance dentro das integrações disponíveis.", ("performance",)),
    ExecutionProfile("accessibility", "Acessibilidade", "Foco em evidências de acessibilidade e boas práticas.", ("accessibility",)),
    ExecutionProfile("web-quality", "Web Quality", "Visão concentrada de boas práticas, SEO e acessibilidade.", ("web-quality",)),
    ExecutionProfile("seo-geo", "SEO + GEO", "Combina search readiness e AI readiness na mesma execução.", ("seo", "geo")),
    ExecutionProfile("seo-geo-performance", "SEO + GEO + Performance", "Combina search/AI readiness com performance de laboratório/campo.", ("seo", "geo", "performance")),
    ExecutionProfile("search-intelligence", "Search Intelligence / SERP", "Observação SERP para termos explicitamente fornecidos nesta sessão.", ("search-intelligence",)),
    ExecutionProfile("experience", "Experiência sintética", "Executa somente medições sintéticas que já tenham sido parametrizadas pelo operador.", ("experience",)),
    ExecutionProfile("deep-analysis", "Análise profunda URL", "Executa a análise evidence-bound adicional quando o item 13 já estiver corretamente configurado.", ("deep-analysis",)),
    ExecutionProfile(
        "complete-safe",
        "Completo seguro",
        "Combina SEO, GEO, Performance, Acessibilidade e Web Quality sem ativar automaticamente SERP, carga sintética ou análise profunda.",
        ("seo", "geo", "performance", "accessibility", "web-quality"),
    ),
)

_PROFILE_BY_ID = {item.id: item for item in PROFILES}
_SESSIONS: dict[int, SessionProfile] = {}


def _baseline(state: Any) -> dict[str, object]:
    return {
        "web_performance": bool(getattr(state, "web_performance", False)),
        "lighthouse_categories": str(getattr(state, "lighthouse_categories", "")),
        "ai_provider": str(getattr(state, "ai_provider", "none")),
        "content_remediation": bool(getattr(state, "content_remediation", False)),
        "technical_remediation": bool(getattr(state, "technical_remediation", False)),
        "synthetic_apdex": bool(getattr(state, "synthetic_apdex", False)),
        "apdex_experience": bool(getattr(state, "apdex_experience", False)),
        "search_queries": tuple(getattr(state, "search_queries", ()) or ()),
        "improvement_enabled": os.environ.get(IMPROVEMENT_ENABLED_ENV),
    }


def active_profile(state: Any) -> SessionProfile | None:
    return _SESSIONS.get(id(state))


def clear_profile(state: Any) -> None:
    _SESSIONS.pop(id(state), None)


def set_profile(
    state: Any,
    *,
    profile_id: str,
    modules: tuple[str, ...] | None = None,
    ai_mode: str = AI_OFF,
    label: str | None = None,
) -> SessionProfile:
    if str(getattr(state, "input_mode", "")).casefold() != "url" or not str(getattr(state, "target", "")).strip():
        raise ValueError("Perfis de execução exigem uma URL única informada no item 1")
    if ai_mode not in {AI_OFF, AI_IF_AVAILABLE}:
        raise ValueError("modo de IA do perfil inválido")
    if modules is None:
        definition = _PROFILE_BY_ID.get(profile_id)
        if definition is None:
            raise ValueError(f"perfil desconhecido: {profile_id}")
        selected = definition.modules
        resolved_label = definition.label
    else:
        selected = tuple(dict.fromkeys(modules))
        if not selected:
            raise ValueError("perfil personalizado exige ao menos um módulo")
        unknown = tuple(item for item in selected if item not in MODULE_BY_ID)
        if unknown:
            raise ValueError("módulo(s) desconhecido(s): " + ", ".join(unknown))
        resolved_label = label or "Personalizado"
    session = SessionProfile(profile_id, resolved_label, selected, ai_mode, _baseline(state))
    _SESSIONS[id(state)] = session
    return session


def _manual(session: SessionProfile, state: Any, domain: str) -> bool:
    if domain in session.manual_overrides:
        return True
    if domain == "web":
        return (
            bool(getattr(state, "web_performance", False)) != session.baseline["web_performance"]
            or str(getattr(state, "lighthouse_categories", "")) != session.baseline["lighthouse_categories"]
        )
    return False


def _profile_categories(session: SessionProfile) -> tuple[str, ...]:
    selected: set[str] = set()
    for module_id in session.modules:
        selected.update(MODULE_BY_ID[module_id].lighthouse_categories)
    return tuple(item for item in _CATEGORY_ORDER if item in selected)


def _effective_ai_provider(state: Any) -> str:
    capabilities = provider_capabilities(blocks=getattr(state, "runtime_blocks", {}))
    current = str(getattr(state, "ai_provider", "none"))
    capability = capabilities.get(current)
    if current != "none" and capability is not None and capability.available:
        return current
    auto = capabilities.get("auto")
    return "auto" if auto is not None and auto.available else "none"


@contextmanager
def effective_profile(state: Any, session: SessionProfile | None = None) -> Iterator[None]:
    """Temporarily project a profile onto the live state/environment and restore it."""
    current = session or active_profile(state)
    if current is None:
        yield
        return

    fields = (
        "web_performance",
        "lighthouse_categories",
        "ai_provider",
        "ai_model",
        "ai_reasoning",
        "content_remediation",
        "technical_remediation",
        "synthetic_apdex",
        "apdex_experience",
        "search_queries",
    )
    saved = {name: getattr(state, name) for name in fields if hasattr(state, name)}
    improvement_present = IMPROVEMENT_ENABLED_ENV in os.environ
    improvement_previous = os.environ.get(IMPROVEMENT_ENABLED_ENV)
    try:
        categories = _profile_categories(current)
        if not _manual(current, state, "web"):
            state.web_performance = bool(categories)
            if categories:
                state.lighthouse_categories = ",".join(categories)

        if "ai" not in current.manual_overrides:
            if current.ai_mode == AI_OFF:
                state.ai_provider = "none"
                state.ai_model = None
                state.ai_reasoning = None
            else:
                provider = _effective_ai_provider(state)
                state.ai_provider = provider
                if provider in {"none", "auto"}:
                    state.ai_model = None
                    state.ai_reasoning = None
        if state.ai_provider == "none" and "remediation" not in current.manual_overrides:
            state.content_remediation = False
            state.technical_remediation = False

        if "search" not in current.manual_overrides and "search-intelligence" not in current.modules and hasattr(state, "search_queries"):
            state.search_queries = ()

        if "experience" not in current.manual_overrides and "experience" not in current.modules:
            if hasattr(state, "synthetic_apdex"):
                state.synthetic_apdex = False
            if hasattr(state, "apdex_experience"):
                state.apdex_experience = False

        if "deep" not in current.manual_overrides and "deep-analysis" not in current.modules:
            os.environ[IMPROVEMENT_ENABLED_ENV] = "false"

        yield
    finally:
        for name, value in saved.items():
            setattr(state, name, value)
        if improvement_present:
            assert improvement_previous is not None
            os.environ[IMPROVEMENT_ENABLED_ENV] = improvement_previous
        else:
            os.environ.pop(IMPROVEMENT_ENABLED_ENV, None)


def dependency_status(state: Any, session: SessionProfile | None = None) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    current = session or active_profile(state)
    if current is None:
        return True, (), ()
    blockers: list[str] = []
    advisories: list[str] = []
    if str(getattr(state, "input_mode", "")).casefold() != "url" or not str(getattr(state, "target", "")).strip():
        blockers.append("perfil exige URL única explícita no item 1")
    if "search-intelligence" in current.modules and not tuple(getattr(state, "search_queries", ()) or ()):
        blockers.append("Search Intelligence selecionado: configure os termos transitórios no item T")
    if "experience" in current.modules and not (
        bool(getattr(state, "synthetic_apdex", False)) or bool(getattr(state, "apdex_experience", False))
    ):
        blockers.append("Experiência sintética selecionada: configure Synthetic/Experience Apdex antes da execução")
    if "deep-analysis" in current.modules:
        raw = (os.environ.get(IMPROVEMENT_ENABLED_ENV) or "").strip().casefold()
        if raw not in {"1", "true", "yes", "on"}:
            blockers.append("Análise profunda selecionada: habilite/configure o item 13 antes da execução")
    if "geo" in current.modules:
        try:
            context = configured_content_analysis_context()
        except ValueError as exc:
            blockers.append(f"contexto editorial inválido: {exc}")
        else:
            if context.is_fully_auto:
                advisories.append("GEO: contexto editorial/YMYL está AUTO; nenhum valor editorial será inventado pelo preset")
            else:
                advisories.append("GEO: contexto editorial explícito existente será preservado")
    if current.ai_mode == AI_IF_AVAILABLE and "ai" not in current.manual_overrides:
        effective = _effective_ai_provider(state)
        if effective == "none":
            advisories.append("IA solicitada se disponível, mas nenhum provider está APTO; a execução seguirá sem IA padrão")
        else:
            advisories.append(f"IA padrão será usada se disponível: provider efetivo={effective}")
    return not blockers, tuple(blockers), tuple(advisories)


def _cost_lines(state: Any, session: SessionProfile) -> tuple[str, ...]:
    lines: list[str] = []
    with effective_profile(state, session):
        estimate: ExposureEstimate = estimate_exposure(state)
        lines.append(f"Exposição estimada do core/IA/Web Performance: {estimate.level}")
        if estimate.max_web_calls:
            lines.append(f"Web Performance: {estimate.min_web_calls}-{estimate.max_web_calls} chamada(s) potencial(is) de API/quota")
        else:
            lines.append("Web Performance: 0 chamadas adicionais projetadas por este perfil")
        if estimate.max_ai_attempts:
            lines.append(f"IA padrão: {estimate.min_ai_attempts}-{estimate.max_ai_attempts} tentativa(s) potenciais; tokens não são inventados previamente")
            lines.extend(estimate.pricing_lines)
        else:
            lines.append("IA padrão: nenhuma tentativa projetada")
        attempts, load = synthetic_load_summary(state)
        if "experience" in session.modules:
            lines.append("Experiência sintética: " + (load if attempts else "depende de configuração prévia; nenhuma carga inventada pelo preset"))
    if "search-intelligence" in session.modules:
        terms = len(tuple(getattr(state, "search_queries", ()) or ()))
        lines.append(f"SERP: provider externo; custo/quota depende de termos/depth ({terms} termo(s) atualmente configurado(s))")
    if "deep-analysis" in session.modules:
        lines.append("Análise profunda: chamadas adicionais de IA separadas da IA padrão; custo depende do provider/model/reasoning do item 13")
    lines.append("Serviços externos já habilitados fora do perfil mantêm seu contrato próprio; o preset não altera credenciais nem inventa preço.")
    return tuple(lines)


def _render_profile_detail(state: Any, session: SessionProfile) -> None:
    print(f"\n{session.label}")
    print("-" * min(max(len(session.label), 24), 80))
    if session.profile_id in _PROFILE_BY_ID:
        print(_PROFILE_BY_ID[session.profile_id].description)
    else:
        print("Composição personalizada para a próxima execução desta sessão.")
    print("\nENVOLVE")
    for module_id in session.modules:
        item = MODULE_BY_ID[module_id]
        print(f"- {item.label}: {item.description}")
    print("\nDEPENDÊNCIAS")
    for module_id in session.modules:
        item = MODULE_BY_ID[module_id]
        print(f"- {item.label}: {item.dependency_note}")
    ready, blockers, advisories = dependency_status(state, session)
    for item in blockers:
        print(paint(f"  CONFIGURAR: {item}", YELLOW, bold=True))
    for item in advisories:
        print(paint(f"  INFO: {item}", CYAN))
    print("\nCUSTO / EXPOSIÇÃO")
    for line in _cost_lines(state, session):
        print(f"- {line}")
    print(paint("\nPersistência do preset: NENHUMA. O overlay existe somente nesta sessão/execução.", GREEN, bold=True))
    if not ready:
        print(paint("O perfil pode ser selecionado agora, mas R. Executar ficará bloqueado até as dependências obrigatórias serem preenchidas.", YELLOW))


def _choose_ai_mode(state: Any) -> str | None:
    print("\nIA PADRÃO DO PERFIL")
    print("1. Não usar IA padrão nesta execução")
    print("2. Usar IA padrão se houver provider APTO (não bloqueia se nenhum estiver disponível)")
    print("   Observação: Improvement Intelligence possui IA própria e independente no item 13.")
    print("V. Voltar")
    raw = input("Escolha: ").strip().upper()
    if raw == "1":
        return AI_OFF
    if raw == "2":
        return AI_IF_AVAILABLE
    if raw == "V":
        return None
    state.error = "opção de IA do perfil inválida"
    return None


def _custom_modules(state: Any) -> tuple[str, ...] | None:
    selected: set[str] = set()
    while True:
        print("\nCOMPOSIÇÃO PERSONALIZADA")
        for index, item in enumerate(MODULES, 1):
            marker = "*" if item.id in selected else " "
            print(f" {index:2d}. [{marker}] {item.label}")
            print(f"     Envolve: {item.description}")
            print(f"     Custo : {item.cost_note}")
            if item.dependency_note:
                print(f"     Requer: {item.dependency_note}")
        print("\nDigite o número para marcar/desmarcar; A=aplicar; V=voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return None
        if raw == "A":
            if not selected:
                state.error = "selecione ao menos um módulo"
                continue
            return tuple(item.id for item in MODULES if item.id in selected)
        try:
            item = MODULES[int(raw) - 1]
        except (ValueError, IndexError):
            state.error = "módulo inválido"
            continue
        if item.id in selected:
            selected.remove(item.id)
        else:
            selected.add(item.id)
        state.error = ""


def configure_profile(state: Any) -> None:
    if str(getattr(state, "input_mode", "")).casefold() != "url" or not str(getattr(state, "target", "")).strip():
        state.error = "Perfis de execução ficam disponíveis somente após informar uma URL única no item 1"
        return
    while True:
        print("\nPERFIS DE EXECUÇÃO — SOMENTE ESTA SESSÃO / URL ÚNICA\n")
        print("O perfil não altera defaults, INI, Windows/User, Windows/Machine ou credenciais.")
        print("Ajustes feitos depois da seleção pelo menu normal vencem o preset na próxima execução.\n")
        for index, profile in enumerate(PROFILES, 1):
            module_costs = " | ".join(dict.fromkeys(MODULE_BY_ID[item].cost_note for item in profile.modules))
            print(f" {index:2d}. {profile.label}")
            print(f"     Envolve: {profile.description}")
            print(f"     Custo : {module_costs}")
        print("\n C. Compor perfil personalizado")
        print(" N. Remover perfil da sessão")
        print(" V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return
        if raw == "N":
            clear_profile(state)
            state.error = ""
            state.operation = "LOCAL:EXECUTION_PROFILE_NONE"
            return
        if raw == "C":
            modules = _custom_modules(state)
            if modules is None:
                continue
            ai_mode = _choose_ai_mode(state)
            if ai_mode is None:
                continue
            candidate = SessionProfile("custom", "Personalizado", modules, ai_mode, _baseline(state))
        else:
            try:
                definition = PROFILES[int(raw) - 1]
            except (ValueError, IndexError):
                state.error = "perfil inválido"
                continue
            ai_mode = _choose_ai_mode(state)
            if ai_mode is None:
                continue
            candidate = SessionProfile(definition.id, definition.label, definition.modules, ai_mode, _baseline(state))
        _render_profile_detail(state, candidate)
        print("\nA. Aplicar à sessão")
        print("V. Voltar sem alterar")
        confirm = input("Escolha: ").strip().upper()
        if confirm != "A":
            continue
        _SESSIONS[id(state)] = candidate
        state.error = ""
        state.operation = "LOCAL:EXECUTION_PROFILE_SELECTED"
        return


def _profile_summary(state: Any) -> None:
    current = active_profile(state)
    allowed = str(getattr(state, "input_mode", "")).casefold() == "url" and bool(str(getattr(state, "target", "")).strip())
    print("\nPERFIL DA PRÓXIMA EXECUÇÃO")
    if current is None:
        if allowed:
            print(f"F. Perfil da execução     : {paint('NENHUM', DIM)} | disponível para URL única | sessão apenas")
        else:
            print(f"F. Perfil da execução     : {paint('INDISPONÍVEL', RED, bold=True)} | informe URL única no item 1")
        return
    ready, blockers, advisories = dependency_status(state, current)
    marker = paint("APTO", GREEN, bold=True) if ready else paint("CONFIGURAR", YELLOW, bold=True)
    modules = ", ".join(MODULE_BY_ID[item].label for item in current.modules)
    ai = "SEM IA" if current.ai_mode == AI_OFF else "IA SE DISPONÍVEL"
    print(f"F. Perfil da execução     : {marker} | {current.label} | {ai} | SESSÃO")
    print(f"   Módulos                : {modules}")
    with effective_profile(state, current):
        estimate = estimate_exposure(state)
    print(f"   Exposição estimada     : {estimate.level} | Web API até {estimate.max_web_calls} | IA até {estimate.max_ai_attempts} tentativa(s)")
    for item in blockers:
        print(paint(f"   CONFIGURAR             : {item}", YELLOW))
    for item in advisories:
        print(paint(f"   INFO                   : {item}", CYAN))
    if current.manual_overrides:
        print(paint("   Ajustes finos          : " + ", ".join(sorted(current.manual_overrides)), CYAN))
    print(paint("   Persistência           : nenhuma; não altera INI/defaults/SO", DIM))


def _mark_manual_override(state: Any, choice: str) -> None:
    current = active_profile(state)
    if current is None:
        return
    mapping = {
        "4": "ai",
        "5": "remediation",
        "6": "web",
        "11": "experience",
        "13": "deep",
        "T": "search",
    }
    domain = mapping.get(choice.upper())
    if domain:
        current.manual_overrides.add(domain)


def install(console_module: ModuleType) -> None:
    """Install execution profiles around the final local-console contract."""
    if getattr(console_module, "_rasai_execution_profiles", False):
        return
    original_menu = console_module._menu
    original_configure = console_module._configure
    original_readiness = console_module._execution_readiness
    original_run = console_module.run_audit_from_console

    def menu(state: Any) -> str:
        original_input = builtins.input
        injected = False

        def decorated_input(prompt: str = "") -> str:
            nonlocal injected
            if not injected and prompt.strip().casefold().startswith("escolha"):
                _profile_summary(state)
                injected = True
            return original_input(prompt)

        builtins.input = decorated_input
        try:
            return original_menu(state)
        finally:
            builtins.input = original_input

    def configure(state: Any, choice: str) -> None:
        if choice.upper() == PROFILE_CHOICE:
            configure_profile(state)
            return
        original_configure(state, choice)
        current = active_profile(state)
        if current is None:
            return
        if choice == "1" and (str(getattr(state, "input_mode", "")).casefold() != "url" or not str(getattr(state, "target", "")).strip()):
            clear_profile(state)
            state.error = "Perfil removido automaticamente: perfis exigem URL única explícita"
            return
        _mark_manual_override(state, choice)

    def readiness(state: Any) -> tuple[bool, str]:
        current = active_profile(state)
        if current is None:
            return original_readiness(state)
        deps_ready, blockers, _ = dependency_status(state, current)
        if not deps_ready:
            return False, "; ".join(blockers)
        with effective_profile(state, current):
            ready, reason = original_readiness(state)
        if not ready:
            return ready, reason
        return True, f"configuração válida; perfil={current.label}; overlay somente da sessão"

    def run(state: Any) -> int:
        current = active_profile(state)
        if current is None:
            return int(original_run(state) or 0)
        deps_ready, blockers, _ = dependency_status(state, current)
        if not deps_ready:
            state.error = "; ".join(blockers)
            return 2
        with effective_profile(state, current):
            return int(original_run(state) or 0)

    console_module._menu = menu
    console_module._configure = configure
    console_module._execution_readiness = readiness
    console_module.run_audit_from_console = run
    console_module._rasai_execution_profiles = True
