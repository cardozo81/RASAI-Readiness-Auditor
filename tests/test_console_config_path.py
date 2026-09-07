from __future__ import annotations

from pathlib import Path
import tempfile

from rasai.console_config_path import CANONICAL_CONSOLE_INI, CONSOLE_INI_ENV, canonical_console_config_path, prepare_console_config


def test_default_console_path_is_rasai() -> None:
    with tempfile.TemporaryDirectory() as directory:
        env: dict[str, str] = {}
        root = Path(directory)
        path = prepare_console_config(env=env, cwd=root)
        assert path == (root / CANONICAL_CONSOLE_INI).resolve()
        assert env[CONSOLE_INI_ENV] == str(path)


def test_explicit_rasai_console_override_is_preserved() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        env = {CONSOLE_INI_ENV: "custom-console.ini"}
        path = prepare_console_config(env=env, cwd=root)
        assert path == (root / "custom-console.ini").resolve()
        assert canonical_console_config_path(env=env, cwd=root) == path
