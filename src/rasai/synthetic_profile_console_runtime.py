"""Interactive-console presentation for canonical synthetic runtime profile settings."""
from __future__ import annotations

from rasai.synthetic_runtime_profiles import (
    PROFILE_ENV,
    PROFILE_ENV_NAMES,
    default_preset,
    describe_preset,
    preset_ids,
    validate_preset,
)

_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import console_environment as ce, interactive_console as ic

    replacements = {}
    for device in ("MOBILE", "DESKTOP", "TABLET"):
        for kind in ("client", "hardware", "network"):
            name = PROFILE_ENV[(device, kind)]
            allowed = preset_ids(kind, device)
            labels = "; ".join(f"{item} = {describe_preset(kind, item)}" for item in allowed)
            purpose = {
                "client": f"Perfil de cliente {device}: viewport/DPR/touch e identidade Chromium coerente.",
                "hardware": f"Envelope de CPU {device} aplicado por slowdown relativo CDP.",
                "network": f"Envelope de rede {device}: RTT, download e upload controlados por CDP.",
            }[kind]
            replacements[name] = ce.EnvironmentSpec(
                name=name,
                category="Synthetic Apdex",
                purpose=purpose,
                value_type="enum",
                accepted=allowed,
                default=default_preset(kind, device),
                required_when="Nunca; o default controlado é aplicado automaticamente.",
                impact="Altera somente a condição sintética de execução; não altera a fórmula Apdex.",
                source="docs/SYNTHETIC_RUNTIME_PROFILES.md",
                notes=labels,
            )

    # Names are canonical in console_m23/console_environment from import time. Replace
    # only their generic metadata with rich enum metadata used by the interactive list.
    ce.ENV_NAMES = tuple(dict.fromkeys((*ce.ENV_NAMES, *PROFILE_ENV_NAMES)))
    by_name = {spec.name: spec for spec in ce.SPECS}
    by_name.update(replacements)
    ce.SPECS = tuple(by_name[name] for name in ce.ENV_NAMES if name in by_name)
    ce.SPEC_BY_NAME = {spec.name: spec for spec in ce.SPECS}

    # interactive_console also imports the name tuple by value; keep help/startup in
    # lockstep with the canonical environment catalog.
    ic.ENV_NAMES = tuple(dict.fromkeys((*ic.ENV_NAMES, *PROFILE_ENV_NAMES)))

    original_validate = ce._validate
    if not getattr(original_validate, "_rasai_synthetic_profiles", False):
        reverse = {name: (device, kind) for (device, kind), name in PROFILE_ENV.items()}

        def validate(name: str, raw: str) -> str:
            if name in PROFILE_ENV_NAMES:
                device, kind = reverse[name]
                return validate_preset(kind, device, raw)
            return original_validate(name, raw)

        validate._rasai_synthetic_profiles = True
        ce._validate = validate

    _INSTALLED = True
