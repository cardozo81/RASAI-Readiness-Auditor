"""Interactive configuration for both Synthetic Apdex domains."""
from __future__ import annotations

import math
from pathlib import Path

from rasai.console_m23 import State, config_from_state, experience_from_state, synthetic_load_summary
from rasai.console_ui import DIM, YELLOW, paint
from rasai.m25_cli import DEFAULT_UX_DEVICE_MIX, parse_device_mix
from rasai.m25_dynatrace import SUPPORTED_TIME_KPMS


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
    raw = input(f"{prompt} [{current:g}]: ").strip()
    value = current if not raw else (int(raw) if integer else float(raw))
    if value < minimum:
        raise ValueError(f"{prompt} deve ser >= {minimum:g}")
    return int(value) if integer else float(value)


def _yes_no(prompt: str, current: bool) -> bool:
    suffix = "S/n" if current else "s/N"
    raw = input(f"{prompt} [{suffix}]: ").strip().casefold()
    if not raw:
        return current
    if raw in {"s", "sim", "y", "yes", "1", "true", "on"}:
        return True
    if raw in {"n", "nao", "não", "no", "0", "false", "off"}:
        return False
    raise ValueError("responda S ou N")


def _choice(prompt: str, current: str, allowed: tuple[str, ...]) -> str:
    options = ", ".join(allowed)
    raw = input(f"{prompt} [{current}] ({options}): ").strip()
    value = current if not raw else raw
    lookup = {item.casefold(): item for item in allowed}
    selected = lookup.get(value.casefold())
    if selected is None:
        raise ValueError(f"{prompt}: use {options}")
    return selected


def _device_mix(current: str) -> str:
    parsed = dict(parse_device_mix(current or DEFAULT_UX_DEVICE_MIX))
    mobile = float(parsed.get("MOBILE", 0.0))
    desktop = float(parsed.get("DESKTOP", 0.0))
    tablet = float(parsed.get("TABLET", 0.0))
    print(paint("  Distribuição da população sintética por dispositivo. A soma deve ser exatamente 100%.", DIM))
    print(paint("  O percentual distribui user actions/amostras; não representa a quantidade bruta de subrequests HTTP da página.", DIM))
    mobile = float(_number("Mobile %", mobile, minimum=0.0))
    desktop = float(_number("Desktop %", desktop, minimum=0.0))
    tablet = float(_number("Tablet %", tablet, minimum=0.0))
    raw = f"mobile={mobile:g},desktop={desktop:g},tablet={tablet:g}"
    parse_device_mix(raw)
    return raw


def _required_positive(prompt: str, current: float | None) -> float:
    shown = f"{current:g}" if current is not None else "obrigatório"
    raw = input(f"{prompt} [{shown}]: ").strip()
    if raw:
        value = float(raw)
    elif current is not None:
        value = current
    else:
        raise ValueError(f"{prompt} é obrigatório")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{prompt} deve ser número > 0")
    return value


def _configure_navigation(state: State) -> None:
    print("\nSynthetic Navigation Apdex")
    print("Mede repetidamente NAVIGATION_LOAD em Chromium. T é definido pelo usuário/SLO; não existe default metodológico universal.\n")
    enabled = _yes_no("Habilitar Synthetic Navigation Apdex? Gera tráfego HTTP real contra o alvo", state.synthetic_apdex)
    state.synthetic_apdex = enabled
    if not enabled:
        state.apdex_experience = False
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
    state.apdex_concurrency = int(_number(
        "Concorrência (1-2)", state.apdex_concurrency, minimum=1, integer=True,
        help_text="1 é o default conservador; 2 aumenta a carga concorrente.",
    ))
    config_from_state(state)


def _configure_experience(state: State) -> None:
    print("\nSynthetic User Experience Apdex")
    print("Gera apdex-experience.html quando habilitado e executado. Usa população Mobile/Desktop/Tablet configurável.\n")
    enabled = _yes_no("Habilitar Synthetic User Experience Apdex", state.apdex_experience)
    state.apdex_experience = enabled
    if not enabled:
        return
    if not state.synthetic_apdex:
        raise ValueError("Synthetic User Experience Apdex exige Synthetic Navigation Apdex habilitado")

    state.apdex_experience_samples = int(_number(
        "Amostras válidas totais por página", state.apdex_experience_samples, minimum=1, integer=True,
        help_text="as amostras são distribuídas entre dispositivos conforme os percentuais abaixo.",
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
    state.apdex_experience_device_mix = _device_mix(state.apdex_experience_device_mix)
    state.apdex_experience_session_mode = _choice(
        "Modo de sessão", state.apdex_experience_session_mode, ("cold", "warm")
    )
    state.apdex_experience_kpm = _choice(
        "KPM temporal", state.apdex_experience_kpm, tuple(sorted(SUPPORTED_TIME_KPMS))
    )
    state.apdex_experience_errors = _yes_no(
        "Erros qualificáveis forçam Frustrated", state.apdex_experience_errors
    )
    state.apdex_experience_error_scope = _choice(
        "Escopo de erros", state.apdex_experience_error_scope,
        ("navigation", "first-party", "all"),
    )
    state.apdex_experience_settle = float(_number(
        "Janela pós-load (segundos)", state.apdex_experience_settle, minimum=0.000001,
        help_text="janela limitada para XHR/fetch e recursos tardios.",
    ))
    state.apdex_experience_delay = float(_number(
        "Delay entre user actions (segundos)", state.apdex_experience_delay, minimum=0.0
    ))
    state.apdex_experience_concurrency = int(_number(
        "Concorrência Experience (1-2)", state.apdex_experience_concurrency,
        minimum=1, integer=True,
    ))

    state.apdex_dynatrace_import = _yes_no(
        "Importar calibração Dynatrace", state.apdex_dynatrace_import
    )
    if state.apdex_dynatrace_import:
        current_json = state.apdex_dynatrace_config_json
        print(paint("  Prefira JSON exportado para calibração reproduzível. Deixe vazio para importação live.", DIM))
        raw_json = input(f"JSON Dynatrace [{current_json or 'vazio=live'}]: ").strip()
        if raw_json:
            if not Path(raw_json).expanduser().is_file():
                raise ValueError("JSON Dynatrace configurado não existe")
            state.apdex_dynatrace_config_json = raw_json
        if state.apdex_dynatrace_config_json:
            state.dynatrace_base_url = ""
            state.dynatrace_application_id = ""
        else:
            state.dynatrace_base_url = input(
                f"Dynatrace base URL [{state.dynatrace_base_url or 'obrigatória'}]: "
            ).strip() or state.dynatrace_base_url
            state.dynatrace_application_id = input(
                f"Dynatrace application ID [{state.dynatrace_application_id or 'obrigatório'}]: "
            ).strip() or state.dynatrace_application_id
            if not state.dynatrace_base_url or not state.dynatrace_application_id:
                raise ValueError("importação Dynatrace live exige base URL e application ID")
            print(paint("  DYNATRACE_API_TOKEN é secret e deve ser configurado no menu E; nunca é salvo no INI.", DIM))
    else:
        state.apdex_dynatrace_config_json = ""
        state.dynatrace_base_url = ""
        state.dynatrace_application_id = ""
        state.apdex_experience_satisfied = _required_positive(
            "Threshold Satisfied em segundos", state.apdex_experience_satisfied
        )
        state.apdex_experience_frustrated = _required_positive(
            "Threshold Frustrated em segundos", state.apdex_experience_frustrated
        )
        if state.apdex_experience_frustrated <= state.apdex_experience_satisfied:
            raise ValueError("Threshold Frustrated deve ser maior que o threshold Satisfied")

    experience_from_state(state)


def configure_apdex(state: State) -> None:
    """Configure Navigation and User Experience Apdex with coherent defaults."""
    print("Synthetic Apdex gera tráfego HTTP real contra o alvo. Use somente com autorização e capacidade compatível.")
    print("Os dois domínios são independentes de IA e não alteram o SARI/SCORE.\n")
    try:
        _configure_navigation(state)
        if state.synthetic_apdex:
            _configure_experience(state)
        state.error = ""
        attempts, load = synthetic_load_summary(state)
        if attempts:
            print(paint("\nCarga projetada Synthetic Apdex: " + load, YELLOW, bold=True))
    except (ValueError, OverflowError) as exc:
        state.error = str(exc)
