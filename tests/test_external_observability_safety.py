from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.external_observability_safety import _common_crawl_block_reason, _unsafe_reason


def _workspace(tmp_path: Path, url: str):
    root = tmp_path / "AUD-SAFE"
    root.mkdir()
    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE pages(audit_id TEXT NOT NULL, normalized_url TEXT NOT NULL)")
        connection.execute("INSERT INTO pages VALUES (?,?)", ("AUD-SAFE", url))
        connection.commit()
    finally:
        connection.close()
    return SimpleNamespace(database=database, root=root)


def test_unsafe_reason_rejects_private_and_parameterized_targets() -> None:
    assert _unsafe_reason("https://openai.com/research") is None
    assert _unsafe_reason("https://openai.com/research?token=abc") == "QUERY_PRESENT"
    assert _unsafe_reason("https://openai.com/research#private") == "FRAGMENT_PRESENT"
    assert _unsafe_reason("https://user:pass@openai.com/private") == "USERINFO_PRESENT"
    assert _unsafe_reason("http://localhost/admin") == "PRIVATE_OR_RESERVED_HOST"
    assert _unsafe_reason("http://10.0.0.1/admin") == "PRIVATE_OR_RESERVED_IP"
    assert _unsafe_reason("http://service.internal/admin") == "PRIVATE_OR_RESERVED_HOST"


def test_common_crawl_default_is_suppressed_for_unsafe_audit_target(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "https://openai.com/path?secret=value")
    monkeypatch.setenv("RASAI_COMMON_CRAWL_ENABLED", "true")
    monkeypatch.setenv("RASAI_COMMON_CRAWL_MAX_URLS", "3")
    reason = _common_crawl_block_reason(workspace=workspace, audit_id="AUD-SAFE")
    assert reason is not None
    assert reason.startswith("PUBLIC_INDEX_TARGET_NOT_SAFE")
    assert "secret=value" not in reason


def test_common_crawl_default_accepts_safe_public_url(monkeypatch, tmp_path: Path) -> None:
    workspace = _workspace(tmp_path, "https://openai.com/research")
    monkeypatch.setenv("RASAI_COMMON_CRAWL_ENABLED", "true")
    monkeypatch.setenv("RASAI_COMMON_CRAWL_MAX_URLS", "3")
    assert _common_crawl_block_reason(workspace=workspace, audit_id="AUD-SAFE") is None
