from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from rasai.catalog_report_assurance import (
    CATALOG_MATURITY_MIN,
    HIGH_ASSURANCE_MIN,
    _read_only_guard_present,
    _safe_output,
    assess_catalog,
    assurance_matrix_html,
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

def test_security_scanner_ignores_css_sk_classes_but_detects_credential_assignment() -> None:
    ok, failures = _safe_output("<div class='sk-header-content sk-button--loading'></div>")
    assert ok is True
    assert failures == []

    ok, failures = _safe_output("<pre>api_key='prod-value-93af'</pre>")
    assert ok is False
    assert any("credencial" in item for item in failures)


def test_read_only_assurance_follows_materializer_wrapper_chain(monkeypatch) -> None:
    from rasai import catalog_report_site as site

    original = site.materialize_catalog_report_site

    def wrapper(*args, **kwargs):
        return original(*args, **kwargs)

    wrapper._rasai_original = original
    monkeypatch.setattr(site, "materialize_catalog_report_site", wrapper)

    passed, detail = _read_only_guard_present()
    assert passed is True
    assert "fingerprint" in detail


def test_transversal_secret_output_blocks_global_closure(monkeypatch, tmp_path: Path) -> None:
    from rasai import catalog_report_assurance as assurance

    monkeypatch.setattr(
        assurance,
        "assess_catalog",
        lambda _database, _data, catalog_id, _body: {
            "catalog_id": catalog_id,
            "selected": True,
            "functional_status": "CONCLUÍDO",
            "configurability": 100.0,
            "governance": 100.0,
            "exposure": 100.0,
            "reliability": 100.0,
            "integrity": 100.0,
            "security": 100.0,
            "maturity": 100.0,
            "high_assurance": 100.0,
            "closure_eligible": True,
            "checks": [],
        },
    )
    result = assurance.assess_catalogs(
        tmp_path / "audit.db",
        SimpleNamespace(),
        {"ai-integrations.html": "<pre>api_key='prod-value-93af'</pre>"},
    )
    assert result["global_output_security"]["passed"] is False
    assert "ai-integrations.html" in result["global_output_security"]["failures"]
    assert result["closure_eligible"] is False

def test_assurance_matrix_explains_each_axis_without_changing_columns() -> None:
    result = {
        "catalogs": [{
            "catalog_id": "CAT-01",
            "selected": True,
            "configurability": 100,
            "governance": 100,
            "exposure": 100,
            "reliability": 100,
            "integrity": 100,
            "security": 100,
            "maturity": 100,
            "closure_eligible": True,
        }],
        "global": {
            "reliability": 100,
            "integrity": 100,
            "security": 100,
            "maturity": 100,
        },
        "global_output_security": {"passed": True, "failures": {}},
        "closure_eligible": True,
    }
    html = assurance_matrix_html(result)

    assert "Matriz de encerramento estrutural" in html
    assert "Como ler os eixos" in html
    for label in (
        "CAT",
        "Configurabilidade",
        "Governança",
        "Exposição",
        "Confiabilidade",
        "Integridade",
        "Segurança",
        "Maturidade",
        "Gate",
    ):
        assert f"<th>{label}</th>" in html
    assert "cobertura de controles" in html
    assert "probabilidade estatística" in html
