"""Ephemeral Windows/User persistence acceptance on a hosted Windows runner.

No operator secrets, no real provider invocation and no INI or AUD writes.
The unique disposable registry value is always removed in finally.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from uuid import uuid4

import pytest

from rasai.windows_environment import (
    activate_persisted_environment,
    persist_user_environment,
    remove_user_environment,
    user_environment_value,
)


@pytest.mark.skipif(os.name != "nt", reason="real Windows/User registry only")
def test_ephemeral_windows_user_value_survives_fresh_process_without_paid_intent():
    """End-to-end roundtrip through RASAi's real HKCU adapter and another process."""
    name = "RASAI_SMOKE_EPHEMERAL_" + uuid4().hex.upper()
    value = "nonsecret-disposable-ci-sentinel"
    assert user_environment_value(name) is None
    assert name not in os.environ
    try:
        persist_user_environment(name, value)
        assert user_environment_value(name) == value
        assert name not in os.environ

        child_code = """
import json, os, sys
from rasai.windows_environment import (
    user_environment_value, activate_persisted_environment,
)
key, expected = sys.argv[1:]
assert key not in os.environ
assert user_environment_value(key) == expected
assert activate_persisted_environment([key]) == (key,)
assert os.environ.get(key) == expected
os.environ[key] = "explicit-process-override"
assert activate_persisted_environment([key]) == ()
assert os.environ[key] == "explicit-process-override"
assert activate_persisted_environment([key], overwrite=True) == (key,)
assert os.environ[key] == expected
print(json.dumps({"registry_roundtrip": True, "no_paid_consent": True}))
"""
        environment = dict(os.environ)
        environment.pop(name, None)
        result = subprocess.run(
            [sys.executable, "-c", child_code, name, value],
            env=environment, check=True, capture_output=True,
            text=True, timeout=35,
        )
        evidence = json.loads(result.stdout)
        assert evidence == {"registry_roundtrip": True, "no_paid_consent": True}
    finally:
        remove_user_environment(name)
    assert user_environment_value(name) is None
    assert name not in os.environ
