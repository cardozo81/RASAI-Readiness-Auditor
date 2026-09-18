from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from rasai.catalog_report_assurance import (
    CATALOG_MATURITY_MIN,
    HIGH_ASSURANCE_MIN,
    assess_catalog,
    catalog_assurance_html,
)


def _body(extra: str = "") -> str:
    return (
        "<section><h2>Configuração efetiva</h2></section>"
        "<section><h2>Resultados</h2></section>"
        "<section><h2>Evidências</h2><p>Fonte materializada</p></section>"
        "<section><h2>Análise e interpretação</h2></section>"
        "<section><h2>Remediações</h2></section>"
        "<section><h2>Detalhes técnicos</h2></section>"
        + extra
    )


def _data(*, secret: bool = False):
    configuration = {
        "targets": ["https://example.test/"],
        "audit_catalog": {"selected": ["CAT-01"]},
    }
    if secret:
        configuration["api_key"] = "secret-value"
    return SimpleNamespace(
        audit_id="AUD-ASSURANCE",
        configuration=configuration,
        config_hash="same",
        computed_hash="same",
        selected={"CAT-01"},
        work_items=[],
    )


def _patch_catalog(monkeypatch) -> None:
    from rasai import catalog_report_catalog_state as state
    from rasai import catalog_report_page as page

    monkeypatch.setattr(
        page,
        "_catalog_status",
        lambda *_args: ("CONCLUÍDO", "good", "Resultado persistido e exposto."),
    )
    monkeypatch.setattr(
        page,
        "_configuration_rows",
        lambda *_args: [
            ("Incluído nesta auditoria", "Sim", "Plano congelado"),
            ("URL / alvo", "https://example.test/", "Plano congelado"),
            ("Uso de IA nesta capacidade", "Não se aplica", "Plano congelado"),
            ("Política de IA", "Não utiliza IA", "Catálogo"),
        ],
    )
    monkeypatch.setattr(
        page,
        "_catalog_sources",
        lambda *_args: [("sample", "Fonte materializada", 1)],
    )
    monkeypatch.setattr(state, "_catalog_source_specs", lambda _catalog_id: ())


def test_catalog_assurance_reaches_closure_targets_when_all_controls_pass(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    database.write_bytes(b"")
    _patch_catalog(monkeypatch)

    result = assess_catalog(database, _data(), "CAT-01", _body())

    assert result["maturity"] >= CATALOG_MATURITY_MIN
    assert result["reliability"] >= HIGH_ASSURANCE_MIN
    assert result["integrity"] >= HIGH_ASSURANCE_MIN
    assert result["security"] >= HIGH_ASSURANCE_MIN
    assert result["closure_eligible"] is True
    html = catalog_assurance_html(result)
    assert "Maturidade estrutural" in html
    assert "ATENDE" in html


def test_secret_in_frozen_configuration_blocks_security_closure(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    database.write_bytes(b"")
    _patch_catalog(monkeypatch)

    result = assess_catalog(database, _data(secret=True), "CAT-01", _body())

    assert result["security"] < HIGH_ASSURANCE_MIN
    assert result["closure_eligible"] is False
    failed = {item["code"] for item in result["checks"] if not item["passed"]}
    assert "SEC_PERSISTED_CONFIG" in failed


def test_unsafe_external_link_blocks_security_closure(monkeypatch, tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    database.write_bytes(b"")
    _patch_catalog(monkeypatch)

    result = assess_catalog(
        database,
        _data(),
        "CAT-01",
        _body("<a href='https://external.test/path'>externo</a>"),
    )

    assert result["security"] < HIGH_ASSURANCE_MIN
    assert result["closure_eligible"] is False
    failed = {item["code"] for item in result["checks"] if not item["passed"]}
    assert "SEC_EXTERNAL_LINKS" in failed
