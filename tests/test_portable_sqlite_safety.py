from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_portable_sqlite_path_does_not_import_postgresql_runtime(tmp_path: Path) -> None:
    """SQLite must remain usable even if every PostgreSQL module is unavailable.

    This runs in a fresh interpreter so imports from unrelated tests cannot mask an
    accidental PostgreSQL dependency. The import hook deliberately rejects RASAi
    PostgreSQL modules and psycopg; opening and using the SQLite control plane must
    still succeed.
    """

    script = textwrap.dedent(
        f"""
        import importlib.abc
        import os
        from pathlib import Path
        import sys

        class BlockPostgres(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == 'psycopg' or fullname.startswith('psycopg.'):
                    raise ImportError('portable SQLite safety gate blocked psycopg')
                if fullname.startswith('rasai.platform.postgres_'):
                    raise ImportError('portable SQLite safety gate blocked PostgreSQL adapter')
                if fullname.startswith('rasai.search_intelligence.monitoring_postgres'):
                    raise ImportError('portable SQLite safety gate blocked PostgreSQL monitoring adapter')
                return None

        sys.meta_path.insert(0, BlockPostgres())
        os.environ.pop('RASAI_PLATFORM_DB_BACKEND', None)
        os.environ.pop('RASAI_PLATFORM_DATABASE_URL', None)

        from rasai.platform.database import resolve_platform_database_config, open_platform_store
        from rasai.search_intelligence.monitoring_database import open_search_monitoring_repository

        root = Path({str(tmp_path)!r})
        config = resolve_platform_database_config(audits_root=root)
        assert config.backend == 'sqlite'
        assert config.sqlite_database is not None

        with open_platform_store(audits_root=root) as store:
            org, workspace, project, prop, environment = store.ensure_local_hierarchy(
                project_name='Portable SQLite',
                origin='https://portable.example',
            )
            assert store.counts()['organizations'] == 1
            assert project.project_id.startswith('PRJ-')
            assert prop.property_id.startswith('PTY-')
            assert environment.environment_id.startswith('ENV-')

        with open_search_monitoring_repository(audits_root=root) as repository:
            assert repository.list_queries() == ()

        forbidden = [
            name for name in sys.modules
            if name == 'psycopg'
            or name.startswith('psycopg.')
            or name.startswith('rasai.platform.postgres_')
            or name.startswith('rasai.search_intelligence.monitoring_postgres')
        ]
        assert forbidden == [], forbidden
        """
    )
    environment = os.environ.copy()
    environment.pop("RASAI_PLATFORM_DB_BACKEND", None)
    environment.pop("RASAI_PLATFORM_DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-c", script],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_portable_cli_help_works_without_postgresql_configuration() -> None:
    environment = os.environ.copy()
    environment.pop("RASAI_PLATFORM_DB_BACKEND", None)
    environment.pop("RASAI_PLATFORM_DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "rasai", "--help"],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RASAi" in result.stdout or "rasai" in result.stdout.casefold()
