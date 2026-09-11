from __future__ import annotations

import ast
from pathlib import Path

from rasai.runtime_completion_extensions import install_runtime_completion_extensions

install_runtime_completion_extensions()

from rasai.console_environment import ENV_NAMES, SPEC_BY_NAME
from rasai.m25_cli import DEFAULT_UX_DEVICE_MIX, parse_device_mix
from rasai.provider_registry import provider_environment_names


ROOT = Path(__file__).resolve().parents[1]
_ENV_CONSTANT_SUFFIXES = ("_ENV", "_ENV_REF")
_ENV_LOOKUP_METHODS = {"get", "getenv", "pop", "setdefault"}


def _rasai_literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value.strip()
        if value.startswith("RASAI_") and not value.startswith("RASAI_TEST_"):
            return value
    return None


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
    return tuple(names)


def _runtime_rasai_environment_names() -> set[str]:
    """Discover actual environment keys, not every RASAI-prefixed runtime identifier.

    Profile IDs, operational event names and public contract labels also intentionally
    use the RASAI_* namespace. Treating every such string as an environment variable
    creates false positives and would pressure the console into exposing non-settings.
    We therefore inspect explicit *_ENV constants and environment-style lookups.
    """
    names: set[str] = set()
    for path in (ROOT / "src" / "rasai").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = _rasai_literal(node.value)
                if value and any(
                    assigned.endswith(_ENV_CONSTANT_SUFFIXES)
                    for assigned in _assigned_names(node)
                ):
                    names.add(value)
                continue

            if isinstance(node, ast.Call) and node.args:
                method = node.func.attr if isinstance(node.func, ast.Attribute) else (
                    node.func.id if isinstance(node.func, ast.Name) else ""
                )
                if method in _ENV_LOOKUP_METHODS:
                    value = _rasai_literal(node.args[0])
                    if value:
                        names.add(value)
                continue

            if isinstance(node, ast.Subscript):
                value = _rasai_literal(node.slice)
                if value:
                    owner = node.value
                    if (
                        isinstance(owner, ast.Attribute)
                        and isinstance(owner.value, ast.Name)
                        and owner.value.id == "os"
                        and owner.attr == "environ"
                    ):
                        names.add(value)
    return names


def test_every_builtin_rasai_runtime_environment_variable_is_exposed_in_console() -> None:
    discovered = _runtime_rasai_environment_names()
    exposed = set(ENV_NAMES)
    missing = sorted(discovered - exposed)
    assert not missing, "runtime environment variables missing from console catalog: " + ", ".join(missing)


def test_non_setting_rasai_identifiers_are_not_misclassified_as_environment_variables() -> None:
    discovered = _runtime_rasai_environment_names()
    for identifier in (
        "RASAI_DESKTOP_DENSE4G_V1",
        "RASAI_MOBILE_SLOW4G_V1",
        "RASAI_TABLET_CONTROLLED4G_V1",
        "RASAI_READINESS_REPORT_GENERATED",
        "RASAI_READINESS_REPORT_FAILURE",
    ):
        assert identifier not in discovered


def test_provider_environment_contract_is_in_console_catalog() -> None:
    assert set(provider_environment_names()).issubset(set(ENV_NAMES))


def test_every_exposed_environment_variable_has_metadata() -> None:
    assert set(SPEC_BY_NAME) == set(ENV_NAMES)
    assert all(SPEC_BY_NAME[name].purpose for name in ENV_NAMES)
    assert all(SPEC_BY_NAME[name].value_type for name in ENV_NAMES)


def test_exchange_log_limit_is_exposed_in_console_catalog() -> None:
    assert "RASAI_AI_EXCHANGE_LOG_MAX_BYTES" in ENV_NAMES
    assert "RASAI_AI_EXCHANGE_LOG_MAX_BYTES" in SPEC_BY_NAME


def test_experience_apdex_has_a_valid_default_device_distribution() -> None:
    mix = dict(parse_device_mix(DEFAULT_UX_DEVICE_MIX))
    assert set(mix).issubset({"MOBILE", "DESKTOP", "TABLET"})
    assert abs(sum(mix.values()) - 100.0) < 1e-9
    assert SPEC_BY_NAME["RASAI_APDEX_EXPERIENCE_DEVICE_MIX"].default == DEFAULT_UX_DEVICE_MIX


def test_shared_apdex_acquisition_mode_has_explicit_console_metadata() -> None:
    spec = SPEC_BY_NAME["RASAI_APDEX_ACQUISITION_MODE"]
    assert spec.category == "Synthetic Apdex"
    assert spec.default == "auto"
    assert spec.accepted == ("auto", "isolated")
    assert "não altera" in spec.impact
