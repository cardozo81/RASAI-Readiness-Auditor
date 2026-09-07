"""Synthetic Apdex integration helpers for the optional interactive console.

Internal event/table identifiers retain their historical M23/M25 names for
schema compatibility. User-facing text keeps Standard M23 and calibrated M25
explicitly separated without changing the pre-M25 public M23 labels/env catalog.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sqlite3
from typing import Mapping

from rasai.console_config import State as BaseState, validate_env_value as validate_base_env_value
from rasai.m23_apdex import SyntheticApdexConfig
from rasai.m23_cli import (
    APDEX_CONCURRENCY_ENV,
    APDEX_DELAY_ENV,
    APDEX_ENABLED_ENV,
    APDEX_MAX_ATTEMPTS_ENV,
    APDEX_MAX_PAGES_ENV,
    APDEX_SAMPLES_ENV,
    APDEX_THRESHOLD_ENV,
    APDEX_TIMEOUT_ENV,
    DEFAULT_APDEX_CONCURRENCY,
    DEFAULT_APDEX_DELAY_SECONDS,
    DEFAULT_APDEX_MAX_PAGES,
    DEFAULT_APDEX_SAMPLES_PER_CONTEXT,
    DEFAULT_APDEX_TIMEOUT_SECONDS,
    configured_apdex,
)
from rasai.m25_apdex_experience import ExperienceApdexConfig
from rasai.m25_cli import (
    M25_ENV_NAMES,
    configured_experience,
    validate_m25_env_value,
)
from rasai.m25_dynatrace import DYNATRACE_API_TOKEN_ENV

# Public console environment catalog remains backward-compatible. M25 has its
# own CLI/environment contract and is persisted as non-secret INI settings.
M23_ENV_NAMES = (
    APDEX_ENABLED_ENV,
    APDEX_THRESHOLD_ENV,
    APDEX_SAMPLES_ENV,
    APDEX_MAX_ATTEMPTS_ENV,
    APDEX_MAX_PAGES_ENV,
    APDEX_TIMEOUT_ENV,
    APDEX_DELAY_ENV,
    APDEX_CONCURRENCY_ENV,
)
_ALL_APDEX_ENV_NAMES = tuple(dict.fromkeys((*M23_ENV_NAMES, *M25_ENV_NAMES, DYNATRACE_API_TOKEN_ENV)))


@dataclass(slots=True)
class State(BaseState):
    synthetic_apdex: bool = False
    apdex_threshold: float | None = None
    apdex_samples: int = DEFAULT_APDEX_SAMPLES_PER_CONTEXT
    apdex_max_attempts: int = 125
    apdex_max_pages: int = DEFAULT_APDEX_MAX_PAGES
    apdex_timeout: float = DEFAULT_APDEX_TIMEOUT_SECONDS
    apdex_delay: float = DEFAULT_APDEX_DELAY_SECONDS
    apdex_concurrency: int = DEFAULT_APDEX_CONCURRENCY

    apdex_experience: bool = False
    apdex_experience_samples: int = 100
    apdex_experience_max_attempts: int = 125
    apdex_experience_max_pages: int = 1
    apdex_experience_device_mix: str = ""
    apdex_experience_session_mode: str = "cold"
    apdex_experience_kpm: str = "USER_ACTION_DURATION"
    apdex_experience_satisfied: float | None = None
    apdex_experience_frustrated: float | None = None
    apdex_experience_errors: bool = True
    apdex_experience_error_scope: str = "first-party"
    apdex_experience_settle: float = 5.0
    apdex_experience_delay: float = 1.0
    apdex_experience_concurrency: int = 1
    apdex_dynatrace_import: bool = False
    dynatrace_base_url: str = ""
    dynatrace_application_id: str = ""
    apdex_dynatrace_config_json: str = ""


@dataclass(frozen=True, slots=True)
class SyntheticUsage:
    enabled: bool
    status: str
    attempted_samples: int
    valid_samples: int
    invalid_samples: int
    contexts: int
    threshold_seconds: float | None


def _blank_args() -> SimpleNamespace:
    return SimpleNamespace(
        synthetic_apdex=None,
        apdex_threshold_seconds=None,
        apdex_samples_per_context=None,
        apdex_max_attempts_per_context=None,
        apdex_max_pages=None,
        apdex_timeout_seconds=None,
        apdex_delay_seconds=None,
        apdex_concurrency=None,
    )


def _apply_experience_state(state: State, cfg: ExperienceApdexConfig) -> None:
    state.apdex_experience = cfg.enabled
    state.apdex_experience_samples = cfg.target_samples_per_page
    state.apdex_experience_max_attempts = cfg.max_attempts_per_page
    state.apdex_experience_max_pages = cfg.max_pages
    state.apdex_experience_device_mix = _mix_text(cfg)
    state.apdex_experience_session_mode = cfg.session_mode
    state.apdex_experience_kpm = cfg.kpm
    state.apdex_experience_satisfied = cfg.satisfied_threshold_seconds
    state.apdex_experience_frustrated = cfg.frustrated_threshold_seconds
    state.apdex_experience_errors = cfg.errors_affect_apdex
    state.apdex_experience_error_scope = cfg.error_scope
    state.apdex_experience_settle = cfg.settle_seconds
    state.apdex_experience_delay = cfg.delay_seconds
    state.apdex_experience_concurrency = cfg.concurrency
    state.apdex_dynatrace_import = cfg.dynatrace_import
    state.dynatrace_base_url = cfg.dynatrace_base_url or ""
    state.dynatrace_application_id = cfg.dynatrace_application_id or ""
    state.apdex_dynatrace_config_json = cfg.dynatrace_config_json or ""


def apply_m23_environment_defaults(
    state: State,
    env: Mapping[str, str] | None = None,
    names: set[str] | None = None,
) -> tuple[str, ...]:
    """Resolve M23 and, when present, M25 environment defaults."""
    if names is not None and not (set(_ALL_APDEX_ENV_NAMES) & names):
        return ()
    environment = env if env is not None else os.environ
    try:
        cfg = configured_apdex(_blank_args(), environment)
        experience = configured_experience(
            _blank_args(),
            environment,
            standard_max_pages=cfg.max_pages,
            standard_delay_seconds=cfg.delay_seconds,
            standard_concurrency=cfg.concurrency,
        ) if cfg.enabled else ExperienceApdexConfig(enabled=False)
    except ValueError as exc:
        return (str(exc),)
    state.synthetic_apdex = cfg.enabled
    state.apdex_threshold = cfg.threshold_seconds
    state.apdex_samples = cfg.target_valid_samples
    state.apdex_max_attempts = cfg.max_attempts_per_context
    state.apdex_max_pages = cfg.max_pages
    state.apdex_timeout = cfg.timeout_seconds
    state.apdex_delay = cfg.delay_seconds
    state.apdex_concurrency = cfg.concurrency
    _apply_experience_state(state, experience)
    return ()


def validate_env_value(name: str, value: str) -> str:
    """Validate an environment edit without weakening the base console contract."""
    if name not in _ALL_APDEX_ENV_NAMES:
        return validate_base_env_value(name, value)
    raw = value.strip()
    if not raw:
        raise ValueError("valor vazio; remova a variável em vez de gravar vazio")
    if name == DYNATRACE_API_TOKEN_ENV:
        return raw
    if name in M25_ENV_NAMES:
        return validate_m25_env_value(name, raw)
    if name == APDEX_ENABLED_ENV:
        if raw.casefold() not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
            raise ValueError("booleano inválido")
        return raw
    if name in {APDEX_SAMPLES_ENV, APDEX_MAX_ATTEMPTS_ENV}:
        if int(raw) < 1:
            raise ValueError("valor deve ser inteiro >= 1")
        return raw
    if name == APDEX_MAX_PAGES_ENV:
        if int(raw) < 0:
            raise ValueError("valor deve ser inteiro >= 0")
        return raw
    if name == APDEX_CONCURRENCY_ENV:
        value_int = int(raw)
        if value_int < 1 or value_int > 2:
            raise ValueError("concorrência deve estar entre 1 e 2")
        return raw
    if name in {APDEX_THRESHOLD_ENV, APDEX_TIMEOUT_ENV}:
        if float(raw) <= 0:
            raise ValueError("valor deve ser número > 0")
        return raw
    if name == APDEX_DELAY_ENV:
        if float(raw) < 0:
            raise ValueError("valor deve ser número >= 0")
        return raw
    return raw


def config_from_state(state: State) -> SyntheticApdexConfig:
    return SyntheticApdexConfig(
        enabled=state.synthetic_apdex,
        threshold_seconds=state.apdex_threshold,
        target_valid_samples=state.apdex_samples,
        max_attempts_per_context=state.apdex_max_attempts,
        max_pages=state.apdex_max_pages,
        timeout_seconds=state.apdex_timeout,
        delay_seconds=state.apdex_delay,
        concurrency=state.apdex_concurrency,
    ).validate()


def experience_from_state(state: State) -> ExperienceApdexConfig:
    if not state.apdex_experience:
        return ExperienceApdexConfig(enabled=False)
    if not state.synthetic_apdex:
        raise ValueError("M25 Synthetic User Experience Apdex exige M23 Synthetic Apdex habilitado")
    from rasai.m25_cli import parse_device_mix

    return ExperienceApdexConfig(
        enabled=True,
        target_samples_per_page=state.apdex_experience_samples,
        max_attempts_per_page=state.apdex_experience_max_attempts,
        max_pages=state.apdex_experience_max_pages,
        device_mix=parse_device_mix(state.apdex_experience_device_mix),
        session_mode=state.apdex_experience_session_mode,
        kpm=state.apdex_experience_kpm,
        satisfied_threshold_seconds=state.apdex_experience_satisfied,
        frustrated_threshold_seconds=state.apdex_experience_frustrated,
        errors_affect_apdex=state.apdex_experience_errors,
        error_scope=state.apdex_experience_error_scope,
        settle_seconds=state.apdex_experience_settle,
        delay_seconds=state.apdex_experience_delay,
        concurrency=state.apdex_experience_concurrency,
        dynatrace_import=state.apdex_dynatrace_import,
        dynatrace_base_url=state.dynatrace_base_url or None,
        dynatrace_application_id=state.dynatrace_application_id or None,
        dynatrace_config_json=state.apdex_dynatrace_config_json or None,
    ).validate()


def validate_m23_state(state: State) -> None:
    config_from_state(state)
    experience_from_state(state)


def append_m23_command(command: list[str], state: State) -> list[str]:
    result = list(command)
    if not state.synthetic_apdex:
        result.extend(["--no-synthetic-apdex", "--no-apdex-experience"])
        return result
    cfg = config_from_state(state)
    result.extend([
        "--synthetic-apdex",
        "--apdex-threshold-seconds", str(cfg.threshold_seconds),
        "--apdex-samples-per-context", str(cfg.target_valid_samples),
        "--apdex-max-attempts-per-context", str(cfg.max_attempts_per_context),
        "--apdex-max-pages", str(cfg.max_pages),
        "--apdex-timeout-seconds", str(cfg.timeout_seconds),
        "--apdex-delay-seconds", str(cfg.delay_seconds),
        "--apdex-concurrency", str(cfg.concurrency),
    ])
    ux = experience_from_state(state)
    if not ux.enabled:
        result.append("--no-apdex-experience")
        return result
    result.extend([
        "--apdex-experience",
        "--apdex-experience-samples", str(ux.target_samples_per_page),
        "--apdex-experience-max-attempts", str(ux.max_attempts_per_page),
        "--apdex-experience-max-pages", str(ux.max_pages),
        "--apdex-experience-device-mix", _mix_text(ux),
        "--apdex-experience-session-mode", ux.session_mode,
        "--apdex-experience-kpm", ux.kpm,
        "--apdex-experience-error-scope", ux.error_scope,
        "--apdex-experience-settle-seconds", str(ux.settle_seconds),
        "--apdex-experience-delay-seconds", str(ux.delay_seconds),
        "--apdex-experience-concurrency", str(ux.concurrency),
        "--apdex-experience-errors" if ux.errors_affect_apdex else "--no-apdex-experience-errors",
    ])
    if ux.satisfied_threshold_seconds is not None:
        result.extend(["--apdex-experience-satisfied-seconds", str(ux.satisfied_threshold_seconds)])
    if ux.frustrated_threshold_seconds is not None:
        result.extend(["--apdex-experience-frustrated-seconds", str(ux.frustrated_threshold_seconds)])
    if ux.dynatrace_import:
        result.append("--apdex-dynatrace-import")
    if ux.dynatrace_base_url:
        result.extend(["--dynatrace-base-url", ux.dynatrace_base_url])
    if ux.dynatrace_application_id:
        result.extend(["--dynatrace-application-id", ux.dynatrace_application_id])
    if ux.dynatrace_config_json:
        result.extend(["--apdex-dynatrace-config-json", ux.dynatrace_config_json])
    return result


def _mix_text(cfg: ExperienceApdexConfig) -> str:
    return ",".join(f"{name.lower()}={value:g}" for name, value in cfg.device_mix)


def synthetic_load_summary(state: State) -> tuple[int, str]:
    """Return a conservative navigation-attempt ceiling, not an HTTP request count."""
    if not state.synthetic_apdex:
        return 0, "Synthetic Apdex desabilitado"
    pages = state.max_pages if state.apdex_max_pages == 0 else min(state.max_pages, state.apdex_max_pages)
    devices = 2 if state.device == "both" else 1
    contexts = max(pages, 0) * devices
    m23_attempts = contexts * max(state.apdex_max_attempts, 0)
    m25_attempts = 0
    if state.apdex_experience:
        ux_pages = state.max_pages if state.apdex_experience_max_pages == 0 else min(state.max_pages, state.apdex_experience_max_pages)
        m25_attempts = max(ux_pages, 0) * max(state.apdex_experience_max_attempts, 0)
    total = m23_attempts + m25_attempts
    extra = f" + M25 até {m25_attempts} user action(s) sintética(s)" if m25_attempts else ""
    return total, (
        f"até {m23_attempts} navegação(ões) M23 "
        f"({pages} página(s) × {devices} device(s) × {state.apdex_max_attempts} tentativas/contexto){extra}. "
        "Cada navegação/user action pode gerar múltiplos requests HTTP de subrecursos; isso é carga no site, não custo de API estimado."
    )


def actual_m23_usage(workspace: Path | None) -> SyntheticUsage | None:
    if workspace is None:
        return None
    database = workspace / "audit.db"
    if not database.is_file():
        return None
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=0.5)
        connection.row_factory = sqlite3.Row
        try:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='synthetic_apdex_runs'").fetchone()
            if not exists:
                return None
            row = connection.execute(
                "SELECT enabled,status,attempted_samples,valid_samples,invalid_samples,contexts_considered,threshold_seconds "
                "FROM synthetic_apdex_runs ORDER BY rowid DESC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            return SyntheticUsage(
                enabled=bool(row["enabled"]),
                status=str(row["status"]),
                attempted_samples=int(row["attempted_samples"] or 0),
                valid_samples=int(row["valid_samples"] or 0),
                invalid_samples=int(row["invalid_samples"] or 0),
                contexts=int(row["contexts_considered"] or 0),
                threshold_seconds=float(row["threshold_seconds"]) if row["threshold_seconds"] is not None else None,
            )
        finally:
            connection.close()
    except sqlite3.Error:
        return None


def _latest_synthetic_event(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            start = max(size - 65536, 0)
            stream.seek(start)
            payload = stream.read()
    except OSError:
        return None
    lines = payload.decode("utf-8", errors="replace").splitlines()
    if start and lines:
        lines = lines[1:]
    for line in reversed(lines[-160:]):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and str(event.get("event") or "").startswith(("M23_", "M25_")):
            return event
    return None


def observe_m23_workspace(workspace: Path, state: State) -> None:
    """Project the latest M23/M25 synthetic event into the single-screen runtime header."""
    event = _latest_synthetic_event(workspace / "logs" / "audit.log")
    if event is None:
        return
    from rasai.console_runtime import set_runtime_progress

    name = str(event.get("event") or "")
    if name == "M25_UX_STARTED":
        state.status = "SYNTHETIC_UX_APDEX"
        state.operation = "BROWSER:SYNTHETIC_UX_APDEX"
        set_runtime_progress(state, "Apdex calibrado M25", 0.0, detail="preparando user actions sintéticas", exact=False)
    elif name == "M25_UX_SAMPLE":
        state.status = "SYNTHETIC_UX_APDEX"
        state.operation = "BROWSER:SYNTHETIC_UX_APDEX"
        state.current_url = str(event.get("url") or state.current_url)
        state.current_device = str(event.get("device") or state.current_device).upper()
        run_index = int(event.get("run_index") or 0)
        target = int(event.get("target_valid_samples") or 0)
        max_attempts = int(event.get("max_attempts") or 0)
        detail = (
            f"device={state.current_device}; tentativa {run_index}/{max_attempts}; alvo válido={target}; "
            f"último={event.get('classification') or event.get('status') or '-'}"
        )
        percent = min((run_index / max(max_attempts, 1)) * 100.0, 99.0)
        set_runtime_progress(state, "Apdex calibrado M25", percent, detail=detail, exact=False)
    elif name == "M25_UX_COMPLETED":
        state.status = "SYNTHETIC_APDEX"
        state.operation = "BROWSER:SYNTHETIC_APDEX"
        set_runtime_progress(
            state,
            "Apdex calibrado M25 concluído",
            100.0,
            detail=f"válidas={int(event.get('valid_samples') or 0)}; inválidas={int(event.get('invalid_samples') or 0)}; iniciando M23 Standard",
            exact=True,
        )
    elif name in {"M25_UX_RUNTIME_FAILURE", "M25_UX_REPORT_FAILURE", "M25_UX_REPORT_FINALIZATION_FAILURE"}:
        state.status = "SYNTHETIC_LIMITATION"
        state.operation = "LOCAL:M25_FAIL_OPEN"
        set_runtime_progress(state, "Limitação operacional M25", 100.0, detail=name, exact=True)
    elif name == "M23_STARTED" and event.get("enabled"):
        state.status = "SYNTHETIC_APDEX"
        state.operation = "BROWSER:SYNTHETIC_APDEX"
        set_runtime_progress(state, "Synthetic Apdex", 0.0, detail="preparando navegações sintéticas", exact=True)
    elif name == "M23_APDEX_SAMPLE":
        state.status = "SYNTHETIC_APDEX"
        state.operation = "BROWSER:SYNTHETIC_APDEX"
        state.current_url = str(event.get("url") or state.current_url)
        state.current_device = str(event.get("device") or state.current_device).upper()
        context_index = max(int(event.get("context_index") or 1), 1)
        context_total = max(int(event.get("context_total") or 1), 1)
        context_percent = min(max(float(event.get("progress_percent") or 0.0), 0.0), 100.0)
        overall = min(((context_index - 1) + context_percent / 100.0) / context_total * 100.0, 100.0)
        valid = int(event.get("valid_samples") or 0)
        target = int(event.get("target_valid_samples") or 0)
        attempts = int(event.get("attempt_count") or 0)
        max_attempts = int(event.get("max_attempts") or 0)
        detail = (
            f"contexto {context_index}/{context_total}; válidas {valid}/{target}; "
            f"tentativas {attempts}/{max_attempts}; último={event.get('classification') or event.get('status') or '-'}"
        )
        set_runtime_progress(state, "Synthetic Apdex", overall, detail=detail, exact=True)
    elif name == "M23_COMPLETED":
        if str(event.get("status") or "") == "SKIPPED_SOURCE_BLOCKER":
            state.status = "SOURCE_BLOCKED"
            state.operation = "LOCAL:APDEX_SKIPPED"
            set_runtime_progress(
                state,
                "Synthetic Apdex não executado",
                100.0,
                detail="bloqueio técnico da origem detectado antes das navegações repetitivas; 0 amostras iniciadas",
                exact=True,
            )
        else:
            state.status = "FINALIZING"
            state.operation = "LOCAL:APDEX_REPORT"
            set_runtime_progress(
                state,
                "Finalização do Synthetic Apdex",
                100.0,
                detail=(
                    f"Synthetic Apdex concluído: {int(event.get('valid_samples') or 0)} válidas; "
                    f"{int(event.get('invalid_samples') or 0)} inválidas"
                ),
                exact=True,
            )
    elif name in {"M23_RUNTIME_FAILURE", "M23_REPORT_FAILURE"}:
        state.status = "SYNTHETIC_LIMITATION"
        state.operation = "LOCAL:APDEX_FAIL_OPEN"
        set_runtime_progress(state, "Limitação operacional Synthetic Apdex", 100.0, detail=name, exact=True)


def run_audit_from_console(state: State) -> int:
    """Run the base console runtime with M23/M25 command/observation extension."""
    from rasai import console_runtime
    original_build = console_runtime.build_command
    original_observe = console_runtime.observe_workspace

    def build(current: State) -> list[str]:
        return append_m23_command(original_build(current), current)

    def observe(workspace: Path, current: State) -> None:
        original_observe(workspace, current)
        observe_m23_workspace(workspace, current)

    try:
        console_runtime.build_command = build
        console_runtime.observe_workspace = observe
        return console_runtime.run_audit_from_console(state)
    finally:
        console_runtime.build_command = original_build
        console_runtime.observe_workspace = original_observe


def render_m23_help(state: State) -> None:
    attempts, load = synthetic_load_summary(state)
    print("\n11. Synthetic Apdex")
    print("  M23 Standard     : NAVIGATION_LOAD; T explícito; Satisfied<=T, Tolerating<=4T, Frustrated>4T.")
    print("  M25 calibrado    : opcional; user action sintética enriquecida, thresholds independentes, mix Mobile/Desktop/Tablet e política de erros.")
    print("  Custo monetário : sem API paga própria e sem LLM; importação Dynatrace consulta apenas configuração.")
    print("  Carga            : " + load)
    print("  Governança       : ambos default OFF; M25 exige M23; concorrência máxima 2; grupos grandes exigem autorização do alvo.")
    if state.apdex_experience:
        print(f"  M25 efetivo      : samples={state.apdex_experience_samples}; mix={state.apdex_experience_device_mix}; sessão={state.apdex_experience_session_mode}; KPM={state.apdex_experience_kpm}.")
        if state.apdex_dynatrace_import:
            print("  Dynatrace        : token somente em DYNATRACE_API_TOKEN; nunca é serializado no INI/comando/report/SQLite.")
    if state.synthetic_apdex and attempts:
        print("  Atenção          : valide autorização/capacidade do alvo antes de executar grupo grande em produção.")
