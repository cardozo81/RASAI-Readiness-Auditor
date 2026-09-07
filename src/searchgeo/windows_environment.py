"""Windows user-environment persistence for console secrets.

Secrets are never persisted in RASAI configuration files. This module only
handles an explicit user request to store/remove a secret in the current
Windows user's environment.
"""
from __future__ import annotations

import ctypes
import os

_USER_ENVIRONMENT_KEY = r"Environment"
_MACHINE_ENVIRONMENT_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"


def _read_windows_environment(name: str, *, user: bool) -> str | None:
    if os.name != "nt":
        return None
    import winreg

    root = winreg.HKEY_CURRENT_USER if user else winreg.HKEY_LOCAL_MACHINE
    path = _USER_ENVIRONMENT_KEY if user else _MACHINE_ENVIRONMENT_KEY
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return str(value) if value is not None else None


def user_environment_value(name: str) -> str | None:
    return _read_windows_environment(name, user=True)


def machine_environment_value(name: str) -> str | None:
    return _read_windows_environment(name, user=False)


def effective_persisted_value(name: str) -> str | None:
    """Return the value a new normal Windows user process should inherit."""
    user_value = user_environment_value(name)
    if user_value is not None:
        return user_value
    return machine_environment_value(name)


def classify_environment_origin(
    current_value: str | None,
    user_value: str | None,
    machine_value: str | None,
) -> str:
    """Describe where the effective value in the current process comes from."""
    current = current_value if current_value not in {None, ""} else None
    user = user_value if user_value not in {None, ""} else None
    machine = machine_value if machine_value not in {None, ""} else None

    if current is None:
        if user is not None:
            return "SO:USER persistida (não ativa nesta sessão)"
        if machine is not None:
            return "SO:MACHINE persistida (não ativa nesta sessão)"
        return ""
    if user is not None and current == user:
        return "SO:USER"
    if user is None and machine is not None and current == machine:
        return "SO:MACHINE"
    if user is not None:
        return "SESSÃO | SO:USER existente"
    if machine is not None:
        return "SESSÃO | SO:MACHINE existente"
    return "SESSÃO"


def environment_origin(name: str, current_value: str | None = None) -> str:
    current = os.environ.get(name) if current_value is None else current_value
    return classify_environment_origin(
        current,
        user_environment_value(name),
        machine_environment_value(name),
    )


def current_matches_persisted(name: str) -> bool:
    current = os.environ.get(name)
    persisted = effective_persisted_value(name)
    current = current if current not in {None, ""} else None
    persisted = persisted if persisted not in {None, ""} else None
    return current == persisted


def _broadcast_environment_change() -> None:
    if os.name != "nt":
        return
    try:
        result = ctypes.c_size_t()
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF,  # HWND_BROADCAST
            0x001A,  # WM_SETTINGCHANGE
            0,
            "Environment",
            0x0002,  # SMTO_ABORTIFHUNG
            5000,
            ctypes.byref(result),
        )
    except (AttributeError, OSError):
        # Registry persistence already succeeded. The broadcast only helps
        # existing desktop processes notice the change sooner.
        return


def persist_user_environment(name: str, value: str) -> None:
    """Persist one value in the current Windows user's environment."""
    if os.name != "nt":
        raise OSError("persistência de credenciais no ambiente do SO está disponível somente no Windows")
    if not value:
        raise ValueError("não há valor da sessão para persistir")
    import winreg

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER,
        _USER_ENVIRONMENT_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    _broadcast_environment_change()


def remove_user_environment(name: str) -> bool:
    """Remove one value from the current Windows user's environment."""
    if os.name != "nt":
        raise OSError("persistência de credenciais no ambiente do SO está disponível somente no Windows")
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _USER_ENVIRONMENT_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        return False
    _broadcast_environment_change()
    return True
