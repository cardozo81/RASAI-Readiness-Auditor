"""Keep user configuration, session state and execution overlays strictly separated.

The interactive console has three different configuration scopes:

* persisted/user configuration (INI, Windows/User, Windows/Machine and secrets);
* the live console session, which reflects explicit operator changes;
* one execution overlay produced by an execution profile or a restored AUD context.

Only the third scope may be projected into the audit subprocess. A profile must never
rewrite canonical ``RASAI_*`` values in the parent console process merely to execute one
AUD. This module provides a private subprocess environment and neutralizes legacy GSC
profile wrappers that temporarily/persistently mutated ``RASAI_GSC_ENABLED``.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import os
import subprocess as _subprocess
from typing import Any, Iterator, Mapping

EXECUTION_GSC_POLICY_ENV = "RASAI_EXECUTION_GSC_POLICY"
_SERP_PROVIDER_ENV = "RASAI_SERP_PROVIDER"
_SERP_MODE_ENV = "RASAI_SERP_MODE"

_ACTIVE_EXECUTION_STATE: ContextVar[Any | None] = ContextVar(
    "rasai_active_execution_state",
    default=None,
)
_AUDIT_REUSE_RENDER_STATE: ContextVar[Any | None] = ContextVar(
    "rasai_audit_reuse_render_state",
    default=None,
)
_STATE_ENVIRONMENT_OVERRIDES: dict[int, dict[str, str]] = {}
_INSTALLED = False


def _capture_environment(name: str) -> tuple[bool, str | None]:
    return name in os.environ, os.environ.get(name)


def _restore_environment(name: str, snapshot: tuple[bool, str | None]) -> None:
    existed, value = snapshot
    if existed and value is not None:
        os.environ[name] = value
    else:
        os.environ.pop(name, None)


def register_execution_environment_override(state: Any, name: str, value: str | None) -> None:
    """Store a non-persistent fallback used only by the next execution context.

    Explicit canonical configuration always wins over these restored-context values.
    This is used for data recovered from an existing AUD (for example SERP provider/mode)
    so loading an AUD cannot silently promote historical execution data into session or
    machine configuration.
    """
    key = str(name or "").strip()
    normalized = str(value or "").strip()
    if not key:
        return
    bucket = _STATE_ENVIRONMENT_OVERRIDES.setdefault(id(state), {})
    if normalized:
        bucket[key] = normalized
    else:
        bucket.pop(key, None)
    if not bucket:
        _STATE_ENVIRONMENT_OVERRIDES.pop(id(state), None)


def execution_environment_overrides(state: Any) -> dict[str, str]:
    return dict(_STATE_ENVIRONMENT_OVERRIDES.get(id(state), {}))


def clear_execution_environment_overrides(state: Any) -> None:
    _STATE_ENVIRONMENT_OVERRIDES.pop(id(state), None)


def _profile_gsc_policy(state: Any) -> tuple[str | None, Any | None]:
    try:
        from rasai import console_execution_profile_readiness as readiness
        from rasai import console_execution_profiles as profiles
    except ImportError:
        return None, None
    current = profiles.active_profile(state)
    if current is None:
        return None, None
    return readiness.gsc_profile_policy(current), readiness


def build_execution_environment(
    state: Any,
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the child-process environment without mutating the console environment."""
    environment = {
        str(key): str(value)
        for key, value in (os.environ if base_environment is None else base_environment).items()
    }

    # Restored-AUD values are fallbacks. A direct user configuration made after loading
    # the AUD must remain authoritative.
    for name, value in execution_environment_overrides(state).items():
        if not str(environment.get(name) or "").strip():
            environment[name] = value

    # Internal execution markers are owned by this projection, never by persisted/user
    # configuration. Remove any stale inherited marker before resolving the active profile.
    environment.pop(EXECUTION_GSC_POLICY_ENV, None)
    policy, readiness = _profile_gsc_policy(state)
    if policy is None or readiness is None or policy == readiness.GSC_PROFILE_INHERIT:
        return environment

    from rasai.gsc_scope import GSC_ENABLED_ENV

    environment[EXECUTION_GSC_POLICY_ENV] = str(policy)
    if policy == readiness.GSC_PROFILE_DISABLED:
        environment[GSC_ENABLED_ENV] = "false"
    elif policy == readiness.GSC_PROFILE_REQUIRED:
        environment[GSC_ENABLED_ENV] = "true"
    elif policy == readiness.GSC_PROFILE_IF_COMPATIBLE:
        # AUTO means the global hard-on/hard-off must not force the execution. Credentials
        # and property compatibility remain available in the copied environment.
        environment.pop(GSC_ENABLED_ENV, None)
    return environment


def _discard_legacy_gsc_baseline(state: Any) -> None:
    """Discard stale baselines retained by the superseded persistent GSC overlay."""
    try:
        from rasai import execution_completion_reliability as legacy

        baselines = getattr(legacy, "_GSC_BASELINE_BY_STATE", None)
        if isinstance(baselines, dict):
            baselines.pop(id(state), None)
    except (ImportError, AttributeError):
        return


def _wrap_profile_context() -> None:
    try:
        from rasai import console_execution_profiles as profiles
        from rasai.gsc_scope import GSC_ENABLED_ENV
    except ImportError:
        return

    effective = profiles.effective_profile
    clear = profiles.clear_profile
    if bool(getattr(effective, "_rasai_execution_context_isolated", False)):
        return

    @contextmanager
    def isolated_effective_profile(
        state: Any,
        session: Any | None = None,
    ) -> Iterator[None]:
        current = session or profiles.active_profile(state)
        gsc_snapshot = _capture_environment(GSC_ENABLED_ENV)
        marker_snapshot = _capture_environment(EXECUTION_GSC_POLICY_ENV)
        token = _ACTIVE_EXECUTION_STATE.set(state if current is not None else None)
        try:
            with effective(state, current):
                # Older wrappers may project GSC into os.environ while entering the
                # context. Restore the canonical session values before any caller sees
                # the context; only the private subprocess copy receives the overlay.
                _restore_environment(GSC_ENABLED_ENV, gsc_snapshot)
                _restore_environment(EXECUTION_GSC_POLICY_ENV, marker_snapshot)
                _discard_legacy_gsc_baseline(state)
                yield
        finally:
            # Inner wrappers may mutate the variables again while unwinding. The session
            # must still equal the operator-owned configuration after execution.
            _restore_environment(GSC_ENABLED_ENV, gsc_snapshot)
            _restore_environment(EXECUTION_GSC_POLICY_ENV, marker_snapshot)
            _discard_legacy_gsc_baseline(state)
            _ACTIVE_EXECUTION_STATE.reset(token)

    def isolated_clear_profile(state: Any) -> None:
        gsc_snapshot = _capture_environment(GSC_ENABLED_ENV)
        marker_snapshot = _capture_environment(EXECUTION_GSC_POLICY_ENV)
        try:
            clear(state)
        finally:
            # Clearing a profile is not permission to roll back a variable that the user
            # may have changed explicitly while the profile was active.
            _restore_environment(GSC_ENABLED_ENV, gsc_snapshot)
            _restore_environment(EXECUTION_GSC_POLICY_ENV, marker_snapshot)
            _discard_legacy_gsc_baseline(state)

    isolated_effective_profile._rasai_execution_context_isolated = True  # type: ignore[attr-defined]
    isolated_effective_profile._rasai_original = effective  # type: ignore[attr-defined]
    isolated_clear_profile._rasai_execution_context_isolated = True  # type: ignore[attr-defined]
    isolated_clear_profile._rasai_original = clear  # type: ignore[attr-defined]
    profiles.effective_profile = isolated_effective_profile
    profiles.clear_profile = isolated_clear_profile


def _install_profile_context_isolation() -> None:
    """Ensure isolation is the outermost profile layer, regardless of install order."""
    try:
        from rasai import console_execution_profile_readiness as readiness
    except ImportError:
        return

    original_installer = readiness._install_profile_gsc_overlay
    if not bool(getattr(original_installer, "_rasai_execution_context_isolation", False)):
        def install_profile_gsc_overlay_isolated() -> None:
            original_installer()
            _wrap_profile_context()

        install_profile_gsc_overlay_isolated._rasai_execution_context_isolation = True  # type: ignore[attr-defined]
        install_profile_gsc_overlay_isolated._rasai_original = original_installer  # type: ignore[attr-defined]
        readiness._install_profile_gsc_overlay = install_profile_gsc_overlay_isolated

    if bool(getattr(readiness, "_INSTALLED", False)):
        _wrap_profile_context()


class _SubprocessProxy:
    """Module-local subprocess proxy that injects only a private execution environment."""

    _rasai_execution_context_proxy = True

    def __init__(self, base: Any) -> None:
        self._base = base

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)

    def Popen(self, *args: Any, **kwargs: Any):  # noqa: N802 - mirrors subprocess API
        state = _ACTIVE_EXECUTION_STATE.get()
        if state is not None and kwargs.get("env") is None:
            kwargs["env"] = build_execution_environment(state)
        return self._base.Popen(*args, **kwargs)


def _install_private_subprocess_environment() -> None:
    # Both runtime paths can launch the same local audit process: the standard console
    # runner and the cancellation-aware replacement. Patch only each module's local
    # reference; the process-wide subprocess module remains untouched.
    for module_name in ("console_runtime", "console_cancellation_runtime"):
        try:
            module = __import__(f"rasai.{module_name}", fromlist=[module_name])
        except ImportError:
            continue
        current = getattr(module, "subprocess", None)
        if current is None or bool(getattr(current, "_rasai_execution_context_proxy", False)):
            continue
        module.subprocess = _SubprocessProxy(current)


def _isolated_serp_runtime_summary(original: Any) -> Any:
    state = _AUDIT_REUSE_RENDER_STATE.get()
    if state is None:
        return original()
    overrides = execution_environment_overrides(state)
    provider = str(os.environ.get(_SERP_PROVIDER_ENV) or overrides.get(_SERP_PROVIDER_ENV) or "").strip().casefold()
    mode = str(os.environ.get(_SERP_MODE_ENV) or overrides.get(_SERP_MODE_ENV) or "").strip().casefold()
    if not provider and not mode:
        return original()
    try:
        from rasai.search_intelligence.config import provider_key_env
        from rasai.search_intelligence.provider_catalog import serp_provider_registration

        registration = serp_provider_registration(provider)
        key_name = provider_key_env(provider)
        key_state = "[SET]" if (os.environ.get(key_name) or "").strip() else "<não definida>"
        engine = registration.engine if registration is not None else "unknown"
        return f"{mode or 'configuração atual'} / {provider or 'provider atual'} / {engine}", key_name, key_state
    except (KeyError, TypeError, ValueError):
        return original()


def _install_restored_audit_environment_isolation() -> None:
    """Keep SERP provider/mode recovered from an AUD out of canonical session env."""
    try:
        from rasai import audit_configuration_reuse_runtime as reuse
    except ImportError:
        return

    original_restore = reuse._restore_search_from_persisted_observations
    if not bool(getattr(original_restore, "_rasai_execution_context_isolated", False)):
        def restore_search_isolated(state: Any, audit_id: str):
            snapshots = {
                _SERP_PROVIDER_ENV: _capture_environment(_SERP_PROVIDER_ENV),
                _SERP_MODE_ENV: _capture_environment(_SERP_MODE_ENV),
            }
            try:
                result = original_restore(state, audit_id)
                for name, snapshot in snapshots.items():
                    before = str(snapshot[1] or "").strip()
                    after = str(os.environ.get(name) or "").strip()
                    if not before and after:
                        register_execution_environment_override(state, name, after)
                return result
            finally:
                for name, snapshot in snapshots.items():
                    _restore_environment(name, snapshot)

        restore_search_isolated._rasai_execution_context_isolated = True  # type: ignore[attr-defined]
        restore_search_isolated._rasai_original = original_restore  # type: ignore[attr-defined]
        reuse._restore_search_from_persisted_observations = restore_search_isolated

    original_summary = reuse._serp_runtime_summary
    if not bool(getattr(original_summary, "_rasai_execution_context_isolated", False)):
        def serp_runtime_summary_isolated():
            return _isolated_serp_runtime_summary(original_summary)

        serp_runtime_summary_isolated._rasai_execution_context_isolated = True  # type: ignore[attr-defined]
        serp_runtime_summary_isolated._rasai_original = original_summary  # type: ignore[attr-defined]
        reuse._serp_runtime_summary = serp_runtime_summary_isolated

    original_render = reuse.render_loaded_configuration_summary
    if not bool(getattr(original_render, "_rasai_execution_context_isolated", False)):
        def render_loaded_configuration_summary_isolated(console_module: Any, state: Any, source: Any):
            token = _AUDIT_REUSE_RENDER_STATE.set(state)
            try:
                return original_render(console_module, state, source)
            finally:
                _AUDIT_REUSE_RENDER_STATE.reset(token)

        render_loaded_configuration_summary_isolated._rasai_execution_context_isolated = True  # type: ignore[attr-defined]
        render_loaded_configuration_summary_isolated._rasai_original = original_render  # type: ignore[attr-defined]
        reuse.render_loaded_configuration_summary = render_loaded_configuration_summary_isolated


def install() -> None:
    """Install context isolation without changing any persisted user configuration."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_profile_context_isolation()
    _install_private_subprocess_environment()
    _install_restored_audit_environment_isolation()
    _INSTALLED = True
