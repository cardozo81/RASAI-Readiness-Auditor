from __future__ import annotations

from pathlib import Path

from rasai.standards_gsc_console_progress import _key, _workspace_from_root


def test_gsc_console_progress_helpers_are_fail_open_for_missing_root(tmp_path: Path) -> None:
    assert _workspace_from_root(None) is None
    assert _key(None) == "None"

    workspace = _workspace_from_root(tmp_path)
    assert workspace is not None
    assert workspace.root == tmp_path
    assert _key(tmp_path)
