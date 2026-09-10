"""Friendly menu for RASAi audit execution."""
from __future__ import annotations

from getpass import getpass
import math
import os

from rasai.console_artifacts import artifact_status, open_audit_folder, open_report
from rasai.console_collection import load_collection_coverage
from rasai.console_config import (
    DEFAULT_MODELS,
    ENV_NAMES as BASE_ENV_NAMES,
    KEY_ENV,
    MODEL_ENV,
    PROVIDERS,
    PROVIDER_MENU_CHOICES,
    SUPPORTED_MODELS,
    apply_environment_defaults,
    is_secret,
    preflight,
    provider_capabilities,
)
from rasai.console_cost import actual_usage, estimate_exposure
from rasai.console_help import menu_cost_badges, render_environment_help, render_help
from rasai.console_m23 import (
    M23_ENV_NAMES,
    State,
    actual_m23_usage,
    apply_m23_environment_defaults,
    config_from_state,
    render_m23_help,
    run_audit_from_console,
    synthetic_load_summary,
    validate_env_value,
    validate_m23_state,
)
from rasai.console_runtime import render_header
from rasai.console_session import (
    clear_secret_volatile,
    get_config_path,
    has_volatile_secrets,
    is_dirty,
    mark_dirty,
    mark_secret_volatile,
    set_config_path,
)
from rasai.console_settings import (
    configuration_fingerprint,
    load_console_config,
    save_console_config,
    sync_nonsecret_runtime_environment,
)
from rasai.console_ui import (
    CYAN,
    DIM,
    GREEN,
    RED,
    YELLOW,
    availability_badge,
    bool_badge,
    cost_color,
    paint,
)
from rasai.provider_runtime_policy import (
    AI_TIMEOUT_ENV,
    LOWEST_REASONING,
    REASONING_OPTIONS,
    WEB_PERFORMANCE_TIMEOUT_ENV,
    apply_console_reasoning_environment,
    configured_reasoning,
)
from rasai.time_contract import (
    PRESENTATION_TIMEZONE_ENV,
    configured_presentation_timezone,
    timezone_offset_label,
    validate_presentation_timezone,
)
from rasai.windows_environment import (
    current_matches_persisted,
    environment_origin,
    machine_environment_value,
    persist_user_environment,
    remove_user_environment,
    user_environment_value,
)

ENV_NAMES = tuple(dict.fromkeys((*BASE_ENV_NAMES, *M23_ENV_NAMES)))

_TIMEZONE_PRESETS = (
    ("America/Sao_Paulo", "Brasil - São Paulo"),
    ("UTC", "UTC / timezone 0"),
    ("America/New_York", "EUA - Nova York"),
    ("America/Chicago", "EUA - Chicago"),
    ("America/Los_Angeles", "EUA - Los Angeles"),
    ("America/Mexico_City", "México - Cidade do México"),
    ("America/Argentina/Buenos_Aires", "Argentina - Buenos Aires"),
    ("Europe/London", "Reino Unido - Londres"),
    ("Europe/Berlin", "Europa Central - Berlim"),
    ("Asia/Tokyo", "Japão - Tóquio"),
    ("Asia/Shanghai", "China - Xangai"),
    ("Asia/Kolkata", "Índia - Calcutá"),
    ("Australia/Sydney", "Austrália - Sydney"),
)


def _select(state: State, title: str, options: list[tuple[str, bool, str]]) -> str | None:
    render_header(state)
    print(title)
    allowed: dict[str, str] = {}
    for index, (value, available, reason) in enumerate(options, 1):
        marker = availability_badge(available)
        reason_text = paint(reason, CYAN if available else RED)
        print(f" {index}. {value:<18} [{marker}] {reason_text}")
        if available:
            allowed[str(index)] = value
    print("\n V. Voltar")
    while True:
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return None
        if raw in allowed:
            return allowed[raw]
        print(paint("Opção indisponível ou inválida.", RED, bold=True))


def _environment_help_menu(state: State) -> None:
    render_header(state)
    print("AJUDA DE VARIÁVEIS - selecione uma variável ou 0 para todas\n")
    for index, name in enumerate(ENV_NAMES, 1):
        print(f"{index:2d}. {name}")
    try:
        raw = input("\nNúmero [0=todas]: ").strip()
        render_header(state)
        print("AJUDA DE VARIÁVEIS\n")
        if raw == "0":
            for name in ENV_NAMES:
                render_environment_help(name)
            render_m23_help(state)
        else:
            selected = ENV_NAMES[int(raw) - 1]
            render_environment_help(selected)
            if selected in M23_ENV_NAMES:
                render_m23_help(state)
    except (ValueError, IndexError):
        print(paint("Variável inválida.", RED, bold=True))
    input("\nENTER para voltar...")


def _sync_secret_volatility(state: State, name: str) -> None:
    if current_matches_persisted(name):
        clear_secret_volatile(state, name)
    else:
        mark_secret_volatile(state, name)


def _secret_persistence_action(state: State, name: str) -> None:
    while True:
        render_header(state)
        current = (os.environ.get(name) or "").strip()
        user_value = user_environment_value(name)
        machine_value = machine_environment_value(name)
        print("PERSISTÊNCIA DE CREDENCIAL NO WINDOWS\n")
        print(f"Variável           : {name}")
        print(f"Sessão atual       : {'[SET]' if current else '<não definida>'}")
        print(f"Windows / User     : {'[PERSISTIDA]' if user_value else '<não persistida>'}")
        print(f"Windows / Machine  : {'[PERSISTIDA]' if machine_value else '<não persistida>'}")
        print("\nO valor da sessão atual é o valor efetivamente usado por esta execução.")
        print("Persistir grava a credencial no ambiente do usuário Windows (User), nunca no INI.")
        print(paint("Variáveis de ambiente não são um cofre de segredos: processos com acesso ao mesmo usuário podem lê-las.", YELLOW))
        print("\nP. Persistir no Windows/User o valor atual da sessão")
        print("R. Remover a persistência Windows/User (mantém a sessão atual)")
        print("V. Voltar")
        action = input("Escolha: ").strip().upper()
        if action == "V":
            return
        if action == "P":
            if os.name != "nt":
                state.error = "persistência de credenciais no SO está disponível somente no Windows"
                return
            if not current:
                state.error = "defina a credencial na sessão antes de persistir"
                return
            confirm = input(f"Confirmar persistência de {name} no ambiente USER do Windows? Digite SIM: ").strip().upper()
            if confirm != "SIM":
                state.error = "persistência cancelada"
                return
            try:
                persist_user_environment(name, current)
                _sync_secret_volatility(state, name)
                state.error = ""
                state.operation = "LOCAL:PERSIST_USER_SECRET"
                print(paint("\nCredencial persistida no ambiente USER do Windows.", GREEN, bold=True))
                input("ENTER para continuar...")
            except (OSError, ValueError) as exc:
                state.error = f"falha ao persistir {name}: {type(exc).__name__}: {exc}"
            return
        if action == "R":
            if os.name != "nt":
                state.error = "persistência de credenciais no SO está disponível somente no Windows"
                return
            if user_value is None:
                state.error = f"{name} não possui persistência no escopo Windows/User"
                return
            confirm = input(f"Confirmar remoção da persistência USER de {name}? Digite SIM: ").strip().upper()
            if confirm != "SIM":
                state.error = "remoção cancelada"
                return
            try:
                remove_user_environment(name)
                _sync_secret_volatility(state, name)
                state.error = ""
                state.operation = "LOCAL:REMOVE_USER_SECRET"
                print(paint("\nPersistência Windows/User removida. O valor da sessão atual não foi alterado.", GREEN, bold=True))
                input("ENTER para continuar...")
            except OSError as exc:
                state.error = f"falha ao remover persistência de {name}: {type(exc).__name__}: {exc}"
            return


def _environment_menu(state: State) -> None:
    while True:
        render_header(state)
        print("Variáveis de ambiente - secrets nunca são exibidos nem gravados no INI.\n")
        print("Para credenciais, a origem do valor efetivamente usado é indicada como SO ou SESSÃO.\n")
        for index, name in enumerate(ENV_NAMES, 1):
            value = os.environ.get(name)
            if is_secret(name):
                shown = paint("[SET]", GREEN, bold=True) if value else paint("<não definida>", DIM)
                origin = environment_origin(name, value)
                if origin:
                    origin_color = GREEN if origin in {"SO:USER", "SO:MACHINE"} else YELLOW
                    shown += " " + paint(f"[{origin}]", origin_color, bold=True)
            elif not value:
                shown = paint("<não definida>", DIM)
            elif value.strip().casefold() in {"true", "1", "yes", "on"}:
                shown = paint(value, GREEN, bold=True)
            elif value.strip().casefold() in {"false", "0", "no", "off"}:
                shown = paint(value, DIM)
            else:
                shown = paint(value, CYAN)
            print(f"{index:2d}. {name:<44} {shown}")
        print("\nAÇÕES")
        print("S. Setar/alterar sessão")
        print("R. Remover da sessão")
        print("P. Persistir/remover credencial no Windows")
        print("H. Ajuda / custo")
        print("V. Voltar")
        action = input("Escolha: ").strip().upper()
        if action == "V":
            return
        if action == "H":
            _environment_help_menu(state)
            continue
        if action not in {"S", "R", "P"}:
            continue
        try:
            selected = int(input("Número: ").strip()) - 1
            name = ENV_NAMES[selected]
        except (ValueError, IndexError):
            state.error = "variável inválida"
            continue
        if action == "P":
            if not is_secret(name):
                state.error = "persistência pelo item P é restrita a credenciais; parâmetros não sensíveis devem usar o INI"
                continue
            _secret_persistence_action(state, name)
            continue
        render_header(state)
        print(f"Variável selecionada: {name}\n")
        secret = is_secret(name)
        if action == "R":
            os.environ.pop(name, None)
            state.error = ""
        else:
            raw = getpass(f"{name}: ") if secret else input(f"{name}: ")
            try:
                os.environ[name] = validate_env_value(name, raw)
                state.error = ""
            except (ValueError, OverflowError) as exc:
                state.error = str(exc)
                continue
        if secret:
            _sync_secret_volatility(state, name)
        issues = list(apply_environment_defaults(state, names={name}))
        issues.extend(apply_m23_environment_defaults(state, names={name}))
        state.error = "; ".join(issues)
        for selection, provider in PROVIDERS.items():
            if KEY_ENV[provider] == name:
                state.runtime_blocks.pop(selection, None)


def _number(prompt: str, current: float, *, minimum: float = 0.0, integer: bool = False, help_text: str = "") -> float | int:
    if help_text:
        print(paint(f"  Para que serve: {help_text}", DIM))
    raw = input(f"{prompt} [{current:g}]: ").strip()
    value = current if not raw else (int(raw) if integer else float(raw))
    if value < minimum:
        raise ValueError(f"{prompt} deve ser >= {minimum:g}")
    return int(value) if integer else float(value)


def _configure_timezone(state: State) -> None:
    render_header(state)
    current = configured_presentation_timezone()
    print("TIMEZONE DE APRESENTAÇÃO\n")
    print(f"Atual: {current} ({timezone_offset_label(current)})")
    print("\nO RASAi continua persistindo e processando timestamps em UTC.")
    print("O offset numérico abaixo é apenas referência; o valor salvo é IANA para preservar regras de horário de verão e histórico.\n")
    for index, (timezone_name, label) in enumerate(_TIMEZONE_PRESETS, 1):
        marker = " (PADRÃO)" if timezone_name == "America/Sao_Paulo" else ""
        print(f"{index:2d}. {label:<34} {timezone_name:<32} {timezone_offset_label(timezone_name)}{marker}")
    print("\n C. Informar outro timezone IANA")
    print(" V. Voltar")
    raw = input("Escolha: ").strip().upper()
    if raw == "V":
        return
    try:
        if raw == "C":
            candidate = input("Timezone IANA (ex.: Pacific/Auckland): ").strip()
        else:
            candidate = _TIMEZONE_PRESETS[int(raw) - 1][0]
        os.environ[PRESENTATION_TIMEZONE_ENV] = validate_presentation_timezone(candidate)
        state.error = ""
    except (ValueError, IndexError) as exc:
        state.error = str(exc) if isinstance(exc, ValueError) else "opção de timezone inválida"


def _configure_apdex(state: State) -> None:
    print("Synthetic Apdex mede repetidamente a navegação real em Chromium e gera carga HTTP contra o alvo.")
    print("Cada parâmetro abaixo controla precisão, duração ou volume da medição.\n")
    enabled = input("Synthetic Apdex? Gera navegações reais repetidas contra o site [s/N]: ").strip().casefold() == "s"
    if not enabled:
        state.synthetic_apdex = False
        state.apdex_threshold = None
        state.error = ""
        return
    try:
        print(paint("  Para que serve: T é o tempo-alvo da Task. <=T é Satisfied; >T até 4T é Tolerating; >4T é Frustrated.", DIM))
        threshold_raw = input(f"Threshold T em segundos [{state.apdex_threshold if state.apdex_threshold is not None else 'obrigatório'}]: ").strip()
        if threshold_raw:
            threshold = float(threshold_raw)
        elif state.apdex_threshold is not None:
            threshold = state.apdex_threshold
        else:
            raise ValueError("Synthetic Apdex exige threshold T explícito")
        state.synthetic_apdex = True
        state.apdex_threshold = threshold
        state.apdex_samples = int(_number("Amostras válidas por contexto", state.apdex_samples, minimum=1, integer=True, help_text="quantidade de navegações válidas exigidas para cada URL/dispositivo. 1-99 é diagnóstico small-group (*); 100 é o grupo final normal da baseline atual."))
        suggested_attempts = max(state.apdex_samples, int(math.ceil(state.apdex_samples * 1.25)))
        if state.apdex_max_attempts < state.apdex_samples:
            state.apdex_max_attempts = suggested_attempts
        state.apdex_max_attempts = int(_number("Máximo de tentativas por contexto", state.apdex_max_attempts, minimum=state.apdex_samples, integer=True, help_text="teto de navegações usadas para alcançar as amostras válidas, permitindo repor amostras inválidas. Quanto maior, maior a carga máxima no alvo."))
        state.apdex_max_pages = int(_number("Máximo de páginas Synthetic Apdex (0=todas)", state.apdex_max_pages, minimum=0, integer=True, help_text="limita quantas páginas já auditadas receberão Synthetic Apdex. 0 usa todas as páginas disponíveis dentro do limite geral da auditoria."))
        minimum_timeout = 4.0 * threshold
        recommended_timeout = max(45.0, minimum_timeout + 5.0)
        if state.apdex_timeout <= minimum_timeout:
            state.apdex_timeout = recommended_timeout
        state.apdex_timeout = float(_number("Timeout por navegação (deve ser > 4T)", state.apdex_timeout, minimum=0.000001, help_text="tempo máximo permitido para uma navegação. Deve ser maior que 4T para não truncar artificialmente a faixa Frustrated."))
        state.apdex_delay = float(_number("Delay mínimo entre inícios", state.apdex_delay, minimum=0.0, help_text="intervalo mínimo, em segundos, entre inícios de navegação. Valores maiores reduzem a pressão sobre o site e aumentam a duração total."))
        state.apdex_concurrency = int(_number("Concorrência (1-2)", state.apdex_concurrency, minimum=1, integer=True, help_text="quantas navegações podem ocorrer simultaneamente. 1 é o modo mais conservador; 2 reduz tempo, mas aumenta carga concorrente."))
        config_from_state(state)
        state.error = ""
        attempts, load = synthetic_load_summary(state)
        if attempts:
            print(paint("\nCarga projetada Synthetic Apdex: " + load, YELLOW, bold=True))
    except (ValueError, OverflowError) as exc:
        state.error = str(exc)


def _configure(state: State, choice: str) -> None:
    render_header(state)
    if choice == "1":
        mode = _select(state, "Fonte (default: URL única)", [("url", True, "URL/domínio; seed de crawl"), ("file", True, "TXT UTF-8; uma URL por linha")])
        if mode:
            render_header(state)
            print(f"Entrada selecionada: {mode}\n")
            state.input_mode = mode
            state.target = input("URL/domínio: " if mode == "url" else "Caminho TXT: ").strip()
            state.current_url = state.target or "-"
    elif choice == "2":
        state.project = input("Projeto (vazio=auto): ").strip()
    elif choice == "3":
        value = _select(state, "Dispositivo", [("mobile", True, "default"), ("desktop", True, "somente desktop"), ("both", True, "mobile + desktop; multiplica volume")])
        if value:
            state.device, state.current_device = value, value.upper()
    elif choice == "4":
        capabilities = provider_capabilities(blocks=state.runtime_blocks)
        value = _select(state, "Provider de IA - providers externos podem gerar cobrança por uso", [(name, capabilities[name].available, capabilities[name].reason) for name in PROVIDER_MENU_CHOICES])
        if value:
            state.ai_provider, state.ai_model, state.ai_reasoning = value, None, None
            if value == "none":
                state.content_remediation = False
                state.technical_remediation = False
            elif value in PROVIDERS:
                provider = PROVIDERS[value]
                default = os.environ.get(MODEL_ENV[provider], DEFAULT_MODELS[provider])
                chosen = _select(state, f"Modelo {provider} - o default público privilegia menor custo/complexidade", [(model, True, "default" if model == default else "suportado") for model in SUPPORTED_MODELS[provider]])
                state.ai_model = chosen or default
                effort_default = configured_reasoning(provider)
                efforts = REASONING_OPTIONS[provider]
                if len(efforts) == 1:
                    state.ai_reasoning = efforts[0]
                else:
                    effort = _select(state, f"Esforço/profundidade {provider} - menor nível reduz latência/tokens", [(item, True, "default mínimo" if item == effort_default else "suportado") for item in efforts])
                    state.ai_reasoning = effort or effort_default
                    apply_console_reasoning_environment(provider, state.ai_reasoning)
            else:
                print(paint("AUTO usa OpenAI/DeepSeek/MiMo; sem override explícito cada provider usa seu modelo mais simples e o menor esforço suportado.", DIM))
            state.ai_timeout = float(_number("Timeout por tentativa de IA", state.ai_timeout, minimum=1, help_text="limite de espera de cada chamada ao provider. Não é o tempo máximo da auditoria inteira."))
            os.environ[AI_TIMEOUT_ENV] = f"{state.ai_timeout:g}"
            state.error = ""
    elif choice == "5":
        capability = provider_capabilities(blocks=state.runtime_blocks)[state.ai_provider]
        if state.ai_provider == "none" or not capability.available:
            state.content_remediation = False
            state.technical_remediation = False
            state.error = "opção 5 requer uma IA configurada e ativa no item 4"
        else:
            state.content_remediation = input("Remediação de conteúdo por IA? Pode gerar chamadas/custo adicionais [s/N]: ").strip().casefold() == "s"
            state.technical_remediation = input("Remediação técnica de crawling/discovery por IA? Advisory, pode gerar chamadas/custo adicionais [s/N]: ").strip().casefold() == "s"
            state.error = ""
    elif choice == "6":
        state.web_performance = input("Web Performance? Usa API/quota externa PageSpeed/CrUX [s/N]: ").strip().casefold() == "s"
        if state.web_performance:
            crux_available = bool((os.environ.get("RASAI_CRUX_API_KEY") or "").strip())
            value = _select(state, "Field data", [("auto", True, "PageSpeed + CrUX direto quando necessário/disponível"), ("pagespeed", True, "PageSpeed"), ("crux", crux_available, "exige RASAI_CRUX_API_KEY"), ("none", True, "sem field data; Lighthouse lab permanece")])
            if value:
                state.field_source = value
            state.web_timeout = float(_number("Timeout PageSpeed/Lighthouse por URL", state.web_timeout, minimum=1, help_text="limite de espera da resposta completa da API PageSpeed/CrUX. PageSpeed executa Lighthouse remotamente; a API pública não expõe um parâmetro separado para o timeout interno de carregamento da página."))
            os.environ[WEB_PERFORMANCE_TIMEOUT_ENV] = f"{state.web_timeout:g}"
            state.error = ""
    elif choice == "7":
        try:
            value = int(input("max-pages (>0; maior valor aumenta teto potencial de consumo): "))
            if value <= 0: raise ValueError
            state.max_pages, state.error = value, ""
        except ValueError:
            state.error = "max-pages inválido"
    elif choice == "8":
        try:
            value = int(input("WebPerf max-pages (>=0; 0=todas as páginas auditadas): "))
            if value < 0: raise ValueError
            state.web_max_pages, state.error = value, ""
        except ValueError:
            state.error = "WebPerf max-pages inválido"
    elif choice == "9":
        state.language = input(f"Idioma [{state.language}]: ").strip() or state.language
        state.market = input(f"Mercado [{state.market}]: ").strip() or state.market
    elif choice == "10":
        state.audits_root = input(f"Raiz [{state.audits_root}]: ").strip() or state.audits_root
    elif choice == "11":
        _configure_apdex(state)
    elif choice == "12":
        _configure_timezone(state)


def _execution_readiness(state: State) -> tuple[bool, str]:
    try:
        configured_presentation_timezone()
        preflight(state)
        validate_m23_state(state)
    except (OSError, ValueError, UnicodeError) as exc:
        return False, str(exc)
    return True, "configuração válida"


def _save_configuration(state: State) -> bool:
    try:
        sync_nonsecret_runtime_environment(state)
        path = save_console_config(state, get_config_path(state))
        set_config_path(state, path)
        mark_dirty(state, False)
        sync_nonsecret_runtime_environment(state)
        state.operation = "LOCAL:SAVE_CONFIG"
        state.error = ""
        render_header(state)
        print(paint(f"Configuração salva em: {path}", GREEN, bold=True))
        print(paint("Chaves/API tokens não são gravados no INI por segurança.", YELLOW))
        input("\nENTER para continuar...")
        return True
    except (OSError, UnicodeError, ValueError) as exc:
        state.error = f"falha ao salvar configuração: {type(exc).__name__}: {exc}"
        return False


def _confirm_exit(state: State) -> bool:
    dirty = is_dirty(state)
    volatile = has_volatile_secrets(state)
    if not dirty and not volatile:
        return True
    while True:
        render_header(state)
        print("ENCERRAR CONSOLE\n")
        if dirty:
            print(paint("Há alterações de configuração ainda não salvas no arquivo INI.", YELLOW, bold=True))
        if volatile:
            print(paint("Uma ou mais alterações de credenciais desta sessão diferem da persistência do Windows e não serão mantidas como default de novos processos.", YELLOW, bold=True))
        if dirty:
            print("\nS. Salvar parâmetros não sensíveis e sair")
            print("D. Sair descartando alterações não salvas")
            print("C. Cancelar")
            choice = input("Escolha: ").strip().upper()
            if choice == "S":
                if _save_configuration(state):
                    return True
            elif choice == "D":
                return True
            elif choice == "C":
                return False
        else:
            print("\nQ. Confirmar saída (alterações voláteis de credenciais da sessão serão descartadas)")
            print("C. Cancelar")
            choice = input("Escolha: ").strip().upper()
            if choice == "Q":
                return True
            if choice == "C":
                return False


def _artifact_action(state: State, action: str) -> None:
    if action == "P":
        ok, detail = open_audit_folder(state)
        state.operation = "LOCAL:OPEN_AUDIT_FOLDER"
    else:
        ok, detail = open_report(state)
        state.operation = "LOCAL:OPEN_REPORT"
    state.error = "" if ok else detail
    render_header(state)
    print((paint("Aberto: ", GREEN, bold=True) if ok else paint("Não foi possível abrir: ", RED, bold=True)) + detail)
    input("\nENTER para continuar...")


def _render_actual_usage(state: State) -> None:
    workspace, _ = artifact_status(state)
    usage = actual_usage(workspace)
    synthetic = actual_m23_usage(workspace)
    coverage = load_collection_coverage(workspace)
    print("\nCONSUMO E COBERTURA REAL PERSISTIDOS")
    print("-" * 100)
    if usage is None:
        print(paint("Telemetria IA/Web Performance indisponível para esta auditoria.", YELLOW))
    else:
        print(f"Tentativas IA       : {usage.ai_attempts} (sucesso: {usage.ai_successes})")
        print(f"Tokens input        : {usage.input_tokens:,}")
        print(f"Tokens input cache  : {usage.cached_input_tokens:,}")
        print(f"Tokens output       : {usage.output_tokens:,}")
        print(f"Tokens reasoning    : {usage.reasoning_tokens:,}")
        print(f"Tokens total        : {paint(f'{usage.total_tokens:,}', CYAN, bold=True)}")
        if usage.costs:
            rendered_costs = " | ".join(f"{currency} {amount:.8f}" for currency, amount in usage.costs)
            print(f"Custo IA estimado   : {paint(rendered_costs, YELLOW, bold=True)}")
        elif usage.ai_attempts:
            print("Custo IA estimado   : não disponível com dados de pricing/tokens persistidos")
        else:
            print("Custo IA estimado   : 0 (nenhuma tentativa de IA persistida)")
        if usage.unpriced_ai_attempts:
            print(paint(f"Atenção: {usage.unpriced_ai_attempts} tentativa(s) IA possuem tokens mas não custo estimável persistido.", YELLOW, bold=True))
        if usage.web_external_calls:
            services = ", ".join(f"{service}={count}" for service, count in usage.web_services)
            print(f"Chamadas Web Perf.  : {usage.web_external_calls} ({services})")
            print("Custo Web Perf.     : não presumido; o console contabiliza chamadas/quota sem inventar preço.")
        else:
            print("Chamadas Web Perf.  : 0")
    if coverage is not None:
        print(f"Web Performance     : {coverage.web_status} | PageSpeed {coverage.pagespeed_successes}/{coverage.pagespeed_attempts} | CrUX via PageSpeed {coverage.crux_via_pagespeed} | CrUX API direta {coverage.crux_successes}/{coverage.crux_attempts}")
        if coverage.web_reason:
            print(f"Motivo Web Perf.    : {coverage.web_reason}")
        a11y_state = "OBTIDA" if coverage.accessibility_contexts and coverage.accessibility_obtained == coverage.accessibility_contexts else ("PARCIAL" if coverage.accessibility_obtained else "NÃO OBTIDA")
        print(f"Acessibilidade      : {a11y_state} | {coverage.accessibility_obtained}/{coverage.accessibility_contexts} contexto(s)")
        print(f"Motivo Acessib.     : {coverage.accessibility_reason}")
    if synthetic is None:
        print("Navegações Apdex    : telemetria não materializada")
    elif not synthetic.enabled:
        print("Navegações Apdex    : 0 (Synthetic Apdex desabilitado)")
    else:
        print(f"Navegações Apdex    : {synthetic.attempted_samples} tentativa(s), {synthetic.valid_samples} válidas, {synthetic.invalid_samples} inválidas, contextos={synthetic.contexts}, status={synthetic.status}")
        print("Custo Synthetic     : sem API paga própria; há CPU/tempo local e tráfego HTTP real contra o alvo.")
    print("Observação           : custos são estimativas técnicas dos adapters, não invoice do provider.")


def _post_run_actions(state: State) -> bool:
    while True:
        render_header(state)
        workspace, report = artifact_status(state)
        if state.audit_id:
            print(f"Audit ID    : {state.audit_id}")
        _render_actual_usage(state)
        print("\nAÇÕES DA AUDITORIA DESTA SESSÃO")
        print(f" P. Abrir pasta da auditoria [{availability_badge(bool(workspace))}]")
        print(f" I. Abrir relatório HTML   [{availability_badge(bool(report))}]")
        print(" V. Voltar ao menu")
        print(" Q. Sair")
        choice = input("Escolha: ").strip().upper()
        if choice == "Q":
            if _confirm_exit(state):
                return True
            continue
        if choice == "V": return False
        if choice == "P" and workspace: _artifact_action(state, "P")
        elif choice == "I" and report: _artifact_action(state, "I")
        elif choice in {"P", "I"}: state.error = "artefato ainda não disponível para esta auditoria"


def _menu(state: State) -> str:
    render_header(state)
    capability = provider_capabilities(blocks=state.runtime_blocks)[state.ai_provider]
    remediation_available = state.ai_provider != "none" and capability.available
    badges = menu_cost_badges(state)
    estimate = estimate_exposure(state)
    m23_attempts, m23_load = synthetic_load_summary(state)
    path = get_config_path(state)
    config_state = paint("ALTERAÇÕES NÃO SALVAS", YELLOW, bold=True) if is_dirty(state) else paint("SALVO", GREEN, bold=True)
    print("CONFIGURAÇÃO DA AUDITORIA\n")
    print(f"Arquivo INI: {path or '<não resolvido>'} | {config_state} | credenciais: sessão/Windows User; nunca no INI")
    print("Exposição financeira potencial: " + paint(estimate.level, cost_color(estimate.level), bold=True))
    if estimate.min_pages == estimate.max_pages:
        print(f"Volume prévio: {estimate.min_pages} página(s) conhecida(s) × {estimate.device_contexts} contexto(s) de dispositivo")
    else:
        print(f"Volume prévio: {estimate.min_pages} página conhecida → teto {estimate.max_pages} × {estimate.device_contexts} contexto(s) de dispositivo")
    if estimate.max_ai_attempts:
        print(f"IA potencial: {estimate.min_ai_attempts}-{estimate.max_ai_attempts} tentativa(s)")
    if estimate.max_web_calls:
        print(f"APIs Web Performance potenciais: {estimate.min_web_calls}-{estimate.max_web_calls} chamada(s)")
    if m23_attempts:
        print(paint("Carga Synthetic Apdex potencial: " + m23_load, YELLOW, bold=True))
    print()
    print(f"1. Entrada               : {'URL única' if state.input_mode == 'url' else 'TXT'} | {state.target or '<não informada>'}")
    print(f"2. Projeto               : {state.project or '<auto>'}")
    print(f"3. Dispositivo           : {state.device}{badges['device']}")
    effort = state.ai_reasoning or (LOWEST_REASONING.get(PROVIDERS.get(state.ai_provider, ''), '-') if state.ai_provider in PROVIDERS else '-')
    print(f"4. IA                    : {state.ai_provider} [{availability_badge(capability.available)}] | modelo={state.ai_model or '<default mínimo>'} | esforço={effort} | timeout={state.ai_timeout:g}s{badges['ai']}")
    if remediation_available:
        print(f"5. Remediações IA        : conteúdo={bool_badge(state.content_remediation)} | técnica crawling={bool_badge(state.technical_remediation)} [DISPONÍVEL - IA ativa no item 4]{badges['remediation']}")
    else:
        print("5. Remediações IA        : " + paint("INDISPONÍVEL", RED, bold=True) + " [REQUER IA CONFIGURADA E ATIVA NO ITEM 4]")
    print(f"6. Web Performance       : {bool_badge(state.web_performance)} | field={state.field_source} | timeout={state.web_timeout:g}s{badges['web']}")
    print(f"7. max-pages             : {state.max_pages}{badges['max_pages']}")
    print(f"8. WebPerf max-pages     : {state.web_max_pages}{badges['web_max_pages']}")
    print(f"9. Idioma / mercado      : {state.language} / {state.market}")
    print(f"10. Raiz auditorias      : {state.audits_root}")
    if state.synthetic_apdex:
        print(f"11. Synthetic Apdex      : {bool_badge(True)} [CARGA SINTÉTICA] | T={state.apdex_threshold}s | válidas={state.apdex_samples} | tentativas={state.apdex_max_attempts} | páginas={state.apdex_max_pages} | timeout={state.apdex_timeout:g}s | delay={state.apdex_delay:g}s | concorrência={state.apdex_concurrency}")
    else:
        print(f"11. Synthetic Apdex      : {bool_badge(False)} [SEM CUSTO API PRÓPRIO]")
    presentation_timezone = configured_presentation_timezone()
    print(f"12. Timezone apresentação: {presentation_timezone} ({timezone_offset_label(presentation_timezone)})")
    ready, reason = _execution_readiness(state)
    marker = availability_badge(ready)
    reason_text = paint(reason, GREEN if ready else RED)
    print("\nAÇÕES")
    print("S. Salvar configuração INI [SEM CHAVES]")
    print("H. Ajuda / custos")
    print("E. Variáveis de ambiente / credenciais")
    print("C. Histórico / relatórios consolidados [OFFLINE - sem APIs]")
    print(f"R. Executar [{marker}] {reason_text}")
    print("Q. Sair")
    workspace, report = artifact_status(state)
    if workspace or report:
        print("\nARTEFATOS")
        print(f"P. Abrir última pasta [{availability_badge(bool(workspace))}]")
        print(f"I. Abrir último relatório [{availability_badge(bool(report))}]")
    return input("Escolha: ").strip().upper()


def main() -> int:
    state = State()
    loaded = load_console_config(state)
    set_config_path(state, loaded.path)
    present_env = {name for name in ENV_NAMES if (os.environ.get(name) or "").strip()}
    issues = list(loaded.warnings)
    issues.extend(apply_environment_defaults(state, names=present_env))
    issues.extend(apply_m23_environment_defaults(state, names=present_env))
    sync_nonsecret_runtime_environment(state)
    mark_dirty(state, False)
    state.error = "; ".join(issues)
    while True:
        choice = _menu(state)
        if choice == "Q":
            if _confirm_exit(state):
                return 0
            continue
        if choice == "S":
            _save_configuration(state)
            continue
        if choice == "H":
            render_help(state)
            render_m23_help(state)
            input("\nENTER para voltar ao menu...")
            continue
        if choice == "E":
            before = configuration_fingerprint(state)
            _environment_menu(state)
            sync_nonsecret_runtime_environment(state)
            if configuration_fingerprint(state) != before:
                mark_dirty(state)
            continue
        if choice in {"P", "I"}:
            _artifact_action(state, choice)
            continue
        if choice == "R":
            ready, reason = _execution_readiness(state)
            if not ready:
                state.status, state.operation, state.error = "PRECHECK_BLOCKED", "LOCAL:PRECHECK", reason
                continue
            sync_nonsecret_runtime_environment(state)
            run_audit_from_console(state)
            if _post_run_actions(state): return 0
            state.status, state.operation, state.error = "READY", "LOCAL:MENU", ""
            continue
        before = configuration_fingerprint(state)
        _configure(state, choice)
        sync_nonsecret_runtime_environment(state)
        if configuration_fingerprint(state) != before:
            mark_dirty(state)


if __name__ == "__main__":
    raise SystemExit(main())
