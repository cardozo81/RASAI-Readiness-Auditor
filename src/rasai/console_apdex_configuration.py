"""Interactive configuration for both Synthetic Apdex domains."""
from __future__ import annotations

import math
import os
from pathlib import Path

from rasai.apdex_concurrency_policy import (
    EXPERIENCE_MAX_CONCURRENCY,
    NAVIGATION_MAX_CONCURRENCY,
    experience_risk,
    navigation_risk,
)
from rasai.configuration_value_labels import configuration_value_choice, configuration_value_info
from rasai.console_confirmation_contract import confirm_sensitive
from rasai.console_input_contract import EditCancelled, prompt_number, prompt_text, prompt_yes_no
from rasai.console_m23 import State, config_from_state, experience_from_state, synthetic_load_summary
from rasai.experience_architecture_guidance_358 import resolve_experience_architecture_guidance
from rasai.device_context import canonical_single_device_mix
from rasai.console_ui import DIM, YELLOW, paint
from rasai.m25_cli import (
    DEFAULT_UX_CONCURRENCY,
    DEFAULT_UX_CONSOLE_ERROR_CAPTURE,
    DEFAULT_UX_CONSOLE_ERRORS_AFFECT,
    DEFAULT_UX_DELAY_SECONDS,
    DEFAULT_UX_FETCH_CAPTURE,
    DEFAULT_UX_JAVASCRIPT_ERROR_CAPTURE,
    DEFAULT_UX_JAVASCRIPT_ERRORS_AFFECT,
    DEFAULT_UX_MAX_ERROR_DETAILS,
    DEFAULT_UX_DEVICE_MIX,
    DEFAULT_UX_ERROR_SCOPE,
    DEFAULT_UX_FRUSTRATED_SECONDS,
    DEFAULT_UX_KPM,
    DEFAULT_UX_MAX_PAGES,
    DEFAULT_UX_REQUEST_ERRORS_AFFECT,
    DEFAULT_UX_SAMPLES,
    DEFAULT_UX_XHR_CAPTURE,
    DEFAULT_UX_SATISFIED_SECONDS,
    DEFAULT_UX_SESSION_MODE,
    DEFAULT_UX_SETTLE_SECONDS,
    DYNATRACE_APPLICATION_ID_ENV,
    DYNATRACE_BASE_URL_ENV,
    DYNATRACE_CONFIG_JSON_ENV,
    DYNATRACE_IMPORT_ENV,
    UX_CONCURRENCY_ENV,
    UX_DELAY_ENV,
    UX_DEVICE_MIX_ENV,
    UX_ENABLED_ENV,
    UX_ERRORS_ENV,
    UX_JAVASCRIPT_ERRORS_ENV,
    UX_REQUEST_ERRORS_ENV,
    UX_CONSOLE_ERRORS_ENV,
    UX_JAVASCRIPT_CAPTURE_ENV,
    UX_XHR_CAPTURE_ENV,
    UX_FETCH_CAPTURE_ENV,
    UX_CONSOLE_CAPTURE_ENV,
    UX_MAX_ERROR_DETAILS_ENV,
    UX_ERROR_SCOPE_ENV,
    UX_FRUSTRATED_ENV,
    UX_KPM_ENV,
    UX_MAX_ATTEMPTS_ENV,
    UX_MAX_PAGES_ENV,
    UX_SAMPLES_ENV,
    UX_SATISFIED_ENV,
    UX_SESSION_MODE_ENV,
    UX_SETTLE_ENV,
    parse_device_mix,
)
from rasai.m25_dynatrace import SUPPORTED_TIME_KPMS
from rasai.m25_dynatrace_defaults import DYNATRACE_LOAD_PRIMARY_KPM
from rasai.synthetic_runtime_profiles import (
    configured_preset,
    describe_preset,
    env_name,
    preset_ids,
)


def _number(
    prompt: str,
    current: float,
    *,
    minimum: float = 0.0,
    integer: bool = False,
    help_text: str = "",
) -> float | int:
    if help_text:
        print(paint(f"  Para que serve: {help_text}", DIM))
    value = prompt_number(prompt, current, integer=integer)
    if value < minimum:
        raise ValueError(f"{prompt} deve ser >= {minimum:g}")
    return int(value) if integer else float(value)


def _yes_no(prompt: str, current: bool) -> bool:
    return prompt_yes_no(prompt, current)


def _choice(
    prompt: str,
    current: str,
    allowed: tuple[str, ...],
    domain_name: str = "",
) -> str:
    options = ", ".join(configuration_value_choice(domain_name, item) for item in allowed)
    current_label = configuration_value_info(domain_name, current)
    print(f"  Opções aceitas: {options}")
    raw = prompt_text(prompt, current=current_label)
    value = current if raw == current_label else raw
    lookup = {item.casefold(): item for item in allowed}
    selected = lookup.get(value.casefold())
    if selected is None:
        raise ValueError(f"{prompt}: use " + ", ".join(allowed))
    return selected


def _configure_experience_runtime_profiles(device_value: str) -> None:
    """Expose only the synthetic profile inherited from the audit device."""
    device = str(device_value or "mobile").strip().upper()
    if device not in {"MOBILE", "DESKTOP"}:
        raise ValueError("Experience Apdex requer device da AUD igual a mobile ou desktop")
    labels = {
        "client": "Cliente/browser",
        "hardware": "Hardware/CPU",
        "network": "Rede",
    }
    print(paint("\n  Perfil sintético efetivo · herdado do device da AUD:", DIM))
    print(paint(f"    {device.title()} [100% das amostras Experience]", DIM))
    for kind in ("client", "hardware", "network"):
        name = env_name(kind, device)
        current = configured_preset(kind, device, os.environ)
        print(
            paint(
                f"      {labels[kind]}: {describe_preset(kind, current)} "
                f"· {name}={current}",
                DIM,
            )
        )
    print(paint(
        "  O CAT-07 não possui device mix independente. Alterar o device da AUD altera "
        "o contexto sintético de Navigation e Experience.",
        DIM,
    ))
    if not _yes_no("Alterar o perfil sintético deste device nesta sessão", False):
        return

    for kind in ("client", "hardware", "network"):
        name = env_name(kind, device)
        current = configured_preset(kind, device, os.environ)
        selected = _choice(
            labels[kind],
            current,
            preset_ids(kind, device),
            name,
        )
        os.environ[name] = selected


def _required_positive(prompt: str, current: float | None) -> float:
    shown = current if current is not None else None
    raw = prompt_text(prompt, current=shown, empty_keeps_current=current is not None)
    if raw:
        value = float(raw)
    elif current is not None:
        value = current
    else:
        raise ValueError(f"{prompt} é obrigatório")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{prompt} deve ser número > 0")
    return value


def _origin(value: object, default: object) -> str:
    return "PADRÃO" if value == default else "CUSTOMIZADO"


def _show_experience_defaults() -> None:
    print(paint("\n  Defaults e variáveis do Synthetic User Experience Apdex:", DIM))
    rows = (
        (UX_ENABLED_ENV, "false", "RASAi"),
        (UX_SAMPLES_ENV, DEFAULT_UX_SAMPLES, "RASAi"),
        (UX_MAX_ATTEMPTS_ENV, "ceil(1.25 × samples)", "RASAi derivado"),
        (UX_MAX_PAGES_ENV, DEFAULT_UX_MAX_PAGES, "RASAi"),
        (UX_SESSION_MODE_ENV, DEFAULT_UX_SESSION_MODE, "RASAi; sem equivalente RUM"),
        (UX_KPM_ENV, DEFAULT_UX_KPM, f"fallback compatível; Dynatrace Load prefere {DYNATRACE_LOAD_PRIMARY_KPM}"),
        (UX_SATISFIED_ENV, f"{DEFAULT_UX_SATISFIED_SECONDS:g}s", "Dynatrace Load fallback/reference"),
        (UX_FRUSTRATED_ENV, f"{DEFAULT_UX_FRUSTRATED_SECONDS:g}s", "Dynatrace Load fallback/reference"),
        (UX_ERRORS_ENV, "true", "Dynatrace: erros elegíveis podem tornar a ação Frustrated"),
        (UX_JAVASCRIPT_ERRORS_ENV, str(DEFAULT_UX_JAVASCRIPT_ERRORS_AFFECT).lower(), "Dynatrace default: JavaScript errors afetam Apdex"),
        (UX_REQUEST_ERRORS_ENV, str(DEFAULT_UX_REQUEST_ERRORS_AFFECT).lower(), "Dynatrace default: request/HTTP/CSP errors afetam Apdex"),
        (UX_CONSOLE_ERRORS_ENV, str(DEFAULT_UX_CONSOLE_ERRORS_AFFECT).lower(), "Dynatrace: console.error só participa quando captura é habilitada"),
        (UX_JAVASCRIPT_CAPTURE_ENV, str(DEFAULT_UX_JAVASCRIPT_ERROR_CAPTURE).lower(), "Dynatrace WebApplicationConfig"),
        (UX_XHR_CAPTURE_ENV, str(DEFAULT_UX_XHR_CAPTURE).lower(), "Dynatrace WebApplicationConfig"),
        (UX_FETCH_CAPTURE_ENV, str(DEFAULT_UX_FETCH_CAPTURE).lower(), "Dynatrace WebApplicationConfig"),
        (UX_CONSOLE_CAPTURE_ENV, str(DEFAULT_UX_CONSOLE_ERROR_CAPTURE).lower(), "Dynatrace: cce=1 é opt-in"),
        (UX_MAX_ERROR_DETAILS_ENV, DEFAULT_UX_MAX_ERROR_DETAILS, "Dynatrace maxErrorsToCapture"),
        (UX_ERROR_SCOPE_ENV, DEFAULT_UX_ERROR_SCOPE, "default all aproxima a cobertura padrão Dynatrace; demais escopos são RASAi"),
        (UX_SETTLE_ENV, f"{DEFAULT_UX_SETTLE_SECONDS:g}s", "RASAi"),
        (UX_DELAY_ENV, f"{DEFAULT_UX_DELAY_SECONDS:g}s", "RASAi"),
        (UX_CONCURRENCY_ENV, DEFAULT_UX_CONCURRENCY, "RASAi"),
        (DYNATRACE_IMPORT_ENV, "false", "RASAi"),
        (DYNATRACE_BASE_URL_ENV, "vazio", "somente importação live"),
        (DYNATRACE_APPLICATION_ID_ENV, "vazio", "somente importação live"),
        (DYNATRACE_CONFIG_JSON_ENV, "vazio", "importação offline/reproduzível"),
    )
    for name, default, source in rows:
        print(paint(f"    {name} = {default}  [{source}]", DIM))
    print(paint("    DYNATRACE_API_TOKEN = secret de ambiente; nunca persistido no INI/report.", DIM))


def _show_effective_experience(state: State) -> None:
    derived_attempts = max(
        state.apdex_experience_samples,
        int(math.ceil(state.apdex_experience_samples * 1.25)),
    )
    values = (
        ("Amostras", state.apdex_experience_samples, DEFAULT_UX_SAMPLES),
        ("Máx. tentativas", state.apdex_experience_max_attempts, derived_attempts),
        ("Máx. páginas", state.apdex_experience_max_pages, DEFAULT_UX_MAX_PAGES),
        ("Device herdado da AUD", str(getattr(state, "device", "mobile")).upper(), "MOBILE"),
        ("Sessão", state.apdex_experience_session_mode, DEFAULT_UX_SESSION_MODE),
        ("KPM executável", state.apdex_experience_kpm, DEFAULT_UX_KPM),
        ("Satisfied", state.apdex_experience_satisfied, DEFAULT_UX_SATISFIED_SECONDS),
        ("Frustrated", state.apdex_experience_frustrated, DEFAULT_UX_FRUSTRATED_SECONDS),
        ("Erros afetam o Apdex", state.apdex_experience_errors, True),
        ("Erros JavaScript afetam o Apdex", state.apdex_experience_javascript_errors, DEFAULT_UX_JAVASCRIPT_ERRORS_AFFECT),
        ("Erros de requisição afetam o Apdex", state.apdex_experience_request_errors, DEFAULT_UX_REQUEST_ERRORS_AFFECT),
        ("Erros de console afetam o Apdex", state.apdex_experience_console_errors, DEFAULT_UX_CONSOLE_ERRORS_AFFECT),
        ("Captura erros JavaScript", state.apdex_experience_javascript_capture, DEFAULT_UX_JAVASCRIPT_ERROR_CAPTURE),
        ("Captura XMLHttpRequest", state.apdex_experience_xhr_capture, DEFAULT_UX_XHR_CAPTURE),
        ("Captura Fetch", state.apdex_experience_fetch_capture, DEFAULT_UX_FETCH_CAPTURE),
        ("Captura console.error", state.apdex_experience_console_capture, DEFAULT_UX_CONSOLE_ERROR_CAPTURE),
        ("Máximo de erros detalhados", state.apdex_experience_max_error_details, DEFAULT_UX_MAX_ERROR_DETAILS),
        ("Escopo dos erros de requisição", state.apdex_experience_error_scope, DEFAULT_UX_ERROR_SCOPE),
        ("Settle", state.apdex_experience_settle, DEFAULT_UX_SETTLE_SECONDS),
        ("Delay", state.apdex_experience_delay, DEFAULT_UX_DELAY_SECONDS),
        ("Concorrência", state.apdex_experience_concurrency, DEFAULT_UX_CONCURRENCY),
    )
    values += (
        ("Arquitetura declarada pelo operador", getattr(state, "apdex_experience_architecture", "AUTO"), "AUTO"),
        ("Modo de calibração de experiência", getattr(state, "apdex_experience_profile_mode", "CUSTOM"), "CUSTOM"),
    )
    print(paint("\n  Configuração efetiva:", DIM))
    for label, value, default in values:
        print(paint(f"    {label}: {value} [{_origin(value, default)}]", DIM))
    if state.apdex_dynatrace_import:
        print(paint("    Calibração: IMPORTADA DO DYNATRACE (sobrepõe KPM/thresholds quando suportados; fallback explícito quando necessário)", DIM))


def _configure_navigation(state: State) -> None:
    print("\nSynthetic Navigation Apdex")
    print("Mede repetidamente NAVIGATION_LOAD em Chromium. T é definido pelo usuário/SLO; não existe default metodológico universal.\n")
    enabled = _yes_no("Habilitar Synthetic Navigation Apdex? Gera tráfego HTTP real contra o alvo", state.synthetic_apdex)
    state.synthetic_apdex = enabled
    if not enabled:
        return

    state.apdex_threshold = _required_positive("Threshold T em segundos", state.apdex_threshold)
    state.apdex_samples = int(_number(
        "Amostras válidas por URL/dispositivo", state.apdex_samples, minimum=1, integer=True,
        help_text="100 é o default operacional; 1-99 é diagnóstico small-group (*).",
    ))
    suggested_attempts = max(state.apdex_samples, int(math.ceil(state.apdex_samples * 1.25)))
    if state.apdex_max_attempts < state.apdex_samples:
        state.apdex_max_attempts = suggested_attempts
    state.apdex_max_attempts = int(_number(
        "Máximo de tentativas por URL/dispositivo", state.apdex_max_attempts,
        minimum=state.apdex_samples, integer=True,
        help_text="permite repor amostras inválidas; o default derivado é ceil(1.25 × amostras).",
    ))
    state.apdex_max_pages = int(_number(
        "Máximo de páginas (0=todas)", state.apdex_max_pages, minimum=0, integer=True,
        help_text="limita quantas páginas auditadas recebem navegações sintéticas.",
    ))
    minimum_timeout = 4.0 * state.apdex_threshold
    recommended_timeout = max(45.0, minimum_timeout + 5.0)
    if state.apdex_timeout <= minimum_timeout:
        state.apdex_timeout = recommended_timeout
    state.apdex_timeout = float(_number(
        "Timeout por navegação (deve ser > 4T)", state.apdex_timeout, minimum=0.000001,
        help_text="evita truncar artificialmente a faixa Frustrated.",
    ))
    state.apdex_delay = float(_number(
        "Delay mínimo entre inícios", state.apdex_delay, minimum=0.0,
        help_text="valores maiores reduzem a pressão sobre o alvo e aumentam a duração.",
    ))
    selected_concurrency = int(_number(
        f"Concorrência (1-{NAVIGATION_MAX_CONCURRENCY})", state.apdex_concurrency, minimum=1, integer=True,
        help_text="1 é recomendado; 3-4 exigem delay >= 1 s e aumentam o risco de interferência na medição/alvo.",
    ))
    if selected_concurrency > NAVIGATION_MAX_CONCURRENCY:
        raise ValueError(f"Concorrência Navigation deve estar entre 1 e {NAVIGATION_MAX_CONCURRENCY}")
    print(paint(f"  Grau de risco: {navigation_risk(selected_concurrency)}", YELLOW if selected_concurrency > 1 else DIM, bold=selected_concurrency > 1))
    if selected_concurrency >= 4 and not confirm_sensitive(
        "CONCORRÊNCIA",
        action_label=f"Usar concorrência Navigation {selected_concurrency} - {navigation_risk(selected_concurrency)}",
        back_label="Cancelar a edição do Synthetic Apdex",
    ):
        raise EditCancelled()
    state.apdex_concurrency = selected_concurrency
    config_from_state(state)


def _configure_experience(state: State) -> None:
    print("\nSynthetic User Experience Apdex")
    print("Gera apdex-experience.html quando habilitado e executado. Usa exclusivamente o device selecionado para a AUD.")
    print("O baseline usa thresholds Dynatrace Load 3s/12s com USER_ACTION_DURATION como fallback executável; VISUALLY_COMPLETE não é falsamente emulado.\n")
    _show_experience_defaults()
    enabled = _yes_no("Habilitar Synthetic User Experience Apdex", state.apdex_experience)
    state.apdex_experience = enabled
    if not enabled:
        return
    print(paint("  Arquitetura é uma declaração prévia; a classificação M6 será descoberta depois da coleta.", DIM))
    state.apdex_experience_architecture = _choice(
        "Arquitetura esperada da URL (AUTO = ainda não determinada)",
        state.apdex_experience_architecture,
        ("AUTO", "STATIC_OR_SSR", "HYDRATED", "CSR_SPA", "MIXED", "UNKNOWN"),
    )
    state.apdex_experience_profile_mode = _choice(
        "Calibração do Experience Apdex",
        "DYNATRACE_IMPORTED" if state.apdex_dynatrace_import else state.apdex_experience_profile_mode,
        ("CUSTOM", "DYNATRACE_GUIDED", "DYNATRACE_IMPORTED"),
    )
    print(paint(
        "  Modo selecionado: " + state.apdex_experience_profile_mode
        + " | arquitetura declarada: " + state.apdex_experience_architecture,
        DIM,
    ))
    print(paint("  Guided propõe apenas o baseline Load executável (USER_ACTION_DURATION, 3s/12s); não mede XHR/soft navigation.", DIM))
    if state.apdex_experience_profile_mode == "DYNATRACE_GUIDED":
        # Present the three proposed values BEFORE lengthy sample/profile/error
        # prompts and the sensitive concurrency gate. They are NOT yet applied.
        # The existing final approval later in this function remains mandatory.
        initial_preview = resolve_experience_architecture_guidance(
            {
                "kpm": state.apdex_experience_kpm,
                "satisfied_threshold_seconds": state.apdex_experience_satisfied,
                "frustrated_threshold_seconds": state.apdex_experience_frustrated,
            },
            selected_architecture=state.apdex_experience_architecture,
            profile_mode="DYNATRACE_GUIDED",
        )
        print(paint("\\n  PRÉVIA GUIADA ANTECIPADA (NÃO APLICADA):", YELLOW))
        for proposed in initial_preview["new_audit_configuration_preview"]:
            print(paint(
                f"    {proposed['variable']} = {proposed['value']}"
                f" | origem: {proposed['source']}"
                f" | substitui valor atual: "
                f"{'SIM' if proposed['would_override_current'] else 'NÃO'}",
                DIM,
            ))
        print(paint(
            "  Esta é só a prévia. A aplicação exige confirmação explícita "
            "depois dos parâmetros de amostragem/concorrência.",
            YELLOW,
        ))
    else:
        print(paint(
            "  Nenhum preset Guided será apresentado/aplicado em modo "
            + state.apdex_experience_profile_mode + ".",
            DIM,
        ))
    if state.apdex_experience_satisfied is None:
        state.apdex_experience_satisfied = DEFAULT_UX_SATISFIED_SECONDS
    if state.apdex_experience_frustrated is None:
        state.apdex_experience_frustrated = DEFAULT_UX_FRUSTRATED_SECONDS

    state.apdex_experience_samples = int(_number(
        "Amostras válidas totais por página", state.apdex_experience_samples, minimum=1, integer=True,
        help_text="target independente do Navigation; todas as amostras usam o device selecionado para a AUD.",
    ))
    suggested_attempts = max(
        state.apdex_experience_samples,
        int(math.ceil(state.apdex_experience_samples * 1.25)),
    )
    if state.apdex_experience_max_attempts < state.apdex_experience_samples:
        state.apdex_experience_max_attempts = suggested_attempts
    state.apdex_experience_max_attempts = int(_number(
        "Máximo de tentativas totais por página", state.apdex_experience_max_attempts,
        minimum=state.apdex_experience_samples, integer=True,
        help_text="default derivado: ceil(1.25 × amostras).",
    ))
    state.apdex_experience_max_pages = int(_number(
        "Máximo de páginas Experience (0=todas)", state.apdex_experience_max_pages,
        minimum=0, integer=True,
    ))
    state.apdex_experience_device_mix = canonical_single_device_mix(state.device)
    _configure_experience_runtime_profiles(state.device)
    state.apdex_experience_session_mode = _choice(
        "Modo de sessão",
        state.apdex_experience_session_mode,
        ("cold", "warm"),
        UX_SESSION_MODE_ENV,
    )
    if state.apdex_experience_profile_mode == "CUSTOM":
        state.apdex_experience_kpm = _choice(
            "KPM temporal executável",
            state.apdex_experience_kpm,
            tuple(sorted(SUPPORTED_TIME_KPMS)),
            UX_KPM_ENV,
        )
    state.apdex_experience_errors = _yes_no(
        "Erros qualificáveis podem forçar Frustrated", state.apdex_experience_errors
    )
    state.apdex_experience_javascript_errors = _yes_no(
        "Erros JavaScript afetam o Apdex", state.apdex_experience_javascript_errors
    )
    state.apdex_experience_request_errors = _yes_no(
        "Erros de requisição/HTTP/CSP afetam o Apdex", state.apdex_experience_request_errors
    )
    state.apdex_experience_console_errors = _yes_no(
        "Erros de console (console.error) afetam o Apdex", state.apdex_experience_console_errors
    )
    print(paint("  Captura e impacto no Apdex são controles independentes.", DIM))
    state.apdex_experience_javascript_capture = _yes_no(
        "Capturar erros JavaScript", state.apdex_experience_javascript_capture
    )
    state.apdex_experience_xhr_capture = _yes_no(
        "Capturar XMLHttpRequest (XHR)", state.apdex_experience_xhr_capture
    )
    state.apdex_experience_fetch_capture = _yes_no(
        "Capturar requisições Fetch", state.apdex_experience_fetch_capture
    )
    state.apdex_experience_console_capture = _yes_no(
        "Capturar console.error", state.apdex_experience_console_capture
    )
    state.apdex_experience_max_error_details = int(_number(
        "Máximo de erros detalhados por amostra",
        state.apdex_experience_max_error_details,
        minimum=0,
        integer=True,
        help_text="default Dynatrace 10; faixa 0..50 por amostra/página carregada. Não trunca os contadores agregados do RASAi.",
    ))
    if state.apdex_experience_max_error_details > 50:
        raise ValueError("Máximo de erros detalhados por amostra deve estar entre 0 e 50")
    if state.apdex_experience_console_errors and not state.apdex_experience_console_capture:
        raise ValueError("Para erros de console afetarem o Apdex, habilite também a captura de console.error")
    print(paint(
        "  Padrão Dynatrace: JavaScript, XHR e Fetch capturados; console.error desligado salvo cce=1; máximo de 10 erros por página.",
        DIM,
    ))
    state.apdex_experience_error_scope = _choice(
        "Escopo dos erros de requisição",
        state.apdex_experience_error_scope,
        ("navigation", "first-party", "all"),
        UX_ERROR_SCOPE_ENV,
    )
    state.apdex_experience_settle = float(_number(
        "Janela pós-load (segundos)", state.apdex_experience_settle, minimum=0.000001,
        help_text="janela limitada para XHR/fetch e recursos tardios.",
    ))
    state.apdex_experience_delay = float(_number(
        "Delay entre user actions (segundos)", state.apdex_experience_delay, minimum=0.0
    ))
    selected_experience_concurrency = int(_number(
        f"Concorrência Experience (1-{EXPERIENCE_MAX_CONCURRENCY})", state.apdex_experience_concurrency,
        minimum=1, integer=True,
        help_text="1 é recomendado; 3 exige delay >= 1 s, é avançado e deve ser escolhido explicitamente.",
    ))
    if selected_experience_concurrency > EXPERIENCE_MAX_CONCURRENCY:
        raise ValueError(f"Concorrência Experience deve estar entre 1 e {EXPERIENCE_MAX_CONCURRENCY}")
    print(paint(f"  Grau de risco: {experience_risk(selected_experience_concurrency)}", YELLOW if selected_experience_concurrency > 1 else DIM, bold=selected_experience_concurrency > 1))
    if selected_experience_concurrency >= 3 and not confirm_sensitive(
        "CONCORRÊNCIA",
        action_label=f"Usar concorrência Experience {selected_experience_concurrency} - {experience_risk(selected_experience_concurrency)}",
        back_label="Cancelar a edição do Synthetic Apdex",
    ):
        raise EditCancelled()
    state.apdex_experience_concurrency = selected_experience_concurrency

    state.apdex_dynatrace_import = (
        state.apdex_experience_profile_mode == "DYNATRACE_IMPORTED"
    )
    if state.apdex_dynatrace_import:
        current_json = state.apdex_dynatrace_config_json
        print(paint("  Prefira JSON exportado para calibração reproduzível. Deixe vazio para importação live.", DIM))
        raw_json = prompt_text(
            "Arquivo JSON Dynatrace",
            current=current_json or "",
            empty_keeps_current=False,
        )
        if raw_json:
            if not Path(raw_json).expanduser().is_file():
                raise ValueError("JSON Dynatrace configurado não existe")
            state.apdex_dynatrace_config_json = raw_json
        if state.apdex_dynatrace_config_json:
            state.dynatrace_base_url = ""
            state.dynatrace_application_id = ""
        else:
            state.dynatrace_base_url = prompt_text(
                "Dynatrace base URL",
                current=state.dynatrace_base_url or "",
            )
            state.dynatrace_application_id = prompt_text(
                "Dynatrace application ID",
                current=state.dynatrace_application_id or "",
            )
            if not state.dynatrace_base_url or not state.dynatrace_application_id:
                raise ValueError("importação Dynatrace live exige base URL e application ID")
            print(paint("  DYNATRACE_API_TOKEN é secret e deve ser configurado no menu E; nunca é salvo no INI.", DIM))
    else:
        state.apdex_dynatrace_config_json = ""
        state.dynatrace_base_url = ""
        state.dynatrace_application_id = ""
        if state.apdex_experience_profile_mode == "CUSTOM":
            state.apdex_experience_satisfied = _required_positive(
                f"Threshold Satisfied em segundos (default Dynatrace-compatible {DEFAULT_UX_SATISFIED_SECONDS:g}s)",
                state.apdex_experience_satisfied,
            )
            state.apdex_experience_frustrated = _required_positive(
                f"Threshold Frustrated em segundos (default Dynatrace-compatible {DEFAULT_UX_FRUSTRATED_SECONDS:g}s)",
                state.apdex_experience_frustrated,
            )
            if state.apdex_experience_frustrated <= state.apdex_experience_satisfied:
                raise ValueError("Threshold Frustrated deve ser maior que o threshold Satisfied")
        else:
            recommendation = resolve_experience_architecture_guidance(
                {
                    "kpm": state.apdex_experience_kpm,
                    "satisfied_threshold_seconds": state.apdex_experience_satisfied,
                    "frustrated_threshold_seconds": state.apdex_experience_frustrated,
                },
                selected_architecture=state.apdex_experience_architecture,
                profile_mode="DYNATRACE_GUIDED",
            )
            print(paint("\n  Prévia de alteração guiada para a PRÓXIMA auditoria:", YELLOW))
            for entry in recommendation["new_audit_configuration_preview"]:
                print(paint(
                    f"    {entry['variable']} = {entry['value']} "
                    f"[origem: {entry['source']}; altera campo atual: "
                    f"{'sim' if entry['would_override_current'] else 'não'}]",
                    DIM,
                ))
            print(paint(
                "  Não há perfil universal SPA. Load mede apenas a navegação inicial; "
                "nenhuma configuração muda sem confirmação.",
                DIM,
            ))
            if not _yes_no("Aplicar os 3 valores de referência Load executáveis", False):
                raise EditCancelled()
            state.apdex_experience_kpm = DEFAULT_UX_KPM
            state.apdex_experience_satisfied = DEFAULT_UX_SATISFIED_SECONDS
            state.apdex_experience_frustrated = DEFAULT_UX_FRUSTRATED_SECONDS

    experience_from_state(state)
    _show_effective_experience(state)


def configure_apdex(state: State) -> None:
    """Configure Navigation and User Experience Apdex with coherent defaults."""
    print("Synthetic Apdex gera tráfego HTTP real contra o alvo. Use somente com autorização e capacidade compatível.")
    print("Os dois domínios são independentes de IA e não alteram o SARI/SCORE.")
    print("V em qualquer campo cancela toda esta edição e preserva os valores anteriores.\n")

    tracked_state = {
        name: getattr(state, name)
        for name in dir(state)
        if (
            name == "synthetic_apdex"
            or name.startswith("apdex_")
            or name.startswith("dynatrace_")
        )
        and not name.startswith("__")
        and not callable(getattr(state, name))
    }
    prefixes = ("RASAI_APDEX_", "RASAI_SYNTHETIC_APDEX", "DYNATRACE_")
    tracked_environment = {
        name: value
        for name, value in os.environ.items()
        if name.startswith(prefixes)
    }
    try:
        _configure_navigation(state)
        # CAT-06 Navigation and CAT-07 Experience are independently selectable.
        # Disabling one must not hide calibration/architecture of the other.
        _configure_experience(state)
        state.error = ""
        attempts, load = synthetic_load_summary(state)
        if attempts:
            print(paint("\nCarga projetada Synthetic Apdex: " + load, YELLOW, bold=True))
    except EditCancelled:
        for name, value in tracked_state.items():
            setattr(state, name, value)
        for name in tuple(os.environ):
            if name.startswith(prefixes) and name not in tracked_environment:
                os.environ.pop(name, None)
        os.environ.update(tracked_environment)
        state.error = ""
        state.operation = "LOCAL:APDEX_EDIT_CANCELLED"
    except (ValueError, OverflowError) as exc:
        # A failed edit cannot leave half-applied architecture/preset values
        # or runtime profile environment mutations behind.
        for name, value in tracked_state.items():
            setattr(state, name, value)
        for name in tuple(os.environ):
            if name.startswith(prefixes) and name not in tracked_environment:
                os.environ.pop(name, None)
        os.environ.update(tracked_environment)
        state.error = str(exc)
