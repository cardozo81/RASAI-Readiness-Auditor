from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tomllib
import unittest

from rasai import __version__
from rasai import cli


ROOT = Path(__file__).resolve().parents[1]


class VersionContractTests(unittest.TestCase):
    def test_package_version_matches_pyproject(self) -> None:
        project = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(project["version"], __version__)

    def test_cli_version_reports_package_version(self) -> None:
        parser = cli.build_parser()
        output = StringIO()
        with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            parser.parse_args(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), f"rasai {__version__}")


if __name__ == "__main__":
    unittest.main()
