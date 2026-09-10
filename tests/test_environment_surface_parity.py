from __future__ import annotations

import re
from pathlib import Path

from rasai.console_environment import ENV_NAMES, SPEC_BY_NAME
from rasai.m25_cli import DEFAULT_UX_DEVICE_MIX, parse_device_mix
from rasai.provider_registry import provider_environment_names


ROOT = Path(__file__).resolve().parents[1]
RASAI_ENV_RE = re.compile(r"\bRASAI_[A-Z0-9_]+\b")


def _runtime_rasai_environment_names() -> set[str]:
    names: set[str] = set()
    for path in (ROOT / "src" / "rasai").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        names.update(RASAI_ENV_RE.findall(text))
    # RASAI_TEST_* is reserved for CI/integration-test infrastructure, not runtime
    # product configuration. Source modules should not normally contain it, but the
    # exclusion keeps the contract explicit if a test helper moves under src later.
    return {name for name in names if not name.startswith("RASAI_TEST_")}


def test_every_builtin_rasai_runtime_environment_variable_is_exposed_in_console() -> None:
    discovered = _runtime_rasai_environment_names()
    exposed = set(ENV_NAMES)
    missing = sorted(discovered - exposed)
    assert not missing, "runtime environment variables missing from console catalog: " + ", ".join(missing)


def test_provider_environment_contract_is_in_console_catalog() -> None:
    assert set(provider_environment_names()).issubset(set(ENV_NAMES))


def test_every_exposed_environment_variable_has_metadata() -> None:
    assert set(SPEC_BY_NAME) == set(ENV_NAMES)
    assert all(SPEC_BY_NAME[name].purpose for name in ENV_NAMES)
    assert all(SPEC_BY_NAME[name].value_type for name in ENV_NAMES)


def test_experience_apdex_has_a_valid_default_device_distribution() -> None:
    mix = dict(parse_device_mix(DEFAULT_UX_DEVICE_MIX))
    assert set(mix).issubset({"MOBILE", "DESKTOP", "TABLET"})
    assert abs(sum(mix.values()) - 100.0) < 1e-9
    assert SPEC_BY_NAME["RASAI_APDEX_EXPERIENCE_DEVICE_MIX"].default == DEFAULT_UX_DEVICE_MIX
