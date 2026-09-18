"""Canonical configuration/catalog UI for the local interactive console."""
from __future__ import annotations

from configparser import ConfigParser
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

from rasai.console_ui import CYAN, DIM, GREEN, RED, YELLOW, paint


def configuration_id(name: str) -> str:
    """Return the stable numeric public ID for a canonical configuration key."""
    key = str(name).strip().upper().encode("utf-8")
    digest = hashlib.blake2s(key, digest_size=4, person=b"RASAI-CF").digest()
    return f"{int.from_bytes(digest, 'big') % 100_000_000:08d}"


CORE_IDS = {
    "profile": "00000001", "input": "00000002", "project": "00000003",
    "device": "00000004", "language_market": "00000005", "timezone": "00000006",
    "audits_root": "00000007", "ai_primary": "00000008", "web_performance": "00000009",
    "search_terms": "00000010", "apdex_navigation": "00000011",
    "apdex_experience": "00000012", "deep_analysis": "00000013", "remediations": "00000014",
    "passive_security": "00000015",
}

_STATUS_COLORS = {
    "APTO": GREEN, "INCLUÍDO": GREEN, "CONCLUÍDO": GREEN, "HABILITADO": GREEN,
    "CONFIGURAR": YELLOW, "PARCIAL": YELLOW, "APTO COM LIMITAÇÕES": YELLOW,
    "PERSONALIZADO": CYAN, "AUTOMÁTICO": CYAN, "HERDADO": CYAN, "DERIVADO": CYAN,
    "ERRO": RED, "INDISPONÍVEL": RED, "BLOQUEADO": RED,
    "DESABILITADO": DIM, "NÃO APLICÁVEL": DIM, "PADRÃO": DIM,
}


def badge(label: str) -> str:
    value = str(label).strip().upper()
    return paint(value, _STATUS_COLORS.get(value, CYAN), bold=True)


def section(label: str) -> None:
    print("\n" + paint(f"[ {label} ]", CYAN, bold=True))


def info(label: str, value: object) -> None:
    print(f"{label:<20}: {value}")


def _config_path(state: Any) -> Path | None:
    try:
        from rasai.console_session import get_config_path
        value = get_config_path(state)
        return Path(value) if value else None
    except (OSError, TypeError, ValueError):
        return None


def _persisted_env(state: Any, name: str) -> str | None:
    path = _config_path(state)
    if path is None or not path.is_file():
        return None
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    if parser.has_option("environment", name):
        return parser.get("environment", name, raw=True).strip() or None
    return None


def origin_for(state: Any, spec: Any) -> str:
    from rasai.windows_environment import environment_origin
    raw = (os.environ.get(spec.name) or "").strip()
    if raw:
        if _persisted_env(state, spec.name) == raw:
            return "ARQUIVO"
        origin = environment_origin(spec.name, raw)
        return origin.replace("SO:", "WINDOWS/") if origin else "SESSÃO"
    return "DEFAULT" if spec.default is not None else "NÃO CONFIGURADO"


def owner_for(spec: Any) -> str:
    from rasai.console_configuration_guidance import context_for
    context, category = str(context_for(spec)).strip(), str(spec.category).strip()
    if category.startswith("IA"):
        return f"Inteligência Artificial / {context}"
    if "Search" in category or "Observability" in category:
        return f"Search / {context}"
    if "Web Performance" in category or "Métricas" in category:
        return f"Web / {context}"
    if "Synthetic Apdex" in category:
        return f"Synthetic Apdex / {context}"
    if "Identity" in category:
        return f"Identity / {context}"
    if "Control plane" in category or "Remote" in category:
        return f"Plataforma / {context}"
    return f"{category} / {context}"


def is_pending(spec: Any) -> bool:
    if (os.environ.get(spec.name) or "").strip() or spec.default is not None:
        return False
    required = str(spec.required_when or "").strip().casefold()
    return bool(required and not required.startswith("nunca") and "opcional" not in required)


def is_modified(state: Any, spec: Any) -> bool:
    raw = (os.environ.get(spec.name) or "").strip()
    return bool(raw and (spec.default is None or raw != str(spec.default).strip()))


def _value(spec: Any) -> str:
    from rasai import console_environment as base
    raw = (os.environ.get(spec.name) or "").strip()
    if base._is_sensitive_spec(spec):
        return "[SET]" if raw else "<não configurada>"
    if raw:
        return raw
    return f"{spec.default} [default]" if spec.default is not None else "<não configurado>"


def _apply(state: Any, spec: Any, raw: str | None) -> None:
    from rasai import console_provider_environment as env
    if raw is None:
        os.environ.pop(spec.name, None)
    else:
        os.environ[spec.name] = env._validate(spec.name, raw)
    if env.base_environment._is_sensitive_spec(spec):
        env.base_environment._sync_secret_state(state, spec.name)
    env.base_environment._apply_change(state, spec.name)
    env.refresh_specs()


def _destination(secret: bool) -> str:
    print("\nDESTINO DA ALTERAÇÃO")
    print("1. Aplicar somente nesta sessão")
    print("2. Aplicar na sessão e persistir em Windows/User" if secret else "2. Aplicar na sessão e salvar no arquivo de configuração")
    if secret:
        print(paint("   Secrets nunca são gravados no rasai-console.ini.", YELLOW))
    print("V. Cancelar")
    while True:
        raw = input("Escolha: ").strip().upper()
        if raw in {"1", "2", "V"}:
            return raw
        print(paint("Opção inválida.", RED, bold=True))


def variable_editor(console_module: ModuleType, state: Any, spec: Any) -> None:
    """Edit one canonical variable with help, domain, origin and persistence choice."""
    from getpass import getpass
    from rasai import console_provider_environment as env
    from rasai.console_configuration_guidance import context_for, prompt_guided_value, render_enrichment
    while True:
        spec = env.normalize_spec(spec)
        env.base_environment.render_header(state)
        print(paint(f"CONFIGURAÇÃO > {owner_for(spec)}", CYAN, bold=True))
        print(paint(f"\n{configuration_id(spec.name)} · {spec.name}", CYAN, bold=True))
        section("INFORMAÇÃO")
        info("Para que serve", spec.purpose); info("Owner", owner_for(spec)); info("Contexto", context_for(spec))
        info("Necessário quando", spec.required_when); info("Impacto", spec.impact)
        if spec.notes: info("Observação", spec.notes)
        section("ESTADO ATUAL")
        info("Valor", _value(spec)); info("Origem", origin_for(state, spec)); info("Estado", env.decision_badge(spec))
        section("DOMÍNIO / INPUT")
        info("Tipo", spec.value_type)
        if spec.accepted:
            info("Valores aceitos", ", ".join(spec.accepted)); print(paint("Entrada livre não é usada quando o domínio é conhecido.", DIM))
        else:
            print(paint("Valor aberto; o runtime continua sendo a autoridade de validação.", DIM))
        info("Default", spec.default if spec.default is not None else "<sem default>"); render_enrichment(spec)
        secret = env.base_environment._is_sensitive_spec(spec)
        section("AÇÕES")
        print("S. Definir / alterar\nL. Limpar override somente desta sessão")
        print("R. Restaurar estado não configurado nesta sessão\nP. Gerenciar persistência Windows/User" if secret else "R. Restaurar default/ausência canônica e salvar no arquivo")
        print("D. Documentação\nV. Voltar")
        action = input("Escolha: ").strip().upper()
        if action == "V": return
        if action == "D": env.base_environment._open_docs(state); continue
        if action == "P" and secret:
            try: env.base_environment._persist_secret(state, spec)
            except (OSError, ValueError) as exc: state.error = f"falha de persistência: {type(exc).__name__}: {exc}"
            continue
        if action in {"L", "R"}:
            _apply(state, spec, None); state.error = ""; state.operation = "LOCAL:CONFIG_RESTORED" if action == "R" else "LOCAL:CONFIG_OVERRIDE_CLEARED"
            if action == "R" and not secret: console_module._save_configuration(state)
            continue
        if action != "S": state.error = "ação inválida"; continue
        try:
            raw = prompt_guided_value(spec) if spec.accepted else (getpass(f"{spec.name}: ") if secret else input(f"{spec.name}: "))
            if raw is None: continue
            validated = env._validate(spec.name, raw)
        except (ValueError, OverflowError) as exc:
            state.error = str(exc); continue
        destination = _destination(secret)
        if destination == "V": continue
        try:
            _apply(state, spec, validated); state.error = ""; state.operation = "LOCAL:CONFIG_UPDATED"
            if destination == "2":
                env.base_environment._persist_secret(state, spec) if secret else console_module._save_configuration(state)
        except (OSError, ValueError, OverflowError) as exc:
            state.error = str(exc)


def catalog_specs(view: str) -> tuple[Any, ...]:
    from rasai import console_provider_environment as env
    specs = env.refresh_specs()
    if view == "ai": return tuple(s for s in specs if str(s.category).startswith("IA"))
    if view == "integrations": return tuple(s for s in specs if s.category != "Aplicação e execução" and not str(s.category).startswith("IA"))
    return tuple(specs)


def _sorted(state: Any, specs: Iterable[Any], mode: str) -> tuple[Any, ...]:
    rows = tuple(specs)
    if mode == "alpha": return tuple(sorted(rows, key=lambda s: s.name.casefold()))
    if mode == "state": return tuple(sorted(rows, key=lambda s: (not is_pending(s), origin_for(state, s), s.name)))
    if mode == "modified": return tuple(sorted((s for s in rows if is_modified(state, s)), key=lambda s: s.name))
    if mode == "pending": return tuple(sorted((s for s in rows if is_pending(s)), key=lambda s: s.name))
    return tuple(sorted(rows, key=lambda s: (owner_for(s).casefold(), s.name.casefold())))


def _rows(state: Any, rows: tuple[Any, ...], grouped: bool) -> None:
    owner = None
    for spec in rows:
        current = owner_for(spec)
        if grouped and current != owner:
            print("\n" + paint(f"[{current}]", CYAN, bold=True)); owner = current
        status = "CONFIGURAR" if is_pending(spec) else "APTO" if (os.environ.get(spec.name) or "").strip() or spec.default is not None else "OPCIONAL"
        print(f"{configuration_id(spec.name)}  {spec.name:<46} {badge(status)} [{origin_for(state, spec)}]")


def catalog_menu(console_module: ModuleType, state: Any, *, view: str, title: str) -> None:
    from rasai import console_provider_environment as env
    mode, search_rows = "owner", None
    while True:
        specs = catalog_specs(view); rows = search_rows if search_rows is not None else _sorted(state, specs, mode)
        env.base_environment.render_header(state); print(paint(f"INÍCIO > {title}", CYAN, bold=True))
        print("\nCada variável possui ID numérico estável; o mesmo ID aparece em qualquer contexto.")
        print(paint("Números identificam configurações; letras representam ações/navegação.", DIM))
        if view == "ai":
            section("IA PRINCIPAL DA EXECUÇÃO")
            print(f"1. {CORE_IDS['ai_primary']}  Seleção principal          : {getattr(state, 'ai_provider', 'none')}")
            print(paint("   AUTO e seleção explícita continuam sob a orquestração canônica do runtime.", DIM))
        _rows(state, rows, mode == "owner" and search_rows is None)
        if not rows: print(paint("\nNenhuma configuração corresponde ao filtro atual.", DIM))
        section("AÇÕES")
        print("O. Por owner funcional\nA. Ordem alfabética\nE. Por estado\nM. Somente modificadas\nP. Somente pendentes\nF. Localizar por ID/nome/finalidade")
        if view == "integrations": print("D. Diagnóstico técnico das integrações")
        print("V. Voltar")
        raw = input("ID ou ação: ").strip().upper()
        if raw == "V": return
        if raw == "1" and view == "ai": console_module._configure(state, "4"); search_rows = None; continue
        if raw in {"O", "A", "E", "M", "P"}: mode = {"O":"owner","A":"alpha","E":"state","M":"modified","P":"pending"}[raw]; search_rows = None; continue
        if raw == "F":
            term = input("ID, nome ou texto para localizar: ").strip().casefold()
            search_rows = tuple(s for s in specs if configuration_id(s.name) == term or term in s.name.casefold() or term in str(s.purpose).casefold() or term in owner_for(s).casefold()) if term else ()
            continue
        if raw == "D" and view == "integrations":
            from rasai import integration_diagnostics_console as diag
            diag.integration_menu(console_module, state, lambda current: catalog_menu(console_module, current, view="all", title="TODAS AS CONFIGURAÇÕES")); continue
        selected = next((s for s in specs if configuration_id(s.name) == raw), None)
        if selected is None: state.error = "ID/ação inválido"; continue
        variable_editor(console_module, state, selected); search_rows = None


def _matches(spec: Any, capability: str) -> bool:
    name, category, owner = str(spec.name).upper(), str(spec.category).casefold(), owner_for(spec).casefold()
    if capability == "domain-discovery": return name == "RASAI_AI_TECHNICAL_REMEDIATION"
    if capability == "accessibility": return "LIGHTHOUSE" in name or "PAGESPEED" in name or "ACCESS" in name
    if capability == "web-performance": return any(x in name for x in ("WEB_PERFORMANCE","PAGESPEED","CRUX","LIGHTHOUSE"))
    if capability == "standards": return "métricas" in category or any(x in name for x in ("W3C","MDN","WEB_PLATFORM","WEB_FEATURES","RETRIEVAL"))
    if capability == "search-intelligence": return any(x in name for x in ("SERP","SEARCH_CONSOLE","GSC_","GOOGLE_SEARCH_CONSOLE"))
    if capability == "apdex-navigation": return ("APDEX" in name and "EXPERIENCE" not in name and "DYNATRACE" not in name) or "synthetic navigation" in owner
    if capability == "apdex-experience": return any(x in name for x in ("EXPERIENCE","DYNATRACE")) or "user experience" in owner
    if capability == "ai-visibility": return "AI_VISIBILITY" in name or "visibility" in owner
    if capability == "observability": return "observ" in category or any(x in name for x in ("CLARITY","DYNATRACE","GSC_","SEARCH_CONSOLE"))
    if capability == "deep-analysis": return name.startswith("RASAI_IMPROVEMENT_") or name == "RASAI_AI_ANALYSIS_LANGUAGE"
    if capability == "content-suggestions": return name == "RASAI_AI_CONTENT_REMEDIATION" or "contexto editorial" in category
    if capability == "remediation": return name in {"RASAI_AI_CONTENT_REMEDIATION","RASAI_AI_TECHNICAL_REMEDIATION"}
    if capability == "passive-security":
        return category.startswith("cat-10") or name in {"RASAI_MDN_OBSERVATORY","RASAI_STANDARDS_MDN_OBSERVATORY"}
    return False


def capability_specs(capability: str) -> tuple[Any, ...]:
    from rasai import console_provider_environment as env
    return tuple(s for s in env.refresh_specs() if _matches(s, capability))


@dataclass(frozen=True, slots=True)
class CapabilityUI:
    key: str; label: str; help_text: str; handler_choice: str | None = None; automatic: bool = False; derived: bool = False


CAPABILITIES = (
    CapabilityUI("domain-discovery","Domínio e descoberta","robots.txt, sitemaps/feeds, crawler controls, descoberta e llms.txt.",automatic=True),
    CapabilityUI("accessibility","Acessibilidade","Evidências de acessibilidade; Lighthouse pode enriquecer a análise.",automatic=True),
    CapabilityUI("web-performance","Web Performance","Coleta PageSpeed/Lighthouse/CrUX e limites relacionados.","6"),
    CapabilityUI("standards","Métricas e padrões","Serviços/métricas complementares baseados em padrões web."),
    CapabilityUI("search-intelligence","Search Intelligence","Observação SERP com provider, limites e compatibilidade validados antes da execução.","T"),
    CapabilityUI("apdex-navigation","Apdex de navegação","Navegações reais repetidas no browser sintético.","11"),
    CapabilityUI("apdex-experience","Apdex de experiência","População sintética por dispositivo e calibração opcional Dynatrace.","11"),
    CapabilityUI("ai-visibility","Visibilidade em IA","Resultado quando houver fontes/evidências aplicáveis."),
    CapabilityUI("observability","Search & AI observados","Fontes observacionais externas configuradas."),
    CapabilityUI("deep-analysis","Análise profunda e melhorias","Análise evidence-bound de URL única com a IA principal.","13"),
    CapabilityUI("content-suggestions","Conteúdo e JSON-LD","Conteúdo/estrutura com IA opcional como enriquecimento advisory."),
    CapabilityUI("remediation","Remediações","Correções determinísticas e orientação opcional por IA.","5"),
    CapabilityUI("passive-security","Segurança passiva","Postura HTTP/browser, cookies, recursos, third-party, runtime e vulnerability intelligence sem active scanning."),
    CapabilityUI("quality","Quality & decisão","Resultado derivado do conjunto de evidências.",automatic=True,derived=True),
)


def capability_status(state: Any, capability: CapabilityUI) -> tuple[str, str]:
    if capability.key in {"domain-discovery","accessibility","quality"}: return ("DERIVADO" if capability.derived else "INCLUÍDO", "gerado pelo contrato da auditoria")
    if capability.key == "web-performance": return ("APTO" if bool(getattr(state,"web_performance",False)) else "DESABILITADO", "configuração da próxima auditoria")
    if capability.key == "search-intelligence":
        if not tuple(getattr(state,"search_queries",()) or ()): return "DESABILITADO", "nenhum termo SERP configurado"
        try:
            from rasai.console_search_intelligence import validate_search_readiness
            ready, detail = validate_search_readiness(state); return ("APTO" if ready else "CONFIGURAR", detail)
        except (ImportError, ValueError) as exc: return "CONFIGURAR", str(exc)
    if capability.key == "apdex-navigation":
        if not bool(getattr(state,"synthetic_apdex",False)): return "DESABILITADO", "Navigation Apdex não solicitado"
        try:
            from rasai.console_m23 import validate_m23_state
            validate_m23_state(state); return "APTO", "configuração sintética válida"
        except (ValueError, OSError) as exc: return "CONFIGURAR", str(exc)
    if capability.key == "apdex-experience":
        if not bool(getattr(state,"apdex_experience",False)): return "DESABILITADO", "Experience Apdex não solicitado"
        if not bool(getattr(state,"synthetic_apdex",False)): return "CONFIGURAR", "Experience Apdex exige Navigation Apdex"
        return "APTO", f"mix={getattr(state,'apdex_experience_device_mix','-')}"
    if capability.key == "deep-analysis":
        if not bool(getattr(state,"improvement_enabled",False)): return "DESABILITADO", "análise profunda não solicitada"
        try:
            from rasai.improvement_intelligence_console import _single_url_ready
            ready, detail = _single_url_ready(state)
            if not ready: return "CONFIGURAR", detail
        except ImportError: pass
        return ("CONFIGURAR","exige IA principal ativa") if str(getattr(state,"ai_provider","none")) == "none" else ("APTO","URL única e IA principal configuradas")
    if capability.key == "remediation":
        enabled = bool(getattr(state,"content_remediation",False) or getattr(state,"technical_remediation",False))
        if not enabled: return "INCLUÍDO", "remediações determinísticas; IA advisory desabilitada"
        return ("APTO","enriquecimento por IA solicitado") if str(getattr(state,"ai_provider","none")) != "none" else ("CONFIGURAR","remediação por IA exige IA principal")
    if capability.key == "passive-security":
        return "APTO", "modo passivo; HTTP/browser/runtime reutilizados; OSV/KEV são externos opcionais e MDN Observatory é reutilizado"
    specs = capability_specs(capability.key); pending = tuple(s for s in specs if is_pending(s))
    if pending: return "CONFIGURAR", f"{len(pending)} configuração(ões) obrigatória(s) pendente(s)"
    return ("AUTOMÁTICO", "usa integrações configuradas quando aplicável")


def capability_menu(console_module: ModuleType, state: Any, capability: CapabilityUI) -> str | None:
    from rasai import console_provider_environment as env
    while True:
        status, detail, specs = *capability_status(state, capability), capability_specs(capability.key)
        env.base_environment.render_header(state); print(paint(f"INÍCIO > PREPARAR AUDITORIA > {capability.label.upper()}", CYAN, bold=True))
        section("ESTADO"); info("Capacidade", capability.label); info("Estado", badge(status)); info("Detalhe", detail)
        section("INFORMAÇÃO"); print(capability.help_text)
        if capability.automatic: print(paint("Resultado automático/derivado; não há checkbox independente.", DIM))
        if capability.handler_choice is not None: section("CONFIGURAÇÃO DA ANÁLISE"); print("1. Alterar parâmetros próprios desta análise")
        section("DEPENDÊNCIAS / CONFIGURAÇÕES RELACIONADAS")
        if specs:
            for spec in sorted(specs,key=lambda s:(owner_for(s).casefold(),s.name.casefold())): print(f"{configuration_id(spec.name)}  {spec.name:<46} [{origin_for(state,spec)}]")
        else: print(paint("Nenhuma variável adicional é necessária neste contexto.", DIM))
        section("AÇÕES"); print("H. Ajuda de contexto\nV. Voltar para Preparar auditoria")
        raw = input("Número/ID ou ação: ").strip().upper()
        if raw == "V": return None
        if raw == "H": print("\nSomente configurações consumidas por esta capacidade são exibidas; o owner canônico é único."); input("ENTER para continuar..."); continue
        if raw == "1" and capability.handler_choice is not None: return capability.handler_choice
        selected = next((s for s in specs if configuration_id(s.name) == raw), None)
        if selected is not None: variable_editor(console_module,state,selected); continue
        state.error = "opção inválida neste relatório/capacidade"
