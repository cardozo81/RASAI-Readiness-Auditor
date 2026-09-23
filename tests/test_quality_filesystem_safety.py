from __future__ import annotations

from pathlib import Path
import tempfile

from rasai.quality.content_controls import _read


def test_content_control_reader_rejects_parent_traversal() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        workspace = root / "AUD-X"
        workspace.mkdir()
        secret = root / "secret.html"
        secret.write_text("<span data-nosnippet>secret</span>", encoding="utf-8")
        assert _read(workspace, "../secret.html") is None


def test_content_control_reader_reads_in_workspace_artifact() -> None:
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory) / "AUD-X"
        artifact = workspace / "artifacts" / "page.html"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("<span data-nosnippet>ok</span>", encoding="utf-8")
        assert _read(workspace, "artifacts/page.html") == "<span data-nosnippet>ok</span>"
