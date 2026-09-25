from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from rasai import __version__
from rasai import cli


ROOT = Path(__file__).resolve().parents[1]


def test_package_version_matches_pyproject() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == __version__


def test_cli_version_reports_package_version(capsys: pytest.CaptureFixture[str]) -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"rasai {__version__}"
