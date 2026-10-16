"""Issue #320: discovery report projects M6 architecture only from sealed snapshots."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rasai.m24_reporting import _architecture_section, _load, _page


def _db(tmp_path: Path, *, legacy_without_architecture: bool = False) -> Path:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE pages (page_id TEXT PRIMARY KEY, audit_id TEXT)")
        if legacy_without_architecture:
            connection.execute(
                "CREATE TABLE page_snapshots (snapshot_id TEXT PRIMARY KEY, page_id TEXT, "
                "device TEXT, requested_url TEXT, final_url TEXT)"
            )
        else:
            connection.execute(
                "CREATE TABLE page_snapshots (snapshot_id TEXT PRIMARY KEY, page_id TEXT, "
                "device TEXT, requested_url TEXT, final_url TEXT, architecture_classification TEXT)"
            )
        connection.execute("INSERT INTO pages VALUES ('P-1','AUD-1')")
        connection.execute("INSERT INTO pages VALUES ('P-OTHER','AUD-OTHER')")
        if not legacy_without_architecture:
            for num, arch in enumerate(("CSR_SPA", "STATIC_OR_SSR", "HYDRATED", "MIXED", "UNKNOWN"), 1):
                connection.execute(
                    "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
                    (
                        f"SNP-{num}",
                        "P-1",
                        "MOBILE" if num == 1 else "DESKTOP",
                        "https://example.com/request?z=<script>alert(1)</script>" if num == 1
                        else f"https://example.com/page-{num}",
                        "https://example.com/final" if num == 1 else None,
                        arch,
                    ),
                )
            connection.execute(
                "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
                ("SNP-OTHER", "P-OTHER", "MOBILE", "https://private.invalid/", None, "CSR_SPA"),
            )
        connection.commit()
    finally:
        connection.close()
    return database


def test_discovery_architecture_is_a_read_only_per_snapshot_projection(tmp_path: Path) -> None:
    database = _db(tmp_path)
    workspace = SimpleNamespace(database=database, root=tmp_path)
    original = database.read_bytes()
    data = _load("AUD-1", workspace)
    assert len(data["architectures"]) == 5
    assert all(row["snapshot_id"] != "SNP-OTHER" for row in data["architectures"])
    content = _page(data, tmp_path / "report")
    assert "Como as URLs analisadas são renderizadas" in content
    for label in (
        "SPA renderizada no cliente (CSR)",
        "Estática ou renderizada no servidor (SSR)",
        "Renderizada no servidor com hidratação",
        "Mista",
        "Não determinada",
    ):
        assert label in content
    assert "SNP-1" in content
    assert "Móvel" in content and "Desktop" in content
    assert "URL final:" in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content
    assert "<script>alert(1)</script>" not in content
    assert "private.invalid" not in content
    assert content == _page(_load("AUD-1", workspace), tmp_path / "report")
    assert original == database.read_bytes()


def test_discovery_missing_snapshots_remains_explicitly_unknown(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    sqlite3.connect(database).close()
    data = _load("AUD-1", SimpleNamespace(database=database, root=tmp_path))
    assert data["architectures"] == []
    html = _page(data, tmp_path / "report")
    assert "Arquitetura não determinada" in html
    assert "não possui classificação arquitetural persistida" in html


def test_legacy_missing_classification_column_does_not_infer_static(tmp_path: Path) -> None:
    database = _db(tmp_path, legacy_without_architecture=True)
    data = _load("AUD-1", SimpleNamespace(database=database, root=tmp_path))
    assert data["architectures"] == []
    assert "Arquitetura não determinada" in _architecture_section(data["architectures"])
