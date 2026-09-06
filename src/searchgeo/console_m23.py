"""Synthetic Apdex integration helpers for the optional interactive console.

Internal event/table identifiers retain their historical M23 names for schema
compatibility, but user-facing text describes the capability by function.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sqlite3
from typing import Mapping

from searchgeo.console_config import State as BaseState, validate_env_value as validate_base_env_value
from searchgeo.m23_apdex import SyntheticApdexConfig
from searchgeo.m23_cli import (
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


def apply_m23_environment_defaults(
    state: State,
    env: Mapping[str, str] | None = None,
    names: set[str] | None = None,
) -> tuple[str, ...]:
    """Resolve Synthetic Apdex environment defaults with the exact CLI contract."""
    if names is not None and not (set(M23_ENV_NAMES) & names):
        return ()
    environment = env if env is not None else os.environ
    try:
        cfg = configured_apdex(_blank_args(), environment)
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
    return ()


def validate_env_value(name: str, value: str) -> str:
    """Validate an environment edit without weakening the base console contract."""
    if name not in M23_ENV_NAMES:
        return validate_base_env_value(name, value)
    raw = value.strip()
    if not raw:
        raise ValueError("valor vazio; remova a variável em vez de gravar vazio")
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


def validate_m23_state(state: State) -> None:
    config_from_state(state)


def append_m23_command(command: list[str], state: State) -> list[str]:
    result = list(command)
    if not state.synthetic_apdex:
        result.append("--no-synthetic-apdex")
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
    return result


def synthetic_load_summary(state: State) -> tuple[int, str]:
    """Return a conservative navigation-attempt ceiling, not an HTTP request count."""
    if not state.synthetic_apdex:
        return 0, "Synthetic Apdex desabilitado"
    pages = state.max_pages if state.apdex_max_pages == 0 else min(state.max_pages, state.apdex_max_pages)
    devices = 2 if state.device == "both" else 1
    contexts = max(pages, 0) * devices
    attempts = contexts * max(state.apdex_max_attempts, 0)
    return attempts, (
        f"até {attempts} navegação(ões) sintética(s) iniciadas "
        f"({pages} página(s) × {devices} device(s) × {state.apdex_max_attempts} tentativas/contexto). "
        "Cada navegação pode gerar múltiplos requests HTTP de subrecursos; isso é carga no site, não custo de API estimado."
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


def _latest_m23_event(path: Path) -> dict[str, object] | None:
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
    for line in reversed(lines[-120:]):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and str(event.get("event") or "").startswith("M23_"):
            return event
    return None


def observe_m23_workspace(workspace: Path, state: State) -> None:
    """Project the latest Synthetic Apdex event into the single-screen runtime header."""
    event = _latest_m23_event(workspace / "logs" / "audit.log")
    if event is None:
        return
    from searchgeo.console_runtime import set_runtime_progress

    name = str(event.get("event") or "")
    if name == "M23_STARTED" and event.get("enabled"):
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
    """Run the base console runtime with Synthetic Apdex command/observation extension."""
    from searchgeo import console_runtime
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
    print("  Para que serve : mede repetidamente a Task de navegação com Chromium, perfis CPU/rede controlados e cache frio.")
    print("  Fórmula         : Apdex = (Satisfied + 0,5 × Tolerating) / amostras válidas; Frustrated > 4T ou erro de aplicação/navegação válido.")
    print("  Custo monetário : sem API paga própria e sem LLM; não altera a faixa financeira do console.")
    print("  Carga            : " + load)
    print("  Governança       : default OFF; T é obrigatório; concorrência máxima 2; 100 amostras válidas é o grupo final normal.")
    if state.synthetic_apdex and attempts:
        print("  Atenção          : valide autorização/capacidade do alvo antes de executar um grupo grande em produção.")
