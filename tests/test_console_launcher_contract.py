from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_windows_console_launcher_is_the_single_current_cmd_entrypoint() -> None:
    launcher = ROOT / "abrir-rasai-console.cmd"
    removed_launcher = ROOT / ("iniciar" + ".cmd")

    assert launcher.is_file()
    assert not removed_launcher.exists()

    text = launcher.read_text(encoding="utf-8").casefold()
    assert "python.python.3.13" in text
    assert ".venv\\scripts\\python.exe" in text
    assert ".venv\\scripts\\rasai-console.exe" in text
    assert "pip install" in text
    assert "playwright install chromium" in text


def test_product_documentation_references_only_current_launcher_and_no_history_labels() -> None:
    removed_name = "iniciar" + ".cmd"
    history_word = re.compile(r"\b(?:legacy|legado)\b", re.IGNORECASE)

    markdown_files = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        assert removed_name not in text, path
        assert history_word.search(text) is None, path


def test_console_modules_do_not_carry_development_history_vocabulary() -> None:
    for path in sorted((ROOT / "src" / "rasai").glob("console*.py")):
        text = path.read_text(encoding="utf-8").casefold()
        assert "legacy" not in text, path
        assert "legado" not in text, path
