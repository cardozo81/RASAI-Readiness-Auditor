from __future__ import annotations

from pathlib import Path
import tempfile

from searchgeo.console_config_migration import (
    CANONICAL_CONSOLE_INI,
    CONSOLE_INI_ENV,
    LEGACY_CONSOLE_INI,
    canonical_console_config_path,
    prepare_console_config,
)


def test_canonical_filename_is_rasai_console_ini() -> None:
    with tempfile.TemporaryDirectory() as directory:
        env: dict[str, str] = {}
        root = Path(directory)
        path = prepare_console_config(env=env, cwd=root)
        assert path == (root / CANONICAL_CONSOLE_INI).resolve()
        assert path.name == "rasai-console.ini"
        assert env[CONSOLE_INI_ENV] == str(path)


def test_legacy_default_is_atomically_migrated() -> None:
    with tempfile.TemporaryDirectory() as directory:
        env: dict[str, str] = {}
        root = Path(directory)
        legacy = root / LEGACY_CONSOLE_INI
        legacy.write_text("[console]\nproject = Existing project\n", encoding="utf-8")

        path = prepare_console_config(env=env, cwd=root)

        assert path == (root / CANONICAL_CONSOLE_INI).resolve()
        assert path.read_text(encoding="utf-8") == "[console]\nproject = Existing project\n"
        assert not legacy.exists()


def test_explicit_override_is_preserved_without_migration() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        legacy = root / LEGACY_CONSOLE_INI
        legacy.write_text("legacy", encoding="utf-8")
        env = {CONSOLE_INI_ENV: "custom-console.ini"}

        path = prepare_console_config(env=env, cwd=root)

        assert path == (root / "custom-console.ini").resolve()
        assert env[CONSOLE_INI_ENV] == "custom-console.ini"
        assert legacy.exists()
        assert not (root / CANONICAL_CONSOLE_INI).exists()


def test_existing_canonical_wins_without_overwriting_legacy() -> None:
    with tempfile.TemporaryDirectory() as directory:
        env: dict[str, str] = {}
        root = Path(directory)
        canonical = root / CANONICAL_CONSOLE_INI
        legacy = root / LEGACY_CONSOLE_INI
        canonical.write_text("canonical", encoding="utf-8")
        legacy.write_text("legacy", encoding="utf-8")

        path = prepare_console_config(env=env, cwd=root)

        assert path == canonical.resolve()
        assert canonical.read_text(encoding="utf-8") == "canonical"
        assert legacy.read_text(encoding="utf-8") == "legacy"


def test_path_query_has_no_side_effects() -> None:
    with tempfile.TemporaryDirectory() as directory:
        env: dict[str, str] = {}
        root = Path(directory)
        path = canonical_console_config_path(env=env, cwd=root)
        assert path == (root / CANONICAL_CONSOLE_INI).resolve()
        assert env == {}
        assert not path.exists()
