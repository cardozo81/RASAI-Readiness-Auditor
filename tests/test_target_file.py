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


def test_public_runtime_accepts_only_one_direct_target(tmp_path: Path) -> None:
    install()
    path = tmp_path / "urls.txt"
    path.write_text("https://example.com/a\nhttps://example.com/b\n", encoding="utf-8")

    assert cli._audit_targets(
        SimpleNamespace(target="https://example.com/a", urls_file=None)
    ) == ("https://example.com/a",)

    with pytest.raises(ValueError, match="--urls-file is not supported"):
        cli._audit_targets(SimpleNamespace(target="", urls_file=str(path)))

    with pytest.raises(ValueError, match="exactly one"):
        cli._audit_targets(
            SimpleNamespace(
                target=["https://example.com/a", "https://example.com/b"],
                urls_file=None,
            )
        )

    state = console_config.State(
        input_mode="file",
        target=str(path),
        max_pages=2,
        ai_provider="none",
    )
    assert console_cost._configured_page_range(state) == (0, 0)
    with pytest.raises(ValueError, match="URL única"):
        console_config.preflight(state)


def test_target_file_parser_remains_available_for_historical_internal_readers(tmp_path: Path) -> None:
    path = tmp_path / "urls.txt"
    path.write_text(
        "https://example.com/a\nhttps://example.com/b\n",
        encoding="utf-8",
    )
    assert validated_target_file(path, cli.validate_target) == (
        "https://example.com/a",
        "https://example.com/b",
    )
