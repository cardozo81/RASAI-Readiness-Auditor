from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.report_scope_clarity import enrich_report_scope_clarity


def _workspace(tmp_path: Path) -> SimpleNamespace:
    root = tmp_path / "AUD-TEST"
    report = root / "report"
    report.mkdir(parents=True)
    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE pages(page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            CREATE TABLE page_snapshots(snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT);
            """
        )
        for index in range(1, 4):
            page_id = f"P{index}"
            connection.execute(
                "INSERT INTO pages(page_id,audit_id,normalized_url) VALUES(?,?,?)",
                (page_id, "AUD-TEST", f"https://example.test/{index}"),
            )
            connection.execute(
                "INSERT INTO page_snapshots(snapshot_id,page_id,device) VALUES(?,?,?)",
                (f"S{index}", page_id, "MOBILE"),
            )
        connection.commit()
    finally:
        connection.close()
    return SimpleNamespace(root=root, database=database)


def test_index_explains_group_scope_and_non_average_semantics(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    path = workspace.root / "report" / "index.html"
    path.write_text("<html><body><header><h1>Visão geral</h1></header></body></html>", encoding="utf-8")

    enrich_report_scope_clarity(audit_id="AUD-TEST", workspace=workspace)
    html = path.read_text(encoding="utf-8")

    assert "data-rasai-scope-disclosure='true'" in html
    assert "3 URL(s)" in html
    assert "SARI-001" in html
    assert "não é a nota de uma URL isolada" in html
    assert "mínimo a máximo" in html
    assert "Core Web Vitals" in html


def test_readiness_explains_weight_distribution_across_page_scopes(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    path = workspace.root / "report" / "readiness.html"
    path.write_text("<html><body><header><h1>SARI</h1></header></body></html>", encoding="utf-8")

    enrich_report_scope_clarity(audit_id="AUD-TEST", workspace=workspace)
    html = path.read_text(encoding="utf-8")

    assert "agregados por dispositivo sobre todas as URLs aplicáveis" in html
    assert "peso metodológico é dividido entre os escopos de página" in html
    assert "Não é média simples de páginas" in html


def test_apdex_experience_labels_population_cards_as_per_url(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    path = workspace.root / "report" / "apdex-experience.html"
    path.write_text("<html><body><header><h1>Apdex</h1></header></body></html>", encoding="utf-8")

    enrich_report_scope_clarity(audit_id="AUD-TEST", workspace=workspace)
    first = path.read_text(encoding="utf-8")
    enrich_report_scope_clarity(audit_id="AUD-TEST", workspace=workspace)
    second = path.read_text(encoding="utf-8")

    assert first == second
    assert "Cada card de população representa <strong>uma URL</strong>" in first
