"""Read-only, secret-safe provenance for the interactive configuration (#523).

This module never hydrates an execution flag, sets an environment variable,
or writes the operator's INI. Its count is informational, not an authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from rasai.console_config import is_secret
from rasai.console_configuration_inventory_523 import _ini_with_status
from rasai.console_provider_environment import refresh_specs


@dataclass(frozen=True, slots=True)
class ConfigurationProvenance:
    file_status: str
    persisted_public: int
    session_overrides: int
    invalid_entries: int
    private_values_excluded: bool = True
    private_entries_in_ini: int = 0


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
        if path.is_symlink():
            return ConfigurationProvenance("NÃO INSPECIONADO: caminho simbólico", 0, 0, 0)
        if not path.is_file():
            return empty
        if path.stat().st_size > 2_000_000:
            return ConfigurationProvenance("NÃO INSPECIONADO: limite de tamanho", 0, 0, 0)
    except OSError:
        return ConfigurationProvenance("INDISPONÍVEL", 0, 0, 0)
    registered = tuple(refresh_specs())
    specs = {
        spec.name for spec in registered
        if not spec.sensitive and not is_secret(spec.name)
    }
    sensitive_specs = {
        spec.name for spec in registered
        if spec.sensitive or is_secret(spec.name)
    }
    # Reuse the bounded descriptor-based inventory reader. Unlike a direct
    # ConfigParser.items() call, _sections enumerates only assignments
    # physically present in [environment], never inherited [DEFAULT] keys.
    parser, source_status = _ini_with_status(path)
    if parser is None:
        statuses = {
            "SOURCE_SYMLINK_DISALLOWED": "NÃO INSPECIONADO: caminho simbólico",
            "SOURCE_NOT_FOUND_OR_NOT_A_FILE": "AUSENTE",
            "SOURCE_TOO_LARGE": "NÃO INSPECIONADO: limite de tamanho",
            "SOURCE_UNREADABLE": "INDISPONÍVEL",
            "SOURCE_INVALID_INI": "INVÁLIDO",
            "SOURCE_CHANGED_DURING_READ": "NÃO INSPECIONADO: arquivo alterado durante leitura",
        }
        return ConfigurationProvenance(
            statuses.get(source_status, "NÃO INSPECIONADO: origem não verificada"),
            0, 0, 0,
        )
    if not parser.has_section("environment"):
        return ConfigurationProvenance("LIDO: sem inventário de ambiente", 0, 0, 0)

    saved = dict(parser._sections["environment"])
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
        private_entries_in_ini=sum(
            key in sensitive_specs or is_secret(key)
            for key in saved
        ),
    )


def render_provenance(summary: ConfigurationProvenance) -> str:
    """Return text without file content, keys, secrets or PII-bearing paths."""
    if summary.file_status.startswith("LIDO"):
        return (
            f"Configuração INI: {summary.file_status} | "
            f"{summary.persisted_public} variáveis públicas inventariadas | "
            f"{summary.session_overrides} divergência(s) sessão/INI (prioridade efetiva depende do campo)"
            + (f" | {summary.invalid_entries} entrada(s) ignoradas" if summary.invalid_entries else "")
            + (
                f" | ATENÇÃO: {summary.private_entries_in_ini} entrada(s) "
                "potencialmente sensível(is) no INI; revisar sem divulgar valores"
                if summary.private_entries_in_ini else ""
            )
        )
    return f"Configuração INI: {summary.file_status}"
