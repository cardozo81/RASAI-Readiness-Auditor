"""Provider-aware environment catalog facade for the interactive console.

The legacy environment editor owns the general UI and validation surface. This module
projects AI/SERP registry metadata before the menu is rendered, without mutating the
legacy module at runtime. It is the canonical environment surface used by the console
entrypoint while the broader environment editor remains stable.
"""
from __future__ import annotations

from dataclasses import replace
from getpass import getpass
import os

from rasai import console_environment as legacy
from rasai.provider_registry import provider_registrations
from rasai.search_intelligence.config import SERP_PROVIDER_ENV
from rasai.search_intelligence.provider_catalog import (
    SERP_PROVIDER_REGISTRY,
    serp_provider_ids,
)

EnvironmentSpec = legacy.EnvironmentSpec
CATEGORIES = legacy.CATEGORIES
DOCUMENT_NAME = legacy.DOCUMENT_NAME


def _build_specs() -> tuple[EnvironmentSpec, ...]:
    specs = list(legacy.environment_specs())
    by_name = {spec.name: index for index, spec in enumerate(specs)}

    provider_index = by_name.get(SERP_PROVIDER_ENV)
    if provider_index is not None:
        specs[provider_index] = replace(
            specs[provider_index],
            accepted=serp_provider_ids(),
            notes=(
                "O provider selecionado determina engine, variável de credencial e "
                "estratégia de paginação. Consulte `rasai providers --kind serp`."
            ),
        )

    by_key: dict[str, list[object]] = {}
    for registration in SERP_PROVIDER_REGISTRY:
        by_key.setdefault(registration.key_env, []).append(registration)
    for key_env, registrations in by_key.items():
        index = by_name.get(key_env)
        if index is None:
            continue
        provider_ids = ", ".join(item.id for item in registrations)
        display_names = " / ".join(dict.fromkeys(item.display_name for item in registrations))
        credential_url = registrations[0].credential_url
        notes = " | ".join(
            dict.fromkeys(item.free_tier_note for item in registrations if item.free_tier_note)
        )
        specs[index] = replace(
            specs[index],
            category="Search Intelligence / Observability",
            purpose=f"Credencial BYOK do provider {display_names}.",
            value_type="segredo/API key",
            required_when=(
                "Obrigatória quando RASAI_SERP_MODE=live e RASAI_SERP_PROVIDER "
                f"for um de: {provider_ids}."
            ),
            sensitive=True,
            impact=(
                "Consome quota/créditos do provider; os limites do RASAi não "
                "substituem a quota do fornecedor."
            ),
            source=f"{display_names} chave/login - {credential_url}",
            notes=notes,
        )

    ai_by_key = {registration.key_env: registration for registration in provider_registrations()}
    for index, spec in enumerate(specs):
        registration = ai_by_key.get(spec.name)
        if registration is None:
            continue
        notes = registration.auth_note or (
            f"Obtenha/gerencie a credencial em {registration.credential_url}. "
            f"Documentação: {registration.documentation_url}"
        )
        specs[index] = replace(
            spec,
            source=f"{registration.display_name} credencial/login - {registration.credential_url}",
            notes=notes,
        )
    return tuple(specs)


def environment_specs() -> tuple[EnvironmentSpec, ...]:
    return _build_specs()


def refresh_specs() -> tuple[EnvironmentSpec, ...]:
    """Refresh this facade after runtime extensions mutate the legacy catalog."""
    global ENV_NAMES, SPECS, SPEC_BY_NAME
    ENV_NAMES = legacy.ENV_NAMES
    SPECS = environment_specs()
    SPEC_BY_NAME = {spec.name: spec for spec in SPECS}
    return SPECS


ENV_NAMES = legacy.ENV_NAMES
SPECS = environment_specs()
SPEC_BY_NAME = {spec.name: spec for spec in SPECS}


def _validate(name: str, raw: str) -> str:
    if name == SERP_PROVIDER_ENV:
        value = str(raw).strip().casefold()
        if not value:
            raise ValueError("valor vazio; remova a variável em vez de gravar vazio")
        allowed = serp_provider_ids()
        if value not in set(allowed):
            raise ValueError("use " + ", ".join(allowed))
        return value
    return legacy._validate(name, raw)


def _variable_menu(state: object, spec: EnvironmentSpec) -> None:
    while True:
        legacy.render_header(state)
        legacy._render_detail(spec)
        sensitive = legacy._is_sensitive_spec(spec)
        if sensitive:
            print("\nAÇÕES\nS. Setar/alterar sessão\nR. Remover da sessão\nP. Persistência Windows/User\nD. Documentação\nV. Voltar")
        else:
            print("\nAÇÕES\nS. Setar/alterar\nR. Remover override\nD. Documentação\nV. Voltar")
        action = input("Escolha: ").strip().upper()
        if action == "V":
            return
        if action == "D":
            legacy._open_docs(state)
            continue
        if action == "P" and sensitive:
            try:
                legacy._persist_secret(state, spec)
            except (OSError, ValueError) as exc:
                setattr(state, "error", f"falha de persistência: {type(exc).__name__}: {exc}")
            continue
        if action == "R":
            os.environ.pop(spec.name, None)
            if sensitive:
                legacy._sync_secret_state(state, spec.name)
            legacy._apply_change(state, spec.name)
            continue
        if action != "S":
            continue
        try:
            if spec.accepted and spec.value_type in {"enum", "enum inteiro", "booleano"}:
                raw = legacy._prompt_choice(spec)
                if raw is None:
                    continue
            else:
                raw = getpass(f"{spec.name}: ") if sensitive else input(f"{spec.name}: ")
            os.environ[spec.name] = _validate(spec.name, raw)
            if sensitive:
                legacy._sync_secret_state(state, spec.name)
            legacy._apply_change(state, spec.name)
        except (ValueError, OverflowError) as exc:
            setattr(state, "error", str(exc))


def _category_menu(state: object, title: str, specs: tuple[EnvironmentSpec, ...]) -> None:
    while True:
        legacy.render_header(state)
        print(f"VARIÁVEIS DE AMBIENTE - {title}\n")
        for index, spec in enumerate(specs, 1):
            print(f"{index:2d}. {spec.name:<44} {legacy._status(spec)}")
        print("\nAÇÕES\nD. Abrir documentação detalhada\nV. Voltar")
        raw = input("Selecione a variável: ").strip().upper()
        if raw == "V":
            return
        if raw == "D":
            legacy._open_docs(state)
            continue
        try:
            _variable_menu(state, specs[int(raw) - 1])
        except (ValueError, IndexError):
            setattr(state, "error", "variável inválida")


def environment_menu(state: object) -> None:
    """Show the registry-aware product environment catalog grouped by functional scope."""
    refresh_specs()
    grouped = {
        category: tuple(spec for spec in SPECS if spec.category == category)
        for category in CATEGORIES
    }
    while True:
        legacy.render_header(state)
        print("CONFIGURAÇÃO AVANÇADA - VARIÁVEIS DE AMBIENTE\n")
        print("Defaults coerentes são aplicados internamente; defina variável para override/credencial.")
        print("Secrets não entram no INI. Opções de control plane/Identity são de operador, não de tenant.\n")
        choices: dict[str, str] = {}
        for index, category in enumerate(CATEGORIES, 1):
            specs = grouped[category]
            configured = sum(1 for spec in specs if (os.environ.get(spec.name) or "").strip())
            print(f" {index:2d}. {category:<34} {configured}/{len(specs)} override(s) definidos")
            choices[str(index)] = category
        print("\n A. Todas as variáveis")
        print(f" D. Abrir documentação detalhada (docs/{DOCUMENT_NAME})")
        print(" V. Voltar")
        raw = input("Escolha: ").strip().upper()
        if raw == "V":
            return
        if raw == "D":
            legacy._open_docs(state)
            continue
        if raw == "A":
            _category_menu(state, "Todas", SPECS)
            continue
        category = choices.get(raw)
        if category:
            _category_menu(state, category, grouped[category])
        else:
            setattr(state, "error", "grupo inválido")
