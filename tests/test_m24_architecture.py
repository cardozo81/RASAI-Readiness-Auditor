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
    assert _architecture_section(data["architectures"]) == _architecture_section(
        _load("AUD-1", workspace)["architectures"]
    )
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


def test_architecture_projection_labels_observation_not_effective_profile(tmp_path: Path) -> None:
    database = _db(tmp_path)
    data = _load("AUD-1", SimpleNamespace(database=database, root=tmp_path))
    html = _architecture_section(data["architectures"])
    assert html.count("descoberta automática registrada nesta captura") == 5
    assert html.count("não propagada a parâmetros de coleta ou índices") == 5
    assert html.count("Configuração declarada:</strong> N/D") == 5
    assert "arquitetura aplicada automaticamente" not in html.lower()



def test_architecture_report_discloses_sealed_choice_without_replacing_observation(tmp_path):
    from rasai.audit_configuration_reuse import (
        persist_audit_configuration, KIND_CONSOLE,
    )
    from rasai.architecture_choice import ArchitectureChoice, write_choice

    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE audits (audit_id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO audits VALUES ('AUD-1')")
    stored = persist_audit_configuration(
        db, audit_id="AUD-1", kind=KIND_CONSOLE,
        configuration=write_choice({"settings": {}}, ArchitectureChoice("DECLARED", "HYDRATED")),
    )
    before = db.read_bytes()
    result = _load("AUD-1", SimpleNamespace(database=db, root=tmp_path))
    html = _page(result, tmp_path / "report")
    assert result["architecture_choice_status"] == "SEALED_SELECTION"
    assert html.count("Seleção arquitetural desta AUD:") == 5
    assert html.count("HYDRATED (informada pelo operador)") == 5
    assert html.count("Divergência com a observação") == 3
    assert html.count("não propagada a parâmetros de coleta ou índices") == 5
    assert "arquitetura aplicada automaticamente" not in html.lower()
    assert stored.configuration_hash
    assert db.read_bytes() == before


def test_architecture_report_abstains_on_corrupted_choice_seal(tmp_path):
    from rasai.audit_configuration_reuse import persist_audit_configuration, KIND_CONSOLE
    from rasai.architecture_choice import ArchitectureChoice, write_choice

    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE audits (audit_id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO audits VALUES ('AUD-1')")
    persist_audit_configuration(
        db, audit_id="AUD-1", kind=KIND_CONSOLE,
        configuration=write_choice({}, ArchitectureChoice("DECLARED", "CSR_SPA")),
    )
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE audit_execution_configurations SET configuration_hash=? WHERE audit_id=?",
            ("invalid-checksum", "AUD-1"),
        )
    before = db.read_bytes()
    data = _load("AUD-1", SimpleNamespace(database=db, root=tmp_path))
    html = _page(data, tmp_path / "report")
    assert data["architecture_choice"] is None
    assert data["architecture_choice_status"] == "INTEGRITY_NOT_VERIFIED"
    assert html.count("não verificável (integridade do registro não comprovada)") == 5
    assert "CSR_SPA (informada pelo operador)" not in html
    assert db.read_bytes() == before


def test_architecture_report_legacy_mode_has_no_extra_choice_claim(tmp_path):
    db = _db(tmp_path)
    result = _load("AUD-1", SimpleNamespace(database=db, root=tmp_path))
    assert result["architecture_choice"] is None
    assert result["architecture_choice_status"] == "LEGACY_ABSENT"
    html = _page(result, tmp_path / "report")
    assert html.count("Configuração declarada:</strong> N/D") == 5
    assert "Seleção arquitetural desta AUD:" not in html



def test_architecture_report_legacy_config_table_without_hash_stays_readable(tmp_path):
    db = _db(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE audit_execution_configurations "
                    "(audit_id TEXT PRIMARY KEY, configuration_json TEXT)")
        con.execute(
            "INSERT INTO audit_execution_configurations VALUES (?,?)",
            ("AUD-1", '{"architecture_choice":{"mode":"DECLARED","declared_architecture":"CSR_SPA"}}'),
        )
    original = db.read_bytes()
    result = _load("AUD-1", SimpleNamespace(database=db, root=tmp_path))
    html = _page(result, tmp_path / "report")
    assert result["architecture_choice"] is None
    assert result["architecture_choice_status"] == "INTEGRITY_NOT_VERIFIED"
    assert "CSR_SPA (informada pelo operador)" not in html
    assert db.read_bytes() == original
