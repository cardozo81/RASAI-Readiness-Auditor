from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from rasai import cli, console_config, console_cost
from rasai.target_file import read_target_entries, validated_target_file
from rasai.target_input_runtime import install


def test_target_file_accepts_utf8_bom_and_plain_utf8(tmp_path: Path) -> None:
    bom = tmp_path / "bom.txt"
    bom.write_bytes(b"\xef\xbb\xbfhttps://example.com/a\nhttps://example.com/b\n")
    plain = tmp_path / "plain.txt"
    plain.write_text("https://example.com/a\nhttps://example.com/b\n", encoding="utf-8")

    assert [item.value for item in read_target_entries(bom)] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    assert [item.value for item in read_target_entries(plain)] == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_target_file_reports_exact_invalid_line(tmp_path: Path) -> None:
    path = tmp_path / "urls.txt"
    path.write_text(
        "# comentário\nhttps://example.com/a\nHTTPSX://example.com/b\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"linha 3") as exc:
        validated_target_file(path, cli.validate_target)
    assert "scheme must be http or https" in str(exc.value)
    assert "HTTPSX://example.com/b" in str(exc.value)


def test_runtime_uses_same_parser_for_cli_console_and_exposure(tmp_path: Path) -> None:
    install()
    path = tmp_path / "urls.txt"
    path.write_bytes(
        b"\xef\xbb\xbfhttps://example.com/a\nhttps://example.com/b\n"
    )

    args = SimpleNamespace(target=[], urls_file=str(path))
    assert cli._audit_targets(args) == (
        "https://example.com/a",
        "https://example.com/b",
    )

    state = console_config.State(
        input_mode="file",
        target=str(path),
        max_pages=2,
        ai_provider="none",
    )
    assert console_config.preflight(state) == (
        "https://example.com/a",
        "https://example.com/b",
    )
    assert console_cost._configured_page_range(state) == (2, 2)


def test_exposure_never_silently_drops_invalid_file_line(tmp_path: Path) -> None:
    install()
    path = tmp_path / "urls.txt"
    path.write_text(
        "https://example.com/a\ninvalid path/without-scheme\n",
        encoding="utf-8",
    )
    state = console_config.State(
        input_mode="file",
        target=str(path),
        max_pages=10,
        ai_provider="none",
    )
    assert console_cost._configured_page_range(state) == (0, 0)
    with pytest.raises(ValueError, match=r"linha 2"):
        console_config.preflight(state)
