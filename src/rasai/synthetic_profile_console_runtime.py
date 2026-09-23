"""Interactive-console presentation for canonical synthetic runtime profile settings.

The installer is deliberately repairable: other runtime extensions may rebuild the
base environment catalog after this module has already been installed. Profile metadata
must therefore remain part of the source factory and be re-upserted on every install
call instead of relying on a one-shot import-time mutation.
"""
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


def _profile_specs(ce: object) -> dict[str, object]:
    replacements: dict[str, object] = {}
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
    return replacements


def install() -> None:
    global _INSTALLED
    from rasai import console_environment as ce, interactive_console as ic

    replacements = _profile_specs(ce)

    # Make profile metadata part of the source factory. Runtime-completion extensions
    # legitimately rebuild SPECS from environment_specs(); without this wrapper those
    # rebuilds would fall back to generic EnvironmentSpec rows for the profile vars.
    original_fixed_specs = ce._fixed_specs
    if not getattr(original_fixed_specs, "_rasai_synthetic_profiles_factory", False):
        def fixed_specs_with_profiles():
            items = list(original_fixed_specs())
            by_name = {spec.name: index for index, spec in enumerate(items)}
            for name, spec in _profile_specs(ce).items():
                index = by_name.get(name)
                if index is None:
                    by_name[name] = len(items)
                    items.append(spec)
                else:
                    items[index] = spec
            return tuple(items)

        fixed_specs_with_profiles._rasai_synthetic_profiles_factory = True
        fixed_specs_with_profiles._rasai_original = original_fixed_specs
        ce._fixed_specs = fixed_specs_with_profiles

    # Always repair the materialized catalog because another installer may have rebuilt
    # it after the first call. This is an upsert, not a destructive full rebuild, so
    # metadata installed by standards/other runtime extensions is preserved.
    ce.ENV_NAMES = tuple(dict.fromkeys((*ce.ENV_NAMES, *PROFILE_ENV_NAMES)))
    by_name = {spec.name: spec for spec in ce.SPECS}
    by_name.update(replacements)
    ce.SPECS = tuple(by_name[name] for name in ce.ENV_NAMES if name in by_name)
    ce.SPEC_BY_NAME = {spec.name: spec for spec in ce.SPECS}

    # interactive_console also imports the name tuple by value; keep help/startup in
    # lockstep with the canonical environment catalog.
    ic.ENV_NAMES = tuple(dict.fromkeys((*ic.ENV_NAMES, *PROFILE_ENV_NAMES)))

    if not _INSTALLED:
        original_validate = ce._validate
        if not getattr(original_validate, "_rasai_synthetic_profiles", False):
            reverse = {name: (device, kind) for (device, kind), name in PROFILE_ENV.items()}

            def validate(name: str, raw: str) -> str:
                if name in PROFILE_ENV_NAMES:
                    device, kind = reverse[name]
                    return validate_preset(kind, device, raw)
                return original_validate(name, raw)

            validate._rasai_synthetic_profiles = True
            validate._rasai_original = original_validate
            ce._validate = validate

    _INSTALLED = True
