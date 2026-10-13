"""Read-only, secret-safe provenance for the interactive configuration (#523).

This module never hydrates an execution flag, sets an environment variable,
or writes the operator's INI. Its count is informational, not an authorization.
"""
from __future__ import annotations

from configparser import ConfigParser, Error as ConfigError
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from rasai.console_config import is_secret
from rasai.console_provider_environment import refresh_specs


@dataclass(frozen=True, slots=True)
class ConfigurationProvenance:
    file_status: str
    persisted_public: int
    session_overrides: int
    invalid_entries: int
    private_values_excluded: bool = True


def inspect_configuration(
    path: Path | None,
    *,
    env: Mapping[str, str] | None = None,
) -> ConfigurationProvenance:
    """Count configuration precedence conflicts without displaying actual values.

    Environment override counts only when a known nonsecret key is present
    in the saved inventory with a different value. An override is not
    interpreted as a saved value, and a file's existence is not proof of load.
    """
    empty = ConfigurationProvenance("AUSENTE", 0, 0, 0)
    if path is None:
        return ConfigurationProvenance("NÃO RESOLVIDO", 0, 0, 0)
    path = Path(path)
    try:
        if not path.is_file():
            return empty
        if path.stat().st_size > 2_000_000:
            return ConfigurationProvenance("NÃO INSPECIONADO: limite de tamanho", 0, 0, 0)
    except OSError:
        return ConfigurationProvenance("INDISPONÍVEL", 0, 0, 0)
    specs = {
        spec.name
        for spec in refresh_specs()
        if not spec.sensitive and not is_secret(spec.name)
    }
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        with path.open("r", encoding="utf-8") as f:
            parser.read_file(f)
    except (OSError, UnicodeError, ConfigError):
        return ConfigurationProvenance("INVÁLIDO", 0, 0, 0)
    if not parser.has_section("environment"):
        return ConfigurationProvenance("LIDO: sem inventário de ambiente", 0, 0, 0)

    saved = dict(parser.items("environment", raw=True))
    valid = {name: value for name, value in saved.items() if name in specs}
    overrides = env if env is not None else os.environ
    conflicts = sum(
        1 for name, value in valid.items()
        if (overrides.get(name) or "").strip()
        and (overrides.get(name) or "").strip() != value.strip()
    )
    return ConfigurationProvenance(
        "LIDO: arquivo existente",
        len(valid),
        conflicts,
        len(saved) - len(valid),
    )


def render_provenance(summary: ConfigurationProvenance) -> str:
    """Return text without file content, keys, secrets or PII-bearing paths."""
    if summary.file_status.startswith("LIDO"):
        return (
            f"Configuração INI: {summary.file_status} | "
            f"{summary.persisted_public} variáveis públicas inventariadas | "
            f"{summary.session_overrides} divergência(s) sessão/INI (prioridade efetiva depende do campo)"
            + (f" | {summary.invalid_entries} entrada(s) ignoradas" if summary.invalid_entries else "")
        )
    return f"Configuração INI: {summary.file_status}"
